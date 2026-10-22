# Host qualification attempt03

Narrow registration-support repair after attempt02's retained declaration FAIL.
The checker now handles generated bracket/quoted/bare names, rejects malformed,
missing and duplicate declarations, and uses matching CTest canonical names.
Commands remain generated declarations; full declaration validation does not
claim full runnable collection. All existing required checks remain active.

Host regressions read the retained CMake3.28.3 syntax directly from attempt02's
immutable evidence archive. The old checker fails3/11 tests (bracket forms and
accepted duplicates); fixed checker passes11/11, including missing required names,
quoted/bare forms and malformed syntax. No native math, oracle, adapter, CMake,
original native tests, frozen inputs or numerical tolerances change.

Attempt03 reuses attempt02's Release binaries only after matching every retained
source file, build artifact hash, dependency manifest, tool hash and source archive
hash. Compiled identity remains5c8f6b4f / oracle135ee09e; no fresh compilation is
claimed. New support source is archived separately at the support commit.

Both locks use nonblocking acquisition; CPU ownership is held through execution.
The common build lock is released after identity verification because no build is
needed. Runtime uses CPU8 and numeric threads1. A fresh CTest view byte-copies
original generated declarations/cache, retaining their actual executable/script
commands. Its logs and all temporary outputs go to new task scratch; old source,
build and output trees are read only. Four new and four existing focused commands
must be runnable; every new registration also gets an actual-command drop-one
check. Full unbuilt collection remains outside the claimed runnable subset.

No retry on admission or native failure, placeholder binaries, GPU queries/work,
full suite, corpus, reconstruction, scientific or performance qualification.
