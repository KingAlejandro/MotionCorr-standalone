# Attempt 1: NONQUALIFYING

Configured with a stub `numpy` package on `PYTHONPATH` that bypassed the real-NumPy requirement in `CMakeLists.txt`
(the stub's own comment wrongly says real numpy is absent on the host; it was absent only for the interpreter CMake
chose). Nothing here supports a qualification claim.

The `mut_*` files are the saved mutant logs. `mut_m1.log` is a NumPy configure failure; the others end at "Built target"
and contain **no test verdicts**. The runtime mutant kills reported in conversation (call site passing `false`, global
leak, half-width, capture-guard term removed) are therefore **UNVERIFIED**; static review supports that each defect would
fail the tests. The mutants were not rerun with a real NumPy. `INDEX.txt` is the original author index. Full logs and the
stub package are in the durable copy (see EVIDENCE_INDEX.md).
