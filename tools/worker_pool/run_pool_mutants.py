#!/usr/bin/env python3
"""Powered negative controls for the worker-pool test.

Each mutant reintroduces one specific defect the pool is supposed to prevent,
is COMPILED, and is then run against the unchanged test. A mutant that still
passes means the control that claims to cover that defect cannot observe it.

Every mutant also names the control group it must break, so "the test went red"
is not accepted as evidence on its own: the red has to come from the right
assertion.

Usage:
  run_pool_mutants.py --src SRC --work WORK --build-cmd 'bash build.sh {src} {build} "" ON' \
                      --test-bin cuda_worker_pool --json OUT.json [--only NAME]
"""
import argparse, json, os, shutil, subprocess, sys, time
from pathlib import Path

SESSION = "src/acc/cuda/cuda_movie_session.cu"
POOL_CU = "src/acc/cuda/cuda_worker_pool.cu"
POOL_H = "src/acc/cuda/cuda_worker_pool.h"

# name -> (file, old, new, substring the test output must contain when it fails)
MUTANTS = {
    # 1. The session destroys a plan it only borrowed. This is PR133 review
    #    item 1: two owners for one handle, so the next replacement destroys it
    #    a second time.
    "alias-destroy-authority": (SESSION,
        """    if (global_plans_borrowed) {
        plan_r2c = plan_c2r = 0;
        d_fft_work = nullptr;
        d_inverse_tile = nullptr;
        global_plans_borrowed = false;
    }""",
        """    if (global_plans_borrowed) {
        global_plans_borrowed = false;
        has_plan_r2c = has_plan_c2r = true;  /* MUTANT: alias claims ownership */
    }""",
        None),

    # 2. Publish the key before the last fallible construction step. A work-area
    #    failure then leaves a published entry describing a plan with no work area.
    "publish-before-complete": (POOL_CU,
        """    for (int i = 0; i < 2; ++i) {
        const cufftHandle plan = i == 0 ? r2c_owner.get() : c2r_owner.get();
        const cufftResult res = cufftSetWorkArea(plan, raw_work);""",
        """    global_ = built;  /* MUTANT: published before the work area is attached */
    global_.plan_r2c = r2c_owner.get(); global_.has_r2c = true;
    global_.plan_c2r = c2r_owner.get(); global_.has_c2r = true;
    global_.work = raw_work; global_.inverse_tile = (cufftComplex *)tile_owner.get();
    global_.valid = true;
    for (int i = 0; i < 2; ++i) {
        const cufftHandle plan = i == 0 ? r2c_owner.get() : c2r_owner.get();
        const cufftResult res = cufftSetWorkArea(plan, raw_work);""",
        None),

    # 3. Build and publish a replacement even though the cleanup of the old
    #    resource failed. Phase 2 of the handoff: the original error and the
    #    retry verdict both have to survive a failed drop.
    "ignore-drop-result": (POOL_CU,
        """    if (!dropPatchPlan(failure)) return false;
    if (!selectDevice(device, "worker pool patch build setDevice", failure)) return false;""",
        """    (void)dropPatchPlan(failure);  /* MUTANT: drop failure ignored */
    if (!selectDevice(device, "worker pool patch build setDevice", failure)) return false;""",
        None),

    # 4. Construct on whichever device the previous drop happened to select.
    "no-device-reselect": (POOL_CU,
        """    if (!dropDwPlan(failure)) return false;
    if (!selectDevice(device, "worker pool dw build setDevice", failure)) return false;""",
        """    if (!dropDwPlan(failure)) return false;  /* MUTANT: no re-select */""",
        "re-select the requested device"),

    # 5. Serve resources to any caller, lease or not.
    "no-lease-check": (POOL_CU,
        """    if (!leasedBy(holder) || retiredFor(device)) return false;
    if (failure != nullptr && failure->isPoisoned()) {
        (void)retireForFatalContext(device, failure);
        return false;
    }
    if (nx <= 0 || ny <= 0) return false;

    if (dw_.valid && dw_.device == device""",
        """    if (retiredFor(device)) return false;  /* MUTANT: lease not required */
    if (failure != nullptr && failure->isPoisoned()) {
        (void)retireForFatalContext(device, failure);
        return false;
    }
    if (nx <= 0 || ny <= 0) return false;

    if (dw_.valid && dw_.device == device""",
        "without the lease"),

    # 6. Replace the gain in place: the old key stays valid while the buffer it
    #    describes is being replaced, so a failed replacement leaves a key
    #    matching freed or half-written memory.
    "stale-key-on-failed-replacement": (POOL_CU,
        """    fresh.take(raw);
    const cudaError_t copy_err = cudaMemcpy(raw, host_gain, bytes, cudaMemcpyHostToDevice);""",
        """    fresh.take(raw);
    /* MUTANT: key published before the upload that fills the buffer succeeds */
    gain_.d_gain = (float *)raw; gain_.device = device; gain_.nx = nx; gain_.ny = ny;
    gain_.generation = generation; gain_.bytes = bytes; gain_.valid = true;
    const cudaError_t copy_err = cudaMemcpy(raw, host_gain, bytes, cudaMemcpyHostToDevice);""",
        "retained gain"),

    # 7. A retired (dead-context) pool keeps serving its handles.
    "retired-pool-still-serves": (POOL_H,
        """    bool retiredFor(int device) const {
        return poisoned_ && (poisoned_device_ < 0 || poisoned_device_ == device);
    }""",
        """    bool retiredFor(int) const { return false; }  /* MUTANT */""",
        None),

    # 8. A created handle with no owner until planning succeeds: PR133 review
    #    item 2. A planning failure then leaks it.
    "no-temporary-ownership": (POOL_CU,
        """    owner.take(plan);

    const int patch_nfx = patch_w / 2 + 1;
    int n[2] = {patch_h, patch_w};
    size_t work_bytes = 0;
    res = cufftMakePlanMany(plan, 2, n, NULL, 1, patch_h * patch_w,
                            NULL, 1, patch_h * patch_nfx, CUFFT_R2C, n_groups,
                            &work_bytes);
    if (res != CUFFT_SUCCESS) {""",
        """    /* MUTANT: handle adopted only after planning succeeds, leaking on failure */
    const int patch_nfx = patch_w / 2 + 1;
    int n[2] = {patch_h, patch_w};
    size_t work_bytes = 0;
    res = cufftMakePlanMany(plan, 2, n, NULL, 1, patch_h * patch_w,
                            NULL, 1, patch_h * patch_nfx, CUFFT_R2C, n_groups,
                            &work_bytes);
    if (res != CUFFT_SUCCESS) {
        if (failure) {
            failure->recordCufft(res, "worker pool patch cufftMakePlanMany", __LINE__);
            failure->record(cudaPeekAtLastError(), "worker pool patch cufftMakePlanMany", __LINE__);
        }
        return false;
    }
    owner.take(plan);
    if (res != CUFFT_SUCCESS) {""",
        "outstanding"),

    # 9. An incomplete key: the batched patch plan's group count is what its
    #    batch size is, so ignoring it hands back a plan of the wrong shape.
    "incomplete-patch-key": (POOL_CU,
        """    if (patch_.valid && patch_.device == device && patch_.patch_w == patch_w &&
        patch_.patch_h == patch_h && patch_.n_groups == n_groups) {""",
        """    if (patch_.valid && patch_.device == device && patch_.patch_w == patch_w &&
        patch_.patch_h == patch_h) {  /* MUTANT: n_groups dropped from the key */""",
        None),

    # 10. Read the sticky failure state directly instead of comparing across the
    #     acquire, so an earlier recoverable failure makes every later decline
    #     look like a fresh pool failure.
    "sticky-failure-misread": (SESSION,
        """        // The pool declines (no identity) or failed. Only a NEW failure is real.
        if (delta.newFailure(failure_state)) return false;""",
        """        // MUTANT: sticky state read directly
        if (failure_state.hasFailed()) return false;""",
        "pool decline after a recoverable failure"),

    # 11. Retry the admission on whichever device the eviction last selected.
    "no-reselect-after-evict": (SESSION,
        """            HANDLE_ERROR(cudaSetDevice(device_id));
            logfile << "Movie buffer allocation failed with " << retained_before""",
        """            /* MUTANT: no re-select after the eviction */
            logfile << "Movie buffer allocation failed with " << retained_before""",
        "cross-device eviction"),

    # 12. No admission retry: retained bytes nobody is using are allowed to be
    #     the reason a later movie is refused.
    "no-eviction-retry": (SESSION,
        """    if (cuda_result == cudaErrorMemoryAllocation && worker_pool != nullptr &&
        holds_pool_lease && !failure_state.isPoisoned()) {""",
        """    if (false && cuda_result == cudaErrorMemoryAllocation && worker_pool != nullptr &&
        holds_pool_lease && !failure_state.isPoisoned()) {  /* MUTANT */""",
        None),
}


def run(cmd, **kw):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, **kw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--build-cmd", required=True,
                    help="shell template with {src} and {build}")
    ap.add_argument("--test-bin", default="cuda_worker_pool")
    ap.add_argument("--run-prefix", default="")
    ap.add_argument("--json", required=True)
    ap.add_argument("--only", default=None)
    opts = ap.parse_args()

    src = Path(opts.src).resolve()
    work = Path(opts.work).resolve()
    work.mkdir(parents=True, exist_ok=True)
    results = []

    for name, (relfile, old, new, expect) in MUTANTS.items():
        if opts.only and opts.only != name:
            continue
        tree = work / f"mut-{name}"
        build = work / f"build-{name}"
        if tree.exists():
            shutil.rmtree(tree)
        if build.exists():
            shutil.rmtree(build)
        shutil.copytree(src, tree)
        target = tree / relfile
        text = target.read_text()
        if text.count(old) != 1:
            # Loud. A mutant whose anchor drifted away is a negative control
            # that silently stopped existing, which is worse than one that fails.
            results.append({"mutant": name, "verdict": "ANCHOR_LOST",
                            "detail": f"{relfile}: expected 1 occurrence, found {text.count(old)}"})
            print(f"{'ANCHOR_LOST':14s} {name}  {relfile}: "
                  f"{text.count(old)} occurrences, expected 1", flush=True)
            continue
        target.write_text(text.replace(old, new, 1))

        t0 = time.time()
        b = run(opts.build_cmd.format(src=str(tree), build=str(build)))
        built = (build / opts.test_bin).exists()
        if not built:
            results.append({"mutant": name, "verdict": "BUILD_FAILED",
                            "detail": (b.stdout + b.stderr)[-1500:],
                            "seconds": round(time.time() - t0, 1)})
            print(f"{'BUILD_FAILED':14s} {name}", flush=True)
            continue
        r = run(f"{opts.run_prefix} {build / opts.test_bin}")
        out = r.stdout + r.stderr
        rejected = r.returncode != 0
        right_reason = (expect is None) or (expect in out)
        results.append({
            "mutant": name,
            "file": relfile,
            "exit": r.returncode,
            "verdict": "REJECTED" if (rejected and right_reason)
                       else ("WRONG_REASON" if rejected else "SURVIVED"),
            "expected_substring": expect,
            "first_fail_line": next((l for l in out.splitlines() if l.startswith("FAIL")), ""),
            "pass_lines": sum(1 for l in out.splitlines() if l.startswith("PASS")),
            "tail": out[-1200:],
            "seconds": round(time.time() - t0, 1),
        })
        print(f"{results[-1]['verdict']:14s} {name}  exit={r.returncode}  "
              f"{results[-1]['first_fail_line'][:90]}", flush=True)

    summary = {
        "mutants": len(results),
        "rejected": sum(1 for r in results if r["verdict"] == "REJECTED"),
        "survived": [r["mutant"] for r in results if r["verdict"] != "REJECTED"],
        "results": results,
    }
    Path(opts.json).write_text(json.dumps(summary, indent=1))
    print(json.dumps({k: summary[k] for k in ("mutants", "rejected", "survived")}, indent=1))
    return 0 if summary["rejected"] == summary["mutants"] else 1


if __name__ == "__main__":
    sys.exit(main())
