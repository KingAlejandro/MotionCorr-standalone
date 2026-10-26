# Local full-width pilot packet (HELD): snapshot of review tools and evidence

**These files are a byte-for-byte snapshot of `/tmp/mc-local-full-width-pilot-20261026`, plus the independent reviews and one
parent access probe. The scripts keep their absolute `/tmp`, `~/Documents` and worktree paths and hash anchors; they are review
tools, not a portable or executable release.** Nothing here launches a producer. No driver exists. Native execution is HELD.

## What is claimed (and no more)
- Source `634e4b48` and the CMake follow-up `5bcfa987` are unchanged; this packet adds documentation and snapshot tools only.
- Host tests were bounded (macOS arm64, real NumPy 2.4.2, 1-2 threads). Scorer v3: 109 checks (run3), 11/11 guard-removal controls killed.
  Pair/decision v4: 126 checks (run5), 36 guard-removal controls: 31 killed, 5 shadowed (a different guard fires first) and declared as such.
  Failed attempts are kept (`logs_v3/ATTEMPTS_v3.md`, `logs_v4/ATTEMPTS_v4.md`).
- Review findings M1 (arm/argv/env/cwd/witness binding, v3) and M2 (pair/decision layer, v4) are **closed at the consumer level, with
  synthetic receipts and tiny fake products only**. That tests consumer logic; it does not show that any producer obeys it.
- Oracle: the direct physical-field RMS for the fixed runtime global of the retained noisy movie, 0.0367925 A, was independently
  reproduced by Opus (differences <= 3.2e-16 A). A passing field exists in the native-18 family for the **two exposed affine-truth
  fixtures only**. This is not an estimator claim: no floor subtraction, no p95/max floor claim, no native STAR writer round trip, and it
  carries no information about the local estimator or the flag.
- Independent reviews R1 (oracle + scorer v2), R2 (consumer v3) and R3 (pair/decision v4) are included with their scripts and results
  (`reviews/`); reports have sha256 `dcb6094c...`, `c3a8cb2a...`, `36bd2d44...`.

## Not established (UNRUN)
Any native, GPU or SSH work; a producer driver; a real witness (the 9 log lines) on an actual run; the 33 real fixture bytes and the 8x19
retained baseline bytes at the venue; the final Linux source/build/binary/venue/lease pins and a re-anchored release module; byte neutrality
of any real run; harm controls; N5/9/13/20; the .20/.40/.80 field gates on native output; STAR/runtime comparison on native output.
The pilot stays at 8 cases and at most 16 producers with P1/P2 unchanged. No full100, adoption, merge or default change.

## Read first
`DRIVER_RELEASE_REQUIREMENTS.md` (supported v4 flow, the R3 L1 caller contract, mandatory L2-L4 release checklist), `PLAN.md`,
`ADMISSION_AMENDMENT_v3.md`, `V4_INDEX.md`, `FINAL_PACKET_INDEX.md`. Native access: `ACCESS_CHECK.json` (19:45 UTC, original) and
`access_r2/ACCESS_CHECK.json` (parent probes, 21:11 UTC): both strict direct probes timed out with exit 255; the changed gateway host key
is not accepted and the gateway was not retried.
