# Prelaunch amendment 1: report subprocess cleanup

Frozen after the protocol and initial uncommitted driver draft, before any
driver/native execution. Source inspection shows that `--skip_logfile` skips
track plots but still generates dataset PDFs via subprocesses. The assumption
that this argv cannot have child processes was wrong.

Keep argv and all acceptance criteria unchanged. Launch each CPU application in
its own new session/process group. For timeout or an exception while its direct
root is still unreaped, signal only that new group through the known Popen root
(never the parent's group): TERM, bounded wait5s, then KILL and bounded wait5s.
Record the signal/exit/cleanup result. Do not launch another patch after an
exception. This amends the protocol's direct-child-only timeout cleanup.

Additionally compare the per-movie `affine.log` byte-for-byte with the retained
one. It contains all patch iteration lines and establishes that the selector
did not change those recorded decisions. This strengthens neutrality; no
numerical gate or tolerance changes. No build, native process or GPU operation
has run for this new capture at this freeze.
