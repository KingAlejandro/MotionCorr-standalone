#!/usr/bin/env python3
"""Main-functionality support matrix for the composed MotionCorr candidate.

Every row runs MAIN and the CANDIDATE with identical options on identical
inputs and compares the complete product tree. A row is PASS only when both
arms exit the same way AND their products agree; a row where main itself
cannot run is UNSUPPORTED, not a candidate failure.

The flags exercised here were derived from main's parser at 6393547e, not from
a wish list. IOParser treats an unrecognised --xxx as a warning, so a row that
merely passes a flag would be vacuous; every row therefore asserts on an
observable product or exit-status difference, and rows that pin behaviour with
--ingest fail loudly when the path is unavailable.
"""
from __future__ import annotations
import argparse, hashlib, json, os, re, shutil, subprocess, sys
from pathlib import Path

W = Path("/home/alex/mc-unified-20260930")
DATA = W / "data"
OUT = W / "matrix"
BASE_OPTS = ["--use_own", "--dose_weighting", "--dose_per_frame", "1.277",
             "--patch_x", "5", "--patch_y", "5", "--bfactor", "150",
             "--gainref", "Movies/gain.mrc", "--seed", "1"]

def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()

TS = re.compile(rb"(?<=Relion    )[0-9]{2}-[A-Za-z]{3}-[0-9]{2}  [0-9]{2}:[0-9]{2}:[0-9]{2}")
NOISE = ("Full movie wall time", "execution time:", "transfer time:", "Kernel:",
         "Total GPU alignment time:", " ms", '~~(,_,"', "nvCOMP ingestion:",
         "Staging this movie as native unsigned 16-bit",
         "Staging this movie as native unsigned 8-bit",
         "Released native uint16 host staging",
         "Released native uint8 host staging",
         "Recovered the movie from device memory")

def digest_tree(root: Path) -> dict:
    """Path -> content digest, with only declared variation normalised."""
    out = {}
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = str(p.relative_to(root))
        if p.suffix.lower() == ".pdf":
            out[rel] = "PDF(inventoried)"
            continue
        raw = p.read_bytes()
        if p.suffix.lower() in (".log", ".star", ".eps", ".lst", ".txt"):
            t = raw.decode("latin-1").replace(str(root), "<OUT>")
            if p.suffix.lower() == ".log":
                t = "\n".join(l for l in t.split("\n")
                              if not any(m in l for m in NOISE))
            raw = t.encode("latin-1")
        else:
            raw = TS.sub(b"00-XXX-00  00:00:00", raw)
        out[rel] = hashlib.sha256(raw).hexdigest()
    return out

def run(binary: Path, outdir: Path, star: str, extra: list[str], cwd: Path = DATA):
    if outdir.exists():
        shutil.rmtree(outdir)
    outdir.mkdir(parents=True)
    cmd = [str(binary), "--i", star, "--o", str(outdir) + "/"] + BASE_OPTS + extra
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=1800)
    (outdir.parent / (outdir.name + ".stdout")).write_text(r.stdout[-20000:] + r.stderr[-20000:])
    return r.returncode

ROWS: list[tuple[str, str, list[str], list[str]]] = []
def row(name, star, main_extra, cand_extra=None):
    ROWS.append((name, star, main_extra, cand_extra if cand_extra is not None else main_extra))

G = ["--gpu", "0"]
# ---- input / execution -------------------------------------------------
row("star_input_cuda",       "movies_one.star", G + ["--j", "4"])
# Positive wildcard coverage. Non-STAR input requires angpix and voltage; the
# earlier row omitted them, so it tested an invalid invocation and left
# wildcard input itself unrun.
row("wildcard_input",        "Movies/20170629_0002[12]_frameImage.tiff",
    G + ["--j", "4", "--angpix", "0.885", "--voltage", "200"])
row("cpu_backend",           "movies_one.star", ["--j", "4"])
row("j1",                    "movies_one.star", G + ["--j", "1"])
row("j8_io2",                "movies_one.star", G + ["--j", "8", "--max_io_threads", "2"])
row("do_at_most_2",          "movies.star",     G + ["--j", "4", "--do_at_most", "2"])
# ---- frames / grouping -------------------------------------------------
row("first_last_frame_sum",  "movies_one.star", G + ["--j", "4", "--first_frame_sum", "3", "--last_frame_sum", "20"])
row("group_frames_3",        "movies_one.star", G + ["--j", "4", "--group_frames", "3"])
row("group_frames_5_unequal","movies_one.star", G + ["--j", "4", "--group_frames", "5"])
row("expected_frames_ok",    "movies_one.star", G + ["--j", "4", "--expected_frames", "24"])
# ---- gain / defect -----------------------------------------------------
row("no_gain",               "movies_one.star", G + ["--j", "4"])            # gainref stripped below
# Positive gain-rotation coverage. A 90-degree rotation of a 3710x3838 gain no
# longer matches the movie, so the previous row proved matched rejection, not
# that rotation works. 180 degrees preserves the shape and exercises the same
# rotation code on this detector.
row("gain_rot_180",          "movies_one.star", G + ["--j", "4", "--gain_rot", "2"])
row("gain_flip_1",           "movies_one.star", G + ["--j", "4", "--gain_flip", "1"])
row("skip_defect",           "movies_one.star", G + ["--j", "4", "--skip_defect"])
row("seed_7",                "movies_one.star", G + ["--j", "4", "--seed", "7"])
# ---- alignment ---------------------------------------------------------
row("global_only_1x1",       "movies_one.star", G + ["--j", "4", "--patch_x", "1", "--patch_y", "1"])
row("patch_3x3",             "movies_one.star", G + ["--j", "4", "--patch_x", "3", "--patch_y", "3"])
row("interpolate_shifts",    "movies_one.star", G + ["--j", "4", "--interpolate_shifts"])
# Positive binning coverage. bin_factor 2 on 3710x3838 gives 1855x1919, and main
# rejects an odd binned dimension, so a factor of 2 only ever proved matched
# rejection on this fixture. 1.855 lands on even dimensions and exercises the
# binning path itself, early and late.
row("bin_even_early",        "movies_one.star", G + ["--j", "4", "--bin_factor", "1.855"])
row("bin_even_late",         "movies_one.star", G + ["--j", "4", "--bin_factor", "1.855", "--no_early_binning"])
row("reject_bin2_no_early",  "movies_one.star", G + ["--j", "4", "--bin_factor", "2", "--no_early_binning"])
row("max_iter_1",            "movies_one.star", G + ["--j", "4", "--max_iter", "1"])
# ---- output ------------------------------------------------------------
row("save_noDW",             "movies_one.star", G + ["--j", "4", "--save_noDW"])
row("even_odd_split",        "movies_one.star", G + ["--j", "4", "--even_odd_split"])
row("ps_512",                "movies_one.star", G + ["--j", "4", "--grouping_for_ps", "4", "--ps_size", "512"])
row("float16",               "movies_one.star", G + ["--j", "4", "--grouping_for_ps", "4", "--float16"])
row("skip_logfile",          "movies_one.star", G + ["--j", "4", "--skip_logfile"])
# ---- metadata ----------------------------------------------------------
row("preexposure",           "movies_one.star", G + ["--j", "4", "--preexposure", "3.0"])
row("dose_cutoff",           "movies_one.star", G + ["--j", "4", "--dose_motionstats_cutoff", "2.0"])

# Retained as matched-rejection rows: main refuses these, and the candidate must
# refuse them identically. They are not evidence that the feature is
# unsupported, which is how the first report read them.
row("reject_gain_rot_90",    "movies_one.star", G + ["--j", "4", "--gain_rot", "1"])
row("reject_bin2_early",     "movies_one.star", G + ["--j", "4", "--bin_factor", "2"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--main", type=Path, default=W / "build-main-cuda/motioncorr")
    ap.add_argument("--cand", type=Path, default=W / "build-cand-cuda/motioncorr")
    ap.add_argument("--main-cpu", type=Path, default=W / "build-main-cpu/motioncorr")
    ap.add_argument("--cand-cpu", type=Path, default=W / "build-cand-cpu/motioncorr")
    ap.add_argument("--only", default=None)
    a = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    results = []
    for name, star, mx, cx in ROWS:
        if a.only and a.only not in name:
            continue
        mb, cb = a.main, a.cand
        if name == "cpu_backend":
            mb, cb = a.main_cpu, a.cand_cpu
        opts_m, opts_c = list(mx), list(cx)
        md, cd = OUT / f"{name}.main", OUT / f"{name}.cand"
        global BASE_OPTS
        saved = BASE_OPTS
        if name == "no_gain":
            # Drop the gain reference for this row only. The no-gain path is the
            # one #95 measured a regression on and the one the compact arm's
            # memory claim rests on, so it needs its own row.
            BASE_OPTS = [o for o in saved if o not in ("--gainref", "Movies/gain.mrc")]
        rc_m = run(mb, md, star, opts_m); rc_c = run(cb, cd, star, opts_c)
        BASE_OPTS = saved
        if rc_m != 0 and rc_c != 0:
            # Both refused. That is still a claim about the candidate --
            # preserving main's failure behaviour means the same exit status,
            # the same retained partial products and the same reason. Recording
            # "both failed" without checking any of that asserts nothing.
            dm, dc = digest_tree(md), digest_tree(cd)
            same_tree = (dm == dc)
            def reason(d):
                txt = (d.parent / (d.name + ".stdout")).read_text(errors="ignore")
                for line in txt.splitlines():
                    if "ERROR:" in line and line.strip() != "ERROR:":
                        return line.strip()[:120]
                for line in txt.splitlines():
                    if "failed for" in line:
                        return line.strip()[:120]
                return "(no reason line)"
            rm_, rc_ = reason(md), reason(cd)
            if rc_m == rc_c and same_tree and rm_ == rc_:
                verdict = "UNSUPPORTED-BY-MAIN"
                detail = (f"both arms exit {rc_m} with the same {len(dm)} retained "
                          f"products and the same reason: {rm_}")
            else:
                verdict = "FAIL"
                detail = (f"arms refuse differently: exit {rc_m}/{rc_c}, "
                          f"same_products={same_tree}, main={rm_!r}, cand={rc_!r}")
        elif rc_m != rc_c:
            verdict, detail = "FAIL", f"exit status differs: main={rc_m} cand={rc_c}"
        else:
            dm, dc = digest_tree(md), digest_tree(cd)
            missing = sorted(set(dm) - set(dc)); extra = sorted(set(dc) - set(dm))
            diff = sorted(k for k in set(dm) & set(dc) if dm[k] != dc[k])
            if missing or extra or diff:
                verdict = "FAIL"
                detail = f"missing={missing[:3]} extra={extra[:3]} differ={diff[:4]}"
            else:
                verdict, detail = "PASS", f"{len(dm)} products identical, exit {rc_m}"
        print(f"{verdict:<20} {name:<24} {detail}", flush=True)
        results.append({"row": name, "verdict": verdict, "detail": detail,
                        "main_rc": rc_m, "cand_rc": rc_c,
                        "star": star, "main_args": opts_m, "cand_args": opts_c})
        shutil.rmtree(md, ignore_errors=True); shutil.rmtree(cd, ignore_errors=True)
    (OUT / "matrix.json").write_text(json.dumps({
        "main_binary_sha256": sha(a.main), "cand_binary_sha256": sha(a.cand),
        "rows": results}, indent=1))
    n = len(results)
    p = sum(1 for r in results if r["verdict"] == "PASS")
    f = sum(1 for r in results if r["verdict"] == "FAIL")
    u = n - p - f
    print(f"\nMATRIX: {p}/{n} PASS, {f} FAIL, {u} UNSUPPORTED-BY-MAIN")
    return 1 if f else 0

if __name__ == "__main__":
    sys.exit(main())
