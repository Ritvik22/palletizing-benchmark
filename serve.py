#!/usr/bin/env python3.11
"""Serve the Palletizer SKU & Order Database (the "packs and cases" dataset UI).

The React frontend is prebuilt (frontend/dist) and the FastAPI backend ships as
sourceless bytecode (backend/*.pyc, Python 3.11). This runner imports the bytecode
app, points it at the bundled SQLite DB, and serves the SPA same-origin so the
frontend's relative API calls (/skus, /orders, /auth, ...) resolve without CORS.

    python3.11 serve.py      # then open http://127.0.0.1:8000
"""
import os
import sys
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
BACKEND = HERE / "backend"
DIST = HERE / "frontend" / "dist"
INDEX = DIST / "index.html"

# database.pyc reads DATABASE_URL; pin it to the bundled DB with an absolute path
# so the app works regardless of the current working directory.
os.environ.setdefault("DATABASE_URL", f"sqlite:///{BACKEND / 'palletizer.db'}")
os.environ.setdefault("SECRET_KEY", "local-dev-secret")

sys.path.insert(0, str(HERE))
from backend import main  # noqa: E402  (bytecode package)
from starlette.staticfiles import StaticFiles  # noqa: E402
from starlette.responses import FileResponse, JSONResponse, HTMLResponse  # noqa: E402
import sqlite3  # noqa: E402

app = main.app

# The API defines its own root "/" handler — drop it so the SPA can own "/".
app.router.routes = [r for r in app.router.routes if getattr(r, "path", None) != "/"]

# ---------------------------------------------------------------------------
# 3D pallet visualizer (/viz) + read-only data endpoints it reads from.
# These query the SQLite DB directly (no auth) so the standalone Three.js page
# can render packs without carrying a bearer token. Local, read-only.
# ---------------------------------------------------------------------------
VIZ = HERE / "viz"
DB_PATH = str(BACKEND / "palletizer.db")
RESULTS = HERE / "results"  # phase-1/2 outputs: <order_id>.placed.json / .remainder.json
RESULTS_EP = HERE / "results_ep"  # full EP packs: <order_id>.packformation.json
RESULTS_NEAT = HERE / "results_neat"  # full NEAT packs, same convention
RESULTS_RL = HERE / "results_rl"      # full RL packs, same convention


def _db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


@app.get("/viz-api/skus")
def _viz_skus():
    with _db() as con:
        rows = con.execute(
            "SELECT sku_id, name, length, width, height, weight FROM skus"
        ).fetchall()
    return JSONResponse([dict(r) for r in rows])


@app.get("/viz-api/orders")
def _viz_orders():
    with _db() as con:
        rows = con.execute(
            "SELECT o.order_id, COUNT(oi.id) AS sku_count, "
            "COALESCE(SUM(oi.quantity),0) AS total_boxes "
            "FROM orders o LEFT JOIN order_items oi ON oi.order_id = o.order_id "
            "GROUP BY o.order_id ORDER BY o.order_id"
        ).fetchall()
    return JSONResponse([dict(r) for r in rows])


@app.get("/viz-api/orders/{order_id}")
def _viz_order(order_id: str):
    with _db() as con:
        items = con.execute(
            "SELECT sku_id, quantity FROM order_items WHERE order_id = ? ORDER BY id",
            (order_id,),
        ).fetchall()
    return JSONResponse({"order_id": order_id, "items": [dict(r) for r in items]})


@app.get("/viz-api/result/{order_id}")
def _viz_result(order_id: str):
    """Phase 1+2 result for an order: the packed boxes (real positions) and the
    remainder. Returns available=False if this pack hasn't been computed yet."""
    import json as _json
    placed_p = RESULTS / f"{order_id}.placed.json"
    remainder_p = RESULTS / f"{order_id}.remainder.json"
    if not placed_p.exists() or not remainder_p.exists():
        return JSONResponse({"available": False, "order_id": order_id})
    return JSONResponse({
        "available": True,
        "order_id": order_id,
        "placed": _json.loads(placed_p.read_text()),
        "remainder": _json.loads(remainder_p.read_text()),
    })


@app.get("/viz-api/ep-result/{order_id}")
def _viz_ep_result(order_id: str):
    """The FULL EP pack for an order — phases 1, 2 and 3.

    Distinct from /viz-api/result, which is Phase 1+2 only. Those two together are
    the point: Phase 1+2 is the deterministic part every engine shares, and the
    difference between the two views is exactly what Phase 3 contributed.
    """
    import json as _json
    p = RESULTS_EP / f"{order_id}.packformation.json"
    if not p.exists():
        return JSONResponse({"available": False, "order_id": order_id})
    return JSONResponse({"available": True, "order_id": order_id,
                         "pack": _json.loads(p.read_text())})


@app.get("/viz-api/neat-result/{order_id}")
def _viz_neat_result(order_id: str):
    """The full NEAT pack for an order (same contract as /viz-api/ep-result)."""
    import json as _json
    p = RESULTS_NEAT / f"{order_id}.packformation.json"
    if not p.exists():
        return JSONResponse({"available": False, "order_id": order_id})
    return JSONResponse({"available": True, "order_id": order_id,
                         "pack": _json.loads(p.read_text())})


@app.get("/viz-api/rl-result/{order_id}")
def _viz_rl_result(order_id: str):
    """The full RL pack for an order (same contract as /viz-api/ep-result)."""
    import json as _json
    p = RESULTS_RL / f"{order_id}.packformation.json"
    if not p.exists():
        return JSONResponse({"available": False, "order_id": order_id})
    return JSONResponse({"available": True, "order_id": order_id,
                         "pack": _json.loads(p.read_text())})


@app.get("/viz-api/results-index")
def _viz_results_index():
    """Order ids that have a computed phase-1/2 result."""
    if not RESULTS.exists():
        return JSONResponse([])
    ids = sorted(p.name[:-len(".placed.json")]
                 for p in RESULTS.glob("*.placed.json"))
    return JSONResponse(ids)


@app.get("/viz")
def _viz_index():
    return FileResponse(str(VIZ / "index.html"))


app.mount("/viz-static", StaticFiles(directory=str(VIZ)), name="viz")

# Hashed assets, then an SPA fallback for client-side routes (/admin, /login, ...).
app.mount("/assets", StaticFiles(directory=str(DIST / "assets")), name="assets")


# Serve the SPA index with our 3D-view enhancement script injected. The React
# bundle can't be rebuilt (no source), so we augment it at runtime instead.
def _spa_html():
    html = INDEX.read_text()
    if "/viz-static/inject.js" not in html:
        ver = int((VIZ / "inject.js").stat().st_mtime)  # cache-bust on edits
        tag = f'<script src="/viz-static/inject.js?v={ver}"></script>\n</body>'
        html = html.replace("</body>", tag, 1)
    return HTMLResponse(html)


@app.get("/")
def _spa_root():
    return _spa_html()


@app.get("/{full_path:path}")
def _spa_fallback(full_path: str):
    return _spa_html()


if __name__ == "__main__":
    import uvicorn

    # Bind 0.0.0.0 so it works behind a PaaS load balancer (Render/etc.);
    # $PORT is injected by most hosts. Both default sensibly for local use.
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    print(f"Palletizer dataset UI → http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="warning")
