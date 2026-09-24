# Build & Test Report: MotionCorr Standalone

- **Agent**: MotionCorr Testing Agent (`agents/testing_agent/`)
- **Timestamp**: {{TIMESTAMP}}
- **Target Architecture**: {{TARGET_ARCH}} ({{OS_NAME}} {{OS_VERSION}})
- **Compiler**: {{CXX_COMPILER_ID}} {{CXX_COMPILER_VERSION}}
- **Build Type**: {{BUILD_TYPE}} (Sanitizer: {{SANITIZER}})
- **Final Verdict**: `{{FINAL_VERDICT}}`

---

## 1. Executive Summary

{{EXECUTIVE_SUMMARY}}

---

## 2. Environment & Pre-Flight Checks

| Dependency | Detected Version / Path | Status |
| :--- | :--- | :--- |
| **CMake** | {{CMAKE_VERSION}} | {{CMAKE_STATUS}} |
| **C++ Compiler** | {{CXX_PATH}} | {{CXX_STATUS}} |
| **OpenMP** | {{OPENMP_INFO}} | {{OPENMP_STATUS}} |
| **FFTW3 (Double & Float)** | {{FFTW_INFO}} | {{FFTW_STATUS}} |
| **Image Codecs (TIFF, PNG, JPEG, ZLIB)** | {{CODECS_INFO}} | {{CODECS_STATUS}} |

---

## 3. Compilation & Build Telemetry

- **Target Binary**: `{{BINARY_PATH}}`
- **Build Duration**: {{BUILD_WALL_TIME}}s
- **Parallel Compilation Jobs**: {{BUILD_JOBS}}
- **Compiler Warnings / Errors**: {{WARNING_COUNT}}
- **Build Status**: {{BUILD_STATUS}}

---

## 4. Test Suite & Parity Validation Results

| Test Fixture | Execution Mode | Trajectory Delta ($\Delta x, \Delta y$) | Image RMSE | Status |
| :--- | :--- | :--- | :--- | :--- |
| `SyntheticRegression` | Serial (1 thread) | {{SHIFT_DELTA_1T}} | {{RMSE_1T}} | {{STATUS_1T}} |
| `SyntheticRegression` | Parallel (4 threads) | {{SHIFT_DELTA_4T}} | {{RMSE_4T}} | {{STATUS_4T}} |
| `ThreadDeterminism` | 1T vs 4T Drift | {{THREAD_DRIFT}} | {{THREAD_RMSE}} | {{THREAD_STATUS}} |

---

## 5. Defensive Diagnostics & Error Logs

{{DIAGNOSTIC_LOGS}}

---

## 6. Actionable Next Steps

{{NEXT_STEPS}}
