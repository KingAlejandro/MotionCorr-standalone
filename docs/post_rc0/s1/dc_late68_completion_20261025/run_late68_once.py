#!/usr/bin/env python3
"""Strict one-shot CPU64 caller for the exact late68 B ROOT only."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import resource
import shutil
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "COLLECTION-MANIFEST.json"
IDS_FILE = HERE / "late68-ids.txt"
SOURCE_CLOSURE = HERE / "SOURCE-CLOSURE.json"
EVALUATOR = HERE / "source" / "evaluate-late68-v1.py"
EXPECTED_IDS_SHA256 = "b43462cf148c76c7bffd663aba29ee3e42de647804256b0c60637f36063d01a9"
EXPECTED_EVALUATOR_SHA256 = "66903f90da17c72d785f1c18ff6149b5cf4cc4ad3ed940c39027c02422e114b7"
EXPECTED_ORIGINAL_SHA256 = "dcc5ddb3d52d14652f11214fb2a9339fb5fb63637d87dc0c82ee3a4c2d0de14d"
EXPECTED_CURRENT_GUARD_SHA256 = "e535f1de3c681b83af82503080e79dda376cc3a7bcd2d323f65cdb14b022d681"
EXPECTED_MANIFEST_SHA256 = "37e8a35895a58863a57a5f668ecdfa1cbc1f86d99e5d289e10fa9dd8b9e0993c"
EXPECTED_SOURCE_CLOSURE_SHA256 = "b2e94f1923417300550487f25cbc71adb1a910f528b706afdb73f89727bcb43a"
SOURCE_ROOT = "/mnt/clathrin/alex-motioncorr-dc-fourarm-20261022-3eee0a4b"
RAM_CAP = 8 * 1024**3
SMALL_FILE_CAP = 16 * 1024**2
MIN_SCRATCH_BUDGET = 12 * 1024**3
CHUNK = 1 << 20


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def json_file(path: Path):
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def admission_check(path: Path) -> dict:
    a = json_file(path)
    if a.get("scope") != "dc-late68-evaluator-only":
        raise ValueError("admission scope is not dc-late68-evaluator-only")
    captured = dt.datetime.fromisoformat(a["captured_utc"].replace("Z", "+00:00"))
    age = (dt.datetime.now(dt.timezone.utc) - captured).total_seconds()
    if age < -60 or age > 600:
        raise ValueError(f"resource admission is stale or future-dated: age={age:.1f}s")
    required = {
        "cpu_core": 62,
        "cpu_lock_held": True,
        "busy_check_clear": True,
        "active_evaluator_processes": 0,
        "ram_cap_bytes": RAM_CAP,
    }
    for k, value in required.items():
        if a.get(k) != value:
            raise ValueError(f"admission mismatch for {k}: {a.get(k)!r} != {value!r}")
    if int(a.get("available_ram_bytes", 0)) < RAM_CAP:
        raise ValueError("fresh admission has less than 8 GiB available RAM")
    if int(a.get("scratch_budget_bytes", 0)) < MIN_SCRATCH_BUDGET:
        raise ValueError("fresh admission lacks a 12 GiB scratch budget")
    return a


def safe_relative(value: str) -> PurePosixPath:
    p = PurePosixPath(value)
    if p.is_absolute() or not p.parts or any(x in ("", ".", "..") for x in p.parts) or "\\" in value:
        raise ValueError(f"unsafe stage path: {value!r}")
    return p


def verify_stage(root: Path, manifest: dict, ids: list[str]) -> dict:
    if not root.is_dir() or root.resolve() == Path(SOURCE_ROOT):
        raise ValueError("stage root must be a distinct new directory")
    if str(root.resolve()).startswith(SOURCE_ROOT + "/"):
        raise ValueError("stage root cannot be inside the frozen campaign source root")

    expected = {item["stage"]: item for item in manifest["all_files"]}
    if len(expected) != len(manifest["all_files"]):
        raise ValueError("duplicate paths in static collection manifest")
    seen = set()
    for relative, item in expected.items():
        safe_relative(relative)
        path = root.joinpath(*PurePosixPath(relative).parts)
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(root.resolve()):
            raise ValueError(f"staged path escapes root: {relative}")
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"staged input is not a regular file: {relative}")
        size = path.stat().st_size
        if item.get("bytes") is not None and size != int(item["bytes"]):
            raise ValueError(f"size mismatch for {relative}: {size} != {item['bytes']}")
        large = relative.endswith(".mrc") or relative.startswith("truth/")
        if not large and size > SMALL_FILE_CAP:
            raise ValueError(f"small staged file exceeds 16 MiB: {relative}")
        if large and not (relative.endswith(".mrc") or relative.startswith("truth/")):
            raise ValueError(f"unexpected large staged member: {relative}")
        if sha256_file(path) != item["sha256"]:
            raise ValueError(f"SHA-256 mismatch for staged input: {relative}")
        seen.add(relative)

    actual = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"symlink in stage: {path.relative_to(root)}")
        if path.is_file():
            actual.add(path.relative_to(root).as_posix())
    if actual != seen:
        raise ValueError(f"stage file set differs: extra={sorted(actual-seen)[:5]} missing={sorted(seen-actual)[:5]}")

    runs_root = root / "runs"
    run_dirs = {p.name for p in runs_root.iterdir() if p.is_dir()}
    if run_dirs != set(ids):
        raise ValueError("staged runs directory does not contain exactly the frozen 68 IDs")
    for ident in ids:
        rec = json_file(runs_root / ident / "RUN.json")
        if (rec.get("id"), rec.get("tier"), rec.get("backend"), rec.get("exit"),
            rec.get("source_sha")) != (ident, "B", "cpu", 0, "3eee0a4b4e367f9b57f950c440c89679a5ec9c93"):
            raise ValueError(f"RUN identity/exit/source mismatch: {ident}")
        original_receipt = str(Path(rec["cwd"]) / "RECEIPT.json")
        receipt_stage = f"fixture-receipts/{ident}/RECEIPT.json"
        if rec.get("inputs", {}).get(original_receipt) != expected[receipt_stage]["sha256"]:
            raise ValueError(f"staged recipe receipt does not match RUN input pin: {ident}")
        if rec.get("arm") != "plain":
            for rel in ("runtime.json", "output/movie.star", "output/movie.log", "output/movie.mrc"):
                item = expected[f"runs/{ident}/{rel}"]
                pin = rec.get("outputs", {}).get(rel, {})
                if item["sha256"] != pin.get("sha256") or item["bytes"] != pin.get("bytes"):
                    raise ValueError(f"staged input differs from RUN output pin: {ident}/{rel}")
    eval_dir = root / "eval"
    if eval_dir.exists() and any(eval_dir.iterdir()):
        raise ValueError("new ROOT eval directory is not empty")


def parse_outputs(root: Path, ids: list[str]) -> dict:
    rows = {}
    out_dir = root / "eval" / "B"
    for ident in ids:
        p = out_dir / f"{ident}.json"
        if not p.is_file():
            rows[ident] = {"state": "MISSING"}
            continue
        size = p.stat().st_size
        if size > SMALL_FILE_CAP:
            rows[ident] = {"state": "OUTPUT_TOO_LARGE", "bytes": size}
            continue
        digest = sha256_file(p)
        try:
            row = json_file(p)
            if row.get("id") != ident or not isinstance(row.get("status"), str):
                raise ValueError("missing identity or status")
            rows[ident] = {"state": row["status"], "bytes": size, "sha256": digest}
        except Exception as exc:
            rows[ident] = {"state": "MALFORMED", "bytes": size, "sha256": digest,
                           "error": f"{type(exc).__name__}: {exc}"}
    return rows


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path, help="fresh staged B ROOT containing exactly the manifest")
    parser.add_argument("--admission", required=True, type=Path, help="fresh parent CPU64 admission JSON")
    args = parser.parse_args()

    if sha256_file(IDS_FILE) != EXPECTED_IDS_SHA256:
        raise SystemExit("ID list hash mismatch")
    if sha256_file(EVALUATOR) != EXPECTED_EVALUATOR_SHA256:
        raise SystemExit("amended evaluator hash mismatch")
    if sha256_file(HERE / "source" / "evaluate-original.py") != EXPECTED_ORIGINAL_SHA256:
        raise SystemExit("original deployed evaluator hash mismatch")
    if sha256_file(MANIFEST) != EXPECTED_MANIFEST_SHA256:
        raise SystemExit("static collection manifest hash mismatch")
    if sha256_file(SOURCE_CLOSURE) != EXPECTED_SOURCE_CLOSURE_SHA256:
        raise SystemExit("source closure manifest hash mismatch")
    current_guard_path = HERE / "CURRENT-EVAL-GUARD.json"
    if sha256_file(current_guard_path) != EXPECTED_CURRENT_GUARD_SHA256:
        raise SystemExit("current evaluation guard hash mismatch")
    current_guard = json_file(current_guard_path)
    if current_guard.get("all_current_B_json_count") != 345:
        raise SystemExit("current B evaluation count differs from captured guard")
    current_rows = current_guard.get("late68_current_evaluations", {})
    if set(current_rows) != set(IDS_FILE.read_text(encoding="utf-8").splitlines()) or any(
        row.get("exists") is not False for row in current_rows.values()
    ):
        raise SystemExit("selected IDs are not all absent from current eval snapshot")

    manifest = json_file(MANIFEST)
    ids = IDS_FILE.read_text(encoding="utf-8").splitlines()
    if (len(ids), len(set(ids)), manifest.get("ids_sha256")) != (68, 68, EXPECTED_IDS_SHA256):
        raise SystemExit("frozen late68 ID contract mismatch")
    closure = json_file(SOURCE_CLOSURE)
    if closure.get("all_deployed_hashes_complete") is not True:
        raise SystemExit("deployed import closure is incomplete")
    closure_pins = {x["stage"]: x["sha256"] for x in closure["modules"]}
    manifest_pins = {x["stage"]: x["sha256"] for x in manifest["all_files"]}
    if any(manifest_pins.get(path) != digest for path, digest in closure_pins.items()):
        raise SystemExit("source closure and collection manifest disagree")
    if sha256_file(HERE / "source" / "evaluate-original.py") != manifest["all_files"][
        next(i for i, x in enumerate(manifest["all_files"]) if x["stage"] == "source/evaluate-original.py")
    ]["sha256"]:
        raise SystemExit("source manifest evaluator pin mismatch")

    admission = admission_check(args.admission)
    root = args.root.resolve(strict=True)
    available = os.sched_getaffinity(0)
    if 62 not in available:
        raise SystemExit("CPU 62 is not available to this process")
    os.sched_setaffinity(0, {62})
    if os.sched_getaffinity(0) != {62}:
        raise SystemExit("failed to bind the runner to CPU 62")
    if shutil.disk_usage(root).free < 1024**3:
        raise SystemExit("less than 1 GiB free beside staged inputs")
    if str(Path(sys.executable).resolve()) != str(Path(admission["python_executable"]).resolve()):
        raise SystemExit("Python executable differs from the fresh admission")
    verify_stage(root, manifest, ids)
    source_id = (root / "source/SOURCE_SHA").read_text(encoding="utf-8").strip()
    if source_id != "3eee0a4b4e367f9b57f950c440c89679a5ec9c93":
        raise SystemExit("staged SOURCE_SHA differs from the frozen experiment source")

    marker = root / "LATE68-ONCE.json"
    try:
        fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise SystemExit("one-shot marker already exists; no retries")
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump({"started_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                   "ids_sha256": EXPECTED_IDS_SHA256, "evaluator_sha256": EXPECTED_EVALUATOR_SHA256,
                   "manifest_sha256": EXPECTED_MANIFEST_SHA256, "admission": str(args.admission)}, stream)
        stream.write("\n")

    out_dir = root / "eval" / "B"
    out_dir.mkdir(parents=True, exist_ok=False)
    env = os.environ.copy()
    for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        env[key] = "1"

    def child_limits():
        resource.setrlimit(resource.RLIMIT_AS, (RAM_CAP, RAM_CAP))
        resource.setrlimit(resource.RLIMIT_FSIZE, (SMALL_FILE_CAP, SMALL_FILE_CAP))
        os.sched_setaffinity(0, {62})

    stdout_path = root / "LATE68-stdout.log"
    stderr_path = root / "LATE68-stderr.log"
    command = [sys.executable, "-I", "-B", str(EVALUATOR), "B", str(root)]
    started = time.monotonic()
    with stdout_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
        child = subprocess.run(command, cwd=root, env=env, stdout=stdout, stderr=stderr,
                               preexec_fn=child_limits, check=False)
    elapsed = time.monotonic() - started
    if stdout_path.stat().st_size > SMALL_FILE_CAP or stderr_path.stat().st_size > SMALL_FILE_CAP:
        raise SystemExit("evaluator log exceeded 16 MiB output cap")
    rows = parse_outputs(root, ids)
    complete = all(isinstance(row.get("state"), str) and "sha256" in row for row in rows.values())
    receipt = {
        "scope": "late68 B/CPU existing-output evaluation only",
        "evaluator_argv": command,
        "evaluator_source_sha256": EXPECTED_EVALUATOR_SHA256,
        "original_evaluator_sha256": EXPECTED_ORIGINAL_SHA256,
        "collection_manifest_sha256": EXPECTED_MANIFEST_SHA256,
        "source_closure_sha256": EXPECTED_SOURCE_CLOSURE_SHA256,
        "ids_sha256": EXPECTED_IDS_SHA256,
        "ids_count": len(ids),
        "root": str(root),
        "python": sys.executable,
        "cpu_affinity": sorted(os.sched_getaffinity(0)),
        "memory_cap_bytes": RAM_CAP,
        "small_output_cap_bytes": SMALL_FILE_CAP,
        "admission": admission,
        "elapsed_s": elapsed,
        "child_exit": child.returncode,
        "recorded_all_68": complete,
        "records": rows,
        "baseline_736_imported": False,
        "current_eval_345_imported": False,
        "scientific_grade": "NOT_ASSIGNED_BY_RUNNER"
    }
    result_path = root / "LATE68-RESULT.json"
    with result_path.open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, indent=2, sort_keys=True)
        stream.write("\n")
    return 0 if child.returncode == 0 and complete else 2


if __name__ == "__main__":
    raise SystemExit(main())
