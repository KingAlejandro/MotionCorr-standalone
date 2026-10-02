#!/usr/bin/env python3
"""Small heterogeneous-workload correctness probe, not a throughput benchmark.

Reuses the independent test TIFF writer and production reader probe. Re-encodings
share exact canonical samples. Separate signal families are synthetic, not new
experimental datasets. EER, BigTIFF and large-file I/O are deliberately unclaimed.
"""
import argparse
import hashlib
import json
import lzma
from pathlib import Path
import struct
import subprocess
import sys
import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO/'tests'))
sys.path.insert(0, str(REPO/'tools'))
from test_tiff_read import write_tiff
from compare_motioncorr import parse_mrc, normalized_mrc_labels, parse_star_file


def sha(data):
    return hashlib.sha256(data).hexdigest()


def mrc(data, mode):
    f,y,x = data.shape
    dtype = {2:'<f4',6:'<u2',12:'<f2'}[mode]
    converted = data.astype(dtype)
    if not np.array_equal(converted.astype('f4'),data):
        raise ValueError('encoding would change canonical samples')
    h = bytearray(1024)
    struct.pack_into('<4i',h,0,x,y,f,mode)
    struct.pack_into('<3i',h,28,x,y,f)
    struct.pack_into('<3f',h,40,float(x),float(y),float(f))
    struct.pack_into('<3f',h,52,90.,90.,90.)
    struct.pack_into('<3i',h,64,1,2,3)
    struct.pack_into('<3f',h,76,float(data.min()),float(data.max()),float(data.mean()))
    h[208:216] = b'MAP '+bytes([68,65,0,0])
    return bytes(h)+converted.tobytes()


def star(path, cases):
    path.write_text('data_optics\n\nloop_\n_rlnOpticsGroupName #1\n_rlnOpticsGroup #2\n'
        '_rlnMicrographOriginalPixelSize #3\n_rlnVoltage #4\n'
        '_rlnSphericalAberration #5\n_rlnAmplitudeContrast #6\n'
        'optics1 1 1.0 300 2.7 0.1\noptics2 2 1.5 200 2.7 0.1\n\n'
        'data_movies\n\nloop_\n_rlnMicrographMovieName #1\n_rlnOpticsGroup #2\n'
        '_rlnNrOfFrames #3\n'+''.join(f"{c['path']} {c['optics']} {c['frames']}\n" for c in cases))


def identity(out, case):
    # Input paths have no dots except extensions; compressed MRC retains .mrc
    # in its basename, which the production output-name function turns into _mrc.
    stem = str(Path(case['path']).with_suffix('')).replace('.','_')
    products = {}
    for suffix in ('.mrc','_noDW.mrc'):
        _,pixels,h = parse_mrc(out/(stem+suffix))
        if not np.isfinite(pixels).all():
            raise ValueError('nonfinite corrected image')
        products[suffix] = sha(h[:224]+normalized_mrc_labels(h)+pixels.tobytes())
    metadata = parse_star_file(out/(stem+'.star'))
    # Preserve all metadata except the deliberately different input name.
    for block in metadata.values():
        if isinstance(block,dict):
            block.get('fields',{}).pop('_rlnMicrographMovieName',None)
    products['metadata'] = metadata
    return products


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--binary',type=Path,required=True)
    p.add_argument('--helper',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--gpu',action='store_true')
    a = p.parse_args()
    binary,helper = a.binary.resolve(),a.helper.resolve()
    root = a.output.resolve(); root.mkdir(parents=True,exist_ok=False)
    inputs = root/'inputs'; inputs.mkdir()
    cases = []
    shapes = [(256,192,4),(256,192,24),(256,192,80),(256,192,160),(384,256,17)]
    families = [('counts',*shape) for shape in shapes]+[('high_u16',256,192,12),('signed',256,192,12)]
    for index,(signal,x,y,f) in enumerate(families):
        rng = np.random.default_rng(500+index)
        base = rng.integers(16,96,size=(y,x))
        data = np.stack([np.roll(base,(i%5,i%3),axis=(0,1)) for i in range(f)]).astype('f4')
        if signal=='high_u16': data *= 37
        if signal=='signed': data = data/8-7
        # Include a reproducible detector outlier, identical in every encoding.
        data[:,y//2,x//2] = float(data.max())
        variants = [('mrc_f32',2,0,0),('mrc_xz',2,0,0)]
        if signal=='signed': variants += [('mrc_f16',12,0,0)]
        else:
            variants += [('mrc_u16',6,0,0),('tif_u16_raw',16,1,17),
                         ('tif_u16_deflate_r1',16,8,1),('tif_u16_deflate_r17',16,8,17)]
            if signal=='counts':
                variants += [('tif_u8_raw',8,1,17),('tif_u8_deflate',8,8,17)]
        for variant,bits,compression,rps in variants:
            name=f'case{index}_{variant}'
            ext = '.tiff' if compression else ('.mrc.xz' if variant=='mrc_xz' else '.mrc')
            path = inputs/(name+ext)
            if compression:
                disk = data[:,::-1,:].astype('u1' if bits==8 else '<u2')
                if not np.array_equal(disk[:,::-1,:].astype('f4'),data):
                    raise ValueError('TIFF narrowing would change samples')
                write_tiff(path,[[row.tobytes() for row in frame] for frame in disk],bits,compression,rps,x)
            else:
                raw = mrc(data,bits)
                path.write_bytes(lzma.compress(raw) if variant=='mrc_xz' else raw)
            # The Image helper cannot read compressed MRC. Verify its encoded
            # bytes independently here; the application exercises the pipe reader.
            if variant=='mrc_xz':
                if lzma.decompress(path.read_bytes()) != mrc(data,2):
                    raise ValueError('compressed MRC source mismatch')
            else:
                dump=root/'decoded.raw'
                subprocess.run([str(helper),'read_tiff_raw',str(path),str(dump)],check=True)
                raw=dump.read_bytes(); dump.unlink()
                if struct.unpack('<3q',raw[:24])!=(x,y,f) or raw[24:]!=data.astype('<f4').tobytes():
                    raise ValueError(f'production reader differs from canonical samples: {variant}')
            cases.append(dict(path=str(path.relative_to(root)),family=index,signal=signal,nx=x,ny=y,
                frames=f,variant=variant,optics=index%2+1,bytes=path.stat().st_size,
                input_sha256=sha(path.read_bytes()),samples_sha256=sha(data.astype('<f4').tobytes())))
    (root/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
    (root/'gain.mrc').write_bytes(mrc((1+np.indices((192,256))[1]%4/8).astype('f4')[None],2))
    (root/'defects.txt').write_text('20 30 2 2\n')
    results=[]
    for profile in ('mixed','gain_defect'):
        selected = cases if profile=='mixed' else [c for c in cases if c['nx']==256]
        reference=None
        arms=['float','auto','reverse'] if profile=='mixed' else ['float','auto']
        for arm in arms:
            ordered=list(reversed(selected)) if arm=='reverse' else selected
            name=profile+'-'+arm; star(root/(name+'.star'),ordered)
            out=root/name; witness=root/(name+'.witness')
            cmd=[str(binary),'--i',name+'.star','--o',str(out),'--use_own','--j','4',
                 '--max_io_threads','4','--seed','1','--skip_logfile','--dose_weighting',
                 '--dose_per_frame','1','--save_noDW','--patch_x','1','--patch_y','1',
                 '--ingest','float' if arm=='float' else 'auto','--ingest_witness',str(witness)]
            if a.gpu: cmd+=['--gpu','0']
            if profile=='gain_defect': cmd+=['--gainref','gain.mrc','--defect_file','defects.txt']
            with (root/(name+'.log')).open('w') as log:
                subprocess.run(cmd,cwd=root,stdout=log,stderr=subprocess.STDOUT,check=True)
            by_case={c['path']:identity(out,c) for c in selected}
            by_family={}
            for c in selected:
                got=by_case[c['path']]
                if c['family'] in by_family and got!=by_family[c['family']]:
                    raise ValueError(f'encoding changes products: {name} {c["path"]}')
                by_family[c['family']]=got
            if reference is None: reference=by_case
            if by_case!=reference: raise ValueError(f'route/order changes products: {name}')
            routes=[line.rsplit(' ',1) for line in witness.read_text().splitlines()]
            expected={c['path']:('compact' if a.gpu and arm!='float' and c['variant'].startswith('tif_') else 'float') for c in selected}
            if len(routes)!=len(expected) or dict(routes)!=expected:
                raise ValueError('missing, duplicate or unexpected ingest route')
            if not (out/'corrected_micrographs.star').is_file(): raise ValueError('no aggregate')
            row=dict(profile=profile,arm=arm,movies=len(selected),encodings_exact=True,
                routes_exact=True,products_sha256=sha(json.dumps(by_case,sort_keys=True).encode()),command=cmd)
            results.append(row); print(json.dumps(row),flush=True)
            (root/'results.json').write_text(json.dumps(results,indent=2)+'\n')
    (root/'provenance.json').write_text(json.dumps(dict(binary_sha256=sha(binary.read_bytes()),
        helper_sha256=sha(helper.read_bytes()),gpu=a.gpu,movies=len(cases),
        note='synthetic encoding/transition coverage; not scientific diversity or performance'),indent=2)+'\n')


if __name__=='__main__': main()
