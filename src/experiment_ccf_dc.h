// SPDX-License-Identifier: GPL-2.0-or-later
// EXPERIMENT ONLY: native CCF DC conditioning, CPU and CUDA. The hooks below are
// compiled in only with -DMC_EXPERIMENT_CCF_DC=ON. The primitive is the reviewed
// #262/PR284 one (3eee0a4b); a default build contains none of the hooks.
//
// Operation: when the arm selects the stage (global or local), the disposable
// CCF scratch spectrum's (0,0) bin is set to zero immediately before the CCF
// inverse transform. In exact arithmetic that subtracts a constant from the
// map. Nothing else changes: frame/resident spectra, weights, peak search,
// ties, guard, fit, convergence, acceptance and publication are untouched.
//
// Request: MC_EXPERIMENT_CCF_DC_ARM=none|global|local|both (unset means none).
// MC_EXPERIMENT_CCF_DC_REPORT=<path> asks for a JSON witness of the per-site
// eligible/zeroed counts; nothing is added to the console or product logs. Its
// status is "incomplete" from start, and "atexit" once the process ran its
// normal exit handlers. "atexit" says nothing about whether the producer
// succeeded: the producer's own exit status must be retained separately.
// Differences from PR284: unset selects none instead of aborting, and the
// request is validated once, in MotioncorrRunner::read(), in every build:
// an unknown value, an arm or report in a build without the hooks, an arm on
// the --use_motioncor2 route, and an unwritable or existing report path are
// all refused before any device query or pixel is touched (the one-movie tap
// rule and the tap file creation need the final movie list and run in
// initialise(), still before the first movie).
//
// The same build option also compiles the #269 observation-only runtime-model
// tap (MC_DIAG_MODEL_OUT, motioncorr_runner.cpp). It writes one JSON file for
// exactly one movie and changes no computation.
#ifndef MOTIONCORR_EXPERIMENT_CCF_DC_H
#define MOTIONCORR_EXPERIMENT_CCF_DC_H

#include "src/error.h"

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>

#ifdef MC_EXPERIMENT_CCF_DC
#include <atomic>

enum ExperimentCcfDcSite { EXP_DC_CPU = 0, EXP_DC_CUDA_SINGLE = 1, EXP_DC_CUDA_BATCHED = 2, EXP_DC_SITES = 3 };

struct ExperimentCcfDcState {
    // bit 0: global stage selected; bit 1: local stage selected; -1: not parsed.
    std::atomic<int> arm{-1};
    // [site][stage: 0 global, 1 local][0 eligible, 1 zeroed], counted in CCF frames.
    std::atomic<unsigned long long> count[EXP_DC_SITES][2][2] = {};
    // Same indices, counted in calls (one call = one batched/serial CCF inverse).
    std::atomic<unsigned long long> calls[EXP_DC_SITES][2][2] = {};
    std::string report_path;
};

inline ExperimentCcfDcState &experimentCcfDcState() {
    static ExperimentCcfDcState s;
    return s;
}
#endif

// -1 invalid; an unset request is none.
inline int experimentCcfDcParseArm(const char *v) {
    static const char *names[] = {"none", "global", "local", "both"};
    if (!v) return 0;
    for (int i = 0; i < 4; i++)
        if (std::strcmp(v, names[i]) == 0) return i;
    return -1;
}

#ifdef MC_EXPERIMENT_CCF_DC
inline const char *experimentCcfDcArmName(int arm) {
    static const char *names[] = {"none", "global", "local", "both"};
    return (arm >= 0 && arm < 4) ? names[arm] : "invalid";
}

// Writes the witness; status is "incomplete" until the exit handler runs ("atexit").
inline bool experimentCcfDcWriteReport(const char *path, const char *mode, const char *status) {
    ExperimentCcfDcState &s = experimentCcfDcState();
    FILE *f = std::fopen(path, mode);
    if (!f) return false;
    static const char *site[] = {"cpu", "cuda_single", "cuda_batched"};
    static const char *stage[] = {"global", "local"};
    std::fprintf(f, "{\"schema\":\"mc-ccf-dc-witness-v1\",\"status\":\"%s\",\"arm\":\"%s\","
                 "\"test_only_isotropic_global_weight\":%s,\"sites\":{", status,
                 experimentCcfDcArmName(s.arm.load()),
#ifdef MC_TEST_ONLY_ISOTROPIC_GLOBAL_WEIGHT
                 "true"
#else
                 "false"
#endif
                 );
    for (int i = 0; i < EXP_DC_SITES; i++) {
        std::fprintf(f, "%s\"%s\":{", i ? "," : "", site[i]);
        for (int j = 0; j < 2; j++)
            std::fprintf(f, "%s\"%s\":{\"calls_eligible\":%llu,\"calls_zeroed\":%llu,\"frames_eligible\":%llu,\"frames_zeroed\":%llu}",
                         j ? "," : "", stage[j], s.calls[i][j][0].load(), s.calls[i][j][1].load(),
                         s.count[i][j][0].load(), s.count[i][j][1].load());
        std::fprintf(f, "}");
    }
    std::fprintf(f, "}}\n");
    return std::fclose(f) == 0;
}

inline void experimentCcfDcAtExit() {
    const std::string &p = experimentCcfDcState().report_path;
    if (!p.empty() && !experimentCcfDcWriteReport(p.c_str(), "w", "atexit"))
        std::fprintf(stderr, "MC_EXPERIMENT_CCF_DC: cannot write the witness report %s\n", p.c_str());
}
#endif

// Validates the whole request. Called once from MotioncorrRunner::read(), before
// any device query. `own_route` is true for --use_own, the only route with hooks.
inline void experimentCcfDcCheckRequest(bool own_route) {
    const char *arm_env = std::getenv("MC_EXPERIMENT_CCF_DC_ARM");
    const char *report_env = std::getenv("MC_EXPERIMENT_CCF_DC_REPORT");
    const char *tap_env = std::getenv("MC_DIAG_MODEL_OUT");
    const int arm = experimentCcfDcParseArm(arm_env);
    if (arm < 0)
        REPORT_ERROR(std::string("MC_EXPERIMENT_CCF_DC_ARM must be none|global|local|both (got ") + arm_env + ")");
#ifndef MC_EXPERIMENT_CCF_DC
    if (arm != 0 || report_env || tap_env)
        REPORT_ERROR("MC_EXPERIMENT_CCF_DC_ARM, MC_EXPERIMENT_CCF_DC_REPORT or MC_DIAG_MODEL_OUT was requested, but this "
                     "binary was built without -DMC_EXPERIMENT_CCF_DC=ON. Rebuild with it, or unset them.");
    (void)own_route;
#else
    if ((arm != 0 || tap_env) && !own_route)
        REPORT_ERROR("MC_EXPERIMENT_CCF_DC_ARM and MC_DIAG_MODEL_OUT apply only to --use_own; the --use_motioncor2 "
                     "route would ignore them.");
    if (tap_env) {
        if (!*tap_env) REPORT_ERROR("MC_DIAG_MODEL_OUT is empty");
        if (FILE *probe = std::fopen(tap_env, "rb")) {
            std::fclose(probe);
            REPORT_ERROR(std::string("MC_DIAG_MODEL_OUT already exists: ") + tap_env);
        }
    }
    ExperimentCcfDcState &s = experimentCcfDcState();
    s.arm.store(arm);
    if (report_env) {
        if (!*report_env) REPORT_ERROR("MC_EXPERIMENT_CCF_DC_REPORT is empty");
        // "wx" proves the path is writable and refuses to overwrite a retained file.
        if (!experimentCcfDcWriteReport(report_env, "wx", "incomplete"))
            REPORT_ERROR(std::string("MC_EXPERIMENT_CCF_DC_REPORT cannot be created exclusively: ") + report_env);
        s.report_path = report_env;
        std::atexit(experimentCcfDcAtExit);
    }
#endif
}

#ifdef MC_EXPERIMENT_CCF_DC
// Called from initialise() once the movie list is final, before the first movie:
// the tap captures exactly one movie, and its file is created exclusively now so an
// unwritable path is refused before any pixel work. The tap block rewrites it.
inline void experimentCcfDcPrepareTap(size_t n_movies) {
    const char *path = std::getenv("MC_DIAG_MODEL_OUT");
    if (!path) return;
    if (n_movies != 1)
        REPORT_ERROR("MC_DIAG_MODEL_OUT captures exactly one movie per process; this run selected " +
                     std::to_string(n_movies));
    FILE *f = std::fopen(path, "wx");
    if (!f || std::fputs("{\"status\":\"incomplete\"}\n", f) < 0 || std::fclose(f))
        REPORT_ERROR(std::string("MC_DIAG_MODEL_OUT cannot be created exclusively: ") + path);
}

inline int experimentCcfDcArm() {
    ExperimentCcfDcState &s = experimentCcfDcState();
    int arm = s.arm.load();
    if (arm >= 0) return arm;
    const char *v = std::getenv("MC_EXPERIMENT_CCF_DC_ARM");
    const int parsed = experimentCcfDcParseArm(v);
    if (parsed < 0) {
        std::fprintf(stderr, "MC_EXPERIMENT_CCF_DC: MC_EXPERIMENT_CCF_DC_ARM must be none|global|local|both (got %s)\n", v);
        std::abort();
    }
    int expected = -1;
    s.arm.compare_exchange_strong(expected, parsed);
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
    s.calls[site][stage][0] += 1;
    if (zero) {
        s.count[site][stage][1] += (unsigned long long)frames;
        s.calls[site][stage][1] += 1;
    }
    return zero;
}
#endif // MC_EXPERIMENT_CCF_DC
#endif // MOTIONCORR_EXPERIMENT_CCF_DC_H
