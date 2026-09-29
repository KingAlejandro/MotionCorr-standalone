#!/usr/bin/env python3
"""Compare two output trees for output modes the manifest comparator does not model.

compare_output_trees.py expects exactly one corrected MRC per movie, so it cannot
grade a run that also writes _noDW, _EVN, _ODD and _PS products. This driver takes
the whole product inventory instead and compares, for every file:

  *.mrc   header bytes 0-224 and the payload from 1024 on, exactly. The 224-1024
          label block is excluded because it carries a creation timestamp.
  *.star  the text with each arm's own output root replaced by a placeholder. The
          joint STAR embeds the absolute output directory, so two arms writing to
          differently named directories differ there for a reason that is not a
          product difference. Nothing else is normalised.

It runs four negative controls afterwards and reports FAIL unless all four behave:
a flipped MRC payload bit and an appended STAR line must both be detected, a
non-path STAR field edit must be detected (so the normalisation is not swallowing
real differences), and a pure output-root rename must NOT be reported.

Usage: compare_requested_modes.py <base-out> <candidate-out> [--json-out F]
"""
import argparse, hashlib, json, shutil, sys, tempfile
from pathlib import Path


def inventory(root):
    return sorted(p.relative_to(root).as_posix()
                  for p in root.rglob("*") if p.is_file() and p.suffix in (".mrc", ".star"))


def digest(root, rel):
    p = root / rel
    if p.suffix == ".mrc":
        raw = p.read_bytes()
        return hashlib.sha256(raw[:224] + raw[1024:]).hexdigest()
    text = p.read_text(errors="replace").replace(str(root), "<OUTPUT_ROOT>")
    return hashlib.sha256(text.encode()).hexdigest()


def compare(base, cand):
    ia, ib = inventory(base), inventory(cand)
    if ia != ib:
        return {"status": "FAIL", "files": len(ia),
                "differences": [f"inventory differs: {sorted(set(ia) ^ set(ib))[:10]}"]}
    diffs = [r for r in ia if digest(base, r) != digest(cand, r)]
    return {"status": "FAIL" if diffs else "PASS", "files": len(ia),
            "differences": [f"{r}: differs" for r in diffs]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base", type=Path)
    ap.add_argument("candidate", type=Path)
    ap.add_argument("--json-out", type=Path)
    a = ap.parse_args()
    base, cand = a.base.resolve(), a.candidate.resolve()
    report = compare(base, cand)
    report["base"], report["candidate"] = str(base), str(cand)

    controls = {}
    with tempfile.TemporaryDirectory() as tmp:
        def fresh(name):
            d = Path(tmp) / name
            shutil.copytree(cand, d)
            return d
        inv = inventory(cand)
        one_mrc = next(r for r in inv if r.endswith(".mrc"))
        joint = next(r for r in inv if Path(r).parent.as_posix() == ".")

        m = fresh("mrc")
        raw = bytearray((m / one_mrc).read_bytes()); raw[1024] ^= 0x01
        (m / one_mrc).write_bytes(bytes(raw))
        controls["flipped_mrc_payload_bit_detected"] = compare(base, m)["status"] == "FAIL"

        m = fresh("starline")
        (m / joint).write_text((m / joint).read_text() + "# injected\n")
        controls["appended_star_line_detected"] = compare(base, m)["status"] == "FAIL"

        m = fresh("starfield")
        t = (m / joint).read_text()
        # Change a numeric/metadata token, not a path: take the last whitespace
        # separated token of the last non-empty line.
        lines = [l for l in t.splitlines() if l.strip()]
        parts = lines[-1].split()
        parts[-1] = parts[-1] + "X"
        lines[-1] = " ".join(parts)
        (m / joint).write_text("\n".join(lines) + "\n")
        controls["star_field_edit_detected"] = compare(base, m)["status"] == "FAIL"

        m = Path(tmp) / "renamed_root"
        shutil.copytree(cand, m)
        controls["pure_output_root_rename_not_reported"] = compare(cand, m)["status"] == "PASS"

    report["negative_controls"] = controls
    ok = report["status"] == "PASS" and all(controls.values())
    report["overall"] = "PASS" if ok else "FAIL"
    if a.json_out:
        a.json_out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"requested-modes comparison: {report['status']}; files={report['files']}; "
          f"differences={len(report['differences'])}")
    for d in report["differences"][:20]:
        print("  DIFF", d)
    for k, v in controls.items():
        print(f"  control {k}={v}")
    print("OVERALL", report["overall"])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
