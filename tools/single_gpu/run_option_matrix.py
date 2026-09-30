#!/usr/bin/env python3
"""Exact current-main/candidate products in scoped one-movie option arms."""
import argparse,importlib.util,json,os,struct,subprocess,sys
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--baseline',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--source',type=Path,required=True);p.add_argument('--input-dir',type=Path,required=True);p.add_argument('--root',type=Path,required=True);a=p.parse_args();a.root.mkdir(parents=True,exist_ok=False)
spec=importlib.util.spec_from_file_location('cmp',a.source/'docs/issue85_laneC/compare_output_trees.py');cmp=importlib.util.module_from_spec(spec);sys.modules[spec.name]=cmp;spec.loader.exec_module(cmp)
manifest=json.loads((a.source/'docs/issue85_laneC/tutorial_24_movie_manifest.json').read_text());movie=manifest['movies'][0];stem=Path(movie).stem
inp=a.root/'input';inp.mkdir();(inp/'Movies').symlink_to((a.input_dir/'Movies').resolve(),target_is_directory=True)
lines=(a.input_dir/'movies.star').read_text().splitlines();selected=[q for q in lines if not q.strip().startswith('Movies/') or q.split()[0]==movie];(inp/'movies.star').write_text('\n'.join(selected)+'\n')
base=['--i','movies.star','--use_own','--dose_weighting','--dose_per_frame','1.277','--patch_x','5','--patch_y','5','--bfactor','150','--gainref','Movies/gain.mrc','--seed','1','--gpu','0','--j','6','--max_io_threads','6','--ingest','nvcomp']
rows=[('local5',[],[]),('global1',['--patch_x','1','--patch_y','1'],[]),('local3',['--patch_x','3','--patch_y','3'],[]),('selected',['--first_frame_sum','3','--last_frame_sum','20'],[]),('groups3',['--group_frames','3'],[]),('no_gain',[],[]),('even_odd',['--even_odd_split'],['_EVN','_ODD']),('save_noDW',['--save_noDW'],['_noDW']),('power_spectrum',['--grouping_for_ps','4','--ps_size','512'],['_PS']),('no_dose',[],[])]
records=[]
for name,extra,products in rows:
 opts=list(base)
 if name=='no_gain':del opts[opts.index('--gainref'):opts.index('--gainref')+2]
 if name=='no_dose':del opts[opts.index('--dose_weighting')];del opts[opts.index('--dose_per_frame'):opts.index('--dose_per_frame')+2]
 expected_mrc={f'Movies/{stem}{suffix}.mrc' for suffix in ['',*products]};expected_star={f'Movies/{stem}.star','corrected_micrographs.star'};trees=[]
 for arm,binary in [('baseline',a.baseline),('candidate',a.candidate)]:
  out=a.root/(name+'-'+arm);out.mkdir();cmd=[str(binary.resolve()),*opts,*extra,'--o',str(out.resolve())+'/'];r=subprocess.run(cmd,cwd=inp,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=180);(a.root/(name+'-'+arm+'.log')).write_text(r.stdout)
  assert r.returncode==0,f'{name}/{arm}: failed {r.returncode}'
  assert 'Unrecognised' not in r.stdout and 'WARNING:' not in r.stdout,f'{name}/{arm}: warning'
  files={str(q.relative_to(out)):q for q in out.rglob('*') if q.is_file()}
  assert {q for q in files if q.endswith('.mrc')}==expected_mrc, f'{name}: requested MRC inventory'
  assert {q for q in files if q.endswith('.star')}==expected_star, f'{name}: STAR inventory'
  digests={}
  for rel,q in files.items():
   if q.suffix=='.mrc':
    shape=[512,512,1] if rel.endswith('_PS.mrc') else manifest['expected_shape_xyz'];info=cmp.validate_mrc(q,shape);digests[rel]=[info.header_sha256,info.extended_sha256,info.payload_sha256]
   elif q.suffix.lower()=='.pdf':digests[rel]='PDF inventory only'
   else:
    raw=q.read_bytes()
    if q.suffix.lower() in cmp.TEXT_SUFFIXES:raw=cmp._normalise_text(q,out,raw)
    import hashlib
    digests[rel]=hashlib.sha256(raw).hexdigest()
  trees.append(digests)
 assert trees[0]==trees[1],f'{name}: non-PDF tree differs '+str([q for q in trees[0] if trees[0][q]!=trees[1].get(q)])
 records.append({'case':name,'status':'PASS','mrc_inventory':sorted(expected_mrc),'star_inventory':sorted(expected_star),'scope':'full normalized MRC headers/extended/pixels and complete non-PDF tree','digests':trees[0]});(a.root/'result.json').write_text(json.dumps(records,indent=2));print(name,'PASS',flush=True)
# Preserve the actual resident→host retry contract at the changed native symbol.
out=a.root/'retry';out.mkdir();binary=a.candidate.parent/'motioncorr_retry_caller';r=subprocess.run([str(binary),*base,'--o',str(out.resolve())+'/'],cwd=inp,env=dict(os.environ,MC_RETRY_CALLER='1'),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=180);(a.root/'retry.log').write_text(r.stdout)
assert r.returncode==0 and all(q in r.stdout for q in ['injected nonconvergence with nonzero shifts','actual runner reset both vectors','second native alignment succeeded']),'production retry caller boundary failed'
records.append({'case':'actual-resident-retry','status':'PASS','scope':'test-only nonconvergence interposition; actual host retry zero reset and native convergence'})
(a.root/'result.json').write_text(json.dumps(records,indent=2));print('OPTION_MATRIX_PASS')
