/* Runtime enhancement for the prebuilt Palletizer DB site.
 *
 * The React app ships as a compiled bundle (no source to rebuild), so we can't
 * edit its components. We augment it at runtime instead:
 *
 *   1) Embed a 3D pallet visualizer (boxes grouped by SKU) INSIDE the order
 *      "View" modal — served from /viz filtered to that order.
 *   2) Fix the tiny isometric box thumbnails. The bundled glyph scales boxes at
 *      a fixed "px per unit" tuned for inch-magnitude numbers; with metric dims
 *      (~0.2 m) every box collapses to ~1px. We rescale each box-viz SVG to fit
 *      its glyph, unit-agnostically, by reading its own polygon proportions.
 */
(function () {
  "use strict";
  const DN = Math.sqrt(3) / 2, TR = 0.5;
  const assetBase = new URL('.', document.currentScript.src);
  const loadScript = file => new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = new URL(file, assetBase);
    script.onload = resolve; script.onerror = reject;
    document.head.appendChild(script);
  });
  const panelReady = loadScript('result-dataset.js?v=2').then(() => loadScript('order-panel.js?v=3'));
  const css = document.createElement('link');
  css.rel = 'stylesheet'; css.href = new URL('order-panel.css?v=3', assetBase);
  document.head.appendChild(css);

  // ---- (2) mini isometric box thumbnails ---------------------------------
  function pts(str) {
    return str.trim().split(/\s+/).map((p) => p.split(",").map(Number));
  }
  function dist(a, b) { return Math.hypot(a[0] - b[0], a[1] - b[1]); }

  function fixBoxSvg(svg) {
    if (svg.dataset.viz3dFixed) return;
    const polys = svg.querySelectorAll("polygon");
    if (polys.length < 3) return;
    // creation order in the bundle: right, front, top
    const right = pts(polys[0].getAttribute("points"));
    const front = pts(polys[1].getAttribute("points"));
    if (front.length < 4 || right.length < 4) return;
    const j = front[0], w = front[1], d = front[3], p = right[1];
    let g = dist(j, w), f = dist(w, p), h = Math.abs(j[1] - d[1]);
    if (!(g > 0) || !(f > 0) || !(h > 0)) { svg.dataset.viz3dFixed = "1"; return; }
    // rescale to fill the 120x95 viewBox (same geometry the bundle uses)
    const o = (g + f) * DN, u = (g + f) * TR + h;
    const factor = Math.min(88 / o, 58 / u);
    g *= factor; f *= factor; h *= factor;
    const S = 60 - (g - f) * DN / 2, y = 88;
    const P = {
      j: [S, y], w: [S + g * DN, y - g * TR],
      p: [S + g * DN - f * DN, y - g * TR - f * TR],
      d: [S, y - h], m: [S + g * DN, y - g * TR - h],
      x: [S + g * DN - f * DN, y - g * TR - f * TR - h],
      N: [S - f * DN, y - f * TR - h],
    };
    const s = (...a) => a.map((q) => q[0].toFixed(1) + "," + q[1].toFixed(1)).join(" ");
    polys[0].setAttribute("points", s(P.w, P.p, P.x, P.m)); // right
    polys[1].setAttribute("points", s(P.j, P.w, P.m, P.d)); // front
    polys[2].setAttribute("points", s(P.d, P.m, P.x, P.N)); // top
    svg.dataset.viz3dFixed = "1";
  }
  function fixAllBoxes(root) {
    (root || document).querySelectorAll("svg.box-viz:not([data-viz3d-fixed])").forEach(fixBoxSvg);
  }

  // ---- (1) embed 3D pallet inside the order View modal --------------------
  function augmentModal(modal) {
    const body = modal.querySelector(".modal-body") || modal;
    // only order-detail modals carry the box thumbnails
    if (!body.querySelector(".order-detail-box")) return;
    // The order id, taken from the element that holds it rather than scraped out
    // of concatenated text. The modal renders it as
    //   <div class="modal-title">Order: <span class="mono">ORD-99876481</span></div>
    //   <div class="text-muted">Created 8/19/2026, ...</div>
    // and textContent joins adjacent nodes with NO separator, so the old pattern
    // /ORD-[A-Za-z0-9]+/ ran straight past the id into the next line and produced
    // "ORD-99876481Created". That matches no order, so the viewer fell back to the
    // first order in the list — which is why every View showed ORD-00178905.
    // The regex fallback is digits-only for the same reason.
    const mono = modal.querySelector(".modal-title .mono");
    const id = (mono && mono.textContent.trim())
            || ((modal.textContent || "").match(/ORD-[0-9]+/) || [])[0];
    if (!id || !/^ORD-[0-9]+$/.test(id)) return;
    if (body.dataset.viz3d === id && body.querySelector('.op-panel')) return;
    body.dataset.viz3d = id;
    panelReady.then(() => {
      if (body.isConnected && body.dataset.viz3d === id) window.PalletOrderPanel.attach(modal, id);
    }).catch(() => { body.dataset.viz3d = ''; });
  }

  function scan() {
    fixAllBoxes(document);
    document.querySelectorAll(".modal").forEach(augmentModal);
  }

  const obs = new MutationObserver(() => {
    // debounce to a microtask-ish tick so we act after React finishes a render
    if (obs._t) return;
    obs._t = setTimeout(() => { obs._t = null; scan(); }, 30);
  });
  obs.observe(document.body, { childList: true, subtree: true });
  scan();
  console.log("[viz3d] active — embeds 3D in order View modal + fixes box thumbnails.");
})();
