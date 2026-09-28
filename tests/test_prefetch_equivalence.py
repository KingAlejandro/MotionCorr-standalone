#!/usr/bin/env python3
"""Bounded next-movie prefetch (#94) must change timing, never results.

The prefetch producer moves the geometry probe, the frame selection and the
frame decode of movie N+1 onto a second thread while movie N is corrected. The
only acceptable observable difference is speed, so every case here runs the
same movies twice -- once serial, once prefetched -- and requires identical
corrected pixels, identical global shifts and an identical frame selection.

The MRC label area carries a wall-clock timestamp, so whole-file hashes cannot
be compared; pixel payloads are compared instead (the same normalization the
rest of the suite uses).

Cases, with the control that proves the comparison can fail:
  normal      default automatic budget, several movies
  mixed       different geometries and frame counts in one run
  tight       budget exactly one movie: the producer is blocked nearly always
  starved     budget below any movie: every movie takes the in-line fallback
  gain        gain reference applied, prefetched
  frames      --first_frame_sum/--last_frame_sum selection, prefetched
  damaged     damaged first and damaged last movie, against serial behaviour
  resume      --only_do_unfinished with a non-prefix gap already done
  control     a deliberately different run must NOT compare equal
"""
import argparse
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

NX, NY, NFRAMES = 64, 48, 8


def write_mrc(path: Path, frames, nx, ny):
    flat = [v for f in frames for v in f]
    nz = len(frames)
    h = bytearray(1024)
    struct.pack_into("<3i", h, 0, nx, ny, nz)
    struct.pack_into("<i", h, 12, 2)                       # mode 2 = float32
    struct.pack_into("<3i", h, 28, nx, ny, nz)
    struct.pack_into("<3f", h, 40, float(nx), float(ny), float(nz))
    struct.pack_into("<3f", h, 52, 90.0, 90.0, 90.0)
    struct.pack_into("<3i", h, 64, 1, 2, 3)
    struct.pack_into("<3f", h, 76, min(flat), max(flat), sum(flat) / len(flat))
    h[208:212] = b"MAP "
    struct.pack_into("<i", h, 212, 0x00004144)
    with open(path, "wb") as fh:
        fh.write(bytes(h))
        fh.write(struct.pack(f"<{len(flat)}f", *flat))


def write_star(path: Path, movies):
    path.write_text(
        "# version 30001\n\ndata_optics\n\nloop_\n"
        "_rlnOpticsGroupName #1\n_rlnOpticsGroup #2\n"
        "_rlnMicrographOriginalPixelSize #3\n_rlnVoltage #4\n"
        "_rlnSphericalAberration #5\n_rlnAmplitudeContrast #6\n"
        "opticsGroup1 1 1.000 300.0 2.7 0.1\n\n"
        "# version 30001\n\ndata_movies\n\nloop_\n"
        "_rlnMicrographMovieName #1\n_rlnOpticsGroup #2\n"
        + "\n".join(f"{m} 1" for m in movies) + "\n"
    )


def synthetic_frames(seed, nx, ny, nframes, drift=1):
    """A drifting blob on a textured background, deterministic without numpy."""
    state = seed
    def rnd():
        nonlocal state
        state = (state * 1103515245 + 12345) & 0x7FFFFFFF
        return state / 0x7FFFFFFF
    base = [rnd() * 50.0 + 100.0 for _ in range(nx * ny)]
    frames = []
    for n in range(nframes):
        f = list(base)
        cx, cy = nx // 2 + n * drift, ny // 2 + (n % 2)
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                x, y = cx + dx, cy + dy
                if 0 <= x < nx and 0 <= y < ny:
                    f[y * nx + x] += 400.0 / (1.0 + dx * dx + dy * dy)
        frames.append(f)
    return frames


def read_mrc_pixels(path: Path) -> bytes:
    """Pixel bytes only: the MRC label area carries a wall-clock timestamp."""
    data = path.read_bytes()
    nx, ny, nz, mode = struct.unpack("<4i", data[:16])
    if mode != 2:
        raise ValueError(f"Unsupported MRC mode: {mode}")
    return data[1024:1024 + nx * ny * nz * 4]


def read_star_body(path: Path) -> str:
    """STAR text with comment lines dropped, so version banners do not matter."""
    return "\n".join(l.rstrip() for l in path.read_text().splitlines()
                     if not l.strip().startswith("#"))


def frames_line(log: Path) -> str:
    for line in log.read_text().splitlines():
        if line.startswith("Frames to be used:"):
            return line.strip()
    raise AssertionError(f"no frame selection line in {log}")


def run(binary, star, out_dir, extra=(), expect_ok=True):
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [str(binary.resolve()), "--i", star.name, "--o", str(out_dir) + "/", "--use_own",
           "--j", "2", "--skip_defect", "--seed", "1", "--angpix", "1.0", "--voltage", "300",
           "--patch_x", "1", "--patch_y", "1", "--bfactor", "150", *extra]
    res = subprocess.run(cmd, cwd=str(star.parent), capture_output=True, text=True)
    if expect_ok and res.returncode != 0:
        print("CMD:", " ".join(cmd))
        print("STDOUT:\n", res.stdout[-4000:])
        print("STDERR:\n", res.stderr[-4000:])
        raise RuntimeError(f"motioncorr failed ({res.returncode})")
    return res


def products(out_dir: Path):
    """Corrected images keyed by name, excluding the gain copy the runner writes."""
    return {p.name: read_mrc_pixels(p)
            for p in sorted(out_dir.glob("**/*.mrc")) if p.name != "gain.mrc"}


def stars(out_dir: Path):
    return {p.name: read_star_body(p) for p in sorted(out_dir.glob("**/*.star"))}


def logs(out_dir: Path):
    return {p.name: frames_line(p) for p in sorted(out_dir.glob("**/*.log"))}


def parse_prefetch_stats(stdout: str) -> dict:
    stats = {}
    for key, value in re.findall(r"(\w+) = (-?[\d.]+(?:[eE][+-]?\d+)?)", stdout):
        if key in stats:
            continue
        stats[key] = float(value) if "." in value or "e" in value.lower() else int(value)
    return stats


def assert_same(label, serial_dir, prefetch_dir):
    a, b = products(serial_dir), products(prefetch_dir)
    assert set(a) == set(b), f"{label}: different output sets\n  serial={sorted(a)}\n  prefetch={sorted(b)}"
    assert a, f"{label}: no corrected images at all -- the comparison would be vacuous"
    for name in sorted(a):
        assert len(a[name]) > 0, f"{label}: {name} has no pixels"
        assert a[name] == b[name], f"{label}: corrected pixels differ for {name}"
    sa, sb = stars(serial_dir), stars(prefetch_dir)
    assert set(sa) == set(sb), f"{label}: different STAR sets"
    for name in sorted(sa):
        assert sa[name] == sb[name], f"{label}: STAR metadata differs for {name}"
    la, lb = logs(serial_dir), logs(prefetch_dir)
    assert la == lb, f"{label}: frame selection differs\n  serial={la}\n  prefetch={lb}"
    return len(a)


def build_movies(tmp: Path):
    movies = tmp / "Movies"
    movies.mkdir(exist_ok=True)
    names = []
    for i in range(4):
        name = f"mov{i}.mrcs"
        write_mrc(movies / name, synthetic_frames(11 + i, NX, NY, NFRAMES), NX, NY)
        names.append(f"Movies/{name}")
    return names


def case_equivalence(binary, tmp, label, names, extra_prefetch, star_name, out_suffix,
                     serial_extra=()):
    star = tmp / star_name
    write_star(star, names)
    serial_dir = tmp / f"serial_{out_suffix}"
    prefetch_dir = tmp / f"prefetch_{out_suffix}"
    run(binary, star, serial_dir, extra=serial_extra)
    res = run(binary, star, prefetch_dir, extra=tuple(serial_extra) + tuple(extra_prefetch))
    count = assert_same(label, serial_dir, prefetch_dir)
    stats = parse_prefetch_stats(res.stdout)
    return count, stats, res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--binary", type=Path, required=True)
    args = ap.parse_args()
    repo = Path(__file__).resolve().parent.parent

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        names = build_movies(tmp)

        # --- normal: automatic budget --------------------------------------
        count, stats, res = case_equivalence(
            args.binary, tmp, "normal", names, ["--prefetch"], "all.star", "normal")
        assert count == 4, f"expected 4 corrected images, got {count}"
        assert stats.get("decoded") == 4, f"prefetch did not decode all movies: {stats}"
        assert stats.get("inline_loaded") == 0, f"unexpected in-line fallback: {stats}"
        assert stats.get("failed") == 0, f"unexpected failure: {stats}"
        assert stats.get("forced_grants") == 0, f"unexpected budget override: {stats}"
        assert stats.get("peak_reserved_bytes", 0) <= stats.get("budget_bytes", 0), \
            f"the declared byte bound was exceeded: {stats}"
        # Sanity, not a control: peak occupancy is >= 1 for any published record.
        # The real control for "this test can fail" is the B-factor case below.
        assert stats.get("peak_queue_occupancy", 0) >= 1, \
            f"nothing was ever published through the queue: {stats}"
        print(f"  normal:  4/4 movies identical; budget={stats['budget_bytes']} B, "
              f"peak_reserved={stats['peak_reserved_bytes']} B, "
              f"peak_queue={stats['peak_queue_occupancy']}")

        # --- control: the comparison must be able to fail -------------------
        # Same inputs, one deliberately different option. If this compares
        # equal, every equality above is vacuous.
        ctl_star = tmp / "all.star"
        ctl_dir = tmp / "control_bfactor"
        run(args.binary, ctl_star, ctl_dir, extra=["--prefetch", "--bfactor", "400"])
        base = products(tmp / "serial_normal")
        ctl = products(ctl_dir)
        assert set(base) == set(ctl), "control produced a different output set"
        assert any(base[n] != ctl[n] for n in base), (
            "CONTROL FAILED: a different B-factor produced identical pixels, so this "
            "test cannot observe a change in the corrected output at all")
        print("  control: a changed option does change the pixels (the checks can fail)")

        # --- mixed geometry and frame counts in one run ---------------------
        mixed_dir = tmp / "Movies"
        mixed_names = []
        for i, (nx, ny, nf) in enumerate([(64, 48, 8), (48, 64, 6), (80, 40, 10), (64, 48, 8)]):
            name = f"mix{i}.mrcs"
            write_mrc(mixed_dir / name, synthetic_frames(31 + i, nx, ny, nf), nx, ny)
            mixed_names.append(f"Movies/{name}")
        count, stats, _ = case_equivalence(
            args.binary, tmp, "mixed", mixed_names, ["--prefetch"], "mixed.star", "mixed")
        assert count == 4, f"expected 4 corrected images, got {count}"
        assert stats.get("decoded", 0) + stats.get("inline_loaded", 0) == 4, \
            f"mixed geometry lost a movie: {stats}"
        print(f"  mixed:   4/4 identical across differing geometry and frame counts "
              f"(decoded={stats.get('decoded')}, inline={stats.get('inline_loaded')})")

        # --- tight budget: exactly one movie --------------------------------
        one_movie_mb = max(1, (NX * NY * 4 * NFRAMES) // (1024 * 1024) + 1)
        count, stats, _ = case_equivalence(
            args.binary, tmp, "tight", names,
            ["--prefetch", "--prefetch_mem_mb", str(one_movie_mb)], "all.star", "tight")
        assert count == 4, f"expected 4 corrected images, got {count}"
        assert stats.get("peak_reserved_bytes", 0) <= stats.get("budget_bytes", 0), \
            f"the tight bound was exceeded: {stats}"
        print(f"  tight:   4/4 identical with a {one_movie_mb} MiB budget "
              f"(peak_reserved={stats['peak_reserved_bytes']} B)")

        # --- starved budget: every movie takes the in-line fallback ---------
        # 1 MiB cannot hold any of these movies once overhead is charged, so
        # every one must be published as a LoadInline marker and loaded by the
        # consumer -- and still produce identical output.
        big_names = []
        for i in range(3):
            name = f"big{i}.mrcs"
            write_mrc(mixed_dir / name, synthetic_frames(71 + i, 512, 512, 6), 512, 512)
            big_names.append(f"Movies/{name}")
        count, stats, _ = case_equivalence(
            args.binary, tmp, "starved", big_names,
            ["--prefetch", "--prefetch_mem_mb", "1"], "big.star", "starved")
        assert count == 3, f"expected 3 corrected images, got {count}"
        assert stats.get("inline_loaded") == 3, \
            f"CONTROL: the starved budget did not actually force the fallback: {stats}"
        assert stats.get("decoded") == 0, f"a movie was admitted despite the budget: {stats}"
        assert stats.get("forced_grants") == 3, \
            f"in-line loads were not charged to the budget: {stats}"
        print(f"  starved: 3/3 identical, all via the counted in-line fallback "
              f"(forced_grants={stats['forced_grants']})")

        # --- gain reference -------------------------------------------------
        write_mrc(tmp / "gain2.mrc", [[2.0] * (NX * NY)], NX, NY)
        count, _, _ = case_equivalence(
            args.binary, tmp, "gain", names, ["--prefetch"], "all.star", "gain",
            serial_extra=["--gainref", "gain2.mrc"])
        assert count == 4
        print("  gain:    4/4 identical with a gain reference applied")

        # --- frame range selection -----------------------------------------
        count, _, _ = case_equivalence(
            args.binary, tmp, "frames", names, ["--prefetch"], "all.star", "frames",
            serial_extra=["--first_frame_sum", "2", "--last_frame_sum", "7"])
        assert count == 4
        print("  frames:  4/4 identical with --first_frame_sum 2 --last_frame_sum 7")

        # --- damaged first and damaged last ---------------------------------
        source = repo / "test-data" / "synthetic" / "synthetic_movie.tiff"
        if not source.is_file():
            raise FileNotFoundError(f"fixture missing: {source}")
        raw = source.read_bytes()
        shutil.copy(source, mixed_dir / "good1.tiff")
        shutil.copy(source, mixed_dir / "good2.tiff")
        # Keep the IFD chain intact and cut the strip data, so the failure lands
        # in the frame read rather than the header read.
        (mixed_dir / "bad.tiff").write_bytes(raw[:len(raw) - 200_000])
        for label, order in (("damaged-first", ["Movies/bad.tiff", "Movies/good1.tiff",
                                                "Movies/good2.tiff"]),
                             ("damaged-last", ["Movies/good1.tiff", "Movies/good2.tiff",
                                               "Movies/bad.tiff"])):
            star = tmp / f"{label}.star"
            write_star(star, order)
            sdir = tmp / f"serial_{label}"
            pdir = tmp / f"prefetch_{label}"
            sres = run(args.binary, star, sdir, expect_ok=False)
            pres = run(args.binary, star, pdir, extra=["--prefetch"], expect_ok=False)
            assert sres.returncode > 0 and pres.returncode > 0, (
                f"{label}: a damaged movie must fail the job without a signal "
                f"(serial={sres.returncode}, prefetch={pres.returncode})")
            assert sres.returncode == pres.returncode, (
                f"{label}: exit code changed, {sres.returncode} vs {pres.returncode}")
            assert "bad.tiff" in (pres.stdout + pres.stderr), \
                f"{label}: the damaged movie was not named by the prefetching run"
            sp, pp = products(sdir), products(pdir)
            assert set(sp) == set(pp) == {"good1.mrc", "good2.mrc"}, (
                f"{label}: healthy movies were lost\n  serial={sorted(sp)}\n"
                f"  prefetch={sorted(pp)}")
            for name in sp:
                assert sp[name] == pp[name], f"{label}: healthy pixels differ for {name}"
            print(f"  {label}: exit {pres.returncode} matches serial, both healthy "
                  f"movies retained and identical")

        # --- non-prefix resume ----------------------------------------------
        # Process only the middle movie first, then resume: the gap is not a
        # prefix, so the producer's movie list is the filtered one and its
        # records must still line up with the consumer's.
        resume_names = names
        star = tmp / "all.star"
        write_star(star, resume_names)
        seed_dir = tmp / "resume_seed"
        one = tmp / "one.star"
        write_star(one, [resume_names[2]])
        run(args.binary, one, seed_dir)
        serial_resume = tmp / "serial_resume"
        prefetch_resume = tmp / "prefetch_resume"
        for dest in (serial_resume, prefetch_resume):
            dest.mkdir(parents=True, exist_ok=True)
            for p in seed_dir.glob("**/*"):
                if p.is_file():
                    target = dest / p.relative_to(seed_dir)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy(p, target)
        run(args.binary, star, serial_resume, extra=["--only_do_unfinished"])
        rres = run(args.binary, star, prefetch_resume,
                   extra=["--only_do_unfinished", "--prefetch"])
        count = assert_same("resume", serial_resume, prefetch_resume)
        assert count == 4, f"resume did not produce full coverage: {count}"
        rstats = parse_prefetch_stats(rres.stdout)
        assert rstats.get("decoded") == 3, (
            f"CONTROL: resume should have prefetched exactly the 3 unfinished movies, "
            f"got {rstats}")
        print(f"  resume:  non-prefix resume identical, full 4/4 coverage, "
              f"{rstats['decoded']} movies prefetched")

    print("prefetch equivalence: all cases identical to serial")
    return 0


if __name__ == "__main__":
    sys.exit(main())
