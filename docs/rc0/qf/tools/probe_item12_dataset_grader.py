#!/usr/bin/env python3
"""Negative controls for item12_retry.grade_dataset(): runs that never exercised the fault must FAIL.

  1. rc 127, empty output directory (no status file, no workers, no refusal witness) graded as each
     expectation (poison_one, poison_both, pass);
  2. a FAIL status file with dataset_ready false but no workers/status.json;
  3. a complete-looking FAIL status with two workers on their devices and cleanup complete, but no fault
     injected or refusal in either console log (the fault never ran).
Every one must be reported with at least one problem. Exit 0 only if all are rejected.
  QF_W=... QF_CPUS=... QF_GPU_UUID=... QF_GPU_LOCK=... python3 tools/probe_item12_dataset_grader.py
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import item12_retry as m  # noqa: E402

GPUS = ['GPU-aaaaaaaa-0000-0000-0000-000000000000', 'GPU-bbbbbbbb-0000-0000-0000-000000000000']
ok = True


def expect_fail(name, problems):
    global ok
    good = bool(problems)
    ok &= good
    print(f"{'ok ' if good else 'BAD'} {name}: {len(problems)} problem(s); first: {problems[:2]}")


with tempfile.TemporaryDirectory() as tmp:
    t = Path(tmp)
    empty = t / 'rc127'
    empty.mkdir()
    for exp in ('poison_one', 'poison_both', 'pass'):
        expect_fail(f'rc 127, no files, expect={exp}', m.grade_dataset('x', empty, 127, 2, exp, GPUS, fault_worker=1))

    only_ds = t / 'only_ds'
    only_ds.mkdir()
    (only_ds / 'dataset_status.json').write_text(json.dumps({'verdict': 'FAIL', 'dataset_ready': False,
                                                             'failure': 'Worker phase exited 3'}))
    expect_fail('FAIL status, no workers/status.json', m.grade_dataset('x', only_ds, 3, 2, 'poison_one', GPUS, fault_worker=1))

    nofault = t / 'nofault'
    (nofault / 'workers').mkdir(parents=True)
    workers = []
    for k in range(2):
        wd = nofault / 'workers' / f'w{k}'
        (wd / 'Movies').mkdir(parents=True)
        (wd / 'launcher.console.log').write_text('[qf-fault-wrapper] fault=off\nall good\n')
        workers.append({'index': k, 'returncode': 1, 'log': str(wd / 'launcher.console.log')})
    (nofault / 'dataset_status.json').write_text(json.dumps({'verdict': 'FAIL', 'dataset_ready': False,
                                                             'failure': 'Worker phase exited 3', 'process_ownership_errors': []}))
    (nofault / 'workers' / 'status.json').write_text(json.dumps({
        'n_workers': 2, 'workers': workers, 'devices': [{'uuid': g} for g in GPUS],
        'gpu_witness': {'all_pids_witnessed_on_intended_distinct_devices': True, 'distinct_devices_witnessed': 2},
        'process_cleanup': {'complete': True, 'observed_live_before_cleanup': [], 'unexpected_descendants': False},
        'verdict': 'FAIL'}))
    for exp in ('poison_one', 'poison_both'):
        expect_fail(f'FAIL status, workers present, fault never ran, expect={exp}',
                    m.grade_dataset('x', nofault, 3, 2, exp, GPUS, fault_worker=1))
print('PROBE', 'PASS' if ok else 'FAIL')
sys.exit(0 if ok else 1)
