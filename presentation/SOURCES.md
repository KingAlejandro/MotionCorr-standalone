# Evidence and editorial notes

## Snapshot and scope

Repository material was reviewed on 24 September 2026. The film is a snapshot of an active hackathon, not a release announcement. All issue and pull-request bodies available in the repository review, numbered through #46, were read. Selected implementation metadata, presentation documents and review threads were also inspected. This is not a claim that every source-code line or every comment was audited, nor that the scientific software or its benchmarks were independently rerun for this video.

The user's direct account supplies the event context: STFC with Google and PA, extensive use of Google Antigravity, and specialist agents for a Gemini Enterprise workflow.

## Presentation basis

- Presentation script: https://github.com/KingAlejandro/MotionCorr-standalone/blob/dev_milan/presentation/PRESENTATION_SCRIPT.md
- Agent lifecycle: https://github.com/KingAlejandro/MotionCorr-standalone/blob/dev_milan/presentation/AGENTIC_LIFECYCLE.md

The original one-minute script was expanded into a three-minute story. Unqualified statements about guaranteed bit-exact GPU output, universal upstream parity and zero regression risk were not retained. The original CPU scaling figures were not relabelled as GPU acceleration results.

## Scene evidence

### 00:00–00:46 | Scientific problem and three acceleration routes

The introductory microscopy animation is original, deterministic synthetic imagery. It illustrates the alignment-and-summation problem, not a measured experimental comparison. The compute diagram is schematic.

The standalone extraction, reference checks and acceleration work packages are described in issues #4, #14–17 and the Metal epic #29. JAX is described as an exploration track, not as a completed backend.

- https://github.com/KingAlejandro/MotionCorr-standalone/issues/4
- https://github.com/KingAlejandro/MotionCorr-standalone/issues/14
- https://github.com/KingAlejandro/MotionCorr-standalone/issues/15
- https://github.com/KingAlejandro/MotionCorr-standalone/issues/16
- https://github.com/KingAlejandro/MotionCorr-standalone/issues/17
- https://github.com/KingAlejandro/MotionCorr-standalone/issues/29

### 00:46–01:28 | Google tools, specialist agents, human review

Antigravity and Gemini Enterprise usage follows the team's account. The agent roles are adapted from the lifecycle document and PR #21. The illustrated workspace is not a product screenshot. Agent dialogue is written for this film and is not quoted from an actual tool run.

PR #1 documents label-gated GitHub triage, bounded draft fixes and reviews using Gemini via Vertex AI on Cloud Run, with no automatic approval or merge. The film avoids presenting the automation as infallible.

- https://github.com/KingAlejandro/MotionCorr-standalone/pull/1
- https://github.com/KingAlejandro/MotionCorr-standalone/pull/21

### 01:28–01:40 | 24/24 means fixed standalone CPU thread agreement

The 24/24 figure comes from the updated PR #23 comparison of fixed standalone CPU outputs at one and four threads. PR #24 addresses thread-dependent defect-replacement randomness.

This is explicitly **not** a 24/24 claim against the older saved full-RELION outputs. PR #23 reports only 1/24 against that upstream reference after the deterministic fix, with the separate discrepancy tracked in #20. No acceptance tolerance was changed to obtain the displayed thread-agreement result.

- https://github.com/KingAlejandro/MotionCorr-standalone/pull/23
- https://github.com/KingAlejandro/MotionCorr-standalone/pull/24
- https://github.com/KingAlejandro/MotionCorr-standalone/issues/20

### 01:40–01:53 | Small synthetic pass, experimental image differences

PR #28 reports 2/2 small synthetic global-alignment fixtures passing on A100. PR #25 records 0/24 complete experimental Gate 2 passes because relative corrected-image RMSE ranges from 0.002899 to 0.010082 against the unchanged 0.001 limit. Other successful checks do not override this failure. The film shows the rounded range 0.0029–0.0101.

The numerical diagnosis is tracked in #36 and draft PR #38. These are investigations, not a completed scientific fix.

- https://github.com/KingAlejandro/MotionCorr-standalone/pull/25
- https://github.com/KingAlejandro/MotionCorr-standalone/pull/28
- https://github.com/KingAlejandro/MotionCorr-standalone/issues/36
- https://github.com/KingAlejandro/MotionCorr-standalone/pull/38

### 01:53–02:04 | Fast kernels did not yet improve whole-movie time

PR #37 reports five isolated runs per path on an A100 host with eight CPU threads. CPU median 15.66 seconds; GPU-assisted median 16.38 seconds. Their ratio is approximately 0.96×. This is the local-patch prototype, before the later reconstruction proposal, not a general GPU performance verdict.

That PR reports approximately 10.5 seconds of CPU reconstruction work and identifies why speeding up cross-correlation alone did not produce end-to-end acceleration. The chart uses those reported whole-movie medians.

- https://github.com/KingAlejandro/MotionCorr-standalone/pull/37
- https://github.com/KingAlejandro/MotionCorr-standalone/issues/44

### 02:04–02:17 | Preliminary reconstruction-stage report

Open PR #45 reports a reconstruction-stage change from 10.5 seconds to 0.356 seconds, approximately 29.5×, with streaming buffers. This is clearly labelled **early / preliminary / stage-specific** in the film. It is not an independently reproduced result and not a claim of 29.5× whole-movie speedup. The PR separately reports 14.0 to 10.8 seconds for a full movie.

The PR was open and unmerged when inspected. Its reported stage-level numerical result does not resolve the earlier full-pipeline 24-movie image-gate failure. Full-pipeline scientific acceptance and isolated performance validation remain distinct questions.

PR head inspected: `be4c71e0aa09b33d4912c6211a993a1febef91f5`.

- https://github.com/KingAlejandro/MotionCorr-standalone/pull/45

### 02:17–02:29 | Different backends, different maturity

PR #43 proposes actual Metal global-alignment kernels and MPSGraph inverse FFT use on Apple silicon. It reports small-fixture numerical results. It was open and unmerged when inspected; full experimental acceptance was still pending. The film does not promote the earlier device-dispatch smoke or harness-only tests to scientific GPU validation.

JAX remains an exploration workstream in issues #14–15. Feasibility projections in PR #46 are not shown as measured speedups.

PR #43 head inspected: `559df17e7d74c1dc69250fa9bec73cd70a34b869`.

- https://github.com/KingAlejandro/MotionCorr-standalone/pull/43
- https://github.com/KingAlejandro/MotionCorr-standalone/issues/34
- https://github.com/KingAlejandro/MotionCorr-standalone/pull/46

### 02:29–03:00 | Lessons and presentation joke

The closing lessons are an editorial synthesis of the development and validation record: bounded tasks, tests that can fail, and human scientific judgment. The snack and presentation dialogue are affectionate dramatisations, not quotations.

## Full review index

The issue bodies reviewed were #4–18, #20, #26–27, #29–36 and #44. The pull-request bodies reviewed were #1–3, #19, #21–25, #28, #37–43 and #45–46. Together these cover the 46 numbered issues and pull requests surfaced at the review snapshot.

- All issues: https://github.com/KingAlejandro/MotionCorr-standalone/issues?q=is%3Aissue
- All pull requests: https://github.com/KingAlejandro/MotionCorr-standalone/pulls?q=is%3Apr

## Original assets and soundtrack

All microscopy illustrations and the electronic soundtrack were generated programmatically for this film from deterministic scripts included in `source/`. They are not downloaded experimental images, stock music or a generated voice. The score is 112 BPM, 180 seconds, stereo, and contains no sampled recordings. No third-party font files are distributed.
