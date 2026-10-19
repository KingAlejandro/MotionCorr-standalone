#!/usr/bin/env python3
"""Grade the W-D11 in-product matrix: route, log witnesses, products vs standalone, cleanup."""
import json, re, struct, sys
from pathlib import Path
W = Path('/mnt/clathrin/alex-motioncorr-rc0/W-D11/runs')
SETS = {'S1': ('auto', ['e10216', 'tut26', 'tut27']), 'S2': ('nvcomp', ['e10216d', 'tut26', 'tut27']),
        'S3': ('auto', ['e10216', 'e10164', 'tut26']), 'S4': ('auto', ['e10441', 'tut26', 'e10164'])}
FREE = {'S1': '8.5', 'S2': '8.5', 'S3': '8.5', 'S4': '16'}

def mrc(p):
    d = p.read_bytes(); ns = struct.unpack_from('<i', d, 92)[0]
    return d[:224] + d[1024 + ns:]           # header fields before the labels, plus payload

def prods(out, m):
    r = {}
    for ext in ('.mrc', '.star'):
        p = out / 'Movies' / (m + ext)
        if p.exists():
            r[ext] = mrc(p) if ext == '.mrc' else p.read_bytes()
    return r

def logw(out, m):
    p = out / 'Movies' / (m + '.log')
    if not p.exists():
        return {}
    t = p.read_text(errors='replace')
    free = re.findall(r'free device memory (\d+) of (\d+) MiB', t)
    return {'cuda_error': [l.strip()[:120] for l in t.splitlines() if 'CUDA Error' in l],
            'fallback': [l.strip()[:120] for l in t.splitlines() if 'Falling back' in l or 'failed recoverably' in l],
            'batched_free_mib': [int(a) for a, _ in free]}

rows = []
for arm in ('main', 'fix'):
    for s, (ingest, ms) in SETS.items():
        run = W / f'{arm}-{s}'; res = json.loads((run / 'result.json').read_text())
        out = run / 'out'; so = (run / 'stdout.txt').read_text(errors='replace')
        routes = dict(l.split() for l in res['witness'] if l)
        failed = sorted({l.strip() for l in so.splitlines() if 'Motion correction failed for' in l})
        row = {'run': f'{arm}-{s}', 'ingest': ingest, 'free_gib': FREE[s], 'exit': res['exit'], 'wall_s': res['wall_s'],
               'job_failure': failed, 'oom_site': sorted(set(re.findall(r'out of memory in \S+/(src/\S+) at line (\d+)', so))),
               'gpu_after': {'free_used_mib': res['after_free_used_mib'], 'apps': res['after_apps']},
               'movies': []}
        for i, m in enumerate(ms):
            ref_ingest = '-nvcomp' if ingest == 'nvcomp' else ''
            refrun = W / f'ref-{m}{ref_ingest}'
            entry = {'movie': m, 'route': routes.get(f'Movies/{m}' + {'e10216': '.mrcs', 'e10216d': '.tiff', 'tut26': '.tiff', 'tut27': '.tiff', 'e10164': '.mrcs', 'e10441': '.tif'}[m]),
                     'products': sorted(prods(out, m)), 'log': logw(out, m)}
            if i > 0:
                ref = prods(refrun / 'out', m)
                entry['identical_to_standalone'] = bool(ref) and prods(out, m) == ref
                refb = W / f'ref-{m}{ref_ingest}-at{FREE[s]}'
                if (refb / 'out').exists():
                    rr = json.loads((refb / 'result.json').read_text())
                    entry['standalone_at_same_free'] = {'free_at_launch': rr['free_mib_at_launch'],
                                                        'batched_free_mib': logw(refb / 'out', m).get('batched_free_mib'),
                                                        'route': rr['witness'][0].split()[1] if rr['witness'] and rr['witness'][0] else None}
            row['movies'].append(entry)
        rows.append(row)
Path(sys.argv[1]).write_text(json.dumps(rows, indent=1))
for r in rows:
    print(f"{r['run']:<8} ingest={r['ingest']:<6} free={r['free_gib']:>4} exit={r['exit']} wall={r['wall_s']:>5} oom={r['oom_site']} gpu_after={r['gpu_after']}")
    print(f"         job: {r['job_failure']}")
    for e in r['movies']:
        print(f"   {e['movie']:<8} route={e['route']} prods={e['products']} identical={e.get('identical_to_standalone')} "
              f"cudaerr={len(e['log'].get('cuda_error', []))} fallback={e['log'].get('fallback')} free={e['log'].get('batched_free_mib')} "
              f"standalone={e.get('standalone_at_same_free')}")
