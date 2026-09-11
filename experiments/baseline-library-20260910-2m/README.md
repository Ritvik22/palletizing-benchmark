# September 10 full-library experimental baseline

Finished September 11, 2026, at 06:25:31 UTC. **Research archive only: not an
official leaderboard submission, published strategy replacement, or training-data approval.**

## Visual inspection

Filter the order database normally and open an order's **View** pop-up. Its
**Result date** selector lists that order's available result collections, newest
first by default. Switch dates and strategies within the same pop-up; the 3D
pack, order snapshot, statistics and provenance change together. A method not
included in the selected run is marked unavailable, not replaced with an older
result. The existing direct `/viz?dataset=baseline-library-20260910-2m&view=ep`
link remains supported for embeds and bookmarks, but there is no separate
results-browsing button. The teacher audit is **not the EP run's foundation**; do not subtract
its count from EP and call that a Phase 3 improvement. The published strategy
library remains separate and unchanged.

The viewer uses the frozen teacher inventory for dimensions, weights and order
quantities, not the mutable website database. `teacher/orders-audited.jsonl.gz`
is now byte-copied from the pinned suite archive for portable visualization;
`viewer.json` records its SHA-256 and source revision. It is an audit artifact,
not approval to train. No local admin accounts, preview databases or laptop
paths are needed to display these results.

## Results

- Fixed dataset: 1,000 orders / 155,904 boxes; 0.8 x 1.2 x **2.0 m hard ceiling**.
- EP: **1,000 valid packs, 305 complete orders, 128,533 boxes placed**;
  27,371 remain. Every exported pack passes both the chronological suite audit
  and a fresh independent website audit. Valid partial packs are not completion.
- Website LVE: **1.781607896692267 mean**, over the **305 valid complete packs
  only** (lower is better). Do not average this over all 1,000 orders or confuse
  it with packed-prism utilization (its reciprocal) or container utilization.
- P1+2: **29,643/29,643 exact PPO action matches** across **993 nonempty teachers**.
  Seven orders have no full/partial layers. No worker failures, unmatched steps,
  invalid replay prefixes or unvisited teacher actions were recorded.
- Historical snap-only layers proposed **89,275** boxes; clearance-aware
  proposals contained **91,585**. Certified/retained teachers contain **29,643**.
  Complete action replay is not complete foundation retention or full-order packing.

Empty teachers: ORD-15490573, ORD-31839638, ORD-44650004, ORD-53902375,
ORD-74729607, ORD-77752632 and ORD-92970771. They remain in the denominator
and explain `complete_with_failures` in the coordinator's final record.

## What changed

The suite's default EP method is `validated-grid-static-greedy-ep-v2`: shared
1 mm XY center grid, exact Z drop, vetted full/partial foundation layers,
large-footprint greedy construction, bounded beam suffix/void repair and an
additional global static force/moment gate. It prioritizes box count, then
lower actual height. It does not guarantee elimination of upper pyramiding.

P1+2 imitation uses clearance-aware layers and exact offered-action replay,
without singleton fillers, fabricated labels, or EP demonstrations. This batch
uses **4,096 global candidates and local cap ONE**, retaining **10 degree minimum
tipping angle / +/-15 mm per-axis uncertainty**. Production local cap remains
4,096; full-local-window throughput and broader training quality are unproven.

The website evaluator is unchanged. Its model is exact-contact rigid-body
gravity equilibrium, not transport/crush/deformation certification. Its optional
weight-class stacking rule is disabled in this audit. Six duration outliers are
recorded; laptop suspension/timekeeping makes this unsuitable as a controlled
speed benchmark. This result does not establish performance non-regression or
state-of-the-art quality against a matched historical baseline.

## Revision and files

Suite revision: [`1a66b636ef3ca53bcdc6cccbb4192993d106dd41`](https://github.com/b0coat01/Nomagic_Palletizing_Hybrid_NEAT/commit/1a66b636ef3ca53bcdc6cccbb4192993d106dd41),
branch `final-palletizing-suite-bwc`.
[Full evidence and frozen-source archive](https://github.com/b0coat01/Nomagic_Palletizing_Hybrid_NEAT/tree/1a66b636ef3ca53bcdc6cccbb4192993d106dd41/dataset_manager/experiments/baseline-library-20260910-2m).

- `packs/` and `reports/`: exact EP artifacts and detailed suite validation.
- `inputs.json`, `manifest.json`, `integrity.json`: byte-preserved frozen
  dataset/configuration and original manifest hash. The manifest's parent Git
  commit predates uncommitted measured changes; its source hashes are authoritative.
- `summary.json`: suite metrics and fixed-denominator totals.
- `competition-audit.json`: fresh website audit of all 1,000 exact pack bytes.
- `recorded-competition-audit.json`: original per-order verdicts, which agree
  with the fresh audit. Do not aggregate missing counts from original single-order
  audit runs; use the fresh all-order totals.
- `teacher/`: all-order coverage, replay contract and compressed audited teacher
  records for visualization, not approved training data.
- `suite-export-verification.json`: copied verification index for the **full
  suite archive**. Frozen source and raw evidence referenced there intentionally
  live in the pinned suite archive, not here. The later viewer addition also
  copies the compressed teacher orders, verified separately by `viewer.json`.
- `final-progress.json`: original completed outcome with I/O-only recovery metadata.
  The full suite preserves that recovery and all 224 pre-recovery completed results.
- `suite-revision.json`: explicit linkage to the code and full evidence.

All copied artifacts retain their source bytes; `.gitattributes` prevents Git
newline conversion. No production database, website authentication, live UI or
official leaderboard changed in this export.

To independently rerun the audit, copy this directory to a NEW location without
its existing `competition-audit.json`, then use
`python -m competition.audit_ep_experiment --experiment NEW-COPY` from this repo.
The command refuses to overwrite the original audit.
