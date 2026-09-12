# EP laptop pilot: 2.0 m maximum, 2026-09-10

Ten deterministic sample orders, **1,569 expected boxes**. Two local workers,
20 seconds per bounded search phase and a 180-second whole-order timeout.
See the parent README for the intentionally lighter `laptop` profile.

## Actual outcomes

- Nine orders exported packs; one order timed out (`ORD-00178905`).
- **1,350 raw placements**, not 1,350 validated placements. Seven exported
  packs contain their full order, but count alone does not establish validity.
- Every exported pack matches the frozen instance/SKU/dimension/mass identities.
- Maximum exported top: **1.9999999905 m**, within the 2.0 m ceiling.
- EP's stronger chronological repair audit: **1/10 valid and complete**,
  containing 42 boxes. The other exported packs fail placement or cumulative
  build-step checks. Reported minimum footprint support ranges as low as 4.7%.
- Website exact-contact static-equilibrium audit: **3/10 valid and complete**,
  containing 283 boxes; six packs invalid, one missing due to timeout.
- No result was submitted to or promoted on the official competition leaderboard.

The three static-valid orders are `ORD-10280100` (120 boxes), `ORD-29845118`
(121 boxes), and `ORD-59488997` (42 boxes). Only the last also passes the
stronger EP chronological repair contract.

These results show **remaining end-to-end consistency defects**, not state of
the art performance. The rotation metadata fix removed the earlier item-master
crashes, but it did not fix the layer/remainder safety-contract mismatch.
Protected-foundation repair cannot repair invalid boxes in its locked prefix;
completion correctly refuses an invalid incumbent instead of legitimizing it.

Next: enforce the chosen support/identity contract throughout layer building,
remainder search and polish; then add look-ahead/repair objectives that favor
lower placements and discourage narrow upper towers. A 2.0 m ceiling is a hard
limit, not a goal height. This run does not introduce a new anti-pyramid penalty.

Regression checks accompanying the changes: 76 suite-root tests (39 subtests),
202 RL tests, 4 NEAT tests, 24 EP geometry assertions, 66 website Python tests and
14 website JavaScript tests passed. Those software checks do not override the
real-order failures recorded here.
