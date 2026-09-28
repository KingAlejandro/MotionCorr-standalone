#!/usr/bin/env python3
"""Add one control placed AT the harm margin, to test the property that actually protects a
non-inferiority PASS: an arm at the margin must not be able to earn one.

Recalibrated from the two new controls, which give rho = 1/(1 + k*f) with k = 0.847
(f=0.076 -> 0.93963, f=0.110 -> 0.91460).  For rho = 0.950 exactly:
    f = (1/0.95 - 1) / 0.847 = 0.0621  ->  use f = 0.062
Prediction recorded before the reconstructions are analysed.
"""
import hashlib, json, os, struct, sys
import numpy as np
sys.path.insert(0, "/home/ubuntu/mc-issue61b/scripts")
ROOT = "/home/ubuntu/mc-issue61b"
CPU = "/home/ubuntu/MotionCorr-issue36-full24/results/cpu"
REF = f"{ROOT}/ref"
NAME, PARAM, SEEDB = "ctrl_noise_f0062", 0.062, 65000
MOVIES = sorted(os.listdir(CPU))


def read_mrc(p):
    with open(p, "rb") as fh:
        head = bytearray(fh.read(1024))
        nx, ny, nz, mode = struct.unpack("<4i", bytes(head[0:16]))
        assert mode == 2 and nz == 1
        return head, np.frombuffer(fh.read(), dtype="<f4").reshape(ny, nx).astype(np.float32)


def write_mrc(p, head, d):
    head = bytearray(head)
    struct.pack_into("<3f", head, 76, float(d.min()), float(d.max()), float(d.mean()))
    struct.pack_into("<f", head, 216, float(d.std()))
    with open(p, "wb") as fh:
        fh.write(bytes(head)); fh.write(np.ascontiguousarray(d, dtype="<f4").tobytes())


def payload_sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        fh.seek(1024)
        while True:
            c = fh.read(1 << 22)
            if not c: break
            h.update(c)
    return h.hexdigest()


d = f"{ROOT}/arms/{NAME}"; os.makedirs(d, exist_ok=True)
rec = {}
for mid in MOVIES:
    dst = f"{d}/20170629_{mid}_frameImage.mrc"
    if not os.path.exists(dst):
        head, img = read_mrc(f"{CPU}/{mid}/output/Movies/20170629_{mid}_frameImage.mrc")
        rng = np.random.default_rng(SEEDB + int(mid))
        sigma = float(np.sqrt(PARAM * img.var(dtype=np.float64)))
        write_mrc(dst, head, img + rng.normal(0.0, sigma, size=img.shape).astype(np.float32))
        rec[mid] = {"sigma_added": sigma}
    rec.setdefault(mid, {})["pixel_payload_sha256"] = payload_sha(dst)

p = f"{ROOT}/proj/{NAME}"
for sub in ("MotionCorr/job002/Movies", "CtfFind/job003", "Refine3D/job019", "MaskCreate/job020"):
    os.makedirs(f"{p}/{sub}", exist_ok=True)
for mid in MOVIES:
    l = f"{p}/MotionCorr/job002/Movies/20170629_{mid}_frameImage.mrc"
    if os.path.islink(l) or os.path.exists(l): os.remove(l)
    os.symlink(f"{d}/20170629_{mid}_frameImage.mrc", l)
for rel, tgt in [("CtfFind/job003/micrographs_ctf.star", f"{REF}/CtfFind/job003/micrographs_ctf.star"),
                 ("Refine3D/job019/run_data.star", f"{REF}/Refine3D/job019/run_data.star"),
                 ("MaskCreate/job020/mask.mrc", f"{REF}/MaskCreate/job020/mask.mrc"),
                 ("mtf_k2_200kV.star", f"{REF}/mtf_k2_200kV.star")]:
    l = f"{p}/{rel}"
    if os.path.islink(l) or os.path.exists(l): os.remove(l)
    os.symlink(tgt, l)

json.dump({"control": NAME, "f": PARAM, "seed_base": SEEDB,
           "predicted_rho": 0.950, "model": "rho = 1/(1+0.847 f)",
           "prediction_recorded_before_analysis": True, "arms": {NAME: rec}},
          open(f"{ROOT}/results/control_manifest_margin.json", "w"), indent=1, sort_keys=True)
print("built", NAME, "f =", PARAM, "predicted rho = 0.950")
