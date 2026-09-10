# Full-profile smoke check, 2.0 m maximum

This is one selected diagnostic order, not an additional random benchmark:
`ORD-59488997`, 42 boxes. It passed the laptop profile's research audit, so the
same order was tested with legacy support retry and polish enabled (`full`).

The full profile exported all **42/42** boxes and passed the website's exact-
contact final static-equilibrium evaluator. However, it failed EP's chronological
repair audit at `placement_gate:21`; the lighter profile had passed that audit.
Minimum support changed from approximately 72.2% to 58.6%, while the reported
final cumulative-failure count remained zero. This localizes another mismatch
to the additional legacy passes/returned sequence; it does not yet isolate one
specific polish operation as the cause.

Do not infer that adding more legacy search always improves pack quality.
Require a final chosen-contract audit before adopting its output. This artifact
is retained for regression design and was not published to the leaderboard.
