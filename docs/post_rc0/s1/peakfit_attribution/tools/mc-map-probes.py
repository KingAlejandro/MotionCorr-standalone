import pathlib,json,os,subprocess,sys
s=pathlib.Path('/mnt/clathrin/alex-motioncorr-peakfit');mode=sys.argv[1];worker=int(sys.argv[2]);n=3 if mode=='cpu' else 2
requests=json.load(open(s/'map-requests.json'))
for j,r in enumerate(requests):
 if j%n!=worker:continue
 mv,g=r['movie'],r['grid'];sw=pathlib.Path('/mnt/clathrin/alex-motioncorr-s1/sweep')
 if not (sw/'runs'/('%s-p%d-F-cuda'%(mv,g))/'run.json').exists():sw=s/'extra/sweep'
 e=dict(os.environ,S13C_ROOT=str(s),S13C_SWEEP=str(sw),LANE_GPU=['0','2'][worker] if mode=='gpu' else '0')
 if mode=='cpu':e.update(MC_CPU_MASK=['32-39','40-47','48-55'][worker],MC_CPU_LOCK='/tmp/motioncorr-peakfit-mapcpu%d.lock'%worker)
 for arm in (['cpu'] if mode=='cpu' else r['arms']):
  label='%s-p%d-map-%s'%(mv,g,arm);d=s/'runs'/label;(d/'maps').mkdir(parents=True,exist_ok=True)
  source='4837b210' if arm=='cpu' else '9a834380';e['MC_SOURCE_SHA']=source
  cmd=['/usr/bin/python3',str(s/'tools/run_c.py'),'--sweep-label','%s-p%d-F-cuda'%(mv,g),'--label',label,'--binary',str(s/('build-A0' if arm=='cpu' else 'build-A1')/'motioncorr'),'--env','MC_DIAG_CCF={out}/ccf.txt','--env','MC_DIAG_GLOBAL_SHIFTS_OUT={out}/global.txt','--env','MC_DIAG_MAPS={out}/maps','--env','MC_DIAG_MAP_PATCHES='+';'.join(r['patches'])]
  if arm!='cpu':cmd+=['--gpu']
  if arm=='A2':cmd+=['--env','MC_DIAG_ZERO_CCF_DC=1']
  subprocess.run(cmd,env=e,check=True)
  ref=s/'runs'/('%s-p%d-%s'%(mv,g,arm))
  if arm=='cpu':
   ref=pathlib.Path('/mnt/clathrin/alex-motioncorr-s1/sweep/runs')/('%s-p%d-F-cpu'%(mv,g))
   if not ref.exists():ref=s/'runs'/('%s-p%d-refCPU'%(mv,g))
  p=subprocess.run(['/usr/bin/python3',str(s/'tools/identity.py'),str(ref),str(d)],capture_output=True,text=True,check=True)
  (d/'identity-parent.json').write_text(p.stdout)
print('DONE')
