#!/usr/bin/env python3
"""A stand-in for the MotionCorr binary, for scheduling tests without a GPU.

It accepts the argument subset the launcher passes (--i, --o,
--only_do_unfinished, --gpu, and anything else it ignores) and reproduces the
output-naming and fixed-name-aggregate behaviour the scheduler has to cope with:

  * per movie, <out>/<root>.mrc and <out>/<root>.star, where <root> is the movie
    path with its extension dropped and every remaining '.' turned into '_',
    matching getOutputFileNames() (src/motioncorr_runner.cpp:553);
  * the per-movie STAR carries the movie name, optics group and pre-exposure it
    was given, so a test can prove metadata survived partitioning rather than
    only that a file appeared;
  * the fixed-name aggregates every real process writes, so the merge has
    something real to have to skip;
  * --only_do_unfinished skips a movie whose products already exist, which is
    what makes a non-prefix resume testable.

Fault injection makes the failure paths observable: a worker can drop a movie,
claim one it was not assigned, exit non-zero, or kill itself part-way through.
These exist so the guards can be shown to fire, not merely to be present.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "multi_gpu"))
import star_io  # noqa: E402

PRODUCTS = (".mrc", ".star")


def star_quote(value: str) -> str:
    """The subset of escapeStringForSTAR (src/strings.cpp:88) these fixtures need.

    A path containing whitespace must be quoted, or the reader sees extra
    columns. Embedded quotes are not produced by any fixture here, and the \a
    escaping the C++ writer would emit for them does not survive its own reader
    (see tools/multi_gpu/star_io.py), so it is deliberately not imitated.
    """
    if value == "":
        return '""'
    if value[0] in ('"', "'") or any(c in value for c in " \t"):
        return '"' + value + '"'
    return value


def write_products(outdir: Path, movie: str, optics: str, pre_exposure: str,
                   truncate_mrc: bool = False, marker: str = "") -> None:
    # getOutputFileNames is plain string concatenation, fn_out + fn_root
    # (src/motioncorr_runner.cpp:553-573), so an absolute movie name lands at
    # <out>//abs/path.mrc -- i.e. worker-relative abs/path.mrc. Joining an
    # absolute root with pathlib would instead escape --o entirely and write
    # outside the worker directory.
    root = star_io.worker_relative_root(star_io.output_root(movie))
    mrc = outdir / (root + ".mrc")
    mrc.parent.mkdir(parents=True, exist_ok=True)
    # Not a real MRC; the CPU fixtures never read pixels. Content is a stable
    # function of the movie so a duplicate or a swap is detectable by bytes.
    mrc.write_text(f"FAKEMRC {movie}{marker}\n" if not truncate_mrc else "FAKEMRC")
    (outdir / (root + ".star")).write_text(json.dumps({
        "rlnMicrographMovieName": movie,
        "rlnOpticsGroup": optics,
        "rlnMicrographPreExposure": pre_exposure,
    }, sort_keys=True) + "\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--i", dest="inp", required=True)
    ap.add_argument("--o", dest="out", required=True)
    ap.add_argument("--only_do_unfinished", action="store_true")
    ap.add_argument("--aggregate_only", action="store_true")
    ap.add_argument("--fake_missing_report", action="store_true")
    ap.add_argument("--gpu", default=None)
    ap.add_argument("--fake_skip", default=None,
                    help="comma-separated movie names to silently not produce")
    ap.add_argument("--fake_extra", default=None,
                    help="comma-separated movie names to produce although unassigned")
    ap.add_argument("--fake_fail_rc", type=int, default=0)
    ap.add_argument("--fake_die_after", type=int, default=None,
                    help="SIGKILL self after producing this many movies")
    ap.add_argument("--fake_truncate", default=None,
                    help="comma-separated movie names whose .mrc is written short")
    ap.add_argument("--fake_reverse_aggregate", action="store_true",
                    help="emit the aggregate STAR rows in reverse order")
    ap.add_argument("--fake_reprocess", action="store_true",
                    help="ignore --only_do_unfinished and rewrite every movie with "
                         "different bytes. Stands in for the real binary judging a "
                         "staged product incomplete because the option set it was "
                         "given does not match the one the workers ran under "
                         "(isMovieComplete is option-dependent, and since PR110 also "
                         "frame-count dependent).")
    ap.add_argument("--fake_sleep_per_movie", type=float, default=0.0,
                    help="sleep this long after each movie. With uneven shards the "
                         "workers then finish at genuinely different times, which is "
                         "what makes the launcher's final-worker tail observable.")
    ap.add_argument("--fake_note", default=None,
                    help="write this text to <out>/note.txt; used to prove that extra "
                         "arguments actually reached the process rather than being "
                         "silently dropped by the caller's argument handling")
    a, _unknown = ap.parse_known_args(argv)

    outdir = Path(a.out)
    outdir.mkdir(parents=True, exist_ok=True)
    star = star_io.parse(a.inp)
    block = star_io.movie_block(star)
    name_col = block.column(star_io.MOVIE_LABEL)
    try:
        optics_col = block.column(star_io.OPTICS_GROUP_LABEL)
    except star_io.StarFormatError:
        optics_col = None
    try:
        pre_col = block.column("rlnMicrographPreExposure")
    except star_io.StarFormatError:
        pre_col = None

    skip = set((a.fake_skip or "").split(",")) - {""}
    truncate = set((a.fake_truncate or "").split(",")) - {""}
    done = 0
    processed = []
    for row in block.rows:
        movie = row.values[name_col]
        if movie in skip:
            continue
        root = star_io.worker_relative_root(star_io.output_root(movie))
        if ((a.only_do_unfinished or a.aggregate_only) and not a.fake_reprocess
                and all((outdir / (root + s)).exists() for s in PRODUCTS)):
            continue
        write_products(outdir, movie,
                       row.values[optics_col] if optics_col is not None else "",
                       row.values[pre_col] if pre_col is not None else "",
                       truncate_mrc=movie in truncate,
                       marker=" REPROCESSED" if a.fake_reprocess else "")
        processed.append(movie)
        done += 1
        if a.fake_sleep_per_movie:
            time.sleep(a.fake_sleep_per_movie)
        if a.fake_die_after is not None and done >= a.fake_die_after:
            sys.stdout.flush()
            os.kill(os.getpid(), signal.SIGKILL)

    for movie in (a.fake_extra or "").split(","):
        if movie:
            write_products(outdir, movie, "", "")

    # The fixed-name aggregates every real process writes into its --o.
    roots = [star_io.output_root(m) for m in
             (r.values[name_col] for r in block.rows)
             if (outdir / (star_io.worker_relative_root(
                 star_io.output_root(m)) + ".mrc")).exists()]
    lines = ["\n", "data_micrographs\n", "\n", "loop_\n",
             "_rlnMicrographName #1\n", "_rlnMicrographMetadata #2\n"]
    # The aggregate rows carry what the binary serializes: fn_out + fn_root,
    # concatenated, leading slash and all (src/motioncorr_runner.cpp:572).
    for root in (reversed(roots) if a.fake_reverse_aggregate else roots):
        prefix = str(outdir) if str(outdir).endswith(os.sep) else str(outdir) + os.sep
        lines.append(f"{star_quote(prefix + root + '.mrc')} "
                     f"{star_quote(prefix + root + '.star')}\n")
    lines.append("\n")
    (outdir / "corrected_micrographs.star").write_text("".join(lines))
    if not a.fake_missing_report:
        (outdir / "logfile.pdf").write_text("%PDF-1.4 fake\n%%EOF\n")
    (outdir / "logfile.pdf.lst").write_text("fake\n")
    (outdir / "corrected_micrographs_all_accum.eps").write_text("%!PS fake\n")

    if a.fake_note is not None:
        (outdir / "note.txt").write_text(a.fake_note + "\n")

    print(f"fake_worker processed {len(processed)} movie(s) into {outdir}")
    return a.fake_fail_rc


if __name__ == "__main__":
    sys.exit(main())
