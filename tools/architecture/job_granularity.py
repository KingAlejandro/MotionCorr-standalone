#!/usr/bin/env python3
"""Compare fresh process per movie with bounded multi-movie jobs, no concurrency.

Six copies of one tiny fixture measure overhead and process-boundary correctness,
not diverse science or detector-sized throughput. Products are verified after
timing. The aggregate STAR is inventoried but not merged across separate jobs.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from compare_motioncorr import parse_mrc, normalized_mrc_labels


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def products(root, names, gpu):
    records = {}
    for name in names:
        mrcs = sorted(root.rglob(name + '*.mrc'))
        stars = list(root.rglob(name + '.star'))
        logs = list(root.rglob(name + '.log'))
        if len(mrcs) != 2 or len(stars) != 1 or len(logs) != 1:
            raise RuntimeError(f'incomplete or ambiguous products for {name}')
        for p in mrcs:
            _, pixels, header = parse_mrc(p)
            records[p.name] = hashlib.sha256(
                header[:224] + normalized_mrc_labels(header) + pixels.tobytes()).hexdigest()
        # Preserve every per-movie metadata field, normalizing only output path.
        text = stars[0].read_text().replace(str(root) + '/', 'OUTPUT/')
        records[stars[0].name] = hashlib.sha256(text.encode()).hexdigest()
        log = logs[0].read_text()
        if gpu and ('Fourier transforms (CUDA in-VRAM)' not in log
                    or re.search(r'failed|falling back|CUDA Error', log, re.I)):
            raise RuntimeError('native resident CUDA witness missing or failure present')
    aggregates = list(root.rglob('corrected_micrographs.star'))
    if len(aggregates) != 1 or not aggregates[0].stat().st_size:
        raise RuntimeError('aggregate metadata missing')
    return records


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--binary', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--gpu', action='store_true')
    p.add_argument('--rounds', type=int, default=5)
    a = p.parse_args()
    if a.rounds < 1:
        p.error('--rounds must be positive')
    a.binary = a.binary.resolve()
    root = a.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    movies = root / 'movies'
    movies.mkdir()
    fixture = Path(__file__).resolve().parents[2] / 'test-data/synthetic/synthetic_movie.tiff'
    for n in range(6):
        shutil.copyfile(fixture, movies / f'm{n}.tiff')
    provenance = dict(binary_sha256=digest(a.binary), fixture_sha256=digest(fixture),
                      gpu=a.gpu, threads=4, concurrency=1, movie_count=6)
    (root/'provenance.json').write_text(json.dumps(provenance, indent=2)+'\n')
    reference = None
    with (root/'observations.jsonl').open('w') as rows:
        # A complete warmup round is retained but excluded from the summary.
        for round_no in range(-1, a.rounds):
            order = [1, 2, 6]
            if round_no >= 0:
                k = round_no % 3
                order = order[k:] + order[:k]
                if round_no % 2:
                    order.reverse()
            for group in order:
                elapsed = 0
                inventory = {}
                commands = []
                for begin in range(0, 6, group):
                    names = [f'm{n}' for n in range(begin, begin+group)]
                    out = root/f'round{round_no}-group{group}-start{begin}'
                    pattern = 'movies/m['+''.join(str(n) for n in range(begin, begin+group))+'].tiff'
                    cmd = [str(a.binary), '--i', pattern, '--o', str(out), '--use_own',
                           '--j', '4', '--max_io_threads', '4', '--seed', '1', '--skip_logfile',
                           '--angpix', '1', '--voltage', '300', '--dose_weighting', '--save_noDW',
                           '--dose_per_frame', '1', '--patch_x', '3', '--patch_y', '3', '--bfactor', '150']
                    if a.gpu:
                        cmd += ['--gpu', '0']
                    with Path(str(out)+'.log').open('w') as log:
                        start = time.perf_counter()
                        subprocess.run(cmd, cwd=root, stdout=log, stderr=subprocess.STDOUT, check=True)
                        elapsed += time.perf_counter()-start
                    inventory.update(products(out, names, a.gpu))
                    commands.append(cmd)
                if reference is None:
                    reference = inventory
                if inventory != reference:
                    raise RuntimeError(f'product differs: round {round_no}, group {group}')
                row = dict(round=round_no, movies_per_process=group, seconds=elapsed,
                           exact_products=len(inventory), products=inventory, commands=commands)
                rows.write(json.dumps(row)+'\n')
                rows.flush()
                print(json.dumps({k:v for k,v in row.items() if k not in ('products','commands')}), flush=True)


if __name__ == '__main__':
    main()
