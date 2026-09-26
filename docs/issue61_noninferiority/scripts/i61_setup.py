#!/usr/bin/env python3
"""Issue 61 stage 0: build one matched RELION project per arm.

Every downstream command is byte-identical across arms; only the symlink target
of MotionCorr/job002/Movies/<name>.mrc differs.  Control arms are written as
real MRC files derived from the CPU arm.
"""
import hashlib, json, os, struct, sys
import numpy as np

ROOT = "/home/alex/mc-issue61"
RESULTS = "/home/alex/MotionCorr-issue36-full24/results"
PRE = "/home/alex/relion-container-tests/data/spa-relion50-precalculated/extracted"
REAL_ARMS = ["cpu", "default", "allfftw"]
CTRL = {"ctrl_noise_f005": ("noise", 0.05, 61000),
        "ctrl_noise_f020": ("noise", 0.20, 62000),
        "ctrl_envelope_b20": ("envelope", 20.0, 0)}
MOVIES = sorted(os.listdir(os.path.join(RESULTS, "default")))
ANGPIX = 0.885


def read_mrc(path):
    with open(path, "rb") as fh:
        head = bytearray(fh.read(1024))
        nx, ny, nz, mode = struct.unpack("<4i", bytes(head[0:16]))
        assert mode == 2 and nz == 1, (mode, nz)
        data = np.frombuffer(fh.read(), dtype="<f4").reshape(ny, nx)
    return head, data.astype(np.float32)


def write_mrc(path, head, data):
    head = bytearray(head)
    struct.pack_into("<3f", head, 76, float(data.min()), float(data.max()),
                     float(data.mean()))
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


def envelope(ny, nx, bfac, angpix):
    fy = np.fft.fftfreq(ny, d=angpix)[:, None]
    fx = np.fft.rfftfreq(nx, d=angpix)[None, :]
    s2 = fy * fy + fx * fx
    return np.exp(-bfac * s2 / 4.0).astype(np.float32)


def src_mrc(arm, mid):
    return f"{RESULTS}/{arm}/{mid}/output/Movies/20170629_{mid}_frameImage.mrc"


manifest = {"movies": MOVIES, "arms": {}, "angpix": ANGPIX,
            "control_definitions": {k: {"kind": v[0], "param": v[1], "seed_base": v[2]}
                                    for k, v in CTRL.items()}}

os.makedirs(f"{ROOT}/arms", exist_ok=True)
for name, (kind, param, seedb) in CTRL.items():
    d = f"{ROOT}/arms/{name}"
    os.makedirs(d, exist_ok=True)
    rec = {}
    env = None
    for mid in MOVIES:
        dst = f"{d}/20170629_{mid}_frameImage.mrc"
        if not os.path.exists(dst):
            head, img = read_mrc(src_mrc("cpu", mid))
            if kind == "noise":
                rng = np.random.default_rng(seedb + int(mid))
                sigma = float(np.sqrt(param * img.var(dtype=np.float64)))
                img = img + rng.normal(0.0, sigma, size=img.shape).astype(np.float32)
                rec[mid] = {"sigma_added": sigma}
            else:
                if env is None or env.shape[0] != img.shape[0]:
                    env = envelope(img.shape[0], img.shape[1], param, ANGPIX)
                img = np.fft.irfft2(np.fft.rfft2(img) * env, s=img.shape).astype(np.float32)
                rec[mid] = {"bfactor": param}
            write_mrc(dst, head, img)
        rec.setdefault(mid, {})["pixel_payload_sha256"] = payload_sha(dst)
    manifest["arms"][name] = rec
    print(f"built {name}", flush=True)

ALL = REAL_ARMS + list(CTRL)
for arm in ALL:
    p = f"{ROOT}/proj/{arm}"
    os.makedirs(f"{p}/MotionCorr/job002/Movies", exist_ok=True)
    os.makedirs(f"{p}/CtfFind/job003", exist_ok=True)
    os.makedirs(f"{p}/Refine3D/job019", exist_ok=True)
    os.makedirs(f"{p}/MaskCreate/job020", exist_ok=True)
    for mid in MOVIES:
        link = f"{p}/MotionCorr/job002/Movies/20170629_{mid}_frameImage.mrc"
        tgt = (src_mrc(arm, mid) if arm in REAL_ARMS
               else f"{ROOT}/arms/{arm}/20170629_{mid}_frameImage.mrc")
        if os.path.islink(link) or os.path.exists(link):
            os.remove(link)
        os.symlink(tgt, link)
    for rel, tgt in [("CtfFind/job003/micrographs_ctf.star", f"{PRE}/CtfFind/job003/micrographs_ctf.star"),
                     ("Refine3D/job019/run_data.star", f"{PRE}/Refine3D/job019/run_data.star"),
                     ("MaskCreate/job020/mask.mrc", f"{PRE}/MaskCreate/job020/mask.mrc"),
                     ("mtf_k2_200kV.star", f"{PRE}/mtf_k2_200kV.star")]:
        link = f"{p}/{rel}"
        if os.path.islink(link) or os.path.exists(link):
            os.remove(link)
        os.symlink(tgt, link)

manifest["arms_all"] = ALL
with open(f"{ROOT}/results/control_manifest.json", "w") as fh:
    json.dump(manifest, fh, indent=1, sort_keys=True)
print("SETUP_DONE", len(ALL), "arms")
