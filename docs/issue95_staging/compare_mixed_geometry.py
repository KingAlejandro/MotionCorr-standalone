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
import argparse, hashlib, importlib.util, json, os, shutil, sys, tempfile
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


def root_spellings(*roots):
    """Every way an arm's own output root can appear inside its STAR files.

    MotioncorrRunner records the --o argument it was given, which is not the
    resolved path when a parent is a symlink. compare_output_trees.py normalizes
    this before comparing STAR text; comparing raw bytes here instead reported
    every STAR as differing whenever the two arms wrote to differently named
    directories. Longest first so a prefix never shadows a longer match.
    """
    out = set()
    for r in roots:
        out.add(str(r))
        out.add(str(Path(r).resolve()))
        out.add(os.path.realpath(str(r)))
    return sorted((s for s in out if s), key=len, reverse=True)


def star_digest(root, rel, spellings):
    text = (root / rel).read_text(errors="replace")
    for s in spellings:
        text = text.replace(s, "<OUTPUT_ROOT>")
    return hashlib.sha256(text.encode()).hexdigest()


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
    spellings = root_spellings(base, cand)
    for rel in [f"Movies/{s}.star" for s in stems] + ["corrected_micrographs.star"]:
        db = star_digest(base, rel, spellings)
        dc = star_digest(cand, rel, spellings)
        if db != dc:
            diffs.append(f"{rel}: STAR text differs")
        checked.append({"file": rel, "root_normalised_sha256": db})
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
    # Deliberately NOT resolved: root_spellings() needs the spelling the run was
    # given as well as the resolved one.
    report = grade(cot, a.base, a.candidate, geom)

    # Negative control: the same grading must reject a one-bit payload edit and a
    # one-byte STAR edit, otherwise a PASS above says nothing.
    with tempfile.TemporaryDirectory() as tmp:
        mutant = Path(tmp) / "mutant"
        shutil.copytree(a.candidate, mutant)
        stem0 = Path(geom["movies"][0]).stem
        mrc = mutant / f"Movies/{stem0}.mrc"
        raw = bytearray(mrc.read_bytes())
        # The payload starts after the 1024-byte header AND the extended header,
        # so read nsymbt rather than assuming it is zero; otherwise the control
        # would edit the extended header and report the wrong provenance.
        nsymbt = int.from_bytes(bytes(raw[92:96]), "little")
        payload0 = 1024 + nsymbt
        raw[payload0] ^= 0x01
        mrc.write_bytes(bytes(raw))
        star = mutant / "corrected_micrographs.star"
        star.write_text(star.read_text() + "# injected\n")
        control = grade(cot, a.base, mutant, geom)
        want_mrc = f"Movies/{stem0}.mrc: payload_sha256"
        want_star = "corrected_micrographs.star: STAR text differs"
        saw_mrc = any(d.startswith(want_mrc) for d in control["differences"])
        saw_star = want_star in control["differences"]
        report["negative_control"] = {
            "status": control["status"],
            "differences": control["differences"],
            "payload_offset": payload0,
            # Naming both injected differences, rather than counting them, so the
            # control cannot trip on an unrelated difference and look healthy.
            "tripped": control["status"] == "FAIL" and saw_mrc and saw_star,
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
