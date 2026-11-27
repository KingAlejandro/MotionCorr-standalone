#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Device-free shim and acceptance-predicate controls; NOT native CUDA evidence."""
import argparse
import json
import os
from pathlib import Path
import resource
import subprocess
import tempfile

from run_nvcomp_reconstruction_controls import write_deflate_tiff
from run_tiff_identity_controls import identity
from run_tiff_identity_later_chunk_controls import CONVERTED, LATER, mutation_checks, write_expected
from test_gain_cache import synthetic_frames


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host-binary", type=Path, required=True)
    args = ap.parse_args()
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    frames = [[int(v) for v in f] for f in synthetic_frames()]
    results = []
    with tempfile.TemporaryDirectory(prefix="mc-tiff-host-") as tmp:
        root = Path(tmp)
        expected = root / "expected.bin"
        write_expected(expected, frames)
        for mode in ("healthy", "fortified", "launch-error", "sync-error", "copy-error",
                     "frame-mismatch", "sum-mismatch", "no-consumption", "wrong-kernel"):
            for mutation in ("grow", "replace"):
                movie = root / f"{mode}-{mutation}.tiff"
                replacement = root / "replacement.tiff"
                write_deflate_tiff(movie, frames)
                write_deflate_tiff(replacement, [[v + 1 for v in f] for f in frames])
                before = identity(movie)
                env = dict(os.environ, MC_TIFF_CHANGE_POINT="later-strip-read", MC_TIFF_CHANGE_MODE=mutation,
                           MC_TIFF_CONVERSION_EXPECTED=str(expected), MC_TIFF_REPLACEMENT=str(replacement))
                r = subprocess.run([str(args.host_binary.resolve()), str(movie), mode], env=env,
                                   capture_output=True, text=True, timeout=5)
                text = r.stdout + r.stderr
                good = mode in ("healthy", "fortified")
                changed = identity(movie) != before
                assert changed == good, (mode, mutation, r.returncode, text)
                assert (CONVERTED in text) == good, (mode, mutation, text)
                assert (LATER in text) == good, (mode, mutation, text)
                if good:
                    assert r.returncode == 0 and text.index(CONVERTED) < text.index(LATER)
                elif mode != "wrong-kernel":
                    assert r.returncode != 0, (mode, mutation, text)
                results.append(dict(mode=mode, mutation=mutation, passed=True))
        marker = "[tiffidentity] changed mode=grow point=later-strip-read"
        ordered = "\n".join((CONVERTED, LATER, marker))
        before, after = [1, 2, 100, 0], [1, 2, 116, 1]
        assert all(mutation_checks(ordered, before, after, "a", "b", "grow").values())
        for text in (ordered.replace(CONVERTED, ""), ordered.replace(LATER, ""),
                     ordered.replace(marker, ""), ordered + "\n" + CONVERTED,
                     "\n".join((marker, CONVERTED, LATER))):
            assert not all(mutation_checks(text, before, after, "a", "b", "grow").values())
        assert not all(mutation_checks(ordered, before, before, "a", "b", "grow").values())
    print(json.dumps(results, indent=2))
    print("PASS: 18 fake-CUDA host controls and missing/duplicate/order/identity predicate rejections; native UNRUN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
