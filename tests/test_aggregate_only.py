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
import struct
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


def literal_controls(binary, tmp):
    original=(tmp/'in.star').read_text()
    (tmp/'in.star').write_text(original.replace('Movies/b.tiff','Movies/b[1].tiff'))
    shutil.copyfile(tmp/'Movies/b.tiff',tmp/'Movies/b[1].tiff')
    out=tmp/'literal-baseline';r=run(binary,tmp,out)
    require(r.returncode==0,'literal movie processing fixture failed: '+r.stderr)
    literal=out/'Movies/b[1]_shifts.eps';stale=out/'Movies/b1_shifts.eps'
    expected=[str(literal),str(out/'Movies/a_shifts.eps')]
    failures=[]
    for mode in ['literal-only','stale-match','missing-literal']:
        if mode=='stale-match':shutil.copyfile(literal,stale)
        if mode=='missing-literal':literal.unlink()
        for name in ['corrected_micrographs.star','logfile.pdf']:
            (out/name).unlink(missing_ok=True)
        before=products(out);r=run(binary,tmp,out,['--aggregate_only'])
        if mode=='missing-literal':
            ok=r.returncode>0 and not (out/'corrected_micrographs.star').exists() and 'b[1]' in r.stderr
        else:
            ok=r.returncode==0 and (out/'batch.pdf.lst').read_text().splitlines()==expected
        ok=ok and products(out)==before
        print(('PASS ' if ok else 'FAIL ')+'strict '+mode+' selects/refuses exact original literal movie path')
        if not ok:failures.append(mode+': '+r.stderr[-800:])
    (tmp/'in.star').write_text(original)
    require(not failures,'literal report selection controls: '+str(failures))


def effective_optics_controls(binary,tmp):
    original=(tmp/'in.star').read_text()
    variants=[
        ('optics-overrides-cli',original.replace('one 1 1.0','one 1 2.0')),
        ('multiple-optics',original.replace('one 1 1.0 300 2.7 0.1',
            'one 1 1.0 300 2.7 0.1\ntwo 2 2.0 300 2.7 0.1').replace('Movies/a.tiff 1','Movies/a.tiff 2'))]
    failures=[]
    for name,star in variants:
        (tmp/'in.star').write_text(star);out=tmp/name
        r=run(binary,tmp,out)
        require(r.returncode==0,name+' processing fixture failed: '+r.stderr)
        for movie,expected in [('a',2.0),('b',2.0 if name=='optics-overrides-cli' else 1.0)]:
            data=(out/'Movies'/f'{movie}.mrc').read_bytes()
            sampling=struct.unpack_from('<f',data,40)[0]/struct.unpack_from('<i',data,28)[0]
            require(sampling==expected,name+' did not establish actual effective '+movie+' sampling')
        # The worker invocation retains --angpix1 in ARGS; input optics supply
        # effective2 for the contradictory case and1/2 for the two groups.
        before=products(out);r=run(binary,tmp,out,['--aggregate_only'])
        ok=r.returncode==0 and products(out)==before
        if ok:
            text=(out/'corrected_micrographs.star').read_text()
            ok='2.000000' in text and (name!='multiple-optics' or '1.000000' in text)
        print(('PASS ' if ok else 'FAIL ')+name+' accepts same effective per-movie optics without rewriting')
        if not ok:failures.append(name+': '+r.stderr[-800:])
    (tmp/'in.star').write_text(original)
    require(not failures,'effective optics controls: '+str(failures))


def geometry_controls(binary,tmp,baseline):
    failures=[]
    for name,extra,mutation in [
        ('binning-mismatch',['--bin_factor','2'],None),
        ('declared-optics-sampling',[], 'optics'),
        ('accepted-mrc-sampling',[], 'sampling'),
        ('accepted-mrc-geometry',[], 'geometry')]:
        out=tmp/name;shutil.copytree(baseline,out)
        original=(tmp/'in.star').read_text()
        if mutation=='optics':(tmp/'in.star').write_text(original.replace('one 1 1.0','one 1 2.0'))
        if mutation in ('sampling','geometry'):
            file=out/'Movies/a.mrc';data=bytearray(file.read_bytes())
            if mutation=='sampling':struct.pack_into('<f',data,40,2*struct.unpack_from('<f',data,40)[0])
            else:struct.pack_into('<i',data,0,struct.unpack_from('<i',data,0)[0]//2)
            file.write_bytes(data)
        for f in ['corrected_micrographs.star','logfile.pdf']:(out/f).unlink(missing_ok=True)
        before=products(out);r=run(binary,tmp,out,['--aggregate_only',*extra])
        ok=r.returncode>0 and not (out/'corrected_micrographs.star').exists() and not (out/'logfile.pdf').exists() and products(out)==before
        ok=ok and ('a.tiff' in r.stderr or 'b.tiff' in r.stderr) and ('sampling' in r.stderr or 'geometry' in r.stderr or 'binning' in r.stderr)
        print(('PASS ' if ok else 'FAIL ')+name+' refuses named movie without rewriting/publication')
        if not ok:failures.append(name+': '+r.stderr[-800:])
        (tmp/'in.star').write_text(original)
    # A genuine bin2 result is accepted; no special-case blanket bin2 refusal.
    out=tmp/'healthy-bin2';r=run(binary,tmp,out,['--bin_factor','2'])
    require(r.returncode==0,'healthy bin2 processing control failed: '+r.stderr)
    before=products(out);r=run(binary,tmp,out,['--aggregate_only','--bin_factor','2'])
    require(r.returncode==0 and products(out)==before,'matching bin2 aggregate refused or rewrote products: '+r.stderr)
    print('PASS matching bin2 geometry/sampling accepts without rewriting')
    require(not failures,'geometry/sampling controls: '+str(failures))


def tomography_controls(binary,tmp,publication_only=None):
    import sys
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/multi_gpu'))
    import star_io
    original=(tmp/'in.star').read_text()
    for name in ['c','d']:shutil.copyfile(tmp/'Movies/a.tiff',tmp/'Movies'/f'{name}.tiff')
    (tmp/'tilt_series').mkdir(exist_ok=True)
    (tmp/'in.star').write_text('data_global\nloop_\n_rlnTomoName #1\n'
        '_rlnTomoTiltSeriesStarFile #2\n_rlnMicrographOriginalPixelSize #3\n'
        '_rlnVoltage #4\n_rlnSphericalAberration #5\n_rlnAmplitudeContrast #6\n'
        'one tilt_series/one.star 1.0 300 2.7 0.1\n'
        'two tilt_series/two.star 1.0 300 2.7 0.1\n')
    for name,rows in [('one',[('b',0),('a',5)]),('two',[('d',11),('c',17)])]:
        (tmp/'tilt_series'/f'{name}.star').write_text('data_'+name+'\nloop_\n'
            '_rlnMicrographMovieName #1\n_rlnMicrographPreExposure #2\n'+
            ''.join('Movies/'+movie+'.tiff '+str(dose)+'\n' for movie,dose in rows))
    try:
        out=tmp/'tomo-baseline';r=run(binary,tmp,out)
        require(r.returncode==0,'tomographic processing fixture failed: '+r.stderr[-2000:])
        before=products(out)
        (out/'corrected_tilt_series.star').unlink()
        shutil.rmtree(out/'tilt_series') # Fresh worker-product assembly has no aggregate sidecars.
        for repeat in range(2):
            r=run(binary,tmp,out,['--aggregate_only'])
            require(r.returncode==0,'tomographic aggregate failed: '+r.stderr[-2000:])
            joint=star_io.parse(out/'corrected_tilt_series.star')
            global_block=joint.block_with_label('rlnTomoTiltSeriesStarFile')
            reference_col=global_block.column('rlnTomoTiltSeriesStarFile')
            name_col=global_block.column('rlnTomoName')
            require(len(global_block.rows)==2,'tomographic joint coverage incomplete')
            got=[]
            for row in global_block.rows:
                path=Path(row.values[reference_col]);name=row.values[name_col]
                require('.aggregate-' not in str(path) and path.is_file(),
                        'tomographic aggregate falsely succeeded with dangling staged reference: '+str(path))
                require(path.resolve()==(out/'tilt_series'/f'{name}.star').resolve(),
                        'tomographic final reference points outside declared per-series output')
                table=star_io.parse(path);block=table.block_with_label('rlnMicrographName')
                movie_col=block.column('rlnMicrographName');metadata_col=block.column('rlnMicrographMetadata')
                exposure_col=block.column('rlnMicrographPreExposure')
                expected={'one':[('b',0),('a',5)],'two':[('d',11),('c',17)]}[name]
                values=[]
                for tilt in block.rows:
                    image=Path(tilt.values[movie_col]);metadata=Path(tilt.values[metadata_col])
                    require(image.is_file() and metadata.is_file(),'nested tomographic movie/metadata reference unreadable')
                    require(image.resolve()==(out/'Movies'/image.name).resolve() and
                            metadata.resolve()==(out/'Movies'/metadata.name).resolve(),
                            'nested tomographic movie/model association points outside worker products')
                    values.append((image.stem,float(tilt.values[exposure_col])))
                require(values==expected,'nested tomographic row order/exposure association changed')
                got.append(name)
            require(got==['one','two'],'tomogram joint order changed')
            require(products(out)==before,'tomographic aggregate rewrote complete movie pixels/headers/STAR/EPS/mtimes')
            require(not list(out.glob('.aggregate-*')),'tomographic private staging leaked')
            print('PASS tomography final nested references/readable row associations, unchanged movie bytes/mtimes repeat'+str(repeat))
        tomo_input=(tmp/'in.star').read_text()
        for mode in ['partial-movie','reference-publication-failure','joint-reference-collision','movie-reference-collision','report-reference-collision',
                     'mc2-out-collision','mc2-err-collision','mc2-com-collision']:
            target=tmp/('tomo-'+mode);shutil.copytree(out,target)
            (target/'corrected_tilt_series.star').unlink();(target/'logfile.pdf').unlink()
            if mode=='partial-movie':(target/'Movies/c.star').unlink()
            elif mode=='reference-publication-failure':
                path=target/'tilt_series/one.star';path.unlink();path.mkdir();(path/'owned-sentinel').write_text('do not overwrite')
            elif mode=='movie-reference-collision':
                shutil.copyfile(tmp/'tilt_series/one.star',tmp/'Movies/a.star')
                (tmp/'in.star').write_text(tomo_input.replace('tilt_series/one.star','Movies/a.star'))
            elif mode.startswith('mc2-'):
                # A --use_motioncor2 run leaves Movies/a.{out,err,com} beside the products.
                diagnostic='Movies/a.'+mode.split('-')[1];(target/diagnostic).write_text('motioncor2 diagnostic')
                shutil.copyfile(tmp/'tilt_series/one.star',tmp/diagnostic)
                (tmp/'in.star').write_text(tomo_input.replace('tilt_series/one.star',diagnostic))
            elif mode=='report-reference-collision':
                shutil.copyfile(tmp/'tilt_series/one.star',tmp/'logfile.pdf')
                (tmp/'in.star').write_text(tomo_input.replace('tilt_series/one.star','logfile.pdf'))
            else:
                shutil.copyfile(tmp/'tilt_series/one.star',tmp/'corrected_tilt_series.star')
                (tmp/'in.star').write_text(tomo_input.replace('tilt_series/one.star','corrected_tilt_series.star'))
            retained=products(target);r=run(binary,tmp,target,['--aggregate_only'])
            require(r.returncode>0,'tomographic '+mode+' must fail normally')
            require(not (target/'corrected_tilt_series.star').exists() and not (target/'logfile.pdf').exists(),
                    'tomographic '+mode+' published a success marker/report')
            require(('c.tiff' if mode=='partial-movie' else 'corrected_tilt_series.star' if mode=='joint-reference-collision' else 'a.star' if mode=='movie-reference-collision' else 'logfile.pdf' if mode=='report-reference-collision' else 'a.'+mode.split('-')[1] if mode.startswith('mc2-') else 'one.star') in r.stderr,
                    'tomographic '+mode+' failure did not name its input/reference')
            if mode.startswith('mc2-'):
                require((target/diagnostic).read_text()=='motioncor2 diagnostic','tomographic '+mode+' replaced the MotionCor2 diagnostic')
                (tmp/diagnostic).unlink()
            require(products(target)==retained and not list(target.glob('.aggregate-*')),
                    'tomographic failure rewrote movie products or leaked staging')
            print('PASS tomography '+mode+' withholds joint success without movie rewriting')
            (tmp/'in.star').write_text(tomo_input)
        if publication_only not in ('lists','header','logfile'):
            # A failed rerun must leave an already valid global/series dataset intact.
            # Force a late report-list publication error after series replacements.
            target=tmp/'tomo-existing-rollback';r=run(binary,tmp,target)
            require(r.returncode==0,'existing tomography dataset fixture failed: '+r.stderr[-2000:])
            existing=star_io.parse(target/'corrected_tilt_series.star')
            for row in existing.block_with_label('rlnTomoTiltSeriesStarFile').rows:
                require(Path(row.values[1]).is_file(),'old dataset sidecar is not readable')
            series=tmp/'tilt_series/one.star';old_series=series.read_text()
            second=tmp/'tilt_series/two.star';old_second=second.read_text()
            # Known input-only tilt metadata survives conversion and changes the new sidecar.
            lines=old_series.splitlines();lines.insert(lines.index('_rlnMicrographPreExposure #2')+1,
                                                    '_rlnTomoNominalStageTiltAngle #3')
            changed='\n'.join(line+' 37' if line.startswith('Movies/') else line for line in lines)+'\n'
            series.write_text(changed)
            lines=old_second.splitlines();lines.insert(lines.index('_rlnMicrographPreExposure #2')+1,
                                                    '_rlnTomoNominalStageTiltAngle #3')
            second.write_text('\n'.join(line+' 37' if line.startswith('Movies/') else line for line in lines)+'\n')
            try:
                healthy=tmp/'tomo-changed-positive';r=run(binary,tmp,healthy)
                require(r.returncode==0,'changed tomography metadata fixture failed: '+r.stderr[-2000:])
                r=run(binary,tmp,healthy,['--aggregate_only'])
                require(r.returncode==0 and b'37.000000' in (healthy/'tilt_series/one.star').read_bytes(),
                        'changed metadata positive is not powered: '+r.stderr[-2000:])
                blocker=target/'header.pdf.lst'
                for fault in ('directory','dangling-symlink'):
                    if blocker.is_dir() and not blocker.is_symlink():shutil.rmtree(blocker)
                    else:blocker.unlink(missing_ok=True)
                    if fault=='directory':
                        blocker.mkdir();(blocker/'owned-sentinel').write_text('keep old valid dataset')
                    else:blocker.symlink_to(tmp/'missing-report-target')
                    before_all={str(path.relative_to(target)):(hashlib.sha256(path.read_bytes()).hexdigest(),path.stat().st_mtime_ns)
                                for path in target.rglob('*') if path.is_file()}
                    r=run(binary,tmp,target,['--aggregate_only'])
                    after_all={str(path.relative_to(target)):(hashlib.sha256(path.read_bytes()).hexdigest(),path.stat().st_mtime_ns)
                               for path in target.rglob('*') if path.is_file()}
                    changed=sorted(key for key in set(before_all)|set(after_all) if before_all.get(key)!=after_all.get(key))
                    require(r.returncode>0 and 'header.pdf.lst' in r.stderr,
                            'late tomography publication '+fault+' did not fail normally')
                    require(after_all==before_all,'failed tomography rerun changed old complete dataset bytes/mtimes: '+str(changed))
                    require((blocker.is_dir() and (blocker/'owned-sentinel').read_text()=='keep old valid dataset') if fault=='directory'
                            else blocker.is_symlink() and blocker.readlink()==tmp/'missing-report-target',
                            'late publication obstruction was replaced')
                    require(not list(target.glob('.aggregate-*')),'successful rollback leaked private staging')
                    print('PASS existing valid tomography rerun restores all old global/series/report/movie bytes/mtimes after changed-metadata late '+fault+' failure')
            finally:
                    series.write_text(old_series);second.write_text(old_second)
        if publication_only!='rollback':
            for name,flags in [('header.pdf.lst',[]),('logfile.pdf.lst',['--skip_logfile'])]:
                if publication_only in ('header','logfile') and name!=publication_only+'.pdf.lst':continue
                target=tmp/('tomo-list-collision-'+name)
                r=run(binary,tmp,target)
                require(r.returncode==0,'report-list collision fixture failed: '+r.stderr[-2000:])
                shutil.copyfile(tmp/'tilt_series/one.star',tmp/name)
                (tmp/'in.star').write_text(tomo_input.replace('tilt_series/one.star',name))
                before_all={str(path.relative_to(target)):(hashlib.sha256(path.read_bytes()).hexdigest(),path.stat().st_mtime_ns)
                            for path in target.rglob('*') if path.is_file()}
                r=run(binary,tmp,target,['--aggregate_only',*flags])
                after_all={str(path.relative_to(target)):(hashlib.sha256(path.read_bytes()).hexdigest(),path.stat().st_mtime_ns)
                           for path in target.rglob('*') if path.is_file()}
                require(r.returncode>0 and name in r.stderr and 'collides' in r.stderr,
                        'generated report-list collision was not refused before staging: '+name+' '+r.stderr[-2000:])
                require(after_all==before_all and not list(target.glob('.aggregate-*')),
                        'report-list collision changed old dataset or reached publication')
                print('PASS tomography '+name+' collision before staging preserves old dataset'+(' with skip_logfile' if flags else ''))
                (tmp/'in.star').write_text(tomo_input)
        # Flipping a real gain prepares the shared output/gain.mrc referenced by
        # every movie model. A series input with that name must not replace it.
        from test_gain_cache import write_mrc
        # The healthy unbinned output already has the TIFF's width/height; use
        # its MRC header rather than requiring a Python image-decoder package.
        with (out/'Movies/a.mrc').open('rb') as image:nx,ny=struct.unpack('<2i',image.read(8))
        require(nx>0 and ny>0,'healthy unbinned gain-fixture dimensions missing')
        gain=tmp/'prepared-input-gain.mrc';write_mrc(gain,[[1.0]*(nx*ny)],nx,ny)
        gain_args=['--gainref',str(gain),'--gain_flip','1']
        target=tmp/'tomo-gain-collision';r=run(binary,tmp,target,gain_args)
        require(r.returncode==0,'tomographic actual gain fixture failed: '+r.stderr[-2000:])
        prepared=target/'gain.mrc'
        require(prepared.is_file(),'actual shared gain was not prepared')
        for model in (target/'Movies').glob('*.star'):
            require(str(prepared) in model.read_text(),'movie model does not reference prepared shared gain')
        retained=products(target);gain_before=(hashlib.sha256(prepared.read_bytes()).hexdigest(),prepared.stat().st_mtime_ns)
        (target/'corrected_tilt_series.star').unlink();(target/'logfile.pdf').unlink()
        shutil.copyfile(tmp/'tilt_series/one.star',tmp/'gain.mrc')
        (tmp/'in.star').write_text(tomo_input.replace('tilt_series/one.star','gain.mrc'))
        r=run(binary,tmp,target,[*gain_args,'--aggregate_only'])
        gain_after=(hashlib.sha256(prepared.read_bytes()).hexdigest(),prepared.stat().st_mtime_ns)
        require(r.returncode>0 and 'gain.mrc' in r.stderr,'tomographic gain-reference collision falsely succeeded: exit='+str(r.returncode)+' gain_preserved='+str(gain_after==gain_before))
        require(not (target/'corrected_tilt_series.star').exists() and not (target/'logfile.pdf').exists(),
                'tomographic gain-reference collision published joint/report success')
        require(products(target)==retained and gain_after==gain_before and not list(target.glob('.aggregate-*')),
                'tomographic gain collision changed prepared gain/movie bytes/mtimes or leaked staging')
        print('PASS tomography shared-gain collision refuses, preserves prepared gain/model/movie bytes and mtimes')
    finally:(tmp/'in.star').write_text(original)


def main() -> int:
    import os
    ap = argparse.ArgumentParser()
    ap.add_argument('--binary', type=Path, required=True)
    ap.add_argument('--aggregate-arg',default='--aggregate_only',choices=['--aggregate_only','--only_do_unfinished'])
    ap.add_argument('--only',choices=['literal','effective-optics','geometry','tomography','tomography-rollback','tomography-list-collisions','tomography-header-collision','tomography-logfile-collision'])
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
        if a.only and a.only.startswith('tomography'):
            selection={'tomography':None,'tomography-rollback':'rollback','tomography-list-collisions':'lists','tomography-header-collision':'header','tomography-logfile-collision':'logfile'}[a.only]
            tomography_controls(binary,tmp,selection);return 0
        if a.only=='literal':literal_controls(binary,tmp);return 0
        if a.only=='effective-optics':effective_optics_controls(binary,tmp);return 0
        if a.only=='geometry':geometry_controls(binary,tmp,baseline);return 0
        literal_controls(binary,tmp)
        geometry_controls(binary,tmp,baseline)
        effective_optics_controls(binary,tmp)
        tomography_controls(binary,tmp)
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
