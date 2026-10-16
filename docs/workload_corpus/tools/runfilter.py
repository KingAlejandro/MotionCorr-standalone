"""Which run records are usable. Shared by analyse.py and suspects.py.

A record is excluded when
  1. it is flagged for foreign load on the lane (/proc/stat deltas) or a settle timeout, or
  2. its CPU time (user+sys) exceeds the minimum CPU time of its cell (family, config, j,
     over every recorded run of that cell) by more than CPU_SUSPECT. The same deterministic
     work takes a very stable CPU time; a run that took much more was disturbed by
     something the lane /proc/stat deltas cannot see (cache or memory-bandwidth contention from
     jobs on other cores; seen while other users' refmac5 jobs ran on cpu64 and not attributable
     to a specific resource).
Rule 2 uses only CPU time, never wall, so it cannot select for a favourable timing. The
profile instrumentation adds negligible CPU, so profiled runs share the cell reference.
For each arm (family, config, j, kind, rep) the last usable record is kept.
"""
CPU_SUSPECT = 0.15


def cell_key(r):
    return (r['family'], r['cfg'], r['j'])


def arm_key(r):
    return (r['family'], r['cfg'], r['j'], r['kind'], r['rep'])


def cpu(r):
    return r['user_s'] + r['sys_s']


def usable_records(runs):
    """Returns (usable by arm, excluded list of (record, reason))."""
    runs = [r for r in runs if r['kind'] != 'warmup' and r.get('ok')]
    floor = {}
    for r in runs:
        k = cell_key(r)
        floor[k] = min(floor.get(k, 1e18), cpu(r))
    usable, excluded = {}, []
    for r in runs:
        if r['flag_foreign']:
            excluded.append((r, 'foreign load or settle timeout'))
        elif cpu(r) > (1 + CPU_SUSPECT) * floor[cell_key(r)]:
            excluded.append((r, 'cpu time +%.0f%% over cell minimum' % (100 * (cpu(r) / floor[cell_key(r)] - 1))))
        else:
            usable[arm_key(r)] = r          # later records replace earlier ones
    return usable, excluded
