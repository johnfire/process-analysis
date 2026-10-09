# Deployment

Push to `main` → CI (lint, types, tests, integration on Postgres, score ratchet, dependency audit,
secret scan) → image `ghcr.io/johnfire/process-analysis:<sha>` → SSH to the VPS → migrate → import the synthetic corpus (`python -m web.manage import-seed`, safe to repeat) → `up -d`
→ `/health` on the VPS → `/health` and the landing page over HTTPS. The VPS never builds; it pulls.

Live at `https://process-analysis.christopherrehm.de`. Container port 8000, published only on
`127.0.0.1:8110`; Apache on the host terminates TLS.

## One-time setup

Done once, by hand. After it, every push to `main` deploys.

1. **DNS:** `process-analysis  A  82.165.32.162` on christopherrehm.de.
2. **GitHub secrets** on `johnfire/process-analysis`: `VPS_HOST`, `VPS_USER`, `VPS_PORT`,
   `VPS_SSH_KEY` (same values as flashkarte's).
3. **VPS checkout and secrets:**
   ```bash
   ssh claude@82.165.32.162
   sudo git clone https://github.com/johnfire/process-analysis.git /opt/process-analysis
   sudo chown -R claude:claude /opt/process-analysis
   cd /opt/process-analysis
   cp .env.example .env
   sed -i "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$(openssl rand -hex 24)/" .env
   chmod 600 .env
   ```
4. **Apache and certificate** (after DNS resolves):
   ```bash
   sudo cp deploy/apache/process-analysis.conf /etc/apache2/sites-available/
   sudo a2ensite process-analysis
   sudo apache2ctl configtest && sudo systemctl reload apache2
   sudo certbot --apache -d process-analysis.christopherrehm.de
   ```
5. Push to `main` (or re-run the workflow) and watch the `verify-live` job go green.

## First user

Signup is invitation-only, so the first administrator is created on the server. Everyone after that
is invited from the **Invites** page. `-t` is needed because the command asks for the password
without echoing it:

```bash
ssh -t claude@82.165.32.162 'cd /opt/process-analysis && \
  docker compose -f docker-compose.prod.yml exec web python -m web.manage create-user you@example.com'
```

Locked out? `python -m web.manage set-password you@example.com` (same way) sets a new password and
signs out every session. Without `MAIL_*` in `.env` the emailed links cannot be sent: the Invites
page shows the invitation link on screen instead, and a forgotten password needs `set-password`.

## Model providers

Extraction calls a provider's API from the worker. In `/opt/process-analysis/.env`:

```
PROVIDERS_ENABLED=openrouter,deepseek         # which providers the forms offer
SENSITIVE_OK_PROVIDERS=openrouter             # the subset YOU have approved for sensitive clients
OPENROUTER_API_KEY=...                        # keys reach the worker only, never the web container
```

Then `docker compose -f docker-compose.prod.yml up -d web worker`. Leaving `SENSITIVE_OK_PROVIDERS`
empty means sensitive clients can use no provider at all, which is the safe default. Approving a
provider is your statement that you have read its data-handling terms; the software cannot check.
Read `docs/PRIVACY.md` first.

## Operating

- Health: `curl -s http://127.0.0.1:8110/health` on the VPS; reports database, migrations, worker.
- Logs: `docker compose -f docker-compose.prod.yml logs -f web worker` (JSON lines with
  `correlation_id`).
- Roll back: `IMAGE_TAG=<older sha> docker compose -f docker-compose.prod.yml up -d web worker`.
  Migrations are forward-only in production; a rollback across a migration needs its own plan.
- Backups: daily dumps in `/opt/process-analysis/backups` (7 daily, 4 weekly, 3 monthly).
