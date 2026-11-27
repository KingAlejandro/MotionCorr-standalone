#!/usr/bin/env python3
"""Issue 61 follow-up: margin-calibrated positive controls for the Stage B primary endpoint.

PR #65 review finding r4119264405: the 5%-nominal control `ctrl_noise_f005` measured
rho = 0.9666 with a lower bound of 0.9567, i.e. it PASSES the 0.95 harm margin, so it
never demonstrated that B1 can reject degradation at its own boundary.

The measured response of the existing two controls fits rho = 1/(1 + k*f) with k = 0.694
(f=0.05 -> 0.9666, f=0.20 -> 0.8775), so the noise level needed for a true loss L is
f = L / (k * (1 - L)).  Two new levels bracket the margin:

    f = 0.076  -> predicted rho ~ 0.950  (exactly AT the harm margin)
    f = 0.110  -> predicted rho ~ 0.929  (just BEYOND it; must be rejected)

`ctrl_noise_f020` is rebuilt here so its jackknife interval can be completed, and its
pixel digests are checked against the values committed in PR #65 as a cross-host
determinism control.  Construction is byte-for-byte the procedure of the committed
`i61_setup.py`; only the level and seed base differ.
"""
import hashlib, json, os, struct, sys
import numpy as np

ROOT = "/home/ubuntu/mc-issue61b"
CPU = "/home/ubuntu/MotionCorr-issue36-full24/results/cpu"
REF = f"{ROOT}/ref"
ANGPIX = 0.885
# name -> (kind, param, seed_base)
CTRL = {"ctrl_noise_f020":  ("noise", 0.20,  62000),   # rebuild of the PR #65 control
        "ctrl_noise_f0076": ("noise", 0.076, 63000),   # at the margin
        "ctrl_noise_f011":  ("noise", 0.110, 64000)}   # beyond the margin
MOVIES = sorted(os.listdir(CPU))


def read_mrc(path):
    with open(path, "rb") as fh:
        head = bytearray(fh.read(1024))
        nx, ny, nz, mode = struct.unpack("<4i", bytes(head[0:16]))
        assert mode == 2 and nz == 1, (mode, nz)
        data = np.frombuffer(fh.read(), dtype="<f4").reshape(ny, nx)
    return head, data.astype(np.float32)


def write_mrc(path, head, data):
    head = bytearray(head)
    struct.pack_into("<3f", head, 76, float(data.min()), float(data.max()), float(data.mean()))
    struct.pack_into("<f", head, 216, float(data.std()))
    with open(path, "wb") as fh:
        fh.write(bytes(head))
        fh.write(np.ascontiguousarray(data, dtype="<f4").tobytes())


def payload_sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        fh.seek(1024)
        while True:
            c = fh.read(1 << 22)
            if not c:
                break
            h.update(c)
    return h.hexdigest()


def src_cpu(mid):
    return f"{CPU}/{mid}/output/Movies/20170629_{mid}_frameImage.mrc"


manifest = {"movies": MOVIES, "angpix": ANGPIX, "root": ROOT,
            "numpy": np.__version__, "python": sys.version.split()[0],
            "control_definitions": {k: {"kind": v[0], "param": v[1], "seed_base": v[2]}
                                    for k, v in CTRL.items()},
            "model": "rho = 1/(1 + k*f), k = 0.694 fitted to the PR #65 f=0.05 and f=0.20 controls",
            "arms": {}}

for name, (kind, param, seedb) in CTRL.items():
    d = f"{ROOT}/arms/{name}"
    os.makedirs(d, exist_ok=True)
    rec = {}
    for mid in MOVIES:
        dst = f"{d}/20170629_{mid}_frameImage.mrc"
        if not os.path.exists(dst):
            head, img = read_mrc(src_cpu(mid))
            rng = np.random.default_rng(seedb + int(mid))
            sigma = float(np.sqrt(param * img.var(dtype=np.float64)))
            img = img + rng.normal(0.0, sigma, size=img.shape).astype(np.float32)
            rec[mid] = {"sigma_added": sigma}
            write_mrc(dst, head, img)
        rec.setdefault(mid, {})["pixel_payload_sha256"] = payload_sha(dst)
    manifest["arms"][name] = rec
    print("built", name, flush=True)

# cross-host determinism control: the rebuilt f020 must reproduce PR #65's digests
prev = json.load(open(f"{ROOT}/pr65_control_manifest.json"))["arms"]["ctrl_noise_f020"]
same = sum(1 for m in MOVIES
           if manifest["arms"]["ctrl_noise_f020"][m]["pixel_payload_sha256"]
           == prev[m]["pixel_payload_sha256"])
manifest["f020_rebuild_matches_pr65_digests"] = {"matched": same, "of": len(MOVIES)}
print(f"f020 rebuild reproduces PR #65 pixel digests: {same}/{len(MOVIES)}")

# one matched RELION project per arm; only the micrograph symlink target differs
for arm in ["cpu"] + list(CTRL):
    p = f"{ROOT}/proj/{arm}"
    os.makedirs(f"{p}/MotionCorr/job002/Movies", exist_ok=True)
    os.makedirs(f"{p}/CtfFind/job003", exist_ok=True)
    os.makedirs(f"{p}/Refine3D/job019", exist_ok=True)
    os.makedirs(f"{p}/MaskCreate/job020", exist_ok=True)
    for mid in MOVIES:
        link = f"{p}/MotionCorr/job002/Movies/20170629_{mid}_frameImage.mrc"
        tgt = src_cpu(mid) if arm == "cpu" else f"{ROOT}/arms/{arm}/20170629_{mid}_frameImage.mrc"
        if os.path.islink(link) or os.path.exists(link):
            os.remove(link)
        os.symlink(tgt, link)
    for rel, tgt in [("CtfFind/job003/micrographs_ctf.star", f"{REF}/CtfFind/job003/micrographs_ctf.star"),
                     ("Refine3D/job019/run_data.star", f"{REF}/Refine3D/job019/run_data.star"),
                     ("MaskCreate/job020/mask.mrc", f"{REF}/MaskCreate/job020/mask.mrc"),
                     ("mtf_k2_200kV.star", f"{REF}/mtf_k2_200kV.star")]:
        link = f"{p}/{rel}"
        if os.path.islink(link) or os.path.exists(link):
            os.remove(link)
        os.symlink(tgt, link)

manifest["arms_all"] = ["cpu"] + list(CTRL)
json.dump(manifest, open(f"{ROOT}/results/control_manifest_followup.json", "w"),
          indent=1, sort_keys=True)
print("SETUP_DONE", len(manifest["arms_all"]), "arms")
