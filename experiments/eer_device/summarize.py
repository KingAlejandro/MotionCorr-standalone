#!/usr/bin/env python3
"""Markdown tables from the matrix results. usage: summarize.py <results-dir>"""
import glob, json, os, sys
R = sys.argv[1]
GiB = 1 << 30
def load(p):
    try:
        return json.load(open(p))
    except Exception:
        return None
def f(v, n=3):
    return ('%.*f' % (n, v))
def rng(s, n=3):
    return '%s (%s–%s)' % (f(s['median'], n), f(s['min'], n), f(s['max'], n))

print('### Exactness (every pixel of every group vs `EERRenderer::renderFrames`)\n')
print('| case | enc | grouping (groups, remainder) | ups | frame | device out | pixels compared | mismatched | electrons host = device | verdict |')
print('|---|---|---|---:|---:|---|---:|---:|---|---|')
for p in sorted(glob.glob(R + '/*.verify.json')):
    d = load(p)
    if not d or 'verify' not in d:
        continue
    v = d['verify']
    print('| %s | %s | %d (%d, %d) | %d | %d² | %s | %d | %d | %s | **%s** |' % (d['label'], d['compression'], d['grouping'], d['groups'], d['remainder_fractions'], d['upsampling'], d['frame_dim'],
          d['output'], v['pixels_compared'], v['mismatched_pixels'], 'yes' if v['host_electrons'] == v['device_electrons'] and v['groups_with_electron_count_mismatch'] == 0 else 'NO', v['verdict']))

print('\n### Admission\n')
print('| case | verdict | need GiB | free GiB | reserve GiB | reason |')
print('|---|---|---:|---:|---:|---|')
for p in sorted(glob.glob(R + '/*.verify.json')):
    d = load(p)
    if not d or 'admission' not in d:
        continue
    a = d['admission']
    if 'admit' in d['label'] or d['label'].startswith('f4-g40-u2'):
        print('| %s | %s | %.1f | %.1f | %.1f | %s |' % (d['label'], a['verdict'], a['need_bytes'] / GiB, a['free_vram_bytes'] / GiB, a['reserve_bytes'] / GiB, a['reason']))

print('\n### Working set against the d_Fframes-sized arena (float output, borrowed arena)\n')
print('| case | compressed GiB | tables MiB | output (float) GiB | d_Fframes equiv. GiB | arena use | decode chunks | VRAM used after decode GiB | extra over output + arena MiB |')
print('|---|---:|---:|---:|---:|---:|---:|---:|---:|')
for p in sorted(glob.glob(R + '/*-float.verify.json')):
    d = load(p)
    if not d or 'working_set' not in d:
        continue
    w, m = d['working_set'], d['memory']
    extra = m['cudaMemGetInfo_used_after_decode_bytes'] - w['output_bytes'] - w['d_Fframes_equivalent_bytes']
    print('| %s | %.2f | %.2f | %.2f | %.2f | %.0f%% | %d | %.2f | %.0f |' % (d['label'], w['compressed_strips_h2d_bytes'] / GiB, w['tables_bytes'] / (1 << 20), w['output_bytes'] / GiB,
          w['d_Fframes_equivalent_bytes'] / GiB, 100.0 * (w['compressed_strips_h2d_bytes'] + w['tables_bytes']) / w['d_Fframes_equivalent_bytes'], w['decode_chunks'],
          m['cudaMemGetInfo_used_after_decode_bytes'] / GiB, extra / (1 << 20)))

print('\n### Timing: balanced AB/BA pairs, host = `EERRenderer` render into uint16 (8 OMP threads), device = file bytes to float frames ready\n')
print('| case | pairs | host render s | device e2e s | saving s, median (min–max) | device/host | bar (≥1.0 s or ≥25 %) | CPU s host / device | max foreign cores | other GPUs busy samples |')
print('|---|---:|---|---|---|---:|---|---|---:|---|')
for p in sorted(glob.glob(R + '/*.timing.json')):
    d = load(p)
    if not d or 'pairs' not in d:
        continue
    q = d['pairs']
    fc = max(max(q['device']['foreign_cores']['values']), max(q.get('host', {}).get('foreign_cores', {}).get('values', [0])))
    gs = ''
    gp = p.replace('.timing.json', '')
    for a in (1, 2, 3):
        c = gp + '.gpu-samples%d.csv' % a
        if os.path.exists(c):
            rows = [r.split(',') for r in open(c).read().strip().splitlines()]
            rows = [r for r in rows if len(r) >= 4 and r[1].strip() in ('1', '2', '3')]
            busy = sum(int(r[2].strip().split()[0]) > 0 for r in rows)
            gs = '%d/%d' % (busy, len(rows))
    if 'host' in q:
        sav, rat = q['saving_s_host_minus_device'], q['device_over_host']
        h = q['host']['render_total_s']
        ok = sav['min'] > 0 and (sav['median'] >= 1.0 or sav['median'] >= 0.25 * h['median'])
        print('| %s | %d | %s | %s | %s | %.3f | %s | %.1f / %.2f | %.3f | %s |' % (d['label'], q['n'], rng(h, 2), rng(q['device']['end_to_end_s']), rng(sav, 2), rat['median'], 'PASS' if ok else 'not met',
              q['host']['process_cpu_s']['median'], q['device']['process_cpu_s']['median'], fc, gs))
    else:
        print('| %s | %d | not run | %s | – | – | – | – / %.2f | %.3f | %s |' % (d['label'], q['n'], rng(q['device']['end_to_end_s']), q['device']['process_cpu_s']['median'], fc, gs))

print('\n### Device phases, median (min–max) s\n')
print('| case | index (LibTIFF walk) | read + H2D (ring) | decode kernel | end to end |')
print('|---|---|---|---|---|')
for p in sorted(glob.glob(R + '/*.timing.json')):
    d = load(p)
    if not d or 'pairs' not in d:
        continue
    q = d['pairs']['device']
    print('| %s | %s | %s | %s | %s |' % (d['label'], rng(q['index_s'], 3), rng(q['read_and_h2d_s'], 3), rng(q['decode_s'], 3), rng(q['end_to_end_s'], 3)))
