# #240 Python 3.14 dataset finalization

Implementation head: `ed24e44b614ec158ffa919a356efaa2806b9c309`; unfixed control: `c8844894`.

The private `_RestorationFailed` exception carries only the existing successful-run restoration-failure override to the public entry point, which returns 3. It is raised at the same position as the old finally return, after the unchanged status write and signal-handler restoration. Earlier exceptions, failure return codes, and exceptions from finalization retain their precedence. Nothing changes in worker execution, product publication, metadata, or numerical gates.

Local commands and results (macOS arm64, Homebrew Python 3.14.8):

- `python3.14 -W error::SyntaxWarning -m py_compile tools/multi_gpu/run_dataset.py`: unfixed rc 1, fixed rc 0.
- `python3.14 tests/test_dataset_finalization.py`: unfixed rc 1 solely for the strict compile; fixed rc 0. Sixteen exit/status subcases cover success, worker rc 7, aggregate rc 9, report failure, ordinary try-body exception, signal 15, BaseException, and a pending BaseException after PASS, each with/without restoration failure. The last pair explicitly injects the BaseException into the try body. Status writes, return/exception precedence and handler restoration match unfixed behavior.
- `python3.14 tests/test_dataset_endpoint.py`: rc 0, seven endpoint/withheld-publication controls, including failed worker/report and same-byte late rewrite.
- `python3.14 tests/test_multi_gpu_scheduling.py`: rc 0, 71/71 cases, including owned-worker failures, TERM-ignoring/descendant cleanup, late writers and report failure. These use fake workers; they are not native GPU execution.

§9.4 publication/multi-GPU tooling rows apply: dataset endpoints at 1/2/4 workers and failure injection. `dataset240.sh` adapts only the existing QF driver's CPU allocation to this task's eight-CPU cap: one worker × 8 threads, two × 4, four × 2; all cases stay within CPUs 112–119. It retains the endpoint/product graders and controls. No timing comparison is claimed. The Python tooling is the candidate head; production C++ binaries are unchanged and explicitly reused from the frozen Release builds at F (`6d68e2d6`). Native replay results are recorded after completion.

Native replay on 4GPUs: **PASS, 8/8 dataset endpoints** (G/L × 1/2/4 workers and mixed × 1/2). All worker/shard/publication/cleanup predicates passed, all 12 tutorial pairwise product comparisons passed (including single-process references), mixed product identity passed, and positive/negative byte-flip controls discriminated. Each tutorial PDF has 30 pages; mixed has 12. Full-file diagnostic comparisons differ only in per-movie `.log` files across thread/worker counts; strict MRC/STAR product checks and the identity library pass. These logs are not product or metadata differences.

All four per-GPU locks were held in ascending order, followed by the bench lock; the wrapper verified no foreign GPU process before launching, and released every lock on exit. CPUs 112–119; UUIDs are in the retained summaries and worker records. No remote run was counted from a dropped SSH connection: failed setup attempts had no scheduling log; the successful scheduling run explicitly recorded exit 0 and 71/71. Linux finalization controls also passed.

Frozen binary provenance, exact input hashes, source cleanliness, native driver source and worker status records are in `native/`. `native/logs/endpoint.log` and the summaries retain the raw verdicts. The candidate changes only Python finalization; no C++ rebuild or full three-configuration CTest is required for this tooling class. UNRUN: full QF, fresh performance/scientific acceptance, other format/route campaigns; their historical results keep their earlier SHAs.
