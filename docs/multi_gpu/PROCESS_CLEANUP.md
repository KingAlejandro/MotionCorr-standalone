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
