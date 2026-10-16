#!/usr/bin/env python3
"""Join device and host per-fraction verdicts for the mutated fixtures.
usage: classify_malformed.py <malformed-out-dir> <fixture-dir> > table.md   (writes summary JSON next to the table)"""
import json, os, sys, collections

out, fx = sys.argv[1], sys.argv[2]

def jl(path):
    rows = {}
    if not os.path.exists(path):
        return rows
    for line in open(path):
        line = line.strip()
        if line.startswith('{'):
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if 'f' in d:
                rows[d['f']] = d
    return rows

manifest = {r['f']: r['mutation'] for r in json.load(open(os.path.join(fx, 'mut48.manifest.json')))['fractions']}
summary = {}
print('| ups | f | mutation | host release | host ASan | device | verdict |')
print('|---:|---:|---|---|---|---|---|')
for u in (1, 2):
    dev = jl(f'{out}/dev.mut48.u{u}.run1.jsonl')
    base = jl(f'{out}/dev.base48.u{u}.run1.jsonl')
    hr = jl(f'{out}/host.mut48.u{u}.release.jsonl')
    ha = jl(f'{out}/host.mut48.u{u}.asan.jsonl')
    cats = collections.Counter()
    for f in sorted(manifest):
        d, b, r, a = dev.get(f), base.get(f), hr.get(f), ha.get(f)
        if d is None or r is None:
            continue
        dev_ok = d['err'] == 0
        dtxt = 'ok' if dev_ok else 'FAIL(err=%d)' % d['err']
        if 'host_error' in r:
            htxt, host_ok, host_bad = 'error: ' + r['host_error'][:50], False, True
        elif 'crash_rc' in r:
            htxt, host_ok, host_bad = 'crash rc=%d' % r['crash_rc'], False, True
        elif r['skipped']:
            htxt, host_ok, host_bad = 'frame skipped (warning)', False, True
        else:
            htxt, host_ok, host_bad = 'accepted', True, False
        atxt = 'clean'
        if a is None:
            atxt = 'n/a'
        elif 'asan' in a:
            atxt = (a['asan'] or 'rc=%s' % a.get('asan_rc'))[:60]
        if host_ok and dev_ok:
            same = (r['hash'] == d['hash'])
            changed = (b is not None and d['hash'] != b['hash'])
            cat = ('both accept, identical counts' + (' (silent change vs. original)' if changed else ' (no effect)')) if same else 'BOTH ACCEPT, COUNTS DIFFER'
        elif (not host_ok) and (not dev_ok):
            cat = 'both reject'
        elif host_ok and not dev_ok:
            cat = 'device stricter (host accepted)'
        else:
            cat = 'DEVICE ACCEPTS, host rejects'
        cats[cat] += 1
        if manifest[f] != 'unmodified' or cat.startswith(('BOTH ACCEPT', 'DEVICE')):
            print(f'| {u} | {f} | {manifest[f]} | {htxt} | {atxt} | {dtxt} | {cat} |')
    summary[f'ups{u}'] = dict(cats)
json.dump(summary, open(os.path.join(out, 'classification-summary.json'), 'w'), indent=1)
print()
print('```')
print(json.dumps(summary, indent=1))
print('```')

# file-level fixtures: whole-file verdicts, host vs device
print()
print('| fixture | ups | host release | host ASan | device |')
print('|---|---:|---|---|---|')
for fxn in ('trunc_last', 'trunc_file', 'empty_strip'):
    for u in (1, 2):
        hr = jl(f'{out}/host.{fxn}.u{u}.release.jsonl'); ha = jl(f'{out}/host.{fxn}.u{u}.asan.jsonl')
        dpath = f'{out}/dev.{fxn}.u{u}.run1.jsonl'
        dev = jl(dpath)
        idx = [l for l in open(dpath) if 'index_error' in l] if os.path.exists(dpath) else []
        def hs(rows):
            c = collections.Counter()
            for r in rows.values():
                c['error: ' + r['host_error'][:60] if 'host_error' in r else 'crash rc=%s' % r['crash_rc'] if 'crash_rc' in r else 'asan: ' + (r['asan'] or 'rc=%s' % r.get('asan_rc'))[:70] if 'asan' in r else 'skipped' if r.get('skipped') else 'accepted'] += 1
            return '; '.join('%dx %s' % (n, k) for k, n in c.items())
        dtxt = ('REFUSED at index: ' + json.loads(idx[0])['index_error']) if idx else '; '.join('%dx %s' % (n, k) for k, n in collections.Counter('ok' if r['err'] == 0 else 'FAIL(err=%d)' % r['err'] for r in dev.values()).items())
        print(f'| {fxn} | {u} | {hs(hr)} | {hs(ha)} | {dtxt} |')
