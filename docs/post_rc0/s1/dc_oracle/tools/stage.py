#!/usr/bin/env python3
"""Stage-only DC sweep. FFTW float/double vs independent full-complex NumPy FFT.
No movie preprocessing or production shifting helper is used.
"""
import ctypes as c, ctypes.util, json, pathlib, sys
import numpy as np

def inverse(a, nx, double=False):
    dt=np.complex128 if double else np.complex64;rt=np.float64 if double else np.float32
    a=np.array(a,dtype=dt,order='C',copy=True);out=np.empty((a.shape[0],nx),dtype=rt)
    lib=c.CDLL(ctypes.util.find_library('fftw3' if double else 'fftw3f'))
    pre='fftw_' if double else 'fftwf_';plan=getattr(lib,pre+'plan_dft_c2r_2d')
    plan.argtypes=[c.c_int,c.c_int,c.c_void_p,c.c_void_p,c.c_uint];plan.restype=c.c_void_p
    p=plan(a.shape[0],nx,a.ctypes.data,out.ctypes.data,64)
    if not p:raise RuntimeError('plan failed')
    ex=getattr(lib,pre+'execute');ex.argtypes=[c.c_void_p];ex(p)
    de=getattr(lib,pre+'destroy_plan');de.argtypes=[c.c_void_p];de(p)
    return out.astype(np.float64)

def full_reference(a,nx):
    a=np.array(a,dtype=np.complex128,copy=True);ny=a.shape[0]
    # Independently project the two self-conjugate columns, then explicitly
    # populate every negative-x coefficient before a full complex inverse.
    for x in [0,nx//2]:
        col=a[:,x].copy();a[:,x]=.5*(col+np.conj(col[(-np.arange(ny))%ny]))
    z=np.empty((ny,nx),complex);z[:,:nx//2+1]=a
    for x in range(1,nx//2):z[:,nx-x]=np.conj(a[(-np.arange(ny))%ny,x])
    out=np.fft.ifft2(z)*nx*ny
    assert np.max(abs(out.imag))<1e-7*max(1,np.max(abs(out.real)))
    return out.real

def select(m,r):
    ny,nx=m.shape;best=-1e30;px=py=0;ties=0
    for y in range(-r,r+1):
        for x in range(-r,r+1):
            v=m[y%ny,x%nx]
            if v>best:best=v;px=x;py=y
    vals=[m[py%ny,px%nx],m[py%ny,(px+1)%nx],m[py%ny,(px-1)%nx],m[(py+1)%ny,px%nx],m[(py-1)%ny,px%nx]]
    cur=[];den=[]
    for pos,vp,vn in [(px,vals[1],vals[2]),(py,vals[3],vals[4])]:
        d=float(vp)+float(vn)-2*float(best);den.append(d)
        cur.append(pos-.5*(float(vp)-float(vn))/d if abs(d)>1e-15 else float(pos))
    return {'integer':[px,py],'candidate':cur,'curvature':den,'ties':int(sum(m[y%ny,x%nx]==best for y in range(-r,r+1) for x in range(-r,r+1))),'boundary':abs(px)==r or abs(py)==r,'finite':bool(np.isfinite(m).all()),'guard':[abs(d)<=1e-15 for d in den],'fit_taken':[abs(d)>1e-15 for d in den]}

def sweep(name,spec,nx,r,truth=None):
    # Non-DC is fixed for every row; DC equals the map pedestal because
    # these inverses are unnormalised, like NewFFT.
    spec=spec.astype(np.complex128);native_dc=float(spec[0,0].real);spec[0,0]=0
    ref=full_reference(spec,nx);sr=select(ref,r)
    px,py=sr['integer'];v=ref[py%len(ref),px%nx]
    contrast=max(abs(v-ref[py%len(ref),(px+1)%nx]),abs(v-ref[py%len(ref),(px-1)%nx]),abs(v-ref[(py+1)%len(ref),px%nx]),abs(v-ref[(py-1)%len(ref),px%nx]))
    rows=[]
    for pedestal in sorted(set([0.,36000.,1e6,native_dc])):
        for arm in ['float-none','float-zero','double-none','double-zero']:
            z=spec.copy();z[0,0]=0 if arm.endswith('zero') else pedestal
            m=inverse(z,nx,arm.startswith('double'));q=select(m,r)
            delta=np.array(q['candidate'])-sr['candidate'];cur=np.array(q['curvature'])-sr['curvature']
            stored_dc=0. if arm.endswith('zero') else float(pedestal if arm.startswith('double') else np.float32(pedestal))
            centered=m-stored_dc
            rows.append({'case':name,'pedestal':pedestal,'stored_spectral_DC':stored_dc,'arm':arm,'reference':sr,'measured':q,'contrast':float(contrast),'candidate_error_px':float(np.linalg.norm(delta)),'curvature_max_abs_error':float(max(abs(cur))),'curvature_error_over_contrast':float(max(abs(cur))/contrast) if contrast else None,'map_max_abs_error':float(np.max(abs(centered-ref))),'map_error_over_contrast':float(np.max(abs(centered-ref))/contrast) if contrast else None,'analytic_truth':truth})
    return rows

def main(root,out):
    root=pathlib.Path(root);rows=[];native=[]
    ny=nx=32;y,x=np.mgrid[:ny,:nx];xx=(x+nx//2)%nx-nx//2;yy=(y+ny//2)%ny-ny//2
    cases={
        'parabola':(-(xx-.23)**2*.7-(yy+.31)**2*.4,{'vertex':[.23,-.31],'curvature':[-1.4,-.8]}),
        'flat':(np.zeros((ny,nx)),None),
        'exact-tie':(-((xx**2-4)**2)-yy**2,None),
        'near-tie':(-((xx**2-4)**2)-yy**2+xx*1e-5,None),
        'boundary':(-(xx-6.2)**2-(yy+.2)**2,{'unbracketed':True}),
        'guard':(-1e-16*(xx**2+yy**2),None)}
    for name,(m,truth) in cases.items():
        for scale in ([.01,1.,100.] if name=='parabola' else [1.]):
            z=np.fft.rfft2(m*scale)/(nx*ny)
            scaled_truth=dict(truth) if truth else None
            if scaled_truth and 'curvature' in scaled_truth:scaled_truth['curvature']=[v*scale for v in scaled_truth['curvature']]
            rows+=sweep(name+'-scale'+str(scale),z,nx,5,scaled_truth)
    for d in sorted(root.iterdir()):
        shape=json.load(open(d/'in.json'))['shape'];n,ny,nfx=shape;nx=2*(nfx-1)
        frames=np.fromfile(d/'in.bin',np.complex64).reshape(shape);w=np.fromfile(d/'wt.bin',np.float32).reshape(ny,nfx)
        # Sequential reference accumulation matches the specified algebra.
        fref=np.zeros((ny,nfx),np.complex64);ref64=np.zeros((ny,nfx),np.complex128)
        for f in frames:fref+=f;ref64+=f.astype(np.complex128)
        for f in [0,min(10,n-1)]:
            z=(fref-frames[f])*frames[f].conj()*w
            z64=(ref64-frames[f].astype(np.complex128))*frames[f].astype(np.complex128).conj()*w.astype(float)
            rows+=sweep(d.name+'-fr'+str(f+1),z.astype(np.complex128),nx,min(12,nx//2-1))
            a=inverse(z64,nx,True);b=full_reference(z64,nx)
            sym=max(float(np.max(abs(z64[:,j]-np.conj(z64[(-np.arange(ny))%ny,j])))) for j in [0,nx//2])
            native.append({'boundary_conjugacy_max_abs':sym,'case':d.name,'frame':f+1,'fftw_double_vs_full_complex_max_error':float(np.max(abs(a-b))),'map_pedestal':float(z64[0,0].real),'source':json.load(open(d/'in.json'))})
    nonfinite={}
    for v in [float('nan'),float('inf'),-float('inf')]:
        m=np.zeros((32,32));m[0,0]=v;nonfinite[str(v)]=select(m,5)
    def clean(o):
        if isinstance(o,float) and not np.isfinite(o):return str(o)
        if isinstance(o,dict):return {k:clean(v) for k,v in o.items()}
        if isinstance(o,list):return [clean(v) for v in o]
        return o
    json.dump(clean({'rows':rows,'real_double_crosscheck':native,'nonfinite_current_policy':nonfinite,'limitations':'Stage candidates preserve CPU search/guard. Native CUDA tie reduction differs. Flat/tie/boundary outputs are characterized, not valid measured motion.'}),open(out,'w'),indent=1,allow_nan=False)
    print('stage rows',len(rows),'real double max crosscheck',max(q['fftw_double_vs_full_complex_max_error'] for q in native))
if __name__=='__main__':main(*sys.argv[1:])
