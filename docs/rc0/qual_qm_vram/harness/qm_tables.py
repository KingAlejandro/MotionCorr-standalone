import json, collections
rows = json.load(open('/mnt/clathrin/alex-motioncorr-rc0/W-QM/final/cases.json'))
def outcome(r):
    if r['exit'] != 0:
        if r['ingest'] == 'compact' and not r['route']:
            return 'FAIL-FAST (pinned compact refused)'
        adm = [x for x in r['route'] if x != 'float']
        if adm and 'patch-prep-declined' in r['flags']:
            return 'FAIL (session admitted, patch-stage OOM)'
        return 'FAIL (streaming OOM)'
    fl = r['flags']; route = r['route']
    if r['n_movies'] > 1:
        tag = ','.join(route)
    else:
        tag = route[0]
    if not fl:
        return f'OK {tag}'
    if 'session-init-OOM->streaming' in fl and len(fl) == 1:
        return 'OK streaming (session declined)'
    return 'OK degraded: ' + '+'.join(f.split('->')[1] for f in fl)
single = [r for r in rows if not r['family'].startswith('mm') and r['case'].endswith(tuple('@%s' % x for x in ('40','24','16')))]
single = [r for r in rows if not r['family'].startswith('mm') and '_bis' not in r['case'] and '_scan' not in r['case'] and not r['case'].endswith('@none')]
out = []
out.append('### Main matrix (free VRAM measured after the balloon, GPU1)\n')
out.append('| Movie | Config | `--ingest` | free GiB (nominal) | exit | route | wall s | products vs unconstrained | outcome |')
out.append('|---|---|---|---:|---:|---|---:|---|---|')
for r in sorted(single, key=lambda r: (r['family'], r['config'], r['ingest'], -r['free_mib'])):
    ident = {True: 'identical', False: '—', None: '—'}[r['products_identical']] if r['exit'] == 0 else 'no products'
    out.append(f"| {r['family']} | {r['config']} | {r['ingest']} | {round(r['free_mib']/1024,1)} | {r['exit']} | {','.join(r['route']) or '—'} | {r['wall_s']:.1f} | {ident} | {outcome(r)} |")
out.append('')
out.append('### All constrained probes (main matrix, bisection and scan runs)\n')
out.append('Free VRAM in GiB measured after the balloon; outcome as above. `ident` = corrected image, motion STAR and joint STAR identical to the unconstrained run (products-only comparison).\n')
groups = collections.defaultdict(list)
for r in rows:
    if r['case'].endswith('@none') or r['family'].startswith('mm'):
        continue
    groups[(r['family'], r['config'], r['ingest'])].append(r)
for k in sorted(groups):
    out.append(f"**{k[0]} {k[1]} --ingest {k[2]}**\n")
    out.append('| free GiB | exit | route | wall s | host RSS GiB | ident | outcome |')
    out.append('|---:|---:|---|---:|---:|---|---|')
    seen = set()
    for r in sorted(groups[k], key=lambda r: r['free_mib']):
        key2 = (r['free_mib'], r['exit'], tuple(r['route']))
        out.append(f"| {r['free_mib']/1024:.2f} | {r['exit']} | {','.join(r['route']) or '—'} | {r['wall_s']:.1f} | {((r['max_rss_mib'] or 0)/1024):.1f} | {'yes' if r['products_identical'] else ('n/a' if r['exit'] else '—')} | {outcome(r)} |")
    out.append('')
out.append('### Multi-movie jobs\n')
out.append('| Job | free GiB | exit | routes (movie 1, 2, 3) | movies with products | per-movie products identical | notes |')
out.append('|---|---:|---:|---|---|---|---|')
for r in sorted([r for r in rows if r['family'].startswith('mm')], key=lambda r: (r['family'], r['config'], -r['free_mib'])):
    if r['case'].endswith('@none'): continue
    out.append(f"| {r['family']}-{r['config']} | {r['free_mib']/1024:.1f} | {r['exit']} | {','.join(r['route'])} | {r['movies_with_products']}/{r['n_movies']} | {r['products_identical']} | {','.join(r['flags'])} |")
open('/mnt/clathrin/alex-motioncorr-rc0/W-QM/final/tables.md', 'w').write('\n'.join(out) + '\n')
print('\n'.join(out)[:200])
