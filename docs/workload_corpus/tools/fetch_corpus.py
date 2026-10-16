#!/usr/bin/env python3
"""Fetch EMPIAR files over HTTPS and verify size and SHA-256 against a manifest.

Adapted from the #96 validation corpus fetcher (fetch-selected.py). Differences:
data/evidence roots and the manifest are arguments, and a download that fails
verification is renamed to <name>.failed-<epoch> and kept as evidence instead of
being left as a .partial file. Only verified files end up at their final path.

Manifest: {"files": [{"relative_path": "EMPIAR-NNNNN/...", "bytes": N, "expected_sha256": "..." or null}]}
Usage: fetch_corpus.py MANIFEST DATA_ROOT EVIDENCE_DIR [--workers 4]
"""
import argparse
import concurrent.futures
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()


def fetch(row, data, evidence):
    rel = Path(row['relative_path'])
    if rel.is_absolute() or '..' in rel.parts or not rel.parts[0].startswith('EMPIAR-'):
        raise ValueError('unsafe corpus-relative path: %s' % rel)
    accession = rel.parts[0][len('EMPIAR-'):]
    if not accession.isdigit():
        raise ValueError('invalid accession: %s' % accession)
    target = data / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    if data.resolve() not in target.resolve().parents:
        raise ValueError('target escaped data root')
    tag = hashlib.sha256(str(rel).encode()).hexdigest()[:16]
    part = target.with_name(target.name + '.partial')
    url = ('https://ftp.ebi.ac.uk/empiar/world_availability/' + accession + '/'
           + quote('/'.join(rel.parts[1:]), safe='/'))
    record = {'path': str(rel), 'url': url, 'expected_sha256': row['expected_sha256'],
              'expected_bytes': row['bytes'], 'started_epoch': time.time()}
    if target.exists():
        record.update({'sha256': digest(target), 'bytes': target.stat().st_size, 'reused': True})
    else:
        cmd = ['curl', '--fail', '--location', '--silent', '--show-error',
               '--connect-timeout', '20', '--max-time', '3600', '--retry', '2',
               '--retry-delay', '2', '--speed-limit', '1024', '--speed-time', '60',
               '--dump-header', str(evidence / (tag + '.headers')), '--output', str(part),
               '--write-out', 'bytes=%{size_download} seconds=%{time_total} bytes_per_second=%{speed_download}\n',
               url]
        with (evidence / (tag + '.curl.log')).open('w') as f:
            record['returncode'] = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT).wait()
        if record['returncode'] == 0:
            record.update({'sha256': digest(part), 'bytes': part.stat().st_size})
    # Files new to this corpus have no earlier hash: expected_sha256 is null and the
    # size (from the HTTP Content-Length) is the only check; the observed SHA-256 is
    # recorded as the identity for later runs.
    record['pass'] = (record.get('bytes') == row['bytes']
                      and (row['expected_sha256'] is None
                           or record.get('sha256') == row['expected_sha256']))
    if record['pass'] and not target.exists():
        part.rename(target)
    elif not record['pass'] and part.exists():
        failed = part.with_name(target.name + '.failed-%d' % int(time.time()))
        part.rename(failed)
        record['retained_failed'] = str(failed)
    record['ended_epoch'] = time.time()
    (evidence / (tag + '.json')).write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps({k: record.get(k) for k in ('path', 'pass', 'bytes', 'returncode')}), flush=True)
    return record


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('manifest')
    ap.add_argument('data')
    ap.add_argument('evidence')
    ap.add_argument('--workers', type=int, default=4)
    a = ap.parse_args()
    manifest, data, evidence = Path(a.manifest), Path(a.data), Path(a.evidence)
    data.mkdir(parents=True, exist_ok=True)
    evidence.mkdir(parents=True, exist_ok=True)
    rows = json.loads(manifest.read_text())['files']
    if len({r['relative_path'] for r in rows}) != len(rows):
        raise RuntimeError('duplicate relative_path in manifest')
    out = {'manifest_sha256': digest(manifest), 'fetcher_sha256': digest(Path(__file__)),
           'pid': os.getpid(), 'cpus': sorted(os.sched_getaffinity(0)), 'data_root': str(data),
           'records': []}
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as pool:
        for rec in pool.map(lambda r: fetch(r, data, evidence), rows):
            out['records'].append(rec)
    out['all_pass'] = len(out['records']) == len(rows) and all(r['pass'] for r in out['records'])
    (evidence / ('result-%s.json' % manifest.stem)).write_text(json.dumps(out, indent=2) + '\n')
    return 0 if out['all_pass'] else 2


if __name__ == '__main__':
    sys.exit(main())
