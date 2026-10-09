// Follows a running extraction job by asking the server for its status. Progressive enhancement:
// without this file the page still shows the state it was loaded with.
(function () {
  "use strict";

  var root = document.getElementById("job");
  if (!root) { return; }
  var url = root.getAttribute("data-status-url");
  var POLL_MILLISECONDS = 2000;

  function field(name) { return root.querySelector('[data-field="' + name + '"]'); }

  function cell(text) {
    var element = document.createElement("td");
    element.textContent = text;
    return element;
  }

  function renderRow(entry) {
    var row = document.createElement("tr");
    row.appendChild(cell(entry.name || entry.person_key));
    row.appendChild(cell(entry.state + (entry.error ? ": " + entry.error : "")));
    row.appendChild(cell(entry.claims === undefined ? "" : String(entry.claims)));
    var dropped = entry.ungrounded === undefined ? "" : entry.ungrounded + " not quoted exactly, " + entry.invalid + " invalid";
    row.appendChild(cell(dropped));
    return row;
  }

  function render(state) {
    field("status").textContent = state.status.replace(/_/g, " ");
    field("tokens").textContent = (state.tokens_in + state.tokens_out).toLocaleString();
    var errorBox = field("error");
    errorBox.textContent = state.error || "";
    errorBox.hidden = !state.error;
    var body = field("progress");
    body.replaceChildren.apply(body, state.progress.map(renderRow));
    if (state.is_finished) {
      field("results-link").hidden = false;
      var cancel = root.querySelector("form");
      if (cancel) { cancel.remove(); }
    }
  }

  function poll() {
    fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (response) { return response.ok ? response.json() : Promise.reject(response.status); })
      .then(function (state) {
        render(state);
        if (!state.is_finished) { window.setTimeout(poll, POLL_MILLISECONDS); }
      })
      .catch(function () { window.setTimeout(poll, POLL_MILLISECONDS * 3); });
  }

  if (!root.querySelector('[data-field="results-link"]').hidden) { return; }
  window.setTimeout(poll, POLL_MILLISECONDS);
})();
