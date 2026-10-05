# Current-main composition and saved-EER review delta — 5 October

Source `26cee51f46d1908116f53f620cbaf2f5773b4e97` retains author head `0be2463` and merges main `78473ccd` through `a0979b0`. The union preserves CompressedMovieSequence, MicrographModelBounds and JointStarPublication, including count-preserving missing-name controls; required inventory/CI minimum is35. No numerical gates changed.

Codex review r4184680992 identified saved EER grouping narrowing/positivity omitted from the original bounds check. Both EER integer fields now read as long before narrowing. Grouping must be positive within int; upsampling preserves the actual renderer-supported -1,1,2,3 modes, including absent-field default -1. Missing grouping is refused. This validates saved metadata and the real completion decision; no EER input is decoded here.

On Mac CPU Release, collection35/35 passes;33 tests pass, SyntheticRegression retains the known exact-baseline failure (raw output retained), and Linux-only NativeMovieStaging RSS is skipped. Actual parser/query/resume suite passes normally and under Python -O: original38 malformed records/9 invalid queries,7 valid EER records/11 malformed EER records and3 corrupt-hotpixel resumes. Eight CI boundary tests pass, preserving required-name negative controls.

Powered EER negatives invoke the real Micrograph constructor and MotioncorrRunner::isMovieComplete with a complete numerical MRC and all four saved frame rows. The actual a0979b0 production predecessor (only new test-adapter modes added) accepts all11 malformed EER records and marks them complete; the candidate rejects parsing and returns incomplete, without modifying products. Both normal/-O raw outcomes are retained. No simulated reimplementation of the production predicate is used.

Commands, from this checkout (configured Python executable is the bundled runtime):

```
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON -DCUDA=OFF -DPython3_EXECUTABLE=<runtime-python>
cmake --build build --parallel 4
python tools/validate_test_collection.py --test-dir build --min-count 35
ctest --test-dir build --output-on-failure --parallel 2
python tests/test_micrograph_model_bounds.py --binary build/motioncorr --helper build/runner_numerics
python -O tests/test_micrograph_model_bounds.py --binary build/motioncorr --helper build/runner_numerics
python tools/test_ci_fail_closed.py -v
```

Current composed CUDA compilation awaits CI. Native CUDA, EER codec runtime and performance are UNRUN. Original targeted model-object ASan/UBSan evidence remains at author head; LeakSanitizer remains unrun. Processing-identity receipts remain a separate branch; when composed, keep local-model RAII ownership until receipt parsing also accepts every table.
