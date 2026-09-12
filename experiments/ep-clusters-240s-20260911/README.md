# Six-order EP cluster experiment — September 11, 2026

Generated after pushing suite commit `c12271c2ef1b8fdaee3fcdbc718fd60cac440d39`
and website code commit `aee5cd51f96db40d3e3895b9cc648dabde929e36`.
Each order ran in a fresh process, sequentially, with clustering enabled,
a 240-second planning allowance, and a 0.8 × 1.2 × 2.0 m container.
The shared 1 mm XY lattice, capped spreading, 50% cluster spread-area threshold,
physical gates and container-height limit were unchanged across the batch.

Results (placed / ordered; final height; boxes in accepted clusters):

- ORD-03744939: **184 / 184; 1.67 m; 0 cluster boxes**.
- ORD-46957314: **139 / 154; 1.77 m; 0 cluster boxes** — 15 unplaced.
- ORD-84051639: **185 / 194; 1.78 m; 0 cluster boxes** — 9 unplaced.
- ORD-08511033: **175 / 175; 1.69 m; 12 cluster boxes in 1 group**.
- ORD-40068316: **194 / 194; 1.78 m; 0 cluster boxes**.
- ORD-53527595: **175 / 175; 1.71 m; 26 cluster boxes in 2 groups**.

Total: **1,052 / 1,076 boxes; four complete orders, two partial orders**.
Enabling clustering does not force a group to be accepted. Ordinary layers and
individual EP actions remain available. ORD-46957314 stopped at its bounded
candidate search; ORD-84051639 reached its time budget. No result is silently
substituted with an older pack.

All six saved packs passed serialized chronological engine replay and the
engine's full-pack audit. Export separately verified immutable IDs, dimensions,
weights, XY grid, exact chronological drop, container bounds, recomputed metrics,
and source/artifact hashes. The unchanged website `rigid-static-v1.0.0` evaluator
also accepted all six packs: zero invalid or missing orders, 1,052 accepted boxes.
Static validity is not certification for transport, crush strength, wrapping,
friction or robot execution. The independent audit uses no SKU stacking rule.

This is an **experimental EP revision, not a leaderboard submission or PPO
teacher dataset**. The existing 1,000-order baseline and published strategy files
are preserved. There is no cluster-off control for five of these six orders;
this batch alone cannot establish a general cluster benefit. ORD-08511033
reproduced the previous 175-box / 1.69 m cluster-enabled outcome.

## Evidence and viewing

- `viewer.json`: source commit, UTC run dates, inventory and pack hashes.
- `manifest.json`, `inputs.json`, `source-integrity.json`: settings and source/input identity.
- `packs/`: actual exported placement sequences, not schematic layouts.
- `reports/`, `summary.json`: counts, heights, timings, cluster decisions and search diagnostics.
- `competition-audit.json`: independent static evaluation, including partial-pack denominators.

Reported per-order runtime includes the planner's internal audit, but excludes
the worker's additional serialized replay and the final website audit. It is
not a time-to-first-complete measurement or a controlled speed benchmark.
The committed `.gitattributes` preserves the exact bytes used by the hashes.

With this branch served by the website backend, select **Sep 11, 2026 · EP
clusters · 240 s** in an order's revision picker, or use
`/viz?dataset=ep-clusters-240s-20260911&order=ORD-08511033&view=ep`.
Only these six orders have this revision; it exposes EP and SKU schematic views,
never a borrowed P1+2 teacher, NEAT, or RL result.

## Reproduce

From the suite root, using a new output directory:

```powershell
python -B dataset_manager/run_cluster_batch.py run --out NEW-RUN --orders ORD-03744939 ORD-46957314 ORD-84051639 ORD-08511033 ORD-40068316 ORD-53527595
```

From the website repository:

```powershell
python -B -m competition.audit_ep_experiment --experiment ABSOLUTE-RUN-PATH
```

Then from the suite root:

```powershell
python -B dataset_manager/run_cluster_batch.py export --run NEW-RUN --out NEW-WEBSITE-ARCHIVE
```

Original jobs and frozen source copies are retained locally under
`dataset_manager/experiments/ep-clusters-240s-20260911` in the suite workspace.
No order database or pre-existing result artifact was rewritten.
