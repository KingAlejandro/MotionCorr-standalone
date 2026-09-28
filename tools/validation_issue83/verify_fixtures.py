#!/usr/bin/env python3
"""Check generated fixtures against the *committed* known-motion manifest.

The generator writes a fresh ``MANIFEST.json`` beside the fixtures it just
produced, so a manifest found in the output directory agrees with those
fixtures by construction. Comparing against it proves nothing. This checks
against the manifest tracked in git instead, which is the only copy that
records what the fixtures are *supposed* to be.

That distinction is not hypothetical: the two hosts used for issue #83 produced
different fixture bytes for the same case (NumPy 1.22.4 versus 2.x), and each
host's freshly written manifest agreed with its own output, so the drift was
invisible until the committed manifest was consulted directly.

Both declared digests are checked: ``movie_sha256`` for the ``.mrcs`` and
``ground_truth_sha256`` for the ``*_ground_truth.json``. The motion-truth
verdicts are computed against the truth file, not the movie, so checking only
the movie would let an edited truth file move a gate between PASS and FAIL
while this tool still called the fixture set fully verified.

Exits nonzero on any mismatch, missing case or unreadable manifest. A fixture
that is absent from the output directory is reported as ``missing`` rather than
silently skipped; a case present on disk but absent from the manifest is
reported as ``undeclared``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

MANIFEST_PATH = "test-data/known_motion/MANIFEST.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def committed_manifest(repo: Path, ref: str) -> Dict[str, Any]:
    """Read the manifest from git, never from the fixtures directory."""
    out = subprocess.run(["git", "-C", str(repo), "show", f"{ref}:{MANIFEST_PATH}"],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


#: Keys of a ground-truth file that record *which checkout generated it* rather
#: than any part of the injected motion. The generator stamps the current commit
#: into every truth file, so a truth regenerated from a different commit can
#: never match a digest recorded at another one even when every motion value is
#: identical -- measured on cpu64 at 93d427e, where all four regenerated truths
#: differed from the committed ones in exactly this one key and in none of the
#: 4131 other leaves.
#:
#: Narrow and named on purpose. Anything outside this tuple is a real drift.
TRUTH_PROVENANCE_KEYS = ("source_commit",)


def committed_blob(repo: Path, ref: str, path: str) -> Optional[str]:
    out = subprocess.run(["git", "-C", str(repo), "show", f"{ref}:{path}"],
                         capture_output=True, text=True)
    return out.stdout if out.returncode == 0 else None


def truth_difference(committed: str, observed: Path) -> Dict[str, Any]:
    """Classify a truth-file digest mismatch as provenance-only or real.

    Compares the parsed documents leaf by leaf. A mismatch confined to
    :data:`TRUTH_PROVENANCE_KEYS` means the fixture was regenerated from a
    different checkout and carries identical motion; anything else -- a changed
    value, an added or removed leaf, an unparseable file -- is drift and stays a
    MISMATCH. A mutated digit in a motion value is not in the allowed set and is
    still caught, which is what the ``ground_truth_mutation`` control asserts.
    """
    try:
        want = json.loads(committed)
        got = json.loads(observed.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        return {"provenance_only": False, "why": f"unparseable: {exc}"}

    def leaves(node: Any, prefix: str = "") -> Dict[str, Any]:
        if isinstance(node, dict):
            out: Dict[str, Any] = {}
            for key, value in node.items():
                out.update(leaves(value, f"{prefix}/{key}"))
            return out
        if isinstance(node, list):
            out = {}
            for index, value in enumerate(node):
                out.update(leaves(value, f"{prefix}[{index}]"))
            return out
        return {prefix: node}

    want_leaves, got_leaves = leaves(want), leaves(got)
    differing = sorted(set(want_leaves) ^ set(got_leaves))
    differing += sorted(k for k in want_leaves.keys() & got_leaves.keys()
                        if want_leaves[k] != got_leaves[k])
    allowed = {f"/{key}" for key in TRUTH_PROVENANCE_KEYS}
    unexpected = [k for k in differing if k not in allowed]
    return {
        "provenance_only": bool(differing) and not unexpected,
        "differing_leaves": differing[:20],
        "differing_leaf_count": len(differing),
        "unexpected_leaves": unexpected[:20],
        "leaves_compared": len(want_leaves),
        "generated_at": {k: got_leaves.get(f"/{k}") for k in TRUTH_PROVENANCE_KEYS},
        "declared_at": {k: want_leaves.get(f"/{k}") for k in TRUTH_PROVENANCE_KEYS},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fixtures-dir", type=Path, required=True)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--ref", default="HEAD",
                        help="Git ref to read the manifest from")
    parser.add_argument("--json", type=Path)
    parser.add_argument("--allow-missing", action="store_true",
                        help="Do not fail on fixtures absent from the directory "
                             "(the heavy case is often not generated)")
    opts = parser.parse_args()

    try:
        manifest = committed_manifest(opts.repo, opts.ref)
    except (subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        print(f"cannot read committed {MANIFEST_PATH}: {exc}", file=sys.stderr)
        return 2

    cases = manifest.get("cases", {})
    result: Dict[str, Any] = {
        "schema": "issue83-fixture-verify/3",
        "manifest_ref": opts.ref,
        "manifest_source_commit": manifest.get("source_commit"),
        "fixtures_dir": str(opts.fixtures_dir),
        "verifier_numpy_version": None,
        "cases": {},
        "mismatched": [],
        "provenance_only": [],
        "missing": [],
        "undeclared": [],
    }
    try:
        import numpy  # noqa: WPS433 -- the checking process, not the generator
        result["verifier_numpy_version"] = numpy.__version__
    except ImportError:
        pass

    for case, spec in sorted(cases.items()):
        entry: Dict[str, Any] = {}
        statuses = []
        # Both declared artefacts are checked. The motion-truth verdicts are
        # computed against the *_ground_truth.json, so a movie that matches
        # while its truth file has drifted would still change PASS/FAIL while
        # the fixture set reported as fully verified.
        for kind, filename, digest_key in (
                ("movie", f"{case}.mrcs", "movie_sha256"),
                ("ground_truth", f"{case}_ground_truth.json", "ground_truth_sha256")):
            path = opts.fixtures_dir / filename
            want: Optional[str] = spec.get(digest_key)
            if want is None:
                entry[kind] = {"status": "undeclared_in_manifest", "file": filename}
                statuses.append("missing")
                result["missing"].append(f"{case} ({kind})")
                continue
            if not path.exists():
                entry[kind] = {"status": "missing", "file": filename, "expected": want}
                statuses.append("missing")
                result["missing"].append(f"{case} ({kind})")
                continue
            got = sha256_file(path)
            ok = (got == want)
            status = "match" if ok else "MISMATCH"
            detail: Dict[str, Any] = {
                "status": status, "file": filename,
                "expected": want, "observed": got,
                "observed_bytes": path.stat().st_size,
            }
            if kind == "movie":
                detail["expected_bytes"] = spec.get("movie_bytes")
            elif not ok:
                # The truth file embeds the commit it was generated from, so a
                # byte mismatch is not yet evidence that the motion drifted.
                # Compare the content before deciding which it is.
                blob = committed_blob(opts.repo, opts.ref,
                                      f"test-data/known_motion/{filename}")
                if blob is None:
                    detail["content_comparison"] = {
                        "provenance_only": False,
                        "why": "no committed copy of this truth file to compare"}
                else:
                    detail["content_comparison"] = truth_difference(blob, path)
                if detail["content_comparison"]["provenance_only"]:
                    status = "provenance_only"
                    detail["status"] = status
            entry[kind] = detail
            statuses.append(status)
            if status == "MISMATCH":
                result["mismatched"].append(f"{case} ({kind})")
            elif status == "provenance_only":
                result["provenance_only"].append(f"{case} ({kind})")
        if "MISMATCH" in statuses:
            entry["status"] = "MISMATCH"
        elif "provenance_only" in statuses:
            entry["status"] = "provenance_only"
        elif "missing" in statuses:
            entry["status"] = "missing"
        else:
            entry["status"] = "match"
        result["cases"][case] = entry

    for path in sorted(opts.fixtures_dir.glob("*.mrcs")):
        if path.stem not in cases:
            result["undeclared"].append(path.name)
    for path in sorted(opts.fixtures_dir.glob("*_ground_truth.json")):
        if path.name[:-len("_ground_truth.json")] not in cases:
            result["undeclared"].append(path.name)

    failed = bool(result["mismatched"]) or bool(result["undeclared"]) \
        or (bool(result["missing"]) and not opts.allow_missing)
    result["verified"] = not failed

    if opts.json:
        opts.json.parent.mkdir(parents=True, exist_ok=True)
        opts.json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")

    for case, entry in sorted(result["cases"].items()):
        print(f"{entry['status']:>8}  {case}")
        for kind in ("movie", "ground_truth"):
            part = entry.get(kind, {})
            print(f"          {part.get('status', '?'):>8}  {kind}")
            if part.get("status") == "MISMATCH":
                print(f"                    expected {part['expected']}")
                print(f"                    observed {part['observed']}")
                comparison = part.get("content_comparison")
                if comparison and comparison.get("unexpected_leaves"):
                    print(f"                    drifted: "
                          f"{', '.join(comparison['unexpected_leaves'][:4])}")
                elif comparison and comparison.get("why"):
                    print(f"                    {comparison['why']}")
            elif part.get("status") == "provenance_only":
                comparison = part["content_comparison"]
                print(f"                    content identical across "
                      f"{comparison['leaves_compared']} leaves; differs only in "
                      f"{', '.join(comparison['differing_leaves'])}")
                print(f"                    declared at "
                      f"{comparison['declared_at'].get('source_commit')}, "
                      f"regenerated at "
                      f"{comparison['generated_at'].get('source_commit')}")
    if result["undeclared"]:
        print(f"undeclared fixtures: {', '.join(result['undeclared'])}")
    print(f"verifier numpy {result['verifier_numpy_version']}; "
          f"manifest from {opts.ref} ({result['manifest_source_commit']})")
    if result["verified"] and result["provenance_only"]:
        print(f"VERIFIED (content) -- {len(result['provenance_only'])} truth "
              f"file(s) regenerated from a different commit; every motion value "
              f"identical: {', '.join(result['provenance_only'])}")
    else:
        print("VERIFIED" if result["verified"] else "NOT VERIFIED")
    return 0 if result["verified"] else 1


if __name__ == "__main__":
    sys.exit(main())
