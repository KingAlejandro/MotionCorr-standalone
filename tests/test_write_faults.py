#!/usr/bin/env python3
"""A failed output write must fail that movie, not silently complete it.

At 4c952b3f the MRC writer discarded every fwrite/fseek result, so a short
write produced a truncated micrograph, a per-movie STAR claiming success, exit
0 and a joint STAR pointing at the truncation. The only check in the chain --
fclose inside ~fImageHandler -- reported by throwing from an implicitly
noexcept destructor, i.e. std::terminate, which would have taken the whole
batch down without naming the file.

The fault is injected with RLIMIT_FSIZE, so the real stdio and kernel write
path fail at a byte offset we choose, on the test's own temporary directory.
No shared disk is filled. SIGXFSZ is set to SIG_IGN before exec -- ignored
dispositions survive execve -- so the write returns EFBIG instead of killing
the process, which would make the run look like a crash rather than a
handled failure.

The 512x512 float output is 1024 + 1 MiB; the limit below sits under that but
far above every text product, so exactly the image write fails.

Asserted here, in one three-phase sequence:
  phase 1  movie A alone completes and is recorded.
  phase 2  A+B with --only_do_unfinished under the limit: A is skipped as
           complete, B's image write fails. The run exits non-zero without a
           signal, names B and the product path, leaves A's bytes identical,
           writes no completion record for B, and does not add B to the joint
           STAR.
  phase 3  A+B with --only_do_unfinished, limit lifted: B's truncated leftover
           is rejected by the resume check and reprocessed, A is still
           untouched, and the joint STAR now has both.
"""
import argparse
import hashlib
import os
import re
import resource
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

# 1024-byte header + 512*512*4 payload = 1_049_600 bytes.
OUTPUT_BYTES = 1024 + 512 * 512 * 4
# Under the image, far above the STAR/EPS/log products written alongside it.
FSIZE_LIMIT = 600_000
# A finite hard limit for the discriminating control: comfortably above every
# product MotionCorr writes here, so only the *plumbing* changes meaning.
FINITE_HARD_LIMIT = 8 * 1024 * 1024

COMMON_ARGS = ["--use_own", "--j", "2", "--skip_defect", "--angpix", "1.0",
               "--voltage", "300", "--patch_x", "1", "--patch_y", "1",
               "--bfactor", "150", "--skip_logfile"]


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


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def limited_preexec():
    # Runs in the forked child, before exec. Both survive execve: the ignored
    # disposition and the soft limit.
    #
    # The hard limit is read and passed back unchanged. An unprivileged process
    # cannot RAISE a hard limit, so writing RLIM_INFINITY here fails outright
    # under a finite inherited hard limit -- which CI and HPC systems do set --
    # and the child then never execs MotionCorr at all. That failure looks like
    # the writer fault never triggering, which is the opposite of the truth.
    signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
    _, hard = resource.getrlimit(resource.RLIMIT_FSIZE)
    soft = FSIZE_LIMIT if hard == resource.RLIM_INFINITY else min(FSIZE_LIMIT, hard)
    resource.setrlimit(resource.RLIMIT_FSIZE, (soft, hard))


def finite_hard_preexec():
    # Same injection, but the child's hard limit is lowered to a finite value
    # first. Lowering needs no privilege; it is irreversible for that child,
    # which is exactly the environment being reproduced.
    signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
    _, hard = resource.getrlimit(resource.RLIMIT_FSIZE)
    if hard == resource.RLIM_INFINITY or hard > FINITE_HARD_LIMIT:
        hard = FINITE_HARD_LIMIT
    resource.setrlimit(resource.RLIMIT_FSIZE, (min(FSIZE_LIMIT, hard), hard))


def run(binary: Path, cwd: Path, star: str, out: Path, extra=(), limited=False,
        preexec=None):
    if preexec is None and limited:
        preexec = limited_preexec
    return subprocess.run(
        [str(binary.resolve()), "--i", star, "--o", str(out) + "/"] + COMMON_ARGS + list(extra),
        cwd=str(cwd), capture_output=True, text=True,
        preexec_fn=preexec)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--binary", type=Path, required=True)
    ap.add_argument("--runner-arg", action="append", default=[], metavar="OPT",
                    help="Extra option passed to every invocation. Used to run this "
                         "same sequence against the synchronous output writer "
                         "(--sync_output) and against a movie with several MRC "
                         "products, where the fail-closed rule is not just 'the "
                         "image failed' but 'the first failed product cancels the "
                         "rest of that movie, the STAR among them'. Repeatable.")
    args = ap.parse_args()
    global COMMON_ARGS
    COMMON_ARGS = list(COMMON_ARGS) + list(args.runner_arg)
    if args.runner_arg:
        print(f"extra runner options: {' '.join(args.runner_arg)}")
    repo = Path(__file__).resolve().parent.parent
    source = repo / "test-data" / "synthetic" / "synthetic_movie.tiff"
    if not source.is_file():
        raise FileNotFoundError(f"fixture missing: {source}")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        movies = tmp / "Movies"
        movies.mkdir()
        shutil.copy(source, movies / "a.tiff")
        shutil.copy(source, movies / "b.tiff")
        write_star(tmp / "a.star", ["Movies/a.tiff"])
        write_star(tmp / "ab.star", ["Movies/a.tiff", "Movies/b.tiff"])
        out = tmp / "out"
        out.mkdir()

        a_mrc = out / "Movies" / "a.mrc"
        a_star = out / "Movies" / "a.star"
        b_mrc = out / "Movies" / "b.mrc"
        b_star = out / "Movies" / "b.star"
        joint = out / "corrected_micrographs.star"

        # -- phase 1: A alone, healthy ----------------------------------
        res = run(args.binary, tmp, "a.star", out)
        assert res.returncode == 0, f"healthy run failed:\n{(res.stdout + res.stderr)[-2000:]}"
        assert a_mrc.is_file() and a_star.is_file(), "healthy run produced no output"
        assert a_mrc.stat().st_size == OUTPUT_BYTES, (
            f"unexpected output size {a_mrc.stat().st_size}; the limit below is "
            f"calibrated against {OUTPUT_BYTES}")
        a_mrc_hash, a_star_hash = sha256(a_mrc), sha256(a_star)
        joint_hash = sha256(joint) if joint.is_file() else None
        print(f"  phase 1: a.mrc {a_mrc.stat().st_size} B, sha256 {a_mrc_hash[:16]}")

        # -- phase 2: B fails its image write ---------------------------
        res = run(args.binary, tmp, "ab.star", out, ["--only_do_unfinished"], limited=True)
        combined = res.stdout + res.stderr
        tail = combined[-2500:]

        assert res.returncode != 0, (
            f"a failed image write was treated as success:\n{tail}")
        assert res.returncode > 0, (
            f"killed by signal {-res.returncode}: the write fault escaped as a signal or "
            f"a destructor throw instead of a handled per-movie failure\n{tail}")
        assert "b.tiff" in combined, f"the failed movie was not named:\n{tail}"
        assert "b.mrc" in combined, f"the failed output product was not named:\n{tail}"

        assert not b_star.is_file(), (
            "a completion record was written for a movie whose image write failed")
        assert sha256(a_mrc) == a_mrc_hash, "the healthy movie's image was modified"
        assert sha256(a_star) == a_star_hash, "the healthy movie's metadata was modified"
        if joint_hash is None:
            assert not joint.is_file(), "a joint STAR was published by a failed batch"
        else:
            assert sha256(joint) == joint_hash, (
                "the joint STAR was republished by a failed batch")
            assert "b.mrc" not in joint.read_text(), (
                "the failed movie was added to the joint STAR")
        # The per-movie log must not be left claiming success for a product that
        # failed. "Written ..." is emitted when the write is QUEUED, not when it
        # lands -- deliberately, because the text and its position are compared
        # against main byte for byte and making it truthful in background mode
        # would change a product. The safety property is therefore not that the
        # claim is never premature, but that a deferred failure always corrects
        # it in the same file. Nothing asserted that until now.
        b_log = out / "Movies" / "b.log"
        assert b_log.is_file(), "the failed movie has no log at all"
        log_text = b_log.read_text()
        # The property is "the log never claims a product was written when it
        # was not", and the two writer modes satisfy it differently.
        #
        # Background: "Written ..." is emitted when the write is QUEUED, so the
        # claim is already in the file when the write later fails. The deferred
        # failure must append the correction.
        #
        # Inline (--sync_output): the write throws before that line is reached,
        # so the claim is never made and there is nothing to correct. An
        # unconditional assertion for the correction fails here -- which is how
        # this was found -- and would have been asserting the wrong thing.
        claimed = "Written" in log_text and "b.mrc" in log_text
        if claimed:
            assert "ERROR:" in log_text, (
                "the log claims b.mrc was written and carries no correction; a reader of "
                f"this file alone would believe it succeeded:\n{log_text[-800:]}")
            assert "b.mrc" in log_text.split("ERROR:", 1)[1], (
                "the correction does not name the product that failed")
        else:
            # No claim was made, which is the inline path. Assert that directly
            # rather than asserting nothing: the log must not say the product
            # was written.
            assert not re.search(r"Written[^\n]*b\.mrc", log_text), (
                "the log claims b.mrc was written on a path that should not have "
                f"reached that line:\n{log_text[-800:]}")
        print(f"    log check: claim_present={claimed} corrected={'ERROR:' in log_text}")
        a_log_text = (out / "Movies" / "a.log").read_text()
        assert "ERROR:" not in a_log_text, (
            "the healthy movie's log was given a failure it did not have")

        leftover = b_mrc.stat().st_size if b_mrc.is_file() else 0
        assert leftover < OUTPUT_BYTES, (
            f"b.mrc is {leftover} bytes: the fault did not truncate anything, so the "
            f"assertions above are not observing the injected short write")
        print(f"  phase 2: exit {res.returncode}, b.mrc truncated to {leftover} B, "
              f"no b.star, a.mrc unchanged")

        # -- phase 3: repaired retry ------------------------------------
        res = run(args.binary, tmp, "ab.star", out, ["--only_do_unfinished"])
        tail = (res.stdout + res.stderr)[-2500:]
        assert res.returncode == 0, f"the repaired retry failed:\n{tail}"
        assert b_mrc.is_file() and b_mrc.stat().st_size == OUTPUT_BYTES, (
            "the truncated leftover was accepted as complete instead of being "
            "reprocessed by --only_do_unfinished")
        assert b_star.is_file(), "the retry produced no completion record for b"
        assert sha256(a_mrc) == a_mrc_hash, "the retry rewrote the already-complete movie"
        assert sha256(a_star) == a_star_hash, "the retry rewrote the complete movie's metadata"
        assert joint.is_file(), "the successful retry published no joint STAR"
        joint_text = joint.read_text()
        assert "a.mrc" in joint_text and "b.mrc" in joint_text, (
            f"the joint STAR does not list both movies:\n{joint_text}")
        print(f"  phase 3: exit 0, b.mrc {b_mrc.stat().st_size} B, joint STAR lists both, "
              f"a.mrc still sha256 {sha256(a_mrc)[:16]}")

        # -- phase 4: the same fault under a FINITE hard limit ----------
        # Discriminating control for the harness itself. Phases 2-3 pass even
        # if the preexec writes RLIM_INFINITY as the hard limit, because the
        # test runner usually inherits an infinite one and setting it to
        # infinity is then a no-op. Here the child's hard limit is finite, so a
        # preexec that tries to raise it fails before exec and MotionCorr never
        # runs -- which would present as "the fault did not fire".
        #
        # Passing therefore requires the injection to reach the real binary:
        # asserted below on MotionCorr's own EFBIG message, not on an exit code
        # that a failed spawn could also produce.
        c_mrc = out / "Movies" / "c.mrc"
        c_star = out / "Movies" / "c.star"
        shutil.copy(source, movies / "c.tiff")
        write_star(tmp / "abc.star", ["Movies/a.tiff", "Movies/b.tiff", "Movies/c.tiff"])
        joint_before = sha256(joint)
        b_mrc_hash, b_star_hash = sha256(b_mrc), sha256(b_star)
        res = subprocess.run(
            [sys.executable, "-c",
             "import resource;"
             "print('child hard limit:', resource.getrlimit(resource.RLIMIT_FSIZE)[1])"],
            capture_output=True, text=True, preexec_fn=finite_hard_preexec)
        assert res.returncode == 0, (
            f"could not lower the hard limit in a child: {res.stderr.strip()}")
        assert str(FINITE_HARD_LIMIT) in res.stdout, (
            f"the control did not actually get a finite hard limit: {res.stdout.strip()}")

        res = run(args.binary, tmp, "abc.star", out, ["--only_do_unfinished"],
                  preexec=finite_hard_preexec)
        combined = res.stdout + res.stderr
        tail = combined[-2500:]
        assert res.returncode > 0, (
            f"exit {res.returncode} under a finite hard RLIMIT_FSIZE; an unprivileged "
            f"child cannot raise a hard limit, so the injection may never have reached "
            f"MotionCorr\n{tail}")
        assert "Failed to write image data" in combined and "c.mrc" in combined, (
            f"the run failed, but not with MotionCorr's own short-write error naming "
            f"c.mrc -- so the fault did not reach the writer\n{tail}")
        assert not c_star.is_file(), "a completion record was written under the finite-hard control"
        assert sha256(a_mrc) == a_mrc_hash, "the finite-hard control disturbed movie a"
        assert sha256(b_mrc) == b_mrc_hash and sha256(b_star) == b_star_hash, (
            "the finite-hard control disturbed movie b, which phase 3 had repaired")
        assert sha256(joint) == joint_before, (
            "the joint STAR was republished by the failed finite-hard-control batch")
        leftover_c = c_mrc.stat().st_size if c_mrc.is_file() else 0
        assert leftover_c < OUTPUT_BYTES, (
            f"c.mrc is {leftover_c} bytes: nothing was truncated, so this phase is not "
            f"observing the injected fault")
        print(f"  phase 4: finite hard limit {FINITE_HARD_LIMIT} B -> exit "
              f"{res.returncode}, MotionCorr reported the short write on c.mrc, "
              f"c.mrc truncated to {leftover_c} B, no c.star")

    print("fail-closed image writes: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
