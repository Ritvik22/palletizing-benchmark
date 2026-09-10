# Local EP experiments

These are research artifacts, not replacements for the competition leaderboard.
The existing database and `dataset_manager/benchmark_ep/summary.json` are not
modified by this runner. Every run uses a new output directory.

## Reproduce a laptop pilot

From the suite root, with its numerical dependencies installed:

```powershell
.\.venv-search\Scripts\python.exe -B dataset_manager/run_ep_pilot.py --out dataset_manager/experiments/NEW-RUN-ID --height 2.0 --limit 10 --workers 2 --phase-budget 20 --order-timeout 180
```

The sample is deterministic and spread across sorted order IDs. `inputs.json`
freezes every instance's dimensions, mass, SKU and weight-class metadata.
`manifest.json` records source hashes (including any uncommitted code), the
parent Git commit, input hash, runtime, container, profile, seed and budgets.
Workers use separate interpreters and scratch directories. The source must
still match the manifest when each order starts. Wall-clock stopping is not
bitwise reproducible across laptop loads. This is a pilot, not a speed benchmark.

The `laptop` profile runs pattern/group layers, EP, grid fallback, void repair
and completion. It skips legacy support retry and relocation polish using the
existing count-only switch. Safety gates are NOT disabled, and final research
validation is performed independently of that switch. `--profile full` restores
the expensive legacy passes; the whole-order timeout still applies.

## Two distinct validation contracts

- `summary.json`: exact exported identities and dimensions plus the EP repair
  audit, including chronological replay, minimum 50% footprint support,
  cumulative reserves and isolated-column checks. This uses the explicit
  **10 mm near-level assumed-settling model**, not simulated tilted boxes.
- `competition-audit.json`: the website's unchanged `rigid-static-v1.0.0`
  evaluator, using exact-contact rigid-body force/moment equilibrium. It checks
  the final pack, not the robot trajectory. It does not impose EP's 50% support
  floor or its lateral-acceleration reserve. The optional weight-class stacking
  rule is not enabled for this audit. It is not a crush-strength test.

A pack can pass one contract and fail the other. Neither certifies real transport
safety, deformation, friction, gripper access or pallet wrapping. Missing,
failed and invalid orders stay in the denominator. Raw placed counts must never
be advertised as validated completion.

Run the second audit from the website checkout:

```powershell
.\.venv-competition\Scripts\python.exe -B -m competition.audit_ep_experiment --experiment C:\Palletizing\dataset_manager\experiments\NEW-RUN-ID
```

The audit refuses to overwrite an existing review. Exit code 2 means some orders
failed validation or are missing; that is a recorded experimental outcome, not
an instruction to weaken the evaluator.

`packed_prism_utilization` is packed volume / (pallet footprint * actual top),
so higher is better. The competition's `lve` is the reciprocal, lower is better,
and is reported only for valid, complete packs. Container-volume utilization
uses the ceiling and must not be confused with either of these metrics.

## Next development priorities

1. Make foundation placement obey the same chosen stability/identity contract
   as remainder search. Reject or rebuild an invalid foundation before freezing
   it: protected-prefix repair cannot fix a prefix it is forbidden to change.
2. Add short-horizon beam search over **both item order and position**, with
   inventory-aware free-space scoring. Keep validated incumbent packs at all
   times; compare at equal compute budgets.
3. Extend suffix repair into dependency-aware neighborhood repair of voids and
   narrow upper towers. This is offline planning, not permission to move boxes
   already built by a robot.
4. Train a graph/geometry/inventory value model on validated search trajectories
   to guide that search. Increasing candidate count alone is not strategic
   planning. Measure the shortlist's loss of good actions and keep a geometric
   fallback under a matched budget.
5. Validate robustness separately with measured load limits and disturbances,
   held-out orders and seeds. Weight class is not measured crush strength.

The current user objective is a **2.0 m hard ceiling**, maximum valid completion,
then reduced actual stack height and avoidance of narrow pyramiding. The ceiling
is never the height to aim for. A future objective needs to expose the tradeoff
when one extra box would require an undesirable tower; this pilot does not
pretend that tradeoff has been solved or silently change the scoring weights.

Related primary research: [AAAI 2026: scalable offline packing](https://ojs.aaai.org/index.php/AAAI/article/view/40009)
uses attention over unpacked items, spaces and packed items with diversified
search and dynamic candidate selection. [Gao et al., 2025 preprint](https://arxiv.org/abs/2507.09123)
studies stability validation and rearrangement. These motivate comparisons;
their assumptions and reported gains are not evidence of our system's performance.
