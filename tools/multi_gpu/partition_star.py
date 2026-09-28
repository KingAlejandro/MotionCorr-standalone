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

Contiguous, not round-robin: which distribution balances load better is a
question for measurement, and this tool makes no such claim.
"""

from __future__ import annotations

import argparse
import hashlib
import json
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


def preflight(star: star_io.StarFile, block: star_io.Block) -> list[str]:
    names_col = block.column(star_io.MOVIE_LABEL)
    names = [r.values[names_col] for r in block.rows]

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
    reserved = {"gain", "corrected_micrographs", "logfile", "header", "batch",
                "all_batches"}

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
                "with '_' and concatenates onto --o, src/motioncorr_runner.cpp:491)"
            )
        roots.setdefault(root, name)

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
        star = star_io.parse(src)
        block = star_io.movie_block(star)
    except star_io.StarFormatError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2

    if star.render() != src.read_bytes().decode():
        print("FAIL: parser did not round-trip the input byte for byte", file=sys.stderr)
        return 2

    rows = block.rows
    if not rows:
        print(f"FAIL: {src} has no movie rows", file=sys.stderr)
        return 2
    if a.n > len(rows):
        print(f"FAIL: {a.n} shards requested for {len(rows)} movies; an empty shard "
              "would make a worker claim a device and process nothing", file=sys.stderr)
        return 2

    problems = preflight(star, block)
    if problems:
        print(f"FAIL: {len(problems)} preflight problem(s):", file=sys.stderr)
        for p in problems:
            print(f"  {p}", file=sys.stderr)
        return 3

    outdir = Path(a.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    names_col = block.column(star_io.MOVIE_LABEL)

    shards = []
    for k, (lo, hi) in enumerate(contiguous_slices(len(rows), a.n)):
        chunk = rows[lo:hi]
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
        back_block = star_io.movie_block(back)
        if [r.raw for r in back_block.rows] != [r.raw for r in chunk] or \
           [r.values for r in back_block.rows] != [r.values for r in chunk]:
            print(f"FAIL: {target} did not round-trip its assigned rows", file=sys.stderr)
            return 5
        if back_block.labels != block.labels:
            print(f"FAIL: {target} label set differs from the input", file=sys.stderr)
            return 5

        shards.append({
            "index": k,
            "path": str(target),
            "sha256": hashlib.sha256(content.encode()).hexdigest(),
            "n_movies": len(chunk),
            "first_input_row": lo,
            "movies": [r.values[names_col] for r in chunk],
            "output_roots": [star_io.worker_relative_root(
                star_io.output_root(r.values[names_col])) for r in chunk],
        })

    assigned = [m for s in shards for m in s["movies"]]
    canonical = [r.values[names_col] for r in rows]
    if assigned != canonical:
        print("FAIL: shards do not reproduce the canonical movie order exactly",
              file=sys.stderr)
        return 5

    manifest = {
        "input_star": str(src),
        "input_sha256": hashlib.sha256(src.read_bytes()).hexdigest(),
        "movie_block": block.name,
        "labels": block.labels,
        "n_movies": len(rows),
        "n_shards": a.n,
        "partition": "contiguous",
        "canonical_movies": canonical,
        "canonical_output_roots": [
            star_io.worker_relative_root(star_io.output_root(m)) for m in canonical],
        "shards": shards,
    }
    mpath = Path(a.manifest) if a.manifest else outdir / f"{a.prefix}_manifest.json"
    mpath.write_text(json.dumps(manifest, indent=2) + "\n")

    for s in shards:
        print(f"{s['path']}\t{s['n_movies']}")
    print(f"manifest\t{mpath}")
    print(f"TOTAL\t{len(rows)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
