#!/usr/bin/env python3
"""Actual pinned nvCOMP runner: per-chunk acceptance before any decoded byte is used.

The test-only shim alters descriptor readback on healthy compressed input. Native
kernel controls separately exercise inaccessible failed/short decoder output.
No corrupt-Deflate execution or genuinely poisoned CUDA context is tested.

The ingest is pipelined in chunks (docs/nvcomp_ingest_pipeline.md). The fixture
has 6 frames; MOTIONCORR_NVCOMP_CHUNK_FRAMES=2 gives three chunks on two slots.

  healthy, -c1, -c6    products identical across chunk sizes (3 chunks, 6 chunks
                       with slot reuse, and a 6-frame request that does not fit
                       the fixture's arena and halves); witness says nvcomp.
  status/size c0       whole-chunk decoder rejection precedes Adler; no gain
                       launch, no products under --ingest nvcomp.
  status c1 (middle)   chunk 1 refused after chunk 0 was converted: exactly one
                       gain launch, no products under the pin; under --ingest
                       auto the host reader produces products identical to healthy.
  adler c2 (late)      last chunk fails its checksum: exactly two gain launches,
                       no products under the pin (earlier chunks' gain/sum is not
                       published); under auto, identical products via fallback.

The gain-launch count is the negative control for "verify before consume": a
build that launches chunk k's gain/sum kernel before checking chunk k reports
c+1 launches for a refusal at chunk c and fails the c1/c2 rows.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

from run_nvcomp_reconstruction_controls import write_deflate_tiff
from test_gain_cache import synthetic_frames, write_star


def mrc_payloads(out):
    """MRC payload bytes (after the 1024-byte header) keyed by relative path."""
    return {str(p.relative_to(out)): p.read_bytes()[1024:]
            for p in sorted(out.rglob("*.mrc"))}


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

    def run(label, mode, chunk_frames, target_chunk=0, ingest="nvcomp"):
        out = root / label
        out.mkdir()
        witness = root / (label + ".witness")
        cmd = (["taskset", "-c", args.cpus] if args.cpus else []) + [
            str(args.binary.resolve()), "--i", "movies.star", "--o", str(out)+"/",
            "--use_own", "--gpu", "0", "--j", "1", "--max_io_threads", "1",
            "--patch_x", "2", "--patch_y", "2", "--max_iter", "1",
            "--bfactor", "150", "--seed", "1", "--angpix", "1.0", "--voltage", "300",
            "--ingest", ingest, "--ingest_witness", str(witness)]
        env = dict(os.environ, OMP_NUM_THREADS="1",
                   MOTIONCORR_NVCOMP_CHUNK_FRAMES=str(chunk_frames),
                   MC_NVCOMP_ACCEPTANCE_CHUNK=str(target_chunk))
        env.pop("MC_NVCOMP_ACCEPTANCE_FAULT", None)
        if mode != "healthy": env["MC_NVCOMP_ACCEPTANCE_FAULT"] = mode
        r = subprocess.run(cmd, cwd=inp, env=env, text=True, capture_output=True, timeout=180)
        text = r.stdout + r.stderr
        # Decoder diagnostics belong to the per-movie log, while wrapper
        # refusal and test-only readback witnesses are on the process streams.
        # Require and retain both actual surfaces; neither alone proves order.
        (root / (label + ".log")).write_text(text)
        movie_log = out / "Movies/control.log"
        if not movie_log.is_file():
            rows.append({"label": label, "returncode": r.returncode, "pass": False,
                         "command": cmd, "error": "actual movie diagnostic log missing"})
            (root / "result.json").write_text(json.dumps(rows, indent=2)+"\n")
            raise RuntimeError("actual movie diagnostic log missing: " + str(movie_log))
        text += "\n" + movie_log.read_text()
        products = sorted(str(p.relative_to(out)) for p in out.rglob("*")
                          if p.suffix.lower() in {".mrc", ".star"})
        m = re.search(r"\[nvcompaccept\] gain-launches=(\d+)", text)
        gains = int(m.group(1)) if m else -1
        taken = witness.read_text().split()[1] if witness.exists() else "none"
        return r, text, out, products, gains, taken, cmd

    rows = []
    # Healthy, at three chunkings. Products must not depend on the chunk size.
    reference = None
    for cf in (2, 1, 6):
        # The first row keeps the plain name: test_nvcomp_acceptance_diagnostics.py
        # reads healthy.log when the binary fails at startup.
        label = "healthy" if cf == 2 else f"healthy-c{cf}"
        r, text, out, products, gains, taken, cmd = run(label, "healthy", cf)
        # The 48x40 fixture's pre-FFT arena (48000 bytes) cannot hold a 6-frame
        # slot, so a 6-frame request halves until it fits, as the batch did
        # before the pipeline. Check against the chunking actually chosen.
        m = re.search(r"chunk=(\d+)/6 frames x (\d+) chunks", text)
        got_cf, n_chunks = (int(m.group(1)), int(m.group(2))) if m else (0, -2)
        payload = mrc_payloads(out)
        if reference is None and r.returncode == 0:
            reference = payload
        same = bool(payload) and payload == reference
        # The fit loop halves (6 -> 3 -> 1), so only those sizes are legitimate
        # outcomes of a 6-frame request; 1 and 2 must be taken as asked.
        halving = [6, 3, 1] if cf == 6 else [cf]
        ok = (r.returncode == 0 and products and taken == "nvcomp" and gains == n_chunks
              and got_cf in halving and n_chunks == (6 + got_cf - 1) // got_cf
              and same)
        rows.append({"label": label, "returncode": r.returncode, "products": products,
                     "chunk_frames": got_cf, "chunks": n_chunks,
                     "gain_launches": gains, "path": taken, "identical_to_c2": same,
                     "pass": bool(ok), "command": cmd})

    # Refusal before Adler on the first chunk (the pre-pipeline contract).
    for mode in ("status", "size"):
        label = f"{mode}-chunk0"
        r, text, out, products, gains, taken, cmd = run(label, mode, 2, 0)
        ok = (r.returncode != 0 and not products and "nvCOMP rejected strip 1 of frames [0,2)" in text
              and "failed its zlib Adler-32 check" not in text and gains == 0
              and all(f"chunk=0 phase={n} mode={mode}" in text for n in (1, 2, 3)))
        rows.append({"label": label, "returncode": r.returncode, "products": products,
                     "gain_launches": gains, "pass": bool(ok), "command": cmd})

    # Middle-chunk decoder rejection and late-chunk checksum failure.
    cases = (("status", 1, "nvCOMP rejected strip 1 of frames [2,4)"),
             ("adler", 2, "strip 0 of frames [4,6) failed its zlib Adler-32 check"))
    for mode, chunk, needle in cases:
        label = f"{mode}-chunk{chunk}-pinned"
        r, text, out, products, gains, taken, cmd = run(label, mode, 2, chunk)
        ok = (r.returncode != 0 and not products and needle in text and gains == chunk
              and f"chunk={chunk} phase=3 mode={mode}" in text)
        rows.append({"label": label, "returncode": r.returncode, "products": products,
                     "gain_launches": gains, "pass": bool(ok), "command": cmd})
        label = f"{mode}-chunk{chunk}-fallback"
        r, text, out, products, gains, taken, cmd = run(label, mode, 2, chunk, ingest="auto")
        same = mrc_payloads(out) == reference and reference is not None
        # A verification refusal records no CUDA error, so ingestMovie reports it
        # as NotApplicable and the runner takes the host reader (compact arm).
        ok = (r.returncode == 0 and products and needle in text and gains == chunk
              and taken not in ("nvcomp", "none") and same)
        rows.append({"label": label, "returncode": r.returncode, "products": products,
                     "gain_launches": gains, "path": taken, "identical_to_healthy": same,
                     "pass": bool(ok), "command": cmd})

    (root / "result.json").write_text(json.dumps(rows, indent=2)+"\n")
    print(json.dumps(rows, indent=2))
    return 0 if all(r["pass"] for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
