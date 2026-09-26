#!/usr/bin/env python3
"""Replay every captured global CUDA CCF spectrum through float FFTW.

Iteration 1 isolates the inverse-FFT contribution against matching inputs.
Later iterations also contain propagated input/reference differences.
"""

import argparse
import json
import pathlib
import re
import subprocess
import tempfile


def run_json(command):
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cpu", type=pathlib.Path)
    parser.add_argument("cuda", type=pathlib.Path)
    parser.add_argument("output", type=pathlib.Path)
    parser.add_argument("--replay", type=pathlib.Path, required=True)
    parser.add_argument("--comparator", type=pathlib.Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError(f"Refusing to overwrite: {args.output}")
    result = []
    with tempfile.TemporaryDirectory(prefix="issue36-fftw-replay-") as temporary:
        spectra = sorted(args.cuda.glob("g_i??_fccs_f???.bin"))
        if not spectra:
            raise ValueError("No global CCF spectra found")
        for spectrum in spectra:
            match = re.fullmatch(r"g_i(\d{2})_fccs_f(\d{3})", spectrum.stem)
            if not match:
                raise ValueError(f"Unexpected spectrum key: {spectrum}")
            iteration, frame = map(int, match.groups())
            prefix = f"g_i{iteration:02d}"
            tag = f"f{frame:03d}"
            info = json.loads(spectrum.with_suffix(".json").read_text())
            ny, complex_nx = info["shape"]
            nx = (complex_nx - 1) * 2
            replayed = pathlib.Path(temporary) / f"replayed_i{iteration:02d}_{tag}.bin"
            subprocess.run([str(args.replay), str(spectrum), str(replayed), str(nx), str(ny)], check=True)
            cpu_ccf = args.cpu / f"{prefix}_iccs_{tag}.bin"
            cuda_ccf = args.cuda / f"{prefix}_iccs_{tag}.bin"
            native = run_json([str(args.comparator), str(cpu_ccf), str(cuda_ccf), "f4", "f4"])
            replay = run_json([str(args.comparator), str(cpu_ccf), str(replayed), "f4", "f4"])
            result.append({"iteration": iteration, "frame": frame, "cpu_vs_cuda": native,
                           "cpu_vs_cuda_spectrum_fftw": replay})
            print(f"Replayed iteration {iteration} frame {frame:02d}: native {native['rmse']:.8g}, FFTW {replay['rmse']:.8g}", flush=True)
    args.output.write_text(json.dumps({"checkpoints": result}, indent=2) + "\n")


if __name__ == "__main__":
    main()
