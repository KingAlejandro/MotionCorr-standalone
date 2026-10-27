"""Synthetic stand-in bundle (same layout/dtypes as native-map-bundle-r1) to exercise stage1_v1.py without captured data."""
import hashlib, json, os, sys
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import numpy as np
import jointobj_core_v1 as core
from jointobj_core_v1 import NF, NY, NX, HX, MX

root, amp, seed = sys.argv[1], float(sys.argv[2]), int(sys.argv[3])
rng = np.random.default_rng(seed)
files = {}
def put(rel, arr, dtype, shape, stage="synthetic"):
    d = os.path.dirname(os.path.join(root, rel)); os.makedirs(d, exist_ok=True)
    arr = np.ascontiguousarray(arr, dtype=dtype)
    arr.tofile(os.path.join(root, rel + ".bin"))
    json.dump(dict(dtype=dtype, shape=list(shape), stage=stage), open(os.path.join(root, rel + ".json"), "w"))
def cput(rel, c):
    put(rel, np.stack([c.real, c.imag], -1).astype("<f4"), "<f4", (NY, HX, 2))
W32 = core.native_weight(150.0).astype(np.float32)
def phase(s):
    return np.exp(-1j * (core.OMEGA_X[None] * s[:, 0, None, None] + core.OMEGA_Y[None] * s[:, 1, None, None]))
for patch in ("patch-62-79", "patch-62-47"):
    base = f"evidence/runs/ON/capture/{patch}/"
    G = np.fft.rfft2(rng.standard_normal((NY, NX))) * amp / (NY * NX)
    sstar = np.vstack([np.zeros((1, 2)), rng.normal(0, 3, (NF - 1, 2))])
    F0 = np.stack([(G + 0.8 * np.fft.rfft2(rng.standard_normal((NY, NX))) * amp / (NY * NX)) *
                   np.exp(1j * (core.OMEGA_X * sstar[f, 0] + core.OMEGA_Y * sstar[f, 1])) for f in range(NF)])
    F0[:, NY // 2, :] = 0; F0[:, :, HX - 1] = 0
    F0 = F0.astype(np.complex64)
    put(base + "weights", W32, "<f4", (NY, HX))
    for f in range(NF):
        cput(base + f"initial-frame{f}-fft", F0[f])
    s1 = np.vstack([np.zeros((1, 2)), rng.normal(0, 2, (NF - 1, 2))])
    s2 = np.vstack([np.zeros((1, 2)), rng.normal(0, 2, (NF - 1, 2))])
    for it, s_enter, s_exit in ((1, np.zeros((NF, 2)), s1), (2, s1, s2)):
        Fe = (F0.astype(np.complex128) * phase(s_enter)).astype(np.complex64)
        Fref = Fe.sum(axis=0, dtype=np.complex64)
        for f in range(NF):
            S = (Fref - Fe[f]) * np.conj(Fe[f]) * W32
            pre = S.copy(); S[0, 0] = 0
            m = (np.fft.irfft2(S.astype(np.complex128), s=(NY, NX)) * (NY * NX)).astype("<f4")
            cput(base + f"iter{it}-frame{f}-enter-fft", Fe[f]); cput(base + f"iter{it}-frame{f}-window-fft", Fe[f])
            cput(base + f"iter{it}-frame{f}-weighted-pre-dc", pre); cput(base + f"iter{it}-frame{f}-weighted-api-consumed", S)
            put(base + f"iter{it}-frame{f}-real-map", m, "<f4", (NY, NX))
        put(base + f"iter{it}-enter-shifts", s_enter, "<f8", (NF, 2)); put(base + f"iter{it}-exit-shifts", s_exit, "<f8", (NF, 2))
    put(base + "final-local-shifts", s2, "<f8", (NF, 2))
ents = []
for dp, _, fn in os.walk(root):
    for n in fn:
        rel = os.path.relpath(os.path.join(dp, n), root)
        if rel == "INDEX.json": continue
        b = open(os.path.join(dp, n), "rb").read()
        ents.append(dict(path=rel, bytes=len(b), sha256=hashlib.sha256(b).hexdigest()))
json.dump(dict(files=sorted(ents, key=lambda e: e["path"]), count=len(ents), scope="SYNTHETIC dry-run stand-in"), open(os.path.join(root, "INDEX.json"), "w"))
print(hashlib.sha256(open(os.path.join(root, "INDEX.json"), "rb").read()).hexdigest())
