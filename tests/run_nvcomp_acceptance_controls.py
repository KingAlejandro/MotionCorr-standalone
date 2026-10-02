#!/usr/bin/env python3
"""Actual pinned nvCOMP runner: whole-batch decoder rejection precedes Adler.

The test-only shim alters descriptor readback on healthy compressed input. Native
kernel controls separately exercise inaccessible failed/short decoder output.
No corrupt-Deflate execution or genuinely poisoned CUDA context is tested.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

from run_nvcomp_reconstruction_controls import write_deflate_tiff
from test_gain_cache import synthetic_frames, write_star


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--binary", type=Path, required=True)
    ap.add_argument("--workdir", type=Path)
    ap.add_argument("--cpus")
    args = ap.parse_args()
    root = args.workdir.resolve() if args.workdir else Path(tempfile.mkdtemp(prefix="mc-adler-accept-"))
    root.mkdir(parents=True, exist_ok=True)
    # Preserve prior runs; a supplied nonempty evidence directory is an error.
    if any(root.iterdir()):
        raise RuntimeError("workdir must be empty")
    inp = root / "input"
    (inp / "Movies").mkdir(parents=True)
    write_deflate_tiff(inp / "Movies/control.tiff", [[int(v) for v in f] for f in synthetic_frames()])
    write_star(inp / "movies.star", ["Movies/control.tiff"])
    rows = []
    for mode in ("healthy", "status", "size"):
        out = root / mode
        out.mkdir()
        witness = root / (mode + ".witness")
        cmd = (["taskset", "-c", args.cpus] if args.cpus else []) + [
            str(args.binary.resolve()), "--i", "movies.star", "--o", str(out)+"/",
            "--use_own", "--gpu", "0", "--j", "1", "--max_io_threads", "1",
            "--patch_x", "2", "--patch_y", "2", "--max_iter", "1",
            "--bfactor", "150", "--seed", "1", "--angpix", "1.0", "--voltage", "300",
            "--ingest", "nvcomp", "--ingest_witness", str(witness)]
        env = dict(os.environ, OMP_NUM_THREADS="1")
        env.pop("MC_NVCOMP_ACCEPTANCE_FAULT", None)
        if mode != "healthy": env["MC_NVCOMP_ACCEPTANCE_FAULT"] = mode
        r = subprocess.run(cmd, cwd=inp, env=env, text=True, capture_output=True, timeout=180)
        text = r.stdout + r.stderr
        (root / (mode + ".log")).write_text(text)
        products = sorted(str(p.relative_to(out)) for p in out.rglob("*")
                          if p.suffix.lower() in {".mrc", ".star"})
        if mode == "healthy":
            ok = r.returncode == 0 and products and witness.exists() and "nvcomp" in witness.read_text().split()
        else:
            ok = (r.returncode != 0 and not products and "nvCOMP rejected strip 1" in text
                  and "failed its zlib Adler-32 check" not in text
                  and all(f"phase={n} mode={mode}" in text for n in (1, 2, 3)))
        rows.append({"mode":mode, "returncode":r.returncode, "products":products,
                     "pass":bool(ok), "command":cmd})
    (root / "result.json").write_text(json.dumps(rows, indent=2)+"\n")
    print(json.dumps(rows, indent=2))
    return 0 if all(r["pass"] for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
