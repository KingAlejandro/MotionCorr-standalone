#!/usr/bin/env python3
"""Split a movies STAR into N disjoint shards without re-serializing any metadata.

Each shard is the original file's bytes with the movie block's data rows replaced
by a contiguous slice of the original row bytes. The optics block, the version
comment, the loop header, the label lines and every column value are therefore
byte-identical to the input in every shard -- optics group, pixel size, voltage
and pre-exposure are preserved structurally rather than by a serializer.

Preflight, all fail-closed:

  * the input parses under the C++ reader's own semantics (see star_io.py);
  * no movie name appears twice in the input;
  * no two movies collapse to the same output root, which
    getOutputFileNames() would silently overwrite -- 'Movies/a.b/x.tif' and
    'Movies/a_b/x.tif' both become 'Movies/a_b/x.mrc';
  * every shard is non-empty;
  * the shards partition the input exactly: every row exactly once, in order;
  * each written shard re-parses to exactly the rows it was given.

Tomography input (data_global with rlnTomoTiltSeriesStarFile) is sharded by
whole tilt series: each shard keeps the global block's header and a contiguous
slice of its rows, and the per-series tables stay where they are. The manifest
records each series' table, the joint-STAR sidecar the runner will write for it,
and its movies in pre-exposure order, which is the canonical order the merge
validates against. Old-format input, a sidecar that would land on a reserved
name, a movie product or outside the output directory, and more shards than
series are refused.

Contiguous, not round-robin: which distribution balances load better is a
question for measurement, and this tool makes no such claim.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import posixpath
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import star_io  # noqa: E402


def contiguous_slices(total: int, n: int) -> list[tuple[int, int]]:
    """Blocks differing by at most one, mirroring divide_equally()."""
    base, extra = divmod(total, n)
    out, start = [], 0
    for k in range(n):
        size = base + (1 if k < extra else 0)
        out.append((start, start + size))
        start += size
    return out


def preflight(names: list[str]) -> list[str]:
    problems = []
    seen: dict[str, int] = {}
    for i, name in enumerate(names):
        if name in seen:
            problems.append(
                f"duplicate movie in input: {name!r} at rows {seen[name] + 1} and {i + 1}"
            )
        else:
            seen[name] = i

    # Fixed-name artifacts the runner writes into --o. A movie whose output root
    # plus a decoration lands on one of these is overwritten by, or overwrites,
    # a per-run product.
    reserved = {"gain", "corrected_micrographs", "corrected_tilt_series", "logfile",
                "header", "batch", "all_batches"}

    # Canonicalize exactly as the runner and the merger do, BEFORE any collision
    # or decoration check. '/a/x.tif' and 'a/x.tif' have different raw roots but
    # both land at 'a/x.*' beneath the worker output directory, so a raw-root
    # check passes them, the second silently overwrites the first, and the merge
    # then sees one surviving pair satisfying two movies -- PASS on corrupted
    # coverage.
    roots: dict[str, str] = {}
    for name in names:
        root = star_io.worker_relative_root(star_io.output_root(name))
        prior = roots.get(root)
        if prior is not None and prior != name:
            problems.append(
                f"output-name collision: {prior!r} and {name!r} both write {root}.mrc "
                "beneath the worker output directory (getOutputFileNames replaces '.' "
                "with '_' and concatenates onto --o, src/motioncorr_runner.cpp:553)"
            )
        roots.setdefault(root, name)

    plots = {}
    for name in names:
        try:
            plot = star_io.shift_plot_path(name)
        except ValueError as exc:
            problems.append(str(exc))
            continue
        if plot.startswith("_workers/"):
            problems.append(f"reserved-namespace collision: {name!r} writes {plot}")
        prior = plots.setdefault(plot, name)
        if prior != name:
            problems.append(f"shift-plot collision: {prior!r} and {name!r} both write {plot}")

    # merge_workers.py stages each worker's fixed-name aggregates under
    # <out>/_workers/w<k>/. A movie whose output root enters that namespace --
    # '_workers/w0/corrected_micrographs' -- is staged to the exact path worker
    # 0's own aggregate is copied to, and the aggregate wins, destroying the
    # per-movie metadata while `produced` still records the path and the merge
    # reports PASS. Such a name cannot be written unquoted, because the STAR
    # reader treats a leading '_' as a label, but a quoted one is accepted.
    for root, name in roots.items():
        if root == "_workers" or root.startswith("_workers/"):
            problems.append(
                f"reserved-namespace collision: {name!r} writes {root}.* into "
                "_workers/, which is where the merge stages each worker's "
                "fixed-name aggregates; the aggregate would overwrite it"
            )

    for root, name in roots.items():
        for decoration in star_io.OUTPUT_DECORATIONS:
            if (root + decoration) in reserved:
                problems.append(
                    f"reserved-name collision: {name!r} writes "
                    f"{root + decoration}.* into the output root, which is a "
                    "fixed-name per-run artifact"
                )

    # One movie's decorated output can be another movie's main output: with
    # --grouping_for_ps, movie 'a' writes a_PS.mrc, which is exactly movie
    # 'a_PS''s corrected image. Whichever runs second wins, silently.
    for root, name in roots.items():
        for decoration in star_io.OUTPUT_DECORATIONS:
            if not decoration:
                continue
            other = roots.get(root + decoration)
            if other is not None and other != name:
                problems.append(
                    f"decorated-output collision: {name!r} writes "
                    f"{root + decoration}.mrc under some options, which is "
                    f"{other!r}'s own output root"
                )
    return problems


def tomography_series(global_block: star_io.Block) -> tuple[list[dict], list[str]]:
    """Expand a tomography global table into per-series movie lists.

    Mirrors what each worker will do with its shard: TomogramSet::read resolves
    every rlnTomoTiltSeriesStarFile against the process cwd and reads block
    data_<rlnTomoName> (src/jaz/tomography/tomogram_set.cpp:84-99), and
    generateSingleMetaDataTable stable-sorts each table by pre-exposure
    (:797-803). The expanded order is therefore the order the joint per-series
    tables must list the corrected images in.
    """
    problems: list[str] = []
    try:
        name_col = global_block.column(star_io.TOMO_NAME_LABEL)
        ref_col = global_block.column(star_io.TOMO_STAR_LABEL)
    except star_io.StarFormatError as exc:
        # Without rlnTomoTiltSeriesStarFile the runner converts the old
        # relion-4.0 layout in memory; nothing here models that conversion.
        return [], [f"tomography input is not in the per-series-file format: {exc}"]

    series = []
    sidecars: dict[str, str] = {}
    for row in global_block.rows:
        name, ref = row.values[name_col], row.values[ref_col]
        post = star_io.pipeline_post(ref)
        sidecar = posixpath.normpath(post.lstrip("/")) if post.strip("/") else ""
        if not sidecar or sidecar == "." or sidecar == ".." or sidecar.startswith("../"):
            problems.append(f"tilt series {name!r}: per-series table {ref!r} would be "
                            "written outside the output directory")
            continue
        prior = sidecars.setdefault(sidecar, name)
        if prior != name:
            problems.append(f"tilt series {prior!r} and {name!r} both write {sidecar}")
            continue
        if sidecar == "corrected_tilt_series.star" or sidecar.startswith("_workers/") \
                or sidecar == "_workers":
            problems.append(f"tilt series {name!r}: {sidecar} is a reserved output path")
            continue
        try:
            # Workers and the aggregate step each reopen this table, and its
            # dose/tilt metadata reaches the published STAR without any
            # cross-check, so the merge revalidates this digest.
            ref_sha256 = hashlib.sha256(Path(ref).read_bytes()).hexdigest()
            table = star_io.parse(ref).block(name)
            movie_col = table.column(star_io.MOVIE_LABEL)
            pre_col = table.column(star_io.PRE_EXPOSURE_LABEL)
            if hashlib.sha256(Path(ref).read_bytes()).hexdigest() != ref_sha256:
                raise OSError("changed while it was being read")
        except (OSError, star_io.StarFormatError) as exc:
            problems.append(f"tilt series {name!r}: cannot read data_{name} from "
                            f"{ref!r} relative to {Path.cwd()}: {exc}")
            continue
        if not table.rows:
            problems.append(f"tilt series {name!r}: {ref!r} has no images")
            continue
        try:
            keyed = [(float(r.values[pre_col]), r.values[movie_col]) for r in table.rows]
        except ValueError as exc:
            problems.append(f"tilt series {name!r}: unreadable pre-exposure: {exc}")
            continue
        if any(not math.isfinite(k) for k, _ in keyed):
            problems.append(f"tilt series {name!r}: non-finite pre-exposure")
            continue
        # std::stable_sort with MdDoubleComparator: ties keep file order.
        movies = [m for _, m in sorted(keyed, key=lambda kv: kv[0])]
        series.append({"name": name, "ref": ref, "ref_path": str(Path(ref).resolve()),
                       "ref_sha256": ref_sha256, "sidecar": sidecar, "movies": movies})
    return series, problems


def sidecar_collisions(series: list[dict], names: list[str]) -> list[str]:
    """A per-series table written over a movie product, in a worker or the merge."""
    roots = {star_io.worker_relative_root(star_io.output_root(m)) for m in names}
    plots = {star_io.shift_plot_path(m) for m in names}
    problems = []
    for s in series:
        if s["sidecar"] in plots or star_io.split_output_path(s["sidecar"], roots):
            problems.append(f"tilt series {s['name']!r}: per-series table {s['sidecar']} "
                            "is also a movie product path")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--star", required=True, help="input movies STAR")
    ap.add_argument("--n", type=int, required=True, help="number of shards")
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--prefix", default="shard")
    ap.add_argument("--manifest", default=None,
                    help="where to write the assignment manifest "
                         "(default <outdir>/<prefix>_manifest.json)")
    ap.add_argument("--force", action="store_true",
                    help="overwrite an existing shard whose content differs; without "
                         "it, a differing shard is refused")
    a = ap.parse_args(argv)

    if a.n < 1:
        print(f"FAIL: --n must be >= 1, got {a.n}", file=sys.stderr)
        return 2

    src = Path(a.star)
    try:
        # One read: the manifest digest, the round-trip check and every shard
        # all describe this snapshot, even if the file is replaced meanwhile.
        data = src.read_bytes()
        star = star_io.parse(src, data)
        tomo = star_io.tomo_global_block(star)
        block = tomo if tomo is not None else star_io.movie_block(star)
    except star_io.StarFormatError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2

    a.input_sha256 = hashlib.sha256(data).hexdigest()
    if star.render() != data.decode():
        print("FAIL: parser did not round-trip the input byte for byte", file=sys.stderr)
        return 2
    return (partition_tomography(a, src, star, block) if tomo is not None
            else partition_movies(a, src, star, block))


def write_shard(a, outdir: Path, k: int, star: star_io.StarFile,
                block: star_io.Block, chunk: list) -> tuple[Path, str] | int:
    target = outdir / f"{a.prefix}_{a.n}way_{k}.star"
    content = star.render_with_rows(block, chunk)
    if target.exists() and target.read_bytes().decode() != content and not a.force:
        print(f"FAIL: {target} exists and differs from the shard this input "
              "produces; refusing to overwrite", file=sys.stderr)
        return 4
    target.write_text(content)

    # Round-trip: the shard the worker will read must parse back to exactly
    # the rows assigned to it, with the same bytes and the same tokens.
    back = star_io.parse(target)
    back_block = (star_io.tomo_global_block(back) if block.name == star_io.TOMO_GLOBAL_BLOCK
                  else star_io.movie_block(back))
    if back_block is None:
        print(f"FAIL: {target} lost its data_global rows", file=sys.stderr)
        return 5
    if [r.raw for r in back_block.rows] != [r.raw for r in chunk] or \
       [r.values for r in back_block.rows] != [r.values for r in chunk]:
        print(f"FAIL: {target} did not round-trip its assigned rows", file=sys.stderr)
        return 5
    if back_block.labels != block.labels:
        print(f"FAIL: {target} label set differs from the input", file=sys.stderr)
        return 5
    return target, content


def report_preflight(problems: list[str]) -> int:
    print(f"FAIL: {len(problems)} preflight problem(s):", file=sys.stderr)
    for p in problems:
        print(f"  {p}", file=sys.stderr)
    return 3


def roots_of(movies: list[str]) -> list[str]:
    return [star_io.worker_relative_root(star_io.output_root(m)) for m in movies]


def finish(a, src: Path, block: star_io.Block, canonical: list[str], shards: list[dict],
           extra: dict) -> int:
    assigned = [m for s in shards for m in s["movies"]]
    if assigned != canonical:
        print("FAIL: shards do not reproduce the canonical movie order exactly",
              file=sys.stderr)
        return 5
    outdir = Path(a.outdir)
    manifest = {
        "input_star": str(src),
        "input_sha256": a.input_sha256,
        "movie_block": block.name,
        "labels": block.labels,
        "n_movies": len(canonical),
        "n_shards": a.n,
        "partition": "contiguous",
        "canonical_movies": canonical,
        "canonical_output_roots": roots_of(canonical),
        "shards": shards,
        **extra,
    }
    mpath = Path(a.manifest) if a.manifest else outdir / f"{a.prefix}_manifest.json"
    mpath.write_text(json.dumps(manifest, indent=2) + "\n")

    for s in shards:
        print(f"{s['path']}\t{s['n_movies']}")
    print(f"manifest\t{mpath}")
    print(f"TOTAL\t{len(canonical)}", file=sys.stderr)
    return 0


def partition_tomography(a, src: Path, star: star_io.StarFile,
                         block: star_io.Block) -> int:
    """Shard whole tilt series: the global table's rows, contiguously.

    A tilt series cannot be split, because each worker regenerates its
    per-series table from the series it was given. The manifest's canonical
    movie order is series order, then pre-exposure within each series.
    """
    if a.n > len(block.rows):
        print(f"FAIL: {a.n} shards requested for {len(block.rows)} tilt series; an "
              "empty shard would make a worker claim a device and process nothing",
              file=sys.stderr)
        return 2
    series, problems = tomography_series(block)
    if problems:
        return report_preflight(problems)
    canonical = [m for s in series for m in s["movies"]]
    problems = preflight(canonical) or sidecar_collisions(series, canonical)
    if problems:
        return report_preflight(problems)

    outdir = Path(a.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    shards = []
    for k, (lo, hi) in enumerate(contiguous_slices(len(block.rows), a.n)):
        written = write_shard(a, outdir, k, star, block, block.rows[lo:hi])
        if isinstance(written, int):
            return written
        target, content = written
        mine = series[lo:hi]
        movies = [m for s in mine for m in s["movies"]]
        shards.append({
            "index": k,
            "path": str(target),
            "sha256": hashlib.sha256(content.encode()).hexdigest(),
            "n_movies": len(movies),
            "first_input_row": lo,
            "movies": movies,
            "output_roots": roots_of(movies),
            "series": [s["name"] for s in mine],
            "sidecars": [s["sidecar"] for s in mine],
        })
    return finish(a, src, block, canonical, shards,
                  {"input_type": "tomography", "tomography": {"series": series}})


def partition_movies(a, src: Path, star: star_io.StarFile, block: star_io.Block) -> int:
    rows = block.rows
    if not rows:
        print(f"FAIL: {src} has no movie rows", file=sys.stderr)
        return 2
    if a.n > len(rows):
        print(f"FAIL: {a.n} shards requested for {len(rows)} movies; an empty shard "
              "would make a worker claim a device and process nothing", file=sys.stderr)
        return 2

    names_col = block.column(star_io.MOVIE_LABEL)
    canonical = [r.values[names_col] for r in rows]
    problems = preflight(canonical)
    if problems:
        return report_preflight(problems)

    outdir = Path(a.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    shards = []
    for k, (lo, hi) in enumerate(contiguous_slices(len(rows), a.n)):
        chunk = rows[lo:hi]
        written = write_shard(a, outdir, k, star, block, chunk)
        if isinstance(written, int):
            return written
        target, content = written
        movies = [r.values[names_col] for r in chunk]
        shards.append({
            "index": k,
            "path": str(target),
            "sha256": hashlib.sha256(content.encode()).hexdigest(),
            "n_movies": len(chunk),
            "first_input_row": lo,
            "movies": movies,
            "output_roots": roots_of(movies),
        })
    return finish(a, src, block, canonical, shards, {"input_type": "spa"})


if __name__ == "__main__":
    sys.exit(main())
