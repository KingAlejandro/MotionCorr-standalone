#!/usr/bin/env python3
"""Assert that the composition invented no production content.

The claim this branch rests on is that every production byte came from one of
three owners' reviewed sources and the integrator only resolved conflicts. That
is checkable, and it has to be re-checked after every recomposition -- a
three-way merge of files two branches changed in overlapping regions can produce
a plausible blend that belongs to neither side and that no test would notice.

Two assertions:

  1. Every file under src/ that differs from the base must be byte-identical to
     that file in at least one owner source. Any other content is a merge
     artefact or an undeclared edit.

  2. The exception is the one file all three owners touch. Its expected content
     is reconstructed independently: take PR118's version and apply PR117's
     base->source diff to it with patch(1). If that reconstruction does not
     equal the branch's file, the merge changed something neither owner wrote.

Exit 0 only if both hold. This is a structural check on provenance, not a
review: it says nothing about whether the composed behaviour is correct.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path


def git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout


def blob(repo: Path, rev: str, path: str) -> bytes | None:
    r = subprocess.run(["git", "-C", str(repo), "show", f"{rev}:{path}"],
                       capture_output=True)
    return r.stdout if r.returncode == 0 else None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", type=Path, default=Path("."))
    ap.add_argument("--base", default="6393547e")
    ap.add_argument("--head", default="HEAD")
    ap.add_argument("--owner", action="append", required=True, metavar="LABEL=REV",
                    help="owner source, repeatable, e.g. --owner pr115=0f2ddd5d")
    ap.add_argument("--three-way", default="src/motioncorr_runner.cpp",
                    help="file every owner touches; reconstructed independently")
    ap.add_argument("--reconstruct", metavar="FROM=REV,PATCHED_WITH=REV",
                    default="from=pr118,patched_with=pr117",
                    help="which owner supplies the base content and which supplies "
                         "the diff, by label")
    a = ap.parse_args(argv)

    owners = dict(o.split("=", 1) for o in a.owner)
    spec = dict(kv.split("=", 1) for kv in a.reconstruct.split(","))
    base_label, patch_label = spec["from"], spec["patched_with"]
    for lbl in (base_label, patch_label):
        if lbl not in owners:
            print(f"FAIL: --reconstruct names unknown owner {lbl!r}")
            return 2

    changed = [p for p in git(a.repo, "diff", "--name-only", a.base, a.head).split()
               if p.startswith("src/")]
    if not changed:
        print("FAIL: no src/ file differs from the base; nothing to verify")
        return 2

    unexplained, explained = [], {}
    for path in changed:
        if path == a.three_way:
            continue
        head_bytes = blob(a.repo, a.head, path)
        match = [lbl for lbl, rev in owners.items() if blob(a.repo, rev, path) == head_bytes]
        if match:
            explained[path] = match
        else:
            unexplained.append(path)

    print(f"src/ files changed vs {a.base}: {len(changed)}")
    for path, m in sorted(explained.items()):
        print(f"  OK        {path}  == {'/'.join(sorted(m))}")
    for path in unexplained:
        print(f"  UNSOURCED {path}  matches no owner source")

    # The three-way file, reconstructed rather than compared.
    ok3 = False
    head3 = blob(a.repo, a.head, a.three_way)
    if head3 is None:
        print(f"  MISSING   {a.three_way} is absent from {a.head}")
    else:
        with tempfile.TemporaryDirectory() as td:
            t = Path(td)
            (t / "expected").write_bytes(blob(a.repo, owners[base_label], a.three_way) or b"")
            (t / "base").write_bytes(blob(a.repo, a.base, a.three_way) or b"")
            (t / "patched").write_bytes(blob(a.repo, owners[patch_label], a.three_way) or b"")
            diff = subprocess.run(["diff", "-u", str(t / "base"), str(t / "patched")],
                                  capture_output=True, text=True).stdout
            if not diff:
                print(f"  NOTE      {patch_label} does not change {a.three_way}; "
                      f"expecting {base_label}'s content unmodified")
            ap_ = subprocess.run(["patch", "-s", "-p0", str(t / "expected")],
                                 input=diff, capture_output=True, text=True)
            if ap_.returncode != 0:
                print(f"  FAIL      cannot reconstruct {a.three_way}: "
                      f"{patch_label}'s diff does not apply to {base_label}'s content")
                print(ap_.stdout + ap_.stderr)
            else:
                ok3 = (t / "expected").read_bytes() == head3
                verdict = "OK       " if ok3 else "MISMATCH "
                print(f"  {verdict} {a.three_way}  == {base_label} + {patch_label} diff")
                if not ok3:
                    subprocess.run(["diff", "-u", str(t / "expected"), "-"],
                                   input=head3.decode(errors="replace"), text=True)

    if unexplained or not ok3:
        print("\nRESULT: FAIL -- the branch carries production content no owner wrote.")
        return 1
    print("\nRESULT: PASS -- every production byte is traceable to an owner source.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
