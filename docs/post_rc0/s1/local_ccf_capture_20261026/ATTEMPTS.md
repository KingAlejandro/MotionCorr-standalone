# Additive attempt ledger

- Source-edit helper attempt1: Python SyntaxError (unterminated triple-quoted string) before execution; no runner edits applied. Corrected the local helper, then applied once. No native/build/test attempt occurred.
- Remote tooling query: cpu64 has no rg; CMake cache query rerun with grep. Read-only, no job/native data changed.
- Source staging attempt1: git archive rejected nonexistent `cmake` path; remote tar rejected empty stream, leaving an empty source directory. No files transferred. Corrected tracked paths and staged into distinct source-r2.
- Build admission r2 PASS (all eight leases including canonical, affinity32-47, scratch1.16GB); configure invocation failed exit127 because noninteractive cpu64 PATH omitted cmake. Configure log retained; no compiler/native job ran. Resolve exact existing CMake binary, separately named r3 invocation.
- Author pre-build CMake disposition: register diagnostic CLI test only for the DC-hook build it requires, so default non-DC build does not receive an inapplicable test. No production delta from927a6890.
- Full CPU Release/DC-hook configure/build r3 PASS at ea775cc5 (production source identical927a6890). Existing compiler warning about fclose attributes retained in full build log. Binary SHA fd69d602f9c333b68f8ab4ccfaf32b56c586d872f4f7972fc1b379656806fd7d.
- Selected CTest r3:5/8 PASS; PatchRetryState, GlobalHalfGain, CoupledPeak ABORT because required DC arm was unset in launcher. Original failed logs retained; capture writer/actual-C2R bit neutrality, capture CLI, B2, DC hook, experimental CLI passed.
- Corrected invocation r4 reran only those3 existing tests with MC_EXPERIMENT_CCF_DC_ARM=none, no source/test changes, fresh leases/admission,j2:3/3 PASS. These eight selected checks are not full CPU qualification. No native movie producer has run at this ledger point.
