/**
 * Настройка видимости столбцов таблиц pass_docs (как в Битриксе): чекбоксы + localStorage.
 * Не меняет маршруты и данные на сервере — только классы в DOM.
 */
(function () {
  var STORAGE_PREFIX = "pd_table_cols_v1_";
  var TYPE_CODES_KEY = "pd_show_type_codes_v1";

  function readPrefs(tableId) {
    try {
      var raw = localStorage.getItem(STORAGE_PREFIX + tableId);
      return raw ? JSON.parse(raw) : null;
    } catch (e) {
      return null;
    }
  }

  function writePrefs(tableId, obj) {
    try {
      localStorage.setItem(STORAGE_PREFIX + tableId, JSON.stringify(obj));
    } catch (e) {}
  }

  function colIndexBySlug(table, slug) {
    var ths = table.querySelectorAll("thead tr:first-child th");
    for (var j = 0; j < ths.length; j++) {
      if ((ths[j].dataset.pdCol || "") === slug) return j;
    }
    return -1;
  }

  function setColumnVisible(table, slug, visible) {
    var idx = colIndexBySlug(table, slug);
    if (idx < 0) return;
    var hidden = !visible;
    var rows = table.querySelectorAll("tr");
    for (var r = 0; r < rows.length; r++) {
      var cells = rows[r].children;
      if (cells[idx]) cells[idx].classList.toggle("pd-col-vis-hidden", hidden);
    }
  }

  function defaultVisibility(th) {
    return th.dataset.pdDefaultVis !== "0";
  }

  function applyTablePrefs(table) {
    var id = table.dataset.pdTable;
    if (!id) return;
    var prefs = readPrefs(id);
    var ths = table.querySelectorAll("thead tr:first-child th[data-pd-col]");
    for (var t = 0; t < ths.length; t++) {
      var th = ths[t];
      var slug = th.dataset.pdCol;
      if (!slug) continue;
      var def = defaultVisibility(th);
      var visible =
        prefs && Object.prototype.hasOwnProperty.call(prefs, slug)
          ? !!prefs[slug]
          : def;
      setColumnVisible(table, slug, visible);
    }
  }

  function humanLabel(th) {
    var v = (th.dataset.pdColLabel || "").trim();
    if (v) return v;
    return (th.textContent || "").replace(/\s+/g, " ").trim() || th.dataset.pdCol;
  }

  function fillPanel(panel, table, tableId) {
    panel.innerHTML = "";
    var title = document.createElement("div");
    title.className = "pd-cols-panel__title";
    title.textContent = "Видимость столбцов";
    panel.appendChild(title);

    var ths = table.querySelectorAll("thead tr:first-child th[data-pd-col]");
    var prefs = readPrefs(tableId) || {};

    for (var i = 0; i < ths.length; i++) {
      var th = ths[i];
      var slug = th.dataset.pdCol;
      if (!slug) continue;
      var def = defaultVisibility(th);
      var checked = Object.prototype.hasOwnProperty.call(prefs, slug) ? !!prefs[slug] : def;

      var lab = document.createElement("label");
      lab.className = "pd-cols-panel__row";
      var cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = checked;
      cb.dataset.pdCol = slug;
      lab.appendChild(cb);
      var span = document.createElement("span");
      span.textContent = humanLabel(th);
      lab.appendChild(span);
      panel.appendChild(lab);

      cb.addEventListener("change", function () {
        var p = readPrefs(tableId) || {};
        p[this.dataset.pdCol] = this.checked;
        writePrefs(tableId, p);
        setColumnVisible(table, this.dataset.pdCol, this.checked);
      });
    }

    if (document.querySelector(".pd-tech-inline")) {
      var sep = document.createElement("div");
      sep.className = "pd-cols-panel__sep";
      sep.textContent = "Дополнительно";
      panel.appendChild(sep);
      var lab2 = document.createElement("label");
      lab2.className = "pd-cols-panel__row";
      var cb2 = document.createElement("input");
      cb2.type = "checkbox";
      cb2.className = "js-pd-type-codes";
      cb2.checked = localStorage.getItem(TYPE_CODES_KEY) === "1";
      lab2.appendChild(cb2);
      var sp2 = document.createElement("span");
      sp2.textContent = "Показывать внутренние коды типов";
      lab2.appendChild(sp2);
      panel.appendChild(lab2);
      cb2.addEventListener("change", function () {
        var on = this.checked;
        if (on) localStorage.setItem(TYPE_CODES_KEY, "1");
        else localStorage.removeItem(TYPE_CODES_KEY);
        syncTypeCodes();
        document.querySelectorAll(".js-pd-type-codes").forEach(function (x) {
          if (x !== cb2) x.checked = on;
        });
      });
    }

    var reset = document.createElement("button");
    reset.type = "button";
    reset.className = "pd-btn pd-btn--ghost pd-cols-panel__reset";
    reset.textContent = "Сбросить настройки таблицы";
    reset.addEventListener("click", function () {
      localStorage.removeItem(STORAGE_PREFIX + tableId);
      panel.innerHTML = "";
      fillPanel(panel, table, tableId);
      applyTablePrefs(table);
    });
    panel.appendChild(reset);
  }

  function syncTypeCodes() {
    document.body.classList.toggle(
      "pd-show-type-codes",
      localStorage.getItem(TYPE_CODES_KEY) === "1"
    );
  }

  function bindToolbar(btn) {
    var tid = btn.dataset.pdTableTarget;
    if (!tid) return;
    var table = document.querySelector('table[data-pd-table="' + tid + '"]');
    if (!table) return;
    var toolbar = btn.closest(".pd-cols-toolbar");
    if (!toolbar) return;
    var panel = toolbar.querySelector(".pd-cols-panel");
    if (!panel) return;

    btn.addEventListener("click", function (ev) {
      ev.stopPropagation();
      var open = panel.hidden;
      document.querySelectorAll(".pd-cols-panel").forEach(function (p) {
        p.hidden = true;
      });
      if (open) {
        fillPanel(panel, table, tid);
        panel.hidden = false;
      }
    });

    panel.addEventListener("click", function (ev) {
      ev.stopPropagation();
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("table[data-pd-table]").forEach(applyTablePrefs);
    syncTypeCodes();
    document.querySelectorAll(".js-pd-cols-btn").forEach(bindToolbar);
    document.addEventListener("click", function () {
      document.querySelectorAll(".pd-cols-panel").forEach(function (p) {
        p.hidden = true;
      });
    });
  });
})();
