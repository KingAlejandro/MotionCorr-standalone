#!/usr/bin/env python3
"""TIFF integrity and expected-frame count validation suite (Issue #92).

Verifies that:
1. Truncated strip data inside OpenMP fails gracefully (not abort/SIGABRT).
2. Truncated/corrupted IFD directory chains fail immediately during header inspection
   and directory count traversal rather than silently shortening the movie.
3. Hard truncation and zeroed header files fail gracefully.
4. Expected frame count (--expected_frames and STAR metadata) catches frame count mismatches.
5. Valid shorter movies (e.g. 4 frames) with clean EOF succeed without assuming 24 frames.
6. Damaged movies are isolated across batch ordering (damaged-first and damaged-last) and threads (-j 1, -j 4).
7. Successful per-movie outputs are retained and resuming with --only_do_unfinished works.
"""
import argparse
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path


def write_star(path: Path, movies, expected_frames_col=None):
    if expected_frames_col:
        header = (
            "# version 30001\n\ndata_optics\n\nloop_\n"
            "_rlnOpticsGroupName #1\n_rlnOpticsGroup #2\n"
            "_rlnMicrographOriginalPixelSize #3\n_rlnVoltage #4\n"
            "_rlnSphericalAberration #5\n_rlnAmplitudeContrast #6\n"
            "opticsGroup1 1 1.000 300.0 2.7 0.1\n\n"
            "# version 30001\n\ndata_movies\n\nloop_\n"
            "_rlnMicrographMovieName #1\n_rlnOpticsGroup #2\n_rlnNrOfFrames #3\n"
        )
        lines = [f"{m} 1 {ef}" for m, ef in zip(movies, expected_frames_col)]
        path.write_text(header + "\n".join(lines) + "\n")
    else:
        header = (
            "# version 30001\n\ndata_optics\n\nloop_\n"
            "_rlnOpticsGroupName #1\n_rlnOpticsGroup #2\n"
            "_rlnMicrographOriginalPixelSize #3\n_rlnVoltage #4\n"
            "_rlnSphericalAberration #5\n_rlnAmplitudeContrast #6\n"
            "opticsGroup1 1 1.000 300.0 2.7 0.1\n\n"
            "# version 30001\n\ndata_movies\n\nloop_\n"
            "_rlnMicrographMovieName #1\n_rlnOpticsGroup #2\n"
        )
        lines = [f"{m} 1" for m in movies]
        path.write_text(header + "\n".join(lines) + "\n")


def run_motioncorr(binary: Path, cwd: Path, args_list):
    cmd = [
        str(binary.resolve()),
        "--use_own",
        "--skip_defect",
        "--angpix", "1.0",
        "--voltage", "300",
        "--patch_x", "1",
        "--patch_y", "1",
        "--bfactor", "150",
    ] + args_list
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)


def test_strip_truncation(binary: Path, source: Path):
    """Truncated strip in OpenMP must fail damaged movie, retain good movie."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        movies = tmp / "Movies"
        movies.mkdir()
        shutil.copy(source, movies / "good.tiff")
        raw = source.read_bytes()
        (movies / "bad.tiff").write_bytes(raw[:len(raw) - 200_000])
        write_star(tmp / "m.star", ["Movies/bad.tiff", "Movies/good.tiff"])

        out = tmp / "out"
        out.mkdir()
        res = run_motioncorr(binary, tmp, ["--i", "m.star", "--o", str(out) + "/", "--j", "4"])

        assert res.returncode != 0, "a damaged movie must fail the job"
        assert res.returncode > 0, f"killed by signal {-res.returncode}"
        combined = res.stdout + res.stderr
        assert "bad.tiff" in combined, f"the damaged movie was not named: {combined}"

        produced = sorted(p.name for p in out.glob("**/*.mrc"))
        assert "good.mrc" in produced, f"healthy movie output missing: {produced}"
        assert "bad.mrc" not in produced, f"damaged movie produced output: {produced}"
    print("  [PASS] test_strip_truncation")


def test_ifd_directory_truncation(binary: Path, source: Path):
    """Partial IFD truncation must be caught during directory counting, not silent shortening."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        movies = tmp / "Movies"
        movies.mkdir()
        shutil.copy(source, movies / "good.tiff")
        raw = source.read_bytes()
        # Cut 500kB: directories 0..5 survive, directory 6/7 truncated
        (movies / "bad_ifd.tiff").write_bytes(raw[:len(raw) - 500_000])
        write_star(tmp / "m.star", ["Movies/bad_ifd.tiff", "Movies/good.tiff"])

        out = tmp / "out"
        out.mkdir()
        res = run_motioncorr(binary, tmp, ["--i", "m.star", "--o", str(out) + "/", "--j", "2"])

        assert res.returncode != 0, "partial IFD truncation must fail the job"
        assert res.returncode > 0, f"killed by signal {-res.returncode}"
        combined = res.stdout + res.stderr
        assert "bad_ifd.tiff" in combined, f"the damaged movie was not named: {combined}"
        assert ("Corrupted TIFF directory structure" in combined or
                "Error fetching directory count" in combined), f"corrupted IFD not detected in logs: {combined}"

        produced = sorted(p.name for p in out.glob("**/*.mrc"))
        assert "good.mrc" in produced, f"healthy movie output missing: {produced}"
        assert "bad_ifd.mrc" not in produced, f"damaged movie produced output: {produced}"
    print("  [PASS] test_ifd_directory_truncation")


def test_hard_truncation(binary: Path, source: Path):
    """Hard truncation (1MB prefix) must fail gracefully."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        movies = tmp / "Movies"
        movies.mkdir()
        shutil.copy(source, movies / "good.tiff")
        raw = source.read_bytes()
        (movies / "bad_hard.tiff").write_bytes(raw[:min(len(raw), 1024 * 1024)])
        write_star(tmp / "m.star", ["Movies/bad_hard.tiff", "Movies/good.tiff"])

        out = tmp / "out"
        out.mkdir()
        res = run_motioncorr(binary, tmp, ["--i", "m.star", "--o", str(out) + "/", "--j", "2"])

        assert res.returncode != 0, "hard truncation must fail the job"
        assert res.returncode > 0, f"killed by signal {-res.returncode}"
        combined = res.stdout + res.stderr
        assert "bad_hard.tiff" in combined, f"the damaged movie was not named: {combined}"

        produced = sorted(p.name for p in out.glob("**/*.mrc"))
        assert "good.mrc" in produced, f"healthy movie output missing: {produced}"
        assert "bad_hard.mrc" not in produced, f"damaged movie produced output: {produced}"
    print("  [PASS] test_hard_truncation")


def test_corrupt_header(binary: Path, source: Path):
    """Zeroed header file must fail gracefully."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        movies = tmp / "Movies"
        movies.mkdir()
        shutil.copy(source, movies / "good.tiff")
        (movies / "bad_zeros.tiff").write_bytes(b"\x00" * 4096)
        write_star(tmp / "m.star", ["Movies/bad_zeros.tiff", "Movies/good.tiff"])

        out = tmp / "out"
        out.mkdir()
        res = run_motioncorr(binary, tmp, ["--i", "m.star", "--o", str(out) + "/", "--j", "2"])

        assert res.returncode != 0, "corrupt header must fail the job"
        assert res.returncode > 0, f"killed by signal {-res.returncode}"
        combined = res.stdout + res.stderr
        assert "bad_zeros.tiff" in combined, f"the damaged movie was not named: {combined}"

        produced = sorted(p.name for p in out.glob("**/*.mrc"))
        assert "good.mrc" in produced, f"healthy movie output missing: {produced}"
        assert "bad_zeros.mrc" not in produced, f"damaged movie produced output: {produced}"
    print("  [PASS] test_corrupt_header")


def test_expected_frames_cli(binary: Path, source: Path):
    """CLI --expected_frames must reject mismatched frame count and accept matched count."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        movies = tmp / "Movies"
        movies.mkdir()
        shutil.copy(source, movies / "good8.tiff")
        write_star(tmp / "m.star", ["Movies/good8.tiff"])

        # 1. Mismatch: expected 24, decoded 8 -> FAIL
        out_fail = tmp / "out_fail"
        out_fail.mkdir()
        res_fail = run_motioncorr(
            binary, tmp,
            ["--i", "m.star", "--o", str(out_fail) + "/", "--j", "1", "--expected_frames", "24"]
        )
        assert res_fail.returncode != 0, "--expected_frames mismatch must fail"
        combined_fail = res_fail.stdout + res_fail.stderr
        assert "frame count mismatch" in combined_fail, f"mismatch error expected: {combined_fail}"
        assert "expected 24 frames, but decoded 8 frames" in combined_fail

        # 2. Match: expected 8, decoded 8 -> SUCCESS
        out_succ = tmp / "out_succ"
        out_succ.mkdir()
        res_succ = run_motioncorr(
            binary, tmp,
            ["--i", "m.star", "--o", str(out_succ) + "/", "--j", "1", "--expected_frames", "8"]
        )
        assert res_succ.returncode == 0, f"--expected_frames match should succeed: {res_succ.stdout}\n{res_succ.stderr}"
        produced = sorted(p.name for p in out_succ.glob("**/*.mrc"))
        assert "good8.mrc" in produced, f"expected good8.mrc produced: {produced}"
        assert (out_succ / "corrected_micrographs.star").is_file(), "joint star missing"
    print("  [PASS] test_expected_frames_cli")


def test_expected_frames_star(binary: Path, source: Path):
    """STAR metadata rlnNrOfFrames must validate frame count per micrograph."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        movies = tmp / "Movies"
        movies.mkdir()
        shutil.copy(source, movies / "good8.tiff")
        # STAR specifies expected 16 frames for this 8-frame movie
        write_star(tmp / "m.star", ["Movies/good8.tiff"], expected_frames_col=[16])

        out = tmp / "out"
        out.mkdir()
        res = run_motioncorr(binary, tmp, ["--i", "m.star", "--o", str(out) + "/", "--j", "1"])
        assert res.returncode != 0, "STAR rlnNrOfFrames mismatch must fail"
        combined = res.stdout + res.stderr
        assert "frame count mismatch" in combined, f"mismatch error expected: {combined}"
        assert "expected 16 frames, but decoded 8 frames" in combined
    print("  [PASS] test_expected_frames_star")


def create_clean_truncated_tiff(source: Path, target: Path, target_frames: int = 4):
    """Slice TIFF to target_frames by pointing the last IFD next-pointer to 0 (pure Python, no PIL)."""
    data = bytearray(source.read_bytes())
    endian = "<" if data[:2] == b"II" else ">"
    ifd_offset = struct.unpack_from(f"{endian}I", data, 4)[0]
    for frame in range(target_frames):
        num_tags = struct.unpack_from(f"{endian}H", data, ifd_offset)[0]
        next_ifd_ptr = ifd_offset + 2 + num_tags * 12
        next_ifd = struct.unpack_from(f"{endian}I", data, next_ifd_ptr)[0]
        if frame == target_frames - 1:
            struct.pack_into(f"{endian}I", data, next_ifd_ptr, 0)
        else:
            ifd_offset = next_ifd
    target.write_bytes(data)


def test_positive_control_short_valid_movie(binary: Path, source: Path):
    """A valid short movie (e.g. 4 frames) with clean EOF must succeed without universal 24-frame rule."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        movies = tmp / "Movies"
        movies.mkdir()
        short_tiff = movies / "short4.tiff"
        create_clean_truncated_tiff(source, short_tiff, target_frames=4)

        write_star(tmp / "m.star", ["Movies/short4.tiff"])
        out = tmp / "out"
        out.mkdir()
        res = run_motioncorr(binary, tmp, ["--i", "m.star", "--o", str(out) + "/", "--j", "1"])

        assert res.returncode == 0, f"valid 4-frame movie must succeed: {res.stdout}\n{res.stderr}"
        produced = sorted(p.name for p in out.glob("**/*.mrc"))
        assert "short4.mrc" in produced, f"short4.mrc produced: {produced}"
        assert (out / "corrected_micrographs.star").is_file(), "joint star missing"
    print("  [PASS] test_positive_control_short_valid_movie")


def test_batch_permutations(binary: Path, source: Path):
    """Damaged-first vs damaged-last with -j 1 and -j 4 must isolate correctly."""
    for threads in [1, 4]:
        for order in [("bad.tiff", "good.tiff"), ("good.tiff", "bad.tiff")]:
            with tempfile.TemporaryDirectory() as tmp:
                tmp = Path(tmp)
                movies = tmp / "Movies"
                movies.mkdir()
                shutil.copy(source, movies / "good.tiff")
                raw = source.read_bytes()
                (movies / "bad.tiff").write_bytes(raw[:len(raw) - 200_000])

                write_star(tmp / "m.star", [f"Movies/{order[0]}", f"Movies/{order[1]}"])
                out = tmp / "out"
                out.mkdir()
                res = run_motioncorr(
                    binary, tmp,
                    ["--i", "m.star", "--o", str(out) + "/", "--j", str(threads)]
                )
                assert res.returncode > 0, f"failed returncode expected with {order} at -j {threads}"
                produced = sorted(p.name for p in out.glob("**/*.mrc"))
                assert "good.mrc" in produced, f"good.mrc missing in {order} at -j {threads}: {produced}"
                assert "bad.mrc" not in produced, f"bad.mrc should not exist: {produced}"
    print("  [PASS] test_batch_permutations")


def test_resume_isolation(binary: Path, source: Path):
    """Failed movie can be replaced and completed with --only_do_unfinished."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        movies = tmp / "Movies"
        movies.mkdir()
        shutil.copy(source, movies / "good.tiff")
        raw = source.read_bytes()
        (movies / "bad.tiff").write_bytes(raw[:len(raw) - 200_000])
        write_star(tmp / "m.star", ["Movies/bad.tiff", "Movies/good.tiff"])

        out = tmp / "out"
        out.mkdir()

        # Step 1: Run with bad movie -> fails
        res1 = run_motioncorr(binary, tmp, ["--i", "m.star", "--o", str(out) + "/", "--j", "2"])
        assert res1.returncode != 0
        assert (out / "Movies" / "good.mrc").is_file()
        assert not (out / "Movies" / "bad.mrc").is_file()
        assert not (out / "corrected_micrographs.star").is_file()

        # Step 2: Replace bad.tiff with valid movie and rerun with --only_do_unfinished
        shutil.copy(source, movies / "bad.tiff")
        res2 = run_motioncorr(
            binary, tmp,
            ["--i", "m.star", "--o", str(out) + "/", "--j", "2", "--only_do_unfinished"]
        )
        assert res2.returncode == 0, f"resumed run should succeed: {res2.stdout}\n{res2.stderr}"
        assert (out / "Movies" / "good.mrc").is_file()
        assert (out / "Movies" / "bad.mrc").is_file()
        assert (out / "corrected_micrographs.star").is_file()
    print("  [PASS] test_resume_isolation")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--binary", type=Path, required=True)
    args = ap.parse_args()
    repo = Path(__file__).resolve().parent.parent
    source = repo / "test-data" / "synthetic" / "synthetic_movie.tiff"
    if not source.is_file():
        raise FileNotFoundError(f"fixture missing: {source}")

    print("Running TIFF integrity and expected-frame validation test suite...")
    test_strip_truncation(args.binary, source)
    test_ifd_directory_truncation(args.binary, source)
    test_hard_truncation(args.binary, source)
    test_corrupt_header(args.binary, source)
    test_expected_frames_cli(args.binary, source)
    test_expected_frames_star(args.binary, source)
    test_positive_control_short_valid_movie(args.binary, source)
    test_batch_permutations(args.binary, source)
    test_resume_isolation(args.binary, source)

    print("All TIFF integrity and expected-frame validation tests PASSED.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
