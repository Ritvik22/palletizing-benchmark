#!/usr/bin/env python3
"""Compute the benchmark summary from the published packs themselves.

Every figure is derived here from the files the site actually serves, so the
summary cannot drift from what a visitor can open and inspect. Re-run after
publishing a pack set:

    python3 build_benchmark_summary.py

A note on what is and is not comparable. **Phase 1+2 is not a competing
method** -- it is the deterministic prefix that EP, NEAT and RL all start from,
and it deliberately stops before the phase that fills the remainder. Ranking it
against the full engines would be meaningless, so it is reported separately as
the shared starting point rather than as a fourth entry in the comparison.

LVE (liquid volume efficiency) is the pack's bounding volume over the volume of
the boxes in it -- pallet footprint times top-of-stack height, divided by the
summed box volumes. **Lower is better**: 1.0 would be a perfectly solid block.
It is computed only over orders a method packed completely, because a pack that
placed fewer boxes gets a flattering LVE simply by being smaller, and comparing
across different completion rates would reward giving up early.
"""
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "backend", "palletizer.db")

METHODS = [
    ("rl",      "RL Full",       "results_rl",   ".packformation.json",
     "Candidate-ranking PPO policy, trained on whole orders with a hard "
     "centre-of-mass stability gate."),
    ("neat",    "NEAT Hybrid",   "results_neat", ".packformation.json",
     "Evolved (NEAT) scorer over the same candidate placements."),
    ("ep",      "EP Hybrid",     "results_ep",   ".packformation.json",
     "Extreme-point heuristic completing the shared Phase 1+2 prefix."),
]
BASELINE = ("phase12", "Phase 1+2", "results", ".placed.json",
            "The deterministic pattern-planning prefix every engine starts "
            "from. It stops before the remainder-filling phase by design, so "
            "it is the shared starting point rather than a competing method.")


def order_totals():
    con = sqlite3.connect(DB)
    rows = con.execute("SELECT order_id, SUM(quantity) FROM order_items "
                       "GROUP BY order_id").fetchall()
    con.close()
    return {o: int(n or 0) for o, n in rows}


def per_order(d, suffix, totals):
    """{order_id: (n_boxes, complete, lve)} for one method."""
    path = os.path.join(HERE, d)
    out = {}
    if not os.path.isdir(path):
        return out
    for f in sorted(os.listdir(path)):
        if not f.endswith(suffix):
            continue
        oid = f[: -len(suffix)]
        try:
            p = json.load(open(os.path.join(path, f)))
        except Exception:                                      # noqa: BLE001
            continue
        boxes = p.get("boxes") or []
        if not boxes:
            out[oid] = (0, False, None)
            continue
        C = p.get("container") or {}
        top = max(b["position"]["z"] + b["dimensions"]["height"] / 2 for b in boxes)
        vol = sum(b["dimensions"]["width"] * b["dimensions"]["depth"]
                  * b["dimensions"]["height"] for b in boxes)
        want = totals.get(oid)
        done = bool(want and len(boxes) == want)
        lve = (C.get("width", 0.8) * C.get("depth", 1.2) * top / vol) if vol else None
        out[oid] = (len(boxes), done, lve)
    return out


def matched(totals):
    """LVE on the orders EVERY engine packed completely.

    The headline LVE columns are each computed over that method's own completed
    orders, which are different sets -- and a method that completes fewer, easier
    orders gets a flattering figure. This restricts every method to the same
    orders so the compactness numbers are directly comparable, which is the only
    way the comparison means anything.
    """
    tables = {k: per_order(d, sfx, totals) for k, _, d, sfx, _ in METHODS}
    common = None
    for t in tables.values():
        done = {o for o, (_, c, l) in t.items() if c and l is not None}
        common = done if common is None else (common & done)
    if not common:
        return None
    out = {"orders": len(common), "lve": {}}
    for k, t in tables.items():
        vals = [t[o][2] for o in common]
        out["lve"][k] = sum(vals) / len(vals)
    # pairwise: how often each method is tighter than the RL policy
    if "rl" in tables:
        out["vs_rl"] = {}
        for k, t in tables.items():
            if k == "rl":
                continue
            wins = sum(1 for o in common if t[o][2] < tables["rl"][o][2])
            out["vs_rl"][k] = {"tighter_than_rl": wins, "of": len(common)}
    return out


def measure(d, suffix, totals):
    path = os.path.join(HERE, d)
    if not os.path.isdir(path):
        return None
    packs = 0
    complete = 0
    placed = 0
    total_of_packed = 0
    lves = []
    heights = []
    for f in sorted(os.listdir(path)):
        if not f.endswith(suffix):
            continue
        oid = f[: -len(suffix)]
        try:
            p = json.load(open(os.path.join(path, f)))
        except Exception:                                      # noqa: BLE001
            continue
        boxes = p.get("boxes") or []
        C = p.get("container") or {}
        packs += 1
        placed += len(boxes)
        want = totals.get(oid)
        if want:
            total_of_packed += want
        if not boxes:
            continue
        top = max(b["position"]["z"] + b["dimensions"]["height"] / 2 for b in boxes)
        heights.append(top)
        vol = sum(b["dimensions"]["width"] * b["dimensions"]["depth"]
                  * b["dimensions"]["height"] for b in boxes)
        if want and len(boxes) == want:
            complete += 1
            bbox = C.get("width", 0.8) * C.get("depth", 1.2) * top
            if vol > 0:
                lves.append(bbox / vol)
    if not packs:
        return None
    mean = lambda xs: (sum(xs) / len(xs)) if xs else None      # noqa: E731
    return {"packs": packs, "orders_complete": complete,
            "boxes_placed": placed, "boxes_expected": total_of_packed,
            "placed_frac": (placed / total_of_packed) if total_of_packed else None,
            "complete_frac": complete / packs,
            "lve_mean": mean(lves), "lve_n": len(lves),
            "height_mean": mean(heights)}


def main():
    totals = order_totals()
    out = {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "orders_in_db": len(totals),
           "boxes_in_db": sum(totals.values()),
           "container": {"width": 0.8, "depth": 1.2, "height": 2.0},
           "lve_note": ("bounding volume / box volume; lower is better. "
                        "Computed only over orders the method packed "
                        "completely, since a smaller pack scores a flattering "
                        "LVE and comparing across completion rates would "
                        "reward giving up early."),
           "methods": [], "baseline": None}

    for key, label, d, suffix, desc in METHODS:
        m = measure(d, suffix, totals)
        if m:
            m.update({"key": key, "label": label, "description": desc})
            out["methods"].append(m)
    out["methods"].sort(key=lambda m: (-m["complete_frac"],
                                       m["lve_mean"] or 9e9))

    out["matched"] = matched(totals)

    key, label, d, suffix, desc = BASELINE
    b = measure(d, suffix, totals)
    if b:
        b.update({"key": key, "label": label, "description": desc})
        out["baseline"] = b

    p = os.path.join(HERE, "benchmark_summary.json")
    with open(p, "w") as f:
        json.dump(out, f, indent=1)

    def line(m):
        return (f"  {m['label']:14s} packs {m['packs']:4d}  complete "
                f"{m['orders_complete']:4d} ({100*m['complete_frac']:5.1f}%)  "
                f"boxes {100*(m['placed_frac'] or 0):6.2f}%  "
                f"LVE {m['lve_mean']:.4f} (n={m['lve_n']})  "
                f"height {m['height_mean']:.3f} m")
    print(f"{out['orders_in_db']} orders, {out['boxes_in_db']:,} boxes in the database\n")
    for m in out["methods"]:
        print(line(m))
    if out["baseline"]:
        print(f"\n  shared prefix:")
        print(line(out["baseline"]))
    if out["matched"]:
        m = out["matched"]
        print(f"\n  matched on the {m['orders']} orders EVERY engine completed:")
        for k, v in sorted(m["lve"].items(), key=lambda kv: kv[1]):
            extra = ""
            if k in (m.get("vs_rl") or {}):
                w = m["vs_rl"][k]
                extra = f"   tighter than RL on {w['tighter_than_rl']}/{w['of']}"
            print(f"    {k:6s} LVE {v:.4f}{extra}")
    print(f"\nwrote {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
