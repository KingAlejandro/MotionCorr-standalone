"""Offline physical-frequency weight arm (x normalisation 22 -> 42 only). HELD: refuses to run without a parent release file.

Same captured float32 initial spectra, same exact core (jointobj_core_v1.py, sha256 d331a2a4...), same 11 starts read verbatim from the
sealed baseline outcomes (sha256 5f942ae8...), same L-BFGS-B settings and 300 s cap. Only the weight array changes:
    Wphys = float32(exp(-2*150*((kx/42)^2 + (signed ky/32)^2)))      (kx = 0..21, signed ky with y=16 -> +16)
Fail-stops (exit 4) unless the inherited formula (x_norm = 22, native operation order, float64 then cast to float32) reproduces ALL 704 saved weights bitwise.
Reads only: INDEX.json, weights.{bin,json}, initial-frame*-fft.{bin,json} of the two patches (whitelist) and the sealed baseline JSON.
Never reads anything under truth; raw J values of this arm must not be ranked against the baseline arm (different objective scale).
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

PINNED_CORE_SHA256 = "d331a2a439adb7a9ce54812d3098ec48708024fde8d87532f8a0bffef8ac9f36"
PINNED_INDEX_SHA256 = "5b3dde3aefa3ff647927cbf702b3489fc1a470083fbcc23644bb8eb2f191c8d3"
PINNED_BASELINE_SHA256 = "5f942ae825219f60029898da94269fd0ab2639fb044d1dfb312d32adceea779d"
DEFAULT_BUNDLE = "/Users/alex.konstantinov/Documents/MotionCorr-evidence/20261026/Local-CCF-native-capture-r1/native-map-bundle-r1"
DEFAULT_BASELINE = "/tmp/mc-local-joint-objective-sonnet-20261026/runs/characterization-r1/stage1_outcomes.json"
RUN_PREFIX = "evidence/runs/ON/capture/"
PATCHES = ["patch-62-79", "patch-62-47"]
TOTAL_WALL_CAP_S = 300.0
BASIN_TOL_PX = 1e-3  # descriptive clustering only: unwrapped max |ds| below this joins a basin
SCALED_B = 150.0
START_LABELS = ["zero", "native_final", "native_iter1_exit"] + [f"rand{i}" for i in range(8)]

_core_hash = hashlib.sha256(open(os.path.join(HERE, "jointobj_core_v1.py"), "rb").read()).hexdigest()
if _core_hash != PINNED_CORE_SHA256:
    raise SystemExit(f"core sha256 {_core_hash} != pinned {PINNED_CORE_SHA256}")
import jointobj_core_v1 as core  # noqa: E402
from jointobj_core_v1 import JointObjective, NF, NY, NX, HX, MX, optimise  # noqa: E402

ALLOWED = re.compile(
    r"^(?:INDEX\.json|" + re.escape(RUN_PREFIX) + r"patch-62-(?:79|47)/(?:weights|initial-frame[0-4]-fft)\.(?:bin|json))$")


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
        self.index = {f["path"]: f for f in json.load(open(os.path.join(self.root, "INDEX.json")))["files"]}
        self.index_sha = got

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
        return np.frombuffer(self.read(f"{RUN_PREFIX}{patch}/{name}.bin"), dtype=dtype).reshape(shape)

    def cplx(self, patch, name):
        a = np.ascontiguousarray(self.array(patch, name, "<f4", (NY, HX, 2)).astype(np.float32))
        return a.view(np.complex64).reshape(NY, HX)


def native_order_weight(x_norm):
    """Native ccfWeightAt operation order (RFLOAT = double in the pinned build), x_norm = nfx (22) inherited; cast to float32 as stored."""
    ly = core.KY[:, None]
    x = core.KX[None, :]
    ly2 = ly * ly / (NY * float(NY))
    dist2 = ly2 + x * x / (x_norm * float(x_norm))
    return np.exp(-2.0 * dist2 * SCALED_B).astype(np.float32)


def physical_weight():
    """Parent-specified formula, verbatim."""
    kx = core.KX[None, :]
    ky = core.KY[:, None]
    return np.exp(-2.0 * 150.0 * ((kx / 42.0) ** 2 + (ky / 32.0) ** 2)).astype(np.float32)


def weight_stats(W32):
    W = W32.astype(np.float64)
    Wm = W * MX[None, :]
    return dict(n_bins_gt_0p01=int((W > 0.01).sum()), n_bins_gt_0p001=int((W > 0.001).sum()), W_max=float(W.max()),
                W_sum=float(W.sum()), WmX_sum=float(Wm.sum()), nyquist_row_max=float(W[NY // 2].max()),
                nyquist_col_max=float(W[:, HX - 1].max()))


def check_release(path):
    c = json.load(open(path))
    need = {"core_sha256": "jointobj_core_v1.py", "script_sha256": "physfreq_stage1_v1.py"}
    for key, f in need.items():
        if c.get(key) != sha256_file(os.path.join(HERE, f)):
            raise SystemExit(f"release {key} does not match {f}")
    pf = c.get("plan_file")
    if not pf or c.get("plan_sha256") != sha256_file(os.path.join(HERE, pf)):
        raise SystemExit("release plan_sha256 does not match plan_file")
    if c.get("pins_sha256") != sha256_file(os.path.join(HERE, "PINS.json")):
        raise SystemExit("release pins_sha256 does not match PINS.json")
    if not c.get("c9_disposition") or not c.get("directional_screen_frozen_sha256"):
        raise SystemExit("release must carry c9_disposition and directional_screen_frozen_sha256")
    if c.get("authorizes_offline_weight_arm") is not True:
        raise SystemExit("release lacks authorizes_offline_weight_arm=true")
    return c


def load_baseline_starts(path):
    if sha256_file(path) != PINNED_BASELINE_SHA256:
        raise SystemExit("baseline outcomes sha256 mismatch")
    base = json.load(open(path))
    if base["start_labels"] != START_LABELS:
        raise SystemExit("baseline start label order differs")
    rs = np.array(base["random_starts_xy"])
    if not np.array_equal(rs, core.initial_start_vectors()):
        raise SystemExit("baseline random starts differ from the frozen PCG64 draw")
    out = {}
    for p in PATCHES:
        outs = base["patches"][p]["outcomes"]
        if [o["label"] for o in outs] != START_LABELS:
            raise SystemExit(f"{p}: baseline outcome label order differs")
        starts = [np.array(o["s_start"], dtype=np.float64) for o in outs]
        for i, k in enumerate(range(8)):
            if not np.array_equal(starts[3 + k][1:], rs[k]):
                raise SystemExit(f"{p}: rand{k} start is not the frozen draw")
        for st in starts:
            if not (st[0] == 0.0).all():
                raise SystemExit(f"{p}: a baseline start has non-zero frame 0")
        out[p] = dict(starts=starts, baseline_candidate=base["patches"][p]["candidate"])
    return out, base


def basins(outs):
    groups = []
    for o in outs:
        if "s_final" not in o:
            continue
        s = np.array(o["s_final"])
        for g in groups:
            if np.abs(s - g["s"]).max() < BASIN_TOL_PX:
                g["labels"].append(o["label"])
                break
        else:
            groups.append(dict(s=s, labels=[o["label"]], J=o["J_final"]))
    return [dict(labels=g["labels"], s=g["s"].tolist(), J_first_member=g["J"]) for g in groups]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--release", required=True, help="parent-written JSON binding script/core/plan/pins hashes")
    ap.add_argument("--out", required=True)
    ap.add_argument("--bundle-root", default=DEFAULT_BUNDLE)
    ap.add_argument("--baseline", default=DEFAULT_BASELINE)
    a = ap.parse_args()
    release = check_release(a.release)
    os.makedirs(a.out, exist_ok=False)
    t0 = time.monotonic()
    deadline = t0 + TOTAL_WALL_CAP_S
    b = Bundle(a.bundle_root, PINNED_INDEX_SHA256)
    bl, base = load_baseline_starts(a.baseline)
    W22_formula = native_order_weight(22)
    Wphys32 = physical_weight()
    Wphys_native_order42 = native_order_weight(42)
    result = dict(stage="physfreq_stage1_v1", python=sys.version.split()[0], numpy=np.__version__, scipy=scipy.__version__, release=release,
                  core_sha256=_core_hash, index_sha256=b.index_sha, baseline_sha256=PINNED_BASELINE_SHA256, bundle_root=b.root,
                  lbfgsb_options=core.LBFGSB_OPTIONS, start_labels=START_LABELS,
                  note="raw J of this arm must not be compared with baseline-arm J (different weights, different objective scale)",
                  weight_check={}, patches={})
    saved = {}
    for p in PATCHES:
        W_saved = b.array(p, "weights", "<f4", (NY, HX)).astype(np.float32)
        mism = int((W_saved.view(np.uint32) != W22_formula.view(np.uint32)).sum())
        result["weight_check"][p] = dict(
            n_bins=int(W_saved.size), n_bitwise_mismatch_formula22_vs_saved=mism,
            max_abs_diff=float(np.abs(W_saved.astype(np.float64) - W22_formula.astype(np.float64)).max()),
            stats_saved22=weight_stats(W_saved), stats_phys42=weight_stats(Wphys32),
            phys42_verbatim_vs_native_order_bitwise_mismatch=int((Wphys32.view(np.uint32) != Wphys_native_order42.view(np.uint32)).sum()),
            phys42_n_bins_different_from_saved22=int((Wphys32.view(np.uint32) != W_saved.view(np.uint32)).sum()))
        saved[p] = W_saved
    if any(c["n_bitwise_mismatch_formula22_vs_saved"] != 0 for c in result["weight_check"].values()):
        result["stopped"] = "inherited x_norm=22 float32 formula does not reproduce all saved weights bitwise; no objective evaluated"
        with open(os.path.join(a.out, "weight_check_FAILED.json"), "w") as fh:
            json.dump(result, fh, indent=1)
        print("WEIGHT CHECK FAILED: stop before any objective")
        sys.exit(4)
    for p in PATCHES:
        F_init = np.stack([b.cplx(p, f"initial-frame{f}-fft") for f in range(NF)]).astype(np.complex128)
        obj = JointObjective(F_init, Wphys32.astype(np.float64))
        starts = bl[p]["starts"]
        refs = {}
        for nm, v in zip(START_LABELS[:3], starts[:3]):
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
        result["patches"][p] = dict(
            jscale=obj.jscale, reference_points=refs, outcomes=outs, basins_unwrapped_tol_px=BASIN_TOL_PX, basins=basins(outs),
            candidate=dict(label=best["label"], s=best["s_final"], J=best["J_final"], status=best["status"], hit_cap=best["hit_cap"],
                           rule="highest J_final over the 11 outcomes of THIS weight arm; ties -> earliest label; chosen before any truth is read"),
            baseline22_candidate_verbatim=bl[p]["baseline_candidate"])
    result["wall_s"] = time.monotonic() - t0
    path = os.path.join(a.out, "stage1_outcomes.json")
    with open(path, "w") as fh:
        json.dump(result, fh, indent=1)
    os.chmod(path, 0o444)
    seal = dict(file="stage1_outcomes.json", sha256=sha256_file(path), candidates={p: result["patches"][p]["candidate"]["label"] for p in PATCHES})
    with open(os.path.join(a.out, "SEAL.json"), "w") as fh:
        json.dump(seal, fh, indent=1)
    print("PHYSFREQ STAGE1 SEALED", json.dumps(seal))


if __name__ == "__main__":
    main()
