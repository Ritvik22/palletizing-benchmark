"""Copy one completed, independently audited EP run into the website archive.

The exporter refuses overwrites, preserves pack bytes, verifies fixed denominators,
and labels the archive as a research result rather than leaderboard or teacher data.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil


DATASET = "ep-latest-multistart-1000-12workers-20260918"
INPUT_SHA = "048e5f21da9382912e1b2ccf7d2c27696047c6b976d6c846db9a82810c145cc8"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")


def source_record(path, root):
    return {"path": path.relative_to(root).as_posix(), "sha256": sha(path),
            "content": path.read_text(encoding="utf-8")}


def publish(run, website):
    run, website = run.resolve(), website.resolve()
    target = website / "experiments" / DATASET
    require(run.name == DATASET, "Unexpected source dataset")
    require(not target.exists(), "Publication target already exists")
    manifest, summary = read(run / "manifest.json"), read(run / "summary.json")
    audit, inputs = read(run / "competition-audit.json"), read(run / "inputs.json")
    totals = audit["totals"]
    require(manifest["version"] == "ep-cold-batch-v1" and manifest["final_verification_run"] is True,
            "Not a final cold EP run")
    require(manifest["input_sha256"] == manifest["parent_input_sha256"] == INPUT_SHA == audit["input_sha256"],
            "Input revision mismatch")
    require(manifest["container"] == {"width": .8, "depth": 1.2, "height": 2.0}, "Container mismatch")
    require(manifest["workers"] == 12 and manifest["budget_s"] == 600.0, "Run budget mismatch")
    portfolio = manifest["portfolio"]
    require(portfolio["start"] == "empty_pallet" and portfolio["archived_seeds"] is False
            and portfolio["schedule"] == "multi-start" and portfolio["trial_budget_s"] == 180.0,
            "Portfolio contract mismatch")
    require(summary["state"] == "completed" and summary["orders_finished"] == 1000
            and summary["orders_valid"] == 1000 and summary["orders_failed"] == 0,
            "Run is not a clean terminal result")
    expected = {"orders_expected": 1000, "orders_submitted": 1000, "orders_missing": 0,
                "orders_invalid": 0, "orders_complete": 953, "boxes_expected": 155904,
                "boxes_accepted": 155607}
    require(all(totals[key] == value for key, value in expected.items()), "Independent audit totals changed")
    require(len(inputs) == 1000 and sum(map(len, inputs.values())) == 155904, "Input denominator mismatch")
    require(set(inputs) == set(audit["orders"]), "Audit coverage mismatch")
    pack_hashes = {}
    for order_id, row in audit["orders"].items():
        source = run / "packs" / f"{order_id}.packformation.json"
        require(row["valid"] is True and source.is_file(), f"Invalid or missing pack: {order_id}")
        require(row["source_pack_sha256"] == sha(source), f"Stale pack audit: {order_id}")
        pack_hashes[order_id] = row["source_pack_sha256"]
    for name, expected_hash in audit["evaluator_source_sha256"].items():
        require(Path(name).name == name and sha(website / "competition" / name) == expected_hash,
                f"Evaluator source changed: {name}")

    target.mkdir(parents=True)
    (target / "packs").mkdir()
    (target / "provenance").mkdir()
    (target / ".gitattributes").write_text("* -text\n", encoding="utf-8", newline="\n")
    for name in ("inputs.json", "manifest.json", "summary.json", "competition-audit.json"):
        shutil.copyfile(run / name, target / name)
    for order_id in sorted(pack_hashes):
        shutil.copyfile(run / "packs" / f"{order_id}.packformation.json",
                        target / "packs" / f"{order_id}.packformation.json")
    with gzip.open(target / "provenance" / "frozen-source.jsonl.gz", "wt", encoding="utf-8", newline="\n") as stream:
        for name in sorted(manifest["source_sha256"]):
            path = run / "source" / name
            require(sha(path) == manifest["source_sha256"][name], f"Frozen source changed: {name}")
            stream.write(json.dumps(source_record(path, run / "source"), separators=(",", ":")) + "\n")
    with gzip.open(target / "provenance" / "evaluator-source.jsonl.gz", "wt", encoding="utf-8", newline="\n") as stream:
        for name in sorted(audit["evaluator_source_sha256"]):
            path = website / "competition" / name
            stream.write(json.dumps(source_record(path, website / "competition"), separators=(",", ":")) + "\n")

    subject = ("Fresh current-source common multi-start EP run: 1,000 valid packs; "
               "953 complete and 47 valid partial; 155,607 of 155,904 boxes accepted. "
               "12 workers, 600-second total budget, 180-second trial cap, 2.0 m container. "
               "All packs passed the independent rigid-static audit. The recorded Git revision had "
               "a dirty working tree, so the bundled frozen source is authoritative. Not leaderboard "
               "data, a PPO teacher, or transport-safety certification.")
    write_json(target / "viewer.json", {
        "kind": "ep-only", "dataset": DATASET,
        "label": "Sep 18–19, 2026 · EP fresh common-schedule · 953/1000 complete",
        "suite_commit": manifest["algorithm_commit"],
        "suite_repository": "https://github.com/b0coat01/Nomagic_Palletizing_Hybrid_NEAT",
        "run_started_at": manifest["created_at"], "run_completed_at": summary["updated_at"],
        "date_kind": "run_completed", "inputs_file_sha256": sha(target / "inputs.json"),
        "pack_sha256": pack_hashes, "ep_subject": subject,
    })
    (target / "README.md").write_text(
        "# Fresh 1,000-order EP run — September 18–19, 2026\n\n" + subject + "\n",
        encoding="utf-8", newline="\n")
    files = {p.relative_to(target).as_posix(): sha(p) for p in sorted(target.rglob("*")) if p.is_file()}
    write_json(target / "verification.json", {
        "version": "fresh-ep-publication-v1", "fresh_generation_verified": True,
        "input_sha256": INPUT_SHA, "files_sha256": files,
    })
    print(target)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--website", type=Path, required=True)
    args = parser.parse_args()
    publish(args.run, args.website)
