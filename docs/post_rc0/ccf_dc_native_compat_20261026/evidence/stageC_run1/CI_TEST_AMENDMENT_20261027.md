# Stage C seal-test CI correction

The Ubuntu CI run on `7bf1a32f` failed `CcfDcStageCSeal` because its child-environment test required the first `/proc/<pid>/cmdline` sample to equal the spawner's argv or report a read error. A script invoked through a Linux shebang may instead appear with its interpreter prepended. The driver deliberately records this mismatch and does not make it a stop condition.

The test now verifies that the recorded boolean agrees with the actual captured argv, including a deterministic exact-argv control and a shebang-prefixed mismatch control. It also accepts a recorded environment read error when the short-lived child exits before that read. The production source, driver, scoring, frozen experiment rules and Stage C run-1 result are unchanged; the original CI failure and the B3 STOP remain recorded.

Validation: on macOS with CPython 3.13.7 / NumPy 2.4.2 and one numeric thread, the full seal suite passed 20/20. On cpu64 with CPython 3.12.3 / NumPy 2.5.3, CPUs 32–47 and all eight overlapping lane leases held after a fresh guard, the focused `ChildEnvironmentRecord` class passed 3/3, including the real `/proc` path and the deterministic mismatch control. The Linux test emitted the existing `/proc` file `ResourceWarning`s. It used fake producers only; no native movie, GPU or Stage C continuation ran.
