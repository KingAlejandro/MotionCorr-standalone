import sys,json,pathlib,subprocess
s=pathlib.Path('/mnt/clathrin/alex-motioncorr-peakfit');mv=sys.argv[1];g=int(sys.argv[2]);primary=lambda d:next((d/'Movies').glob('*.mrc'))
a=s/'runs'/('%s-p%d-refCPU'%(mv,g));b=s/'runs'/('%s-p%d-parent'%(mv,g))
r=json.loads(subprocess.check_output([str(s/'tools/mc-metrics'),str(primary(a)),str(primary(b))],text=True))
old=next(r for r in json.load(open(s/'pr255-control.json')) if r['movie']==mv and r['grid']==g)['pr254']
r['pr255_rel_rmse']=old;r['matches_7_digits']=format(r['relative_rmse'],'.6e')==format(old,'.6e')
json.dump(r,open(b/'control-pr255.json','w'),indent=1);print(mv,g,r,flush=True)
assert r['matches_7_digits'],'#255 control did not reproduce; retain as a failed venue control, do not pool'
