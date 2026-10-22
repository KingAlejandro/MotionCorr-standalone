# Independent parent diagnosis of the CPU pair grader, 23 October 2026

Reviewed source/evidence head `cbd298a747b77c672c63e58fa050ddf7907a5229`, including author diagnosis6f31f1f4; native test source3751bd05a95412dff468557141f2e7e01ad21831. The parent did not write the original N3 grader or author diagnosis. This check is independent of their parsing code: standard-library line/schema parser and exact finite Decimal equality, no imported grader, no tolerance. Scope is retained STAR/global-row evidence only. This is not an independent latest-head review of the whole guard fix.

**The original CPU subset remains FAIL:** 24 native row PASS,3 pair PASS/5 pair FAIL,16 CUDA UNRUN. No original script, grade, prediction, result or native output changed. No full regrade was run.

## Finding and evidence

At `tools/n3.py:69,130–134`, the global block is the raw text after data_global_shift up to the next data_ marker. The pair rule requires raw-string equality. In the five decision-flip cases, accepted models produce a following local-motion block and a version comment; rejected models end the STAR after global shifts. Comments/trailing blank lines differ even though the actual trajectories agree. The writer emits global rows before the conditional local model (`src/micrograph_model.cpp:247–261`). In the tested own-implementation path the global shifts are set at `motioncorr_runner.cpp:3378`, before local fitting and guard3918; other setters belong to the external route.

`check_retained_rows.py` reads regular STAR members of the hash-pinned552,960-byte evidence.tar in memory, without extracting or executing an archive member. All24 STARs contain exactly12 finite rows with frames1–12 and the expected three labels. All8 cases have exact printed numeric equality across base/candidate/mutant. The legacy expression differs in exactly the five recorded failed pairs; stripping only comments/blank lines restores raw-block equality. All five retained pair records have correct decision-flip/image-relation booleans and fail the global-text term. The archive digest is3cc13020d35aaf7113fe16878e8eb63c11652863fd73c0da3974fc7fa09f2760.

Five focused controls using actual native STAR text pass: one1e-6 value change is detected; missing row, duplicate row and NaN are rejected; real-writer following-model presence changes raw text while preserving rows. The script exited0 on macOS/Python3.13.7, stdlib only, after a local occupancy read. No numerical library/thread pool, SSH, build, native or GPU execution. CHECK.json binds every consumed STAR; INPUT_BINDINGS.json binds source/original grader/results.

## Corrections, limits and next action

The author conclusion is supported at **printed precision**. STAR formatting uses variable fixed/scientific precision, so the author's generic “6 significant digits” wording is not an exact contract. No in-memory full-precision trajectory was dumped. The independent check does not establish full-precision equality or CUDA behavior, and is not a production/science/performance PASS.

A separately versioned grader may compare exact parsed finite `(frame,x,y)` values and require complete unique expected frames/labels. Keep every other decision, coefficient, image-relation, mutant and CPU-only coverage requirement unchanged. Use real-writer positive controls plus wrong-value/missing/duplicate/nonfinite controls. Review that implementation before applying a separately labelled regrade. Preserve the old FAIL and all old artifacts.

The local archive lacks MRC payload members. Therefore this diagnosis does not rerun or independently verify image equality/inequality. A full subset regrade must bind and read the immutable original product payloads (or explicitly identify reliance on the retained original image booleans), plus source/binary/injection/RUN identities, in a new namespace. No new native run is needed or authorized here. The16 CUDA rows/full aggregate remain UNRUN/INCOMPLETE.
