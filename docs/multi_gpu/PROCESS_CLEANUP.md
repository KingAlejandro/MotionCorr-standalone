# Checked worker cleanup

The launcher and dataset coordinator retain each launched root's PID and birth
identity, and observe descendants while their parent-child identity can still
be verified. Linux uses `/proc` start ticks; macOS uses the SDK `libproc`
process-birth seconds/microseconds. This identity observer is separate from
Linux RSS sampling, which remains unavailable on macOS.

Immediately before **each** TERM or KILL, cleanup requires an original live
root or an observed live descendant with the same PID/birth identity in that
group. An exited `Popen.pid` or an ambient group number is insufficient.
Observed children remain tracked after reparenting. Missing identity evidence
fails cleanup explicitly and sends no guessed signal. Refused unrelated groups
are not waited on as though they were owned. The coordinator retains failure
and cleanup-error information; absence of observed live descendants is scoped
to this observation, not a claim that polling can recover unseen children.

`tests/test_process_ownership.py` calls the actual shared cleanup helper. It
covers a recycled numeric PID/group (mocked, no real unrelated process is ever
signalled), an observed reparented TERM-ignoring child, a birth change between
TERM and KILL, and a real fixture-owned TERM-ignoring child after its original
parent exits. The latter creates its own new session and verifies its birth
before fixture cleanup. Both normal and optimized Python execute explicit
checks. The retained pre-repair helper fails the no-signal control.

Limitations: process polling cannot recover children born and exited between
observations. PID/birth checks narrow signalling to verified owned identities;
portable group signalling still has a syscall race between the final identity
check and the signal. Native Linux worker/aggregate failure acceptance is a
separate required row; the host controls are not GPU execution evidence.

Every launched-worker outcome, including an ordinary nonzero return and a zero
return, reaches checked cleanup while the identity observer is still active.
Only after cleanup and bounded waiter completion does the observer stop and the
launcher publish its verdict. An unexpected recorded live descendant makes the
outcome FAIL even if cleanup drains it and the original worker returned zero.
The original worker return code and diagnostic remain visible separately from
the cleanup result. Observation errors refuse every signal and fail closed.

The process-ownership suite also executes the actual launcher with a worker
that returns 7 or 0 while its observed TERM-ignoring child survives reparenting;
the zero-return case gives that child a separate session. It requires the same
birth identity, checked TERM receipt, no surviving owned child, FAIL without
worker completion, and preservation of the original return and diagnostic. A
quiescent zero-return worker still passes. These are device-free lifecycle
controls: they support no CUDA, movie-output, throughput, or unseen-child claim.

If identity evidence refuses cleanup while a worker remains live, the launcher
returns a bounded FAIL instead of waiting indefinitely for that worker. Its
return code and exit timestamp remain null, `exit_observed` is false, and the
last observation timestamp is separate from an exit. Incomplete exit spread is
not reported as a measured worker tail. The refusal control interrupts the
actual launcher with an injected observation failure and independently verifies
that the worker remains alive and unsignalled until fixture-only birth-checked
cleanup. It fails against the prior source in normal and optimized Python.

## Fast reparenting boundary (6 October 2026)

Actual Linux launcher execution now enables and reads back `PR_SET_CHILD_SUBREAPER`
before worker/observer/helper launch. A worker orphan that survives between all
parent-edge observations becomes a launcher child, including double-fork and
`setsid` cases. Newly adopted children outside the launcher group are recorded by
PID/birth before signalling. Pre-existing live launcher children refuse activation
and remain untouched: their future orphans would otherwise be ambiguous. Missing
live child identity refuses cleanup. The prior subreaper state is restored only
after checked cleanup/reaping. Import, partition and merge do not alter this
process-wide setting. This uses the Linux syscall, with no new dependency.

Native device execution on non-Linux is refused. Portable device-free simulated
CPU controls remain available there with `observed-descendants-only` scope; they
do not certify arbitrary native descendant containment. RSS still has its own
sampling limitations. PID/birth verification retains the portable signal syscall
race; no unrelated process-name/group signalling is added.

The actual launcher adversary double-forks, creates a new session, ignores TERM,
and exits both intermediate parents while the observer interval is deliberately
30 seconds. The final child must be adopted/drained before verdict, the original
worker return must remain 0, and the verdict must be FAIL. Exact predecessor
5974 leaves the child alive and fails this control; the fixture alone cleans its
retained birth afterward. Normal/-O checks also cover unreadable adopted birth,
pre-existing-child refusal, readback/restoration, and healthy no-child behavior.
These are CPU lifecycle controls; current native hardware acceptance remains UNRUN.

The launcher validates its own PID/birth and every extant thread's child inventory
before activation. A missing live launcher identity/inventory refuses before any
worker starts. Restoration requires original roots to have exited and two empty
owned-child observations after callers stop launching work and join observers.
This establishes the bounded quiescent cleanup contract used by these tools; it
is not a security containment guarantee against arbitrary concurrent forking.
A failed activation readback still retains restoration responsibility, and the
powered control verifies the previous state is restored without launching helpers.

Linux kernels without `CONFIG_CHECKPOINT_RESTORE` omit `task/*/children`.
If a live launcher thread has no such file, the launcher falls back to an
actual `/proc` PID/birth/PPID inventory across all threads. Every enumerated
identity must be readable or proved disappeared; permission/invalid records
refuse rather than silently hiding a child. Launcher birth is checked again
at completion. This fallback preserves the pre-existing-live-child refusal
and checked subreaper adoption/restoration; it does not extend the lifecycle
contract into a security containment claim.
