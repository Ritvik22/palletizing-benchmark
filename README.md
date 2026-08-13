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

## Notes

- `SECRET_KEY` defaults to a throwaway dev value; set the env var for any
  non-local use.
- The 3D layout is schematic (orders store SKU + quantity, not real placements) —
  it groups boxes by SKU for inspection, not a stability-validated pack.
