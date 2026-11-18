// Site-wide behaviour. Page-specific scripts (maps, complaint form) live in their own files.
// No inline event handlers are used anywhere, so the Content-Security-Policy can forbid inline scripts.
document.addEventListener("DOMContentLoaded", function () {
  // Bootstrap toasts rendered by the server are shown so they dismiss themselves.
  document.querySelectorAll(".toast").forEach(function (el) {
    bootstrap.Toast.getOrCreateInstance(el).show();
  });

  // Password fields get a show/hide control. The input, its name, id and validation are untouched.
  document.querySelectorAll("input[type=password]").forEach(function (input) {
    if (input.closest(".rp-pw")) return;
    const wrap = document.createElement("div");
    wrap.className = "rp-pw";
    input.parentNode.insertBefore(wrap, input);
    wrap.appendChild(input);
    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "rp-pw-toggle";
    toggle.setAttribute("aria-label", "Show password");
    toggle.setAttribute("aria-pressed", "false");
    const icon = document.createElement("i");
    icon.className = "ic ic-eye";
    icon.setAttribute("aria-hidden", "true");
    toggle.appendChild(icon);
    toggle.addEventListener("click", function () {
      const show = input.type === "password";
      input.type = show ? "text" : "password";
      icon.className = "ic " + (show ? "ic-eye-off" : "ic-eye");
      toggle.setAttribute("aria-label", show ? "Hide password" : "Show password");
      toggle.setAttribute("aria-pressed", show ? "true" : "false");
    });
    wrap.appendChild(toggle);
  });
});

// <button data-confirm="..."> or <form data-confirm="..."> asks before doing something that is hard to undo.
// A styled dialog (#rpConfirm in base.html) is used when available; otherwise the browser's confirm() box.
(function () {
  function ask(message, onYes) {
    const el = document.getElementById("rpConfirm");
    if (!el || !window.bootstrap || !bootstrap.Modal) { if (window.confirm(message)) onYes(); return; }
    const modal = bootstrap.Modal.getOrCreateInstance(el);
    const ok = document.getElementById("rpConfirmOk");
    document.getElementById("rpConfirmMessage").textContent = message;
    let accepted = false;
    const accept = function () { accepted = true; modal.hide(); };
    const done = function () {
      ok.removeEventListener("click", accept);
      el.removeEventListener("hidden.bs.modal", done);
      if (accepted) onYes();
    };
    ok.addEventListener("click", accept);
    el.addEventListener("hidden.bs.modal", done);
    el.addEventListener("shown.bs.modal", function focusSafe() {
      el.removeEventListener("shown.bs.modal", focusSafe);
      const cancel = el.querySelector("[data-bs-dismiss=modal]:not(.btn-close)");
      if (cancel) cancel.focus();
    });
    modal.show();
  }

  document.addEventListener("click", function (event) {
    const button = event.target.closest("button[data-confirm], a[data-confirm]");
    if (!button) return;
    if (button.dataset.rpConfirmed) { delete button.dataset.rpConfirmed; return; }
    event.preventDefault();
    ask(button.dataset.confirm, function () {
      const form = button.form;
      if (button.tagName === "A") { window.location.href = button.href; }
      else if (form && form.requestSubmit) { button.dataset.rpConfirmed = "1"; form.requestSubmit(button); delete button.dataset.rpConfirmed; }
      else { button.dataset.rpConfirmed = "1"; button.click(); }
    });
  });

  document.addEventListener("submit", function (event) {
    const form = event.target;
    if (form.dataset.confirm && !form.dataset.rpConfirmed) {
      event.preventDefault();
      const submitter = event.submitter;
      ask(form.dataset.confirm, function () {
        form.dataset.rpConfirmed = "1";
        if (form.requestSubmit) { submitter ? form.requestSubmit(submitter) : form.requestSubmit(); } else { form.submit(); }
      });
      return;
    }
    delete form.dataset.rpConfirmed;
    // <form data-busy="Working..."> disables its button after the click so a slow action is not sent twice.
    // Skipped when another handler (e.g. the complaint form's location check) already blocked the submit.
    if (form.dataset.busy && !event.defaultPrevented) {
      const button = form.querySelector("button[type=submit], button:not([type])");
      if (button) {
        setTimeout(function () {
          button.dataset.rpLabel = button.innerHTML;
          button.disabled = true;
          button.textContent = "";
          const spinner = document.createElement("span");
          spinner.className = "spinner-border spinner-border-sm";
          spinner.setAttribute("aria-hidden", "true");
          button.appendChild(spinner);
          button.appendChild(document.createTextNode(" " + form.dataset.busy));
        }, 0);
      }
    }
  });

  // Returning with the browser's Back button can restore a page from cache with its button still disabled.
  window.addEventListener("pageshow", function (event) {
    if (!event.persisted) return;
    document.querySelectorAll("button[data-rp-label]").forEach(function (b) { b.innerHTML = b.dataset.rpLabel; b.disabled = false; });
  });
})();
