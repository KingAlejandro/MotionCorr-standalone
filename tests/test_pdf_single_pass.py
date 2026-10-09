#!/usr/bin/env python3
"""logfile.pdf in one Ghostscript pass, and the fallback to the old concatenation.

generateLogFilePDFAndWriteStarFiles() used to render header.pdf and batch.pdf
and then re-encode the two into logfile.pdf (header.pdf + all_batches.pdf),
a third Ghostscript pass that started only after the first two had finished.
With no earlier batches (a fresh output directory), all_batches.pdf is
batch.pdf, so logfile.pdf is the header EPS list followed by the batch EPS
list. The runner now renders that in one pdfwrite pass over both lists,
concurrently with the other two passes (docs/pdf_tail.md).

A `gs` shim at the front of PATH logs every invocation and runs the real
Ghostscript, so the test sees which passes ran. Arms:

  fresh     one pass over @header.pdf.lst @batch.pdf.lst, no header+all_batches
            concatenation; logfile.pdf rasterises (png16m, 150 dpi, every page)
            identically to the original concatenation of the header.pdf and
            all_batches.pdf this run wrote; no scratch file is left behind.
  rerun     an existing all_batches.pdf is prepended as before, so the single
            pass is not used, the concatenation is, and the page count grows.
  fault     the shim fails the single pass, leaving a truncated PDF as a
            Ghostscript that dies part-way would: the job still succeeds, the
            concatenation produces the same pages and no scratch file is left.

Running this against a binary without the change fails the `fresh` arm; the
compiled mutant that ignores the single pass exit status fails only the `fault` arm, which
--expect-fault-failure asserts (PdfSinglePassMutant_ignore_status).
"""
from __future__ import annotations
import argparse
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

ARGS = ["--use_own", "--j", "1", "--skip_defect", "--angpix", "1.0",
        "--voltage", "300", "--patch_x", "1", "--patch_y", "1", "--bfactor", "150"]

STAR = """# version 30001

data_optics

loop_
_rlnOpticsGroupName #1
_rlnOpticsGroup #2
_rlnMicrographOriginalPixelSize #3
_rlnVoltage #4
_rlnSphericalAberration #5
_rlnAmplitudeContrast #6
opticsGroup1 1 1.0 300 2.7 0.1

# version 30001

data_movies

loop_
_rlnMicrographMovieName #1
_rlnOpticsGroup #2
Movies/a.tiff 1
Movies/b.tiff 1
"""

SHIM = """#!/bin/sh
printf '%s\\n' "$*" >> "{log}"
if [ -n "$MC_TEST_FAIL_SINGLE" ]; then
  for arg in "$@"; do
    case "$arg" in
      -sOutputFile=*logfile_tmp_single.pdf)
        # A Ghostscript that dies part-way: a truncated PDF and a failure.
        printf '%%PDF-1.7\n%%truncated\n' > "${{arg#-sOutputFile=}}"
        exit 1 ;;
    esac
  done
fi
exec "{real}" "$@"
"""

TIMEOUT = 600


def run_gs(real_gs: str, args: list[str]) -> None:
    subprocess.run([real_gs, *args], check=True, timeout=TIMEOUT,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def raster(real_gs: str, pdf: Path, dest: Path) -> list[bytes]:
    """Every page at 150 dpi. A damaged PDF yields fewer (or no) pages rather
    than an exception, so the caller's page comparison reports it."""
    dest.mkdir(parents=True)
    subprocess.run([real_gs, "-q", "-sDEVICE=png16m", "-r150", "-dNOPAUSE", "-dBATCH", "-dSAFER",
                    f"-sOutputFile={dest}/p%04d.png", str(pdf)], timeout=TIMEOUT,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return [p.read_bytes() for p in sorted(dest.glob("p*.png"))]


def reference_concat(real_gs: str, out: Path, dest: Path) -> Path:
    """The original logfile pass: concatenate header.pdf and all_batches.pdf."""
    ref = dest / "reference_logfile.pdf"
    run_gs(real_gs, ["-dNOPAUSE", "-sDEVICE=pdfwrite", f"-sOUTPUTFILE={ref}", "-dBATCH",
                     str(out / "header.pdf"), str(out / "all_batches.pdf")])
    return ref


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--binary", type=Path, required=True)
    ap.add_argument("--expect-fault-failure", action="store_true",
                    help="negative control: pass only if the fresh and rerun arms pass "
                         "and the fault arm fails")
    a = ap.parse_args()
    real_gs = shutil.which("gs")
    if real_gs is None:
        print("SKIP: Ghostscript is not installed")
        return 77
    repo = Path(__file__).resolve().parent.parent
    fixture = repo / "test-data" / "synthetic" / "synthetic_movie.tiff"
    if not fixture.is_file():
        print(f"FAIL: fixture missing: {fixture}")
        return 1

    failures: list[str] = []
    arm = ["fresh"]

    def check(ok: bool, message: str) -> None:
        print(("PASS: " if ok else "FAIL: ") + message)
        if not ok:
            failures.append(f"{arm[0]}: {message}")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "Movies").mkdir()
        shutil.copy(fixture, tmp / "Movies" / "a.tiff")
        shutil.copy(fixture, tmp / "Movies" / "b.tiff")
        (tmp / "in.star").write_text(STAR)
        shim_dir = tmp / "shim"
        shim_dir.mkdir()
        log = tmp / "gs.log"
        (shim_dir / "gs").write_text(SHIM.format(log=log, real=real_gs))
        (shim_dir / "gs").chmod(0o755)

        def job(out: Path, fail_single: bool = False):
            log.write_text("")
            env = dict(os.environ)
            env["PATH"] = f"{shim_dir}{os.pathsep}{env.get('PATH', '')}"
            if fail_single:
                env["MC_TEST_FAIL_SINGLE"] = "1"
            else:
                env.pop("MC_TEST_FAIL_SINGLE", None)
            res = subprocess.run([str(a.binary.resolve()), "--i", "in.star", "--o", str(out) + "/"] + ARGS,
                                 cwd=tmp, capture_output=True, text=True, timeout=TIMEOUT, env=env)
            return res, log.read_text().splitlines()

        def single_pass_lines(calls: list[str]) -> list[str]:
            return [c for c in calls if "logfile_tmp_single.pdf" in c]

        def concat_lines(calls: list[str]) -> list[str]:
            return [c for c in calls if "header.pdf " in c and "all_batches.pdf" in c and "-sOUTPUTFILE=" in c]

        # ---- fresh output directory -------------------------------------
        out = tmp / "fresh"
        res, calls = job(out)
        check(res.returncode == 0, f"fresh run exits 0 (got {res.returncode}): {res.stderr[-800:]}")
        if res.returncode != 0:
            return 1
        single = single_pass_lines(calls)
        check(len(single) == 1 and single[0].endswith(f"@{out}/header.pdf.lst @{out}/batch.pdf.lst"),
              "fresh run renders logfile.pdf in one pass over @header.pdf.lst @batch.pdf.lst")
        check(not concat_lines(calls), "fresh run does not re-encode header.pdf + all_batches.pdf")
        for name in ("header.pdf", "batch.pdf", "all_batches.pdf", "logfile.pdf"):
            p = out / name
            check(p.is_file() and p.stat().st_size > 0 and p.read_bytes()[:5] == b"%PDF-",
                  f"fresh run writes {name}")
        check(not (out / "logfile_tmp_single.pdf").exists(), "fresh run leaves no scratch file")
        ref = reference_concat(real_gs, out, tmp / "ref-fresh")
        got = raster(real_gs, out / "logfile.pdf", tmp / "r-fresh-got")
        want = raster(real_gs, ref, tmp / "r-fresh-want")
        header_pages = len(raster(real_gs, out / "header.pdf", tmp / "r-fresh-header"))
        batch_pages = len(raster(real_gs, out / "batch.pdf", tmp / "r-fresh-batch"))
        check(len(got) == len(want) == header_pages + batch_pages and batch_pages == 2,
              f"fresh logfile.pdf has header+batch pages ({len(got)} vs reference {len(want)}, "
              f"header {header_pages}, batch {batch_pages})")
        check(got == want, "fresh logfile.pdf pages are pixel-identical (150 dpi) to the original concatenation")

        # ---- rerun into the same directory: all_batches.pdf accumulates --
        arm[0] = "rerun"
        res, calls = job(out)
        check(res.returncode == 0, f"rerun exits 0 (got {res.returncode})")
        check(not single_pass_lines(calls), "rerun with an existing all_batches.pdf does not use the single pass")
        check(len(concat_lines(calls)) == 1, "rerun concatenates header.pdf + all_batches.pdf as before")
        allb = len(raster(real_gs, out / "all_batches.pdf", tmp / "r-rerun-allb"))
        got = raster(real_gs, out / "logfile.pdf", tmp / "r-rerun-got")
        want = raster(real_gs, reference_concat(real_gs, out, tmp / "ref-rerun"), tmp / "r-rerun-want")
        check(allb == 2 * batch_pages, f"rerun prepends the earlier all_batches.pdf ({allb} pages)")
        check(got == want and len(got) == header_pages + allb,
              "rerun logfile.pdf is header.pdf + accumulated all_batches.pdf")

        # ---- the single pass fails: fall back to the concatenation -------
        arm[0] = "fault"
        out = tmp / "fault"
        res, calls = job(out, fail_single=True)
        check(res.returncode == 0, f"a failed single pass does not fail the job (exit {res.returncode})")
        check(len(single_pass_lines(calls)) == 1, "fault arm attempted the single pass")
        check(len(concat_lines(calls)) == 1, "a failed single pass falls back to the concatenation")
        check(not (out / "logfile_tmp_single.pdf").exists(), "fault arm leaves no scratch file")
        if (out / "logfile.pdf").is_file():
            got = raster(real_gs, out / "logfile.pdf", tmp / "r-fault-got")
            want = raster(real_gs, reference_concat(real_gs, out, tmp / "ref-fault"), tmp / "r-fault-want")
            check(got == want and len(got) == header_pages + batch_pages,
                  "fault arm logfile.pdf matches the original concatenation")
        else:
            check(False, "fault arm wrote logfile.pdf")

    if a.expect_fault_failure:
        others = [f for f in failures if not f.startswith("fault: ")]
        fault = [f for f in failures if f.startswith("fault: ")]
        if others or not fault:
            print(f"FAIL: negative control expected only fault-arm failures; got {failures}")
            return 1
        print(f"negative control: the fault arm failed as expected ({len(fault)} check(s))")
        return 0
    if failures:
        print(f"{len(failures)} check(s) failed")
        return 1
    print("pdf single pass: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
