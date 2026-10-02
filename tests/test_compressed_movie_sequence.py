#!/usr/bin/env python3
"""Repeated compressed readers must close/reap their decoder before reuse.

Exercises both header-only and full reads through the actual CLI, including a
mixed plain/compressed sequence. The old fclose implementation fails on macOS
after the first compressed movie. Linux runs retain portable pipeline coverage.

Grades core MRC header bytes [0,224), float payload bytes, and STAR existence.
It does not compare label/extended-header or STAR contents, or decoder integrity.
The required suite must fail, not skip, when the xz dependency is unavailable.
"""
import argparse
import lzma
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile

from test_hotpixel_rng_determinism import write_movie, write_star


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--binary',type=Path,required=True)
    a = p.parse_args()
    if not shutil.which('xz'):
        raise RuntimeError('xz is required for compressed-MRC sequence coverage')
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        write_movie(root/'plain.mrc',seed=17,block_origin=None,isolated=[])
        raw=(root/'plain.mrc').read_bytes()
        names=['plain.mrc']
        for i in range(6):
            name=f'compressed{i}.mrc.xz'
            (root/name).write_bytes(lzma.compress(raw))
            names.append(name)
        write_star(root/'movies.star',names)
        result=subprocess.run([str(a.binary.resolve()),'--i','movies.star','--o','out',
            '--use_own','--j','2','--skip_logfile','--patch_x','1','--patch_y','1'],
            cwd=root,capture_output=True,text=True,timeout=90)
        if result.returncode:
            raise AssertionError(result.stdout+'\n'+result.stderr)
        reference=(root/'out/plain.mrc').read_bytes()
        nx,ny,nz,mode=struct.unpack_from('<4i',reference)
        if mode!=2 or len(reference)!=1024+nx*ny*nz*4:
            raise AssertionError('invalid reference image')
        for i in range(6):
            got=(root/f'out/compressed{i}_mrc.mrc').read_bytes()
            if got[:224]!=reference[:224] or got[1024:]!=reference[1024:]:
                raise AssertionError('compressed movie differs from plain input')
            if not (root/f'out/compressed{i}_mrc.star').is_file():
                raise AssertionError('missing per-movie metadata')
        if not (root/'out/corrected_micrographs.star').is_file():
            raise AssertionError('missing aggregate metadata')
    print('PASS: six compressed movies after a plain movie; exact core headers/pixels, STAR files present')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
