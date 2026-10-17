#!/usr/bin/env python3
"""Summarise the RC0 candidate's retained JSON evidence into markdown tables (stdlib only).

usage: summarize_candidate.py <raw dir>   (prints markdown to stdout)
Reads only files copied from the run workspace; grades nothing itself (every verdict shown is the
committed QF tool's own verdict).
"""
import glob
import json
import os
import re
import sys

raw = sys.argv[1]


def load(p):
    with open(p) as f:
        return json.load(f)


print('### Route/product campaign (items 5 and 6)\n')
print('| case | routes auto/compact/float | auto vs compact (products) | auto vs float (products) | '
      'strict all-files, declared route-log allowance | CPU vs Q1 CPU `1db86902` products / strict | '
      'Tier B relative image RMSE vs CPU (diagnostic only, never graded) | campaign verdict |')
print('|---|---|---|---|---|---|---|---|')
for p in sorted(glob.glob(os.path.join(raw, 'campaign/summaries/*-[GL].json'))):
    d = load(p)
    c = d['checks']
    r = d['routes']
    name = f"{d['family']} {d['config']}"

    def prod(key):
        v = c.get(key)
        if not v:
            return '—'
        return v['products_only']['status']

    def allow(key):
        v = c.get(key)
        if not v:
            return '—'
        s = v['strict_all_files']['status']
        a = v.get('declared_route_log_allowance', {}).get('status', '—')
        return f'{s}/{a}'
    refused = c.get('compact_refusal', {})
    compact = r.get('compact', '—')
    if refused.get('refused'):
        compact = 'refused (expected)' if refused.get('expected') else 'REFUSED (unexpected)'
        pub = refused.get('published_after_refusal')
        if pub:
            compact += f' published={pub}'
    rc = c.get('ref_cpu_vs_cpu', {})
    refs = f"{rc.get('products_only', {}).get('status', '—')} / {rc.get('strict_all_files', {}).get('status', '—')}"
    tb = c.get('cpu_vs_cuda_auto_backend_gate_DIAGNOSTIC_ONLY', {})
    rel = re.search(r'Relative RMSE:\s+(\S+)', tb.get('tail', ''))
    tbs = f"{float(rel.group(1)):.4g}" if rel else 'not parsed'
    print(f"| {name} | {r.get('auto')}/{compact}/{r.get('float')} | {prod('auto_vs_compact')} | {prod('auto_vs_float')} | "
          f"{allow('auto_vs_compact')} ; {allow('auto_vs_float')} | {refs} | {tbs} | {d['verdict']} |")

inp = os.path.join(raw, 'campaign/summaries/inputs.json')
if os.path.exists(inp):
    d = load(inp)
    ok = []
    for fam, ident in (d.items() if isinstance(d, dict) else []):
        if isinstance(ident, dict):
            ok.append(f"{fam}: movie {'match' if ident.get('movie_hash_matches_corpus_md') else ident.get('movie_hash_matches_corpus_md')}"
                      + (f", gain {'match' if ident['gain'].get('matches_corpus_md') else ident['gain'].get('matches_corpus_md')}" if ident.get('gain') else ''))
    print('\nInput hashes vs `docs/workload_corpus/corpus.md`: ' + '; '.join(ok) + '\n')
