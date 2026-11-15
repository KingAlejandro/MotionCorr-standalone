#!/usr/bin/env python3
"""#214: complete reads require EOF and decoder success; subsets stop early.

Native damaged streams and a full-output/exit-3 shim are separate controls.
The shim emits an extra MiB after the movie, requiring a drain before pclose.
Missing native tools skip visibly (77), never count as tested codecs.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from test_truncated_mrc_movie import make_frames, mrc_header, encode_frame, STAR_HEAD

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools/profiling'))
from lib import identity


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--binary', type=Path, required=True)
    p.add_argument('--baseline-binary', type=Path)
    p.add_argument('--codec', choices=('bz2', 'xz', 'zst'), required=True)
    p.add_argument('--gpu')
    p.add_argument('--work', type=Path)
    a = p.parse_args()
    tool = {'bz2': 'pbzip2', 'xz': 'xz', 'zst': 'zstd'}[a.codec]
    decoder = shutil.which(tool)
    if not decoder:
        print(f'SKIP: {a.codec}: {tool} absent; no native or shim cases run')
        return 77
    binary = a.binary.resolve()
    baseline = a.baseline_binary.resolve() if a.baseline_binary else None
    tmp = tempfile.TemporaryDirectory() if a.work is None else None
    work = a.work.resolve() if a.work else Path(tmp.name)
    work.mkdir(parents=True, exist_ok=True)
    raw = mrc_header(1) + b''.join(encode_frame(f, 1) for f in make_frames())
    comp = subprocess.run([decoder, '-c', *(['--check'] if a.codec == 'zst' else [])],
                          input=raw, capture_output=True, check=True).stdout
    movie = 'movie.mrc.' + a.codec
    records, failures = [], []

    def require(ok, message):
        if not ok:
            failures.append(message)

    def run(label, blob, *, exe=binary, extra=(), shim=None, batch=False):
        root = work / label
        root.mkdir()
        (root / movie).write_bytes(blob)
        names = [movie]
        if batch:
            (root / 'healthy.mrc').write_bytes(raw)
            names += ['healthy.mrc']
        (root / 'movies.star').write_text(STAR_HEAD + ''.join(f'{n} 1\n' for n in names))
        out = root / 'out'
        cmd = [str(exe), '--i', 'movies.star', '--o', str(out) + '/', '--use_own',
               '--j', '2', '--skip_logfile', '--patch_x', '1', '--patch_y', '1',
               '--seed', '1', *extra]
        if a.gpu is not None:
            cmd += ['--gpu', a.gpu, '--ingest', 'float']
        env = os.environ.copy()
        if shim is not None:
            shimdir = root / 'bin'
            shimdir.mkdir()
            script = shimdir / tool
            # Python writes more than pipe capacity; an early pclose would break it.
            script.write_text(f'#!{sys.executable}\nimport sys\n'
                              f'sys.stdout.buffer.write({raw!r})\n'
                              'sys.stdout.buffer.write(b"x" * (1 << 20))\n'
                              f'sys.stdout.buffer.flush()\nsys.exit({shim})\n')
            script.chmod(0o755)
            env['PATH'] = str(shimdir) + os.pathsep + env['PATH']
        result = subprocess.run(cmd, cwd=root, env=env, capture_output=True, text=True, timeout=90)
        text = result.stdout + result.stderr
        (root / 'run.log').write_text(text)
        files = sorted(str(f.relative_to(out)) for f in out.rglob('*') if f.is_file())
        rec = dict(case=label, command=cmd, rc=result.returncode, files=files)
        records.append(rec)
        return result.returncode, text, out, rec

    # Full, first-frame-only selection, last-frame-only selection and middle subset.
    # Any explicit selection of all frames must still enforce stream integrity.
    for label, extra in [('full', ()), ('first', ('--first_frame_sum', '3')),
                         ('last', ('--last_frame_sum', '6')),
                         ('middle', ('--first_frame_sum', '2', '--last_frame_sum', '6'))]:
        rc, text, out, rec = run(label, comp, extra=extra)
        require(rc == 0 and (out / 'movie_mrc.star').is_file()
                and (out / 'corrected_micrographs.star').is_file(), f'{label}: healthy read failed: {text}')
        if baseline:
            rb, _, old, _ = run(label + '-baseline', comp, exe=baseline, extra=extra)
            cmp = identity.compare_trees(str(old), str(out))
            rec['identity'] = cmp
            require(rb == 0 and cmp['identical'], f'{label}: baseline products differ: {cmp}')

    damaged = {'missing-last-byte': comp[:-1]}
    corrupt = bytearray(comp)
    # xz: last byte of index CRC, before the 12-byte footer. Other codecs:
    # checksum/trailer corruption (bz2 end-of-stream CRC; zstd content checksum).
    corrupt[-13 if a.codec == 'xz' else -2] ^= 0xff
    damaged['index-crc' if a.codec == 'xz' else 'trailer-checksum'] = bytes(corrupt)
    damaged['midstream'] = comp[:len(comp) // 2]
    for label, blob in damaged.items():
        dec = subprocess.run([decoder, '-cd'], input=blob, capture_output=True)
        require(dec.returncode != 0, f'{label}: damage did not fail native decoder')
        rc, text, out, rec = run(label, blob, batch=True)
        rec['decoder_rc'], rec['decoder_bytes'] = dec.returncode, len(dec.stdout)
        require(rc == 1 and movie in text and not (out / 'movie_mrc.star').exists()
                and not (out / 'movie_mrc.mrc').exists()
                and not (out / 'corrected_micrographs.star').exists()
                and (out / 'healthy.star').is_file(), f'{label}: failed Class A rejection')

    for status in (0, 3):
        rc, text, out, _ = run(f'shim-exit-{status}', comp, shim=status, batch=status != 0)
        if status == 0:
            require(rc == 0 and (out / 'movie_mrc.star').is_file(), 'exit-0 drain control failed')
        else:
            require(rc == 1 and movie in text and 'decompression failed' in text
                    and not (out / 'movie_mrc.star').exists()
                    and not (out / 'movie_mrc.mrc').exists()
                    and not (out / 'corrected_micrographs.star').exists()
                    and (out / 'healthy.star').is_file(), 'exit-3: failed Class A rejection')
    # Deliberate policy: even a decoder failure is ignored for a partial read.
    for label, extra in [('subset-exit-3', ('--last_frame_sum', '6')),
                         ('first-exit-3', ('--first_frame_sum', '3')),
                         ('all-explicit-exit-3', ('--first_frame_sum', '1', '--last_frame_sum', '8'))]:
        rc, _, out, _ = run(label, comp, extra=extra, shim=3)
        require((rc == 1 and not (out / 'movie_mrc.star').exists()) if label.startswith('all-')
                else (rc == 0 and (out / 'movie_mrc.star').is_file()), f'{label}: selection status policy failed')
    (work / 'results.json').write_text(json.dumps(dict(codec=a.codec, records=records, failures=failures), indent=2))
    for record in records:
        print(json.dumps(record))
    for failure in failures:
        print('FAIL:', failure)
    print(f'{a.codec}: {len(records)} runs; {len(failures)} failures')
    return bool(failures)


if __name__ == '__main__':
    sys.exit(main())
