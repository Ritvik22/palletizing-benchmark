# ZIP 1 EP results — September 14, 2026

Experimental results from the first 500-order laptop assignment. These are
dated revisions, not replacements for historical packs or EP Bounded results,
not a leaderboard submission, and not PPO imitation-learning demonstrations.

- Assigned: 500 orders / 77,950 boxes. All 500 attempts finished.
- Suite-valid: 484 packs, of which 214 are complete and 270 are partial.
- Placed in suite-valid packs: 65,496 boxes.
- Rejected: 16 attempts failed serialized chronological placement validation
  (`audit_placement_gate`); no valid pack file is published for those orders.
- Planning: clusters enabled, 240 seconds/order, 10 concurrent CPU workers,
  0.8 × 1.2 × 2.0 m container, shared 1 mm XY center grid.
- Runtime: 9,652.5 seconds (about 2 h 41 m), including execution/validation.
- Algorithm: `644c7c32282a363c3b4d96bb32871454aa5f1c04`. Publication occurs later
  and is not the algorithm version used to generate these results.

`summary.json` retains all 500 outcomes in its totals and lists rejected IDs.
`competition-audit.json` is a fresh, independent exact-contact static audit
of every suite-valid pack. Its 16 missing submissions are precisely the 16
recorded suite failures, not missing work or exclusions from the denominator.
Publication requires zero invalid submissions and agreement with suite counts.
Static validity does not certify transport, friction, crush strength, wrap,
deformation or robot execution. Partial-pack efficiency is not directly
comparable with complete-pack efficiency.

`packs/` preserves original successful pack bytes. Their input hashes refer to
the original single-order inputs; `manifest.json` and `inputs.json` identify the
entire frozen 500-order subset and its parent 1,000-order input digest. ZIP 2 is
not part of this run. No retries or safety/packing code changes were made for
publication. Concurrent, wall-clock-budgeted results may differ from sequential
results on another laptop.

`provenance/evidence.jsonl.gz` contains byte-hashed original manifests, terminal
records (including full per-order suite reports), source-integrity records and
failure logs. `frozen-source.jsonl.gz` preserves the exact frozen code once.
`evaluator-source.jsonl.gz` preserves the independent auditor sources. Each gzip
contains JSON lines with `path`, `sha256`, and `utf8`; encode `utf8` as UTF-8 to
recover the original bytes. The local SQLite database and repeated per-order
source trees are intentionally not published.

`verification.json` hashes every other archived file, including the audit and
viewer metadata. Git attributes disable line-ending conversion for this archive.
The same archive is published to both the algorithm and website repositories.
On the website, choose the September 14 ZIP 1 revision inside an order's normal
packing popup; the standalone viewer also accepts
`/viz?dataset=ep-zip1-10workers-20260914&order=ORD-08511033&view=ep`.
Rejected orders have no valid ZIP 1 pack to select; their failures remain in the
archive summary. Previous revisions remain available without cross-run fallback.
