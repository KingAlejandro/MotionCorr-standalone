"""Pre-native, truth-blind bound from pinned STAR observations and B2 conditioning."""
import sys,json,hashlib
from pathlib import Path
sys.dont_write_bytecode = True
import numpy as np
w8=Path('/Users/alex.konstantinov/.t3/worktrees/MotionCorr/t3-6c3dca0d/docs/post_rc0/s1/first_divergence_20261022/w8_intercept_refit_20261026/scripts')
sys.path.insert(0,str(w8))
from w8_refit import read_star
from w8_fit import design,conditioning
root=Path(sys.argv[1]);out={}
for name in ('dose1-s01','dose05-s00','dose4-s00','pedestal32-s00'):
 p=root/name/'F/output/movie.star';nx,ny,g,keys,obs=read_star(p)
 row=dict(star_sha256=hashlib.sha256(p.read_bytes()).hexdigest())
 if len(keys):
  u,v=keys[:,0]/nx-.5,keys[:,1]/ny-.5
  A=design(u,v,40,'B2');inverse=np.linalg.pinv(A)[:18]
  # ||delta coefficients_j|| <= ||inverse_j||_1 * 5e-6, from the pinned writer's worst signed fixed precision.
  # Triangle bound valid at EVERY point |u|,|v|<=.5 and EVERY f<=39, including full border.
  weights=(np.array([1,.5,.25,.5,.25,.25])[:,None]*np.array([39,39**2,39**3])[None,:]).ravel()
  axis_bound=float(weights@np.abs(inverse).sum(axis=1)*5e-6)
  row.update(conditioning=conditioning(u,v,40,'B2'),observation_abs_max=float(np.abs(obs).max()),per_axis_bound_px=axis_bound,vector_bound_px=2**.5*axis_bound,
             threshold_px=2**.5*axis_bound+1e-8)
 else:row.update(status='NO_LOCAL',threshold_px=0)
 out[name]=row
print(json.dumps(out,indent=2))
