# SPDX-License-Identifier: GPL-2.0-or-later
"""Round-2 offline helpers. Same pinned inputs/objective/peak rule; no native run."""
import ast
import hashlib
import json
from pathlib import Path
import sys
import numpy as np

R=Path(__file__).resolve().parents[1]
W5=R.parent
sys.path.insert(0,str(W5/'scripts'))
import common as C
PIX=C.PIX
sha=lambda b:hashlib.sha256(b).hexdigest()

def verify():
    C.verify()
    m=json.loads((R/'INPUTS.json').read_text())
    for rel,pin in m['files'].items():
        b=(W5/rel).read_bytes()
        assert sha(b)==pin['sha256'] and len(b)==pin['bytes'],rel
    return m

def rms(a): return float(np.sqrt(np.mean(np.sum(np.square(a),axis=-1))))

class Estimator:
    def __init__(self,nx=128,ny=96,weight='prod',map32=False):
        self.nx,self.ny=nx,ny
        self.kx=np.fft.fftfreq(nx)*nx; self.ky=np.fft.fftfreq(ny)*ny
        self.W=np.exp(-300*((self.ky[:,None]/ny)**2+(self.kx[None,:]/(nx//2+1 if weight=='prod' else nx))**2))
        self.search=min(50,nx//2-1,ny//2-1)
        self.indices=np.arange(-self.search,self.search+1)
        self.map32=map32
    def shift(self,F,c):
        return F*np.exp(-2j*np.pi*((self.kx/self.nx)[None,:]*c[0]+(self.ky/self.ny)[:,None]*c[1]))
    def peak(self,m):
        s=self.indices
        sub=m[np.ix_(s%self.ny,s%self.nx)]
        i=int(np.argmax(sub)); px,py=int(s[i%len(s)]),int(s[i//len(s)])
        v=float(m[py%self.ny,px%self.nx]); out=[]
        for vp,vn,p in [(m[py%self.ny,(px+1)%self.nx],m[py%self.ny,(px-1)%self.nx],px),
                        (m[(py+1)%self.ny,px%self.nx],m[(py-1)%self.ny,px%self.nx],py)]:
            vp,vn=float(vp),float(vn); d=vp+vn-2*v
            out.append(p-.5*(vp-vn)/d if abs(d)>1e-15 else float(p))
        return np.array(out)
    def update(self,F):
        total=F.sum(0)
        out=[]
        for f in range(len(F)):
            m=np.fft.ifft2((total-F[f])*np.conj(F[f])*self.W).real
            if self.map32:
                # Source CCF values use unnormalised inverse; multiplication before
                # float32 rounding is essential. Double maps differ by a constant scale.
                m=(m*(self.nx*self.ny)).astype(np.float32)
            out.append(self.peak(m))
        out=np.array(out); return out-out[0]
    def run(self,F0,iters=5,tol=.5,start=None,gain=1.,force=False,truth=None,keep_states=False):
        s=np.zeros((len(F0),2)) if start is None else np.array(start,float).copy()
        F=np.array([self.shift(f,c) for f,c in zip(F0,s)])
        history=[]; states=[s.copy()]; converged=False
        for k in range(1,iters+1):
            u=self.update(F); raw=rms(u)
            s+=gain*u
            for f in range(1,len(F)): F[f]=self.shift(F[f],gain*u[f])
            history.append([k,raw,rms(gain*u),None if truth is None else rms(s-truth)])
            if keep_states: states.append(s.copy())
            if raw<tol:
                converged=True
                if not force: break
        # Measure a further map update, rather than mistaking the last step for stationarity.
        final_update=self.update(F)
        out=dict(state=s,history=history,converged=history[-1][1]<tol,ever_under_tolerance=converged,endpoint_update=final_update,
                 endpoint_update_rms_px=rms(final_update),iterations=len(history))
        if keep_states: out['states']=np.array(states)
        return out

def fit(local,coords):
    n,nf,_=local.shape; xy=np.array(coords,float)
    obs=local-(1.5*local[:,:1]-.5*local[:,1:2])
    z=np.broadcast_to(np.arange(nf,dtype=float)+.5,(n,nf))
    A=C.basis(np.broadcast_to(xy[:,0:1]/128-.5,(n,nf)),np.broadcast_to(xy[:,1:2]/96-.5,(n,nf)),z).reshape(-1,18)
    cc,res,rank,sv=np.linalg.lstsq(A,obs.reshape(-1,2),rcond=None)
    assert np.isfinite(cc).all()
    return cc,dict(rank=int(rank),condition=None if sv[-1]==0 else float(sv[0]/sv[-1]),residual_sum_squares=res.tolist())

def pipeline(movie,local=True,iters=5,tol=.5,gain=1.,map32=False):
    nf,ny,nx=movie.shape
    e=Estimator(nx,ny,map32=map32)
    F=np.fft.fft2(movie.astype(float))/(nx*ny)
    gr=e.run(F,iters,tol,gain=gain)
    g=gr['state']
    if not local: return g,None,dict(global_run=serial(gr),patches=[])
    aligned=np.array([np.fft.ifft2(e.shift(F[f],g[f])).real*(nx*ny) for f in range(nf)])
    coeff,info=patch_fit(aligned,iters,tol,gain,map32)
    return g,coeff,dict(global_run=serial(gr),**info)

def patch_fit(movie,iters=5,tol=.5,gain=1.,map32=False):
    nf=movie.shape[0]; accepted=[]; coords=[]; patches=[]
    e=Estimator(42,32,map32=map32)
    for iy in range(3):
        for ix in range(3):
            win=movie[:,iy*32:(iy+1)*32,ix*42:(ix+1)*42]
            F=np.fft.fft2(win)/(42*32)
            rr=e.run(F,iters,tol,gain=gain)
            patches.append(dict(selector=[iy+1,ix+1],**serial(rr)))
            if rr['converged']:
                accepted.append(rr['state']);coords.append((ix*42+20,iy*32+15))
    if len(accepted)*nf<=18:
        return None,dict(patches=patches,fit=None,accepted_centres=coords,model_status='NULL_TOO_FEW_OBSERVATIONS')
    cc,fitinfo=fit(np.array(accepted),coords)
    return cc,dict(patches=patches,fit=fitinfo,accepted_centres=coords,model_status='FITTED')

def serial(o):
    return {k:(v.tolist() if isinstance(v,np.ndarray) else v) for k,v in o.items()}

def field_result(label,g,coeff,truth,movie=None,target=None,recipe=None):
    # Import only the four source-pinned W5 serialization/scoring definitions.
    source=(W5/'scripts/intervention.py').read_text()
    tree=ast.parse(source)
    nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('fmt','rounded','write_star','one')]
    env={k:getattr(C,k) for k in ['NX','NY','Q','PIX','ROI','read_motion_star','field','metrics','score','checker']}
    outdir=R/'results/star';outdir.mkdir(exist_ok=True)
    env.update(np=np,OUT=outdir,sha=sha)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),'W5[serialization definitions]','exec'),env)
    return env['one'](label,g,coeff,truth,movie,target,recipe)

def save(name,out):
    p=R/'results'/name; assert not p.exists(),str(p)
    out.update(python=sys.version,numpy=np.__version__,
        script_hashes={str(x.relative_to(R)):sha(x.read_bytes()) for x in sorted((R/'scripts').glob('*.py'))},
        input_manifest_sha256=sha((R/'INPUTS.json').read_bytes()))
    p.write_text(json.dumps(out,indent=1,allow_nan=False)+'\n')
