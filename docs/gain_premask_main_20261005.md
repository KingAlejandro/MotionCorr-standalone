# PR143 composition with saved-model main

Source composition: `c07014138339f9f9cba0ea126b7c1c3815e08da0`.
Parents: gain/test-isolation `c0fcbe9d6a3480c6e1b949a3ecd8b0361163382e`
and main `282eb7de8c14d969603fed812d8ad647f975764e` (PR148).
This update supersedes the baseline and collection count in
`gain_premask_current_main.md`; historical evidence remains unchanged.

## Source review

The merge preserves existing author history. The sole conflict was the
fail-closed collection harness: keep both gain ownership and saved-model bounds
names, the count-preserving missing-name controls, and the 36-test minimum in CI.
Shared saved-model/parser source and the numerical helper match main exactly.
CUDA, gain cache, kernel arithmetic, premask/RNG order, and the preceding fresh
process CUDA fault isolation are unchanged from the gain parent. No new external
implementation or license dependency is introduced.

## Executed CPU checks

AppleClang Release, CUDA off, build parallelism four, runtime Python with NumPy.
The existing local build directory was retained and reconfigured.

- Build and required-name/minimum collection: PASS, 36 tests.
- Focused CTest: `GainCacheOwnership`, `GainCache`, `MicrographModelBounds`,
  `CiFailClosedControls`, 4/4 PASS.
- Actual saved-model/EER parser and completion controls: PASS normal and Python
  `-O`; seven valid and eleven malformed saved-EER cases, 38 malformed saved
  models, fractional/sparse/mask/round-trip and real hot-pixel resume controls.
- Actual gain header host controls and powered predecessor/guard mutants:
  PASS under Python `-O`, including its repeated optimized child.
- Diff whitespace check: PASS.

The collected required names are: `PatchRetryState`, `RunnerInterpolateRecenter`,
`MrcHeaderStats`, `PdfConcat`, `DefectParser`, `DeflateLayout`, `ScratchArena`,
`DefectNeighbours`, `GainCacheOwnership`, `NvcompGuards`, `SyntheticRegression`,
`HotPixelRngDeterminism`, `RunnerExposure`, `Runner_failure`, `Runner_invalid`,
`Runner_resume`, `Runner_tomography`, `RunnerLateBin`, `RunnerExportedUnits`,
`GainCache`, `TiffRead`, `DamagedMovie`, `CompressedMovieSequence`,
`GlobalIfftElision`, `RunnerModelParser`, `MicrographModelBounds`,
`RunnerInterpolateShifts`, `WriteFaults`, `WriteFaultsSync`,
`WriteFaultsMultiProduct`, `OutputStageFaults`, `CiFailClosedControls`,
`OutputTreeComparator`, `JointStarPublication`, `ImageWriteFaults`, and
`NativeMovieStaging`.

## Remaining acceptance

This is a focused CPU result, not a full 36-test suite PASS. The inherited Mac
synthetic-reference failure and Linux-only staging RSS skip remain retained in
the earlier records; neither gate was changed. Current-composition CUDA
compilation, Linux CI and full-product native CUDA acceptance are UNRUN here.
Saved-EER parsing controls do not establish EER decoding acceptance. Freeze the
new source/bundle and unchanged-main baseline before the qualified native replay;
retain all prior failed native runs. No fresh performance or scientific claim is
made. No push or product merge was performed for this composition.
