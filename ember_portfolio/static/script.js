/* Sri Lochana portfolio: front-end behaviour (plain JavaScript, no libraries). */
(function () {
  "use strict";

  // If the page is ever hosted separately from the API, set window.API_BASE
  // (for example "https://my-api.onrender.com") before this script loads.
  var API_BASE = window.API_BASE || "";

  /* ---------- mobile navigation ---------- */
  var toggle = document.getElementById("navToggle");
  var links = document.getElementById("navLinks");
  toggle.addEventListener("click", function () {
    var open = links.classList.toggle("open");
    toggle.setAttribute("aria-expanded", String(open));
  });
  links.addEventListener("click", function (e) {
    if (e.target.tagName === "A") {
      links.classList.remove("open");
      toggle.setAttribute("aria-expanded", "false");
    }
  });

  /* ---------- pixel icons: 8x8 bitmaps drawn as SVG squares ---------- */
  var ICONS = {
    code:  ["........", ".#....#.", "#.#..#.#", "#..##..#", "#.#..#.#", ".#....#.", "........", "........"],
    brain: ["..####..", ".#.##.#.", "##.##.##", "#.####.#", "##.##.##", ".#.##.#.", "..####..", "........"],
    chip:  [".#.##.#.", "########", "##....##", "#.####.#", "#.####.#", "##....##", "########", ".#.##.#."],
    bulb:  ["..####..", ".######.", ".######.", ".######.", "..####..", "..#..#..", "..####..", "...##..."],
    pot:   ["..#..#..", "...#..#.", "........", "########", "#......#", "########", ".######.", ".######."]
  };
  var COLORS = { code: "#ffb3d9", brain: "#b9a6f0", chip: "#8fc4ff", bulb: "#ffb3d9", pot: "#e0399e" };

  document.querySelectorAll(".px-icon").forEach(function (el) {
    var name = el.getAttribute("data-icon");
    var rows = ICONS[name];
    if (!rows) return;
    var rects = "";
    rows.forEach(function (row, y) {
      row.split("").forEach(function (cell, x) {
        if (cell === "#") rects += '<rect x="' + x + '" y="' + y + '" width="1" height="1"/>';
      });
    });
    el.innerHTML = '<svg viewBox="0 0 8 8" fill="' + COLORS[name] + '">' + rects + "</svg>";
  });

  /* ---------- project detail dialogs ---------- */
  document.querySelectorAll("[data-dialog]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var dlg = document.getElementById(btn.getAttribute("data-dialog"));
      if (dlg && typeof dlg.showModal === "function") dlg.showModal();
    });
  });
  document.querySelectorAll("dialog.modal").forEach(function (dlg) {
    // Clicking the dark backdrop closes the dialog
    dlg.addEventListener("click", function (e) {
      if (e.target === dlg) dlg.close();
    });
  });

  /* ---------- contact form ---------- */
  var form = document.getElementById("contactForm");
  var sendBtn = document.getElementById("sendBtn");
  var statusEl = document.getElementById("formStatus");
  var messageEl = document.getElementById("message");
  var countEl = document.getElementById("count");
  var sending = false; // blocks double submissions

  messageEl.addEventListener("input", function () {
    countEl.textContent = messageEl.value.length;
  });

  function setStatus(kind, text) {
    statusEl.className = "form-status " + kind; // replaces any earlier message
    statusEl.textContent = text;
  }

  function clearErrors() {
    ["name", "email", "message"].forEach(function (f) {
      document.getElementById("err-" + f).textContent = "";
      document.getElementById(f).closest(".field").classList.remove("invalid");
    });
  }

  function showFieldErrors(errors) {
    var first = null;
    Object.keys(errors || {}).forEach(function (field) {
      var out = document.getElementById("err-" + field);
      if (!out) return;
      out.textContent = errors[field];
      var input = document.getElementById(field);
      input.closest(".field").classList.add("invalid");
      if (!first) first = input;
    });
    if (first) first.focus();
  }

  // Same rules as the server, so people get quick feedback. The server re-checks everything.
  function validate(data) {
    var errors = {};
    var name = data.name.trim().replace(/\s+/g, " ");
    if (name.length < 2 || name.length > 80) errors.name = "Please enter your name (2 to 80 characters).";
    if (!/^[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}$/.test(data.email.trim()))
      errors.email = "Please enter a valid email address.";
    var msg = data.message.trim();
    if (msg.length < 10 || msg.length > 2000) errors.message = "Your message should be between 10 and 2000 characters.";
    return errors;
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    if (sending) return;

    var data = {
      name: form.name.value,
      email: form.email.value,
      message: form.message.value,
      website: form.website.value
    };

    clearErrors();
    var problems = validate(data);
    if (Object.keys(problems).length) {
      showFieldErrors(problems);
      setStatus("error", "Please fix the highlighted fields and send again.");
      return;
    }

    sending = true;
    sendBtn.disabled = true;
    sendBtn.textContent = "Sending...";
    setStatus("", "");

    fetch(API_BASE + "/api/contact", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data)
    })
      .then(function (res) {
        return res.json().catch(function () { return {}; }).then(function (body) {
          return { status: res.status, body: body };
        });
      })
      .then(function (r) {
        var body = r.body;
        if (body.ok && body.emailed === false) {
          // Saved in the database, but the email alert failed
          setStatus("warn", body.message);
          form.reset();
          countEl.textContent = "0";
        } else if (body.ok) {
          setStatus("ok", body.message);
          form.reset();
          countEl.textContent = "0";
        } else if (r.status === 422) {
          showFieldErrors(body.errors);
          setStatus("error", body.message || "Please check the highlighted fields.");
        } else {
          setStatus("error", body.message || "Your message could not be sent. Please try again.");
        }
      })
      .catch(function () {
        setStatus("error", "Could not reach the server. Check your connection and try again.");
      })
      .then(function () {
        sending = false;
        sendBtn.disabled = false;
        sendBtn.textContent = "Send message";
      });
  });
})();
