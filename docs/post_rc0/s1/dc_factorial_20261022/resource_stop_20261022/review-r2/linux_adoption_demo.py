"""Data-only: real ProcessOwnership.refresh() adoption branch on a synthetic process table. No signals, no /proc."""
import json, sys
from pathlib import Path
T = Path(sys.argv[1])
sys.path.insert(0, str(T / 'tools/multi_gpu'))
import process_ownership as po

W, WPG = 1000, 1000              # worker PID and its process group
class FakeTable:
    def __init__(self, rows): self.rows, self.proc = rows, Path('/proc')
    def pids(self): return list(self.rows)
    def read(self, pid): return dict(self.rows[pid]) if pid in self.rows else None
    def records(self, known=()): return {p: dict(r) for p, r in self.rows.items()}
    def group_live(self, g): return any(r['pgid'] == g and r['state'] != 'Z' for r in self.rows.values())
def row(pid, ppid, pgid, start, state='S'): return dict(pid=pid, ppid=ppid, pgid=pgid, start=start, state=state)
rows = {W: row(W, 1, WPG, 1),
        2000: row(2000, W, 2000, 50),     # job root: Popen(start_new_session=True), watched
        2001: row(2001, 2000, 2000, 51),  # motioncorr under /usr/bin/time
        3000: row(3000, W, 3000, 60),     # sampler's nvidia-smi: Smi._run Popen(start_new_session=True)
        4000: row(4000, W, WPG, 70)}      # control: a helper left in the worker's own group
table = FakeTable(rows)
own = po.ProcessOwnership(table=table)
own.parent_pid, own.parent_group, own.parent_birth = W, WPG, 1
own.adoption, own.child_inventory_mode = True, 'verified-proc-ppid'   # Linux subreaper path, /proc-free inventory branch
own.watch(2000)
own.refresh()
out = dict(step1_owned_live=sorted(r['pid'] for r in own.known_live()),
           step1_verified_group_3000=own.verified_group(3000), step1_verified_group_4000=own.verified_group(4000))
# Job root and motioncorr exit and are reaped; the sampler's query is still in flight (v3 line 350 stops the sampler
# only AFTER the line 336-341 survivor check).
del rows[2000], rows[2001]
own.refresh()
live = own.known_live()
out['step2_after_job_exit_owned_live'] = sorted(r['pid'] for r in live)
out['step2_v3_status_would_be'] = 'EXITED_WITH_OWNED_SURVIVORS' if live else 'EXITED'
out['step2_terminate_groups_would_include'] = sorted({2000} | {r['pgid'] for r in live} - {WPG})
# Polling mode (macOS controls): same table, no adoption.
own2 = po.ProcessOwnership(table=FakeTable({k: v for k, v in rows.items()}))
own2.parent_pid, own2.parent_group = W, WPG
own2.refresh()
out['polling_mode_owned_live'] = sorted(r['pid'] for r in own2.known_live())
print(json.dumps(out, indent=1))
