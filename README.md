# Palletizing Benchmark — SKU & Order Database

A self-contained web app for managing and visualizing a synthetic **palletizing
benchmark dataset**: a master of box SKUs and the "packs" (orders) built from
them, plus a 3D pallet viewer. FastAPI backend + prebuilt React frontend over a
SQLite database, served same-origin by a single runner.

## Run

```bash
pip install fastapi uvicorn sqlalchemy pydantic python-jose passlib bcrypt python-multipart
python3.11 serve.py          # → http://127.0.0.1:8000  (set PORT to change)
```

On first run the app bootstraps a default admin account **`admin` / `admin`**
(the shipped DB has no users — change it immediately, or set `ADMIN_USERNAME` /
`ADMIN_PASSWORD` before the first launch).

## Deploy (Render)

The backend is **Python 3.11-only** bytecode, so it needs a host that runs a real
3.11 process — not a serverless platform. This repo ships a Docker setup for that:

1. Push to GitHub (already done if you're reading this there).
2. In Render: **New → Blueprint**, point it at this repo. It reads `render.yaml`
   and builds the `Dockerfile` (pinned to `python:3.11-slim`).
   - Or **New → Web Service → Docker runtime** and let it use the `Dockerfile`.
3. Render injects `$PORT`; `serve.py` binds `0.0.0.0:$PORT` automatically.
4. Set a real `SECRET_KEY` (the blueprint generates one).

Note: the container filesystem is ephemeral — the SQLite DB (and the bootstrapped
admin) resets on each redeploy/restart. Attach a Render **Disk** mounted over
`backend/` if you need writes to persist.

> Not deployable on Vercel: its Python runtime is 3.12/3.13/3.14, and sourceless
> `.pyc` won't import on anything but 3.11. Vercel functions also can't write the
> SQLite DB.

## What's inside

- **`serve.py`** — imports the backend, pins it to `backend/palletizer.db`, mounts
  the 3D viewer, and serves the frontend same-origin so its relative API calls
  work without CORS. Also injects the runtime UI enhancement (below).
- **`backend/`** — FastAPI app as **sourceless Python 3.11 bytecode** (`*.pyc`).
  The original `.py` sources were unavailable; the bytecode runs as-is **only on
  Python 3.11** (the `.pyc` magic is interpreter-specific). Routers: `/auth`,
  `/skus`, `/orders`, `/releases`, `/upload`, `/public`.
- **`backend/palletizer.db`** — the benchmark dataset: **500 SKUs** and **1000
  packs** (orders). Credential rows are stripped from the shipped copy.
- **`frontend/dist/`** — prebuilt React admin/public UI (no source; `node_modules`
  omitted — not needed to serve the built app).
- **`viz/`** — a standalone Three.js **3D pallet visualizer** (`/viz`) plus
  `inject.js`, a runtime patch that embeds that viewer inside the site's order
  "View" modal and fixes the isometric box thumbnails for metric-scale dimensions.

## The benchmark dataset

Boxes are drawn from the dimension/weight statistics of the canonical **EP-176**
packformation (176 boxes), kept in **metric** units (metres, kg):

| per box | min | max | avg | std |
|---|---|---|---|---|
| length | 0.107 | 0.321 | 0.220 | 0.054 |
| width  | 0.107 | 0.285 | 0.159 | 0.050 |
| height | 0.091 | 0.300 | 0.175 | 0.064 |
| weight (kg) | 0.30 | 6.87 | 1.96 | 1.86 |

Each pack contains a number of distinct SKUs centered near the benchmark's line
count (avg ≈ 13.5, std ≈ 4.5) with per-line quantities drawn from the benchmark's
per-SKU counts (avg ≈ 13.5, 1–31).

## Phase 1+2 placement results

`results/<order_id>.placed.json` / `.remainder.json` hold, for every one of the
1000 packs, the result of the benchmark's **Phase 1 (pattern) + Phase 2
(flat-space group)** placement heuristic — the exact `_cache_pattern_placement()`
path from the 176-box benchmark engine (`hybrid_neat_palletizer_v2`, 0.8×1.2×2.0 m
container, trained group-placement checkpoint). `placed` carries solved box
positions; `remainder` is every box the heuristic left unplaced (all boxes −
placed). Phase 3 (NEAT/greedy) is intentionally not run.

Each order's **View** in the site loads these automatically: the 3D viewer offers
**Phase 1+2 packed** (real positions in the container), **Remainder** (leftover
boxes by SKU), and **Schematic by SKU**, all color-coded per SKU.

## Notes

- `SECRET_KEY` defaults to a throwaway dev value; set the env var for any
  non-local use.
- The 3D layout is schematic (orders store SKU + quantity, not real placements) —
  it groups boxes by SKU for inspection, not a stability-validated pack.
