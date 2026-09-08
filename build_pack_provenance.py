#!/usr/bin/env python3
"""Derive, from git history, when each published pack was added and last changed.

Git is the honest record here: a pack appeared on the site when the commit that
introduced it was pushed, and changed when a later commit rewrote it. Nothing
else on disk knows that -- file mtimes are reset by every clone, and Render
builds a fresh checkout on each deploy, so mtime would report the deploy time
for every pack equally.

Emits `pack_provenance.json`, which serve.py loads at startup. Re-run it after
publishing a pack set:

    python3 build_pack_provenance.py

Output is compact by design. Packs are published in sets, so within a source
almost every order shares the same (added, updated) pair; that pair is stored
once as the source default and only genuine exceptions are listed. The EP set is
the reason exceptions exist at all -- it went out in three instalments (461
orders, then 924, then all 1000), so those orders really do have different
histories.
"""
import json
import os
import subprocess
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))

#: source key -> (directory, filename suffix identifying one pack)
SOURCES = {
    "phase12": ("results", ".placed.json"),
    "ep": ("results_ep", ".packformation.json"),
    "neat": ("results_neat", ".packformation.json"),
    "rl": ("results_rl", ".packformation.json"),
    "reranker": ("results_rl_reranker", ".packformation.json"),
}


def git(*args):
    return subprocess.run(("git",) + args, cwd=HERE, capture_output=True,
                          text=True, check=True).stdout


def main():
    dirs = [d for d, _ in SOURCES.values()]
    # One pass, oldest first, so the first sighting of a path is when it was
    # added and the last is when it was most recently changed.
    raw = git("log", "--reverse", "--name-only", "--no-renames",
              "--format=@|%H|%cI|%s", "--", *dirs)

    commits, order = {}, []
    first, last = {}, {}
    cur = None
    for line in raw.splitlines():
        line = line.rstrip()
        if line.startswith("@|"):
            _, sha, date, subject = line.split("|", 3)
            cur = sha
            if sha not in commits:
                commits[sha] = {"sha": sha[:7], "date": date, "subject": subject}
                order.append(sha)
        elif line and cur:
            first.setdefault(line, cur)
            last[line] = cur

    idx = {sha: i for i, sha in enumerate(order)}
    out = {"generated_from": "git history", "commits": [commits[s] for s in order],
           "sources": {}}

    for key, (d, suffix) in SOURCES.items():
        pairs = {}
        for path, c0 in first.items():
            if not path.startswith(d + "/") or not path.endswith(suffix):
                continue
            name = os.path.basename(path)[: -len(suffix)]
            pairs[name] = (idx[c0], idx[last[path]])
        if not pairs:
            continue
        common = Counter(pairs.values()).most_common(1)[0][0]
        overrides = {k: list(v) for k, v in sorted(pairs.items()) if v != common}
        latest = max(v[1] for v in pairs.values())
        out["sources"][key] = {
            "dir": d, "count": len(pairs),
            "default": list(common), "overrides": overrides,
            "latest_commit": latest,
        }
        print(f"{key:9s} {len(pairs):5d} packs   default added="
              f"{commits[order[common[0]]]['date'][:10]} updated="
              f"{commits[order[common[1]]]['date'][:10]}   "
              f"{len(overrides)} exception(s)")

    p = os.path.join(HERE, "pack_provenance.json")
    with open(p, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"\nwrote {p} ({os.path.getsize(p)/1024:.0f} KB, "
          f"{len(out['commits'])} commits)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
