#!/usr/bin/env python3
"""Header fields and raw sample statistics of an MRC movie (read-only; W-MRC-Q item 5).

For mode 0 it reports the IMOD stamp/flags (bit 0 of imodFlags: signed bytes), the byte
value histogram, and how many samples change value when read as signed int8 instead of
uint8 (any raw byte >= 128). For mode 1/6 it does the same for the 16-bit sign bit.
"""
import json
import struct
import sys

import numpy as np


def main(path):
    with open(path, "rb") as f:
        h = f.read(1024)
    nx, ny, nz, mode = struct.unpack("<4i", h[:16])
    amin, amax, amean = struct.unpack("<3f", h[76:88])
    nsymbt = struct.unpack("<i", h[92:96])[0]
    ext = h[104:108]
    stamp, flags = struct.unpack("<ii", h[152:160])
    rms = struct.unpack("<f", h[216:220])[0]
    nlabl = struct.unpack("<i", h[220:224])[0]
    out = {"file": path, "nx": nx, "ny": ny, "nz": nz, "mode": mode, "nsymbt": nsymbt,
           "header_amin": amin, "header_amax": amax, "header_amean": amean, "header_rms": rms,
           "exttyp": ext.decode("latin1"), "imodStamp": stamp, "imodStamp_is_IMOD": stamp == 1146047817,
           "imodFlags": flags, "imodFlags_bit0_signed_bytes": bool(flags & 1) if stamp == 1146047817 else None,
           "map": h[208:212].decode("latin1"), "machst": h[212:216].hex(), "nlabl": nlabl,
           "labels": [h[224 + 80 * i:224 + 80 * (i + 1)].rstrip(b"\0 ").decode("latin1")
                      for i in range(min(nlabl, 10))]}
    dt = {0: np.uint8, 1: np.int16, 6: np.uint16}.get(mode)
    if dt is None:
        print(json.dumps(out, indent=1))
        return
    n = nx * ny * nz
    raw = np.memmap(path, dtype=dt, mode="r", offset=1024 + nsymbt, shape=(n,))
    if mode == 0:
        hist = np.zeros(256, np.int64)
        for i in range(0, n, 1 << 26):
            hist += np.bincount(raw[i:i + (1 << 26)], minlength=256)
        ge128 = int(hist[128:].sum())
        vals = np.nonzero(hist)[0]
        out.update({"samples": n, "byte_min": int(vals.min()), "byte_max": int(vals.max()),
                    "samples_ge128": ge128, "frac_ge128": ge128 / n,
                    "hist_0_15": hist[:16].tolist(), "hist_120_135": hist[120:136].tolist(),
                    "hist_240_255": hist[240:].tolist(),
                    "signed_min": int(vals.min()) if vals.min() < 128 else int(np.int8(vals[vals >= 128].min())),
                    "unsigned_mean": float((hist * np.arange(256)).sum() / n),
                    "signed_mean": float((hist * np.arange(256).astype(np.uint8).view(np.int8)).sum() / n),
                    "values_changed_by_signed_read": ge128})
    else:
        hist_neg = 0
        mn, mx = None, None
        for i in range(0, n, 1 << 26):
            c = np.asarray(raw[i:i + (1 << 26)])
            cmin, cmax = int(c.min()), int(c.max())
            mn = cmin if mn is None else min(mn, cmin)
            mx = cmax if mx is None else max(mx, cmax)
            hist_neg += int((c.view("<u2") >= 32768).sum()) if mode == 1 else int((c >= 32768).sum())
        out.update({"samples": n, "min_as_stored_dtype": mn, "max_as_stored_dtype": mx,
                    "samples_with_bit15": hist_neg, "frac_bit15": hist_neg / n})
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
