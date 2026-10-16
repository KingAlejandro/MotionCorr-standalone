#!/usr/bin/env python3
"""Page-for-page comparison of two PDFs by r50 grayscale raster.

PDFs are not byte-reproducible (Ghostscript writes dates), so equality is
defined as: same page count and identical PNG bytes for every page.

  pagecmp.py cmp A.pdf B.pdf            exit 0 iff identical pages
  pagecmp.py controls TREE              calibrate the comparator on TREE's own EPS
"""
import hashlib, os, subprocess, sys, tempfile
from pathlib import Path

JOIN = ["gs", "-sDEVICE=pdfwrite", "-dNOPAUSE", "-dBATCH", "-dSAFER", "-dDEVICEWIDTHPOINTS=800", "-dDEVICEHEIGHTPOINTS=800"]


def pages(pdf):
    with tempfile.TemporaryDirectory() as d:
        r = subprocess.run(["gs", "-q", "-dNOPAUSE", "-dBATCH", "-sDEVICE=pnggray", "-r50",
                            f"-sOutputFile={d}/p%03d.png", str(pdf)], capture_output=True, text=True)
        if r.returncode:
            raise SystemExit(f"gs failed on {pdf}: {r.stderr}")
        return [hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path(d).glob("p*.png"))]


def compare(a, b):
    pa, pb = pages(a), pages(b)
    if len(pa) != len(pb):
        return len(pa), len(pb), None
    return len(pa), len(pb), sum(x != y for x, y in zip(pa, pb))


def verdict(a, b):
    na, nb, diff = compare(a, b)
    if diff is None:
        return f"pages {na} vs {nb}: DIFFERENT (page count)", False
    return f"pages {na} vs {nb}: differing={diff} " + ("IDENTICAL" if diff == 0 else "DIFFERENT"), diff == 0


def render(lst_lines, out):
    with tempfile.NamedTemporaryFile("w", suffix=".lst", delete=False) as f:
        f.write("\n".join(lst_lines) + "\n")
    try:
        subprocess.run(JOIN + [f"-sOutputFile={out}", "@" + f.name], check=True, capture_output=True)
    finally:
        os.unlink(f.name)


def controls(tree):
    tree = Path(tree)
    hdr = (tree / "header.pdf.lst").read_text().split()
    bat = (tree / "batch.pdf.lst").read_text().split()
    ref = tree / "logfile.pdf"
    cases = {
        "c0 unperturbed EPS list (expect IDENTICAL)": hdr + bat,
        "c1 one batch EPS dropped (expect DIFFERENT)": hdr + bat[1:],
        "c2 two batch EPS swapped (expect DIFFERENT)": hdr + [bat[1], bat[0]] + bat[2:],
        "c3 header EPS dropped (expect DIFFERENT)": hdr[1:] + bat,
        "c4 batch before header (expect DIFFERENT)": bat + hdr,
    }
    ok = True
    with tempfile.TemporaryDirectory() as d:
        for name, lines in cases.items():
            out = Path(d) / "c.pdf"
            render(lines, out)
            text, same = verdict(ref, out)
            expect_same = name.startswith("c0")
            ok &= same == expect_same
            print(f"{name}: {text}")
    return 0 if ok else 1


if __name__ == "__main__":
    if sys.argv[1] == "cmp":
        text, same = verdict(sys.argv[2], sys.argv[3])
        print(text)
        sys.exit(0 if same else 1)
    sys.exit(controls(sys.argv[2]))
