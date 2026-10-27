"""Stage 1 (v2): truth-isolated joint-objective optimizer on the two retained patches. HELD: refuses to run without a clearance file.

v2 vs v1 (additive amendment, see PLAN_STAGE1_AMENDMENT_v2.md): closure B now GATES together with A; new closure C (initial-spectrum J at the
final native shifts vs direct J of the last iteration's actual exit spectra, phase-drift consistency only) also gates; whitelist adds iter[12]-frame*-exit-fft.

Reads ONLY whitelisted files of the immutable native-map bundle (every read is verified against INDEX.json sha256) and
never touches the truth-scoring bundle. Order of work: (1) bundle/INDEX verification, (2) closure A/B on every captured
entering iteration (stop before optimisation if A fails), (3) 11 optimiser runs per patch, (4) highest-J selection,
(5) sealed JSON. Stage 2 (truth scoring) is not implemented here.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np  # noqa: E402
import scipy  # noqa: E402

import jointobj_core_v1 as core  # noqa: E402
from jointobj_core_v1 import JointObjective, NF, NY, NX, HX, MX, optimise, initial_start_vectors, native_weight  # noqa: E402

PINNED_INDEX_SHA256 = "5b3dde3aefa3ff647927cbf702b3489fc1a470083fbcc23644bb8eb2f191c8d3"
DEFAULT_BUNDLE = "/Users/alex.konstantinov/Documents/MotionCorr-evidence/20261026/Local-CCF-native-capture-r1/native-map-bundle-r1"
RUN_PREFIX = "evidence/runs/ON/capture/"
PATCHES = ["patch-62-79", "patch-62-47"]
CLOSURE_ABS_BOUND = 5e-6          # proposed; objective units (native unnormalised-C2R units)
CLOSURE_C_GATES = True          # parent amendment: C gates with the same bound (recorded in the result; reversible only by a new version)
CLOSURE_VACUITY_FACTOR = 10.0     # a 1 px state perturbation must move J by > factor * bound, else the bound cannot see anything
TOTAL_WALL_CAP_S = 300.0          # both patches together
START_LABELS = ["zero", "native_final", "native_iter1_exit"] + [f"rand{i}" for i in range(core.N_RANDOM_STARTS)]

# Truth isolation: the only files this script may open under the bundle.
ALLOWED = re.compile(
    r"^(?:RUN_PINS\.json|INDEX\.json|" + re.escape(RUN_PREFIX) + r"patch-62-(?:79|47)/"
    r"(?:weights|initial-frame[0-4]-fft|final-local-shifts|iter[12]-(?:enter|exit)-shifts"
    r"|iter[12]-frame[0-4]-(?:enter-fft|exit-fft|window-fft|real-map|weighted-pre-dc|weighted-api-consumed))\.(?:bin|json))$")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class Bundle:
    def __init__(self, root, index_sha):
        self.root = os.path.realpath(root)
        got = sha256_file(os.path.join(self.root, "INDEX.json"))
        if got != index_sha:
            raise SystemExit(f"INDEX.json sha256 mismatch: {got} != {index_sha}")
        idx = json.load(open(os.path.join(self.root, "INDEX.json")))
        self.index = {f["path"]: f for f in idx["files"]}
        self.index_sha = got

    def has(self, rel):
        return rel in self.index

    def read(self, rel):
        if not ALLOWED.match(rel) or "truth" in rel:
            raise SystemExit(f"refusing to read non-whitelisted path: {rel}")
        p = os.path.realpath(os.path.join(self.root, rel))
        if not p.startswith(self.root + os.sep):
            raise SystemExit(f"path escapes bundle: {rel}")
        ent = self.index[rel]
        data = open(p, "rb").read()
        if len(data) != ent["bytes"] or hashlib.sha256(data).hexdigest() != ent["sha256"]:
            raise SystemExit(f"bundle file fails INDEX size/sha256: {rel}")
        return data

    def array(self, patch, name, dtype, shape):
        meta = json.loads(self.read(f"{RUN_PREFIX}{patch}/{name}.json"))
        if meta["dtype"] != dtype or list(meta["shape"]) != list(shape):
            raise SystemExit(f"{patch}/{name}: metadata {meta['dtype']} {meta['shape']} != expected {dtype} {shape}")
        a = np.frombuffer(self.read(f"{RUN_PREFIX}{patch}/{name}.bin"), dtype=dtype)
        return a.reshape(shape)

    def cplx(self, patch, name):
        a = self.array(patch, name, "<f4", (NY, HX, 2)).astype(np.float32)
        return np.ascontiguousarray(a).view(np.complex64).reshape(NY, HX)

    def iterations(self, patch):
        its = set()
        for k in self.index:
            m = re.fullmatch(re.escape(RUN_PREFIX + patch) + r"/iter(\d+)-frame0-enter-fft\.bin", k)
            if m:
                its.add(int(m.group(1)))
        return sorted(its)


def native_half_sum_of_maps(maps):
    return 0.5 * float(sum(float(maps[f][0, 0]) for f in range(NF)))


def native_expression_c64(Fe, W32):
    """Native expression in complex64/float32 arithmetic, summed in float64: 0.5 sum_f sum_half m_x Re[(Fref-F_f) conj(F_f) W], DC zero."""
    Fref = Fe.sum(axis=0, dtype=np.complex64)
    tot = 0.0
    for f in range(NF):
        S = (Fref - Fe[f]) * np.conj(Fe[f]) * W32
        S[0, 0] = 0
        tot += float((MX[None, :] * S.real.astype(np.float64)).sum())
    return 0.5 * tot


def closure_patch(b, patch, W, W32, F_init, bound):
    out = dict(patch=patch, iterations={}, passed_A=True, passed_B=True, vacuous=False)
    rng = np.random.default_rng(404)
    direction = rng.normal(size=(NF - 1, 2))
    direction /= np.linalg.norm(direction)
    for it in b.iterations(patch):
        Fe = np.stack([b.cplx(patch, f"iter{it}-frame{f}-enter-fft") for f in range(NF)])
        maps = [b.array(patch, f"iter{it}-frame{f}-real-map", "<f4", (NY, NX)) for f in range(NF)]
        s_enter = b.array(patch, f"iter{it}-enter-shifts", "<f8", (NF, 2)).astype(np.float64)
        if not (s_enter[0] == 0.0).all():
            raise SystemExit(f"{patch} iter{it}: enter-shifts frame 0 is not exactly 0 (gauge)")
        Fe128 = Fe.astype(np.complex128)
        obj_direct = JointObjective(Fe128, W)
        j_direct = obj_direct.value(np.zeros((NF, 2)))
        j_native = native_half_sum_of_maps(maps)
        j_c64 = native_expression_c64(Fe, W32)
        obj_init = JointObjective(F_init.astype(np.complex128), W)
        j_ideal = obj_init.value(s_enter)
        # sensitivity of the bound: how far must the entering state move before J changes by more than the bound?
        sens = {}
        for px in (0.001, 0.01, 0.1, 1.0):
            s = np.vstack([np.zeros((1, 2)), px * direction])
            sens[str(px)] = abs(obj_direct.value(s) - j_direct)
        vacuous = bool(sens["1.0"] <= CLOSURE_VACUITY_FACTOR * bound)
        # sub-step diagnostics (not gated): saved weighted spectra vs recomputation in complex64
        Fref = Fe.sum(axis=0, dtype=np.complex64)
        sub = {}
        for key in ("weighted-pre-dc", "weighted-api-consumed"):
            d = 0.0
            for f in range(NF):
                S = (Fref - Fe[f]) * np.conj(Fe[f]) * W32
                if key == "weighted-api-consumed":
                    S = S.copy()
                    S[0, 0] = 0
                d = max(d, float(np.abs(S - b.cplx(patch, f"iter{it}-frame{f}-{key}")).max()))
            sub[key + "_max_abs_diff_vs_recompute"] = d
        wf = [b.cplx(patch, f"iter{it}-frame{f}-window-fft") for f in range(NF)]
        rec = dict(
            s_enter=s_enter.tolist(), native_half_sum_of_real_map_lag0=j_native, J_direct_c128_from_entering_F=j_direct,
            delta_A_native_minus_direct=j_native - j_direct, J_native_expression_c64=j_c64,
            remainder_c64_minus_c128=j_c64 - j_direct, remainder_native_minus_c64=j_native - j_c64,
            J_ideal_initial_spectrum_at_s_enter=j_ideal, delta_B_ideal_minus_direct=j_ideal - j_direct,
            jscale_direct=obj_direct.jscale, abs_bound=bound, A_pass=bool(abs(j_native - j_direct) <= bound),
            B_pass=bool(abs(j_ideal - j_direct) <= bound), bound_vacuous=vacuous,
            sensitivity_abs_dJ_by_common_perturbation_px=sens, substep=sub,
            window_equals_enter_bitwise=all(np.array_equal(wf[f], Fe[f]) for f in range(NF)),
            initial_equals_enter_bitwise=all(np.array_equal(F_init[f], Fe[f]) for f in range(NF)),
        )
        out["iterations"][str(it)] = rec
        out["passed_A"] &= rec["A_pass"]
        out["passed_B"] &= rec["B_pass"]
        out["vacuous"] |= vacuous
    # ---- closure C: phase-drift consistency at the final native state (no native map exists at the final exit)
    last = max(b.iterations(patch))
    Fx = np.stack([b.cplx(patch, f"iter{last}-frame{f}-exit-fft") for f in range(NF)])
    s_final = b.array(patch, "final-local-shifts", "<f8", (NF, 2)).astype(np.float64)
    s_exit_last = b.array(patch, f"iter{last}-exit-shifts", "<f8", (NF, 2)).astype(np.float64)
    if not (s_final[0] == 0.0).all():
        raise SystemExit(f"{patch}: final-local-shifts frame 0 is not exactly 0 (gauge)")
    j_exit_direct = JointObjective(Fx.astype(np.complex128), W).value(np.zeros((NF, 2)))
    j_ideal_final = JointObjective(F_init.astype(np.complex128), W).value(s_final)
    c_delta = j_ideal_final - j_exit_direct
    out["C"] = dict(
        label="phase-drift consistency only; no native map exists at the final exit", last_iteration=last,
        s_final=s_final.tolist(), final_equals_last_iter_exit_shifts_bitwise=bool(np.array_equal(s_final, s_exit_last)),
        J_ideal_initial_spectrum_at_final_shifts=j_ideal_final, J_direct_c128_from_last_exit_F=j_exit_direct,
        delta_C_ideal_minus_direct=c_delta, abs_bound=bound, C_pass=bool(abs(c_delta) <= bound), C_gates=CLOSURE_C_GATES)
    out["passed_C"] = out["C"]["C_pass"] or not CLOSURE_C_GATES
    return out


def check_clearance(path):
    c = json.load(open(path))
    for key, f in (("core_sha256", "jointobj_core_v1.py"), ("stage1_sha256", "stage1_v2.py")):
        if c.get(key) != sha256_file(os.path.join(HERE, f)):
            raise SystemExit(f"clearance {key} does not match {f}")
    if not c.get("c9_disposition"):
        raise SystemExit("clearance must state the parent's disposition of the original C9 failure (c9_disposition)")
    pf = c.get("plan_file")
    if not pf or c.get("plan_sha256") != sha256_file(os.path.join(HERE, pf)):
        raise SystemExit("clearance plan_sha256 does not match plan_file")
    return c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clearance", required=True, help="parent-written JSON binding plan/core/stage1 hashes")
    ap.add_argument("--out", required=True)
    ap.add_argument("--bundle-root", default=DEFAULT_BUNDLE)
    ap.add_argument("--index-sha256", default=PINNED_INDEX_SHA256)
    ap.add_argument("--closure-only", action="store_true")
    a = ap.parse_args()
    clearance = check_clearance(a.clearance)
    if os.path.realpath(a.bundle_root) == os.path.realpath(DEFAULT_BUNDLE) and not clearance.get("authorizes_captured_payload") is True:
        raise SystemExit("clearance lacks authorizes_captured_payload=true for the captured bundle")
    os.makedirs(a.out, exist_ok=False)
    t0 = time.monotonic()
    deadline = t0 + TOTAL_WALL_CAP_S
    b = Bundle(a.bundle_root, a.index_sha256)
    rand_starts = initial_start_vectors()
    result = dict(stage="stage1_v2", closure_C_gates=CLOSURE_C_GATES, closure_abs_bound=CLOSURE_ABS_BOUND, python=sys.version.split()[0], numpy=np.__version__, scipy=scipy.__version__,
                  clearance=clearance, index_sha256=b.index_sha, bundle_root=b.root,
                  lbfgsb_options=core.LBFGSB_OPTIONS, random_start_seed=core.RANDOM_START_SEED,
                  random_start_sigma_px=core.RANDOM_START_SIGMA_PX, random_starts_xy=rand_starts.tolist(),
                  start_labels=START_LABELS, closure={}, patches={})
    state = {}
    # ---- closure first
    for patch in PATCHES:
        W32 = b.array(patch, "weights", "<f4", (NY, HX)).astype(np.float32)
        W = W32.astype(np.float64)
        F_init = np.stack([b.cplx(patch, f"initial-frame{f}-fft") for f in range(NF)])
        cl = closure_patch(b, patch, W, W32, F_init, CLOSURE_ABS_BOUND)
        cl["weights_nyquist_row_max"] = float(W[NY // 2].max())
        cl["weights_nyquist_col_max"] = float(W[:, HX - 1].max())
        cl["weights_max"] = float(W.max())
        cl["weights_max_abs_diff_vs_native_formula_B150"] = float(np.abs(W - native_weight(150.0)).max())
        result["closure"][patch] = cl
        state[patch] = (W, F_init)
    gate_ok = all(c["passed_A"] and c["passed_B"] and c["passed_C"] and not c["vacuous"] for c in result["closure"].values())
    result["closure_gate_detail"] = {p: dict(A=c["passed_A"], B=c["passed_B"], C=c["passed_C"], vacuous=c["vacuous"]) for p, c in result["closure"].items()}
    result["closure_gate_passed"] = gate_ok
    if not gate_ok or a.closure_only:
        result["stopped_before_optimisation"] = True
        with open(os.path.join(a.out, "closure_result.json"), "w") as fh:
            json.dump(result, fh, indent=1)
        print("CLOSURE GATE", "PASSED (closure-only)" if gate_ok else "FAILED: no optimisation run")
        sys.exit(0 if gate_ok else 3)
    # ---- optimisation
    for patch in PATCHES:
        W, F_init = state[patch]
        obj = JointObjective(F_init.astype(np.complex128), W)
        nat_final = b.array(patch, "final-local-shifts", "<f8", (NF, 2)).astype(np.float64)
        nat_it1 = b.array(patch, "iter1-exit-shifts", "<f8", (NF, 2)).astype(np.float64)
        for nm, v in (("native_final", nat_final), ("native_iter1_exit", nat_it1)):
            if not (v[0] == 0.0).all():
                raise SystemExit(f"{patch} {nm}: frame-0 shift is not exactly 0; stop for parent decision")
        starts = [np.zeros((NF, 2)), nat_final, nat_it1] + [np.vstack([np.zeros((1, 2)), v]) for v in rand_starts]
        refs = {}
        for nm, v in (("zero", starts[0]), ("native_final", nat_final), ("native_iter1_exit", nat_it1)):
            J, g = obj.value_grad(v)
            refs[nm] = dict(s=v.tolist(), J=J, grad_inf=float(np.abs(g[1:]).max()),
                            hessian_eigmax_J=float(np.linalg.eigvalsh(obj.hessian(v)[2:, 2:]).max()))
        outs = []
        for label, st in zip(START_LABELS, starts):
            if time.monotonic() > deadline:
                outs.append(dict(label=label, status=-8, message="NOT_RUN_TIME_CAP", hit_cap=True, time_capped=True))
                continue
            r = optimise(obj, st, deadline=deadline)
            r["label"] = label
            outs.append(r)
        eligible = [o for o in outs if "J_final" in o and np.isfinite(o["J_final"])]
        best = max(eligible, key=lambda o: (o["J_final"], -START_LABELS.index(o["label"])))
        result["patches"][patch] = dict(
            jscale=obj.jscale, reference_points=refs, outcomes=outs,
            candidate=dict(label=best["label"], s=best["s_final"], J=best["J_final"], status=best["status"], hit_cap=best["hit_cap"],
                           rule="highest J_final over the 11 outcomes; ties -> earliest label in start_labels; chosen before any truth is read"))
    result["wall_s"] = time.monotonic() - t0
    path = os.path.join(a.out, "stage1_outcomes.json")
    with open(path, "w") as fh:
        json.dump(result, fh, indent=1)
    os.chmod(path, 0o444)
    seal = dict(file="stage1_outcomes.json", sha256=sha256_file(path), candidates={p: result["patches"][p]["candidate"]["label"] for p in PATCHES})
    with open(os.path.join(a.out, "SEAL.json"), "w") as fh:
        json.dump(seal, fh, indent=1)
    print("STAGE1 SEALED", json.dumps(seal))


if __name__ == "__main__":
    main()
