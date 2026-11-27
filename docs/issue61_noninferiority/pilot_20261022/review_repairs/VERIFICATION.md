# PR65 pilot review repairs, 2026-10-22

Base: `23640166559bde2357c4852d776d69322297a1aa`. New isolated branch:
`repair/pr65-pilot-isolation-20261022`, in `t3-e2048909`. The thread's initial branch
at `1f0a58bf` and read-only `t3-d0ac321b` at `2364016` were not moved. Scope is the
pilot driver/tests/README and this new evidence directory. Parent owns publication
and fresh independent review; no push, GitHub comment, merge or Notion action occurred.

## Context and design

Read project AGENTS, live [issue 61](https://github.com/KingAlejandro/MotionCorr-standalone/issues/61)
and [PR65](https://github.com/KingAlejandro/MotionCorr-standalone/pull/65) with their
discussion, original pilot README/driver/receipts, design note, frozen protocol and
amendments, descriptive plan and certificate boundary. Live PR head was C0; its body
explicitly withdrew Stage B PASS. The retained `pr65_live.json` says the same at
15:04:26 UTC. The older certificate-head/body description in the pilot README was
incorrect and is now corrected. Published C0 CI does not cover these changes.

The shared wrapper was read on 4GPUs, not changed. It prepends
`--bind PROJECT:PROJECT` before the driver's duplicate `:ro` bind. The installed
`/usr/local/bin/apptainer` resolves to `/usr/bin/singularity`, version 4.1.1.
Host configuration enables default home/tmp mounts. Both original postprocess
logs retain duplicate-destination and refused-HOME warnings. SingularityCE's
[versioned duplicate-bind handling](https://github.com/sylabs/singularity/blob/v4.1.1/internal/pkg/runtime/engine/singularity/container_linux.go#L1589-L1599)
keeps the first bind. Historical inputs were unchanged on reconciliation, but
read-only project mounts and private home/tmp were not established by that pilot.

The bounded repair directly invokes the same image's pinned internal binaries,
preserving every internal numerical argument. `container_options` has one
read-only history bind (containing the project), one read-only plan bind, writable
new scratch and read-only copied sources. `--contain` suppresses implicit cwd,
home and tmp mounts; explicit `--home` and `--workdir` select private locations.
`--no-mount hostfs,bind-paths` disables inherited host/admin mounts. Supported flags
were checked against actual help and the [4.1 documentation](https://docs.sylabs.io/guides/4.1/user-guide/bind_paths_and_mounts.html).
The host environment is allowlisted so runtime variables cannot inject additional
binds, GPU options, overlays or container environment overrides. Preflight pins
the observed runtime/config hashes and verifies version/help/internal binary
hashes, failing on unsupported identities or setup warnings. The shared wrapper
and original plan argv are retained as provenance; actual future runtime argv is
recorded separately. No new third-party code or dependency is used.

At both stage entry points, refuse any existing declared output, other product,
sidecar/log, failed-preflight marker or prior execution receipt. Empty reserved
directories remain allowed; directories at declared output paths and symlinks are
refused. Preflight's exclusive new STARTED marker also blocks partial preflight
reuse; execute accepts a successful fresh preflight and retains its exclusive
execution STARTED barrier. Earlier failure receipts are never overwritten. These
checks cover cooperative one-shot use under the existing CPU lock; they do not
claim protection against hostile concurrent filesystem mutation.

## Host checks and old/fixed proof

Occupancy was checked before tests and at final verification; unrelated busy
security, Zoom, Python and desktop processes were left running. Local free disk
was 13 GiB at the final check. Tests are small, serial standard-library controls,
with no timing claim, dependency installation or actual numerical subprocess.

```sh
export PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1 NUMEXPR_NUM_THREADS=1 BLIS_NUM_THREADS=1
PY=/Users/alex.konstantinov/.local/bin/python3
$PY -B -m unittest discover -s docs/issue61_noninferiority/pilot_20261022 -p test_run_pilot.py -v
```

- Original four tests on an exported original driver: **PASS**, exit 0.
- New two refusal methods against the exported original driver: **FAIL**, exit 1,
  16 failed subcases reaching intercepted `Popen` (including the reviewer's
  existing map and failed-preflight marker) and 11 preflight cases reaching input
  reads instead of refusal. The interception prevented all actual jobs.
- The injected-runtime-environment control on the original driver: **FAIL**, exit 1;
  inherited bind/GPU/overlay controls remain present.
- Final repaired package: **PASS, 16/16**, exit 0. CLI rejection checks run the
  real argparse/main in child interpreters with only host root/lock/affinity
  fixture adaptations. Every rejected-state driver control asserts `Popen` is
  never called. A fresh successful-preflight receipt fixture permits exactly one
  intercepted first launch. Container controls compare all six internal argv
  arrays, accept the supported runtime/binary setup, and refuse changed runtime,
  config, options, binaries, setup warnings and inherited environment controls.

`host_checks.json` retains the original-four, old refusal and intermediate 14-test
results with exact source/test digests. `final_host_checks.json` and
`final_fixed_all.log` identify the final 16-test source. Full old-failure logs and
exported original scripts remain in `/tmp/pr65-pilot-repairs-e2048909/`, with log
digests in these receipts. An initial expanded-suite run had four CLI fixture
failures due to macOS `/var` versus `/private/var`; resolving the fixture path fixed
them. No numerical subprocess ran, and no gate/tolerance was changed.

## Exactly one nonnumerical container probe

`ISOLATION_INTENT.json` was frozen at **15:40:47 UTC**, before launch. Its script
is `isolation_probe.py`. The transport was `ssh -J ccp4-gateway 4GPUs`, with
`taskset -c 14,15`, the six numerical thread variables set to 1, empty
`CUDA_VISIBLE_DEVICES`, bytecode disabled, and the existing nonblocking CPU lock.
The new scratch is `/mnt/clathrin/mc-i61-review-isolation-n1yv6cjv`.

**PASS**, SSH/container exits 0, completed **15:40:59 UTC**. One container call
executed `/bin/sh`, mount/environment inspection, tiny disposable writes and
`sha256sum`; it never invoked a RELION executable, analyser or numerical process.
Actual mountinfo proves read-only history/project, plan and copied sources, and
writable scratch/private home/private `/tmp` and `/var/tmp`. Default host home
and `/mnt/clathrin` were not exposed as whole-directory mounts. The disposable
source write failed with `Read-only file system`, and its bytes were unchanged;
all five disposable writable destinations succeeded. No historical write was
attempted. Cwd remained the project, affinity was 14–15, all six thread values
were 1, CUDA visibility was empty, and no Nvidia devices or `--nv` appeared.
Both internal binary hashes matched the historical identities. Stderr was empty,
with no duplicate-bind or refused-HOME warnings.

`isolation_summary.json` retains exact argv, mountinfo/stdout, binary hashes,
fixture error, runtime/config identities, selected config/occupancy information,
and the raw transport digest. Full raw transport remains at
`/tmp/pr65-pilot-repairs-e2048909/isolation_transport.json`; remote `INTENT.json`,
`RESULT.json` and the copied driver remain in that new scratch. No probe retry
occurred. Final driver changes after the probe only pinned the observed
runtime/config identities and rejected empty directories at declared outputs;
the four probed environment/argv helper bodies are byte-identical, recorded in
`resource_release.json`. These extra identity checks have host controls; the
corrected full preflight and numerical workflow remain **UNRUN**.

At **15:44:18 UTC**, a read-only final check confirmed the runtime/config/wrapper
hashes and that the CPU lock was available. That brief lock check was released.
The probe had exited, and no owned service, GPU reservation or lock remains.
D3's GPU3/CPUs10–13 allocation and all other workloads were left alone. No shared
cache was written: both runtime cache/tmp locations were in the new probe scratch.

## Preservation and limitations

All existing pilot artifacts other than the three owned source/document files
are compared byte-for-byte to `2364016` in the new `preservation.json`. Original
executed-driver identities, hashes, first preflight FAIL, successful six-job
receipts, 92-job UNRUN plan and numerical results are not rewritten. The old
worktree stays clean at `2364016`; root stays at `c8844894` with its pre-existing
untracked `pr117-fix-measure-20260929/`. No other branch was moved.

The repair remains numerically **UNRUN**. No reconstruction, postprocess,
jackknife, extraction, accelerated arm, scan, tuning, big-map read, endpoint
reanalysis or dependency installation occurred. The original resolution/B values,
randomization default, seed61/floored19/20 selection, historical source association,
missing SciPy/22-jackknife analyser limitations and scientific INCONCLUSIVE verdict
remain unchanged. The mount probe is engineering evidence only; it establishes
neither scientific qualification, performance nor current-head CI. Parent's fresh
independent review is next; no merge recommendation is made here.
