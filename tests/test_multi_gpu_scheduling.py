#!/usr/bin/env python3
"""CPU-only scheduling controls for #53: partition, merge, failure and resume.

No GPU, no tutorial dataset, no real binary required for the scheduling cases --
they run against tests/fake_worker.py, which reproduces the output naming and
fixed-name aggregates a real process writes. The point is to catch dropped,
duplicated or misrouted movies and mangled metadata before any hardware time is
spent.

Faults are injected rather than assumed: most cases here *are* the negative
control for a guard. The Python-side guards are additionally covered by
docs/multi_gpu/negative_controls.py, which removes each one in a scratch copy
and requires the corresponding case to fail. The one guard that harness cannot
reach is the C++ device-list rejection, because mutating it needs a rebuild;
its control is the recorded unpatched-main binary, which produces a different
message for the same input (docs/multi_gpu/gpu_evidence/a0_device_list_witness.log).

With --binary pointing at a built motioncorr, the --gpu device-list rejection is
also exercised against the real argument parser.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import signal
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools" / "multi_gpu"
FAKE = ROOT / "tests" / "fake_worker.py"
sys.path.insert(0, str(TOOLS))
import star_io  # noqa: E402

PY = sys.executable

OPTICS = """
# version 30001

data_optics

loop_
_rlnOpticsGroupName #1
_rlnOpticsGroup #2
_rlnMicrographOriginalPixelSize #3
_rlnVoltage #4
_rlnSphericalAberration #5
_rlnAmplitudeContrast #6
opticsGroup1            1     0.885000   200.000000     1.400000     0.100000
'optics group two'      2     1.070000   300.000000     2.700000     0.070000

data_movies

loop_
_rlnMicrographMovieName #1
_rlnOpticsGroup #2
_rlnMicrographPreExposure #3
"""


def build_star(path: Path, rows: list[tuple[str, int, float]]) -> None:
    text = OPTICS.lstrip("\n")
    for name, optics, pre in rows:
        token = f"'{name}'" if " " in name else name
        text += f"{token} {optics} {pre:.6f}\n"
    text += "\n"
    path.write_text(text)


DEFAULT_ROWS = [
    ("Movies/20170629_00021_frameImage.tiff", 1, 0.000000),
    ("Movies/20170629_00022_frameImage.tiff", 1, 1.400000),
    ("Movies/20170629_00023_frameImage.tiff", 2, 2.800000),
    ("Movies/sub dir/20170629_00024_frameImage.tiff", 2, 4.200000),
    ("Movies/20170629_00025_frameImage.tiff", 1, 5.600000),
    ("Movies/20170629_00026_frameImage.tiff", 2, 7.000000),
]


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run([str(c) for c in cmd], capture_output=True, text=True, **kw)


def partition(star: Path, n: int, outdir: Path, extra: list[str] | None = None):
    return run([PY, TOOLS / "partition_star.py", "--star", star, "--n", n,
                "--outdir", outdir] + (extra or []))


def merge(manifest: Path, workers: list[Path], out: Path, status: Path | None,
          report: Path | None = None, extra: list[str] | None = None):
    cmd = [PY, TOOLS / "merge_workers.py", "--manifest", manifest, "--out", out,
           "--workers"] + list(workers)
    if status:
        cmd += ["--status", status]
    if report:
        cmd += ["--report", report]
    return run(cmd + (extra or []))


def fake_status(tmp: Path, codes: list[int], verdict: str = "PASS",
                witness: dict | None = None, name: str = "status.json",
                manifest: Path | None = None,
                workers: list[Path] | None = None) -> Path:
    """A launcher status bound to the run it describes.

    merge_workers.py refuses a status that cannot be shown to describe the
    manifest and worker directories being merged, so this mirrors exactly what
    run_multi_gpu.py records: the resolved manifest path, its digest, and each
    worker's log path under its own directory. Defaults match run_workers().
    """
    p = tmp / name
    man = Path(manifest) if manifest is not None else tmp / "shards" / "shard_manifest.json"
    wdirs = workers if workers is not None else [tmp / f"w{k}" for k in range(len(codes))]
    body: dict = {"workers": [{"index": k, "returncode": rc,
                               "log": str((Path(wdirs[k]) / "run.log").resolve())}
                              for k, rc in enumerate(codes)],
                  "manifest": str(man.resolve()),
                  "manifest_sha256": hashlib.sha256(man.read_bytes()).hexdigest()
                                     if man.exists() else "",
                  "verdict": verdict}
    if witness is not None:
        body["gpu_witness"] = witness
    p.write_text(json.dumps(body))
    return p


def run_workers(tmp: Path, shard_dir: Path, n: int, prefix: str = "shard",
                per_worker: dict[int, list[str]] | None = None,
                resume: set[int] | None = None) -> tuple[list[Path], list[int]]:
    dirs, codes = [], []
    for k in range(n):
        wdir = tmp / f"w{k}"
        wdir.mkdir(exist_ok=True)
        cmd = [PY, FAKE, "--i", shard_dir / f"{prefix}_{n}way_{k}.star", "--o", wdir]
        if resume and k in resume:
            cmd.append("--only_do_unfinished")
        cmd += (per_worker or {}).get(k, [])
        cp = run(cmd)
        dirs.append(wdir)
        codes.append(cp.returncode)
    return dirs, codes


# --------------------------------------------------------------------------
# cases
# --------------------------------------------------------------------------

def case_roundtrip_and_metadata(tmp: Path) -> None:
    """Shards preserve optics, exposure and quoted paths byte for byte."""
    star = tmp / "movies.star"
    build_star(star, DEFAULT_ROWS)
    shards = tmp / "shards"
    cp = partition(star, 3, shards)
    assert cp.returncode == 0, cp.stderr

    src = star_io.parse(star)
    src_block = star_io.movie_block(src)
    src_rows = {r.values[src_block.column(star_io.MOVIE_LABEL)]: r for r in src_block.rows}

    optics_src = src.block("optics")
    seen: list[str] = []
    for k in range(3):
        sp = shards / f"shard_3way_{k}.star"
        sh = star_io.parse(sp)
        # optics block is byte-identical, so pixel size / voltage / group names
        # cannot have been altered by partitioning
        assert "".join(sh.lines[sh.block("optics").start : sh.block("movies").start]) == \
               "".join(src.lines[optics_src.start : src.block("movies").start]), \
               f"shard {k} optics block differs from input"
        blk = star_io.movie_block(sh)
        assert blk.labels == src_block.labels, f"shard {k} labels differ"
        for r in blk.rows:
            name = r.values[blk.column(star_io.MOVIE_LABEL)]
            assert r.raw == src_rows[name].raw, f"row bytes changed for {name}"
            assert r.values == src_rows[name].values, f"row values changed for {name}"
            seen.append(name)
    canonical = [r.values[src_block.column(star_io.MOVIE_LABEL)] for r in src_block.rows]
    assert seen == canonical, f"partition lost canonical order: {seen}"
    assert "Movies/sub dir/20170629_00024_frameImage.tiff" in seen, \
        "quoted path with a space was not carried through"

    man = json.loads((shards / "shard_manifest.json").read_text())
    assert man["canonical_movies"] == canonical
    assert sum(s["n_movies"] for s in man["shards"]) == len(canonical)


def case_empty_shard_rejected(tmp: Path) -> None:
    """More shards than movies is refused, not silently given a worker no work."""
    star = tmp / "movies.star"
    build_star(star, DEFAULT_ROWS[:2])
    cp = partition(star, 4, tmp / "shards")
    assert cp.returncode != 0, "empty shard was accepted"
    assert "empty shard" in cp.stderr, cp.stderr
    # positive control: the same input with a feasible shard count succeeds
    cp = partition(star, 2, tmp / "shards_ok")
    assert cp.returncode == 0, cp.stderr


def case_output_name_collision(tmp: Path) -> None:
    """Two movies that collapse to one output root are refused up front."""
    rows = list(DEFAULT_ROWS[:2]) + [
        ("Movies/set.1/a.tiff", 1, 0.0),
        ("Movies/set_1/a.tiff", 1, 1.4),
    ]
    star = tmp / "movies.star"
    build_star(star, rows)
    cp = partition(star, 2, tmp / "shards")
    assert cp.returncode == 3, f"collision not caught (rc={cp.returncode})"
    assert "output-name collision" in cp.stderr, cp.stderr
    assert star_io.output_root("Movies/set.1/a.tiff") == \
           star_io.output_root("Movies/set_1/a.tiff")
    # positive control: without the aliasing pair the same input partitions
    build_star(star, list(DEFAULT_ROWS[:2]) + [("Movies/set_2/a.tiff", 1, 0.0)])
    assert partition(star, 2, tmp / "shards_ok").returncode == 0


def case_duplicate_movie_in_input(tmp: Path) -> None:
    """A movie listed twice in the input is refused."""
    rows = list(DEFAULT_ROWS[:3]) + [DEFAULT_ROWS[0]]
    star = tmp / "movies.star"
    build_star(star, rows)
    cp = partition(star, 2, tmp / "shards")
    assert cp.returncode == 3, f"duplicate input row not caught (rc={cp.returncode})"
    assert "duplicate movie in input" in cp.stderr, cp.stderr


def case_clean_merge(tmp: Path) -> None:
    """A clean sharded run merges, with every movie present exactly once."""
    star = tmp / "movies.star"
    build_star(star, DEFAULT_ROWS)
    shards = tmp / "shards"
    assert partition(star, 3, shards).returncode == 0
    dirs, codes = run_workers(tmp, shards, 3)
    assert codes == [0, 0, 0], codes
    status = fake_status(tmp, codes)
    report = tmp / "report.json"
    cp = merge(shards / "shard_manifest.json", dirs, tmp / "merged", status, report)
    assert cp.returncode == 0, cp.stderr
    rep = json.loads(report.read_text())
    assert rep["verdict"] == "PASS", rep["problems"]
    assert rep["n_movies_expected"] == 6

    # Metadata that went in comes out: each per-movie STAR still carries the
    # optics group and pre-exposure from the row it was partitioned from.
    for name, optics, pre in DEFAULT_ROWS:
        root = star_io.output_root(name)
        payload = json.loads((tmp / "merged" / (root + ".star")).read_text())
        assert payload["rlnMicrographMovieName"] == name, payload
        assert payload["rlnOpticsGroup"] == str(optics), payload
        assert abs(float(payload["rlnMicrographPreExposure"]) - pre) < 1e-9, payload

    # Per-worker fixed-name aggregates are preserved, not merged or dropped.
    assert any(p.endswith("w0/corrected_micrographs.star")
               for p in rep["per_worker_aggregates_preserved"]), rep
    assert not (tmp / "merged" / "corrected_micrographs.star").exists(), \
        "an unauthoritative aggregate was published into the merged tree"
    assert not (tmp / "merged" / "logfile.pdf").exists(), \
        "a logfile.pdf was published despite being path-dependent"


def case_lost_output(tmp: Path) -> None:
    """A movie a worker silently failed to produce fails the merge."""
    star = tmp / "movies.star"
    build_star(star, DEFAULT_ROWS)
    shards = tmp / "shards"
    assert partition(star, 3, shards).returncode == 0
    lost = DEFAULT_ROWS[2][0]
    dirs, codes = run_workers(tmp, shards, 3,
                              per_worker={1: ["--fake_skip", lost]})
    status = fake_status(tmp, codes)
    report = tmp / "report.json"
    cp = merge(shards / "shard_manifest.json", dirs, tmp / "merged", status, report)
    assert cp.returncode == 3, f"lost movie not caught (rc={cp.returncode})"
    rep = json.loads(report.read_text())
    assert any(p.startswith("lost:") and lost in p for p in rep["problems"]), rep["problems"]


def case_duplicate_and_misrouted_output(tmp: Path) -> None:
    """A worker producing a movie it was not assigned is caught twice over."""
    star = tmp / "movies.star"
    build_star(star, DEFAULT_ROWS)
    shards = tmp / "shards"
    assert partition(star, 3, shards).returncode == 0
    man = json.loads((shards / "shard_manifest.json").read_text())
    stolen = man["shards"][1]["movies"][0]
    dirs, codes = run_workers(tmp, shards, 3,
                              per_worker={0: ["--fake_extra", stolen]})
    status = fake_status(tmp, codes)
    report = tmp / "report.json"
    cp = merge(shards / "shard_manifest.json", dirs, tmp / "merged", status, report)
    assert cp.returncode == 3, f"duplicate output not caught (rc={cp.returncode})"
    rep = json.loads(report.read_text())
    assert any(p.startswith("misrouted:") for p in rep["problems"]), rep["problems"]
    assert any(p.startswith("duplicate:") for p in rep["problems"]), rep["problems"]


def case_unassigned_movie_output(tmp: Path) -> None:
    """Output for a movie in no shard is caught, not quietly staged."""
    star = tmp / "movies.star"
    build_star(star, DEFAULT_ROWS)
    shards = tmp / "shards"
    assert partition(star, 2, shards).returncode == 0
    dirs, codes = run_workers(tmp, shards, 2,
                              per_worker={0: ["--fake_extra", "Movies/ghost.tiff"]})
    status = fake_status(tmp, codes)
    report = tmp / "report.json"
    cp = merge(shards / "shard_manifest.json", dirs, tmp / "merged", status, report)
    assert cp.returncode == 3, f"unassigned output not caught (rc={cp.returncode})"
    rep = json.loads(report.read_text())
    assert any("belongs to no movie" in p for p in rep["problems"]), rep["problems"]


def case_failed_worker_blocks_merge(tmp: Path) -> None:
    """A non-zero worker exit blocks the merge even when every file is present."""
    star = tmp / "movies.star"
    build_star(star, DEFAULT_ROWS)
    shards = tmp / "shards"
    assert partition(star, 2, shards).returncode == 0
    dirs, codes = run_workers(tmp, shards, 2, per_worker={1: ["--fake_fail_rc", "4"]})
    assert codes == [0, 4], codes
    status = fake_status(tmp, codes)
    report = tmp / "report.json"
    cp = merge(shards / "shard_manifest.json", dirs, tmp / "merged", status, report)
    assert cp.returncode == 3, "failed worker was merged"
    rep = json.loads(report.read_text())
    assert any("exited 4" in p for p in rep["problems"]), rep["problems"]


def case_missing_status_blocks_merge(tmp: Path) -> None:
    """Merging without recorded exit codes is refused, not assumed clean."""
    star = tmp / "movies.star"
    build_star(star, DEFAULT_ROWS)
    shards = tmp / "shards"
    assert partition(star, 2, shards).returncode == 0
    dirs, _ = run_workers(tmp, shards, 2)
    report = tmp / "report.json"
    cp = merge(shards / "shard_manifest.json", dirs, tmp / "merged", None, report)
    assert cp.returncode == 3, "merge proceeded with no exit codes checked"
    rep = json.loads(report.read_text())
    assert any("no --status" in p for p in rep["problems"]), rep["problems"]


def case_killed_worker_then_nonprefix_resume(tmp: Path) -> None:
    """A SIGKILLed worker fails the merge; resuming it completes a non-prefix gap."""
    star = tmp / "movies.star"
    build_star(star, DEFAULT_ROWS)
    shards = tmp / "shards"
    assert partition(star, 3, shards).returncode == 0
    man = json.loads((shards / "shard_manifest.json").read_text())
    canonical = man["canonical_movies"]

    dirs, codes = run_workers(tmp, shards, 3,
                              per_worker={1: ["--fake_die_after", "1"]})
    assert codes[1] != 0, f"worker 1 was expected to die, exited {codes[1]}"
    assert codes[0] == 0 and codes[2] == 0, codes

    status = fake_status(tmp, codes)
    cp = merge(shards / "shard_manifest.json", dirs, tmp / "merged_partial", status,
               tmp / "partial.json")
    assert cp.returncode == 3, "a killed worker's run was merged"
    partial = json.loads((tmp / "partial.json").read_text())
    assert any("exited" in p for p in partial["problems"]), partial["problems"]

    # The completed set must genuinely not be a prefix of canonical order, or
    # this exercises the easy case only.
    completed = [m for m in canonical
                 if any((d / (star_io.output_root(m) + ".mrc")).exists() for d in dirs)]
    assert completed != canonical[: len(completed)], (
        "the interrupted run happened to complete a prefix; the resume case would "
        f"not be exercised. completed={completed}")
    assert len(completed) < len(canonical)

    # Resume only the worker that died, against its own partial directory.
    dirs2, codes2 = run_workers(tmp, shards, 3, resume={0, 1, 2})
    assert codes2 == [0, 0, 0], codes2
    status2 = fake_status(tmp, codes2)
    report2 = tmp / "resumed.json"
    cp = merge(shards / "shard_manifest.json", dirs2, tmp / "merged_resumed", status2,
               report2)
    assert cp.returncode == 0, cp.stderr
    rep = json.loads(report2.read_text())
    assert rep["verdict"] == "PASS", rep["problems"]

    # Resume must not have altered what was already correct.
    for name, optics, pre in DEFAULT_ROWS:
        root = star_io.output_root(name)
        payload = json.loads((tmp / "merged_resumed" / (root + ".star")).read_text())
        assert payload["rlnMicrographMovieName"] == name
        assert payload["rlnOpticsGroup"] == str(optics)


def case_star_parser_refusals(tmp: Path) -> None:
    """Constructs the C++ reader mishandles are refused rather than guessed at."""
    star = tmp / "movies.star"

    build_star(star, DEFAULT_ROWS)
    good = star.read_text()

    star.write_bytes(good.replace("\n", "\r\n").encode())
    cp = partition(star, 2, tmp / "s_crlf")
    assert cp.returncode != 0 and "CR+LF" in cp.stderr, cp.stderr

    star.write_text(good.replace("Movies/20170629_00021_frameImage.tiff",
                                 "'Movies/unterminated.tiff"))
    cp = partition(star, 2, tmp / "s_quote")
    assert cp.returncode != 0 and "quoted token" in cp.stderr, cp.stderr

    star.write_text(good.replace("Movies/20170629_00021_frameImage.tiff",
                                 "\"Movies/a\a\".tiff\""))
    cp = partition(star, 2, tmp / "s_bel")
    assert cp.returncode != 0 and "\\a escape" in cp.stderr, cp.stderr

    star.write_text(good + "; multiline\n")
    cp = partition(star, 2, tmp / "s_semi")
    assert cp.returncode != 0 and "semicolon" in cp.stderr, cp.stderr

    star.write_text(good)
    assert partition(star, 2, tmp / "s_ok").returncode == 0


def case_collapsed_spaces_are_a_collision(tmp: Path) -> None:
    """simplify() collapses runs of spaces inside quotes, so two names alias."""
    assert star_io.tokenize(star_io.simplify("'a  b.tif' 1 0.0"))[0] == "a b.tif"
    rows = [("Movies/a b.tiff", 1, 0.0), ("Movies/a  b.tiff", 1, 1.4),
            ("Movies/c.tiff", 1, 2.8)]
    star = tmp / "movies.star"
    build_star(star, rows)
    cp = partition(star, 2, tmp / "shards")
    assert cp.returncode == 3, (
        "two names the C++ reader cannot tell apart were accepted "
        f"(rc={cp.returncode})")
    assert "duplicate movie in input" in cp.stderr, cp.stderr


def case_launcher_refuses_cpu_gpu_confusion(tmp: Path) -> None:
    """A CPU run cannot be filed as a GPU run by omitting --devices."""
    star = tmp / "movies.star"
    build_star(star, DEFAULT_ROWS)
    cp = run([PY, TOOLS / "run_multi_gpu.py", "--star", star, "--out", tmp / "run1",
              "--binary", FAKE, "--workers", "2"])
    assert cp.returncode == 2 and "--no-witness" in cp.stderr, cp.stderr

    cp = run([PY, TOOLS / "run_multi_gpu.py", "--star", star, "--out", tmp / "run2",
              "--binary", FAKE, "--workers", "2", "--no-witness"])
    # Check the launcher wired up shards, per-worker dirs, and a status file
    # carrying both exit codes.
    status = json.loads((tmp / "run2" / "status.json").read_text())
    assert status["n_workers"] == 2, status
    assert [w["returncode"] for w in status["workers"]] == [0, 0], status
    assert status["devices"] is None
    assert "no throughput claim" in status["wall_seconds_note"]
    assert cp.returncode == 0, cp.stderr

    cp = run([PY, TOOLS / "run_multi_gpu.py", "--star", star, "--out", tmp / "run2",
              "--binary", FAKE, "--workers", "2", "--no-witness"])
    assert cp.returncode == 2 and "refusing to reuse" in cp.stderr, cp.stderr


def case_gpu_witness_logic(tmp: Path) -> None:
    """The device witness fails closed on aliased, unobserved and shared devices."""
    sys.path.insert(0, str(TOOLS))
    import gpu_witness

    devices = [
        {"smi_index": "0", "uuid": "GPU-aaaa", "name": "A", "memory_total": "1"},
        {"smi_index": "1", "uuid": "GPU-bbbb", "name": "B", "memory_total": "1"},
    ]
    chosen = gpu_witness.select(["0", "GPU-bbbb"], devices)
    assert [c["uuid"] for c in chosen] == ["GPU-aaaa", "GPU-bbbb"]
    try:
        gpu_witness.select(["0", "GPU-aaaa"], devices)
        raise AssertionError("two selectors for one physical device were accepted")
    except gpu_witness.WitnessError as exc:
        assert "one GPU, not two" in str(exc)

    env = gpu_witness.worker_env(devices[1], {"PATH": "/x"})
    assert env["CUDA_VISIBLE_DEVICES"] == "GPU-bbbb"

    expected = {11: "GPU-aaaa", 22: "GPU-bbbb"}
    ok = gpu_witness.check_observations(expected, [
        {"pid": "11", "gpu_uuid": "GPU-aaaa", "used_gpu_memory": "1 MiB"},
        {"pid": "22", "gpu_uuid": "GPU-bbbb", "used_gpu_memory": "1 MiB"},
    ])
    assert ok["all_pids_witnessed_on_intended_distinct_devices"] is True
    assert ok["distinct_devices_witnessed"] == 2

    # never observed -> unwitnessed, not a pass
    bad = gpu_witness.check_observations(expected, [
        {"pid": "11", "gpu_uuid": "GPU-aaaa", "used_gpu_memory": "1 MiB"}])
    assert bad["unwitnessed_pids"] == [22]
    assert bad["all_pids_witnessed_on_intended_distinct_devices"] is False

    # both workers actually on one device -> caught
    shared = gpu_witness.check_observations(expected, [
        {"pid": "11", "gpu_uuid": "GPU-aaaa", "used_gpu_memory": "1 MiB"},
        {"pid": "22", "gpu_uuid": "GPU-aaaa", "used_gpu_memory": "1 MiB"}])
    assert shared["shared_devices"], shared
    assert shared["wrong_device"], shared
    assert shared["all_pids_witnessed_on_intended_distinct_devices"] is False
    assert shared["distinct_devices_witnessed"] == 1


def case_device_list_rejected(tmp: Path, binary: str) -> None:
    """--use_own rejects a device list instead of silently using the first entry."""
    missing = tmp / "no_such_input.star"
    for spec, needle in (("0:1:2:3", "4 device entries"),
                         ("0,1", "2 device entries"),
                         ("0:1", "2 device entries"),
                         ("0abc", "not a non-negative device id"),
                         ("-1", "not a non-negative device id")):
        cp = run([binary, "--i", missing, "--o", tmp / "out", "--use_own",
                  "--gpu", spec])
        assert cp.returncode != 0, f"--gpu {spec} was accepted"
        combined = cp.stdout + cp.stderr
        assert needle in combined, f"--gpu {spec}: {combined[:400]}"
        assert spec in combined, f"--gpu {spec} not quoted back: {combined[:400]}"

    # A single valid id must not hit either new error, and must reach the check
    # that comes next. Asserting only the ABSENCE of the two strings would pass
    # for any failure mode at all -- including the binary crashing before it
    # parsed --gpu -- so the positive half decides this.
    cp = run([binary, "--i", missing, "--o", tmp / "out", "--use_own", "--gpu", "0"])
    combined = cp.stdout + cp.stderr
    assert "device entries" not in combined, combined[:400]
    assert "not a non-negative" not in combined, combined[:400]
    assert cp.returncode != 0, "--gpu 0 with a missing input must still fail"
    # On a CPU-only build the next check is the missing-CUDA error. On a CUDA
    # build the device id is accepted and the run proceeds to the input, which
    # does not exist. Exactly one of the two must be what happened.
    cpu_only = "built without CUDA support" in combined
    cuda_build = ("Using CUDA acceleration on GPU device 0" in combined
                  or "Invalid GPU device ID" in combined
                  or "no_such_input.star" in combined)
    assert cpu_only or cuda_build, \
        f"--gpu 0 failed for an unrecognised reason: {combined[:400]}"


def case_aggregate_star_canonical_order(tmp: Path) -> None:
    """The regenerated dataset STAR must be in canonical input order."""
    star = tmp / "movies.star"
    build_star(star, DEFAULT_ROWS)
    shards = tmp / "shards"
    assert partition(star, 3, shards).returncode == 0
    dirs, codes = run_workers(tmp, shards, 3)
    status = fake_status(tmp, codes)
    report = tmp / "report.json"
    cp = merge(shards / "shard_manifest.json", dirs, tmp / "merged", status, report,
               extra=["--aggregate-with", str(FAKE), "--input-star", str(star),
                      "--aggregate-args=--only_do_unfinished "
                      "--fake_note=args-were-forwarded"])
    assert cp.returncode == 0, cp.stderr + cp.stdout
    rep = json.loads(report.read_text())
    assert rep["verdict"] == "PASS", rep["problems"]
    agg = rep["aggregate_star"]
    assert agg["returncode"] == 0, agg
    assert agg["n_rows"] == len(DEFAULT_ROWS), agg
    assert agg["row_order"] == "canonical", agg
    # The extra arguments really reached the process. Asserting on the recorded
    # command alone would be vacuous -- --only_do_unfinished is added
    # unconditionally -- so this checks a side effect only a forwarded argument
    # could produce. argparse.REMAINDER after a named option silently captures
    # nothing, which is the failure this case exists to catch.
    note = tmp / "merged" / "note.txt"
    assert note.exists() and note.read_text().strip() == "args-were-forwarded", \
        f"extra aggregate arguments were dropped; command was {agg['command']}"

    merged_star = (tmp / "merged" / "corrected_micrographs.star").read_text()
    for name, _, _ in DEFAULT_ROWS:
        assert star_io.output_root(name) + ".mrc" in merged_star, name


def case_aggregate_wrong_order_rejected(tmp: Path) -> None:
    """An aggregate STAR in completion order rather than input order fails."""
    star = tmp / "movies.star"
    build_star(star, DEFAULT_ROWS)
    shards = tmp / "shards"
    assert partition(star, 3, shards).returncode == 0
    dirs, codes = run_workers(tmp, shards, 3)
    status = fake_status(tmp, codes)
    report = tmp / "report.json"
    cp = merge(shards / "shard_manifest.json", dirs, tmp / "merged", status, report,
               extra=["--aggregate-with", str(FAKE), "--input-star", str(star),
                      "--aggregate-args=--only_do_unfinished "
                      "--fake_reverse_aggregate"])
    assert cp.returncode == 3, f"reversed aggregate order accepted (rc={cp.returncode})"
    rep = json.loads(report.read_text())
    assert any("canonical input order" in p for p in rep["problems"]), rep["problems"]


def case_aggregate_star_must_match_partition_content(tmp: Path) -> None:
    """Same movie rows with edited optics may not source aggregate metadata."""
    star = tmp / "movies.star"
    build_star(star, DEFAULT_ROWS)
    shards = tmp / "shards"
    assert partition(star, 2, shards).returncode == 0
    manifest = json.loads((shards / "shard_manifest.json").read_text())
    original_sha = manifest["input_sha256"]
    dirs, codes = run_workers(tmp, shards, 2)

    original = star.read_bytes()
    modified = original.replace(b"0.885000", b"0.886000", 1)
    assert modified != original and len(modified) == len(original)
    old_stat = star.stat()
    star.write_bytes(modified)
    os.utime(star, ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns))
    assert star.stat().st_size == old_stat.st_size
    assert star.stat().st_mtime_ns == old_stat.st_mtime_ns
    assert hashlib.sha256(star.read_bytes()).hexdigest() != original_sha

    out = tmp / "must_not_aggregate"
    report = tmp / "aggregate_identity.json"
    cp = merge(shards / "shard_manifest.json", dirs, out,
               fake_status(tmp, codes, manifest=shards / "shard_manifest.json",
                           workers=dirs), report,
               extra=["--aggregate-with", str(FAKE), "--input-star", str(star),
                      "--aggregate-args=--fake_note=aggregate-ran"])
    assert cp.returncode == 2, \
        f"aggregate accepted a changed same-size/same-mtime STAR (rc={cp.returncode})"
    assert "does not match the partition manifest" in cp.stderr, cp.stderr
    assert not (out / "note.txt").exists(), "aggregate binary ran on unrelated optics"


def case_aggregate_args_may_not_override_owned_paths(tmp: Path) -> None:
    """Extra arguments cannot redirect the verified aggregate input or output."""
    star = tmp / "movies.star"
    build_star(star, DEFAULT_ROWS)
    shards = tmp / "shards"
    assert partition(star, 2, shards).returncode == 0
    dirs, codes = run_workers(tmp, shards, 2)
    status = fake_status(tmp, codes)
    altered = tmp / "changed_optics.star"
    altered.write_bytes(star.read_bytes().replace(b"200.000000", b"201.000000", 1))
    assert altered.read_bytes() != star.read_bytes()
    for name, args in (("input", ["--i", str(altered)]),
                       ("output", ["--o", str(tmp / "redirected")])):
        out = tmp / f"merge_{name}"
        cp = merge(shards / "shard_manifest.json", dirs, out, status,
                   extra=["--aggregate-with", str(FAKE), "--input-star", str(star),
                          "--aggregate-args=" + shlex.join(args)])
        assert cp.returncode == 2, \
            f"aggregate accepted owned {args[0]} override: {cp.returncode}; {cp.stdout}; {cp.stderr}"
        assert args[0] in cp.stderr and "aggregate" in cp.stderr, cp.stderr
        assert not out.exists(), "staging started before argument ownership was checked"
        assert not (tmp / "redirected").exists(), "aggregate wrote outside its staged tree"

    out = tmp / "merge_valid"
    cp = merge(shards / "shard_manifest.json", dirs, out, status,
               extra=["--aggregate-with", str(FAKE), "--input-star", str(star),
                      "--aggregate-args=--fake_note=valid"])
    assert cp.returncode == 0, cp.stderr + cp.stdout
    assert (out / "note.txt").read_text().strip() == "valid"


def case_decorated_output_collision(tmp: Path) -> None:
    """A movie whose root is another movie's decorated output is refused."""
    rows = [("Movies/a.tiff", 1, 0.0), ("Movies/a_PS.tiff", 1, 1.4),
            ("Movies/b.tiff", 1, 2.8)]
    star = tmp / "movies.star"
    build_star(star, rows)
    cp = partition(star, 2, tmp / "shards")
    assert cp.returncode == 3, (
        f"a_PS.mrc is both movie 'a_PS''s image and movie 'a''s power spectrum "
        f"under --grouping_for_ps, yet the pair was accepted (rc={cp.returncode})")
    assert "decorated-output collision" in cp.stderr, cp.stderr
    # positive control: rename the second movie and the same input partitions
    build_star(star, [("Movies/a.tiff", 1, 0.0), ("Movies/aPS.tiff", 1, 1.4),
                      ("Movies/b.tiff", 1, 2.8)])
    assert partition(star, 2, tmp / "shards_ok").returncode == 0


def case_real_output_suffixes_attributed(tmp: Path) -> None:
    """Every suffix the real binary emits is attributed to the right movie."""
    star = tmp / "movies.star"
    build_star(star, DEFAULT_ROWS)
    shards = tmp / "shards"
    assert partition(star, 3, shards).returncode == 0
    dirs, codes = run_workers(tmp, shards, 3)

    man = json.loads((shards / "shard_manifest.json").read_text())
    owners = {r: s["index"] for s in man["shards"]
              for r in s["output_roots"]}
    # The decorations the runner actually writes: _shifts.eps (:950), .log,
    # _noDW/_DW/_DWS/_PS/_EVN/_ODD.mrc, _frames.mrcs. Drop them into the worker
    # that owns each movie, then require a clean merge.
    for root, k in owners.items():
        for extra in ("_shifts.eps", ".log", "_noDW.mrc", "_PS.mrc", "_EVN.mrc",
                      "_ODD.mrc", "_DW.mrc", "_DWS.mrc", "_frames.mrcs"):
            f = dirs[k] / (root + extra)
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text("x")
    # run_multi_gpu.py drops these into each worker directory
    for d in dirs:
        (d / "command.json").write_text("{}")

    status = fake_status(tmp, codes)
    report = tmp / "report.json"
    cp = merge(shards / "shard_manifest.json", dirs, tmp / "merged", status, report)
    assert cp.returncode == 0, cp.stderr
    rep = json.loads(report.read_text())
    assert rep["verdict"] == "PASS", rep["problems"]

    # ...and the same file under the WRONG worker is still caught.
    wrong = dirs[(owners[man["shards"][0]["output_roots"][0]] + 1) % 3] / (
        man["shards"][0]["output_roots"][0] + "_shifts.eps")
    wrong.parent.mkdir(parents=True, exist_ok=True)
    wrong.write_text("x")
    cp = merge(shards / "shard_manifest.json", dirs, tmp / "merged2", status,
               tmp / "report2.json")
    assert cp.returncode == 3, "a misrouted _shifts.eps was accepted"
    rep2 = json.loads((tmp / "report2.json").read_text())
    assert any(p.startswith("misrouted:") for p in rep2["problems"]), rep2["problems"]


def case_failed_device_witness_blocks_merge(tmp: Path) -> None:
    """A failed GPU-distinctness witness is not laundered into a merge PASS."""
    star = tmp / "movies.star"
    build_star(star, DEFAULT_ROWS)
    shards = tmp / "shards"
    assert partition(star, 2, shards).returncode == 0
    dirs, codes = run_workers(tmp, shards, 2)
    assert codes == [0, 0], codes
    # Every worker exited cleanly and every file is present. The only thing
    # wrong is that both were observed on one physical GPU.
    status = fake_status(tmp, codes, verdict="FAIL", witness={
        "unwitnessed_pids": [],
        "wrong_device": [{"pid": 2, "expected": "GPU-bbbb", "observed": ["GPU-aaaa"]}],
        "shared_devices": [{"gpu_uuid": "GPU-aaaa", "pids": [1, 2]}],
        "distinct_devices_witnessed": 1,
        "all_pids_witnessed_on_intended_distinct_devices": False,
    })
    report = tmp / "report.json"
    cp = merge(shards / "shard_manifest.json", dirs, tmp / "merged", status, report)
    assert cp.returncode == 3, "a run whose device witness failed was merged as PASS"
    rep = json.loads(report.read_text())
    assert any("launcher verdict is FAIL" in p for p in rep["problems"]), rep["problems"]
    assert any("shared_devices" in p for p in rep["problems"]), rep["problems"]

    # positive control: same files, same exit codes, witness held
    ok = fake_status(tmp, codes, verdict="PASS", name="status_ok.json")
    cp = merge(shards / "shard_manifest.json", dirs, tmp / "merged_ok", ok,
               tmp / "report_ok.json")
    assert cp.returncode == 0, cp.stderr


def case_link_with_aggregate_refused(tmp: Path) -> None:
    """Hardlinking into the merged tree cannot be combined with the aggregate step."""
    star = tmp / "movies.star"
    build_star(star, DEFAULT_ROWS)
    shards = tmp / "shards"
    assert partition(star, 2, shards).returncode == 0
    dirs, codes = run_workers(tmp, shards, 2)
    status = fake_status(tmp, codes)
    cp = merge(shards / "shard_manifest.json", dirs, tmp / "merged", status,
               extra=["--link", "--aggregate-with", str(FAKE),
                      "--input-star", str(star)])
    assert cp.returncode == 2, f"--link + --aggregate-with accepted (rc={cp.returncode})"
    assert "shared inode" in cp.stderr, cp.stderr
    # --link alone is fine
    cp = merge(shards / "shard_manifest.json", dirs, tmp / "merged_link", status,
               extra=["--link"])
    assert cp.returncode == 0, cp.stderr


def case_missing_worker_directory(tmp: Path) -> None:
    """A worker directory that does not exist fails the merge."""
    star = tmp / "movies.star"
    build_star(star, DEFAULT_ROWS)
    shards = tmp / "shards"
    assert partition(star, 2, shards).returncode == 0
    dirs, codes = run_workers(tmp, shards, 2)
    # The status must describe the directories actually merged, or the merge
    # rejects it for that instead and this case would never reach the
    # missing-directory check it exists to exercise.
    status = fake_status(tmp, codes, workers=[dirs[0], tmp / "no_such_worker"])
    report = tmp / "report.json"
    cp = merge(shards / "shard_manifest.json", [dirs[0], tmp / "no_such_worker"],
               tmp / "merged", status, report)
    assert cp.returncode == 3, "a missing worker directory was merged"
    rep = json.loads(report.read_text())
    assert any("is not a directory" in p for p in rep["problems"]), rep["problems"]
    assert any(p.startswith("lost:") for p in rep["problems"]), rep["problems"]


def case_output_root_matches_withoutextension(tmp: Path) -> None:
    """output_root reproduces FileName::withoutExtension, dots in directories included."""
    # src/filename.cpp:272-276 is substr(0, rfind(".")) over the whole path.
    assert star_io.output_root("Movies/run.1/mov") == "Movies/run"
    assert star_io.output_root("Movies/a.tif") == "Movies/a"
    assert star_io.output_root("Movies/set.1/a.tif") == "Movies/set_1/a"
    assert star_io.output_root("Movies/plain") == "Movies/plain"
    # Two movies the binary would write to one file are therefore caught.
    rows = [("Movies/run.1/mov", 1, 0.0), ("Movies/run.2/other", 1, 1.4),
            ("Movies/c.tiff", 1, 2.8)]
    star = tmp / "movies.star"
    build_star(star, rows)
    cp = partition(star, 2, tmp / "shards")
    assert cp.returncode == 3, f"both write Movies/run.mrc (rc={cp.returncode})"
    assert "output-name collision" in cp.stderr, cp.stderr


def case_reserved_name_collision(tmp: Path) -> None:
    """A movie whose output collides with a fixed-name per-run artifact is refused."""
    for movie, needle in ((f"gain.tiff", "gain"),
                          ("corrected_micrographs.tiff", "corrected_micrographs")):
        star = tmp / "movies.star"
        build_star(star, [(movie, 1, 0.0), ("Movies/b.tiff", 1, 1.4)])
        cp = partition(star, 2, tmp / ("s_" + needle))
        assert cp.returncode == 3, f"{movie} accepted (rc={cp.returncode})"
        assert "reserved-name collision" in cp.stderr, cp.stderr
    build_star(tmp / "movies.star", [("Movies/gain.tiff", 1, 0.0),
                                     ("Movies/b.tiff", 1, 1.4)])
    assert partition(tmp / "movies.star", 2, tmp / "s_ok").returncode == 0


def case_short_row_refused(tmp: Path) -> None:
    """A row with fewer values than labels is refused, not silently shortened."""
    star = tmp / "movies.star"
    build_star(star, DEFAULT_ROWS)
    text = star.read_text()
    text = text.replace("Movies/20170629_00021_frameImage.tiff 1 0.000000",
                        "Movies/20170629_00021_frameImage.tiff 1")
    star.write_text(text)
    cp = partition(star, 2, tmp / "shards")
    assert cp.returncode != 0, "a short row was accepted"
    assert "fewer columns" in cp.stderr, cp.stderr
    # The two-label shape the C++ reader sometimes tolerates is refused too,
    # with the reason stated, rather than guessed at.
    star.write_text("""
data_movies

loop_
_rlnMicrographMovieName #1
_rlnOpticsGroup #2
Movies/a.tiff
Movies/b.tiff 1

""".lstrip("\n"))
    cp = partition(star, 1, tmp / "shards2")
    assert cp.returncode != 0, "the legacy two-column shape was accepted"
    assert "does not carry the EMDL type table" in cp.stderr, cp.stderr


def case_aggregate_name_shadowing(tmp: Path) -> None:
    """A per-movie output whose basename matches an aggregate is still a movie."""
    # Movies/gain.tiff writes Movies/gain.mrc. Matching the fixed-name artifact
    # list by basename alone would divert it into the per-worker stash and drop
    # it from the merged tree.
    rows = [("Movies/gain.tiff", 1, 0.0), ("Movies/run.tiff", 1, 1.4),
            ("Movies/logfile.tiff", 2, 2.8), ("Movies/ok.tiff", 2, 4.2)]
    star = tmp / "movies.star"
    build_star(star, rows)
    shards = tmp / "shards"
    assert partition(star, 2, shards).returncode == 0, "top-level names are fine " \
        "under Movies/; only the output root itself is reserved"
    dirs, codes = run_workers(tmp, shards, 2)
    status = fake_status(tmp, codes)
    report = tmp / "report.json"
    cp = merge(shards / "shard_manifest.json", dirs, tmp / "merged", status, report)
    assert cp.returncode == 0, cp.stderr
    rep = json.loads(report.read_text())
    assert rep["verdict"] == "PASS", rep["problems"]
    for name, _, _ in rows:
        root = star_io.output_root(name)
        assert (tmp / "merged" / (root + ".mrc")).exists(), \
            f"{root}.mrc was diverted instead of staged"
        assert not (tmp / "merged" / "_workers" / "w0" / (root + ".mrc")).exists()
        assert not (tmp / "merged" / "_workers" / "w1" / (root + ".mrc")).exists()


def case_per_worker_cpu_masks(tmp: Path) -> None:
    """Workers can be pinned to disjoint CPU masks, and a bad count is refused."""
    star = tmp / "movies.star"
    build_star(star, DEFAULT_ROWS)

    cp = run([PY, TOOLS / "run_multi_gpu.py", "--star", star, "--out", tmp / "r_bad",
              "--binary", FAKE, "--workers", "2", "--no-witness",
              "--cpus", "0-1;2-3;4-5"])
    assert cp.returncode == 2 and "3 masks for 2 worker" in cp.stderr, cp.stderr

    if shutil.which("taskset") is None:
        # macOS has no taskset. The launcher must refuse rather than run
        # unpinned, which would silently break a shared-host core budget.
        cp = run([PY, TOOLS / "run_multi_gpu.py", "--star", star,
                  "--out", tmp / "r_no_taskset", "--binary", FAKE, "--workers", "2",
                  "--no-witness", "--cpus", "0-1;2-3"])
        assert cp.returncode == 2 and "needs taskset" in cp.stderr, cp.stderr
        print("      (taskset absent: pinning asserted only as a refusal here; the "
              "launch path is exercised on the Linux validation host)")
        return

    cp = run([PY, TOOLS / "run_multi_gpu.py", "--star", star, "--out", tmp / "r_per",
              "--binary", FAKE, "--workers", "2", "--no-witness",
              "--cpus", "0-1;2-3"])
    assert cp.returncode == 0, cp.stderr
    status = json.loads((tmp / "r_per" / "status.json").read_text())
    assert status["cpu_masks"] == ["0-1", "2-3"], status["cpu_masks"]
    for k, mask in enumerate(["0-1", "2-3"]):
        cmd = json.loads((tmp / "r_per" / f"w{k}" / "command.json").read_text())
        assert cmd["cpu_mask"] == mask, cmd
        assert cmd["command"][:3] == ["taskset", "-c", mask], cmd["command"]

    # a single mask still applies to every worker
    cp = run([PY, TOOLS / "run_multi_gpu.py", "--star", star, "--out", tmp / "r_one",
              "--binary", FAKE, "--workers", "2", "--no-witness", "--cpus", "0-3"])
    assert cp.returncode == 0, cp.stderr
    assert json.loads((tmp / "r_one" / "status.json").read_text())["cpu_masks"] == \
        ["0-3", "0-3"]


def case_sampler_lifecycle(tmp: Path) -> None:
    """The device sampler can be started, stopped and joined without raising.

    threading.Thread defines a private _stop(), and join() calls it through
    _wait_for_tstate_lock() once the thread has finished. An Event attribute
    named _stop shadows it, so every join() after the workers ran raised
    "'Event' object is not callable" -- aborting the launcher *after* the whole
    dataset had been processed, and leaving no status.json. No CPU case reached
    this path, because the sampler only runs when --devices is given.
    """
    sys.path.insert(0, str(TOOLS))
    import gpu_witness
    import run_multi_gpu

    calls = {"n": 0}

    def fake_compute_apps():
        calls["n"] += 1
        return [{"pid": "1", "gpu_uuid": "GPU-aaaa", "used_gpu_memory": "1 MiB"}]

    # Assert the invariant directly, not only through join(). CPython 3.12's
    # _wait_for_tstate_lock() calls self._stop(); 3.14's does not, so exercising
    # join() alone catches this on the validation host and silently misses it on
    # a newer interpreter.
    import inspect as _inspect
    import threading as _threading
    threads = [c for _, c in _inspect.getmembers(run_multi_gpu, _inspect.isclass)
               if issubclass(c, _threading.Thread) and c is not _threading.Thread
               and c.__module__ == run_multi_gpu.__name__]
    assert threads, "no Thread subclass found in run_multi_gpu"
    for cls in threads:
        probe = cls(0.01)
        assert not isinstance(getattr(probe, "_stop", None), _threading.Event), (
            f"{cls.__name__} shadows threading.Thread._stop with an Event; join() "
            "raises \"'Event' object is not callable\" on CPython 3.12")
    # Every Thread subclass in the module, not just the one that had the bug: a
    # later sampler would otherwise reintroduce it uncovered. Asserted
    # structurally rather than through join(), because CPython 3.12's
    # _wait_for_tstate_lock() calls self._stop() and 3.13's does not -- so
    # exercising join() alone catches this on the validation host and silently
    # misses it on a newer interpreter. Absent is fine; an Event in its place is
    # the defect, on every version.

    real = gpu_witness.compute_apps
    gpu_witness.compute_apps = fake_compute_apps
    try:
        s = run_multi_gpu.Sampler(0.01)
        s.start()
        deadline = time.time() + 5
        while calls["n"] < 2 and time.time() < deadline:
            time.sleep(0.01)
        s.stop()
        s.join(timeout=5)          # the call that used to raise
        assert not s.is_alive(), "sampler did not stop"
        assert calls["n"] >= 2, f"sampler only polled {calls['n']} time(s)"
        assert s.errors == [], s.errors
        obs = s.observations()
        assert obs and obs[0]["gpu_uuid"] == "GPU-aaaa", obs
        # joining a second time, and after the thread is long dead, must also work
        s.join(timeout=5)
    finally:
        gpu_witness.compute_apps = real

    # a sampler whose backend fails records the error and stops, rather than
    # leaving the launcher to treat an empty sample set as a clean witness
    def boom():
        raise gpu_witness.WitnessError("nvidia-smi exploded")

    gpu_witness.compute_apps = boom
    try:
        s2 = run_multi_gpu.Sampler(0.01)
        s2.start()
        s2.join(timeout=5)
        assert not s2.is_alive()
        assert s2.errors and "exploded" in s2.errors[0], s2.errors
        assert s2.observations() == []
    finally:
        gpu_witness.compute_apps = real


STUB_COMPARATOR = """#!/usr/bin/env python3
# Minimal stand-in for tools/compare_motioncorr.py. Emits a FAIL report for any
# movie whose reference MRC contains the token FAILME, a PASS report otherwise.
import argparse, json, pathlib, sys
ap = argparse.ArgumentParser()
for f in ("--ref-mrc", "--test-mrc", "--ref-star", "--test-star", "--gate", "--json-out"):
    ap.add_argument(f)
a = ap.parse_args()
bad = "FAILME" in pathlib.Path(a.ref_mrc).read_text()
ok = not bad
report = {
    "overall_status": "PASS" if ok else "FAIL",
    "coverage": {"complete": True},
    "checks": {
        "corrected_image": {"pixel_identical": ok, "image_rmse": 0.0, "passed": ok},
        "motion_trajectory": {"max_shift_error": 0.0, "passed": ok},
        "star_fields": {"difference_count": 0, "passed": ok},
    },
}
pathlib.Path(a.json_out).write_text(json.dumps(report))
sys.exit(0 if ok else 1)
"""


def _tree(base: Path, roots: list[str], failing: set[str]) -> None:
    for r in roots:
        for suffix in (".mrc", ".star"):
            f = base / (r + suffix)
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text("FAILME" if (r in failing and suffix == ".mrc") else "ok")


def case_compare24_report_identity(tmp: Path) -> None:
    """Reports are keyed by the complete root, so shared basenames cannot alias.

    Movies/set1/a and Movies/set2/a both end in 'a'. Keying reports on the
    basename makes the second comparison overwrite the first, and a later
    --reuse then reads one movie's report for both entries -- turning a genuine
    fail-then-pass pair into a false 2/2 exact PASS.
    """
    tool = tmp / "stub_compare.py"
    tool.write_text(STUB_COMPARATOR)
    roots = ["Movies/set1/a", "Movies/set2/a"]
    manifest = tmp / "manifest.json"
    manifest.write_text(json.dumps({"canonical_output_roots": roots,
                                    "canonical_movies": [r + ".tiff" for r in roots]}))
    ref, test = tmp / "ref", tmp / "test"
    # set1/a fails, set2/a passes -- ordered so a basename collision would let
    # the passing report stand in for the failing one.
    _tree(ref, roots, failing={"Movies/set1/a"})
    _tree(test, roots, failing=set())

    def run24(out: Path, reuse: bool = False):
        cmd = [PY, TOOLS / "compare24.py", "--ref", ref, "--test", test,
               "--tool", tool, "--manifest", manifest, "--out", out]
        if reuse:
            cmd.append("--reuse")
        return run(cmd)

    out = tmp / "exact"
    cp = run24(out)
    assert cp.returncode == 1, f"the failing movie was not reported (rc={cp.returncode})"
    summary = json.loads((out / "exact_summary.json").read_text())
    assert summary["verdict"] == "FAIL", summary
    assert summary["passed"] == 1 and summary["failed"] == 1, summary

    reports = sorted(p.name for p in out.glob("*_exact.json"))
    assert len(reports) == 2, f"two movies produced {len(reports)} report(s): {reports}"
    assert len(set(reports)) == 2, reports
    for r in reports:
        assert "set1" in r or "set2" in r, f"report name loses the directory: {r}"

    # --reuse must reach the same verdict, not launder the fail into a pass
    cp = run24(out, reuse=True)
    assert cp.returncode == 1, f"--reuse turned a FAIL into rc={cp.returncode}"
    summary = json.loads((out / "exact_summary.json").read_text())
    assert summary["verdict"] == "FAIL", summary
    assert summary["passed"] == 1 and summary["failed"] == 1, summary

    # positive control: with both movies passing, both verdicts are PASS
    _tree(ref, roots, failing=set())
    out2 = tmp / "exact_ok"
    assert run24(out2).returncode == 0
    assert json.loads((out2 / "exact_summary.json").read_text())["verdict"] == "PASS"
    assert run24(out2, reuse=True).returncode == 0


def case_absolute_movie_roots_attributed(tmp: Path) -> None:
    """Absolute movie names are matched where the runner actually writes them.

    getOutputFileNames is `fn_out + fn_root`, so an absolute name lands at
    <out>//abs/path.mrc, i.e. worker-relative `abs/path.mrc`. Matching against
    the unnormalized absolute root attributes nothing and reports every product
    lost even though the runner wrote it.
    """
    assert star_io.worker_relative_root(star_io.output_root("/data/Movies/a.tiff")) \
        == "data/Movies/a"

    rows = [("/data/Movies/m1.tiff", 1, 0.0), ("/data/Movies/m2.tiff", 2, 1.4),
            ("/data/Movies/m3.tiff", 1, 2.8), ("/data/Movies/m4.tiff", 2, 4.2)]
    star = tmp / "movies.star"
    build_star(star, rows)
    shards = tmp / "shards"
    assert partition(star, 2, shards).returncode == 0, "absolute names were refused"

    man = json.loads((shards / "shard_manifest.json").read_text())
    dirs = []
    for k, s in enumerate(man["shards"]):
        wdir = tmp / f"w{k}"
        dirs.append(wdir)
        for movie in s["movies"]:
            rel = star_io.worker_relative_root(star_io.output_root(movie))
            for suffix in (".mrc", ".star", "_shifts.eps"):
                f = wdir / (rel + suffix)
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text("x")
    status = fake_status(tmp, [0, 0])
    report = tmp / "report.json"
    cp = merge(shards / "shard_manifest.json", dirs, tmp / "merged", status, report)
    assert cp.returncode == 0, cp.stderr
    rep = json.loads(report.read_text())
    assert rep["verdict"] == "PASS", rep["problems"]
    assert rep["n_files_staged"] == 12, rep
    for movie, _, _ in rows:
        rel = star_io.worker_relative_root(star_io.output_root(movie))
        assert (tmp / "merged" / (rel + ".mrc")).exists(), rel

    # completeness still fails closed when one absolute-rooted movie is absent
    (dirs[0] / (star_io.worker_relative_root(
        star_io.output_root(man["shards"][0]["movies"][0])) + ".mrc")).unlink()
    cp = merge(shards / "shard_manifest.json", dirs, tmp / "merged2", status,
               tmp / "report2.json")
    assert cp.returncode == 3, "a missing absolute-rooted product was not reported lost"
    rep2 = json.loads((tmp / "report2.json").read_text())
    assert any(p.startswith("lost:") for p in rep2["problems"]), rep2["problems"]


def case_devices_with_no_witness_refused(tmp: Path) -> None:
    """A real GPU launch cannot opt out of the device witness and still PASS."""
    star = tmp / "movies.star"
    build_star(star, DEFAULT_ROWS)
    cp = run([PY, TOOLS / "run_multi_gpu.py", "--star", star, "--out", tmp / "r",
              "--binary", FAKE, "--devices", "0,1", "--no-witness"])
    assert cp.returncode == 2, f"--devices with --no-witness accepted (rc={cp.returncode})"
    assert "certifying a device claim nothing" in cp.stderr, cp.stderr
    # The rejection must happen before any device is selected, so it also holds
    # on a host with no GPU at all.
    assert "nvidia-smi" not in cp.stderr, cp.stderr


def case_failed_staging_never_reprocesses(tmp: Path) -> None:
    """A failed merge must not hand an incomplete tree to --only_do_unfinished.

    PR55's shell merge resolved its destination relative to each worker
    directory it had cd'd into, so the copies failed while `find` still exited
    zero; the following --only_do_unfinished pass then saw an empty tree and
    silently reprocessed the entire collection, presenting a from-scratch rerun
    as a merge of the worker results. Nothing here chdirs, but the guarantee
    that matters is that the aggregate step cannot run at all once staging has
    failed -- so it is asserted rather than assumed.
    """
    star = tmp / "movies.star"
    build_star(star, DEFAULT_ROWS)
    shards = tmp / "shards"
    assert partition(star, 2, shards).returncode == 0
    lost = DEFAULT_ROWS[0][0]
    dirs, codes = run_workers(tmp, shards, 2, per_worker={0: ["--fake_skip", lost]})
    status = fake_status(tmp, codes)
    report = tmp / "report.json"
    cp = merge(shards / "shard_manifest.json", dirs, tmp / "merged", status, report,
               extra=["--aggregate-with", str(FAKE), "--input-star", str(star),
                      "--aggregate-args=--fake_note=aggregate-should-not-have-run"])
    assert cp.returncode == 3, f"incomplete staging was merged (rc={cp.returncode})"
    rep = json.loads(report.read_text())
    assert rep["aggregate_star"] == "not attempted: staging failed", rep["aggregate_star"]
    assert any(p.startswith("lost:") for p in rep["problems"]), rep["problems"]
    assert not (tmp / "merged" / "note.txt").exists(), \
        "the aggregate binary ran despite staging having failed"
    assert not (tmp / "merged" / "corrected_micrographs.star").exists(), \
        "an aggregate STAR was published from an incomplete tree"

    # positive control: with the movie present, the aggregate does run
    dirs2, codes2 = run_workers(tmp, shards, 2)
    cp = merge(shards / "shard_manifest.json", dirs2, tmp / "merged_ok",
               fake_status(tmp, codes2, name="status_ok.json"), tmp / "report_ok.json",
               extra=["--aggregate-with", str(FAKE), "--input-star", str(star),
                      "--aggregate-args=--fake_note=ran"])
    assert cp.returncode == 0, cp.stderr
    assert (tmp / "merged_ok" / "note.txt").read_text().strip() == "ran"


def case_merge_out_is_resolved(tmp: Path) -> None:
    """A relative --out resolves to the caller's cwd, not somewhere else."""
    star = tmp / "movies.star"
    build_star(star, DEFAULT_ROWS)
    shards = tmp / "shards"
    assert partition(star, 2, shards).returncode == 0
    dirs, codes = run_workers(tmp, shards, 2)
    status = fake_status(tmp, codes)
    workdir = tmp / "cwd"
    workdir.mkdir()
    cp = subprocess.run(
        [str(PY), str(TOOLS / "merge_workers.py"),
         "--manifest", str(shards / "shard_manifest.json"),
         "--workers", *[str(d) for d in dirs],
         "--status", str(status), "--out", "relative_merged",
         "--report", str(tmp / "rel_report.json")],
        capture_output=True, text=True, cwd=workdir)
    assert cp.returncode == 0, cp.stderr
    rep = json.loads((tmp / "rel_report.json").read_text())
    assert rep["verdict"] == "PASS", rep["problems"]
    assert Path(rep["merged_into"]).is_absolute(), rep["merged_into"]
    assert (workdir / "relative_merged").is_dir(), "merged tree is not under the cwd"
    for name, _, _ in DEFAULT_ROWS:
        root = star_io.worker_relative_root(star_io.output_root(name))
        assert (workdir / "relative_merged" / (root + ".mrc")).exists(), root


def case_compare24_injective_report_identity(tmp: Path) -> None:
    """Report identity is injective in the complete root, and validated on reuse.

    Substituting separators is not injective: "a/b" and "a__b" both map to
    "a__b". The second comparison overwrites the first report and a later
    --reuse reads one movie's result for both, turning a genuine fail-then-pass
    pair into a false 2/2 PASS. Ordered here so a non-injective encoding would
    launder the failure.
    """
    import compare24
    assert compare24.report_identifier("a/b") != compare24.report_identifier("a__b")

    tool = tmp / "stub_compare.py"
    tool.write_text(STUB_COMPARATOR)
    roots = ["a/b", "a__b"]          # collide under a separator substitution
    manifest = tmp / "manifest.json"
    manifest.write_text(json.dumps({"canonical_output_roots": roots,
                                    "canonical_movies": [r + ".tiff" for r in roots]}))
    ref, test = tmp / "ref", tmp / "test"
    _tree(ref, roots, failing={"a/b"})   # first fails, second passes
    _tree(test, roots, failing=set())

    def run24(out, reuse=False):
        cmd = [PY, TOOLS / "compare24.py", "--ref", ref, "--test", test,
               "--tool", tool, "--manifest", manifest, "--out", out]
        if reuse:
            cmd.append("--reuse")
        return run(cmd)

    out = tmp / "exact"
    cp = run24(out)
    assert cp.returncode == 1, f"the failing movie was not reported (rc={cp.returncode})"
    s = json.loads((out / "exact_summary.json").read_text())
    assert (s["verdict"], s["passed"], s["failed"]) == ("FAIL", 1, 1), s
    reports = sorted(p.name for p in out.glob("*_exact.json"))
    assert len(reports) == 2 and len(set(reports)) == 2, reports

    cp = run24(out, reuse=True)
    assert cp.returncode == 1, f"--reuse laundered the failure (rc={cp.returncode})"
    s = json.loads((out / "exact_summary.json").read_text())
    assert (s["verdict"], s["passed"], s["failed"]) == ("FAIL", 1, 1), s

    # a sidecar naming a different root must be refused, so report identity is
    # validated independently of whatever the filename encoding happens to be
    side = sorted(out.glob("*.origin.json"))[0]
    tampered = json.loads(side.read_text())
    tampered["root"] = "some/other/root"
    side.write_text(json.dumps(tampered))
    cp = run24(out, reuse=True)
    assert cp.returncode == 1, cp.stdout
    s = json.loads((out / "exact_summary.json").read_text())
    assert any("origin mismatch" in (r.get("reason") or "") for r in s["results"]), s
    side.unlink()
    cp = run24(out, reuse=True)
    assert cp.returncode == 1
    s = json.loads((out / "exact_summary.json").read_text())
    assert any("no origin sidecar" in (r.get("reason") or "") for r in s["results"]), s

    # positive control: both passing gives PASS on the normal pass and on reuse
    _tree(ref, roots, failing=set())
    out2 = tmp / "exact_ok"
    assert run24(out2).returncode == 0
    assert run24(out2, reuse=True).returncode == 0


def case_normalized_root_collision_refused(tmp: Path) -> None:
    """'/a/x.tif' and 'a/x.tif' collide once canonicalized, and are refused."""
    assert star_io.worker_relative_root(star_io.output_root("/a/x.tif")) == "a/x"
    assert star_io.worker_relative_root(star_io.output_root("a/x.tif")) == "a/x"

    rows = [("/a/x.tif", 1, 0.0), ("a/x.tif", 1, 1.4), ("Movies/c.tiff", 1, 2.8)]
    star = tmp / "movies.star"
    build_star(star, rows)
    cp = partition(star, 2, tmp / "shards")
    assert cp.returncode == 3, (
        "two movies that both write a/x.* beneath the worker directory were "
        f"accepted (rc={cp.returncode})")
    assert "output-name collision" in cp.stderr, cp.stderr

    # the decoration check must use the same canonical roots
    rows = [("/a/x.tif", 1, 0.0), ("a/x_PS.tif", 1, 1.4), ("Movies/c.tiff", 1, 2.8)]
    build_star(star, rows)
    cp = partition(star, 2, tmp / "shards_dec")
    assert cp.returncode == 3, f"decoration collision missed (rc={cp.returncode})"
    assert "decorated-output collision" in cp.stderr, cp.stderr

    # positive control
    build_star(star, [("/a/x.tif", 1, 0.0), ("b/x.tif", 1, 1.4),
                      ("Movies/c.tiff", 1, 2.8)])
    assert partition(star, 2, tmp / "shards_ok").returncode == 0

    # the manifest must publish the canonical roots the merger will use
    man = json.loads((tmp / "shards_ok" / "shard_manifest.json").read_text())
    assert "a/x" in man["canonical_output_roots"], man["canonical_output_roots"]
    assert not any(r.startswith("/") for r in man["canonical_output_roots"]), man


def case_duplicate_coverage_and_zero_pairs_rejected(tmp: Path) -> None:
    """One product pair may not satisfy two movies, and zero pairs never pass."""
    # merge: a hand-built manifest whose roots collide after normalization
    man = tmp / "dup_manifest.json"
    man.write_text(json.dumps({
        "canonical_movies": ["/a/x.tif", "a/x.tif"],
        "canonical_output_roots": ["a/x", "a/x"],
        "shards": [{"index": 0, "movies": ["/a/x.tif", "a/x.tif"],
                    "output_roots": ["a/x", "a/x"], "n_movies": 2}]}))
    w = tmp / "w0"
    (w / "a").mkdir(parents=True)
    (w / "a" / "x.mrc").write_text("one")
    (w / "a" / "x.star").write_text("one")
    report = tmp / "dup_report.json"
    cp = merge(man, [w], tmp / "merged",
               fake_status(tmp, [0], manifest=man, workers=[w]), report)
    assert cp.returncode == 3, f"one pair satisfied two movies (rc={cp.returncode})"
    rep = json.loads(report.read_text())
    assert any("duplicate coverage" in p for p in rep["problems"]), rep["problems"]

    # merge: an empty manifest is refused rather than trivially passing
    empty = tmp / "empty_manifest.json"
    empty.write_text(json.dumps({"canonical_movies": [], "canonical_output_roots": [],
                                 "shards": []}))
    cp = merge(empty, [w], tmp / "merged_empty",
               fake_status(tmp, [0], name="status_empty.json",
                           manifest=empty, workers=[w]))
    assert cp.returncode == 2 and "nothing to verify" in cp.stderr, cp.stderr

    # compare24: zero pairs is a FAIL, not a vacuous PASS
    tool = tmp / "stub_compare.py"
    tool.write_text(STUB_COMPARATOR)
    cp = run([PY, TOOLS / "compare24.py", "--ref", tmp, "--test", tmp,
              "--tool", tool, "--manifest", empty, "--out", tmp / "z"])
    assert cp.returncode == 2 and "zero-pair" in cp.stderr, cp.stderr

    # compare24: a manifest whose roots collide after normalization is refused
    cp = run([PY, TOOLS / "compare24.py", "--ref", tmp, "--test", tmp,
              "--tool", tool, "--manifest", man, "--out", tmp / "z2"])
    assert cp.returncode == 2 and "not distinct after normalization" in cp.stderr, cp.stderr


def case_reuse_pins_the_trees_not_just_the_root(tmp: Path) -> None:
    """A report may not be reused as the verdict for different inputs.

    Recording only the output root lets a report produced against one pair of
    trees stand in for the same root against completely different trees -- a
    passing run reused to certify inputs it never saw.
    """
    tool = tmp / "stub_compare.py"
    tool.write_text(STUB_COMPARATOR)
    roots = ["Movies/a"]
    manifest = tmp / "manifest.json"
    manifest.write_text(json.dumps({"canonical_output_roots": roots,
                                    "canonical_movies": ["Movies/a.tiff"]}))
    ref, good, bad = tmp / "ref", tmp / "good", tmp / "bad"
    _tree(ref, roots, failing=set())
    _tree(good, roots, failing=set())
    _tree(bad, roots, failing=set())

    def run24(test, out, reuse=False):
        cmd = [PY, TOOLS / "compare24.py", "--ref", ref, "--test", test,
               "--tool", tool, "--manifest", manifest, "--out", out]
        if reuse:
            cmd.append("--reuse")
        return run(cmd)

    out = tmp / "exact"
    assert run24(good, out).returncode == 0, "baseline comparison should pass"

    # same root, different --test tree: the stored report must not be reused
    cp = run24(bad, out, reuse=True)
    assert cp.returncode == 1, "a report was reused across a different test tree"
    s = json.loads((out / "exact_summary.json").read_text())
    assert any("origin mismatch" in (r.get("reason") or "") for r in s["results"]), s

    # same trees but the reference file changed underneath: also refused
    out2 = tmp / "exact2"
    assert run24(good, out2).returncode == 0
    (ref / "Movies" / "a.mrc").write_text("changed after the report was written")
    cp = run24(good, out2, reuse=True)
    assert cp.returncode == 1, "a report was reused after its inputs changed"
    s = json.loads((out2 / "exact_summary.json").read_text())
    assert any("origin mismatch" in (r.get("reason") or "") for r in s["results"]), s

    # Content, not restored metadata, identifies every MRC/STAR input.
    manifest.write_text(json.dumps({"canonical_output_roots": roots,
                                    "canonical_movies": ["Movies/a.tiff"],
                                    "marker": "1"}))
    bound = tmp / "content_bound"
    assert run24(good, bound).returncode == 0
    assert run24(good, bound, reuse=True).returncode == 0, \
        "unchanged content must remain reusable"

    def reject_same_metadata_change(path: Path, replacement: bytes) -> None:
        original = path.read_bytes()
        assert len(replacement) == len(original) and replacement != original
        old_stat = path.stat()
        path.write_bytes(replacement)
        os.utime(path, ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns))
        assert path.stat().st_size == old_stat.st_size
        assert path.stat().st_mtime_ns == old_stat.st_mtime_ns
        cp = run24(good, bound, reuse=True)
        assert cp.returncode == 1, f"same-size/same-mtime edit was reused: {path}"
        path.write_bytes(original)
        os.utime(path, ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns))
        assert run24(good, bound, reuse=True).returncode == 0, \
            f"restoring the original content should restore reuse: {path}"

    for path in (ref / "Movies" / "a.mrc", good / "Movies" / "a.mrc",
                 ref / "Movies" / "a.star", good / "Movies" / "a.star"):
        original = path.read_bytes()
        reject_same_metadata_change(path, b"X" + original[1:])

    # The partition manifest and the comparator JSON report are content-bound too.
    original_manifest = manifest.read_bytes()
    manifest_stat = manifest.stat()
    changed_manifest = original_manifest.replace(b'"marker": "1"', b'"marker": "2"')
    assert len(changed_manifest) == len(original_manifest)
    manifest.write_bytes(changed_manifest)
    os.utime(manifest, ns=(manifest_stat.st_atime_ns, manifest_stat.st_mtime_ns))
    assert run24(good, bound, reuse=True).returncode == 1, \
        "same-size/same-mtime manifest edit was reused"
    manifest.write_bytes(original_manifest)
    os.utime(manifest, ns=(manifest_stat.st_atime_ns, manifest_stat.st_mtime_ns))
    assert run24(good, bound, reuse=True).returncode == 0

    report = next(bound.glob("*_exact.json"))
    report_bytes = report.read_bytes()
    report_stat = report.stat()
    report.write_bytes(report_bytes + b" ")
    os.utime(report, ns=(report_stat.st_atime_ns, report_stat.st_mtime_ns))
    assert run24(good, bound, reuse=True).returncode == 1, \
        "edited report JSON was reused under its unchanged origin sidecar"


def case_interior_double_slash_is_the_same_product(tmp: Path) -> None:
    """'Movies//a' and 'Movies/a' are one file on disk, so they must collide.

    worker_relative_root originally only stripped leading slashes, while every
    consumer hands the value to pathlib, which also collapses interior runs.
    The two domains disagreeing reproduced both review findings through a
    different spelling: preflight passed the pair, the merge's duplicate guard
    compared distinct strings, and compare24 counted one product pair twice.
    """
    assert star_io.worker_relative_root("Movies//a") == "Movies/a"
    assert star_io.worker_relative_root("///a/x") == "a/x"
    assert star_io.worker_relative_root("a/") == "a/", "a trailing slash names a " \
        "different file and must be preserved"

    rows = [("Movies//a.tif", 1, 0.0), ("Movies/a.tif", 1, 1.4),
            ("Movies/c.tiff", 1, 2.8)]
    star = tmp / "movies.star"
    build_star(star, rows)
    cp = partition(star, 2, tmp / "shards")
    assert cp.returncode == 3, f"'Movies//a' and 'Movies/a' accepted (rc={cp.returncode})"
    assert "output-name collision" in cp.stderr, cp.stderr

    # the merge must catch it too, from a manifest it did not produce
    man = tmp / "man.json"
    man.write_text(json.dumps({
        "canonical_movies": ["Movies//a.tif", "Movies/a.tif"],
        "canonical_output_roots": ["Movies/a", "Movies/a"],
        "shards": [{"index": 0, "movies": ["Movies//a.tif"], "n_movies": 1},
                   {"index": 1, "movies": ["Movies/a.tif"], "n_movies": 1}]}))
    w0, w1 = tmp / "w0", tmp / "w1"
    (w0 / "Movies").mkdir(parents=True)
    (w0 / "Movies" / "a.mrc").write_text("one")
    (w0 / "Movies" / "a.star").write_text("one")
    w1.mkdir()
    report = tmp / "rep.json"
    cp = merge(man, [w0, w1], tmp / "merged",
               fake_status(tmp, [0, 0], manifest=man, workers=[w0, w1]), report)
    assert cp.returncode == 3, f"one pair satisfied two movies (rc={cp.returncode})"
    rep = json.loads(report.read_text())
    assert any("duplicate coverage" in p for p in rep["problems"]), rep["problems"]
    # and it must not invent misroutes on top of the true finding
    assert not any(p.startswith("misrouted:") for p in rep["problems"]), \
        f"phantom misroute reported alongside the real duplicate: {rep['problems']}"

    # compare24 must refuse the same manifest rather than counting one pair twice
    tool = tmp / "stub_compare.py"
    tool.write_text(STUB_COMPARATOR)
    cp = run([PY, TOOLS / "compare24.py", "--ref", w0, "--test", w0,
              "--tool", tool, "--manifest", man, "--out", tmp / "z"])
    assert cp.returncode == 2, f"duplicate normalized roots accepted (rc={cp.returncode})"
    assert "not distinct after normalization" in cp.stderr, cp.stderr



def case_stale_status_is_refused(tmp: Path) -> None:
    """A launcher status may only be believed about the run it describes.

    Nothing else in the merge checks that --status belongs to this run, so a
    status left over from -- or copied out of -- a passing run supplies clean
    exit codes for workers that actually failed, and the merge reports PASS
    having never seen the current run's result.
    """
    star = tmp / "movies.star"
    build_star(star, DEFAULT_ROWS)

    # Two runs with genuinely separate trees. run_workers() names its
    # directories w0..wN under the base it is given, so sharing one base
    # would make both runs write the same directories and the "other run"
    # in this case would not be another run at all.
    a_root, b_root = tmp / "A", tmp / "B"
    a_root.mkdir()
    b_root.mkdir()

    # run A: healthy
    shards_a = a_root / "shards"
    assert partition(star, 2, shards_a).returncode == 0
    dirs_a, codes_a = run_workers(a_root, shards_a, 2)
    good = fake_status(a_root, codes_a, name="status_a.json",
                       manifest=shards_a / "shard_manifest.json", workers=dirs_a)

    # positive control: the matching status merges cleanly, so the refusals
    # below cannot be a merge that rejects everything.
    rep_ok = tmp / "report_ok.json"
    assert merge(shards_a / "shard_manifest.json", dirs_a, tmp / "merged_ok",
                 good, rep_ok).returncode == 0
    assert json.loads(rep_ok.read_text())["verdict"] == "PASS"

    # run B: worker 0 exits non-zero. Its own status records that.
    shards_b = b_root / "shards"
    assert partition(star, 2, shards_b).returncode == 0
    dirs_b, codes_b = run_workers(b_root, shards_b, 2,
                                  per_worker={0: ["--fake_fail_rc", "9"]})
    assert codes_b[0] == 9, codes_b
    own = fake_status(b_root, codes_b, verdict="FAIL", name="status_b.json",
                      manifest=shards_b / "shard_manifest.json", workers=dirs_b)
    rep_own = tmp / "report_own.json"
    assert merge(shards_b / "shard_manifest.json", dirs_b, tmp / "merged_own",
                 own, rep_own).returncode == 3, "run B's own status must fail the merge"

    # the hazard: run A's passing status handed to run B's merge
    cp = merge(shards_b / "shard_manifest.json", dirs_b, tmp / "merged_stale", good,
               tmp / "report_stale.json")
    assert cp.returncode == 2, \
        f"a status from another run was accepted (rc={cp.returncode})"
    assert "manifest" in cp.stderr, cp.stderr

    # a status carrying no manifest at all is refused, not skipped
    bare = tmp / "bare.json"
    bare.write_text(json.dumps({"workers": [{"index": k, "returncode": 0}
                                            for k in range(2)], "verdict": "PASS"}))
    cp = merge(shards_b / "shard_manifest.json", dirs_b, tmp / "merged_bare", bare)
    assert cp.returncode == 2 and "records no manifest" in cp.stderr, cp.stderr

    # a status naming this manifest but another run's worker directories
    crossed = fake_status(b_root, [0, 0], name="status_crossed.json",
                          manifest=shards_b / "shard_manifest.json", workers=dirs_a)
    cp = merge(shards_b / "shard_manifest.json", dirs_b, tmp / "merged_crossed", crossed)
    assert cp.returncode == 2 and "worker directory" in cp.stderr, cp.stderr

    # A copy of this manifest at another path: the digest matches and the
    # worker logs are this run's, so the path check is the only thing that can
    # reject it. Without a case like this the digest and worker-log checks would
    # cover for it and its own mutation would survive.
    twin = b_root / "manifest_copy.json"
    twin.write_bytes((shards_b / "shard_manifest.json").read_bytes())
    twinned = fake_status(b_root, [0, 0], name="status_twin.json",
                          manifest=twin, workers=dirs_b)
    cp = merge(shards_b / "shard_manifest.json", dirs_b, tmp / "merged_twin", twinned)
    assert cp.returncode == 2 and "describes manifest" in cp.stderr, cp.stderr

    # a manifest edited after the run is refused by digest
    edited = shards_b / "shard_manifest.json"
    body = json.loads(edited.read_text())
    body["note"] = "tampered"
    edited.write_text(json.dumps(body))
    cp = merge(edited, dirs_b, tmp / "merged_tampered", own)
    assert cp.returncode == 2 and "has changed since" in cp.stderr, cp.stderr


def case_duplicate_movie_name_refused(tmp: Path) -> None:
    """A movie named twice is not a movie processed twice.

    canonical_movies and each shard are keyed by movie name into the owner map,
    so a repeated name collapses to one entry while n_movies_expected still
    counts it twice. One product pair then satisfies both and the merge reports
    PASS on half the coverage. The cross-shard spelling is caught by
    attribution; the same-shard spelling is invisible without an explicit check.
    """
    def one_pair(w: Path) -> None:
        (w / "Movies").mkdir(parents=True, exist_ok=True)
        (w / "Movies" / "a.mrc").write_text("one")
        (w / "Movies" / "a.star").write_text("one")

    # same shard: the spelling that used to pass
    man = tmp / "same_shard.json"
    man.write_text(json.dumps({
        "canonical_movies": ["Movies/a.tif", "Movies/a.tif"],
        "canonical_output_roots": ["Movies/a", "Movies/a"],
        "shards": [{"index": 0, "movies": ["Movies/a.tif", "Movies/a.tif"],
                    "n_movies": 2}]}))
    w = tmp / "w0"
    w.mkdir()
    one_pair(w)
    cp = merge(man, [w], tmp / "merged_same",
               fake_status(tmp, [0], manifest=man, workers=[w]))
    assert cp.returncode == 2, \
        f"one movie satisfied two expected movies (rc={cp.returncode})"
    assert "same movie more than once" in cp.stderr, cp.stderr

    # across shards: also refused, and for the same reason rather than by luck
    man2 = tmp / "cross_shard.json"
    man2.write_text(json.dumps({
        "canonical_movies": ["Movies/a.tif", "Movies/a.tif"],
        "canonical_output_roots": ["Movies/a", "Movies/a"],
        "shards": [{"index": 0, "movies": ["Movies/a.tif"], "n_movies": 1},
                   {"index": 1, "movies": ["Movies/a.tif"], "n_movies": 1}]}))
    w1 = tmp / "w1"
    w1.mkdir()
    cp = merge(man2, [w, w1], tmp / "merged_cross",
               fake_status(tmp, [0, 0], name="s2.json", manifest=man2, workers=[w, w1]))
    assert cp.returncode == 2 and "same movie more than once" in cp.stderr, cp.stderr

    # A shard that names a movie twice while the canonical list does not: the
    # canonical check cannot see this, so the per-shard check is its only
    # detector. Without this the per-shard mutation survives behind the
    # canonical one.
    man_shard = tmp / "shard_only_dupe.json"
    man_shard.write_text(json.dumps({
        "canonical_movies": ["Movies/a.tif", "Movies/b.tif"],
        "canonical_output_roots": ["Movies/a", "Movies/b"],
        "shards": [{"index": 0, "movies": ["Movies/a.tif", "Movies/a.tif",
                                           "Movies/b.tif"], "n_movies": 3}]}))
    (w / "Movies" / "b.mrc").write_text("two")
    (w / "Movies" / "b.star").write_text("two")
    cp = merge(man_shard, [w], tmp / "merged_shard_dupe",
               fake_status(tmp, [0], name="s4.json", manifest=man_shard, workers=[w]))
    assert cp.returncode == 2, \
        f"a shard naming one movie twice was accepted (rc={cp.returncode})"
    assert "same movie more than once" in cp.stderr, cp.stderr

    # positive control: distinct names over the same shape merge cleanly, so the
    # refusals above are about the duplication and not about the fixture.
    man3 = tmp / "distinct.json"
    man3.write_text(json.dumps({
        "canonical_movies": ["Movies/a.tif", "Movies/b.tif"],
        "canonical_output_roots": ["Movies/a", "Movies/b"],
        "shards": [{"index": 0, "movies": ["Movies/a.tif", "Movies/b.tif"],
                    "n_movies": 2}]}))
    (w / "Movies" / "b.mrc").write_text("two")
    (w / "Movies" / "b.star").write_text("two")
    rep = tmp / "rep_ok.json"
    cp = merge(man3, [w], tmp / "merged_distinct",
               fake_status(tmp, [0], name="s3.json", manifest=man3, workers=[w]), rep)
    assert cp.returncode == 0, cp.stderr
    assert json.loads(rep.read_text())["n_movies_expected"] == 2


def case_worker_args_may_not_override_launcher_options(tmp: Path) -> None:
    """--i, --o and --gpu belong to the launcher and cannot be overridden.

    The launcher appends worker arguments after its own, and IOParser::getOption
    returns the last occurrence (src/args.cpp), so a copied command line
    carrying --o sends every worker into one shared directory -- the collision
    distinct worker directories exist to prevent -- while the children still
    exit zero and the launcher still writes verdict PASS.
    """
    star = tmp / "movies.star"
    build_star(star, DEFAULT_ROWS)
    for clash in (["--o", str(tmp / "shared")], ["--i", str(star)], ["--gpu", "0"]):
        out = tmp / ("run_" + clash[0].strip("-"))
        cp = run([PY, TOOLS / "run_multi_gpu.py", "--star", star, "--out", out,
                  "--binary", FAKE, "--workers", "2", "--no-witness", "--",
                  "--use_own"] + clash)
        assert cp.returncode == 2, \
            f"{clash[0]} in worker arguments was accepted (rc={cp.returncode})"
        assert clash[0] in cp.stderr and "launcher" in cp.stderr, cp.stderr
        assert not (out / "w0").exists(), "workers started before the refusal"

    # positive control: the same command without the clash runs and passes, so
    # the refusals are about the option and not about the launcher being broken.
    out = tmp / "run_ok"
    cp = run([PY, TOOLS / "run_multi_gpu.py", "--star", star, "--out", out,
              "--binary", FAKE, "--workers", "2", "--no-witness", "--", "--use_own"])
    assert cp.returncode == 0, cp.stderr
    assert json.loads((out / "status.json").read_text())["verdict"] == "PASS"


def case_aggregate_may_not_rewrite_staged_products(tmp: Path) -> None:
    """The aggregate pass regenerates the dataset STAR, not the movie products.

    --aggregate-with is a full --only_do_unfinished run, and isMovieComplete is
    option-dependent -- do_dose_weighting/save_noDW, even_odd_split,
    grouping_for_ps, and since PR110 the per-movie expected frame count. If
    --aggregate-args does not match what the workers ran, a movie the merge just
    certified is judged incomplete and reprocessed on top of the staged product,
    and the report then describes bytes the workers never wrote.
    """
    star = tmp / "movies.star"
    build_star(star, DEFAULT_ROWS)
    shards = tmp / "shards"
    assert partition(star, 2, shards).returncode == 0
    dirs, codes = run_workers(tmp, shards, 2)
    status = fake_status(tmp, codes)
    report = tmp / "report.json"
    cp = merge(shards / "shard_manifest.json", dirs, tmp / "merged", status, report,
               extra=["--aggregate-with", str(FAKE), "--input-star", str(star),
                      "--aggregate-args=--fake_reprocess"])
    assert cp.returncode == 3, \
        ("the aggregate pass rewrote staged products and still passed "
         f"(rc={cp.returncode})")
    rep = json.loads(report.read_text())
    assert any("rewrote" in p and "staged worker product" in p
               for p in rep["problems"]), rep["problems"]
    # every movie was rewritten, so the count must say so rather than reporting
    # a single incidental file
    assert any(f"rewrote {len(DEFAULT_ROWS)} staged" in p
               for p in rep["problems"]), rep["problems"]


def case_stale_comparison_report_is_not_republished(tmp: Path) -> None:
    """A report the current comparator did not produce may not be reused.

    Writing the origin sidecar unconditionally after the comparator subprocess
    binds whatever report happens to be on disk to the new inputs. A comparator
    that exits without writing --json-out therefore leaves the previous run's
    verdict looking freshly produced, and --reuse -- whose return code is zero
    by construction -- accepts it.
    """
    tool = tmp / "stub_compare.py"
    tool.write_text(STUB_COMPARATOR)
    roots = ["Movies/a"]
    manifest = tmp / "manifest.json"
    manifest.write_text(json.dumps({"canonical_output_roots": roots,
                                    "canonical_movies": ["Movies/a.tiff"]}))
    ref, test = tmp / "ref", tmp / "test"
    _tree(ref, roots, failing=set())
    _tree(test, roots, failing=set())
    out = tmp / "exact"

    def run24(tool_path, reuse=False):
        cmd = [PY, TOOLS / "compare24.py", "--ref", ref, "--test", test,
               "--tool", tool_path, "--manifest", manifest, "--out", out]
        if reuse:
            cmd.append("--reuse")
        return run(cmd)

    assert run24(tool).returncode == 0, "baseline comparison should pass"

    # the comparator now exits without producing a report; the stale PASS is
    # still on disk from the run above
    silent = tmp / "silent_compare.py"
    silent.write_text("import sys\nsys.exit(7)\n")
    cp = run24(silent)
    assert cp.returncode == 1, "a comparator that produced nothing was accepted"
    s = json.loads((out / "exact_summary.json").read_text())
    assert any("produced no usable report" in (r.get("reason") or "")
               for r in s["results"]), s

    # and the stale report must not have been republished as fresh evidence
    cp = run24(silent, reuse=True)
    assert cp.returncode == 1, "a stale report was reused after a silent comparator"

    # swapping the comparator in place also invalidates reuse: the recorded path
    # is unchanged, so only its contents can tell the two apart
    assert run24(tool).returncode == 0
    tool.write_text(STUB_COMPARATOR + "\n# edited in place\n")
    cp = run24(tool, reuse=True)
    assert cp.returncode == 1, "a report was reused after the comparator changed"
    s = json.loads((out / "exact_summary.json").read_text())
    assert any("origin mismatch" in (r.get("reason") or "") for r in s["results"]), s


def case_launcher_verdict_follows_the_device_witness(tmp: Path) -> None:
    """The launcher's verdict must be decided by what was observed.

    Every other device case stops at an argparse refusal or reads a hand-written
    status dict, so nothing executes run_multi_gpu's witness-to-verdict wiring.
    Without this case, replacing that wiring with an unconditional
    status["verdict"] = "PASS" leaves the whole suite green -- a device claim
    certified by code no test runs.

    nvidia-smi is replaced at the gpu_witness seam: host_devices supplies the
    two UUIDs and compute_apps supplies what the sampler would have seen. The
    workers are real child processes running fake_worker.py.
    """
    import importlib.util

    def load(name: str, path: Path):
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
        return mod

    gw = load("gpu_witness", TOOLS / "gpu_witness.py")
    rmg = load("run_multi_gpu", TOOLS / "run_multi_gpu.py")

    UUID_A, UUID_B = "GPU-aaaaaaaa-0000-0000-0000-000000000001", \
                     "GPU-bbbbbbbb-0000-0000-0000-000000000002"
    gw.host_devices = lambda: [
        {"smi_index": "0", "uuid": UUID_A, "name": "Fake A", "memory_total": "80 MiB"},
        {"smi_index": "1", "uuid": UUID_B, "name": "Fake B", "memory_total": "80 MiB"}]

    star = tmp / "movies.star"
    build_star(star, DEFAULT_ROWS)

    def launch(apps_for, out_name: str):
        """Run two 'GPU' workers; apps_for(pids) supplies each sample."""
        state = {"pids": []}

        def compute_apps():
            if not state["pids"]:
                # The launcher starts the sampler before the children exist, so
                # the first samples legitimately see nothing.
                return []
            return apps_for(state["pids"])

        gw.compute_apps = compute_apps
        real_popen = rmg.subprocess.Popen

        def popen(cmd, **kw):
            p = real_popen(cmd, **kw)
            state["pids"].append(p.pid)
            return p

        rmg.subprocess.Popen = popen
        # Most scenarios here are meant to fail, and the launcher reports that
        # on stderr; leaving it on the terminal makes a passing case look like
        # five failures.
        try:
            with contextlib.redirect_stderr(io.StringIO()), \
                 contextlib.redirect_stdout(io.StringIO()):
                rc = rmg.main(["--star", str(star), "--out", str(tmp / out_name),
                               "--binary", str(FAKE), "--devices", "0,1",
                               "--sample-interval", "0.01", "--", "--use_own"])
        finally:
            rmg.subprocess.Popen = real_popen
        status = json.loads((tmp / out_name / "status.json").read_text())
        return rc, status

    def apps(pid_to_uuid):
        return lambda pids: [{"pid": str(p), "gpu_uuid": pid_to_uuid(i, p)}
                             for i, p in enumerate(pids)]

    # correct: each worker on its own device
    rc, st = launch(apps(lambda i, p: (UUID_A, UUID_B)[i]), "ok")
    assert rc == 0 and st["verdict"] == "PASS", st
    assert st["gpu_witness"]["all_pids_witnessed_on_intended_distinct_devices"], st
    assert [w["returncode"] for w in st["workers"]] == [0, 0], st

    ok_dir = tmp / "ok"
    ok_manifest = Path(st["manifest"])
    ok_workers = [ok_dir / "w0", ok_dir / "w1"]
    ok_status = ok_dir / "status.json"
    ok_report = tmp / "merge_good_witness.json"
    cp = merge(ok_manifest, ok_workers, tmp / "merged_good_witness", ok_status,
               ok_report)
    assert cp.returncode == 0, \
        f"complete GPU witness should merge: {cp.stderr} {cp.stdout}"

    def merge_forged_witness(name: str, mutate) -> None:
        forged = json.loads(json.dumps(st))
        mutate(forged)
        status_path = tmp / f"forged_{name}.json"
        status_path.write_text(json.dumps(forged))
        cp = merge(ok_manifest, ok_workers, tmp / f"merged_forged_{name}",
                   status_path, tmp / f"report_forged_{name}.json")
        assert cp.returncode == 3, \
            f"merge accepted incomplete GPU witness {name}: {cp.stdout} {cp.stderr}"

    merge_forged_witness("missing", lambda status: status.pop("gpu_witness"))
    merge_forged_witness("false_success", lambda status: status["gpu_witness"].update(
        all_pids_witnessed_on_intended_distinct_devices=False))
    merge_forged_witness("missing_sampler_errors", lambda status:
                         status["gpu_witness"].pop("sampler_errors"))
    merge_forged_witness("sampler_error", lambda status:
                         status["gpu_witness"].update(sampler_errors=["sample failed"]))
    merge_forged_witness("missing_pid", lambda status:
                         status["gpu_witness"]["witnessed"].pop(
                             str(status["workers"][0]["pid"])))
    merge_forged_witness("wrong_uuid", lambda status:
                         status["gpu_witness"]["witnessed"].update(
                             {str(status["workers"][0]["pid"]): [UUID_B]}))
    merge_forged_witness("shared_uuid", lambda status:
                         status["gpu_witness"]["witnessed"].update(
                             {str(status["workers"][1]["pid"]): [UUID_A]}))

    # both workers observed on ONE physical device
    rc, st = launch(apps(lambda i, p: UUID_A), "shared")
    assert rc == 3 and st["verdict"] == "FAIL", st
    assert st["gpu_witness"]["shared_devices"], st

    # each worker observed on the other's device
    rc, st = launch(apps(lambda i, p: (UUID_B, UUID_A)[i]), "swapped")
    assert rc == 3 and st["verdict"] == "FAIL", st
    assert st["gpu_witness"]["wrong_device"], st
    assert not st["gpu_witness"]["shared_devices"], st

    # nothing ever observed, although the workers exited zero
    rc, st = launch(lambda pids: [], "unwitnessed")
    assert rc == 3 and st["verdict"] == "FAIL", st
    assert st["gpu_witness"]["unwitnessed_pids"], st
    assert [w["returncode"] for w in st["workers"]] == [0, 0], \
        "the run must fail on the witness, not on an exit code"

    # the sampler dies after witnessing everything correctly: an incomplete
    # observation is not a pass, whatever it managed to see first
    for exc in (gw.WitnessError("nvidia-smi exploded"), RuntimeError("thread died")):
        calls = {"n": 0}
        correct = apps(lambda i, p: (UUID_A, UUID_B)[i])

        def dying(pids, _exc=exc, _c=calls, _ok=correct):
            _c["n"] += 1
            if _c["n"] > 2:
                raise _exc
            return _ok(pids)

        rc, st = launch(dying, "dying_" + type(exc).__name__)
        assert rc == 3 and st["verdict"] == "FAIL", (type(exc).__name__, st)
        assert st["gpu_witness"]["sampler_errors"], st

    # a merge must not launder any of those launcher FAILs into a PASS, nor
    # accept a PASS its own witness record contradicts
    rc, st = launch(apps(lambda i, p: UUID_A), "shared2")
    out = tmp / "shared2"
    (out / "status.json").write_text(json.dumps({**st, "verdict": "PASS"}))
    cp = merge(out / "shards" / "shard_manifest.json", [out / "w0", out / "w1"],
               tmp / "merged_forced", out / "status.json", tmp / "rep_forced.json")
    assert cp.returncode == 3, "a PASS contradicted by its own witness was merged"
    rep = json.loads((tmp / "rep_forced.json").read_text())
    assert any("GPU witness" in p for p in rep["problems"]), rep["problems"]


def case_launcher_signal_reaps_owned_process_group(tmp: Path) -> None:
    """SIGTERM/SIGINT to the launcher must reap workers and their children."""
    star = tmp / "movies.star"
    build_star(star, DEFAULT_ROWS[:1])
    worker = tmp / "term_ignoring_worker.py"
    worker.write_text("""#!/usr/bin/env python3
import json, os, signal, subprocess, sys, time
from pathlib import Path
signal.signal(signal.SIGTERM, signal.SIG_IGN)
out = Path(sys.argv[sys.argv.index('--o') + 1])
child_code = ("import signal,time,sys; from pathlib import Path; "
             "out=Path(sys.argv[1]); signal.signal(signal.SIGTERM, signal.SIG_IGN); "
             "(out/'child_ready').write_text('ready'); time.sleep(300)")
child = subprocess.Popen([sys.executable, '-c', child_code, str(out)])
while not (out / 'child_ready').exists(): time.sleep(0.01)
(out / 'pids.json').write_text(json.dumps({'worker': os.getpid(),
                                          'child': child.pid, 'pgid': os.getpgrp()}))
while True: time.sleep(0.1)
""")
    worker.chmod(0o755)

    wrapper = tmp / "invoke_launcher.py"
    wrapper.write_text(
        "import sys\n"
        f"sys.path.insert(0, {str(TOOLS)!r})\n"
        "import run_multi_gpu as launcher\n"
        "launcher._TERMINATE_GRACE_SECONDS = 0.2\n"
        "launcher._KILL_REAP_SECONDS = 2.0\n"
        "raise SystemExit(launcher.main())\n")

    for signum in (signal.SIGTERM, signal.SIGINT):
        out = tmp / f"run_{signum}"
        proc = subprocess.Popen([PY, wrapper, "--star", star, "--out", out,
                                 "--binary", worker, "--workers", "1", "--no-witness"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        group = None
        try:
            marker = out / "w0" / "pids.json"
            deadline = time.monotonic() + 8.0
            while time.monotonic() < deadline and not marker.exists():
                if proc.poll() is not None:
                    break
                time.sleep(0.02)
            assert marker.exists(), f"worker did not reach signal-ready state for {signum}"
            pids = json.loads(marker.read_text())
            group = int(pids["pgid"])
            assert pids["worker"] == group, pids

            proc.send_signal(signum)
            rc = proc.wait(timeout=8.0)
            stdout, stderr = proc.communicate(timeout=1.0)
            assert rc == 128 + signum, \
                f"launcher did not report signal {signum}: rc={rc}; {stdout}; {stderr}"
            status = json.loads((out / "status.json").read_text())
            assert status["verdict"] == "FAIL" and status["termination_signal"] == signum, status
            assert status["workers"][0]["returncode"] != 0, status

            deadline = time.monotonic() + 3.0
            while time.monotonic() < deadline:
                try:
                    os.killpg(group, 0)
                except ProcessLookupError:
                    break
                time.sleep(0.02)
            else:
                raise AssertionError(f"owned worker process group {group} survived signal cleanup")
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=3.0)
            if group is not None:
                try:
                    os.killpg(group, signal.SIGKILL)
                except ProcessLookupError:
                    pass


def case_launcher_signal_reaches_cooperative_worker(tmp: Path) -> None:
    """A normal worker must receive TERM, not inherit the spawn signal mask."""
    star = tmp / "movies.star"
    build_star(star, DEFAULT_ROWS[:1])
    worker = tmp / "cooperative_worker.py"
    worker.write_text("""#!/usr/bin/env python3
import os, signal, sys, time
from pathlib import Path
out = Path(sys.argv[sys.argv.index('--o') + 1])
def stop(signum, _frame):
    (out/'received_term').write_text(str(signum))
    raise SystemExit(0)
signal.signal(signal.SIGTERM, stop)
(out/'ready').write_text(str(os.getpid()))
while True: time.sleep(0.01)
""")
    worker.chmod(0o755)
    out = tmp / "run"
    proc = subprocess.Popen([PY, TOOLS / "run_multi_gpu.py", "--star", star,
                             "--out", out, "--binary", worker, "--workers", "1",
                             "--no-witness"], stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True)
    group = None
    try:
        marker = out / "w0" / "ready"
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline and not marker.exists() and proc.poll() is None:
            time.sleep(0.02)
        assert marker.exists(), "cooperative worker did not become ready"
        group = int(marker.read_text())
        proc.send_signal(signal.SIGTERM)
        rc = proc.wait(timeout=15.0)
        stdout, stderr = proc.communicate(timeout=1.0)
        assert rc == 128 + signal.SIGTERM, (rc, stdout, stderr)
        assert (out / "w0" / "received_term").exists(), \
            "worker never received TERM; spawn must not leave it blocked across exec"
        status = json.loads((out / "status.json").read_text())
        assert status["verdict"] == "FAIL" and status["termination_signal"] == signal.SIGTERM
        assert status["workers"][0]["returncode"] == 0, status
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=3.0)
        if group is not None:
            try:
                os.killpg(group, signal.SIGKILL)
            except ProcessLookupError:
                pass


def case_launcher_signal_during_spawn_keeps_child_owned(tmp: Path) -> None:
    """An interrupt after Popen but before bookkeeping must still reap the child."""
    star = tmp / "movies.star"
    build_star(star, DEFAULT_ROWS[:1])
    worker = tmp / "sleeping_worker.py"
    worker.write_text("#!/usr/bin/env python3\nimport time\ntime.sleep(300)\n")
    worker.chmod(0o755)
    pid_file = tmp / "spawned.pid"
    wrapper = tmp / "interrupt_spawn.py"
    wrapper.write_text(
        "import os, signal, sys\nfrom pathlib import Path\n"
        f"sys.path.insert(0, {str(TOOLS)!r})\n"
        "import run_multi_gpu as launcher\n"
        "original = launcher.subprocess.Popen\n"
        "def spawn(*args, **kwargs):\n"
        "    child = original(*args, **kwargs)\n"
        f"    Path({str(pid_file)!r}).write_text(str(child.pid))\n"
        "    os.kill(os.getpid(), signal.SIGTERM)\n"
        "    return child\n"
        "launcher.subprocess.Popen = spawn\n"
        "raise SystemExit(launcher.main())\n")
    out = tmp / "run"
    group = None
    try:
        cp = run([PY, wrapper, "--star", star, "--out", out, "--binary", worker,
                  "--workers", "1", "--no-witness"], timeout=15.0)
        assert pid_file.exists(), "spawn boundary was not reached"
        group = int(pid_file.read_text())
        assert cp.returncode == 128 + signal.SIGTERM, cp.stderr + cp.stdout
        status = json.loads((out / "status.json").read_text())
        assert len(status["workers"]) == 1 and status["workers"][0]["pid"] == group, \
            "interrupt discarded ownership of the newly started child"
        try:
            os.killpg(group, 0)
        except ProcessLookupError:
            pass
        else:
            raise AssertionError("child survived interruption during spawn bookkeeping")
    finally:
        if group is None and pid_file.exists():
            group = int(pid_file.read_text())
        if group is not None:
            try:
                os.killpg(group, signal.SIGKILL)
            except ProcessLookupError:
                pass


def case_per_worker_timing_and_rss_recorded(tmp: Path) -> None:
    """Every worker gets its own start, end and resident-set figure.

    A scaling comparison cannot reconstruct these afterwards, and the launcher
    is the only thing that owns the child processes. The tail figure in
    particular has a trap: waiting on the children sequentially records
    worker 1's end as the moment worker 0 was reaped, so the tail reads as zero
    whenever the workers happen to be reaped in finishing order. This case makes
    one worker outlive the other and requires the tail to see it.
    """
    # Five movies over two shards is 3 + 2, and a per-movie delay makes worker 0
    # -- the one reaped FIRST -- also the one that finishes LAST. That ordering is
    # what discriminates: a launcher that waits on its children sequentially
    # stamps worker 1's end at the moment worker 0 was reaped, so its tail
    # collapses to zero here while the real spread is ~0.4 s.
    star = tmp / "movies.star"
    build_star(star, DEFAULT_ROWS[:5])
    out = tmp / "run"
    cp = run([PY, TOOLS / "run_multi_gpu.py", "--star", star, "--out", out,
              "--binary", FAKE, "--workers", "2", "--no-witness",
              "--sample-interval", "0.05", "--", "--use_own",
              "--fake_sleep_per_movie", "0.4"])
    assert cp.returncode == 0, cp.stderr
    st = json.loads((out / "status.json").read_text())

    assert st["started_at"] and st["ended_at"], st
    assert st["final_worker_tail_seconds"] is not None, st
    for w in st["workers"]:
        assert w["started_at"] and w["ended_at"], w
        assert w["ended_at"] >= w["started_at"], w
        assert w["wall_seconds"] >= 0, w
        assert w["wall_seconds"] <= st["wall_seconds"] + 0.5, \
            f"worker wall exceeds run wall: {w}"
        assert "rss_note" in w, w
        if sys.platform.startswith("linux"):
            # A positive figure, not "None or positive". Tolerating None here made
            # this assertion unable to observe a sampler that records nothing:
            # /proc exists, so .unavailable stays unset, rss_note keeps its normal
            # text, and a null figure satisfied the disjunction. The mutation
            # control for the recording path survived on Linux for exactly that
            # reason while passing on macOS, where the branch below catches it.
            # If a host hides VmHWM, this fails loudly and someone decides -- which
            # is the right outcome for a figure the scaling work depends on.
            assert w["rss_hwm_kib"] and w["rss_hwm_kib"] > 0, (
                "no resident-set high-water was recorded on a host with /proc; "
                "a scaling comparison cannot reconstruct it afterwards", w)
        else:
            # No /proc: the absence must be stated, not silently reported as 0.
            assert w["rss_hwm_kib"] is None, w
            assert "no /proc" in w["rss_note"], w

    import datetime as _dt
    ends = [_dt.datetime.fromisoformat(w["ended_at"]) for w in st["workers"]]
    assert len(ends) == 2, st

    # worker 0 owns three movies and worker 1 owns two, so worker 0 must be the
    # later of the two -- and it is the one reaped first
    assert ends[0] > ends[1], \
        f"the worker with the larger shard did not finish last: {st['workers']}"

    # a materially non-zero tail. Comparing the reported tail against the spread
    # of the reported ends would be tautological -- both come from the same
    # stamps -- so the discriminating assertion is the absolute magnitude.
    tail = st["final_worker_tail_seconds"]
    assert tail > 0.25, \
        (f"final-worker tail {tail}s is ~0 although the shards differ by one "
         "movie at 0.4s each; the launcher is not stamping each child's own exit")
    spread = (max(ends) - min(ends)).total_seconds()
    assert abs(spread - tail) < 0.05, f"tail {tail} vs end spread {spread}"


def case_aggregate_staging_namespace_reserved(tmp: Path) -> None:
    """A movie may not write into the namespace the merge stages aggregates in.

    merge_workers stages each worker's fixed-name aggregates under
    <out>/_workers/w<k>/. A movie whose output root is
    '_workers/w0/corrected_micrographs' is staged to the exact path worker 0's
    own aggregate is copied to, and the aggregate -- copied later -- wins. The
    per-movie metadata is destroyed while `produced` still records the path, so
    the merge reports PASS over corrupted output.

    Such a name cannot be written unquoted: the STAR reader takes a leading '_'
    as a label. Quoted, it is a legal movie name and was accepted.
    """
    star = tmp / "movies.star"
    star.write_text(OPTICS.lstrip("\n")
                    + "'_workers/w0/corrected_micrographs.tif' 1 0.000000\n"
                    + "Movies/b.tiff 1 1.400000\n\n")
    cp = partition(star, 1, tmp / "shards")
    assert cp.returncode == 3, f"_workers namespace accepted (rc={cp.returncode})"
    assert "reserved-namespace collision" in cp.stderr, cp.stderr

    # and the merge refuses it from a manifest it did not produce
    man = tmp / "man.json"
    man.write_text(json.dumps({
        "canonical_movies": ["_workers/w0/corrected_micrographs.tif"],
        "canonical_output_roots": ["_workers/w0/corrected_micrographs"],
        "shards": [{"index": 0, "movies": ["_workers/w0/corrected_micrographs.tif"],
                    "n_movies": 1}]}))
    w = tmp / "w0"
    w.mkdir()
    cp = merge(man, [w], tmp / "merged",
               fake_status(tmp, [0], manifest=man, workers=[w]))
    assert cp.returncode == 2, f"merge accepted the namespace (rc={cp.returncode})"
    assert "_workers" in cp.stderr, cp.stderr

    # positive control: '_workers' only as a leading path component is the
    # hazard, so a movie merely containing the word is still accepted
    star2 = tmp / "ok.star"
    star2.write_text(OPTICS.lstrip("\n")
                     + "Movies/_workers_notes.tif 1 0.000000\n"
                     + "Movies/b.tiff 1 1.400000\n\n")
    assert partition(star2, 1, tmp / "shards_ok").returncode == 0


def case_comparator_exit_must_match_its_report(tmp: Path) -> None:
    """A comparator that contradicts itself may not leave reusable evidence.

    If the comparator writes a syntactically passing report and then exits
    non-zero, the first pass fails on the return code -- correctly -- but
    publishing the origin sidecar makes that report reusable, and --reuse
    substitutes rc = 0. The same comparison then satisfies every gate and comes
    back PASS.
    """
    liar = tmp / "liar.py"
    liar.write_text(
        "import argparse, json, pathlib, sys\n"
        "ap = argparse.ArgumentParser()\n"
        "for f in ('--ref-mrc','--test-mrc','--ref-star','--test-star','--gate','--json-out'):\n"
        "    ap.add_argument(f)\n"
        "a = ap.parse_args()\n"
        "pathlib.Path(a.json_out).write_text(json.dumps({\n"
        "  'overall_status':'PASS','coverage':{'complete':True},'checks':{\n"
        "   'corrected_image':{'pixel_identical':True,'rmse':0.0,'passed':True},\n"
        "   'motion_trajectory':{'max_shift_error':0.0,'passed':True},\n"
        "   'star_fields':{'num_differences':0,'passed':True}}}))\n"
        "sys.exit(3)\n")
    roots = ["Movies/a"]
    manifest = tmp / "manifest.json"
    manifest.write_text(json.dumps({"canonical_output_roots": roots,
                                    "canonical_movies": ["Movies/a.tiff"]}))
    ref, test = tmp / "ref", tmp / "test"
    _tree(ref, roots, failing=set())
    _tree(test, roots, failing=set())
    out = tmp / "exact"

    def run24(tool, reuse=False):
        cmd = [PY, TOOLS / "compare24.py", "--ref", ref, "--test", test,
               "--tool", tool, "--manifest", manifest, "--out", out]
        if reuse:
            cmd.append("--reuse")
        return run(cmd)

    cp = run24(liar)
    assert cp.returncode == 1, "a self-contradicting comparator was accepted"
    s = json.loads((out / "exact_summary.json").read_text())
    assert any("contradicts its report" in (r.get("reason") or "")
               for r in s["results"]), s

    # no reusable evidence may have been left behind
    assert not list(out.glob("*.origin.json")), \
        "a sidecar was published for a comparison the comparator contradicted"
    cp = run24(liar, reuse=True)
    assert cp.returncode == 1, "the contradicted report was reused as a pass"

    # positive control: an honest comparator still publishes and still reuses,
    # so the refusals above are about the contradiction and not about the gate
    honest = tmp / "honest.py"
    honest.write_text(STUB_COMPARATOR)
    out2 = tmp / "exact_ok"

    def run_ok(reuse=False):
        cmd = [PY, TOOLS / "compare24.py", "--ref", ref, "--test", test,
               "--tool", honest, "--manifest", manifest, "--out", out2]
        if reuse:
            cmd.append("--reuse")
        return run(cmd)

    assert run_ok().returncode == 0, "the honest comparator should pass"
    assert list(out2.glob("*.origin.json")), "no sidecar published for a clean run"
    assert run_ok(reuse=True).returncode == 0, "a clean report should reuse"


CASES = [
    case_roundtrip_and_metadata,
    case_empty_shard_rejected,
    case_output_name_collision,
    case_duplicate_movie_in_input,
    case_collapsed_spaces_are_a_collision,
    case_decorated_output_collision,
    case_real_output_suffixes_attributed,
    case_aggregate_name_shadowing,
    case_star_parser_refusals,
    case_clean_merge,
    case_lost_output,
    case_duplicate_and_misrouted_output,
    case_unassigned_movie_output,
    case_failed_worker_blocks_merge,
    case_missing_status_blocks_merge,
    case_failed_device_witness_blocks_merge,
    case_missing_worker_directory,
    case_link_with_aggregate_refused,
    case_output_root_matches_withoutextension,
    case_reserved_name_collision,
    case_short_row_refused,
    case_killed_worker_then_nonprefix_resume,
    case_aggregate_star_canonical_order,
    case_aggregate_star_must_match_partition_content,
    case_aggregate_args_may_not_override_owned_paths,
    case_aggregate_wrong_order_rejected,
    case_failed_staging_never_reprocesses,
    case_merge_out_is_resolved,
    case_launcher_refuses_cpu_gpu_confusion,
    case_per_worker_cpu_masks,
    case_devices_with_no_witness_refused,
    case_compare24_report_identity,
    case_compare24_injective_report_identity,
    case_normalized_root_collision_refused,
    case_interior_double_slash_is_the_same_product,
    case_reuse_pins_the_trees_not_just_the_root,
    case_duplicate_coverage_and_zero_pairs_rejected,
    case_absolute_movie_roots_attributed,
    case_gpu_witness_logic,
    case_sampler_lifecycle,
    case_stale_status_is_refused,
    case_duplicate_movie_name_refused,
    case_worker_args_may_not_override_launcher_options,
    case_aggregate_may_not_rewrite_staged_products,
    case_stale_comparison_report_is_not_republished,
    case_launcher_verdict_follows_the_device_witness,
    case_launcher_signal_reaps_owned_process_group,
    case_launcher_signal_reaches_cooperative_worker,
    case_launcher_signal_during_spawn_keeps_child_owned,
    case_per_worker_timing_and_rss_recorded,
    case_aggregate_staging_namespace_reserved,
    case_comparator_exit_must_match_its_report,
]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--binary", default=None,
                    help="built motioncorr; enables the --gpu rejection case")
    ap.add_argument("--only", default=None)
    a = ap.parse_args(argv)

    cases = list(CASES)
    if a.binary:
        cases.append(lambda tmp: case_device_list_rejected(tmp, a.binary))
        cases[-1].__name__ = "case_device_list_rejected"  # type: ignore[attr-defined]
    else:
        print("NOTE: --binary not given; the --gpu device-list rejection case is "
              "NOT run and is not claimed to pass.")

    failures = []
    ran = 0
    for case in cases:
        name = getattr(case, "__name__", str(case))
        if a.only and a.only not in name:
            continue
        ran += 1
        with tempfile.TemporaryDirectory(prefix="mgpu_") as td:
            try:
                case(Path(td))
            except AssertionError as exc:
                failures.append((name, str(exc)))
                print(f"FAIL {name}: {exc}")
                continue
            except Exception as exc:  # noqa: BLE001
                failures.append((name, f"{type(exc).__name__}: {exc}"))
                print(f"ERROR {name}: {type(exc).__name__}: {exc}")
                continue
        print(f"ok   {name}")

    skipped = len(cases) - ran
    print(f"\n{ran - len(failures)}/{ran} passed"
          + (f" ({skipped} not selected by --only, and not claimed)" if skipped else ""))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
