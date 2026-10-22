#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Independent full-complex inverse and peak replay; never invokes MotionCorr."""
import hashlib, json, pathlib, re, sys
import numpy as np

def full_spectrum(half, nx):
    h=np.array(half,dtype=np.complex128,copy=True); ny=h.shape[-2]
    # Real inverse implicitly consumes the Hermitian part of self-conjugate columns.
    neg=(-np.arange(ny))%ny
    for x in [0,nx//2]: h[..., :,x]=(h[..., :,x]+h[...,neg,x].conj())*.5
    full=np.empty(h.shape[:-1]+(nx,),complex);full[...,:nx//2+1]=h
    for x in range(nx//2+1,nx):full[..., :,x]=h[...,neg,nx-x].conj()
    return full

def inverse(half,nx):
    return np.fft.ifft2(full_spectrum(half,nx),axes=(-2,-1),norm='forward').real

def peak(a,search,scale,cuda=False):
    ny,nx=a.shape; q=np.arange(-search,search+1); xx,yy=np.meshgrid(q,q)
    v=a[yy%ny,xx%nx].ravel(); win=0
    if cuda:
        lm=np.full(256,-1e30); li=np.zeros(256,int)
        for t in range(256):
            for j in range(t,len(v),256):
                if v[j]>lm[t]:lm[t]=v[j];li[t]=j
        for stride in [128,64,32,16,8,4,2,1]:
            for t in range(stride):
                if lm[t+stride]>lm[t]:lm[t]=lm[t+stride];li[t]=li[t+stride]
        win=int(li[0])
    else:win=int(np.argmax(v))
    x=int(xx.ravel()[win]);y=int(yy.ravel()[win]);m=float(v[win])
    vp=np.array([a[y%ny,(x+1)%nx],a[(y+1)%ny,x%nx]],float)
    vn=np.array([a[y%ny,(x-1)%nx],a[(y-1)%ny,x%nx]],float)
    den=vp+vn-2*m;pos=np.array([x,y],float)
    eps=float(np.float32(1e-15)) if cuda else 1e-15
    for k in range(2):
        if abs(den[k])>eps:pos[k]-=.5*(vp[k]-vn[k])/den[k]
    shift=pos*np.asarray(scale)
    if cuda:shift=shift.astype(np.float32).astype(float)
    outside=(np.abs(xx.ravel()-x)>1)|(np.abs(yy.ravel()-y)>1)
    comp=float(v[outside].max()) if outside.any() else None
    loc=[]
    for j in np.flatnonzero(outside):
        sx=int(xx.ravel()[j]);sy=int(yy.ravel()[j]);z=v[j]
        if all(a[(sy+dy)%ny,(sx+dx)%nx]<=z for dy in [-1,0,1] for dx in [-1,0,1]):loc.append(float(z))
    return dict(integer_xy=[x,y],shift_xy=shift.tolist(),maximum=m,ties=int(np.count_nonzero(v==m)),
        curvature_xy=den.tolist(),neighbors_plus_xy=vp.tolist(),neighbors_minus_xy=vn.tolist(),
        search_boundary=abs(x)==search or abs(y)==search,competing_outside_3x3=comp,
        competing_local_max=max(loc) if loc else None,local_max_count=len(loc),
        search_contrast=float(v.max()-v.min()))

def controls():
    checks=[]
    ny,nx=12,16
    for dx,dy in [(0,0),(3,0),(0,-2),(3,-2)]:
        a=np.zeros((ny,nx));a[0,0]=1;b=np.roll(a,(dy,dx),(0,1))
        h=np.fft.rfft2(a)*np.fft.rfft2(b).conj()
        m=inverse(h,nx)
        for cuda in [False,True]:
            got=peak(m,4,[1,1],cuda)['shift_xy'];assert np.max(np.abs(np.array(got)-[-dx,-dy]))<1e-12
        checks.append(dict(control='correlation-sign-axis-zero',translation_xy=[dx,dy],expected_shift_xy=[-dx,-dy]))
    y,x=np.mgrid[:ny,:nx];xx=((x+nx//2)%nx)-nx//2;yy=((y+ny//2)%ny)-ny//2
    parab=100-(xx-.25)**2-2*(yy+.375)**2
    for cuda in [False,True]:
        got=peak(parab,4,[2,3],cuda)['shift_xy'];assert np.array_equal(got,[.5,-1.125])
    checks.append(dict(control='quadratic-fractional-and-scale',expected_shift_xy=[.5,-1.125]))
    h=np.arange(6*5,dtype=float).reshape(6,5)+1j*np.arange(30,60).reshape(6,5)
    full=full_spectrum(h,8); yy,xx=np.mgrid[:6,:8];direct=np.zeros((6,8),complex)
    for ky in range(6):
        for kx in range(8):direct+=full[ky,kx]*np.exp(2j*np.pi*(ky*yy/6+kx*xx/8))
    error=float(np.max(np.abs(inverse(h,8)-direct.real)));assert error<1e-10
    assert np.max(np.abs(inverse(h,8)-np.fft.irfft2(h,s=(6,8),norm='forward')))<1e-10
    checks.append(dict(control='direct-complex-DFT-Hermitian-normalization',max_abs=error))
    flat=np.ones((12,16));assert peak(flat,4,[1,1])['ties']==81
    checks.append(dict(control='flat-ties-retained',ties=81))
    return dict(status='PASS',checks=checks,numpy=np.__version__)

def updated(before,candidate,cuda):
    # updatePatchShifts subtracts in float before RFLOAT accumulation on CUDA.
    delta=(candidate.astype(np.float32)-candidate[0].astype(np.float32)).astype(float) if cuda else candidate-candidate[0]
    return before+delta

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def array(stem,it,kind,dtype,shape):
    p=pathlib.Path(str(stem)+f'-i{it}-{kind}.bin');a=np.fromfile(p,dtype=dtype);assert a.size==np.prod(shape),p
    return a.reshape(shape)
def analyze(root):
    rows=[]; trajectory=[]
    for case in ['integer','fractional','affine','noisy']:
      truth=np.load(root/'fixtures'/f'{case}_field.npy',allow_pickle=False)
      for backend in ['cpu','cuda']:
        run=root/'runs'/f'{backend}-{case}-on'; cuda=backend=='cuda'
        global_shift=np.loadtxt(run/'state/global.txt')[:,1:]
        log=(run/'out'/f'{case}.log').read_text()
        for meta in sorted((run/'capture').glob('c*.json')):
          geo=json.loads(meta.read_text());stem=meta.with_suffix('');nx,ny=geo['ccf_nxy'];n=geo['frames']; fx=nx//2+1
          patch=geo['patch_yx']; isglobal=patch==[0,0]
          point=None
          if not isglobal:
            pat=rf'Patch \({patch[0]}, {patch[1]}\):.*?Center = \((\d+), (\d+)\)'
            match=re.search(pat,log);assert match,(pat,run);cx,cy=map(int,match.groups());point=[cx,cy]
          iters=sorted(int(p.name.split('-i')[1].split('-')[0]) for p in stem.parent.glob(stem.name+'-i*-before.bin'))
          wt=array(stem,0,'weight','<f4',(ny,fx)).astype(float)
          for it in iters:
            inputs=array(stem,it,'input','<c8',(n,ny,fx)).astype(complex)
            ref=array(stem,it,'reference','<c8',(ny,fx)).astype(complex)
            if cuda:
              spec=array(stem,it,'spectrum','<c8',(n,ny,fx));maps=array(stem,it,'map','<f4',(n,ny,nx))
            else:
              spec=np.stack([array(stem,it,f'spectrum-f{f}','<c8',(ny,fx)) for f in range(n)])
              maps=np.stack([array(stem,it,f'map-f{f}','<f4',(ny,nx)) for f in range(n)])
            before=array(stem,it,'before','<f8',(n,2));after=array(stem,it,'after','<f8',(n,2));candidates=array(stem,it,'candidate','<f8',(n,2))
            conditional=inverse(spec,nx)
            product=inverse((ref[None]-inputs)*inputs.conj()*wt,nx)
            reaccum=inverse((inputs.sum(axis=0)[None]-inputs)*inputs.conj()*wt,nx)
            peaks={k:[peak(a,geo['search'],geo['scale_xy'],cuda) for a in arrays] for k,arrays in [('stored',maps),('rounded_inverse',conditional.astype(np.float32)),('inverse_double',conditional),('product_double',product),('reference_double',reaccum)]}
            shifts={k:np.array([p['shift_xy'] for p in ps]) for k,ps in peaks.items()}
            assert np.array_equal(updated(before,candidates,cuda),after),('native update mismatch',meta,it)
            gt=truth[:,12:84,12:116].mean(axis=(1,2)) if isglobal else truth[:,point[1],point[0]]-global_shift
            native_est=after if isglobal else after+global_shift
            native_truth=truth[:,12:84,12:116].mean(axis=(1,2)) if isglobal else truth[:,point[1],point[0]]
            trajectory.append(dict(case=case,backend=backend,call=geo['call'],patch_yx=patch,center_xy=point,iteration=it,
                before_xy=before.tolist(),native_candidate_xy=candidates.tolist(),after_xy=after.tolist(),
                truth_residual_xy=gt.tolist(),native_accumulated_plus_global_xy=native_est.tolist(),
                truth_xy=native_truth.tolist(),truth_error_xy=(native_est-native_truth).tolist(),
                truth_vector_rms=float(np.sqrt(np.mean(np.sum((native_est-native_truth)**2,axis=1)))),
                conditional_updates={k:updated(before,s,cuda).tolist() for k,s in shifts.items()},
                neutrality_identity=str(meta.relative_to(root))))
            for f in range(n):
                row=dict(case=case,backend=backend,call=geo['call'],patch_yx=patch,iteration=it,frame=f+1,geometry=geo,
                    native_candidate_xy=candidates[f].tolist(),same_map_candidate_error_xy=(shifts['stored'][f]-candidates[f]).tolist(),
                    peaks={k:v[f] for k,v in peaks.items()},input_spectrum_sha256=sha(pathlib.Path(str(stem)+f'-i{it}-input.bin')),
                    map_abs_error=float(np.max(np.abs(maps[f]-conditional[f]))),
                    map_error_over_search_contrast=(float(np.max(np.abs(maps[f]-conditional[f])))/peaks['inverse_double'][f]['search_contrast'] if peaks['inverse_double'][f]['search_contrast'] else None),
                    conditional_shift_disagreement_xy={k:(s[f]-shifts['stored'][f]).tolist() for k,s in shifts.items() if k!='stored'},
                    candidate_boundary_truth_relative_error_xy=(after-gt)[f].tolist())
                rows.append(row)
    return dict(controls=controls(),rows=rows,trajectories=trajectory,
        limits=['Captured floats retain upstream preprocessing/forward FFT/state loss.',
                'Conditional alternatives reuse native previous state; they are not native trajectories or estimator floors.',
                'Affine/noisy point truth is descriptive, not a patch-correlation target.',
                'Full forward-double physical reference UNRUN; no known-template oracle or DC change.'])
if __name__=='__main__':
    if sys.argv[1]=='--controls':result=controls()
    else:result=analyze(pathlib.Path(sys.argv[1]))
    text=json.dumps(result,indent=2,allow_nan=False)+'\n'
    if len(sys.argv)>2:pathlib.Path(sys.argv[2]).write_text(text)
    else:print(text)
