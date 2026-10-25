# Provider ownership design evidence

[DESIGN-v1.md](DESIGN-v1.md) is a prospective design, not runner/worker implementation or adoption.
All writes this round are confined to this directory, starting at `c7953a46`.

Read-only evidence:

- R6 and the parent v6.1 checkpoint were read in place; neither is copied or modified.
- `public-t3-metadata.json` retains only filtered public metadata from this thread's authenticated
  tool route and `t3_thread_read`: exact thread/run/project/provider/worktree/branch labels and recent
  run metadata. Message bodies and unrelated thread details are omitted. Its read wall-clock was
  not separately captured; the file states that limit.
- `observation-*.json` contains three successful bounded own-ancestry observations. Each snapshot includes PID/birth/UID,
  executable, cwd and parent, with PID birth/parent stability checked before and after the read. Only recognized argv mode words
  and exact comparisons to known public IDs are emitted; no raw argv or environment block is saved.
  The SDK header/layout hash and the inspection script hash are recorded. Inspectors never spawn a
  child or send a signal, and stop before PID 1. No unrelated process arguments were inspected.
- `inspect_ancestry.py` and `inspection-01-FAIL.json` retain the first failed inspection: EPERM at
  PID 1, exit 1, no snapshot written. It is not repaired in place. Separate v2 stops before PID 1;
  v3 adds exact comparisons to the already-public T3 thread/run IDs. No PID 1 retry occurred.
- `preflight-*.json` records the successful probes' exact commands, aggregate load, space, 16 MiB
  cap and nonblocking private inspection lease. No live controller or suite lease was created.

The repeat observations prove app-server reuse across tool invocations. **Cross-thread sharing is
unproven**, as is exclusivity to this task. There is a verifiable public logical task/worktree label,
but no demonstrated persistent OS controller/task binding or complete duplicate-author census.
The design therefore fails closed rather than treating the host or inherited env as a unique owner.

Exact shell command form for each successful inspection (the retained script supplies the APIs and
bounds):

```sh
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 \
/Users/alex.konstantinov/.local/bin/python3 -B \
docs/post_rc0/s1/dc_factorial_20261022/resource_stop_20261022/provider_admission_design_20261023/inspect_ancestry_v2.py
# Second v2 observation is a separate tool invocation. Final observation uses inspect_ancestry_v3.py.
```

No tests or process suite were run. No Popen jobs, signals, SSH, gateway retry, native/GPU work, nested
agents, push/PR/comment/Notion operation or frozen-source/evidence change. Space remained >4 GB and
load averages remained <14 in retained probes; these are observations, not a reservation for a suite.
HASHES.txt hashes the directory's retained files except itself. Private inspection leases end when
an inspector exits; their existence makes no controller-ownership claim.
