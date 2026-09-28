#!/usr/bin/env python3
"""Compare two MotionCorr output trees produced by the same backend.

Written after the first SCARF attempt got this wrong in two ways, both of which
made a clean run look like a 78-artifact regression:

1. It compared .mrc products by whole-file SHA-256. An MRC header carries a
   timestamped label, so two byte-different files can be pixel-identical. The
   repository already knows this; the in-repo comparator reports "Normalized
   headers: Core metadata: 0 diff bytes, Non-timestamp labels: 0 diff bytes"
   precisely so that whole-file hashing is not used as the parity test.
2. It invoked tools/compare_motioncorr.py with --require-complete-coverage but
   without the per-movie STAR pair, so the tool failed on missing coverage
   ("motion_and_star") rather than on the pixels, and returned 1 on a pair whose
   image parity was exact.

So: the image verdict comes from the trusted comparator with its STAR pair
supplied, text products are compared after path normalisation, and remaining
binaries are hashed. Whole-file .mrc hashes are recorded as an observation, not
used as the gate.
"""
from __future__ import annotations
import argparse, hashlib, json, re, subprocess, sys
from pathlib import Path


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def normalise(text: str, ref_root: Path, test_root: Path) -> str:
    # Output roots differ between arms by construction; wall-clock timings and
    # dates are not product content.
    text = text.replace(str(ref_root), "<OUT>").replace(str(test_root), "<OUT>")
    text = re.sub(r"\d+\.\d+/\d+\.\d+ (min|sec)", "<TIME>", text)
    text = re.sub(r"\d{2}:\d{2}:\d{2}", "<CLOCK>", text)
    text = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", "<DATE>", text)
    return text


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ref", required=True, type=Path)
    ap.add_argument("--test", required=True, type=Path)
    ap.add_argument("--comparator", required=True, type=Path)
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--json", required=True, type=Path)
    a = ap.parse_args()

    ref_files = {p.relative_to(a.ref).as_posix() for p in a.ref.rglob("*") if p.is_file()}
    test_files = {p.relative_to(a.test).as_posix() for p in a.test.rglob("*") if p.is_file()}

    rep = {
        "what": "same-backend native CUDA A/B of two complete output trees",
        "not_a_claim_about": ["CPU/CUDA agreement", "RELION parity",
                              "scientific equivalence", "speed"],
        "method": {
            "images": "tools/compare_motioncorr.py exact gate, with the per-movie STAR pair "
                      "supplied; normalized headers, complete pixels",
            "text": "path/time/date normalised, then compared",
            "other_binaries": "sha256",
            "whole_file_mrc_sha256": "recorded as an observation only -- the MRC header label "
                                     "is timestamped, so it is not a parity test",
        },
        "only_in_ref": sorted(ref_files - test_files),
        "only_in_test": sorted(test_files - ref_files),
        "files": [],
    }

    n_img = n_star = n_aux = n_fail = 0
    pixels = 0
    pixel_identical = 0
    for rel in sorted(ref_files & test_files):
        x, y = a.ref / rel, a.test / rel
        e = {"path": rel}
        if rel.endswith(".mrc"):
            e["kind"] = "image"; n_img += 1
            e["whole_file_sha256_equal"] = (sha256(x) == sha256(y))
            star_x, star_y = x.with_suffix(".star"), y.with_suffix(".star")
            cmd = [a.python, str(a.comparator), "--ref-mrc", str(x), "--test-mrc", str(y),
                   "--gate", "exact", "--json"]
            if star_x.is_file() and star_y.is_file():
                cmd += ["--ref-star", str(star_x), "--test-star", str(star_y),
                        "--require-complete-coverage"]
                e["coverage"] = "image+star"
            else:
                e["coverage"] = "image only (no per-movie STAR pair found)"
            r = subprocess.run(cmd, capture_output=True, text=True)
            e["comparator_exit"] = r.returncode
            try:
                cj = json.loads(r.stdout)
                img = cj.get("image") or {}
                e["pixel_identical"] = img.get("pixel_identical")
                e["image_rmse"] = img.get("rmse")
                e["max_abs_diff"] = img.get("max_abs_diff")
                e["normalized_header_diff_bytes"] = img.get("normalized_header_diff_bytes")
                e["gate_status"] = cj.get("status") or cj.get("overall")
                n = img.get("pixels_compared") or img.get("n_pixels") or 0
                pixels += int(n)
                if e["pixel_identical"]:
                    pixel_identical += 1
            except Exception as exc:
                e["comparator_parse_error"] = str(exc)
                e["comparator_stdout_head"] = r.stdout[:400]
                e["comparator_stderr_head"] = r.stderr[:400]
            e["status"] = "PASS" if r.returncode == 0 else "FAIL"
        elif rel.endswith((".star", ".log", ".txt", ".lst", ".eps")):
            e["kind"] = "star" if rel.endswith(".star") else "text"
            if rel.endswith(".star"):
                n_star += 1
            else:
                n_aux += 1
            same = (normalise(x.read_text(errors="replace"), a.ref, a.test)
                    == normalise(y.read_text(errors="replace"), a.ref, a.test))
            e["identical_normalized"] = same
            e["status"] = "PASS" if same else "FAIL"
        else:
            e["kind"] = "auxiliary"; n_aux += 1
            same = sha256(x) == sha256(y)
            e["identical_bytes"] = same
            e["status"] = "PASS" if same else "FAIL"
        if e["status"] == "FAIL":
            n_fail += 1
        rep["files"].append(e)

    rep["summary"] = {
        "artifacts_total": len(ref_files & test_files),
        "artifacts_fail": n_fail,
        "images_compared": n_img,
        "images_pixel_identical": pixel_identical,
        "total_pixels_compared": pixels,
        "star_compared": n_star,
        "auxiliary_compared": n_aux,
    }
    a.json.write_text(json.dumps(rep, indent=2) + "\n")
    print(json.dumps(rep["summary"], indent=2))
    fails = [f["path"] for f in rep["files"] if f["status"] == "FAIL"]
    print("FAILING:", fails if fails else "(none)")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
