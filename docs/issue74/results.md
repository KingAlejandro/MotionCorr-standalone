# Issue #74 — measured result: optional CUDA detailed-event profiling

Run: SCARF Slurm job **3510295**, `COMPLETED`, exit `0:0`, elapsed `00:17:10`,
node `gn3000` (exclusive). Evidence: [`evidence/`](evidence/), raw job trace in
[`evidence/job.log`](evidence/job.log), machine verdicts in
[`evidence/summary.txt`](evidence/summary.txt).

**Headline: no measurable benefit.** Turning the detailed events off does not
make the application faster. The paired estimate is `+0.33 s` (i.e. *slower*)
on a ~26.2 s run, 95 % CI `−0.69 … +1.35 s`, which is a null result, not a
speed-up. Max RSS differs by 2.4 MiB (0.15 %). The measurement is sound and the
answer is "no"; see [Recommendation](#recommendation) for what follows from
that.

Everything below separates three questions that are easy to conflate, and this
document never lets one stand in for another:

1. **Same-backend equality** — do the two modes and the baseline produce the
   same pixels? (Yes, exactly.)
2. **Native CUDA execution witness** — did the GPU actually run, *with
   profiling off*? (Yes, from runtime markers, not exit status.)
3. **Estimator accuracy** — is the science right? (Unchanged by this work, and
   its pre-existing failure is preserved. **No Gate 2 claim is made here.**)

---

## 1. Provenance

| item | value |
|---|---|
| base | `1d7e13f41b6eaf64b367d49ff0f0f5a3e09c0a26` (= `origin/main` at fetch) |
| candidate code | `e0bc6c3257dd9a046a7c85bb40b16b73e4d57302`; branch tip `329e436…` |
| drift check | `git diff --name-only e0bc6c3 HEAD -- src CMakeLists.txt tests` **empty** → docs commits after `e0bc6c3` changed no compiled path |
| node | `gn3000.scarf.rl.ac.uk`, `--exclusive`, `--constraint=scarf23`; `AllocTRES cpu=64,mem=250G,gres/gpu:a100=4`; load average `0.00` at start |
| device | NVIDIA A100-SXM4-40GB (GPU 0), driver `580.178.04`; no other process on any GPU at start |
| toolchain | nvcc 12.8.61, gcc 11.5.0, cmake 3.31.8 |
| cmake options (both arms, identical) | [`evidence/cmake-options.txt`](evidence/cmake-options.txt) — `Release`, `CUDA=ON`, `CMAKE_CUDA_ARCHITECTURES=80`, `TIMING=ON` |
| binaries | [`evidence/binaries.sha256`](evidence/binaries.sha256) — base `774f7563…`, candidate `d89da4ba…` |
| sources / inputs | [`evidence/sources.sha256`](evidence/sources.sha256), [`evidence/inputs.sha256`](evidence/inputs.sha256) (28 staged files) |
| diff under test | [`evidence/candidate-vs-baseline.diff`](evidence/candidate-vs-baseline.diff), 6 files, +413 / −92 |

Three arms, two binaries:

* `base` — baseline binary built from `1d7e13f`.
* `cand-on` — candidate binary, `RELION_CUDA_DETAILED_PROFILE` unset (default).
* `cand-off` — **the same candidate binary bytes**, `RELION_CUDA_DETAILED_PROFILE=0`.

`cand-on` and `cand-off` differ only by an environment variable. That was the
point of choosing a runtime switch over a build-time one: codegen, inlining and
binary layout cannot explain any difference between them.

### Coordination

The node was held exclusively. At submission and throughout, sibling MotionCorr
threads were either on a different node (`i73pair` on `gn0001`) or held
`PENDING` behind the per-user QOS cap (`mc-i83f`, `mcfaults`). No benchmark
shared a physical resource with this one. No other user's processes were
touched.

---

## 2. Same-backend equality — PASS

`tools/compare_motioncorr.py --gate exact` over all 24 tutorial movies, five
comparisons, each **24/24 pixel-identical** (pixels, headers, STAR,
trajectories):

| comparison | result |
|---|---|
| `cand-on` vs merged reference | 24/24 PASS |
| `cand-off` vs merged reference | 24/24 PASS |
| `base` vs merged reference | 24/24 PASS |
| **`cand-off` vs `cand-on`** (same node, same binary) | 24/24 PASS |
| `cand-on` vs `base` (same node) | 24/24 PASS |

Per-movie reports: `evidence/exact-*/` (25 JSON files each); summaries in
`evidence/exact-*.log`.

Gate C does not read every output, so
[`compare_aux_outputs.py`](compare_aux_outputs.py) covers the rest — per-movie
`.log` text, `_shifts.eps`, the aggregate STAR — with timing-variable lines
dropped and nothing else ignored:

* [`aux-candoff-vs-candon.txt`](evidence/aux-candoff-vs-candon.txt) — PASS, no
  label allowance needed.
* [`aux-candon-vs-base.txt`](evidence/aux-candon-vs-base.txt) — PASS with
  `--allow-label-changes`, which is exactly the three honesty corrections listed
  in §5.

> **Caveat on those two reports, added after review — read §7.** They were
> produced by the pre-fix comparator, which walked only the reference tree. They
> are valid for the files they compared, but they could not have detected **any
> extra file in the candidate tree**, nor a *missing* `.mrc`, `.star`, `.pdf` or
> `.lst` — for those types the existence check sat after the content-policy
> `continue`. A missing `.log`, `.eps` or `corrected_micrographs.star` *was*
> caught, so the blind spot is specific, not total. The output trees were
> node-local and are gone, so this cannot be re-checked without a new GPU run,
> which is out of scope here. Treat the aux verdict as "the compared files
> matched", not as "the file sets were identical".

**The switch actually switched.** A pass here would be worthless if the env var
had silently done nothing. The harness reads the emitted `Detailed event
profiling:` value from every movie log and requires it to be uniformly `on` or
`off` at **all 27 profile sites in all 24 logs** — PASS. Representative blocks
from both arms: [`evidence/profile-block-samples.txt`](evidence/profile-block-samples.txt).

All 14 timing runs also produced one single per-movie STAR digest,
`cde2b6407a6fc7de` — so the benchmark itself never perturbed a trajectory.

---

## 3. Native CUDA execution witness — PASS, including with profiling off

This is the claim the issue cares most about, because the events being removed
are themselves a form of evidence that the GPU ran. The witness must survive
their removal.

It does. The startup marker and the per-movie completion markers were already
merged and sit **outside** the `[CUDA … Profile]` block, so they are unaffected
by the switch. Verdicts come from `backend_evidence` in the gate runner's JSON
via [`check_backend_witness.py`](check_backend_witness.py) — never from exit
status.

| run | witness |
|---|---|
| all24, `base` | startup=1, completion=24/24 |
| all24, `cand-on` | startup=1, completion=24/24 |
| all24, **`cand-off`** | startup=1, completion=24/24 |
| known-motion, `base` | 15/15 runs `requested=cuda startup=True completion=True` |
| known-motion, `cand-on` | 15/15 |
| known-motion, **`cand-off`** | 15/15 |

**CPU masquerade rejection — PASS.** A deliberate CPU run over the same 15 cases
shows `requested=cpu`, `unexpected_cuda_marker=False`, `movie_completed=True`
for every one ([`evidence/witness-cpu-control.txt`](evidence/witness-cpu-control.txt)).
The check therefore discriminates in both directions rather than merely
agreeing with whatever it is shown.

Compile-only CI (the "CUDA compile only (no GPU execution)" check on PR #88)
does **not** substitute for any of this, and is not counted as evidence here.

---

## 4. Estimator accuracy — unchanged, and its failure is preserved

Reported separately and deliberately never merged into the verdicts above. The
known-motion aggregate returned `exit=0` for all three arms, recorded as INFO.
Per-case status is **byte-for-byte the same across every arm**, including the
CPU control:

```
cand-on      global_hisnr=PASS local_hisnr=PASS local_noisy=FAIL local_nonsquare=PASS local_realscale=PASS
cand-off     global_hisnr=PASS local_hisnr=PASS local_noisy=FAIL local_nonsquare=PASS local_realscale=PASS
base         global_hisnr=PASS local_hisnr=PASS local_noisy=FAIL local_nonsquare=PASS local_realscale=PASS
cpu-control  global_hisnr=PASS local_hisnr=PASS local_noisy=FAIL local_nonsquare=PASS local_realscale=PASS
```

`km_local_noisy` is a `characterization`-role **FAIL** and stays a FAIL. It is
not hidden, not reclassified, and not affected by this work.

Scope of that `PASS`, verbatim from the JSON: *"gate-role accuracy plus
execution/backend/invariance/witness checks on every requested case"*. That is
the synthetic known-motion suite on GPU. It is **not** Gate 2, it is **not** a
CPU/RELION equivalence claim, and historical CPU/RELION Gate 2 failures remain
failures. Nothing in this document argues otherwise.

---

## 5. Honesty corrections to the profile labels

Three printed claims were wrong or overstated before this change. All key
spellings are byte-identical to before; only qualifiers were appended, so
unanchored parsers keep matching.

| before | after | why |
|---|---|---|
| `Host-to-Device transfer time: 0.00 ms (Resident VRAM)` | `0.00 ms (not measured; frames stay resident, but N shift uploads totalling B B did occur)` | the old text implied zero H2D traffic; shift uploads are real and now counted |
| `Peak GPU memory allocated:` | `… (this call's buffers, not the process peak)` | it was a function-local figure being read as a process peak |
| `Buffer VRAM:` | `… (in scope here, including the caller-owned frame buffer)` | the buffer is not owned by this call |

With profiling off, the three event-derived rows print
`n/a (detailed profiling disabled)` rather than a fabricated `0.00 ms`, and a
`Detailed event profiling: on|off` row states the mode. Both arms still print
`Total GPU alignment time`, which is measured by a single event pair that is
*not* part of the optional set.

---

## 6. Overhead measurement — the negative result

Design: three interleaved ABBA blocks (`on, off, off, on`) ×3 = 12 runs, then
2 baseline runs, all on one allocation, one node, one GPU, back to back.
Interleaving is what protects against thermal or filesystem drift being read as
an arm effect. Raw: [`evidence/timing.tsv`](evidence/timing.tsv), with
`/usr/bin/time -v` output per run in `evidence/t-*-*.time`.

| arm | n | wall mean | sd | min | max | max RSS mean |
|---|---|---|---|---|---|---|
| `cand-on` (default) | 6 | **26.167 s** | 0.629 | 25.60 | 27.27 | 1631.5 MiB |
| `cand-off` | 6 | **26.497 s** | 0.716 | 25.67 | 27.40 | 1629.1 MiB |
| `base` | 2 | 26.380 s | 0.750 | 25.85 | 26.91 | 1632.3 MiB |

Paired by ABBA block, `off − on`:

| block | on | off | off − on |
|---|---|---|---|
| runs 1–4 | 26.440 | 27.195 | +0.755 s |
| runs 5–8 | 26.025 | 26.325 | +0.300 s |
| runs 9–12 | 26.035 | 25.970 | −0.065 s |

Mean `+0.330 s`, sd `0.411`, t = 1.39 on 2 df, **95 % CI `−0.691 … +1.351 s`**.

Read honestly: the point estimate has profiling-off *slower*, which is
physically implausible and is simply noise. The interval spans zero. Run-to-run
spread within a single arm (up to 1.7 s) is several times any plausible arm
effect. **There is no measurable wall-clock benefit, and the data do not
support one existing below about 1.3 s (≈5 %) at this scale.**

Memory, same conclusion: max RSS differs by 2.4 MiB out of ~1630 MiB (0.15 %),
in the direction of profiling-off using *less*, and within the ~1–2 MiB
run-to-run spread. A separate single-pair memory run gave 1669064 KiB (on) vs
1669980 KiB (off) — off marginally higher — which again reads as noise.
Device-side sampling at ~0.24 s intervals gave peak device memory 3497 MiB (on)
vs 3335 MiB (off) and mean utilisation 8.4 % vs 9.0 %; at that sampling rate the
peak is a lower bound that can easily miss a transient, so I do not draw a
conclusion from the 162 MiB gap.

### Why the event-reported numbers must not be used as the benefit

The blocks' own `Total GPU alignment time` summed to 27.14 ms (on) vs 24.05 ms
(off) across 17 blocks of one known-motion fixture — about 3.1 ms per movie.
Quoting that as the win would be circular: it is the instrument measuring its
own removal, and it is ~0.3 % of the ~1.1 s per-movie wall time. It is
consistent with the null wall-clock result rather than evidence against it, and
that consistency is the only use I make of it.

### Scope and limits of this measurement

* One node, one A100, one dataset (24 tutorial movies, `--j 8`), one process
  configuration. It does not generalise to many-GPU or many-thread runs.
* n = 6 per arm. Underpowered for effects below ~1 s; adequate to rule out the
  multi-second effect that would justify a default change.
* Per-movie wall time is ~1.1 s against ~27 removable sync points per movie, so
  the ceiling on the achievable saving was always small. That was foreseeable —
  and measuring it rather than assuming it is the deliverable.

---

## Recommendation

**Do not change the default.** `RELION_CUDA_DETAILED_PROFILE` defaults to `1`,
behaviour is unchanged for every existing user, and a CPU-only CTest
(`CudaProfilePolicyDefault`) pins that default so it cannot drift silently.

The issue asked to avoid complexity that buys no measured benefit. On speed it
buys none, and I am not going to argue otherwise. What the change does buy,
independent of performance, is:

* three printed claims that were false or misleading are now correct (§5);
* with profiling off the code prints `n/a` instead of a fabricated `0.00 ms`;
* the profiling-only synchronizations are now *identified in code* rather than
  tangled with the correctness boundaries, which is what
  [`audit.md`](audit.md) documents.

A reviewer who weighs those below the cost of the switch would be making a
defensible call, and the smaller change — keep the label corrections and the
audit, drop the runtime switch and its header and test — is a coherent
alternative. I am not making that call unilaterally; the measured basis for it
is above. **I am not merging this.**

---

## 7. Post-review correction: the aux comparator accepted extra outputs

Raised on PR #88 at `735523a`
([discussion r4119254472](https://github.com/KingAlejandro/MotionCorr-standalone/pull/88#discussion_r4119254472)):
`compare_aux_outputs.py` iterated `ref.rglob("*")` only, so a file the candidate
emitted that the reference did not was never looked at, and the gate passed. The
finding is correct — an unintended extra output is precisely what this gate
exists to catch — and it is reproduced by the negative controls below.

Reproducing it turned up a second defect the review did not name. The old code
checked `tp.exists()` *after* the `.mrc` / `.star` / `.pdf` / `.lst` early
`continue`s, so for those types it missed **disappearances** as well as
additions. Excluding a file's *content* from comparison had silently excluded
its *existence* too.

**Fix.** The walk is now over the union of both trees, directories included.
Presence is checked first and for every entry; the content policy
(`COVERED_BY_GATE_C`, `EXCLUDED`) decides only whether the bytes are compared.
A file on one side only is a FAIL in either direction, and the summary line
reports `missing_in_test` and `unexpected_in_test` separately. The existing
normalisations are unchanged: EPS creation dates, path prefixes, timing lines,
mode-dependent lines, and the opt-in `--allow-label-changes` all behave exactly
as before, and PDF content stays excluded for the same ghostscript-timestamp
reason — but a PDF that appears or vanishes is now caught.

**Test, with controls that discriminate.** `test_compare_aux_outputs.py` runs
**21 cases**. A fix is worth little if its test would also have passed on the
broken source, so every extra/missing case is additionally run against the
pre-fix comparator recovered by `git show 735523a:…`. **7 of the 21 are proven
discriminating** — the old source returned 0 on each, the new one returns 1 —
so the run makes 28 assertions in total. If the old source cannot be recovered
the controls report SKIP and the suite exits `INCONCLUSIVE` rather than claiming
a win it did not earn. The test is also wired into the harness next to the
ctests, so the instrument is checked in the same run as the thing it measures.

Two limits of that wiring, stated rather than discovered later:

* `PRE_FIX_SHA` is a literal. If this branch is squash-merged or rebased the SHA
  becomes unreachable, the controls SKIP, the suite exits `2` and the harness
  gate reads FAIL on a tree where nothing is wrong. `--old-source FILE` is the
  escape hatch; the harness does not currently pass it. Fail-closed is the right
  default for a gate, but a maintainer merging this should know it.
* `.github/workflows/ci.yml` runs only the `SyntheticRegression` ctests, so this
  self-test does **not** run in PR CI. It runs in the GPU harness, and it was
  run on cpu64 below. Wiring it into CI means editing a workflow file that the
  active #85/#53 threads also touch, so it is flagged here, not done.

**Validation** ([`evidence/aux-comparator-selftest-cpu64.txt`](evidence/aux-comparator-selftest-cpu64.txt)):
CPU-only on `small-refmac-machine`, single process under
`flock /tmp/motioncorr-issue96-cpu-validation.lock` and `taskset -c 32-63`, with
placement recorded from **inside** the pinned process rather than from a
launcher wrapper — `sched_getaffinity` 32–63, `Cpus_allowed_list 32-63`,
`Mems_allowed_list 0-1`, policy `default`, `cpubind 1` / `membind 0 1`. Payload
SHA-256s, executable path (`/usr/bin/python3`, 3.12.3), pid, start/end times and
load (`3.54` before, `3.58` after, on 64 cores) are in the report.
**PASS**, 21/21, 7 discriminating controls, 0 skipped, exit 0.

The run was re-done at this commit rather than reused: the archived artifact
described the 17-case suite and would have understated what now runs. It uses
`--old-source` with a transferred copy of the pre-fix comparator, because cpu64
holds no clone and `git show` cannot resolve there — that copy hashes to
`b0f9d43a…3727`, the same digest the reviewer independently derived from
`735523a`, so the controls are the reviewed source and not a stand-in.

Two labels in that artifact need a gloss, since neither is self-explanatory to a
reader of this directory. The lock file is the **shared** CPU-coordination lock
for this host, named after the thread that introduced it and used by all
MotionCorr threads on it — holding it is what keeps this run off another
thread's cores, and the issue96 name is not a scope leak. "Well under the 16
cap" refers to the instructed per-thread build/runtime concurrency limit for
this machine; this run was a single Python process, so it was nowhere near it.
`placement_probe.py` in the payload manifest is a throwaway probe transferred
for this run and not tracked in the repository, so its hash is a record of what
ran, not something a reader can re-derive.

### 7.1 Second review round, on the fix itself

Two bounded read-only reviewers were run over `735523a..a675e20` (source/spec,
and licence/conventions). Both independently found the same blocking item, and
it was mine: **§7 claimed the suite ran 19 cases when the code defined 17 and
the cited artifact printed 17.** An inflated count in the section whose whole
purpose is correcting an inflated claim. Corrected throughout.

Three further defects were reproduced and are now fixed:

* **A dangling symlink was reported in the wrong direction.** `exists()`
  follows links, so a dangling link read as absent on *both* sides and the
  `missing in test tree` branch always won — an extra file was reported as a
  missing one, corrupting the `missing_in_test` / `unexpected_in_test` split
  the new summary line advertises. Presence is now `exists() or is_symlink()`.
  Verified against the previous commit: `a675e20` labelled an extra dangling
  symlink `missing in test tree`; the current code labels it
  `unexpected file in test tree`.
* **A file replaced by a symlink to identical bytes passed.** Symlinks are now
  compared *as links* — link-vs-regular is a FAIL, differing targets are a
  FAIL, identical targets are recorded present without following them (`rglob`
  does not descend a symlinked directory, so following one would compare a
  target the walk never enumerated).
* **An unreadable file produced a traceback and no report**, costing the
  harness the artifact §6 links to. It is now recorded as a FAIL row.

And the test weakness that let the first of those through: every case asserted
the **exit code only**, so a failure reported under the wrong label was
invisible. Presence cases now assert the expected reason text, which is what
makes the symlink direction testable at all. Two branches added by the union
fix that had no coverage — directory-where-a-file-is-expected, and the
"nothing was actually compared" guard — now have cases. 17 cases became **21**.

**Limitations left in place, stated rather than fixed.** All are pre-existing,
none is a regression, and none reopens the reviewed finding:

* Text paths end in `splitlines()`, so CRLF-vs-LF, a stripped trailing newline,
  and exotic line separators (`\x0c`, ` `) compare equal.
* `errors="replace"` means two *different* invalid byte sequences both collapse
  to U+FFFD and compare equal.
* On a **case-insensitive filesystem** (macOS dev machines, not the Linux nodes
  this gate runs on) `a.log` renamed to `A.LOG` still passes, because the
  presence test case-folds even though the walk does not.
* File modes are not compared.

The gate therefore establishes that the two trees hold the same set of path
*names* and that the compared files' *decoded lines* match — not that they are
byte-identical. For same-node, same-binary arms that is the right scope, but it
is narrower than "identical trees" and should not be read as more.

### 7.2 What the reviewers confirmed

Worth recording, because it is the part a reader should be able to rely on:
the union fix could not be broken for the defect it targets (extras, missings,
nested extra directories, empty directories, file-vs-directory collisions and
all-skipped trees all fail closed); no normalisation was weakened; the counters
cannot yield a false PASS, since every failure branch increments `nfail` and
directories land in `nskip` rather than `npass`; and the `INCONCLUSIVE` path
really does deny a win, because `gate()` records FAIL on exit 2.

The discriminating controls were checked cryptographically rather than taken on
trust: `git show 735523a:docs/issue74/compare_aux_outputs.py` hashes to
`b0f9d43a…3727`, which is exactly the `pre_fix_comparator.py` SHA-256 recorded
in the cpu64 payload manifest. The controls ran against the reviewed source,
not a hand-rolled stand-in.

No production code was touched by this fix: it is confined to
`docs/issue74/`. No new benchmark was run, and the numbers in §6 are unchanged.

---

## Verdict table

| question | verdict | basis |
|---|---|---|
| Builds, both arms, identical options | **PASS** | `evidence/summary.txt` |
| `CudaProfilePolicyDefault` ctest | **PASS** | default pinned |
| `CudaWrapperUploadFailure` ctest, both arms | **PASS** | error boundaries intact |
| Pixel equality, all 5 comparisons, all24 | **PASS** | 24/24 each |
| Auxiliary outputs, compared files | **PASS** | both reports |
| Auxiliary outputs, *file-set* equality | **not established** | pre-fix comparator did not check it; trees are gone (§7) |
| Aux comparator self-test, incl. old-source controls | **PASS** | 21/21 cases + 7 discriminating controls, cpu64 under lock (§7) |
| Switch demonstrably switched | **PASS** | 27 sites × 24 logs, uniform |
| Native CUDA witness incl. profiling-off | **PASS** | runtime markers |
| CPU masquerade rejection | **PASS** | 15/15 negative control |
| Estimator accuracy changed by this work | **no change** | identical per-case status across arms |
| Historical CPU/RELION Gate 2 | **not claimed, not run** | out of scope |
| Wall-clock benefit from disabling events | **none measured** | +0.33 s, CI −0.69…+1.35 s |
| Memory benefit from disabling events | **none measured** | 0.15 % of RSS, within noise |
