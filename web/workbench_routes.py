"""Creating and deleting clients and processes. Only the owner may change anything."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.engine import Connection
from starlette.datastructures import UploadFile

from web import process_store
from web.audit_trail import record_audit
from web.current_user import SignedInUser, client_address, require_user
from web.page_rendering import render_page
from web.passwords import verify_password
from web.provider_policy import SENSITIVE, SENSITIVITY_LEVELS
from web.upload_parsing import MAX_ROWS, MAX_TRANSCRIPT_CHARACTERS, parse_respondents, parse_terms
from web.viewer_routes import parse_id

router = APIRouter()

MAX_NAME = 200
MAX_UPLOAD_BYTES = 6 * 1024 * 1024  # all transcripts in one form, well above any real interview set
ROW_COUNT = 8
DELETE_PHRASE = "DELETE"


def redirect(location: str) -> RedirectResponse:
    return RedirectResponse(location, status_code=303)


def not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Not found")


@router.get("/clients/new", response_class=HTMLResponse)
def new_client_page(request: Request, user: SignedInUser = Depends(require_user)):
    return render_page(request, "client_new.html", user=user, levels=SENSITIVITY_LEVELS, chosen=SENSITIVE)


@router.post("/clients", response_class=HTMLResponse)
def create_client(
    request: Request,
    name: str = Form(""),
    sensitivity: str = Form(SENSITIVE),
    user: SignedInUser = Depends(require_user),
):
    cleaned = name.strip()
    if not cleaned or len(cleaned) > MAX_NAME or sensitivity not in SENSITIVITY_LEVELS:
        page = render_page(
            request,
            "client_new.html",
            user=user,
            status_code=400,
            levels=SENSITIVITY_LEVELS,
            chosen=sensitivity,
            error="Give the client a name (under 200 characters).",
        )
        return page
    with request.app.state.engine.begin() as connection:
        client_id = process_store.create_client(connection, cleaned, user.user_id, False, sensitivity)
        record_audit(
            connection,
            user.user_id,
            user.email,
            "client_create",
            "success",
            client_address(request),
            str(client_id),
        )
    return redirect(f"/clients/{client_id}")


def confirm_deletion(
    request: Request,
    connection: Connection,
    user: SignedInUser,
    password: str,
    confirmation: str,
    action: str,
    target: UUID,
) -> bool:
    """The second step of a delete: the password and the typed word must both be right."""
    is_confirmed = verify_password(user.password_hash, password) and confirmation.strip() == DELETE_PHRASE
    record_audit(
        connection,
        user.user_id,
        user.email,
        action,
        "success" if is_confirmed else "rejected",
        client_address(request),
        str(target),
    )
    return is_confirmed


@router.get("/clients/{client_id}/delete", response_class=HTMLResponse)
def delete_client_page(request: Request, client_id: str, user: SignedInUser = Depends(require_user)):
    with request.app.state.engine.connect() as connection:
        client = process_store.find_owned_client(connection, parse_id(client_id), user.user_id)
    if client is None:
        raise not_found()
    return render_page(
        request,
        "confirm_delete.html",
        user=user,
        what=f"client “{client.name}” and every process under it",
        action=f"/clients/{client.id}/delete",
        back=f"/clients/{client.id}",
        phrase=DELETE_PHRASE,
    )


@router.post("/clients/{client_id}/delete", response_class=HTMLResponse)
def delete_client(
    request: Request,
    client_id: str,
    password: str = Form(""),
    confirmation: str = Form(""),
    user: SignedInUser = Depends(require_user),
):
    with request.app.state.engine.begin() as connection:
        client = process_store.find_owned_client(connection, parse_id(client_id), user.user_id)
        if client is None:
            raise not_found()
        if not confirm_deletion(
            request, connection, user, password, confirmation, "client_delete", client.id
        ):
            return render_page(
                request,
                "confirm_delete.html",
                user=user,
                status_code=400,
                phrase=DELETE_PHRASE,
                what=f"client “{client.name}” and every process under it",
                action=f"/clients/{client.id}/delete",
                back=f"/clients/{client.id}",
                error="Wrong password, or the word was not typed exactly.",
            )
        process_store.delete_client(connection, client.id)
    return redirect("/clients")


@router.get("/clients/{client_id}/processes/new", response_class=HTMLResponse)
def new_process_page(request: Request, client_id: str, user: SignedInUser = Depends(require_user)):
    with request.app.state.engine.connect() as connection:
        client = process_store.find_owned_client(connection, parse_id(client_id), user.user_id)
    if client is None:
        raise not_found()
    return render_page(request, "process_new.html", user=user, client=client, rows=range(ROW_COUNT), form={})


async def read_uploads(form) -> dict[int, bytes]:
    """Uploaded files by row. Reads one byte past the limit so an oversized file is detected, not trusted."""
    uploaded: dict[int, bytes] = {}
    for row in range(MAX_ROWS):
        file = form.get(f"file_{row}")
        if isinstance(file, UploadFile) and file.filename:
            uploaded[row] = await file.read(MAX_TRANSCRIPT_CHARACTERS * 4 + 1)
    return uploaded


def store_process(request: Request, user: SignedInUser, client_id: UUID, values: dict, respondents) -> UUID:
    cast = [{"person_id": r.person_key, "name": r.name, "role": r.role} for r in respondents]
    with request.app.state.engine.begin() as connection:
        process_id = process_store.create_process(
            connection,
            client_id=client_id,
            slug=None,
            name=values["name"],
            domain=values["domain"],
            organisation={"name": values["organisation"]},
            cast=cast,
            private_terms=values["terms"],
            status="draft",
        )
        process_store.add_transcripts(
            connection, process_id, {r.person_key: r.transcript for r in respondents}
        )
        record_audit(
            connection,
            user.user_id,
            user.email,
            "process_create",
            "success",
            client_address(request),
            str(process_id),
        )
    return process_id


@router.post("/clients/{client_id}/processes", response_class=HTMLResponse)
async def create_process(request: Request, client_id: str, user: SignedInUser = Depends(require_user)):
    if int(request.headers.get("content-length", "0") or 0) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="The upload is too large.")
    client = await run_in_threadpool(_owned_client, request, parse_id(client_id), user)
    form = await request.form()
    fields = {key: str(value) for key, value in form.items() if isinstance(value, str)}
    parsed = parse_respondents(fields, await read_uploads(form))
    terms, term_errors = parse_terms(fields.get("terms", ""))
    values = {
        "name": fields.get("name", "").strip(),
        "domain": fields.get("domain", "").strip(),
        "organisation": fields.get("organisation", "").strip(),
        "terms": terms,
    }
    errors = [*parsed.errors, *term_errors]
    if not values["name"] or not values["domain"]:
        errors.insert(0, "Give the process a name and say what it is.")
    if errors:
        return render_page(
            request,
            "process_new.html",
            user=user,
            status_code=400,
            client=client,
            rows=range(ROW_COUNT),
            form=fields,
            errors=errors,
        )
    process_id = await run_in_threadpool(store_process, request, user, client.id, values, parsed.respondents)
    return redirect(f"/processes/{process_id}")


def _owned_client(request: Request, client_id: UUID, user: SignedInUser):
    with request.app.state.engine.connect() as connection:
        client = process_store.find_owned_client(connection, client_id, user.user_id)
    if client is None:
        raise not_found()
    return client


@router.get("/processes/{process_id}/delete", response_class=HTMLResponse)
def delete_process_page(request: Request, process_id: str, user: SignedInUser = Depends(require_user)):
    with request.app.state.engine.connect() as connection:
        process = process_store.find_owned_process(connection, parse_id(process_id), user.user_id)
    if process is None:
        raise not_found()
    return render_page(
        request,
        "confirm_delete.html",
        user=user,
        what=f"process “{process.name}”, its transcripts and results",
        action=f"/processes/{process.id}/delete",
        back=f"/processes/{process.id}",
        phrase=DELETE_PHRASE,
    )


@router.post("/processes/{process_id}/delete", response_class=HTMLResponse)
def delete_process(
    request: Request,
    process_id: str,
    password: str = Form(""),
    confirmation: str = Form(""),
    user: SignedInUser = Depends(require_user),
):
    with request.app.state.engine.begin() as connection:
        process = process_store.find_owned_process(connection, parse_id(process_id), user.user_id)
        if process is None:
            raise not_found()
        if not confirm_deletion(
            request, connection, user, password, confirmation, "process_delete", process.id
        ):
            return render_page(
                request,
                "confirm_delete.html",
                user=user,
                status_code=400,
                phrase=DELETE_PHRASE,
                what=f"process “{process.name}”, its transcripts and results",
                action=f"/processes/{process.id}/delete",
                back=f"/processes/{process.id}",
                error="Wrong password, or the word was not typed exactly.",
            )
        process_store.delete_process(connection, process.id)
    return redirect(f"/clients/{process.owning_client_id}")
