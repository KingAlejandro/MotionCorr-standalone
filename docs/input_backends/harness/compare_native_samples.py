#!/usr/bin/env python3
"""Decoded-sample oracle, comparator half.

Compares every native sample MotionCorr staged (dump_native_samples) against an
independent decode of the same file by tifffile/imagecodecs -- a different
codec implementation from LibTIFF, so a shared bug is not simply reproduced on
both sides.

Two things are asserted, not assumed:

  * the row order. rwTIFF flips each frame to MRC bottom-up order on read, so
    the oracle compares against a vertically flipped independent decode. The
    unflipped comparison is run as well and must FAIL, which is what makes the
    flipped PASS mean something.
  * the comparator's own power. Three mutations of the independent decode --
    a within-row transposition, a one-bit flip and a dropped final frame --
    must each be detected. A within-row transposition in particular leaves
    every row sum unchanged, which is the defect a row-sum check cannot see.

Exit 0 only if the identity comparison passes and every control fires.
"""
import argparse, json, sys
import numpy as np
import tifffile


def read_dump(path):
    with open(path, "rb") as fh:
        nx, ny, nn, bps = np.frombuffer(fh.read(32), dtype="<i8")
        dt = {1: np.uint8, 2: np.uint16}[int(bps)]
        data = np.frombuffer(fh.read(), dtype=dt)
    want = int(nx) * int(ny) * int(nn)
    if data.size != want:
        raise SystemExit(f"{path}: {data.size} samples, header declares {want}")
    return data.reshape(int(nn), int(ny), int(nx))


def independent_decode(path):
    with tifffile.TiffFile(path) as tf:
        return np.stack([p.asarray() for p in tf.pages])


def compare(a, b):
    if a.shape != b.shape:
        return dict(shape_match=False, staged=list(a.shape), independent=list(b.shape),
                    differing=-1)
    diff = a != b
    n = int(diff.sum())
    out = dict(shape_match=True, compared=int(a.size), differing=n)
    if n:
        idx = np.argwhere(diff)[0]
        out["first_differing"] = dict(frame=int(idx[0]), y=int(idx[1]), x=int(idx[2]),
                                      staged=int(a[tuple(idx)]),
                                      independent=int(b[tuple(idx)]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("movie")
    ap.add_argument("dump")
    ap.add_argument("--json", default=None)
    a = ap.parse_args()

    staged = read_dump(a.dump)
    indep = independent_decode(a.movie)
    if indep.dtype != staged.dtype:
        raise SystemExit(f"sample type differs: staged {staged.dtype}, "
                         f"independent {indep.dtype}")

    flipped = indep[:, ::-1, :]
    report = {
        "movie": a.movie,
        "sample_dtype": str(staged.dtype),
        "frames": int(staged.shape[0]),
        "geometry": [int(staged.shape[2]), int(staged.shape[1])],
        "identity_vs_flipped_independent": compare(staged, flipped),
        "controls": {},
    }

    # Row order: the unflipped decode must disagree, otherwise the flip is not
    # being tested at all (it is a no-op on a vertically symmetric frame).
    unflipped = compare(staged, indep)
    report["controls"]["unflipped_row_order_detected"] = unflipped["differing"] != 0

    # Within-row transposition: invisible to any row-sum or row-hash check.
    perm = flipped.copy()
    f, y = 0, flipped.shape[1] // 2
    x0, x1 = 1, flipped.shape[2] - 2
    if perm[f, y, x0] == perm[f, y, x1]:
        # Two equal samples would make the "permutation" a no-op and the control
        # vacuous; find a pair that actually differs. If no row in the frame has
        # two different samples there is nothing to permute, and the control is
        # reported as not applicable rather than silently passing on a no-op.
        x0, x1 = None, None
        for yy in range(flipped.shape[1]):
            row = perm[f, yy]
            neq = np.flatnonzero(row != row[0])
            if neq.size:
                y, x0, x1 = yy, 0, int(neq[0])
                break
    if x0 is None:
        report_perm_applicable = False
        c = dict(shape_match=True, compared=int(staged.size), differing=0,
                 note="no row in frame 0 holds two different samples")
    else:
        report_perm_applicable = True
        perm[f, y, x0], perm[f, y, x1] = perm[f, y, x1], perm[f, y, x0]
        c = compare(staged, perm)
    report["controls"]["row_sums_unchanged"] = bool(
        (perm.sum(axis=2, dtype=np.int64) == flipped.sum(axis=2, dtype=np.int64)).all())
    report["controls"]["within_row_permutation_applicable"] = report_perm_applicable
    report["controls"]["within_row_permutation_detected"] = (
        c["differing"] != 0 if report_perm_applicable else False)
    report["controls"]["within_row_permutation"] = c

    # One-bit flip in the last frame.
    bit = flipped.copy()
    bit[-1, -1, -1] = bit[-1, -1, -1] ^ np.array(1, dtype=bit.dtype)
    report["controls"]["single_bit_flip_detected"] = compare(staged, bit)["differing"] != 0

    # Missing final frame.
    short = compare(staged, flipped[:-1])
    report["controls"]["dropped_frame_detected"] = not short["shape_match"]

    ok = (report["identity_vs_flipped_independent"]["differing"] == 0
          and report["identity_vs_flipped_independent"]["shape_match"]
          and all(v for k, v in report["controls"].items() if k.endswith("_detected"))
          and report["controls"]["row_sums_unchanged"])
    report["verdict"] = "PASS" if ok else "FAIL"

    text = json.dumps(report, indent=1)
    print(text)
    if a.json:
        open(a.json, "w").write(text)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
