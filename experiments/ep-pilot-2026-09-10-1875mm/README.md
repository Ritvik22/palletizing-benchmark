# Superseded diagnostic: 1.875 m

This initial 10-order pilot used the initially selected 1.875 m ceiling, before
the user chose a 2.0 m ceiling. Nine orders crashed at the repair boundary with
an item-master mismatch; one exported pack failed its audit. No order passed
either complete validation contract.

The crashes exposed missing rotation metadata in the EP pattern-layer builder.
Rectangular footprints were swapped without recording 90-degree rotation. A
subsequent regression test reproduced this for full and complementary layers,
and the EP-only metadata fix is included with these experiments.

The 2.0 m pilot uses that fix. These runs differ in BOTH height and source code;
do not use their count difference as an algorithm-improvement measurement.
Raw logs, frozen inputs, hashes and failure reports are retained for diagnosis.
This run is not a candidate leaderboard result.
