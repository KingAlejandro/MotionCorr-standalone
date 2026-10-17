#ifndef MOTIONCORR_CPU_DOSE_SYMMETRY_MODE_H
#define MOTIONCORR_CPU_DOSE_SYMMETRY_MODE_H
// Selects the CPU doseWeighting implementation (CMake MOTIONCORR_CPU_DOSE_SYMMETRY).
// MOTIONCORR_CPU_DOSE_SYMMETRY_MODE: 0 = OFF (original loop), 1 = ON (symmetric
// rows), 2 = AUTO (default). AUTO enables the symmetric path only on the
// qualified toolchain, x86-64 GCC without FMA code generation (#218, #220),
// where it is measured and bit-exact. Every other target keeps the original loop.
// CMake evaluates this same header for its configure message.
#ifndef MOTIONCORR_CPU_DOSE_SYMMETRY_MODE
#define MOTIONCORR_CPU_DOSE_SYMMETRY_MODE 2
#endif

#if MOTIONCORR_CPU_DOSE_SYMMETRY_MODE == 0
#define MOTIONCORR_CPU_DOSE_SYMMETRY 0
#elif MOTIONCORR_CPU_DOSE_SYMMETRY_MODE == 1
#define MOTIONCORR_CPU_DOSE_SYMMETRY 1
#elif MOTIONCORR_CPU_DOSE_SYMMETRY_MODE == 2
#if defined(__x86_64__) && defined(__GNUC__) && !defined(__clang__) && \
    !defined(__INTEL_COMPILER) && !defined(__INTEL_LLVM_COMPILER) && \
    !defined(__NVCOMPILER) && !defined(__PGI) && \
    !defined(__FMA__) && !defined(__FMA4__)
#define MOTIONCORR_CPU_DOSE_SYMMETRY 1
#else
#define MOTIONCORR_CPU_DOSE_SYMMETRY 0
#endif
#else
#error "MOTIONCORR_CPU_DOSE_SYMMETRY_MODE must be 0 (OFF), 1 (ON) or 2 (AUTO)"
#endif

#endif
