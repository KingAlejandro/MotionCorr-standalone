#!/usr/bin/env python3
"""Correctness oracle for the single-pass aggregate logfile.pdf (SCARF gn0005).

Products are expected to be untouched; the artifact that actually changes is
logfile.pdf, which the product oracle skips by design. So the discriminating
comparator here is a page-for-page raster of the PDF, and it is calibrated
against perturbations of the same tree before the treatment result is read.
"""
import hashlib, json, os, shlex, shutil, subprocess, sys, time
from pathlib import Path

BASE = Path("/home/vol05/scarf1415/mc-overhead-20261013")
BINS = {"base": BASE / "build-base" / "motioncorr", "cand": BASE / "build-cand" / "motioncorr"}
TOOLS = BASE / "src-cand" / "tools" / "multi_gpu"
CMP = BASE / "src-base" / "docs" / "issue85_laneC" / "compare_output_trees.py"
PY = sys.executable
DATA = Path("/tmp/bench-data")
G0 = "GPU-47d61ef5-38d4-8bab-6e1b-6673e3e1f011"
MASK = "0-7"  # physical cores on NUMA node0, GPU0's node; the node allocation is the exclusion
WARGS = ("--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 "
         "--bfactor 150 --gainref Movies/gain.mrc --seed 1 --j 8 --ingest nvcomp").split()
W = Path("/tmp/aggorc3")
RUN = W / "run"  # every arm writes this identical absolute path
MAN = BASE / "aggorc3-manifest.json"
MOV = "20170629_00021_frameImage"
if W.exists():
    shutil.rmtree(W)
W.mkdir()
GSO = ["-sDEVICE=pdfwrite", "-dNOPAUSE", "-dBATCH", "-dSAFER",
       "-dDEVICEWIDTHPOINTS=800", "-dDEVICEHEIGHTPOINTS=800"]

def run(arm, out):
    if RUN.exists(): shutil.rmtree(RUN)
    la = ["--devices", G0, "--cpus", MASK, "--cpu-budget", "8"]
    cmd = ["taskset", "-c", MASK, PY,
           str(TOOLS / "run_dataset.py"), "--binary", str(BINS[arm]), "--star", "movies.star",
           "--out", str(RUN), "--launcher-args=" + shlex.join(la), "--", *WARGS]
    p = subprocess.run(cmd, cwd=DATA, capture_output=True, text=True)
    RUN.rename(out)
    for f in out.rglob("*"):
        if f.is_file() and f.suffix in (".star", ".lst"):
            b = f.read_bytes(); nb = b.replace(str(RUN).encode(), str(out).encode())
            if nb != b: f.write_bytes(nb)
    s = json.loads((out / "dataset_status.json").read_text())
    print("%-5s rc=%d wall=%.3f %s logfile.pdf.lst=%s"
          % (arm, p.returncode, s["dataset_wall_s"], s["verdict"],
             (out / "merged" / "logfile.pdf.lst").exists()), flush=True)
    return s

st = {t: run(a, W / t) for t, a in (("base0", "base"), ("base1", "base"), ("cand0", "cand"))}

star = (DATA / "movies.star").read_bytes()
movies = [t[0] for t in (l.split() for l in star.decode("latin-1").splitlines())
          if len(t) == 2 and t[0].startswith("Movies/")]
import struct
nx, ny, nz = struct.unpack("<3i", (W / "base0" / "merged" / "Movies" /
                                   (Path(movies[0]).stem + ".mrc")).read_bytes()[:12])
MAN.write_text(json.dumps({"movies": movies, "expected_shape_xyz": [nx, ny, nz],
                           "input_star_sha256": hashlib.sha256(star).hexdigest(),
                           "joint_star": "corrected_micrographs.star"}, indent=1))

def hide(t):
    p = W / t / "merged" / "_workers"
    if p.is_dir(): p.rename(W / t / "_hidden")
def show(t):
    p = W / t / "_hidden"
    if p.is_dir(): p.rename(W / t / "merged" / "_workers")

def oracle(a, b, tag):
    o = BASE / ("aggo3-%s.json" % tag)
    p = subprocess.run([PY, str(CMP), str(a), str(b), "--manifest", str(MAN),
                        "--input-star", str(DATA / "movies.star"), "--products-only",
                        "--json-out", str(o)], capture_output=True, text=True)
    try:
        j = json.loads(o.read_text()); s, d = j["status"], j["different_products"]
    except Exception:
        s, d = "REJECTED", (p.stderr or p.stdout).strip().splitlines()[-1:]
    print("  %-28s rc=%d status=%-8s differing=%s" % (tag, p.returncode, s, d))
    return s

print("--- product oracle ---")
for t in ("base0", "base1", "cand0"): hide(t)
p_null = oracle(W / "base0" / "merged", W / "base1" / "merged", "null-base-vs-base")
p_treat = oracle(W / "base0" / "merged", W / "cand0" / "merged", "treat-base-vs-cand")
PC = W / "pc"
shutil.copytree(W / "base1", PC, symlinks=True)
for f in PC.rglob("*"):
    if f.is_file() and f.suffix in (".star", ".lst"):
        b = f.read_bytes(); nb = b.replace(str(W / "base1").encode(), str(PC).encode())
        if nb != b: f.write_bytes(nb)
hp = PC / "merged" / "_workers"
if hp.is_dir(): hp.rename(PC / "_hidden")
m = PC / "merged" / "Movies" / (MOV + ".mrc")
bb = bytearray(m.read_bytes()); off = 1024 + 4 * 500000; bb[off] ^= 0x01
m.write_bytes(bytes(bb))
p_ctl = oracle(W / "base0" / "merged", PC / "merged", "ctl-mrc-payload-flip")
for t in ("base0", "base1", "cand0"): show(t)

def pages(pdf, d):
    if d.exists(): shutil.rmtree(d)
    d.mkdir(parents=True)
    subprocess.run(["gs", "-q", "-dNOPAUSE", "-dBATCH", "-dSAFER", "-sDEVICE=png16m", "-r100",
                    "-sOutputFile=%s/p%%03d.png" % d, str(pdf)],
                   capture_output=True)
    return sorted(d.glob("p*.png"))

def raster(a_pdf, b_pdf, tag):
    A, B = pages(a_pdf, W / "ra"), pages(b_pdf, W / "rb")
    if len(A) != len(B):
        print("  %-28s PAGECOUNT %d vs %d -> DIFFER" % (tag, len(A), len(B)))
        return -1
    d = sum(1 for x in A if x.read_bytes() != (W / "rb" / x.name).read_bytes())
    print("  %-28s pages=%d differing=%d" % (tag, len(A), d))
    return d

print("--- report raster, %d pages expected ---" % (len(movies) + 6))
r_null = raster(W / "base0" / "merged" / "logfile.pdf", W / "base1" / "merged" / "logfile.pdf",
                "logfile null-base-vs-base")
r_treat = raster(W / "base0" / "merged" / "logfile.pdf", W / "cand0" / "merged" / "logfile.pdf",
                 "logfile treat-base-vs-cand")
h_treat = raster(W / "base0" / "merged" / "header.pdf", W / "cand0" / "merged" / "header.pdf",
                 "header  treat-base-vs-cand")
b_treat = raster(W / "base0" / "merged" / "batch.pdf", W / "cand0" / "merged" / "batch.pdf",
                 "batch   treat-base-vs-cand")

print("--- raster comparator controls, built from base0 EPS ---")
M0 = W / "base0" / "merged"
hdr = [str(M0 / ("corrected_micrographs_%s_%s.eps" % (k, lab)))
       for lab in ("rlnAccumMotionTotal", "rlnAccumMotionEarly", "rlnAccumMotionLate")
       for k in ("all", "hist")]
bat = [str(M0 / "Movies" / (Path(m).stem + "_shifts.eps")) for m in movies]
def build(lst, out):
    f = W / (out.stem + ".lst"); f.write_text("\n".join(lst) + "\n")
    subprocess.run(["gs"] + GSO + ["-sOutputFile=" + str(out), "@" + str(f)], capture_output=True)
    return out
ctl = {}
ctl["c1-page-content-swapped"] = build(hdr + [bat[1]] + bat[1:], W / "c1.pdf")
ctl["c2-page-dropped"] = build(hdr + bat[1:], W / "c2.pdf")
ctl["c3-pages-reordered"] = build(hdr + [bat[1], bat[0]] + bat[2:], W / "c3.pdf")
ctl["c4-header-omitted"] = build(bat, W / "c4.pdf")
ctl["c0-unperturbed"] = build(hdr + bat, W / "c0.pdf")
cres = {k: raster(M0 / "logfile.pdf", v, k) for k, v in sorted(ctl.items())}

fired = (cres["c0-unperturbed"] == 0 and all(cres[k] != 0 for k in
         ("c1-page-content-swapped", "c2-page-dropped", "c3-pages-reordered", "c4-header-omitted")))
print("RASTER_CONTROLS=%s" % ("ALL_FIRED" if fired else "INCOMPLETE"))

print("--- tree attribution (base0^base1 as null) ---")
def snap(m):
    o = {}
    for p in sorted(Path(m).rglob("*")):
        if not p.is_file(): continue
        b, rel = p.read_bytes(), str(p.relative_to(m))
        if p.suffix == ".mrc": o[rel] = hashlib.sha256(b[:224] + b[1024:]).hexdigest()
        elif p.suffix in (".star", ".eps", ".lst"):
            o[rel] = hashlib.sha256(b.replace(str(RUN).encode(), b"<O>").replace(str(m).encode(), b"<O>")).hexdigest()
        else: o[rel] = "size:%d" % len(b)
    return o
S = {t: snap(W / t / "merged") for t in ("base0", "base1", "cand0")}
def dif(a, b):
    A, B = S[a], S[b]
    return set(A) ^ set(B) | {k for k in set(A) & set(B) if A[k] != B[k]}
nullset = dif("base0", "base1")
attributable = sorted(p for p in dif("base0", "cand0") if p not in nullset)
print("null_diffs=%d treat_diffs=%d attributable=%d" % (len(nullset), len(dif("base0", "cand0")),
                                                        len(attributable)))
for p in attributable: print("    +", p)

res = {"product_null": p_null, "product_treat": p_treat, "product_control": p_ctl,
       "raster_logfile_null": r_null, "raster_logfile_treat": r_treat,
       "raster_header_treat": h_treat, "raster_batch_treat": b_treat,
       "raster_controls": cres, "raster_controls_all_fired": fired,
       "attributable_paths": attributable,
       "walls": {k: v["dataset_wall_s"] for k, v in st.items()},
       "aggregate_phase": {k: v["aggregate_phase_wall_s"] for k, v in st.items()},
       "verdicts": {k: v["verdict"] for k, v in st.items()},
       "binary_sha256": {k: hashlib.sha256(v.read_bytes()).hexdigest() for k, v in BINS.items()}}
(BASE / "aggorc3.json").write_text(json.dumps(res, indent=1))
print("VERDICT product null=%s treat=%s control=%s | raster logfile null=%s treat=%s"
      % (p_null, p_treat, p_ctl, r_null, r_treat))
print("ALLDONE")
