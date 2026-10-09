// Progressive enhancement only: every form and link works without this file.
(function () {
  "use strict";

  var dialog = document.getElementById("login-dialog");

  document.querySelectorAll("[data-open-login]").forEach(function (link) {
    link.addEventListener("click", function (event) {
      if (!dialog || typeof dialog.showModal !== "function") { return; }
      event.preventDefault();
      dialog.showModal();
      var email = dialog.querySelector("input[name=email]");
      if (email) { email.focus(); }
    });
  });

  document.querySelectorAll("[data-close-login]").forEach(function (button) {
    button.addEventListener("click", function () { dialog.close(); });
  });

  document.querySelectorAll("[data-toggle-password]").forEach(function (button) {
    button.addEventListener("click", function () {
      var input = button.parentElement.querySelector("input");
      var isHidden = input.type === "password";
      input.type = isHidden ? "text" : "password";
      button.textContent = isHidden ? "Hide" : "Show";
      button.setAttribute("aria-pressed", String(isHidden));
    });
  });
})();
