#!/usr/bin/env python3
"""Retain one high-pedestal seed for CCF range and double-offset neutrality controls."""
import json,os,pathlib,shutil,subprocess,time
ROOT=pathlib.Path('/home/ubuntu/mc-km-truth-20261021')

def main():
    name='pedestal32-s00';source=ROOT/'fixtures'/name;deadline=time.time()+7200
    while not (source/'RECEIPT.json').exists():
        if time.time()>deadline:raise TimeoutError('stage fixture wait')
        time.sleep(2)
    stage=ROOT/'stage-control';stage.mkdir(exist_ok=False)
    os.link(source/'movie.mrcs',stage/'movie.mrcs')
    for n in ['input.star','RECEIPT.json']:shutil.copyfile(source/n,stage/n)
    rows=[]
    for label,dc,double in [('none','none',False),('both','both',False),('double','none',True),('double-both','both',True)]:
        out=stage/label;out.mkdir()
        env=os.environ|dict(OMP_NUM_THREADS='8',MC_DIAG_CCF_DC=dc,MC_DIAG_CCF_DOUBLE='1' if double else '0',
                            MC_DIAG_MODEL_OUT=str(out/'runtime.json'),MC_DIAG_CCF=str(out/'ccf.txt'))
        cmd=['taskset','-c','56-63',str(ROOT/'diag-build/motioncorr'),'--i','input.star','--o',str(out/'output'),
             '--use_own','--j','8','--patch_x','5','--patch_y','5','--group_frames','1','--bin_factor','1',
             '--seed','1','--skip_defect','--save_noDW','--first_frame_sum','1','--last_frame_sum','40',
             '--skip_logfile','--ingest','float']
        with (out/'stdout.log').open('w') as f:rc=subprocess.run(cmd,cwd=stage,env=env,stdout=f,stderr=subprocess.STDOUT).returncode
        rows.append(dict(label=label,argv=cmd,exit=rc))
        (stage/'runs.json').write_text(json.dumps(rows,indent=2)+'\n')
        if rc:raise RuntimeError('stage process failure')
    (stage/'DONE').write_text('complete\n')

if __name__=='__main__':main()
