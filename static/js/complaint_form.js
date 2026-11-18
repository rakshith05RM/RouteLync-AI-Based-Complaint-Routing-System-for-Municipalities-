// Complaint form behaviour: optional GPS capture, counters and image pre-checks.
// All of this is a convenience. The server re-validates everything.
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);

  // ---- Description counters: characters, and words against the required minimum
  const desc = $("id_description"), count = $("desc-count"), words = $("desc-words");
  if (desc && count) {
    const update = function () {
      count.textContent = desc.value.length;
      if (words) {
        const min = parseInt(words.dataset.min, 10) || 0;
        const n = (desc.value.match(/[^\s]+/g) || []).length;
        words.textContent = n >= min ? n + " words" : n + " of at least " + min + " words";
        words.className = n >= min ? "text-success" : "text-secondary";
      }
    };
    desc.addEventListener("input", update); update();
  }

  // (GPS and map selection live in location_picker.js)

  // ---- Image pre-check (the server is the real authority)
  const file = $("id_image"), msg = $("image-msg");
  if (file) {
    file.addEventListener("change", function () {
      msg.textContent = "";
      const f = file.files[0];
      if (!f) return;
      const max = parseInt(file.dataset.maxBytes, 10);
      if (["image/jpeg", "image/png", "image/webp"].indexOf(f.type) === -1) {
        msg.textContent = "Please choose a JPG, PNG or WEBP image."; file.value = "";
      } else if (max && f.size > max) {
        msg.textContent = "That image is larger than " + Math.round(max / 1048576) + " MB."; file.value = "";
      }
    });
  }
})();
