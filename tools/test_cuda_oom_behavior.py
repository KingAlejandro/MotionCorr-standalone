#!/usr/bin/env python3
"""Automated verification test for GPU Out-Of-Memory (OOM) and allocation failure behavior.

Verifies:
1. When GPU memory is exhausted, MotionCorr cleanly reports an allocation error to stderr.
2. MotionCorr exits with non-zero status (exit code 1).
3. An existing CPU reference MRC remains intact (SHA-256 unchanged).
4. No partial or corrupted output MRC/STAR files are generated in the destination.
"""

import argparse
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description="Test CUDA OOM allocation failure behavior")
    parser.add_argument("--repo-dir", type=Path, default=Path("."))
    parser.add_argument("--cuda-bin", type=Path, default=Path("build-cuda/motioncorr"))
    parser.add_argument("--gpu-id", type=int, default=1)
    parser.add_argument("--nvcc", type=str, default="/usr/local/cuda/bin/nvcc")
    parser.add_argument("--output-dir", type=Path, default=Path("test_oom_results"))
    parser.add_argument("--cpu-reference", type=Path, required=True,
                        help="Existing CPU-produced corrected MRC to preserve and checksum")
    args = parser.parse_args()

    repo = args.repo_dir.resolve()
    cuda_bin = (repo / args.cuda_bin).resolve()
    out = args.output_dir.resolve()
    cpu_ref = args.cpu_reference.resolve()
    synth_dir = repo / "test-data" / "synthetic"
    input_star = synth_dir / "synthetic_local_motion.star"

    if not cuda_bin.is_file():
        sys.exit(f"CUDA binary not found: {cuda_bin}")
    if not input_star.is_file():
        sys.exit(f"Input STAR fixture not found: {input_star}")
    if not cpu_ref.is_file():
        parser.error(f"CPU reference MRC not found: {cpu_ref}")
    with cpu_ref.open("rb") as f:
        header = f.read(212)
    if len(header) < 212 or header[208:212] != b"MAP ":
        parser.error(f"CPU reference is not an MRC file: {cpu_ref}")
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        parser.error(f"Output directory must be empty; refusing to remove existing files: {out}")

    nvcc_path = shutil.which("nvcc") or shutil.which(args.nvcc) or "/usr/local/cuda-12.8/bin/nvcc"
    if not Path(nvcc_path).is_file():
        sys.exit(f"nvcc compiler not found at: {nvcc_path}")

    out.mkdir(parents=True, exist_ok=True)

    # Preserve an actual CPU result supplied before this test starts.
    orig_sha = sha256_file(cpu_ref)
    print(f"[OOM Test] Existing CPU reference: {cpu_ref}")
    print(f"           Original SHA-256: {orig_sha}")

    # 2. Compile standalone vram_eater helper
    vram_eater_cu = out / "vram_eater.cu"
    vram_eater_bin = out / "vram_eater"
    vram_eater_cu.write_text("""#include <cuda_runtime.h>
#include <iostream>
#include <unistd.h>
#include <cstdlib>

int main(int argc, char** argv) {
    int dev = 0;
    if (argc > 1) dev = atoi(argv[1]);
    if (cudaSetDevice(dev) != cudaSuccess) return 1;
    size_t free_mem = 0, total_mem = 0;
    cudaMemGetInfo(&free_mem, &total_mem);
    size_t reserve = 50ULL * 1024ULL * 1024ULL; // leave 50 MB
    if (free_mem <= reserve) return 1;
    size_t to_alloc = free_mem - reserve;
    void* ptr = nullptr;
    if (cudaMalloc(&ptr, to_alloc) != cudaSuccess) return 1;
    std::cout << "ALLOCATED_MIB: " << to_alloc / (1024 * 1024) << std::endl;
    sleep(60);
    cudaFree(ptr);
    return 0;
}
""")

    print(f"[OOM Test] Compiling {vram_eater_cu} with {nvcc_path}...")
    comp_res = subprocess.run([nvcc_path, "-O3", str(vram_eater_cu), "-o", str(vram_eater_bin)],
                              capture_output=True, text=True)
    if comp_res.returncode != 0:
        sys.exit(f"Failed to compile vram_eater: {comp_res.stderr}")

    # 3. Launch vram_eater in background
    eater_proc = subprocess.Popen([str(vram_eater_bin), str(args.gpu_id)],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        # Wait until VRAM is allocated
        line = eater_proc.stdout.readline()
        print(f"[OOM Test] VRAM eater active: {line.strip()} on GPU {args.gpu_id}")

        # 4. Invoke MotionCorr expecting allocation failure
        target_out = out / "candidate_cuda_output.mrc"
        mc_cmd = [
            str(cuda_bin), "--use_own",
            "--i", str(input_star),
            "--o", str(target_out),
            "--gpu", str(args.gpu_id)
        ]
        print(f"[OOM Test] Running MotionCorr with exhausted VRAM: {' '.join(mc_cmd)}")
        mc_res = subprocess.run(mc_cmd, capture_output=True, text=True, cwd=str(synth_dir))

        print(f"[OOM Test] MotionCorr exited with code: {mc_res.returncode}")

        # 5. Verification checks
        exit_code_failed = (mc_res.returncode != 0)
        has_oom_msg = ("out of memory" in mc_res.stderr or "A GPU-function failed to execute" in mc_res.stderr or "out of memory" in mc_res.stdout)
        cpu_intact = cpu_ref.is_file() and sha256_file(cpu_ref) == orig_sha
        # No partial corrected image or STAR metadata should be left behind.
        partial_outputs = [p for p in out.rglob("*") if p.is_file() and p.suffix in {".mrc", ".star"}]
        no_corrupt_output = not partial_outputs

        print(f"  Check 1: Non-zero exit code: {exit_code_failed} (exit {mc_res.returncode})")
        print(f"  Check 2: OOM diagnostic reported: {has_oom_msg}")
        print(f"  Check 3: CPU reference output file intact: {cpu_intact}")
        print(f"  Check 4: No corrupt/partial MRC or STAR outputs written: {no_corrupt_output}")

        passed = exit_code_failed and has_oom_msg and cpu_intact and no_corrupt_output
        print(f"\n[OOM Test] Overall Verdict: {'PASS' if passed else 'FAIL'}")
        return 0 if passed else 1

    finally:
        eater_proc.terminate()
        try:
            eater_proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            eater_proc.kill()


if __name__ == "__main__":
    sys.exit(main())
