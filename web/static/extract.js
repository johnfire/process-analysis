// Picking a provider suggests that provider's usual model, unless the person has typed their own.
(function () {
  "use strict";

  var model = document.getElementById("model");
  if (!model) { return; }
  var hasTypedOwnModel = false;
  model.addEventListener("input", function () { hasTypedOwnModel = true; });

  document.querySelectorAll('input[name="provider"]').forEach(function (radio) {
    radio.addEventListener("change", function () {
      if (!hasTypedOwnModel) { model.value = radio.getAttribute("data-model") || ""; }
    });
  });
})();
