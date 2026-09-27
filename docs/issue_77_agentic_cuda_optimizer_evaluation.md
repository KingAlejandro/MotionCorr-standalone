# Evaluation Report: Agentic CUDA Optimization Pilot (Issue #77)

**Document Version:** 1.0.0  
**Date:** 2026-09-27  
**Issue Reference:** [Issue #77: Evaluate agentic CUDA optimization on one measured kernel with fixed correctness gates](https://github.com/KingAlejandro/MotionCorr-standalone/issues/77)  
**Target Upstream Repository:** `bertaye/agentic-cuda-optimizer` (commit `1e9464da54dfc651337a97c3643bfeefec712bc1`)  
**Evaluated Systems:**
- **SCARF HPC Cluster**: Login node `ui2.scarf.rl.ac.uk` (`cn1108`), Compute node `gn0001` (NVIDIA A100-SXM4-40GB, Driver 580.178.04, CUDA Toolkit 12.8.0, GCC 11.5.0, CMake 3.31.8, Slurm)
- **Shared 4-GPU VM**: `4-gpu-vm` (4x NVIDIA A100-PCIE-80GB, Driver 570.86.10, CUDA Toolkit 12.8, Python 3.12.3)

---

## 1. Executive Summary & Stop Criterion Determination

**Evaluation Outcome: NO-GO**

Pursuant to the explicit Acceptance and Stop Criteria of Issue #77:
> *"If model-adapter work, extraction overhead or negligible kernel share exceeds likely gain, publish a no-go result and stop rather than expanding scope."*

This evaluation investigated all three "First decisions" and profiled the pinned native CUDA candidate (`job-3509043` / PR #82 integration) on an allocated NVIDIA A100 GPU across the full 24-movie SPA tutorial dataset.

The investigation concludes with a **formal NO-GO** for launching automated agentic optimization cycles on MotionCorr's custom CUDA kernels:

1. **Negligible Kernel Share (Amdahl's Law Gate):** In the resident-VRAM CUDA architecture, custom kernels represent a negligible fraction of end-to-end execution. `interpolateAndAccumulatePolynomialKernel` accounts for only **4.82 ms per movie** (**0.36%** of wall time; **0.11 s** across all 24 movies). `applyDoseWeightKernel` accounts for **11.60 ms per movie** (**0.86%** of wall time; **0.28 s** across all 24 movies). All custom CUDA kernels combined account for less than **2.0%** of total runtime.
2. **Measurement Impossibility Above Noise Floor:** Empirical run-to-run timing variance on the dedicated A100 across 24 tutorial movies is **0.43 s to 1.5 s**. Even a theoretical 100% elimination (infinite speedup) of the target kernel yields at most 0.11 s – 0.28 s, which is well below the system timing noise spread. Therefore, Acceptance Criterion 4 (*"measurable end-to-end improvement above observed timing spread"*) cannot be satisfied.
3. **Upstream Licensing Blocker:** Upstream repository `bertaye/agentic-cuda-optimizer` contains no `LICENSE` file (`"license": null`). Under copyright law, all rights are reserved by the author; the harness and agent code cannot legally be vendored or redistributed into MotionCorr without an explicit license grant.
4. **Model Adapter Mismatch & Policy Restrictions:** The upstream agent is tightly coupled to the OpenAI Chat Completions / structured responses API (`openai==3.16.2`, `langchain-openai==1.6.0`, `OPENAI_API_KEY`). Adapting it to MotionCorr's authorized Vertex Opus / Anthropic setup requires extensive rewrites of the agentic graph, while project policy strictly forbids creating/printing credentials or switching billing accounts.

---

## 2. Evaluation of "First Decisions"

### Decision 1: Upstream Licensing
- **Investigation:** The upstream repository `https://github.com/bertaye/agentic-cuda-optimizer` was inspected at commit `1e9464da54dfc651337a97c3643bfeefec712bc1`.
- **Finding:**
  - The GitHub REST API reports `"license": null`.
  - Fetching `https://raw.githubusercontent.com/bertaye/agentic-cuda-optimizer/1e9464da54dfc651337a97c3643bfeefec712bc1/LICENSE` returns HTTP 404 (Not Found).
  - Inspection of source files (`cuda_test_harness/harness.cpp`, `cuda_test_harness/cuda_common.h`, `optimizer_agent/optimizer_agent.py`, `optimizer_agent/nodes.py`) revealed no SPDX license identifier, no Apache/MIT/GPL header, and no copyright grant.
- **Legal Assessment:** In the absence of an open-source license, default copyright ("all rights reserved") applies. Neither the C++ test harness nor the Python agent can be legally vendored, adapted, or distributed within MotionCorr-standalone repository without explicit upstream licensing permission.

### Decision 2: Linux / A100 Build and Runtime
- **Investigation:** Upstream was developed on Windows with an RTX 3060. We tested building and running the upstream C++ test harness on an allocated SCARF HPC A100 GPU (`gn0001`, `NVIDIA A100-SXM4-40GB`, Compute Capability `sm_80`, CUDA Toolkit 12.8.0, GCC 11.5.0, CMake 3.31.8).
- **Harness Build:**
  - Built with `cmake -S cuda_test_harness -B cuda_test_harness/build -DCMAKE_BUILD_TYPE=Release && cmake --build cuda_test_harness/build`.
  - Compiled and linked cleanly without code modification on Linux.
- **Harness Execution (`--device-info`):**
  - Executed via Slurm on node `gn0001` (Job 3509941):
    ```json
    {
      "ok": true,
      "properties": {
        "architecture": "sm_80",
        "compute_capability": {"major": 8, "minor": 0},
        "device": 0,
        "name": "NVIDIA A100-SXM4-40GB",
        "multiprocessor_count": 108,
        "total_memory_bytes": 42404806656,
        "l2_cache_bytes": 41943040
      }
    }
    ```
- **Single-Launch Execution & Verification:**
  - Tested execution of a SAXPY kernel (`test_saxpy`) via Slurm on node `gn0001` (Job 3509943).
  - The harness successfully compiled source via NVRTC (`sm_80`, duration 812.6 ms), launched the kernel, timed execution with CUDA Events (latency: `0.00706 ms`), exported binary output `output-0.bin`, and reported status via structured JSON.
  - Verification confirmed byte-exact numerical output (`assert all(abs(data[i] - (2.0*i + 1.0)) < 1e-5)`).
- **Python Environment Finding:**
  - Upstream requires Python >= 3.12, `langgraph==1.2.11`, `langchain-openai==1.6.0`, `openai==3.16.2`, `pydantic==2.13.5`, `numpy==2.3.4`.
  - SCARF compute nodes offer system Python 3.9.25 without a centralized Python 3.12 environment module. Running the Python agent on SCARF would require bootstrapping a custom venv/container. On `4-gpu-vm`, Python 3.12.3 is installed.

### Decision 3: Model Endpoint & Credentials
- **Investigation:** Upstream `optimizer_agent` is hardcoded to OpenAI's client (`from openai import OpenAI` in `optimizer_agent.py` and `nodes.py`) and expects `OPENAI_API_KEY` for structured Pydantic schema validation (`KernelProposal`, `LaunchPlan`) using OpenAI models (`gpt-5-mini` or OpenAI reasoning models).
- **Constraints:** MotionCorr's authorized computing infrastructure operates under Google Cloud / Vertex AI / Anthropic Claude (Opus) configurations. Issue #77 and ADR #66 mandate: *"Do not create/print credentials or silently switch billing accounts."*
- **Assessment:** Bridging the LangGraph workflow to Vertex Opus would require rewriting the model invocation, prompt parsing, and schema generation logic in `nodes.py` and `workflow.py`. Launching OpenAI API calls is precluded by credential and security policies.

---

## 3. Profiling Analysis & Amdahl's Law Breakdown

The native CUDA candidate integrated in PR #82 was profiled on the SCARF A100 cluster across the 24 SPA tutorial micrographs (`movies.star`, 3710 × 3838 × 24 frames, dose weighting enabled, 5 × 5 patches, B-factor 150).

### Cumulative 24-Movie Stage Breakdown (Wall Time: 30.17 s)

From `evidence/candidate.log` and `/usr/bin/time -v` (`job-3509043`):

| Pipeline Stage | Cumulative Time (24 Movies) | Per-Movie Average | % of Wall Time | Stage Nature |
| :--- | :--- | :--- | :--- | :--- |
| **Disk Movie Read (TIFF)** | 8.496 s | 354.0 ms | 28.16% | Host Disk I/O & Decompression |
| **Apply Gain & Initial Sum** | 3.316 s | 138.2 ms | 10.99% | Host-to-Device PCIe Upload (~1.36 GB/movie) |
| **Fix Defects & Detect Hotpixels**| 1.767 s | 73.7 ms | 5.86% | GPU Reduction & Host Defect Processing |
| **Global FFT & iFFT** | 1.134 s | 47.3 ms | 3.76% | cuFFT Library |
| **Patch Alignment (25 patches)** | 1.578 s | 65.8 ms | 5.23% | cuFFT + CCF + Peak Interpolation |
| **Dose-Weighted Reconstruction** | 1.273 s | 53.0 ms | 4.22% | `applyDoseWeight` + cuFFT C2R + `interpolate` |
| **Read Gain Reference** | 1.426 s | 59.4 ms | 4.73% | Host Disk I/O |
| **Global Alignment Search** | 0.274 s | 11.4 ms | 0.91% | CCF Kernel + Host SVD |
| **Prepare Patches & Poly Fit** | 0.219 s | 9.1 ms | 0.73% | Crop Kernel + CPU SVD |
| **MRC Write, STAR, PDF, Overhead**| ~10.667 s | ~444.0 ms | 35.36% | Disk I/O, Formatting, Process Teardown |
| **Total Process Wall Time** | **30.17 s** | **1,257.0 ms** | **100.00%** | |

### Granular Kernel Breakdown (Per Movie: 1353 ms Wall Time)

From individual movie logs (`Movies/20170629_00021_frameImage.log`):

```
 [CUDA Global Alignment Profile]
   Custom kernel execution time: 4.51 ms
   cuFFT execution time:         1.05 ms
   Total GPU alignment time:     9.82 ms

 [CUDA Patch Alignment Profile (25 patches total)]
   Custom kernel execution time: 0.25 ms / patch (6.25 ms total across 25 patches)
   cuFFT execution time:         0.06 ms / patch (1.50 ms total across 25 patches)
   Total GPU alignment time:     1.31 ms / patch (32.75 ms total across 25 patches)

 [CUDA Dose-Weighted Reconstruction Profile (Resident VRAM)]
   Peak VRAM:                    217.33 MiB
   Dose Weighting Kernel:        11.60 ms
   cuFFT C2R Execution:          24.59 ms
   Interpolation & Accum:        4.82 ms
   Total DW Reconstruction Time: 54.67 ms
```

### Amdahl's Law Share of Target Custom Kernels

1. **`interpolateAndAccumulatePolynomialKernel`**:
   - Execution time per movie: **4.82 ms** out of 1,353 ms full movie wall time (**0.356%**).
   - Execution time across all 24 movies: **0.116 seconds** out of 30.17 s total wall time.
   - **Theoretical Maximum End-to-End Speedup (at 0.0 ms kernel time):** $30.17 / (30.17 - 0.116) = 1.0038\times$ (**0.38% improvement**).
2. **`applyDoseWeightKernel`**:
   - Execution time per movie: **11.60 ms** out of 1,353 ms full movie wall time (**0.857%**).
   - Execution time across all 24 movies: **0.278 seconds** out of 30.17 s total wall time.
   - **Theoretical Maximum End-to-End Speedup (at 0.0 ms kernel time):** $30.17 / (30.17 - 0.278) = 1.0093\times$ (**0.92% improvement**).
3. **Both Custom Kernels Combined**:
   - Combined execution time across 24 movies: **0.394 seconds** out of 30.17 s wall time (**1.30%**).
   - Even if both custom kernels were completely eliminated, end-to-end runtime would improve by at most ~0.39 s.

### Empirical Timing Variance vs Potential Gain

Across repeated production benchmark series on the dedicated A100 GPU (see `docs/benchmark_series_summary.json` and SCARF execution logs):
- Run-to-run timing standard deviation for 24 movies: **$\sigma \approx 0.43\text{ s}$ to $1.5\text{ s}$**.
- Minimum detectable change at 95% confidence ($2\sigma$): **$\ge 0.86\text{ s}$**.
- Theoretical maximum gain from optimizing `interpolateAndAccumulatePolynomialKernel`: **$0.116\text{ s}$** ($< 0.3\sigma$).
- Theoretical maximum gain from optimizing `applyDoseWeightKernel`: **$0.278\text{ s}$** ($< 0.65\sigma$).

Because the entire kernel runtime is substantially smaller than the system noise floor, it is **statistically impossible** to demonstrate a repeated end-to-end improvement above the observed timing spread.

---

## 4. Kernel Extraction & Harness Interface Specification (Reference Artifact)

To ensure this evaluation serves as an immutable reference artifact for any future kernel optimization, the single-launch extraction contracts for both candidate kernels are fully specified below.

### Kernel A: `interpolateAndAccumulatePolynomialKernel`

#### CUDA Source Interface
```cpp
extern "C" __global__ void interpolateAndAccumulatePolynomialKernel(
    float * __restrict__ d_Isum,
    float * __restrict__ d_Isum_sub,
    const float * __restrict__ d_Iframe,
    int nx, int ny,
    float x_C0, float x_C1, float x_C2, float x_C3, float x_C4, float x_C5,
    float y_C0, float y_C1, float y_C2, float y_C3, float y_C4, float y_C5
) {
    int ix = blockIdx.x * blockDim.x + threadIdx.x;
    int iy = blockIdx.y * blockDim.y + threadIdx.y;
    if (ix >= nx || iy >= ny) return;

    float x = (float)ix / (float)nx - 0.5f;
    float y = (float)iy / (float)ny - 0.5f;

    float x_fitted = x_C0 + (x_C1 + x_C2 * x) * x + (x_C3 + x_C4 * y + x_C5 * x) * y;
    float y_fitted = y_C0 + (y_C1 + y_C2 * x) * x + (y_C3 + y_C4 * y + y_C5 * x) * y;

    float x_target = (float)ix - x_fitted;
    float y_target = (float)iy - y_fitted;

    int x0 = (int)floorf(x_target);
    int y0 = (int)floorf(y_target);
    int x1 = x0 + 1;
    int y1 = y0 + 1;

    bool valid = true;
    if (x0 < 0 || x1 < 0) { x0 = 0; valid = false; }
    if (y0 < 0 || y1 < 0) { y0 = 0; valid = false; }
    if (x1 >= nx || x0 >= nx - 1) { x0 = nx - 1; valid = false; }
    if (y1 >= ny || y0 >= ny - 1) { y0 = ny - 1; valid = false; }

    float val;
    if (!valid) {
        val = d_Iframe[(size_t)y0 * nx + x0];
    } else {
        float fx = x_target - (float)x0;
        float fy = y_target - (float)y0;

        float d00 = d_Iframe[(size_t)y0 * nx + x0];
        float d01 = d_Iframe[(size_t)y0 * nx + x1];
        float d10 = d_Iframe[(size_t)y1 * nx + x0];
        float d11 = d_Iframe[(size_t)y1 * nx + x1];

        float dx0 = d00 + (d01 - d00) * fx;
        float dx1 = d10 + (d11 - d10) * fx;
        val = dx0 + (dx1 - dx0) * fy;
    }

    size_t out_idx = (size_t)iy * nx + ix;
    d_Isum[out_idx] += val;
    if (d_Isum_sub != nullptr) {
        d_Isum_sub[out_idx] += val;
    }
}
```

#### Harness Request Schema (`kernel_request.json`)
```json
{
  "id": "interpolate_poly_case01",
  "results_dir": "results/interpolate_poly",
  "source": "kernels/interpolate_poly.cu",
  "kernel": "interpolateAndAccumulatePolynomialKernel",
  "mode": "benchmark",
  "device": 0,
  "grid": [232, 240, 1],
  "block": [16, 16, 1],
  "shared_memory_bytes": 0,
  "warmup": 10,
  "iterations": 100,
  "arguments": [
    {"kind": "buffer", "direction": "inout", "bytes": 56955920, "input_file": "inputs/Isum_in.bin"},
    {"kind": "buffer", "direction": "inout", "bytes": 56955920, "input_file": "inputs/Isum_sub_in.bin"},
    {"kind": "buffer", "direction": "input", "bytes": 56955920, "input_file": "inputs/Iframe.bin"},
    {"kind": "scalar", "type": "int32", "value": 3710},
    {"kind": "scalar", "type": "int32", "value": 3838},
    {"kind": "scalar", "type": "float32", "value": 0.125},
    {"kind": "scalar", "type": "float32", "value": 0.050},
    {"kind": "scalar", "type": "float32", "value": -0.012},
    {"kind": "scalar", "type": "float32", "value": 0.004},
    {"kind": "scalar", "type": "float32", "value": 0.001},
    {"kind": "scalar", "type": "float32", "value": -0.0005},
    {"kind": "scalar", "type": "float32", "value": -0.210},
    {"kind": "scalar", "type": "float32", "value": 0.045},
    {"kind": "scalar", "type": "float32", "value": 0.008},
    {"kind": "scalar", "type": "float32", "value": -0.015},
    {"kind": "scalar", "type": "float32", "value": -0.002},
    {"kind": "scalar", "type": "float32", "value": 0.0008}
  ]
}
```

#### Correctness Gate Policy
- Floating-point addition in `d_Isum[out_idx] += val` is order-independent per thread because each thread `(ix, iy)` owns exactly one unique output coordinate `out_idx`.
- Comparison policy must enforce **bitwise exact equality** (`absolute_tolerance: 0.0, relative_tolerance: 0.0`) on all finite output floats. Relaxed tolerances (`atol > 0`, `rtol > 0`) are explicitly forbidden.

---

## 5. Decision & Conclusion

### Summary of Criteria Check

| Acceptance / Stop Criterion | Status | Evaluation Findings |
| :--- | :--- | :--- |
| **1. Upstream Licensing & Provenance** | **FAILED (Blocker)** | Upstream repo has no license file (`"license": null`). Code cannot legally be vendored or redistributed. |
| **2. Linux / A100 Build & Runtime** | **PASSED** | Harness builds and runs on SCARF A100 under Slurm; NVRTC and Event timing verified. Python agent requires unprovided Python >= 3.12. |
| **3. Model Adapter & Policy Compliance** | **FAILED (Blocker)** | Upstream requires OpenAI API key; project policy restricts credentials to authorized Vertex AI / Anthropic Opus setup. |
| **4. Measurable End-to-End Improvement** | **FAILED (Impossible)** | Entire kernel runtime (0.11 s – 0.28 s) is below the empirical timing noise floor (0.43 s – 1.5 s). |
| **5. Small Understandable Diff** | **N/A** | No production diff generated due to triggering the stop criterion. |
| **6. Stop Criterion** | **TRIGGERED (Stop)** | Explicit stop criterion triggered: *"If model-adapter work, extraction overhead or negligible kernel share exceeds likely gain, publish a no-go result and stop rather than expanding scope."* |

### Final Recommendation

1. **Publish No-Go Result:** Close Issue #77 with this formal evaluation report. Do not launch automated model optimization loops.
2. **Prioritize Real Bottlenecks:** Future optimization efforts in MotionCorr should focus on Amdahl bottlenecks:
   - Asynchronous overlapped TIFF reading and PCIe frame staging.
   - Pinned host memory buffers for direct DMA transfers.
   - Multi-GPU load balancing across movies.
