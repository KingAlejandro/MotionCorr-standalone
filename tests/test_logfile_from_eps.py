#!/usr/bin/env python3
"""The normal report path renders logfile.pdf from EPS only when no earlier
all_batches.pdf exists.

generateLogFilePDFAndWriteStarFiles() builds header.pdf and batch.pdf from EPS,
then used to concatenate header.pdf + all_batches.pdf into logfile.pdf, which
makes Ghostscript re-render pages the process already holds as EPS. When no
all_batches.pdf exists before this run's report, logfile.pdf is exactly header
EPS followed by this run's batch EPS, so it is rendered from the EPS list
instead. When one does exist (--only_do_unfinished, incremental runs) it can
hold batches whose EPS this run lacks, so the concatenation must stay.

The witness is a fake Ghostscript on PATH that records every call, including the
content of its @list file at call time. The runner removes logfile.pdf.lst
after use in this mode, so the call log is the only place the EPS-direct render
can be seen. The fake also stands in for the failure cases. The pixel-level
equality of the two render routes is not asserted here; it needs real
Ghostscript and is measured separately.

Passing --expect-fail inverts the exit status: the compiled mutants of the
runner must fail one of these checks.
"""
from __future__ import annotations
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ARGS = ["--use_own", "--j", "1", "--skip_defect", "--angpix", "1.0",
        "--voltage", "300", "--patch_x", "1", "--patch_y", "1", "--bfactor", "150"]

STAR = """data_optics

loop_
_rlnOpticsGroupName #1
_rlnOpticsGroup #2
_rlnMicrographOriginalPixelSize #3
_rlnVoltage #4
_rlnSphericalAberration #5
_rlnAmplitudeContrast #6
one 1 1.0 300 2.7 0.1

data_movies

loop_
_rlnMicrographMovieName #1
_rlnOpticsGroup #2
"""

FAKE_GS = r'''#!%(python)s
import json, os, pathlib, sys, time
args = sys.argv[1:]
out = None
lst = None
for a in args:
    if a.lower().startswith("-soutputfile="):
        out = a.split("=", 1)[1]
    if a.startswith("@"):
        lst = a[1:]
rec = {"args": args, "out": out,
       "list": pathlib.Path(lst).read_text().splitlines() if lst else None}
fd = os.open(os.environ["FAKE_GS_LOG"], os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
os.write(fd, (json.dumps(rec) + "\n").encode())
os.close(fd)
mode = os.environ.get("FAKE_GS_MODE", "ok")
if mode == "hang":
    time.sleep(1)
if mode in ("fail", "hang"):
    sys.exit(1)
if out:
    pathlib.Path(out).write_bytes(b"%%PDF-1.4 fake\n%%%%EOF\n")
'''


def require(ok: bool, message: str) -> None:
    if not ok:
        raise AssertionError(message)


def write_star(path: Path, movies: list[str]) -> None:
    path.write_text(STAR + "".join(f"Movies/{m}.tiff 1\n" for m in movies))


def run(binary: Path, tmp: Path, star: str, out: Path, env: dict,
        extra: list[str] = []) -> subprocess.CompletedProcess:
    return subprocess.run([str(binary), "--i", star, "--o", str(out) + "/", *ARGS, *extra],
                          cwd=tmp, capture_output=True, text=True, env=env, timeout=300)


def calls(log: Path) -> list[dict]:
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text().splitlines()]


def joins(cs: list[dict], out: Path, name: str) -> list[dict]:
    return [c for c in cs if c["list"] is not None and c["out"] == str(out / name)]


def concats(cs: list[dict], out: Path, name: str) -> list[dict]:
    return [c for c in cs if c["list"] is None and c["out"] == str(out / name)]


def inputs(c: dict) -> list[str]:
    return [a for a in c["args"] if not a.startswith("-")]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--binary", type=Path, required=True)
    ap.add_argument("--expect-fail", action="store_true",
                    help="exit 0 only if a check fails (compiled-mutant control)")
    a = ap.parse_args()
    binary = a.binary.resolve()
    fixture = Path(__file__).resolve().parents[1] / "test-data/synthetic/synthetic_movie.tiff"
    try:
        with tempfile.TemporaryDirectory(prefix="logfile-from-eps-") as td:
            check(binary, fixture, Path(td))
    except AssertionError as exc:
        print("FAIL:", exc)
        return 0 if a.expect_fail else 1
    if a.expect_fail:
        print("FAIL: --expect-fail given but every check passed")
        return 1
    print("logfile from EPS: all checks passed")
    return 0


def check(binary: Path, fixture: Path, tmp: Path) -> None:
    (tmp / "Movies").mkdir()
    for name in "abc":
        shutil.copyfile(fixture, tmp / "Movies" / f"{name}.tiff")
    bindir = tmp / "bin"
    bindir.mkdir()
    gs = bindir / "gs"
    gs.write_text(FAKE_GS % {"python": Path(sys.executable).resolve()})
    gs.chmod(0o755)
    log = tmp / "gs.log"

    def env(mode: str = "ok") -> dict:
        log.unlink(missing_ok=True)
        return dict(os.environ, PATH=str(bindir) + os.pathsep + os.environ["PATH"],
                    FAKE_GS_LOG=str(log), FAKE_GS_MODE=mode)

    # --- No earlier all_batches.pdf: EPS-direct, no concatenation. -----------
    write_star(tmp / "ab.star", ["a", "b"])
    out = tmp / "fresh"
    r = run(binary, tmp, "ab.star", out, env())
    require(r.returncode == 0, "fresh run failed: " + r.stderr[-2000:])
    cs = calls(log)
    header, batch = joins(cs, out, "header.pdf"), joins(cs, out, "batch.pdf")
    logfile = joins(cs, out, "logfile.pdf")
    require(len(header) == 1 and len(batch) == 1,
            "header.pdf and batch.pdf must each be rendered once from EPS: " + repr(cs))
    require(len(logfile) == 1,
            "fresh run must render logfile.pdf once from EPS, not concatenate it: " + repr(cs))
    require(logfile[0]["list"] == header[0]["list"] + batch[0]["list"] and batch[0]["list"],
            "EPS-direct logfile.pdf must list header EPS followed by batch EPS, in order: "
            + repr(logfile[0]["list"]))
    require(not concats(cs, out, "logfile.pdf"),
            "fresh run still concatenated header.pdf + all_batches.pdf into logfile.pdf")
    require(len(cs) == 3, "fresh run must make exactly three Ghostscript calls: " + repr(cs))
    names = sorted(p.name for p in out.iterdir() if p.is_file())
    for needed in ("header.pdf", "header.pdf.lst", "batch.pdf", "batch.pdf.lst",
                   "all_batches.pdf", "logfile.pdf"):
        require(needed in names, "missing output " + needed + ": " + repr(names))
    require("logfile.pdf.lst" not in names,
            "normal path must not add logfile.pdf.lst to the output inventory")
    print("PASS fresh run renders logfile.pdf from EPS (header list + batch list), one render")

    # --- An earlier all_batches.pdf exists: keep the concatenation. ----------
    write_star(tmp / "abc.star", ["a", "b", "c"])
    before = (out / "all_batches.pdf").read_bytes()
    require(before.startswith(b"%PDF"), "fixture: prior all_batches.pdf")
    r = run(binary, tmp, "abc.star", out, env(), ["--only_do_unfinished"])
    require(r.returncode == 0, "incremental run failed: " + r.stderr[-2000:])
    cs = calls(log)
    require(not joins(cs, out, "logfile.pdf"),
            "incremental run rendered logfile.pdf from this run's EPS although a prior "
            "all_batches.pdf exists: the earlier batches would be lost: " + repr(cs))
    cat = concats(cs, out, "logfile.pdf")
    require(len(cat) == 1, "incremental run must concatenate logfile.pdf once: " + repr(cs))
    require(inputs(cat[0]) == [str(out / "header.pdf"), str(out / "all_batches.pdf")],
            "concatenation must be header.pdf then all_batches.pdf: " + repr(inputs(cat[0])))
    require(any(c["out"] and c["out"].endswith("all_batches_tmp_combine.pdf") for c in cs),
            "prior all_batches.pdf must have been merged with the new batch.pdf: " + repr(cs))
    require("logfile.pdf.lst" not in {p.name for p in out.iterdir()},
            "incremental path must not add logfile.pdf.lst")
    print("PASS incremental run with a prior all_batches.pdf keeps the concatenation")

    # --- Failure semantics: Ghostscript failure is not a job failure. --------
    for mode in ("fail", "hang"):
        out = tmp / ("gsfail-" + mode)
        r = run(binary, tmp, "ab.star", out, env(mode))
        require(r.returncode == 0,
                f"gs {mode}: exit {r.returncode}; the concatenation this replaced ignored "
                "Ghostscript failure and so must the EPS-direct render")
        require("terminate called" not in r.stderr, f"gs {mode}: std::terminate")
        require(any("ERROR in executing: gs -sDEVICE=pdfwrite" in line and
                    "-sOutputFile=" + str(out / "logfile.pdf") + " " in line
                    for line in r.stderr.splitlines()),
                f"gs {mode}: the logfile.pdf failure was not reported: " + r.stderr[-1500:])
        require((out / "Movies" / "a.mrc").stat().st_size > 0, f"gs {mode}: product lost")
        # The failed concatenation this replaced left no logfile.pdf; an empty
        # placeholder would read as a written report.
        require(not (out / "logfile.pdf").exists(),
                f"gs {mode}: a failed logfile.pdf render left a file behind; the "
                "concatenation it replaced left none")
    print("PASS Ghostscript failure (immediate and delayed) reports, exits 0 and leaves "
          "no logfile.pdf, as before")

    # A directory in the way of logfile.pdf: gs cannot write it. The old
    # concatenation ignored this, so the job still succeeds, nothing is touched
    # in its place, and nothing escapes the thread as std::terminate.
    out = tmp / "logfile-dir"
    out.mkdir()
    (out / "logfile.pdf").mkdir()
    r = run(binary, tmp, "ab.star", out, env())
    require(r.returncode == 0, f"logfile.pdf directory: exit {r.returncode}: " + r.stderr[-1500:])
    require("terminate called" not in r.stderr, "logfile.pdf directory: std::terminate")
    require(any("ERROR in executing: gs -sDEVICE=pdfwrite" in line and
                "-sOutputFile=" + str(out / "logfile.pdf") + " " in line
                for line in r.stderr.splitlines()),
            "logfile.pdf directory: the failure was not reported: " + r.stderr[-1500:])
    require("Filename::touch ERROR" not in r.stderr,
            "logfile.pdf directory: a placeholder was attempted after the failed render")
    require((out / "logfile.pdf").is_dir() and (out / "batch.pdf").is_file()
            and (out / "Movies" / "a.mrc").stat().st_size > 0,
            "logfile.pdf directory: other products missing")
    print("PASS an unwritable logfile.pdf is reported without failing the job or terminating")


if __name__ == "__main__":
    sys.exit(main())
