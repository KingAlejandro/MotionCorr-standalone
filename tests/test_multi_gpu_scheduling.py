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
message for the same input (docs/multi_gpu/pr_a_evidence/device_list_witness.txt).

With --binary pointing at a built motioncorr, the --gpu device-list rejection is
also exercised against the real argument parser.
"""

from __future__ import annotations

import argparse
import json
import os
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
                witness: dict | None = None, name: str = "status.json") -> Path:
    p = tmp / name
    body: dict = {"workers": [{"index": k, "returncode": rc}
                              for k, rc in enumerate(codes)],
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

    # A single valid id must not hit the list error. On a CPU-only build it
    # reaches the missing-CUDA error instead, which is the correct next check.
    cp = run([binary, "--i", missing, "--o", tmp / "out", "--use_own", "--gpu", "0"])
    combined = cp.stdout + cp.stderr
    assert "device entries" not in combined, combined[:400]
    assert "not a non-negative" not in combined, combined[:400]


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
    status = fake_status(tmp, codes)
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
    import threading as _threading
    probe = run_multi_gpu.Sampler(0.01)
    assert not isinstance(getattr(probe, "_stop", None), _threading.Event), (
        "Sampler shadows threading.Thread._stop with an Event; join() raises "
        "\"'Event' object is not callable\" on CPython 3.12")
    # (CPython 3.14 removed Thread._stop entirely, so absent is fine; an Event
    # in its place is the defect, on every version.)

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
    case_aggregate_wrong_order_rejected,
    case_launcher_refuses_cpu_gpu_confusion,
    case_per_worker_cpu_masks,
    case_devices_with_no_witness_refused,
    case_compare24_report_identity,
    case_absolute_movie_roots_attributed,
    case_gpu_witness_logic,
    case_sampler_lifecycle,
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
