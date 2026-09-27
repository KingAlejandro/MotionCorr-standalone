#!/usr/bin/env python3
"""Check generated fixtures against the committed known-motion manifest.

Ensures fixture files match the trusted, committed MANIFEST.json byte-for-byte
and digest-for-digest. Rejects missing fixtures, corrupted/byte-flipped fixtures,
and undeclared fixtures.

By default, reads the manifest from git (HEAD) to prevent generator-adjacent
overwrites from self-verifying noncanonical fixture data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

MANIFEST_REL_PATH = "test-data/known_motion/MANIFEST.json"
HEAVY_CASES = {"km_local_realscale"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(repo: Path, ref: str = "HEAD", explicit_path: Optional[Path] = None) -> Tuple[Dict[str, Any], str]:
    """Load manifest from git if possible, or explicit path / disk fallback."""
    if explicit_path is not None:
        if not explicit_path.is_file():
            raise FileNotFoundError(f"Explicit manifest file not found: {explicit_path}")
        return json.loads(explicit_path.read_text()), f"file:{explicit_path}"

    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "show", f"{ref}:{MANIFEST_REL_PATH}"],
            capture_output=True, text=True, check=True
        ).stdout
        return json.loads(out), f"git:{ref}:{MANIFEST_REL_PATH}"
    except (subprocess.CalledProcessError, FileNotFoundError):
        fallback = repo / MANIFEST_REL_PATH
        if fallback.is_file():
            return json.loads(fallback.read_text()), f"disk:{fallback}"
        raise RuntimeError(f"Cannot load manifest from git {ref}:{MANIFEST_REL_PATH} or disk {fallback}")


def verify_fixtures(
    fixtures_dir: Path,
    manifest: Dict[str, Any],
    allow_missing: bool = False,
    allow_missing_heavy: bool = True,
    cases_filter: Optional[List[str]] = None,
) -> Tuple[bool, Dict[str, Any]]:
    cases = manifest.get("cases", {})
    report: Dict[str, Any] = {
        "schema": "fixture-verify/1",
        "fixtures_dir": str(fixtures_dir),
        "cases": {},
        "mismatched": [],
        "missing": [],
        "undeclared": [],
    }

    target_cases = cases_filter if cases_filter is not None else sorted(cases.keys())

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
        want_sha = spec.get("movie_sha256")
        want_bytes = spec.get("movie_bytes")
        is_heavy = case in HEAVY_CASES or bool(spec.get("heavy", False))

        if not path.exists():
            can_skip = allow_missing or (is_heavy and allow_missing_heavy)
            status = "MISSING_ALLOWED" if can_skip else "MISSING"
            report["cases"][case] = {
                "status": status,
                "expected_sha256": want_sha,
                "expected_bytes": want_bytes,
                "is_heavy": is_heavy,
            }
            if not can_skip:
                report["missing"].append(case)
            continue

        got_bytes = path.stat().st_size
        got_sha = sha256_file(path)
        sha_ok = (got_sha == want_sha)
        bytes_ok = (got_bytes == want_bytes)
        ok = sha_ok and bytes_ok

        case_entry: Dict[str, Any] = {
            "status": "PASS" if ok else "MISMATCH",
            "expected_sha256": want_sha,
            "observed_sha256": got_sha,
            "expected_bytes": want_bytes,
            "observed_bytes": got_bytes,
            "is_heavy": is_heavy,
        }

        # Check ground truth JSON if present
        gt_path = fixtures_dir / f"{case}_ground_truth.json"
        if gt_path.is_file() and "ground_truth_sha256" in spec:
            gt_sha = sha256_file(gt_path)
            case_entry["ground_truth_sha256"] = gt_sha
            case_entry["expected_ground_truth_sha256"] = spec["ground_truth_sha256"]
            if gt_sha != spec["ground_truth_sha256"]:
                case_entry["ground_truth_status"] = "MISMATCH"
                ok = False
                case_entry["status"] = "MISMATCH"
            else:
                case_entry["ground_truth_status"] = "PASS"

        report["cases"][case] = case_entry
        if not ok:
            report["mismatched"].append(case)

    # Check for undeclared fixtures
    if fixtures_dir.is_dir():
        for path in sorted(fixtures_dir.glob("*.mrcs")):
            if path.stem not in cases:
                report["undeclared"].append(path.stem)

    failed = bool(report["mismatched"]) or bool(report["missing"]) or bool(report["undeclared"])
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
    except Exception as exc:
        print(f"ERROR: Cannot load manifest: {exc}", file=sys.stderr)
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
        if report["undeclared"]:
            print(f"  UNDECLARED FIXTURES: {', '.join(report['undeclared'])}")

    if not success:
        print(f"ERROR: Fixture verification failed (mismatched={len(report['mismatched'])}, "
              f"missing={len(report['missing'])}, undeclared={len(report['undeclared'])})",
              file=sys.stderr)
        return 1

    if not opts.quiet:
        print("VERIFIED: All canonical fixtures match trusted manifest.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
