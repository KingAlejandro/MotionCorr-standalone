#!/usr/bin/env python3
"""CPU binary controls for the complete dataset aggregation endpoint.

No motion arithmetic changes: the controls distinguish aggregate-only from
ordinary resume/reprocessing and require exact requested report coverage.
"""
from __future__ import annotations
import argparse
import hashlib
import shutil
import subprocess
import tempfile
from pathlib import Path

ARGS = ['--use_own', '--j', '1', '--skip_defect', '--angpix', '1.0',
        '--voltage', '300', '--patch_x', '1', '--patch_y', '1', '--bfactor', '150']
STAR = '''data_optics
loop_
_rlnOpticsGroupName #1
_rlnOpticsGroup #2
_rlnMicrographOriginalPixelSize #3
_rlnVoltage #4
_rlnSphericalAberration #5
_rlnAmplitudeContrast #6
one 1 1.0 300 2.7 0.1

data_movies
loop_
_rlnMicrographMovieName #1
_rlnOpticsGroup #2
Movies/b.tiff 1
Movies/a.tiff 1
'''


def require(ok: bool, message: str) -> None:
    if not ok:
        raise AssertionError(message)


def products(out: Path) -> dict:
    return {str(p.relative_to(out)): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
            for p in (out / 'Movies').glob('*') if p.is_file()}


def run(binary: Path, tmp: Path, out: Path, extra: list[str] = [], env=None):
    return subprocess.run([str(binary), '--i', 'in.star', '--o', str(out)+'/', *ARGS, *extra],
                          cwd=tmp, text=True, capture_output=True, env=env)


def main() -> int:
    import os
    ap = argparse.ArgumentParser()
    ap.add_argument('--binary', type=Path, required=True)
    ap.add_argument('--aggregate-arg',default='--aggregate_only',choices=['--aggregate_only','--only_do_unfinished'])
    ap.add_argument('--fake-gs',action='store_true',help='explicit CPU control only; does not validate real PDF rendering')
    a = ap.parse_args()
    binary = a.binary.resolve()
    fixture = Path(__file__).resolve().parents[1] / 'test-data/synthetic/synthetic_movie.tiff'
    with tempfile.TemporaryDirectory(prefix='aggregate-controls-') as td:
        tmp = Path(td); (tmp/'Movies').mkdir()
        if a.fake_gs:
            fake=tmp/'healthy-fake-gs';fake.mkdir();gs=fake/'gs'
            gs.write_text('#!'+str(Path(__import__('sys').executable).resolve())+'\n'
                          'import pathlib,sys\n'
                          'for arg in sys.argv[1:]:\n'
                          ' if arg.lower().startswith("-soutputfile="):\n'
                          '  pathlib.Path(arg.split("=",1)[1]).write_bytes(b"%PDF-1.4 control\\n%%EOF\\n")\n')
            gs.chmod(0o755);os.environ['PATH']=str(fake)+os.pathsep+os.environ.get('PATH','')
            print('CONTROL ONLY: fake Ghostscript; real PDF rendering remains UNRUN')
        else:
            require(shutil.which('gs') is not None, 'real Ghostscript required; use explicit --fake-gs only for limited CPU controls')
        for name in ['a', 'b']:
            shutil.copyfile(fixture, tmp/'Movies'/f'{name}.tiff')
        (tmp/'in.star').write_text(STAR)
        baseline = tmp/'baseline'
        control = run(binary,tmp,baseline)
        require(control.returncode == 0, 'healthy CPU control failed: '+control.stderr[-2000:])
        before = products(baseline)
        # A stale unrelated plot must not be admitted by a directory wildcard.
        (baseline/'Movies/unassigned.eps').write_text('%!PS\nshowpage\n')
        for repeat in range(2):
            r = run(binary,tmp,baseline,[a.aggregate_arg])
            require(r.returncode == 0, 'aggregate failed: '+r.stderr[-2000:])
            after = products(baseline); after.pop('Movies/unassigned.eps')
            require(after == before, 'aggregate-only rewrote per-movie contents or mtimes')
            lines = (baseline/'batch.pdf.lst').read_text().splitlines()
            require(lines == [str(baseline/'Movies/b_shifts.eps'),str(baseline/'Movies/a_shifts.eps')],
                    'full original movie order/report coverage changed or stale EPS admitted')
            pdf = (baseline/'logfile.pdf').read_bytes()
            require(pdf.startswith(b'%PDF-') and b'%%EOF' in pdf[-1024:], 'invalid complete PDF')
        print('PASS aggregate full ordered report, excludes unrelated plot, repeat does not rewrite movies')
        # Each refusal starts with no published dataset marker/report so stale
        # valid artifacts cannot disguise a failed new aggregation.
        cases = [('missing-image','Movies/a.mrc'),('missing-plot','Movies/a_shifts.eps')]
        for name, missing in cases:
            out=tmp/name; shutil.copytree(baseline,out)
            (out/missing).unlink()
            for f in ['corrected_micrographs.star','logfile.pdf']: (out/f).unlink()
            before_case=products(out)
            r=run(binary,tmp,out,[a.aggregate_arg])
            require(r.returncode > 0, name+' must fail normally, not compute or signal-abort')
            require('a.tiff' in r.stderr or 'a_shifts.eps' in r.stderr, name+' must name missing movie/report')
            require(not (out/'corrected_micrographs.star').exists(), name+' published dataset STAR')
            require(products(out)==before_case,name+' reprocessed or rewrote a movie')
            print('PASS '+name+' refuses without reprocessing/publication')
        out=tmp/'expected-frames'; shutil.copytree(baseline,out)
        (out/'corrected_micrographs.star').unlink()
        r=run(binary,tmp,out,[a.aggregate_arg,'--expected_frames','999'])
        require(r.returncode > 0 and not (out/'corrected_micrographs.star').exists(),
                'expected frame count must be enforced before aggregation')
        print('PASS expected frame count refusal')
        out=tmp/'report-fault'; shutil.copytree(baseline,out)
        for f in ['corrected_micrographs.star','logfile.pdf']: (out/f).unlink()
        before_case=products(out)
        fake=tmp/'fake-bin';fake.mkdir();gs=fake/'gs';gs.write_text('#!/bin/sh\nexit 7\n');gs.chmod(0o755)
        env=dict(os.environ,PATH=str(fake)+os.pathsep+os.environ.get('PATH',''))
        r=run(binary,tmp,out,[a.aggregate_arg],env)
        require(r.returncode > 0,'Ghostscript failure must fail normally')
        require(not (out/'corrected_micrographs.star').exists() and not (out/'logfile.pdf').exists(),
                'failed report published dataset products')
        require(products(out)==before_case,'failed report rewrote movies')
        require(not list(out.glob('.aggregate-*')),'private report staging leaked after failure')
        print('PASS report failure withholds joint publication, preserves movies, cleans staging')
    return 0

if __name__=='__main__':
    raise SystemExit(main())
