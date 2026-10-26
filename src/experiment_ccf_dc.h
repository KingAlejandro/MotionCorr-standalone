// SPDX-License-Identifier: GPL-2.0-or-later
// EXPERIMENT ONLY (#262): four-arm CCF DC conditioning. Compiled in only with
// -DMC_EXPERIMENT_CCF_DC=ON; a default build contains none of this.
//
// Operation: when the arm selects the stage (global or local), the disposable
// CCF scratch spectrum's (0,0) bin is set to zero immediately before the CCF
// inverse transform. In exact arithmetic that subtracts a constant from the
// map. Nothing else changes: frame/resident spectra, weights, peak search,
// ties, guard, fit, convergence, acceptance and publication are untouched.
//
// The arm must be given explicitly as MC_EXPERIMENT_CCF_DC_ARM=none|global|local|both;
// unset or any other value aborts at the first CCF, so an experiment binary can
// never silently run an unrecorded arm. At exit one stderr line reports, per
// call site, how many CCF frames were eligible and how many were zeroed.
//
// The same build option also compiles the #269 observation-only runtime-model
// capture (MC_DIAG_MODEL_OUT, motioncorr_runner.cpp), which the unchanged truth
// checker reads; it writes a file and changes no computation.
#ifndef MOTIONCORR_EXPERIMENT_CCF_DC_H
#define MOTIONCORR_EXPERIMENT_CCF_DC_H
#ifdef MC_EXPERIMENT_CCF_DC

#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <cstring>

enum ExperimentCcfDcSite { EXP_DC_CPU = 0, EXP_DC_CUDA_SINGLE = 1, EXP_DC_CUDA_BATCHED = 2, EXP_DC_SITES = 3 };

struct ExperimentCcfDcState {
    // bit 0: global stage selected; bit 1: local stage selected; -1: not parsed.
    std::atomic<int> arm{-1};
    // [site][stage: 0 global, 1 local][0 eligible, 1 zeroed], counted in CCF frames.
    std::atomic<unsigned long long> count[EXP_DC_SITES][2][2] = {};
};

inline ExperimentCcfDcState &experimentCcfDcState() {
    static ExperimentCcfDcState s;
    return s;
}

inline const char *experimentCcfDcArmName(int arm) {
    static const char *names[] = {"none", "global", "local", "both"};
    return (arm >= 0 && arm < 4) ? names[arm] : "invalid";
}

inline void experimentCcfDcReport() {
    ExperimentCcfDcState &s = experimentCcfDcState();
    static const char *site[] = {"cpu", "cuda_single", "cuda_batched"};
    std::fprintf(stderr, "MC_EXPERIMENT_CCF_DC arm=%s", experimentCcfDcArmName(s.arm.load()));
    for (int i = 0; i < EXP_DC_SITES; i++)
        std::fprintf(stderr, " %s.global=%llu/%llu %s.local=%llu/%llu", site[i],
                     s.count[i][0][1].load(), s.count[i][0][0].load(),
                     site[i], s.count[i][1][1].load(), s.count[i][1][0].load());
    std::fprintf(stderr, "\n");
}

inline int experimentCcfDcArm() {
    ExperimentCcfDcState &s = experimentCcfDcState();
    int arm = s.arm.load();
    if (arm >= 0) return arm;
    const char *v = std::getenv("MC_EXPERIMENT_CCF_DC_ARM");
    int parsed = -1;
    for (int i = 0; v && i < 4; i++)
        if (std::strcmp(v, experimentCcfDcArmName(i)) == 0) parsed = i;
    if (parsed < 0) {
        std::fprintf(stderr, "MC_EXPERIMENT_CCF_DC: MC_EXPERIMENT_CCF_DC_ARM must be none|global|local|both (got %s)\n",
                     v ? v : "<unset>");
        std::abort();
    }
    int expected = -1;
    if (s.arm.compare_exchange_strong(expected, parsed)) {
        std::fprintf(stderr, "MC_EXPERIMENT_CCF_DC arm=%s\n", experimentCcfDcArmName(parsed));
        std::atexit(experimentCcfDcReport);
    }
    return s.arm.load();
}

// Test hook only: select the arm for subsequent calls in this process.
inline void experimentCcfDcSetArmForTest(int arm) { experimentCcfDcState().arm.store(arm); }

// Records `frames` eligible CCF frames at `site` and returns whether their DC is zeroed.
inline bool experimentCcfDcZero(bool is_global, ExperimentCcfDcSite site, int frames) {
    const int stage = is_global ? 0 : 1;
    const bool zero = (experimentCcfDcArm() >> stage) & 1;
    ExperimentCcfDcState &s = experimentCcfDcState();
    s.count[site][stage][0] += (unsigned long long)frames;
    if (zero) s.count[site][stage][1] += (unsigned long long)frames;
    return zero;
}

#endif // MC_EXPERIMENT_CCF_DC
#endif // MOTIONCORR_EXPERIMENT_CCF_DC_H
