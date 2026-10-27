# Native B2 census on macOS arm64: STOP at first input hash

**No native accuracy result was produced.** The required first-movie identity
gate failed for `dose1-s00`; the campaign stopped before either OFF or B2 ran.
Exactly one movie was generated and rejected, 99 were unattempted, and all
200 intended native runs remain **UNRUN**. No input, evaluator, limit, ROI,
generator, gauge or B2 source was changed to overcome the mismatch.

This is a **NEW venue**, macOS 26.7.1 arm64 / Apple M4 Pro, 14 logical CPUs,
24 GiB RAM. It is not the Linux cpu64 venue or binary `531a1b09…`.
No remote host was contacted; SSH configuration and known_hosts were untouched.

## Failed input gate

Frozen identity comes from [FIXTURE_INDEX.json](../km_truth/FIXTURE_INDEX.json).
The generator matches the pilot source SHA-256
`a10f694abafc71c146d0e0f2eeb2b1cf2c58131b2dbf6c1b66800405bd126380`.
The fresh `/tmp/motioncorr-b2-census-mac-20261027/venv` contains exactly the
recorded NumPy **2.5.4** and SciPy **1.18.1**; Python is **3.15.1**.
The retained pilot original receipts record Python 3.12.3.

| Artifact | Frozen census SHA-256 | Regenerated Mac SHA-256 |
|---|---|---|
| dose1-s00 movie.mrcs | `de8b20a222a384b7ed525ec265053a87ac285166aecf8e98ed4bfa7b6115ea1d` | `44ee7cc3fca81a6a4e3c8892e59d0309d00a4072f8a4f921c36f6d6e797dddc9` |
| inmodel.npy expectation | `91d8cd86ff646ddf17358a8c7024780f1e239c2ceac382e68f1561fb757ca656` | `665846b4edc7d42f28cb6287090548b2440db4c4b4048bffd3d11fbd2abf21d0` |

The mismatch already exists in the noise-free expectation, before Poisson movie
generation. Matching the two package versions therefore did not reproduce the
frozen input bytes on this venue. The exact numerical cause is **unisolated**:
architecture, Python and numerical-wheel/build differences have not been
separated. It would be unsupported to attribute this to one specific FFT,
rounding or RNG change. No original expectation pixels were available for a
byte comparison in the local sources inspected.

The generator exited 0, its inverse-closure check returned
`4.547473508864641e-13 px`, and its input STAR hash matches the pilot's
`ba3a39e59ca796b5dcaae0a41e0ded6f2c020e877d344a4aa182e4afebf8ac55`.
Those checks do not override the failed movie identity gate.
Full pins and generated metadata are in
[first-input-verification.json](first-input-verification.json),
[generated-RECEIPT.json](generated-RECEIPT.json) and
[generated-expectation.json](generated-expectation.json).

## Source and successful build

Starting evidence branch: `native-b2-cpu-prototype`,
`42af54069e9b33a3f6b7b63c4046457c50daa93c`, initially clean.
Built from a full `git archive`, outside the worktree:

- Reviewed source: `326f03a073aec0d26c9cd585ce4f701d1c808245`.
- Git archive tree: `44ea2f4c053229297f50ce7feb1066e291674b06`.
- Archive stream SHA-256: `63038245056d41bdd8bf7f1c6358c9130e52ec1092ab796b24e32a811838065b`.
- **Mac arm64 binary SHA-256:** `e978af21352295bfe2cf756fa2916703d2b7e6c6b34c352d58630e7975155946`.

```sh
uv venv /tmp/motioncorr-b2-census-mac-20261027/venv --python python3
uv pip install --python /tmp/motioncorr-b2-census-mac-20261027/venv/bin/python numpy==2.5.4 scipy==1.18.1
git archive 326f03a073aec0d26c9cd585ce4f701d1c808245 > /tmp/motioncorr-b2-census-mac-20261027/source.tar
tar -xf /tmp/motioncorr-b2-census-mac-20261027/source.tar -C /tmp/motioncorr-b2-census-mac-20261027/source
cmake -S /tmp/motioncorr-b2-census-mac-20261027/source \
  -B /tmp/motioncorr-b2-census-mac-20261027/build \
  -DCMAKE_BUILD_TYPE=Release '-DCMAKE_C_FLAGS_RELEASE=-O3 -DNDEBUG' \
  '-DCMAKE_CXX_FLAGS_RELEASE=-O3 -DNDEBUG' -DCUDA=OFF \
  -DMC_EXPERIMENT_CCF_DC=ON -DBUILD_TESTING=ON \
  -DPython3_EXECUTABLE=/tmp/motioncorr-b2-census-mac-20261027/venv/bin/python
cmake --build /tmp/motioncorr-b2-census-mac-20261027/build --target motioncorr local_b2_fit -j 6
```

Configure/build exited 0. The first configure selected a Python without NumPy
and failed; [its log](configure-v1-failed.log) is retained. Only the Python
interpreter setting was corrected. See [configure-v2.log](configure-v2.log),
[build.log](build.log), [provenance.json](provenance.json) and
[numeric package configuration](python-numeric-config.txt).
No CTests or native arm were executed after the hash gate failed.
Build success establishes no native accuracy, performance or GPU result.

## Single regeneration command and resources

The actual preflight was an inline Python invocation calling unchanged
`gen.expected(gen.recipe('dose1', 0), inmodel.npy)`, recording its proof,
then `gen.generate(recipe, inmodel.npy, first-movie)`, and comparing both hashes
to the fixture index. [regenerate_first.py](regenerate_first.py) preserves these
calls for reproduction in a fresh scratch root; it was transcribed after the
attempt and was not executed as a second attempt. Equivalent invocation:

```sh
OMP_NUM_THREADS=8 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 \
  /tmp/motioncorr-b2-census-mac-20261027/venv/bin/python -I \
  regenerate_first.py /tmp/motioncorr-b2-census-mac-20261027 \
  ../km_truth/FIXTURE_INDEX.json
```

The expectation took 70.4531 s and movie generation 27.9000 s. These are
generator timings, **not OFF/B2 wall times**. The build used at most six jobs
while the generator occupied about one CPU in the retained snapshot. Other
processes were left alone. The intended native allocation was `--j 8` and
`OMP_NUM_THREADS=8`; no native run consumed it. No affinity claim is made on
macOS. Disk snapshots showed 23 GiB free before work, 21 GiB during expectation
generation and 17 GiB after generation, above the 10 GiB stop threshold.
These are snapshots, not a continuous minimum. At most one movie and one
expectation existed. The 2,684,355,584-byte rejected movie and 2,684,354,688-byte
expectation were hashed and deleted after retaining their compact receipts;
[cleanup.json](cleanup.json) records hashes, sizes and recovered free space.

## Requested results: all UNRUN

Step 1's explicit stop rule prevented step 2's prediction commit and every
native/scoring step. No pre-run prediction commitment is claimed. The requested
frozen predictions remain:

| Prediction / result | Status |
|---|---|
| P1: Native B2 per-movie verdict equals W8 and applied-field difference ≤ 0.013131428741 px on the 80 in-model movies | UNRUN |
| P2: B2 passes more of the 80 in-model movies than OFF | UNRUN |
| P3: List every OFF-pass/B2-fail movie, retaining expected dose4 tail regressions | UNRUN; no native comparisons exist |
| P4: Per-movie OFF/B2 wall times, descriptive only | UNRUN |
| Runtime and actual STAR pass counts, in-model 80 | UNRUN for both arms |
| Runtime and actual STAR pass counts, remaining 20 (10 outmodel + 10 pedestal32/no-local) | UNRUN for both arms |
| Paired sign test, runtime and actual STAR | UNRUN |
| OFF-pass/B2-fail and metric/tail regressions | UNRUN, not zero |
| Per-movie OFF/B2 timing table | No rows; zero native producers |

W8's historical offline 22→68/80 result and the Linux pilot's dose4 regression
remain historical evidence; this stopped Mac attempt adds no accuracy result
and does not supersede any previous failure. The frozen evaluator is unchanged:
SHA-256 `b0ab099a256e458b1c8aea6c2ff5d9ceacab10dd81945b025e96e5c8a87b7ff9`.
Planned arm differences were solely `--experimental_local_b2` as in the pilot,
with CCF DC arm `none` and every other experimental arm at its unchanged default
`none`/off; none of those commands ran.

**Next action:** recover the frozen, hash-verified expectation or movie bytes
from a trusted local archive before a separately authorized attempt. Do not
substitute this regenerated scene, relax input identity, or score unverifiable
movies. This campaign was not retried.
