# B2 + full-width local weight (B2FW): frozen predictions (2026-10-27, before any B2FW run)

Frozen by the orchestrator (Opus 5.5) after the Mac replicate census (#287 head 3fa03bb8). That census gave in-model
passes of OFF 22/80, B2 68/80, FW 41/80, with zero pass-to-fail losses for B2 and FW.

Binary: Mac d57432b87cdeb034c13e52ed920b19c0f819185f6ee92f04f44314337151f546 (source 5bcfa987). It contains both the
B2 flag and `--experimental_local_full_width_weight`. Base: DC arm none, no coupled peak. B2FW = the B2 flag exactly as
the census used it, plus `--experimental_local_full_width_weight`.

## Census (100 Mac replicate movies, regenerated and checked against the Mac-recorded hashes)
- R0: B2 run on binary d574 equals the census B2 run on binary e978 for the first movie (runtime field and STAR).
  If it differs, report it, and use d574 B2 as the paired reference for B2FW.
- R1: B2FW in-model passes >= 68/80.
- R2: zero B2-pass to B2FW-fail movies. Every one is listed if any occur.
- R3: B2FW RMS lower than B2 in more in-model movies than not (sign test, descriptive).
- R4: report the dose4 tail metrics for B2 and B2FW against OFF.

## K267 eight cases (Mac, binary d574, arms OFF / B2 / FW / B2FW)
- K1: zero passes; integer/fractional identical across all arms (global-only); flat/repeated UNIDENTIFIABLE.
- K2: noisy B2FW is not worse than OFF on RMS, p95 or max. This is the test of whether FW removes the B2 blocker
  (Linux B2 noisy was 3.59/7.10/19.56 against OFF 2.34/4.38/9.90 A).
- K3: affine and pedestal under B2FW pass and are not worse than under FW.

## Falsification
- If K2 fails, B2FW still carries the five-frame noisy regression and remains blocked under the contract.
- If R2 fails, B2FW is not a strict improvement over B2.
