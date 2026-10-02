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

A truth file whose digest differs is not assumed to have drifted: it is parsed
and compared leaf by leaf against the committed copy, and excused only when
every difference is the embedded commit stamp or a float that is the same
double to within a few ULP. Both excuses were measured on real fixtures, both
are named in the report, and neither can absorb a changed motion value.

Exits nonzero on any mismatch, missing case or unreadable manifest. A fixture
that is absent from the output directory is reported as ``missing`` rather than
silently skipped; a case present on disk but absent from the manifest is
reported as ``undeclared``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

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

#: A truth file is JSON, so every float in it is a decimal rendering of a
#: double. Two NumPy builds performing the same reduction can land one unit in
#: the last place apart -- measured on cpu64 at 8298158, where
#: ``km_local_hisnr``'s *movie* digest matched the committed manifest exactly
#: while two derived noise statistics differed by 1.8e-16 and 1.5e-16 relative,
#: one ULP each. The bit-identical movie is the proof that the noise actually
#: injected is the same; only the statistic summarising it rounds differently.
#:
#: Four ULP is about 1e-15 relative. A mistyped digit, a changed formula, a
#: different seed or a different scale all land many orders of magnitude
#: outside it -- ``truth_provenance`` asserts exactly that, including at the
#: boundary, so this cannot be stretched into a general numerical tolerance.
TRUTH_FLOAT_ULPS = 4


def within_ulps(a: Any, b: Any, ulps: int = TRUTH_FLOAT_ULPS) -> bool:
    """True when two values are the same double give or take ``ulps`` steps.

    Only floats are eligible. Ints, bools and strings must match exactly: a
    frame count or a case name that changed is drift however small the edit
    looks, and JSON's ``2`` and ``2.0`` are deliberately not interchangeable
    here. Signs are never bridged, so a value that crossed zero is drift.
    """
    if type(a) is not float or type(b) is not float:
        return False
    if a == b:
        return True
    if not (math.isfinite(a) and math.isfinite(b)):
        return False
    if (a < 0) != (b < 0):
        return False
    lo, hi = (a, b) if a < b else (b, a)
    for _ in range(ulps):
        lo = math.nextafter(lo, hi)
        if lo >= hi:
            return True
    return False


def flatten(node: Any, prefix: str = "") -> Dict[str, Any]:
    """Every scalar in a parsed document, keyed by its path.

    ``{"noise": {"sigma": 0.3}}`` becomes ``{"/noise/sigma": 0.3}``; list
    elements are indexed. Comparing flattened documents rather than whole
    subtrees is what lets a difference be attributed to one named leaf.
    """
    if isinstance(node, dict):
        out: Dict[str, Any] = {}
        for key, value in node.items():
            out.update(flatten(value, f"{prefix}/{key}"))
        return out
    if isinstance(node, list):
        out = {}
        for index, value in enumerate(node):
            out.update(flatten(value, f"{prefix}[{index}]"))
        return out
    return {prefix: node}


def committed_blob(repo: Path, ref: str, path: str) -> Optional[str]:
    out = subprocess.run(["git", "-C", str(repo), "show", f"{ref}:{path}"],
                         capture_output=True, text=True)
    return out.stdout if out.returncode == 0 else None


def truth_difference(committed: str, observed: Path) -> Dict[str, Any]:
    """Classify a truth-file digest mismatch as content-equivalent or real.

    Compares the parsed documents leaf by leaf. Two causes are excused, both
    measured rather than assumed: a leaf named in :data:`TRUTH_PROVENANCE_KEYS`
    (the generator stamps the current commit into every truth file), and a
    float leaf whose two values are the same double to within
    :data:`TRUTH_FLOAT_ULPS`. Anything else -- a changed value, an added or
    removed leaf, a changed integer or string, an unparseable file -- is drift
    and stays a MISMATCH. A mutated digit in a motion value is neither named
    nor within a few ULP and is still caught, which is what the
    ``ground_truth_mutation`` control asserts against real fixtures.
    """
    try:
        want = json.loads(committed)
        got = json.loads(observed.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        return {"content_equivalent": False, "why": f"unparseable: {exc}"}

    want_leaves, got_leaves = flatten(want), flatten(got)
    # A leaf present on one side only can never be a rounding difference, so
    # keep the two kinds apart rather than testing structure for ULP distance.
    structural = sorted(set(want_leaves) ^ set(got_leaves))
    changed = sorted(k for k in want_leaves.keys() & got_leaves.keys()
                     if want_leaves[k] != got_leaves[k])
    differing = structural + changed
    allowed = {f"/{key}" for key in TRUTH_PROVENANCE_KEYS}
    rounding: List[str] = [k for k in changed if k not in allowed
                           and within_ulps(want_leaves[k], got_leaves[k])]
    excused = allowed | set(rounding)
    unexpected = [k for k in differing if k not in excused]
    return {
        "content_equivalent": bool(differing) and not unexpected,
        "differing_leaves": differing[:20],
        "differing_leaf_count": len(differing),
        "provenance_leaves": [k for k in differing if k in allowed],
        "float_rounding_leaves": rounding[:20],
        "float_rounding_tolerance_ulps": TRUTH_FLOAT_ULPS,
        "float_rounding_max_relative": max(
            (abs(want_leaves[k] - got_leaves[k]) / abs(want_leaves[k])
             for k in rounding if want_leaves[k]), default=0.0),
        "unexpected_leaves": unexpected[:20],
        "leaves_compared": len(want_leaves),
        "generated_at": {k: got_leaves.get(f"/{k}") for k in TRUTH_PROVENANCE_KEYS},
        "declared_at": {k: want_leaves.get(f"/{k}") for k in TRUTH_PROVENANCE_KEYS},
    }


def verdict(result: Dict[str, Any], allow_missing: bool) -> Dict[str, Any]:
    """Set ``vacuous`` and ``verified`` on a finished comparison record.

    "Nothing mismatched" is not "the inputs are the declared ones" when
    nothing was compared. An empty fixtures directory under ``--allow-missing``,
    or a manifest with no cases, produces no mismatch and no undeclared file,
    so the verdict would be a vacuous pass -- the same empty-set quantification
    that let a resume certify native CUDA without executing a movie. Both
    declared artefact kinds must have been compared at least once.

    A module-level function rather than four lines inside ``main`` so that the
    gate has an address: a negative control can call it on a record that
    compared nothing, and a meta-check can revert it and require that control
    to fail.
    """
    compared = result["compared"]
    result["vacuous"] = not (compared["movie"] and compared["ground_truth"])
    result["verified"] = not (bool(result["mismatched"])
                              or bool(result["undeclared"])
                              or result["vacuous"]
                              or (bool(result["missing"]) and not allow_missing))
    return result


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
        "schema": "issue83-fixture-verify/5",
        "manifest_ref": opts.ref,
        "manifest_source_commit": manifest.get("source_commit"),
        "fixtures_dir": str(opts.fixtures_dir),
        "verifier_numpy_version": None,
        "declared_cases": len(cases),
        "cases": {},
        "mismatched": [],
        "content_equal": [],
        "missing": [],
        "undeclared": [],
        # How many digests were actually computed and compared, per artefact
        # kind. Without this the verdict below cannot tell "everything matched"
        # apart from "nothing was looked at".
        "compared": {"movie": 0, "ground_truth": 0},
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
                # The truth file embeds the commit it was generated from and
                # renders derived statistics as decimal doubles, so a byte
                # mismatch is not yet evidence that the motion drifted. Compare
                # the content before deciding which it is.
                blob = committed_blob(opts.repo, opts.ref,
                                      f"test-data/known_motion/{filename}")
                if blob is None:
                    detail["content_comparison"] = {
                        "content_equivalent": False,
                        "why": "no committed copy of this truth file to compare"}
                else:
                    detail["content_comparison"] = truth_difference(blob, path)
                if detail["content_comparison"]["content_equivalent"]:
                    status = "content_equal"
                    detail["status"] = status
            entry[kind] = detail
            statuses.append(status)
            result["compared"][kind] += 1
            if status == "MISMATCH":
                result["mismatched"].append(f"{case} ({kind})")
            elif status == "content_equal":
                result["content_equal"].append(f"{case} ({kind})")
        if "MISMATCH" in statuses:
            entry["status"] = "MISMATCH"
        elif "content_equal" in statuses:
            entry["status"] = "content_equal"
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

    verdict(result, opts.allow_missing)
    if result["vacuous"]:
        compared = result["compared"]
        print(f"NOT VERIFIED: no digests were compared "
              f"({compared['movie']} movie, {compared['ground_truth']} ground "
              f"truth, over {len(cases)} declared case(s))", file=sys.stderr)

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
            elif part.get("status") == "content_equal":
                comparison = part["content_comparison"]
                print(f"                    content equivalent across "
                      f"{comparison['leaves_compared']} leaves; differs only in "
                      f"{', '.join(comparison['differing_leaves'])}")
                if comparison["provenance_leaves"]:
                    print(f"                    stamped at "
                          f"{comparison['declared_at'].get('source_commit')}, "
                          f"regenerated at "
                          f"{comparison['generated_at'].get('source_commit')}")
                if comparison["float_rounding_leaves"]:
                    print(f"                    "
                          f"{len(comparison['float_rounding_leaves'])} float "
                          f"leaf/leaves agree to within "
                          f"{comparison['float_rounding_tolerance_ulps']} ULP "
                          f"(max {comparison['float_rounding_max_relative']:.2e} "
                          f"relative): "
                          f"{', '.join(comparison['float_rounding_leaves'])}")
    if result["undeclared"]:
        print(f"undeclared fixtures: {', '.join(result['undeclared'])}")
    print(f"verifier numpy {result['verifier_numpy_version']}; "
          f"manifest from {opts.ref} ({result['manifest_source_commit']})")
    if result["verified"] and result["content_equal"]:
        print(f"VERIFIED (content) -- {len(result['content_equal'])} truth "
              f"file(s) differ from the committed bytes only in the commit "
              f"stamp and/or in the last bit of a derived float; every motion "
              f"value is the same number: {', '.join(result['content_equal'])}")
    else:
        print("VERIFIED" if result["verified"] else "NOT VERIFIED")
    return 0 if result["verified"] else 1


if __name__ == "__main__":
    sys.exit(main())
