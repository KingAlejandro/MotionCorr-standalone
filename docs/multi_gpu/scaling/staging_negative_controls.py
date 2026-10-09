"""Targeted mutations of the staging code; each must make its test fail.

Run from anywhere: python3 docs/multi_gpu/scaling/staging_negative_controls.py [name ...]
Each mutation is applied in place and restored in a finally block.
"""
import subprocess, sys
from pathlib import Path
R = Path(__file__).resolve().parents[3]
M = R/"tools/multi_gpu/merge_workers.py"; L = R/"tools/multi_gpu/run_multi_gpu.py"; D = R/"tools/multi_gpu/output_digests.py"
muts = [
 ("no copy fallback", M, "                if exc.errno not in LINK_FALLBACK_ERRNOS:\n                    raise", "                raise", "link_refusal_falls_back"),
 ("fallback on any errno", M, "                if exc.errno not in LINK_FALLBACK_ERRNOS:\n                    raise", "                pass", "link_refusal_falls_back"),
 ("copy is default staging", M, 'choices=("auto", "link", "copy"), default="auto"', 'choices=("auto", "link", "copy"), default="copy"', "link_staging_with_aggregate"),
 ("record not compared", M, "        if record is not None and sha != record[\"sha256\"]:", "        if False:", "change_after_worker_exit"),
 ("no presence check", M, "            for rel in sorted(now - set(records[k])):", "            for rel in []:", "change_after_worker_exit"),
 ("no missing check", M, "            for rel in sorted(set(records[k]) - now):", "            for rel in []:", "change_after_worker_exit"),
 ("digest never reused", M, "        sha = record[\"sha256\"] if record is not None and record[\"key\"] == key else None", "        sha = None", "launcher_exit_digests_are_reused"),
 ("reuse ignores key", M, "        sha = record[\"sha256\"] if record is not None and record[\"key\"] == key else None", "        sha = record[\"sha256\"] if record is not None else None", "change_after_worker_exit"),
 ("failed record ignored", M, "        if worker.get(\"returncode\") == 0:\n            problems.append(f\"worker {k}: outputs were not digested", "        if False:\n            problems.append(f\"worker {k}: outputs were not digested", "exit_digest_records_validated"),
 ("per-file error ignored", M, "                if \"error\" in records[k][rel]:", "                if False:", "exit_digest_records_validated"),
 ("hex not validated", M, "and hexdigest.fullmatch(v[\"sha256\"])", "", "exit_digest_records_validated"),
 ("no final verdict recompute", M, "    # taken from the final list.\n    report[\"verdict\"] = \"PASS\" if not problems else \"FAIL\"", "    # taken from the final list.", "timestamp_barrier_failure"),
 ("merge barrier removed", M, "            output_digests.ctime_barrier(out / \"_workers\", max((k[4] for k in keys), default=0),\n                                         {k[0] for k in keys})", "            pass", "timestamp_barrier_failure"),
 ("after-check by bytes only", M, "            if now == staged[rel][\"dst_key\"]:\n                return rel, False, False", "            if output_digests.hash_file(out / rel, now) == staged[rel][\"sha256\"]:\n                return rel, False, False", "aggregate_same_byte_rewrite"),
 ("staged digest recomputed after aggregate", M, "    if a.report:\n        Path(a.report).write_text", "    report[\"staged_sha256\"] = {str(rel): __import__('hashlib').sha256((out / rel).read_bytes()).hexdigest() for rel in staged}\n    if a.report:\n        Path(a.report).write_text", "aggregate_may_not_rewrite"),
 ("launcher takes no exit digest", L, "            if rc != 0:\n                return\n            t0", "            return\n            t0", "launcher_exit_digests_are_reused"),
 ("digest_tree no barrier", D, "    if keys:\n        ctime_barrier(", "    if False:\n        ctime_barrier(", "output_digest_primitives"),
 ("hash_file no key check", D, "    with open(path, \"rb\") as fh:\n        if stat_key(os.fstat(fh.fileno())) != key:", "    with open(path, \"rb\") as fh:\n        key = stat_key(os.fstat(fh.fileno()))\n        if stat_key(os.fstat(fh.fileno())) != key:", "output_digest_primitives"),
 ("barrier ignores devices", D, "        if devices - {dev}:", "        if False:", "output_digest_primitives"),
 ("stop ignored", D, "    if stop is not None and stop.is_set():\n        raise RuntimeError", "    if False:\n        raise RuntimeError", "output_digest_primitives"),
]
bad = 0
sel = sys.argv[1:]
for name, f, old, new, only in muts:
    if sel and name not in sel: continue
    src = f.read_text()
    if src.count(old) != 1:
        print(f"SKIP-BAD-PATTERN {name} ({src.count(old)})"); bad += 1; continue
    try:
        f.write_text(src.replace(old, new))
        cp = subprocess.run([sys.executable, str(R/"tests/test_multi_gpu_scheduling.py"), "--only", only],
                            capture_output=True, text=True, cwd=R)
        line = [l for l in cp.stdout.splitlines() if l.startswith(("FAIL", "ERROR"))]
        verdict = "KILLED" if cp.returncode != 0 else "SURVIVED"
        if cp.returncode == 0: bad += 1
        print(f"{verdict:8} {name} [{only}] {line[0][:160] if line else ''}")
    finally:
        f.write_text(src)
print("bad:", bad)
sys.exit(1 if bad else 0)
