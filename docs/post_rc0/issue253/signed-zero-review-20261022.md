# PR #254 signed-zero checker correction

Base: `e1706ea910ba6ff7728284aa65f3ab33009a03bb`. The live PR head and
fetched `refs/pull/254/head` both matched; this worktree fast-forwarded from
`c8844894c7c6366abf297699b5312e4b775eb5b0` without drift. Read AGENTS.md,
live issue #253, the PR discussion/reviews through issuecomment-6316239378,
and the independent `t3-b88e4ba7/build/review-pr254-e1706ea9/REVIEW.md`.

The P3 finding is fixed by comparing each float component with `memcmp` for
interior preservation and already-Hermitian pass-through. The checker and its
unchanged independent host projection now live in a host-usable test header,
shared by the native inverse test and `HermitianProjectionOracle` CTest.
The shared self-test rejects individual `-0` to `+0` corruptions in both
interior components and in already-Hermitian boundary components, across
8x6, 7x5, 8x5 and 7x6 geometries. The native already-Hermitian fixtures now
contain genuine signed zeros in interiors, boundary pairs and self bins.

Boundary comparisons for general projection remain numerical. The kernel's
`if (u.y != 0.0f)` guard leaves an existing self-bin imaginary `-0` untouched;
it writes canonical `+0` when projecting a nonzero value. Its pair guard
also preserves numerically Hermitian signed-zero pairs. The host reference
uses `+0` for self-bin imaginary parts, so its projected boundary values must
not be compared bytewise to the input. No representation-contract issue was
found in the current source; native confirmation of these fixtures is unrun.

Local results (macOS arm64, Apple clang 21.0.0; occupancy checked on the
14-CPU host, serial checks/build parallelism at most 2, thread caps below):

- PASS: focused CMake build and CTest, **1/1**.
- PASS: standalone shared signed-zero self-test; the native test's extracted
  host oracle self-test, including direct DFT versus double FFTW.
- PASS: restoring both old numeric comparisons, or either one separately,
  makes the regression exit **1** with the corresponding signed-zero error
  (**3/3** mutants rejected). The boundary-only control isolates pass-through.
- PASS: serial emulation of the exact current kernel body on the four small
  geometries preserves signed-zero fixture bytes and maps nonzero self-bin
  imaginary input to `+0`. This is host evidence, not CUDA execution.
- PASS: source audit confirms the output comparator (both **2e-6** gates),
  host projection arithmetic, direct DFT and double FFTW routines unchanged;
  production source and historical evidence unchanged; `git diff --check`.

Commands from this worktree (scratch/logs in `build/p3-pr254-signed-zero/`):

```sh
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=2
cmake -S . -B build/p3-pr254-signed-zero/cmake -DCUDA=OFF -DBUILD_TESTING=ON -DCMAKE_BUILD_TYPE=Release -DPython3_EXECUTABLE=/Users/alex.konstantinov/.local/bin/python3
cmake --build build/p3-pr254-signed-zero/cmake --target hermitian_projection_oracle --parallel 2
ctest --test-dir build/p3-pr254-signed-zero/cmake -R '^HermitianProjectionOracle$' --output-on-failure -j 2
clang++ -std=c++17 -O2 -Wall -Wextra -pedantic tests/test_hermitian_projection_oracle.cpp -o build/p3-pr254-signed-zero/host-check
build/p3-pr254-signed-zero/host-check
python3 build/p3-pr254-signed-zero/check_mutants.py
clang++ -std=c++17 -O2 -Wall -Wextra -pedantic -Itests -I/opt/homebrew/include build/p3-pr254-signed-zero/native_host_oracle.cpp -L/opt/homebrew/lib -lfftw3 -o build/p3-pr254-signed-zero/native_host_oracle
build/p3-pr254-signed-zero/native_host_oracle
clang++ -std=c++17 -O2 -Wall -Wextra -pedantic -Itests build/p3-pr254-signed-zero/kernel_zero_semantics.cpp -o build/p3-pr254-signed-zero/kernel_zero_semantics
build/p3-pr254-signed-zero/kernel_zero_semantics
```

Initial CMake configure selected Python 3.14 without numpy and failed; the
explicit existing Python above resolved that prerequisite. CUDA compile,
native GPU tests, full CPU suite, remote jobs, performance and scientific
validation: **UNRUN**. Earlier suite counts and CI do not qualify this change.
No production kernels, projection convention, dependencies or gates changed;
no push, merge or GitHub comment. Other checkouts, caches, processes and
historical evidence were preserved.
