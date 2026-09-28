#!/usr/bin/env python3
"""Check generated fixtures against the committed known-motion manifest.

Ensures fixture files match the trusted, committed MANIFEST.json byte-for-byte
and digest-for-digest. Rejects missing fixtures, missing truth files, missing or
altered STAR inputs, corrupted/byte-flipped fixtures, malformed inventories, and
undeclared fixtures.

All three per-case artifacts are digested: the movie, the ground-truth JSON and
the .star gate input. The STAR is checked separately because optics metadata --
pixel size, voltage, movie reference -- can change without moving a pixel, so the
movie digest alone cannot detect it.

By default, reads the manifest strictly from git (HEAD) to prevent generator-adjacent
overwrites from self-verifying noncanonical fixture data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

MANIFEST_REL_PATH = "test-data/known_motion/MANIFEST.json"
HEAVY_CASES = {"km_local_realscale"}
HEX_64_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(repo: Path, ref: str = "HEAD", explicit_path: Optional[Path] = None) -> Tuple[Dict[str, Any], str]:
    """Load manifest strictly from git ref, or explicit manifest path if specified.

    Fails closed if the git ref cannot be resolved or if git is unavailable.
    Does not fall back to an adjacent disk file when ref lookup fails.
    """
    if explicit_path is not None:
        if not explicit_path.is_file():
            raise FileNotFoundError(f"Explicit manifest file not found: {explicit_path}")
        try:
            data = json.loads(explicit_path.read_text())
        except Exception as exc:
            raise ValueError(f"Failed to parse manifest JSON from {explicit_path}: {exc}") from exc
        return data, f"file:{explicit_path}"

    proc = subprocess.run(
        ["git", "-C", str(repo), "show", f"{ref}:{MANIFEST_REL_PATH}"],
        capture_output=True, text=True
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"Failed to load trusted manifest from git ref '{ref}:{MANIFEST_REL_PATH}' (exit {proc.returncode}): "
            f"{proc.stderr.strip()}"
        )
    try:
        data = json.loads(proc.stdout)
    except Exception as exc:
        raise ValueError(f"Failed to parse git manifest JSON from {ref}:{MANIFEST_REL_PATH}: {exc}") from exc
    return data, f"git:{ref}:{MANIFEST_REL_PATH}"


def validate_manifest_schema(manifest: Any) -> Dict[str, Any]:
    """Validate that manifest contains a nonempty, schema-valid cases dictionary."""
    if not isinstance(manifest, dict):
        raise ValueError(f"Manifest root must be a JSON object, got {type(manifest).__name__}")
    cases = manifest.get("cases")
    if not isinstance(cases, dict) or len(cases) == 0:
        raise ValueError("Manifest 'cases' inventory is empty or malformed")

    for name, spec in cases.items():
        if not isinstance(spec, dict):
            raise ValueError(f"Case '{name}' spec must be a JSON object")
        movie_sha = spec.get("movie_sha256")
        if not movie_sha or not HEX_64_PATTERN.match(str(movie_sha)):
            raise ValueError(f"Case '{name}' missing valid 64-hex 'movie_sha256'")
        movie_bytes = spec.get("movie_bytes")
        if not isinstance(movie_bytes, int) or movie_bytes <= 0:
            raise ValueError(f"Case '{name}' missing valid positive 'movie_bytes'")
        gt_sha = spec.get("ground_truth_sha256")
        if not gt_sha or not HEX_64_PATTERN.match(str(gt_sha)):
            raise ValueError(f"Case '{name}' missing valid 64-hex 'ground_truth_sha256'")
        # The .star is a gate input: run_known_motion_gates.py reads its optics group for
        # pixel size and voltage and its movie reference. A manifest that does not pin it
        # cannot detect metadata drift that leaves the movie pixels untouched.
        star_sha = spec.get("star_sha256")
        if not star_sha or not HEX_64_PATTERN.match(str(star_sha)):
            raise ValueError(f"Case '{name}' missing valid 64-hex 'star_sha256'")

    return manifest


def verify_fixtures(
    fixtures_dir: Path,
    manifest: Dict[str, Any],
    allow_missing: bool = False,
    allow_missing_heavy: bool = True,
    cases_filter: Optional[List[str]] = None,
) -> Tuple[bool, Dict[str, Any]]:
    manifest = validate_manifest_schema(manifest)
    cases = manifest["cases"]

    report: Dict[str, Any] = {
        "schema": "fixture-verify/1",
        "fixtures_dir": str(fixtures_dir),
        "cases": {},
        "mismatched": [],
        "missing": [],
        "undeclared": [],
        "verified_count": 0,
        "excluded_heavy_count": 0,
    }

    target_cases = cases_filter if cases_filter is not None else sorted(cases.keys())
    if not target_cases:
        report["status"] = "FAIL"
        report["reason"] = "No target cases selected for verification"
        return False, report

    for case in target_cases:
        if case not in cases:
            report["cases"][case] = {
                "status": "NOT_IN_MANIFEST",
                "error": f"Requested case '{case}' is not declared in manifest",
            }
            report["mismatched"].append(case)
            continue

        spec = cases[case]
        path = fixtures_dir / f"{case}.mrcs"
        gt_path = fixtures_dir / f"{case}_ground_truth.json"
        want_sha = spec["movie_sha256"]
        want_bytes = spec["movie_bytes"]
        want_gt_sha = spec["ground_truth_sha256"]
        want_star_sha = spec["star_sha256"]
        star_path = fixtures_dir / f"{case}.star"
        is_heavy = case in HEAVY_CASES or bool(spec.get("heavy", False))

        if not path.exists():
            if is_heavy and allow_missing_heavy:
                report["cases"][case] = {
                    "status": "EXCLUDED_HEAVY",
                    "expected_sha256": want_sha,
                    "expected_bytes": want_bytes,
                    "is_heavy": True,
                }
                report["excluded_heavy_count"] += 1
                continue
            if allow_missing:
                report["cases"][case] = {
                    "status": "MISSING_ALLOWED",
                    "expected_sha256": want_sha,
                    "expected_bytes": want_bytes,
                    "is_heavy": is_heavy,
                }
                continue
            report["cases"][case] = {
                "status": "MISSING",
                "expected_sha256": want_sha,
                "expected_bytes": want_bytes,
                "is_heavy": is_heavy,
                "error": f"Movie file {path.name} not found",
            }
            report["missing"].append(case)
            continue

        got_bytes = path.stat().st_size
        got_sha = sha256_file(path)
        sha_ok = (got_sha == want_sha)
        bytes_ok = (got_bytes == want_bytes)

        case_entry: Dict[str, Any] = {
            "status": "PASS" if (sha_ok and bytes_ok) else "MISMATCH",
            "expected_sha256": want_sha,
            "observed_sha256": got_sha,
            "expected_bytes": want_bytes,
            "observed_bytes": got_bytes,
            "is_heavy": is_heavy,
        }

        # Ground-truth JSON check: REQUIRED for every verified case
        if not gt_path.is_file():
            case_entry["ground_truth_status"] = "MISSING"
            case_entry["error"] = f"Required ground-truth JSON {gt_path.name} is missing"
            case_entry["status"] = "MISSING"
            report["cases"][case] = case_entry
            report["missing"].append(f"{case}_ground_truth")
            continue

        got_gt_sha = sha256_file(gt_path)
        case_entry["ground_truth_sha256"] = got_gt_sha
        case_entry["expected_ground_truth_sha256"] = want_gt_sha

        if got_gt_sha != want_gt_sha:
            case_entry["ground_truth_status"] = "MISMATCH"
            case_entry["status"] = "MISMATCH"
            report["cases"][case] = case_entry
            report["mismatched"].append(f"{case}_ground_truth")
            continue

        case_entry["ground_truth_status"] = "PASS"

        # STAR input check: REQUIRED for every verified case, and deliberately independent of
        # the movie digest -- a pixel-size, voltage or movie-reference change does not move a
        # single pixel, so the movie hash cannot see it.
        if not star_path.is_file():
            case_entry["star_status"] = "MISSING"
            case_entry["error"] = f"Required STAR input {star_path.name} is missing"
            case_entry["status"] = "MISSING"
            report["cases"][case] = case_entry
            report["missing"].append(f"{case}_star")
            continue

        got_star_sha = sha256_file(star_path)
        case_entry["star_sha256"] = got_star_sha
        case_entry["expected_star_sha256"] = want_star_sha

        if got_star_sha != want_star_sha:
            case_entry["star_status"] = "MISMATCH"
            case_entry["status"] = "MISMATCH"
            report["cases"][case] = case_entry
            report["mismatched"].append(f"{case}_star")
            continue

        case_entry["star_status"] = "PASS"

        if not (sha_ok and bytes_ok):
            report["mismatched"].append(case)
        else:
            report["verified_count"] += 1

        report["cases"][case] = case_entry

    # Check for undeclared fixtures
    if fixtures_dir.is_dir():
        for f_path in sorted(fixtures_dir.glob("*.mrcs")):
            if f_path.stem not in cases:
                report["undeclared"].append(f_path.stem)

    failed = bool(report["mismatched"]) or bool(report["missing"]) or bool(report["undeclared"])
    if report["verified_count"] == 0:
        failed = True
        report["reason"] = "Zero fixtures were successfully verified"

    report["verified"] = not failed
    return not failed, report


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--fixtures-dir", type=Path, default=Path("test-data/known_motion"),
                        help="Directory containing fixture files")
    parser.add_argument("--repo", type=Path, default=Path("."),
                        help="Path to git repository root")
    parser.add_argument("--ref", default="HEAD",
                        help="Git ref to read manifest from (default: HEAD)")
    parser.add_argument("--manifest", type=Path, default=None,
                        help="Explicit path to manifest file (overrides git ref)")
    parser.add_argument("--allow-missing", action="store_true",
                        help="Do not fail on missing fixtures (only check existing ones)")
    parser.add_argument("--allow-missing-heavy", dest="allow_missing_heavy", action="store_true",
                        default=True, help="Allow heavy cases (e.g. km_local_realscale) to be omitted (default: True)")
    parser.add_argument("--no-allow-missing-heavy", dest="allow_missing_heavy", action="store_false",
                        help="Require heavy cases to be present")
    parser.add_argument("--cases", nargs="+", default=None,
                        help="Specific cases to check (default: all declared)")
    parser.add_argument("--json", type=Path, default=None,
                        help="Write machine-readable JSON report")
    parser.add_argument("--quiet", action="store_true",
                        help="Only print error summaries")
    opts = parser.parse_args()

    opts.fixtures_dir = opts.fixtures_dir.resolve()
    opts.repo = opts.repo.resolve()

    try:
        manifest, source = load_manifest(opts.repo, opts.ref, opts.manifest)
        manifest = validate_manifest_schema(manifest)
    except Exception as exc:
        print(f"ERROR: Cannot load trusted manifest: {exc}", file=sys.stderr)
        return 2

    success, report = verify_fixtures(
        fixtures_dir=opts.fixtures_dir,
        manifest=manifest,
        allow_missing=opts.allow_missing,
        allow_missing_heavy=opts.allow_missing_heavy,
        cases_filter=opts.cases,
    )

    if opts.json:
        opts.json.parent.mkdir(parents=True, exist_ok=True)
        opts.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

    if not opts.quiet:
        print(f"=== Canonical Fixture Verification ({source}) ===")
        for case, entry in sorted(report["cases"].items()):
            status = entry.get("status", "UNKNOWN")
            print(f"  {status:>15}  {case}")
            if status == "MISMATCH":
                print(f"      expected SHA256: {entry.get('expected_sha256')}")
                print(f"      observed SHA256: {entry.get('observed_sha256')}")
                print(f"      expected bytes:  {entry.get('expected_bytes')}")
                print(f"      observed bytes:  {entry.get('observed_bytes')}")
            if entry.get("ground_truth_status") == "MISMATCH":
                print(f"      ground-truth JSON hash MISMATCH:")
                print(f"        expected: {entry.get('expected_ground_truth_sha256')}")
                print(f"        observed: {entry.get('ground_truth_sha256')}")
            elif entry.get("ground_truth_status") == "MISSING":
                print(f"      ground-truth JSON MISSING: {entry.get('error')}")
            if entry.get("star_status") == "MISMATCH":
                print(f"      STAR input hash MISMATCH:")
                print(f"        expected: {entry.get('expected_star_sha256')}")
                print(f"        observed: {entry.get('star_sha256')}")
            elif entry.get("star_status") == "MISSING":
                print(f"      STAR input MISSING: {entry.get('error')}")
        if report["undeclared"]:
            print(f"  UNDECLARED FIXTURES: {', '.join(report['undeclared'])}")
        if report.get("reason"):
            print(f"  NOTE: {report['reason']}")

    if not success:
        print(f"ERROR: Fixture verification failed (mismatched={len(report['mismatched'])}, "
              f"missing={len(report['missing'])}, undeclared={len(report['undeclared'])})",
              file=sys.stderr)
        return 1

    if not opts.quiet:
        print(f"VERIFIED: {report['verified_count']} canonical fixtures match trusted manifest "
              f"({report['excluded_heavy_count']} heavy cases excluded).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
