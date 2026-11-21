#!/usr/bin/env python3
"""Seeded counting-statistics extension of diagnostics v2; no production warps.

Synthesis uses an independently oversampled random field and SciPy cubic B-splines.
Only the existing MRC/STAR serializers are reused. See docs/post_rc0/s1/km_truth/.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import platform
import struct
import time
from pathlib import Path
import numpy as np
from generate_known_motion_fixture import STAR_TEMPLATE

SCHEMA = 'motion-counting/1'
PIXEL_SIZE = .885
CONDITIONS = {
    'dose05': dict(dose=.5), 'dose1': dict(dose=1.),
    'dose2': dict(dose=2.), 'dose4': dict(dose=4.),
    'outmodel': dict(dose=1., motion='outmodel'),
    'nonsquare': dict(dose=1., nx=5760, ny=4092),
    'pedestal0': dict(dose=1., pedestal=0.),
    'pedestal32': dict(dose=1., pedestal=32.),
    'contrast025': dict(dose=1., scale=.25, pedestal=1.),
    'contrast4': dict(dose=1., scale=4., pedestal=1.),
}


def recipe(condition='dose1', seed=0, **overrides):
    r = dict(schema=SCHEMA, condition=condition, nx=4096, ny=4096, frames=40,
             dose=1., pedestal=None, scale=1., texture_rms=.04, oversample=2,
             pixel_size=PIXEL_SIZE, motion='inmodel', scene_seed=238267,
             noise_seed=int(seed), control=None)
    r.update(CONDITIONS[condition]); r.update(overrides)
    if r['pedestal'] is None: r['pedestal'] = r['dose']
    if (r['nx'] < 32 or r['ny'] < 32 or r['frames'] < 2 or r['dose'] <= 0
            or r['scale'] <= 0 or r['oversample'] < 2):
        raise ValueError('unsupported geometry/counting parameters')
    return r


def displacement(r, f, x, y):
    """Forward material displacement, not an inverse or a correction field."""
    t = f/(r['frames']-1)
    x, y = np.broadcast_arrays(x, y)
    if r['control'] == 'zero': return np.zeros(x.shape+(2,))
    if r['control'] == 'translation':
        return np.broadcast_to(np.array([f, -2*f], float), x.shape+(2,)).copy()
    g = np.array([8*(-np.expm1(-t/.1))+4*t, -5*(-np.expm1(-t/.15))-2*t])
    u, v = x/r['nx']-.5, y/r['ny']-.5
    # Six spatial monomials x three temporal powers, within the 18-term model.
    lx = (3*u-2*v+4*(u*u-1/12)+2*u*v)*(t+.3*t*t-.3*t**3)
    ly = (-2*u-3*v+3*(v*v-1/12)-u*v)*(t-.2*t*t+.2*t**3)
    if r['motion'] == 'outmodel':
        lx += 2*np.sin(2*np.pi*u)*np.cos(2*np.pi*v)*np.sin(np.pi*t/2)
        ly += 2*np.cos(2*np.pi*u)*np.sin(2*np.pi*v)*np.sin(np.pi*t/2)
    return np.stack((lx+g[0], ly+g[1]), axis=-1)


def inverse(r, f, x, y):
    """Contraction inverse, checked independently by forward closure at every tile."""
    x, y = np.broadcast_arrays(x, y)
    qx, qy = x.copy(), y.copy()
    for _ in range(24):
        d = displacement(r, f, qx, qy)
        ax, ay = x-d[..., 0], y-d[..., 1]
        if max(float(np.max(abs(ax-qx))), float(np.max(abs(ay-qy)))) < 2e-10:
            qx, qy = ax, ay
            break
        qx, qy = ax, ay
    d = displacement(r, f, qx, qy)
    e = max(float(np.max(abs(qx+d[..., 0]-x))), float(np.max(abs(qy+d[..., 1]-y))))
    if e > 1e-8: raise ValueError(f'inverse closure failed: {e}')
    return qx, qy


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(8<<20), b''): h.update(b)
    return h.hexdigest()


def scene(r):
    """Random weak multiscale texture. FFT creates a scene, never shifts a movie.

    Cutoff .16 cycles/detector-pixel; 2x synthesis samples at .5-pixel spacing.
    A 32-pixel halo supplies nonperiodic detector motion without clipping.
    """
    from scipy.ndimage import spline_filter
    margin=32; s=r['oversample']
    ny, nx = (r['ny']+2*margin)*s, (r['nx']+2*margin)*s
    rng=np.random.Generator(np.random.PCG64(r['scene_seed']))
    a=rng.standard_normal((ny,nx),dtype=np.float32)
    spec=np.fft.rfft2(a); del a
    fy=np.fft.fftfreq(ny,d=1/s)[:,None]; fx=np.fft.rfftfreq(nx,d=1/s)[None,:]
    k2=fx*fx+fy*fy
    envelope=np.exp(-k2/(2*.055**2))*(1-np.exp(-k2/(2*.007**2)))
    envelope[k2>.16**2]=0
    spec*=envelope; del envelope,k2
    a=np.fft.irfft2(spec,s=(ny,nx)).astype(np.float32); del spec
    a-=a.mean(dtype=np.float64); a*=r['texture_rms']/a.std(dtype=np.float64)
    if np.max(abs(a)) >= .8: raise ValueError('nonpositive counting intensity')
    # This defines the continuous oversampled scene. No MotionCorr helper is used.
    return spline_filter(a,order=3,output=np.float32,mode='mirror'), margin


def expected(r, out):
    """Cache noise-free unit-dose expectation; stream tiles to limit peak RAM."""
    from scipy.ndimage import map_coordinates
    coeff,margin=scene(r); s=r['oversample']
    movie=np.lib.format.open_memmap(out,mode='w+',dtype='<f4',shape=(r['frames'],r['ny'],r['nx']))
    closure=0.
    for f in range(r['frames']):
        for y0 in range(0,r['ny'],64):
            y,x=np.mgrid[y0:min(y0+64,r['ny']),:r['nx']].astype(float)
            qx,qy=inverse(r,f,x,y)
            d=displacement(r,f,qx,qy)
            closure=max(closure,float(np.max(abs(qx+d[...,0]-x))),float(np.max(abs(qy+d[...,1]-y))))
            if min(qx.min(),qy.min()) < -margin+2 or qx.max() >= r['nx']+margin-2 or qy.max() >= r['ny']+margin-2:
                raise ValueError('synthesis halo exhausted')
            movie[f,y0:y0+len(y)]=1+map_coordinates(coeff,[(qy+margin)*s,(qx+margin)*s],order=3,prefilter=False,mode='mirror')
        movie.flush()
    del movie
    return dict(forward_inverse_max_px=closure, expectation_sha256=digest(out))


def mrc_header(r, lo, hi, mean, rms):
    h=bytearray(1024); nx,ny,nz=r['nx'],r['ny'],r['frames']
    struct.pack_into('<4i',h,0,nx,ny,nz,2); struct.pack_into('<3i',h,28,nx,ny,nz)
    struct.pack_into('<3f',h,40,nx*r['pixel_size'],ny*r['pixel_size'],nz*r['pixel_size'])
    struct.pack_into('<3f',h,52,90,90,90); struct.pack_into('<3i',h,64,1,2,3)
    struct.pack_into('<3f',h,76,lo,hi,mean); h[208:212]=b'MAP '; h[212:216]=bytes((68,65,0,0))
    struct.pack_into('<f',h,216,rms); return h


def generate(r, expectation, out):
    start=time.time(); out.mkdir(parents=True,exist_ok=False)
    a=np.load(expectation,mmap_mode='r',allow_pickle=False)
    if a.shape != (r['frames'],r['ny'],r['nx']): raise ValueError('expectation geometry mismatch')
    record=json.loads(expectation.with_suffix('.json').read_text())
    for key in ['nx','ny','frames','motion','control','scene_seed','texture_rms','oversample']:
        if record['recipe'][key] != r[key]: raise ValueError(f'expectation recipe mismatch: {key}')
    if record['proof']['expectation_sha256'] != digest(expectation): raise ValueError('expectation hash mismatch')
    rng=np.random.Generator(np.random.PCG64(r['noise_seed']))
    lo,hi,total,total2,n= float('inf'),-float('inf'),0.,0.,0
    path=out/'movie.mrcs'
    with path.open('wb') as fh:
        fh.write(bytes(1024))
        for frame in a:
            # Independent detector counts per frame; seed pairs share draws across
            # pedestal/positive-amplitude arms. No sensor-noise realization moves.
            c=frame*r['dose'] if r['control'] else rng.poisson(frame.astype(float)*r['dose'])
            pixels=(r['pedestal']+r['scale']*(c-r['dose'])).astype('<f4')
            pixels.tofile(fh)
            lo=min(lo,float(pixels.min())); hi=max(hi,float(pixels.max()))
            total+=pixels.sum(dtype=float); total2+=np.square(pixels,dtype=float).sum(); n+=pixels.size
        mean=total/n; fh.seek(0); fh.write(mrc_header(r,lo,hi,mean,float(np.sqrt(max(0,total2/n-mean*mean)))))
    (out/'input.star').write_text(STAR_TEMPLATE.format(pixel_size=r['pixel_size'],voltage=300.,movie='movie.mrcs'))
    receipt=dict(schema=SCHEMA,recipe=r,files={p.name:digest(p) for p in [path,out/'input.star']},
                 expectation_sha256=digest(expectation),numpy=np.__version__,python=platform.python_version(),
                 seconds=time.time()-start,mean=mean,std=float(np.sqrt(max(0,total2/n-mean*mean))),
                 orientation='MRC native rows: y increases by stored row, no TIFF conversion',
                 preprocessing='identity: no gain, --skip_defect required; injection commutes exactly')
    (out/'RECEIPT.json').write_text(json.dumps(receipt,indent=2,allow_nan=False)+'\n')
    return receipt


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--condition',choices=list(CONDITIONS),default='dose1')
    ap.add_argument('--seed',type=int,default=0)
    ap.add_argument('--outdir',type=Path)
    ap.add_argument('--expectation',type=Path,required=True)
    ap.add_argument('--make-expectation',action='store_true')
    ap.add_argument('--control',choices=['zero','translation'])
    args=ap.parse_args()
    r=recipe(args.condition,args.seed,**(dict(nx=512,ny=384,frames=5,control=args.control,texture_rms=.15) if args.control else {}))
    if args.make_expectation:
        if args.expectation.exists(): raise FileExistsError(args.expectation)
        proof=expected(r,args.expectation)
        args.expectation.with_suffix('.json').write_text(json.dumps(dict(recipe=r,proof=proof),indent=2)+'\n')
    if args.outdir: generate(r,args.expectation,args.outdir)
