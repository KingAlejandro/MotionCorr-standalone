"""Scoring-only patch-mean and variation supplement; run AFTER stage1 seal."""
from pathlib import Path
import json,sys
import numpy as np
sys.path.insert(0,str(Path(__file__).parent))
import score

inp,out=map(Path,sys.argv[1:3])
candidates=json.loads(inp.read_text())
truth=np.load(score.TRUTH,allow_pickle=False)
rows=[]
for cy in [79,47]:
    p=score.CAP/('patch-62-%d'%cy)
    geom=json.loads((p/'patch.json').read_text())
    x0,x1,y0,y1=geom['extents_xy_halfopen']
    support=truth[:,y0:y1,x0:x1,:]
    mean=support.mean(axis=(1,2))
    global_=score.array(p,'global-shifts')
    local_mean=mean-global_
    center=truth[:,cy,62,:]-global_
    deviation=support-mean[:,None,None,:]
    spread=[score.metrics(d.reshape(-1,2)) for d in deviation]
    comparisons=[]
    for row in candidates:
        if row['patch_y']==cy:
            s=np.asarray(row['shifts'])
            comparisons.append({'label':row['label'],'selected':row.get('selected',False),
                                'error_vs_patch_mean_px':score.metrics(s-local_mean)})
    rows.append({'patch_y':cy,'extents_xy_halfopen':[x0,x1,y0,y1],
                 'mean_local_truth_px':local_mean.tolist(),'center_minus_mean_px':(center-local_mean).tolist(),
                 'within_patch_spread_per_frame_px':spread,'J_patch_mean_truth':score.objective(p,local_mean),
                 'comparisons':comparisons})
out.write_text(json.dumps({'rows':rows,'status':'SCORING_ONLY rigid-patch approximation diagnostic; no floor subtraction'},indent=2,allow_nan=False)+'\n')
