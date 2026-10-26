import pathlib,sys,os,subprocess,json,numpy as np,tifffile
root=pathlib.Path('/home/ubuntu/mc-km-truth-20261021');sys.path[:0]=[str(root/'v2/test-data'),str(root/'v2/tools')]
import generate_realistic_motion as gen
import check_realistic_motion as check
from generate_known_motion_fixture import STAR_TEMPLATE
r=gen.recipe(control='translation',nx=512,ny=384,frames=5,texture_rms=.15)
p=root/'controls/translation/movie.mrcs';a=np.memmap(p,dtype='<f4',mode='r',offset=1024,shape=(5,384,512))
rows=[]
for label in ['mrc','tiff-correct','tiff-row-mutant']:
 d=root/'controls'/label;d.mkdir(exist_ok=False)
 if label=='mrc': (d/'movie.mrcs').symlink_to(p);movie='movie.mrcs'
 else:
  movie='movie.tiff';tifffile.imwrite(d/movie,a[:,::-1,:] if label=='tiff-correct' else a,photometric='minisblack',metadata=None)
 (d/'input.star').write_text(STAR_TEMPLATE.format(pixel_size=.885,voltage=300.,movie=movie))
 out=root/'controls'/(label+'-native')
 env=os.environ|dict(MC_DIAG_CCF_DC='both',MC_DIAG_MODEL_OUT=str(root/'controls'/(label+'.runtime.json')),OMP_NUM_THREADS='8')
 cmd=['taskset','-c','56-63',str(root/'diag-build/motioncorr'),'--i','input.star','--o',str(out),'--use_own','--j','8','--patch_x','1','--patch_y','1','--bin_factor','1','--skip_defect','--skip_logfile']
 with (root/'controls'/(label+'.stdout')).open('w') as f: rc=subprocess.run(cmd,cwd=d,env=env,stdout=f,stderr=subprocess.STDOUT).returncode
 if rc:raise RuntimeError(rc)
 runtime=json.loads((root/'controls'/(label+'.runtime.json')).read_text())
 metric=check.evaluate(r,runtime)
 row=dict(label=label,exit=rc,argv=cmd,input_sha256=gen.digest(d/movie),metrics=metric)
 rows.append(row);print(label,metric['field']['px'],flush=True)
(root/'controls/orientation.json').write_text(json.dumps(rows,indent=2)+'\n')
