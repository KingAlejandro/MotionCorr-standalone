#!/usr/bin/env python3
"""Native controls for the CUDA context warm-up thread (src/acc/cuda/cuda_context_warmup.h).

Runs the test-only fault executable on a small generated TIFF (no tutorial data
needed). The contract under test: a warm-up that succeeds, returns an error or
throws leaves the main thread's behaviour exactly what it is with the warm-up
disabled (MOTIONCORR_CUDA_WARMUP=0), and the helper thread is joined when an
error unwinds out of initialise() or run().

Injected status codes only; no device is poisoned.
"""
import argparse
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from run_preprocessing_failure_controls import digest, require, write_tiff
from test_gain_cache import NX, NY, synthetic_frames, write_star


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--workdir", type=Path)
    args = parser.parse_args()
    binary = args.binary.resolve()
    work = args.workdir.resolve() if args.workdir else Path(tempfile.mkdtemp(prefix="mc-warmup-"))
    if args.workdir:
        work.mkdir(parents=True, exist_ok=False)
    require(binary.is_file(), f"missing binary: {binary}")

    source = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "warmup_comparator", source / "docs/issue85_laneC/compare_output_trees.py")
    comparator = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = comparator
    spec.loader.exec_module(comparator)
    manifest = {"movies": ["Movies/control.tiff"], "expected_shape_xyz": [NX, NY, 1],
                "joint_star": "corrected_micrographs.star"}

    root = work / "input"
    write_tiff(root / "Movies/control.tiff",
               [[int(v) for v in frame] for frame in synthetic_frames()])
    write_star(root / "movies.star", manifest["movies"])
    (root / "defects.txt").write_text("10 12 1 1\n")

    def run(name, env_extra=None, star="movies.star", extra=()):
        out = work / name / "out"
        out.mkdir(parents=True)
        cmd = [str(binary), "--i", star, "--o", str(out) + "/", "--use_own", "--gpu", "0",
               "--j", "4", "--max_io_threads", "2", "--patch_x", "2", "--patch_y", "2",
               "--max_iter", "1", "--bfactor", "150", "--seed", "1", "--angpix", "1.0",
               "--voltage", "300", "--defect_file", "defects.txt", *extra]
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("MC_FAULT", "MC_U16", "MC_COUNT", "MC_PREPROCESS", "MC_WARMUP"))}
        env["OMP_NUM_THREADS"] = "4"
        env.update(env_extra or {})
        proc = subprocess.run(cmd, cwd=root, env=env, capture_output=True, text=True, timeout=180)
        text = proc.stdout + proc.stderr + "\n".join(p.read_text() for p in out.rglob("*.log"))
        (out.parent / "output.txt").write_text(text)
        require("remaining-owned=0 stale-releases=0" in proc.stderr or proc.returncode < 0,
                f"{name}: owned CUDA allocation cleanup was not complete")
        return out, proc.returncode, text

    def published(out):
        return sorted(str(p.relative_to(out)) for p in out.rglob("*") if p.suffix in (".mrc", ".star"))

    disabled = {"MOTIONCORR_CUDA_WARMUP": "0"}
    base, rc, text = run("disabled", disabled)
    require(rc == 0, f"disabled baseline failed: {text[-1500:]}")
    require("[warmupfault]" not in text and "warm-up" not in text,
            "the baseline must run with no warm-up")
    comparator.validate_tree(base, manifest)

    def same_as_baseline(name, out):
        report = comparator.compare_trees(base, out, manifest, compare_auxiliary=False)
        require(report["status"] == "PASS", f"{name}: products differ from the warm-up-disabled run")

    # 1. warm-up succeeds
    out, rc, text = run("warmup-ok")
    require(rc == 0, f"warmup-ok failed: {text[-1500:]}")
    require("warm-up" not in text, "a successful warm-up must be silent")
    same_as_baseline("warmup-ok", out)

    # 2. warm-up fails or throws: main thread behaves as if there were none
    for mode, expect in (("error", "cudaErrorMemoryAllocation"), ("throw", "exception: injected warm-up exception")):
        name = "warmup-" + mode
        out, rc, text = run(name, {"MC_WARMUP_FAULT": mode})
        require(f"[warmupfault]" in text and "no context created" in text,
                f"{name}: the injection did not reach the helper")
        require(rc == 0, f"{name}: the main thread did not recover: {text[-1500:]}")
        require("NOTE: CUDA context warm-up on a helper thread did not complete" in text,
                f"{name}: the failed warm-up was not reported")
        require("falling back to streaming pipeline" not in text and "Failed to initialize CUDA movie session" not in text,
                f"{name}: a failed warm-up diverted the main thread to its fallback")
        same_as_baseline(name, out)

    # 3. a failed warm-up must not change what the main thread's own failure does
    d_out, d_rc, d_text = run("init-fatal-disabled", {**disabled, "MC_PREPROCESS_FAULT": "init-fatal"})
    w_out, w_rc, w_text = run("init-fatal-warmup-error", {"MC_PREPROCESS_FAULT": "init-fatal",
                                                          "MC_WARMUP_FAULT": "error"})
    require(d_rc != 0 and "Refusing CPU fallback after a fatal device error." in d_text,
            "init-fatal baseline did not take the fatal refusal route")
    require(w_rc == d_rc and "Refusing CPU fallback after a fatal device error." in w_text,
            "init-fatal under a failed warm-up took a different route than with no warm-up")
    require(published(w_out) == published(d_out), "init-fatal: published products differ")

    # 4. the helper is joined when an error unwinds past it
    for name, extra, star in (("unwind-initialise", (), "missing.star"),
                              ("unwind-run", ("--gainref", "missing-gain.mrc"), "movies.star")):
        out, rc, text = run(name, {"MC_WARMUP_DELAY_MS": "400"}, star=star, extra=extra)
        require("[warmupfault] helper delayed 400 ms" in text,
                f"{name}: the helper was not running when the error was raised")
        require(rc == 1, f"{name}: expected a clean failure exit (1), got {rc}")
        require("ERROR" in text, f"{name}: the original error was not reported")
        require("[warmupfault] helper done" in text,
                f"{name}: the process ended before the helper finished, so it was not joined")

    print(f"PASS warm-up failure controls; artifacts: {work}")
    print("Injected status codes only; genuine device failure remains untested.")


if __name__ == "__main__":
    main()
