#!/usr/bin/env python3
"""Compare two output trees whose movies do NOT share one geometry.

compare_output_trees.py validates a whole tree against a single expected shape,
which a mixed-geometry run does not have. This driver reuses that module's
validate_mrc -- dimensions, mode, extended-header length, exact file length,
finite pixels, normalized-header / extended-header / payload digests -- once per
movie with that movie's own shape, then requires the two trees to agree on every
one of those fields and on every STAR byte.

It runs its own negative control afterwards: one flipped payload bit and one
edited STAR byte in a copy of the candidate tree must both be reported.

Usage: compare_mixed_geometry.py <base-out> <candidate-out> <geometry.json> [--json-out F]
"""
import argparse, hashlib, importlib.util, json, shutil, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
COMPARATOR = HERE.parent / "issue85_laneC" / "compare_output_trees.py"


def load_comparator():
    spec = importlib.util.spec_from_file_location("cot", COMPARATOR)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def inventory(root):
    return sorted(p.relative_to(root).as_posix()
                  for p in root.rglob("*") if p.is_file() and p.suffix in (".mrc", ".star"))


def grade(cot, base, cand, geom):
    diffs, checked = [], []
    stems = [Path(m).stem for m in geom["movies"]]
    inv_b, inv_c = inventory(base), inventory(cand)
    expected = sorted([f"Movies/{s}.mrc" for s in stems]
                      + [f"Movies/{s}.star" for s in stems] + ["corrected_micrographs.star"])
    if inv_b != expected:
        diffs.append(f"base inventory {inv_b} != expected {expected}")
    if inv_c != expected:
        diffs.append(f"candidate inventory {inv_c} != expected {expected}")
    if diffs:
        return {"status": "FAIL", "differences": diffs, "checked": checked}
    for stem in stems:
        shape = geom["shapes"][stem]
        rel = f"Movies/{stem}.mrc"
        try:
            ib = cot.validate_mrc(base / rel, shape)
            ic = cot.validate_mrc(cand / rel, shape)
        except cot.ValidationError as exc:
            diffs.append(f"{rel}: {exc}")
            continue
        for field in ("dimensions", "mode", "extended_bytes", "file_bytes",
                      "header_sha256", "extended_sha256", "payload_sha256"):
            vb, vc = getattr(ib, field), getattr(ic, field)
            if vb != vc:
                diffs.append(f"{rel}: {field} {vb} != {vc}")
        checked.append({"file": rel, "dimensions": list(ib.dimensions), "mode": ib.mode,
                        "extended_bytes": ib.extended_bytes, "file_bytes": ib.file_bytes,
                        "pixels": ib.dimensions[0] * ib.dimensions[1] * ib.dimensions[2],
                        "payload_sha256": ib.payload_sha256,
                        "header_sha256": ib.header_sha256,
                        "extended_sha256": ib.extended_sha256})
    for rel in [f"Movies/{s}.star" for s in stems] + ["corrected_micrographs.star"]:
        db = hashlib.sha256((base / rel).read_bytes()).hexdigest()
        dc = hashlib.sha256((cand / rel).read_bytes()).hexdigest()
        if db != dc:
            diffs.append(f"{rel}: STAR bytes differ")
        checked.append({"file": rel, "sha256": db})
    return {"status": "FAIL" if diffs else "PASS", "differences": diffs, "checked": checked}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base", type=Path)
    ap.add_argument("candidate", type=Path)
    ap.add_argument("geometry", type=Path)
    ap.add_argument("--json-out", type=Path)
    a = ap.parse_args()
    cot = load_comparator()
    geom = json.loads(a.geometry.read_text())
    report = grade(cot, a.base.resolve(), a.candidate.resolve(), geom)

    # Negative control: the same grading must reject a one-bit payload edit and a
    # one-byte STAR edit, otherwise a PASS above says nothing.
    with tempfile.TemporaryDirectory() as tmp:
        mutant = Path(tmp) / "mutant"
        shutil.copytree(a.candidate, mutant)
        stem0 = Path(geom["movies"][0]).stem
        mrc = mutant / f"Movies/{stem0}.mrc"
        raw = bytearray(mrc.read_bytes())
        raw[1024] ^= 0x01
        mrc.write_bytes(bytes(raw))
        star = mutant / "corrected_micrographs.star"
        star.write_text(star.read_text() + "# injected\n")
        control = grade(cot, a.base.resolve(), mutant, geom)
        report["negative_control"] = {
            "status": control["status"],
            "differences": control["differences"],
            "tripped": control["status"] == "FAIL" and len(control["differences"]) >= 2,
        }
    ok = report["status"] == "PASS" and report["negative_control"]["tripped"]
    report["overall"] = "PASS" if ok else "FAIL"
    if a.json_out:
        a.json_out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"mixed-geometry comparison: {report['status']}; "
          f"files={len(report['checked'])}; differences={len(report['differences'])}; "
          f"negative control tripped={report['negative_control']['tripped']}")
    for d in report["differences"][:20]:
        print("  DIFF", d)
    print("OVERALL", report["overall"])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
