# #235 test hygiene evidence

Base: c8844894c7c6366abf297699b5312e4b775eb5b0. Implementation head: d7e797f9bc01f155733f2dee3cdec3a473c3c288.
Host: local macOS arm64. Python 3.13.7; CMake/AppleClang Release (-O3 -DNDEBUG), two build jobs. No GPU or timing claim.

`python3 tests/test_hygiene_235.py`: before fix rc 1, both controls fail; after fix rc 0, both pass.
The cleanup control creates an actual late file immediately before rmdir under a simulated network TMPDIR, causing ENOTEMPTY.
The fixed selftest avoids that path with local /tmp scratch and restores both tempfile.tempdir and TMPDIR afterwards.
The dependency control injects ImportError for PIL with both EER inputs supplied; old code returns no failures, new code returns an explicit NOT RUN failure.
CTest uses SKIP_RETURN_CODE 77 for NativeMovieStaging; this fix deliberately fails an explicitly requested but incomplete section instead of skipping the whole otherwise-completed test.

Commands (all final exit statuses 0):
```sh
cmake -S . -B /tmp/mc-hygiene/build235 -DCMAKE_BUILD_TYPE=Release -DCUDA=OFF -DBUILD_TESTING=ON -DPython3_EXECUTABLE=$(command -v python3)
cmake --build /tmp/mc-hygiene/build235 --target motioncorr -j2
python3 tools/profiling/mcprof.py selftest
ctest --test-dir /tmp/mc-hygiene/build235 -R '^(ProfilingKit|TestHygiene235|TruncatedGainDefect)$' --output-on-failure
```

Affected CTests: 3/3 passed. Direct ProfilingKit: 134 internal tests, one existing platform skip.
The initial configure without an explicit interpreter failed because auto-selected Python 3.14 lacked NumPy; it was corrected to Python 3.13.7 with NumPy 2.4.2 before the successful Release build.
PanFS and real EER inputs were not run; no GPU, numerical, performance or scientific acceptance claim. Tests-only re-entry does not require QF.
