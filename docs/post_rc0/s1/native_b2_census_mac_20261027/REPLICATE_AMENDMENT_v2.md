# Mac replicate census, not hash-identical to the frozen census

Additive parent scope, fixed before any replicate movie or arm. Original
[replicate amendment](REPLICATE_AMENDMENT.md) commit
`154661ba1bd733ac7993281fa895bfcd3a26b222`, P1–P6, original stops and all resource,
truth, scoring and reporting rules remain in force.

## Additional binary and arms

Use the supplied, unmodified second Mac binary
`/tmp/mc-mac-pilot-20261027/build-numpy253/motioncorr`, SHA-256
`d57432b87cdeb034c13e52ed920b19c0f819185f6ee92f04f44314337151f546`.
Its hash was verified before this amendment. Do not rebuild or modify it.
The PR #290 Mac pilot records git archive source
`5bcfa9878157ae7286d8de01e4baa5df9c073f25`, tree
`d1a67904bdd515bebc548f881e8889ac4a682bb2`, archive SHA-256
`edb6ad1bf729a67dfdd634ea66f87e2fa5a33dc587e3367a51beb54ef7253942`,
AppleClang Release `-O3 -DNDEBUG`, CUDA off and CCF DC hook on. Its venue
amendment was read in the `experiment-local-full-width-weight-20261026`
worktree. Its pilot fixture NumPy stack does not replace this census's
NumPy 2.5.4 / SciPy 1.18.1 generator stack.

Use the exact census argv and thread allocation from amendment v1, changing
only the binary and these arm settings:

| Arm | MC_EXPERIMENT_CCF_DC_ARM | Added flags |
|---|---|---|
| UP | both | `--experimental_coupled_peak all` |
| UPFW | both | `--experimental_coupled_peak all --experimental_local_full_width_weight` |
| FW | none | `--experimental_local_full_width_weight` |

OFF/B2 remain on `e978af21…`; these three arms use `d57432b8…`. All five arms
run sequentially on the same local movie, which is deleted only after scoring
and recording all five. P6 moments apply to their common input.

On the first movie only, also run the second binary with DC arm `none` and no
experimental flags. Compare its products and runtime field against `e978af21`
OFF. Record raw hashes, output-root-normalized path-bearing STAR text, MRC
core header/payload identity and runtime JSON/field differences. If different,
retain OFF from `e978af21` as the reference, report the difference and continue.
Do not promote path normalization or header/payload comparison into raw whole-
file byte identity.

No movies were processed before this amendment, so no backfill is currently
required. If any later backfill becomes necessary, regenerate only the
affected movie, verify its previously recorded Mac hash, and run only missing
new arms; preserve every prior result.

## New predictions (verbatim)

- Q1: FW beats OFF in more in-model movies than not (sign test); report the p-value.
- Q2: the FW pass count on the 80 in-model movies is at least the OFF count.
- Q3: every OFF-pass/FW-fail movie and every UP-pass/UPFW-fail movie is listed.
- Q4: UPFW vs UP is reported the same way as Q1-Q3.

As for B2, report every metric regression (RMS/p95/max) in runtime and actual
STAR separately, plus per-movie timing, P6 strata and all 80/20 counts. The
two-sided exact RMS sign test excludes exact ties and is descriptive under
the shared-noise design. No significance threshold beyond the stated
predictions is added. Report the five arms together at completion.
