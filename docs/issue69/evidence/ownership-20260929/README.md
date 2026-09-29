# Retained CUDA reliability evidence

This directory publishes bounded logs/manifests/drivers, not the large image payloads.
Raw outputs and binaries remain on 4GPUs at
`/home/alex/mc-pr115-ownership-20260929`. Do not remove that directory while reviewing
the claim. Execution occurred on 28 September 2026 UTC (29 September local date).

* Final source/binaries: executed-source-v5.txt, executed-binaries-v5.txt,
  source-status-v5.txt (empty means clean), payload-final.txt.
* Reference: base-binary-hash.txt; validate-native.sh builds main a75a3f8 with the same
  toolchain and executes base24/base-early. provenance-final.txt contains all24 input
  and gain hashes, but its source/binary/payload header is the earlier 0c13ce0 run.
* Final matrix: matrix-v5.log and matrix-v5-restored.log. Four extra ownership sequences
  are listed separately from the 301 injected call-ordinal trials.
* Full test inventory/output: ctest-v5.log. Compile/configure and the initial failed
  harness compile are preserved separately.
* Healthy final parity: parity24-v5.json, parity-early-v5.json and their run logs;
  compare-native.py contains the exact normalization. payload-final.txt and
  parity-payload-final.json independently capture the final actual payload and early-bin
  comparison. The first capture invocation failed on taskset syntax before launching
  work; capture-final-payload.log retains that failure, corrected invocation is separate.
* Production fault/reset logs: retry-v5, final-fault-34, final-fault-35,
  final-recoverable, frame-cache-good. validate-last.sh gives commands/oracles.
* Negative controls: mutant-align/cache/entry/free.log and mutant-reset,
  boundary-mutant, scratch-mutant, frame-cache-mutant. Revision mapping is in
  ../../RESULTS.md and the retained validate-native/final/extra/last.sh scripts.
  binary-hashes-v4.txt belongs to acb2f40; it is not final078 provenance.
* Native resume: validate-resume2.sh/log, resume-reference, resume-work2,
  resume-input-hashes.txt, resume-before2.json, resume-ordinal2.txt and
  parity-resume2.json. The earlier validate-resume.sh/log and resume-work document the
  recoverable ordinal128 probe; that probe is not a failed-middle-movie PASS.
* Empty release-compute*.txt files are nvidia-smi compute-app observations after owned
  work stopped, not missing test rows. Source and resources were restored/released.

The drivers assume their recorded paths, tools and completed reference runs. They
deliberately create new result directories and fail rather than overwrite evidence.
Copy/adapt into fresh scratch when replaying. Some drivers mutate only their private
source clone for negative controls, with restoration; do not run against a shared
checkout. No timings from these correctness runs establish performance.

SHA256SUMS covers all published evidence files except itself.
