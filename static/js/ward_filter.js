// Keep ward suggestions relevant to the selected area without restricting typed ward numbers.
(function () {
  "use strict";
  const area = document.getElementById("id_area"), ward = document.getElementById("id_ward");
  const list = document.getElementById("ward-suggestions");
  if (!area) return;
  if (ward && ward.tagName === "SELECT") {
    function filterSelect() {
      let keep = false;
      Array.from(ward.options).forEach(function (option) {
        if (!option.value) return;
        const visible = !area.value || option.dataset.area === area.value;
        option.hidden = !visible; option.disabled = !visible;
        if (visible && option.selected) keep = true;
      });
      if (!keep) ward.value = "";
    }
    area.addEventListener("change", filterSelect);
    filterSelect();
    return;
  }
  if (!list) return;
  const options = Array.from(list.options);
  function filterWards() {
    const fragment = document.createDocumentFragment();
    options.forEach(function (option) {
      if (!area.value || option.dataset.area === area.value) fragment.appendChild(option);
    });
    list.textContent = "";
    list.appendChild(fragment);
  }
  area.addEventListener("change", filterWards);
  filterWards();
})();
