# Failed owning-device selection

Bounded repair against PR140 `1ae23cf77992c5e8161fc33181ba583ec8564f6a`.
The previous four drop methods discarded their entry and attempted release even
when `cudaSetDevice` failed. Cleanup could then address the unrelated current
context and permanently lose the only owned handles.

The repair invalidates reuse before selection but retains ownership on selection
failure. No free or plan destruction is issued until the owning device is
selected. Pending entries remain in byte accounting and can be retried through
checked `dropAll()` or unused-entry eviction. A fatal retirement remains sticky;
successful cleanup retry does not make it reusable. Selection failure alone
cannot count as an eviction. Successful release ordering is unchanged.

## Host controls executed

`python3 tests/run_worker_pool_cleanup_host.py --work <evidence-directory>`
compiles the actual `cuda_worker_pool.cu` against explicit host API doubles.
Six binaries use one unchanged oracle: candidate, predecessor drop source with
the current header, and four mutants that ignore one owning-device selection
guard. Candidate exercises four resource classes through replacement, eviction,
drop-all and retirement: 16 controls. The predecessor and each guard mutant must
fail the specific wrong-context release assertion for its resource class.

This is production ownership/control-flow evidence, not a GPU or cuFFT result.
The doubles represent two separate contexts and preserve allocations/handles
when an attempted release addresses the wrong one. Raw compiler commands,
binary/source hashes, output and exit statuses are retained by the driver.

## Native acceptance still required

`cuda_worker_pool --case device-cleanup` adds 16 actual-entry controls using the
existing native API wrappers. A failed `cudaSetDevice` is returned without
selecting the device, with the error slot cleared. Each control asserts zero
release calls, retained ownership and bytes, invalidated key refusal, checked
retry and idempotent teardown. Existing full-suite healthy cross-device
restoration/admission controls remain unchanged. One device can exercise the
returned-status boundary; two visible devices additionally keep the current
physical context different from the owner. Native execution, rebuilt CUDA suites
and native compiled guard mutations are **UNRUN** for this repair.

No timing, memory-cap policy, arithmetic, geometry or worker-pool consolidation
change is included. Permanently inaccessible contexts may retain resources until
process teardown; no wrong-context release is used to hide that limitation.
