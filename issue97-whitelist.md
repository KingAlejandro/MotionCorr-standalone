# Change whitelist for issue #97 (strict scope)

Allowed:
- src/motioncorr_runner.cpp:2160-2172 region ONLY (save first-frame origin before in-place subtract for interpolate_shifts path)
- Bounded regression test (new or added) exercising real interpolate + recenter path with nonzero first offset
- WORKER_STATUS.md, this whitelist, ADR, commit messages
- GitHub progress comments on #97

Forbidden (enforced by review):
- Any other source lines or files
- CUDA / GPU code or tests in this PR
- Gate tolerance changes, RELION runs, perf numbers
- Anything outside recenter origin bug

Base: 4c952b3
Branch: round96/97-grok-4-3
Model: grok-4.3
