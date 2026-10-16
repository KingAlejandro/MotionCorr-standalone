#!/usr/bin/env python3
"""Correctness-only paired products; no elapsed-time measurements."""
import hashlib,json,os,pathlib,subprocess,sys,struct,shutil
ROOT=pathlib.Path('/home/ubuntu/fix183-20261016')
sys.path.insert(0,str(ROOT/'candidate/tools/profiling'))
from lib import identity
OUT=ROOT/'products'; OUT.mkdir(exist_ok=True)
LOG=ROOT/'logs'
manifest={'base_revision':'d7171b81','candidate_revision':(ROOT/'candidate.revision').read_text().strip(),'runs':[],'comparisons':[],'hashes':[]}
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
manifest['binaries']={str(p.relative_to(ROOT)):sha(p) for p in [ROOT/'base/build/motioncorr',ROOT/'candidate/build-release/motioncorr']}
manifest['inputs']={str(p.relative_to(ROOT)):sha(p) for p in [ROOT/'data/20170629_00021_frameImage.tiff',ROOT/'data/gain.mrc',ROOT/'data/synthetic_512x512_16frames.mrcs']}
def save(): (LOG/'exact-results.json').write_text(json.dumps(manifest,indent=2)+'\n')
for fixture in ['synthetic','tutorial']:
 for threads in [1,4]:
  for arm in ['base','candidate']:
   binary=ROOT/('base/build/motioncorr' if arm=='base' else 'candidate/build-release/motioncorr')
   tag=f'{fixture}-p5-j{threads}-{arm}'; output=OUT/tag
   movie=ROOT/('data/20170629_00021_frameImage.tiff' if fixture=='tutorial' else 'data/synthetic_512x512_16frames.mrcs')
   cmd=[str(binary),'--i',str(movie),'--o',str(output),'--use_own','--j',str(threads),'--angpix','0.885' if fixture=='tutorial' else '1','--voltage','300','--bfactor','150','--seed','1','--patch_x','5','--patch_y','5','--group_frames','5','--dose_weighting','--dose_per_frame','1.277','--save_noDW','--even_odd_split']
   if fixture=='tutorial': cmd+=['--gainref',str(ROOT/'data/gain.mrc')]
   env=dict(os.environ,OMP_NUM_THREADS=str(threads),OMP_DYNAMIC='FALSE',OMP_WAIT_POLICY='PASSIVE')
   # The driver and all children inherit CPUs 56-61; no timing lock.
   wrapped=cmd
   with (LOG/f'{tag}.log').open('w') as f: rc=subprocess.run(wrapped,stdout=f,stderr=subprocess.STDOUT,env=env).returncode
   manifest['runs'].append(dict(tag=tag,command=wrapped,exit_status=rc)); save(); assert rc==0
  a,b=[OUT/f'{fixture}-p5-j{threads}-{arm}' for arm in ['base','candidate']]
  result=identity.compare_trees(str(a),str(b),expect_mrc=4)
  manifest['comparisons'].append(dict(fixture=fixture,threads=threads,**result)); save(); assert result['identical']
  for rel in identity.inventory(str(a)):
   if pathlib.Path(rel).suffix not in ['.mrc','.mrcs','.star']: continue
   row={'fixture':fixture,'threads':threads,'file':rel}
   for arm,root in [('base',a),('candidate',b)]:
    data=(root/rel).read_bytes()
    if pathlib.Path(rel).suffix in ['.mrc','.mrcs']:
     nsymbt=struct.unpack('<i',data[92:96])[0]
     row[arm+'_payload_sha256']=hashlib.sha256(data[1024+nsymbt:]).hexdigest()
     data=identity.normalise_mrc_header(data[:1024])+data[1024:]
    else: data=identity.normalise(data,str(root))
    row[arm+'_canonical_sha256']=hashlib.sha256(data).hexdigest()
   assert row['base_canonical_sha256']==row['candidate_canonical_sha256']; manifest['hashes'].append(row)
  save()
# Corrupt one payload byte in a private copy; require the real comparator to fail.
a=OUT/'synthetic-p5-j1-base'; negative=OUT/'negative-payload'; shutil.copytree(OUT/'synthetic-p5-j1-candidate',negative)
# Re-root textual products so only the deliberate payload mutation differs.
for q in negative.rglob('*'):
 if q.is_file() and q.suffix not in ['.mrc','.mrcs','.pdf']:
  q.write_bytes(q.read_bytes().replace(str(OUT/'synthetic-p5-j1-candidate').encode(),str(negative).encode()))
p=next(negative.rglob('*.mrc')); data=bytearray(p.read_bytes()); offset=1024+struct.unpack('<i',data[92:96])[0]; data[offset]^=1; p.write_bytes(data)
result=identity.compare_trees(str(a),str(negative),expect_mrc=4)
manifest['negative_control']=dict(mutation='xor first MRC payload byte with 1',file=str(p),comparator_exit_status=1 if not result['identical'] else 0,**result)
save(); assert not result['identical']
assert len(result['differences'])==1 and 'payload differs' in result['differences'][0]['difference']
print('PASS four strict 5x5 tutorial/synthetic j1/j4 product pairs; payload mutation rejected')
