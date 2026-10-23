# Data-only: verify each v5_mutants.json replacement target is unique in the exact worker blob, emit mutants, compile in memory.
import json, sys, hashlib
from pathlib import Path
tools = Path(sys.argv[1]); out = {}
src = (tools / 'gpu_worker_v5.py').read_text()
for name, spec in json.loads((tools / 'v5_mutants.json').read_text()).items():
    s, counts = src, []
    for a, b in spec['replace']:
        counts.append(s.count(a)); s = s.replace(a, b)
    compile(s, name, 'exec')
    p = tools / f'_r4mutant_{name}.py'; p.write_text(s)
    out[name] = dict(only=spec['only'], target_counts=counts, changed=s != src, sha256=hashlib.sha256(s.encode()).hexdigest())
# R4-only extra mutants (data-only K30 / branch coverage probes)
extra = {
 'k30_default_prefix_l': [("'taskset -c {cpu} /usr/bin/time -v -o {out}/time-v.log'", "'taskset -c {cpu} /usr/bin/time -l -o {out}/time-v.log'")],
 'k30_default_prefix_no_taskset': [("'taskset -c {cpu} /usr/bin/time -v -o {out}/time-v.log'", "'/usr/bin/time -v -o {out}/time-v.log'")],
 'loop_branch_root_signal_only_removed': [("            signal_root(root, grace, signalled)  # R3-m2: descendants unverified, root only\n            return signalled, errors",
                                           "            return signalled, errors")],
 'errors_branch_root_signal_removed': [("        signal_root(root, grace, signalled)\n        return signalled, ['observer errors: '", "        return signalled, ['observer errors: '")],
}
for name, reps in extra.items():
    s, counts = src, []
    for a, b in reps:
        counts.append(s.count(a)); s = s.replace(a, b)
    compile(s, name, 'exec'); (tools / f'_r4mutant_{name}.py').write_text(s)
    out[name] = dict(target_counts=counts, changed=s != src, r4_extra=True)
print(json.dumps(out, indent=1))
