import pathlib as P,json,hashlib,tarfile,re,subprocess,difflib,collections,math,os
W=P.Path(__file__).parent; D=W/'exact/docs/post_rc0/issue268_quality_prototype_20261023'; E=D/'evidence-2f434253-4gpus'
sha=lambda b:hashlib.sha256(b).hexdigest()
F={os.fsencode('campaign/'+str(p.relative_to(E/'campaign'))):p.read_bytes() for p in (E/'campaign').rglob('*') if p.is_file()}
ordinary=len(F)
with tarfile.open(E/'nonutf8_named_files.tar.gz') as t:
 for m in t.getmembers():
  assert m.isfile() and not m.name.startswith('/') and '..' not in m.name.split('/')
  F[os.fsencode(m.name)]=t.extractfile(m).read()
H={}
for l in (E/'receipts/campaign_files.sha256').read_bytes().splitlines():
 digest,name=l.split(b'  ',1); assert len(digest)==64 and name not in H; H[name]=digest.decode()
assert len(H)==1113
for n,b in F.items(): assert H[n]==sha(b),(n,'digest')
print('RETAINED',ordinary,'TAR',len(F)-ordinary,'HASH_ROWS',len(H),'HASH_ONLY',len(H)-len(F))
def strict(b):
 def pairs(p):
  d={}
  for k,v in p:
   assert k not in d,('duplicate',k); d[k]=v
  return d
 return json.loads(b.decode('utf8'),object_pairs_hook=pairs,parse_constant=lambda s:(_ for _ in ()).throw(ValueError(s)))
def get(n): return F[b'campaign/'+n]
def J(n): return strict(get(n))
def txt(v): return v.encode() if isinstance(v,str) else bytes.fromhex(v['non_utf8_bytes_hex'])
manifest=J(b'manifest.json'); revision=manifest['revision']; binary=manifest['binaries']['v2']['sha256']
assert revision=='2f43425340b7525e85288e7b35ee109dd3a4c3cc' and manifest['skipped']==[]
assert len(manifest['runs'])==16
expected_tree=subprocess.check_output(['git','rev-parse',revision+'^{tree}'],text=True).strip(); assert expected_tree in (E/'receipts/sources.txt').read_text()
assert not subprocess.check_output(['git','diff','1215febd',revision,'--','src','CMakeLists.txt'])
assert not subprocess.check_output(['git','diff',revision,'e9c1e9b4','--','src','CMakeLists.txt'])
for r in manifest['runs']:
 q=r['id'].encode(); rec=J(q+b'/run.json'); assert rec['argv']==r['argv'] and rec['exit']==r['exit']
 assert rec['argv'][:3]==['taskset','-c','14']; assert rec['argv'][3]==manifest['binaries'][rec['binary']]['path']; assert rec['argv'][rec['argv'].index('--j')+1]=='1'
 assert rec['exit']==(1 if q in (b'Q11',b'Q12') else 0)
assert sha((E/'driver_v2.sh').read_bytes())==(E/'launch_inputs.sha256').read_text().splitlines()[1].split()[0]
# Fixtures are identity-checked against the exact tracked generation record, without generating movies.
record=strict(subprocess.check_output(['git','show',revision+':test-data/motion_diagnostics_v2/GENERATION_RECORD.json']))
for case in ('zero','integer','fractional','affine','flat','noisy'):
 for name,digest in record['cases'][case]['files'].items(): assert manifest['fixtures'][name]==digest
print('IDENTITY tree',expected_tree,'binary',binary,'campaign argv/exits and fixture record PASS')
sidecount=summarycount=patchcount=0; ids=set(); details=[]
for n,b in sorted(F.items()):
 if not n.endswith(b'.quality.json') or n.startswith(b'campaign/Q9/'): continue # Q9 deliberately tampered; checked separately
 d=strict(b); q=n.split(b'/')[1]; movie=txt(d['movie']['path']); rec=J(q+b'/run.json'); argv=rec['argv'][3:]
 assert d['schema']=='motioncorr-quality-prototype/1'
 ident=d['identity']; assert ident['configured_source_revision']==revision and ident['configured_source_dirty']=='false' and ident['binary_sha256']==binary
 assert ident['argv']==argv and ident['backend']=='cpu' and ident['gpu_id']==-1
 ids.add(ident['run_id'])
 assert d['movie']['bytes']==1024+128*96*5*4
 assert d['movie']['sha256']==H[b'campaign/'+q+b'/'+movie]
 stem=movie.rsplit(b'.',1)[0]; log=get(q+b'/out/'+stem+b'.log').decode('utf8','surrogateescape')
 # Independently parse global and each patch section; exact 6-significant-digit printed values.
 gtext=log.split('Global alignment:\n',1)[1].split('Local alignments:',1)[0]
 it=re.findall(r' Iteration (\d+): RMSD = (\S+) px',gtext)
 g=d['global_alignment']; maxit=int(argv[argv.index('--max_iter')+1]) if '--max_iter' in argv else 5
 assert g['route']=='cpu' and g['max_iter']==maxit and g['tolerance_px']==.5 and g['iterations']==len(it)
 if it:
  assert float(format(g['final_incremental_rmsd_px'],'.6g'))==float(it[-1][1])
  conv=g['final_incremental_rmsd_px']<.5; assert g['converged']==conv and g['solver_returned']==conv and g['state']==('converged' if conv else 'iteration_limit')
 loc=d['local_alignment']; patches=loc['patches']; sections=re.split(r'Patch \((\d+), (\d+)\): (\d+) / (\d+)[^\n]*\n',log)
 assert len(patches)==(len(sections)-1)//5
 for i,p in enumerate(patches):
  iy,ix,idx,planned,body=sections[1+5*i:6+5*i]; assert (p['iy'],p['ix'],p['index'])==(int(iy),int(ix),int(idx))
  its=re.findall(r' Iteration (\d+): RMSD = (\S+) px',body); assert len(p['attempts'])==1
  a=p['attempts'][0]; assert a['route']=='cpu' and a['kind']=='first' and a['max_iter']==maxit and a['tolerance_px']==.5 and a['iterations']==len(its)
  assert float(format(a['final_incremental_rmsd_px'],'.6g'))==float(its[-1][1])
  conv=a['final_incremental_rmsd_px']<.5; assert a['converged']==conv and a['solver_returned']==conv and p['final']==('converged' if conv else 'dropped') and p['device_preparation_declined']==False
 finals=collections.Counter(p['final'] for p in patches)
 assert [loc[k] for k in ('converged_patches','dropped_patches','interrupted_patches')]==[finals[k] for k in ('converged','dropped','interrupted')]
 assert loc['patches_recorded']==len(patches) and loc['solver_attempts']==len(patches) and loc['same_input_retries']==loc['device_preparation_declined']==0
 m=d['local_model']; fit=re.search(r'Polynomial fit RMSD: X = (\S+) px Y = (\S+) px',log)
 if patches:
  assert m['observations']==5*finals['converged'] and m['min_observations_exclusive']==18
 if fit:
  assert [float(format(m[k],'.6g')) for k in ('fit_rmsd_x_px','fit_rmsd_y_px')]==list(map(float,fit.groups())) and m['fit_rmsd_limit_px']==10 and m['distortion_limit_px']==3
 if d['publication']['state']=='published':
  for k in ('star','micrograph'):
   prod=d['products'][k]; assert prod['sha256']==H[b'campaign/'+q+b'/'+txt(prod['path'])]
  star=get(q+b'/'+txt(d['products']['star']['path'])); assert (b'data_local_motion_model' in star)==(m['state']=='retained')
 else:
  assert q==b'Q12' and movie==b'in/integer.mrcs' and d['publication']['reason']=='product_write_failed' and d['products']=={'star':None,'micrograph':None}
 assert d['motion_identifiability']==d['peak_validity']=='not_assessed'
 sidecount+=1; patchcount+=len(patches); details.append([n.decode('utf8','backslashreplace'),g['state'],m['state']])
for n,b in sorted(F.items()):
 if not n.endswith(b'/quality_summary.json'): continue
 s=strict(b); q=n.split(b'/')[1]; entries=s['movies']; rec=J(q+b'/run.json')
 assert s['identity']['argv']==rec['argv'][3:] and s['identity']['binary_sha256']==binary and s['identity']['configured_source_revision']==revision
 membership=get(q+b'/in/batch.star').split(b'_rlnOpticsGroup #2\n')[-1].splitlines(); membership=[v.rsplit(b' ',1)[0] for v in membership if v.strip()]
 assert list(map(lambda e:txt(e['movie']),entries))==membership
 counts={k:collections.Counter(e[k] for e in entries if k=='publication' or e['source']!='unknown_legacy') for k in ('global_alignment','local_model','publication')}
 for k,v in counts.items(): assert dict(v)==s['counts'][k]
 assert s['counts']['movies']==len(entries)
 for e in entries:
  if e['sidecar']['sha256'] is not None: assert e['sidecar']['sha256']==sha(get(q+b'/'+txt(e['sidecar']['path'])))
  if e['output_root_collision']: assert e['publication']=='ambiguous_output_root' and e['sidecar']['path'] is None
 assert s['quality_evidence_complete']==not_any if False else True # explicit completeness below
 legacy=sum(e['source']=='unknown_legacy' for e in entries); collisions=sum(e['output_root_collision'] for e in entries); fail=sum(e['sidecar']['write_failed'] for e in entries)
 assert (legacy,collisions,fail)==tuple(s['counts'][k] for k in ('unknown_legacy','output_root_collisions','sidecar_write_failures'))
 assert s['quality_evidence_complete']==(legacy==collisions==fail==0)
 summarycount+=1
resume=J(b'Q9/out/quality_summary.json'); assert [(e['source'],e['reason']) for e in resume['movies']]==[('resumed_sidecar',None) if txt(e['movie'])==b'in/flat.mrcs' else ('unknown_legacy','sidecar_invalid') for e in resume['movies']]
print('INDEPENDENT reports',sidecount,'patches',patchcount,'summaries',summarycount,'unique current-run ids',len(ids),'PASS')
# Per-movie logs, strictly enumerating every retained pair and preserving solver lines.
drop=re.compile(rb'^(Full movie wall time:|in: .*, line \d+$|\d+\s+\S+\s+0x[0-9a-f]+ )|\(\+0x[0-9a-f]+\) \[0x[0-9a-f]+\]$')
normalize=lambda b:b'\n'.join(l for l in b.split(b'\n') if not drop.search(l))
pairs=[(b'Q1',x) for x in (b'Q2',b'Q3',b'Q4',b'Q13',b'Q16')]+[(b'Q5',b'Q6'),(b'Q7',b'Q8'),(b'Q11',b'Q12'),(b'Q14',b'Q15')]; count=0
for a,z in pairs:
 for n,b in F.items():
  prefix=b'campaign/'+a+b'/out/'
  if n.startswith(prefix) and n.endswith(b'.log'):
   twin=b'campaign/'+z+b'/out/'+n[len(prefix):]; assert normalize(b)==normalize(F[twin]),(n,twin); count+=1
print('NORMALIZED LOG PAIRS',count,'PASS')
for b,total,passed in [('v1',90,89),('v2',92,91)]:
 log=(E/f'receipts/ctest-{b}.log').read_text(); listings=(E/f'receipts/ctest-{b}-list.txt').read_text()
 actual=re.findall(r'\d+/\d+ Test\s+#\d+: (\S+)\s+.*?(Passed|\*\*\*Skipped|\*\*\*Failed)',log)
 assert len(actual)==total and collections.Counter(v for _,v in actual)=={'Passed':passed,'***Skipped':1}
 assert [n for n,v in actual if v=='***Skipped']==['CompressedMrcStatus_bz2']; assert f'Total Tests: {total}' in listings
 print('CTEST',b,dict(collections.Counter(v for _,v in actual)))
# Static OFF stripping independently, no preprocessing/build.
def off(text):
 stack=[]; out=[]
 for line in text.splitlines(True):
  s=line.strip()
  if re.match(r'#\s*ifdef\s+MC_EXPERIMENTAL_QUALITY_REPORT\b',s): stack.append(False); continue
  if re.match(r'#\s*if(n?def)?\b',s): stack.append(None)
  elif re.match(r'#\s*else\b',s) and stack and stack[-1] is not None: stack[-1]=not stack[-1]; continue
  elif re.match(r'#\s*endif\b',s):
   v=stack.pop()
   if v is not None: continue
  if False not in stack: out.append(line)
 assert not stack
 return ''.join(out)
for f in ('src/motioncorr_runner.cpp','src/motioncorr_runner.h','src/acc/cuda/cuda_alignpatch.cu'):
 base=subprocess.check_output(['git','show','bbf24607:'+f],text=True); src=(W/'exact'/f).read_text()
 diff=''.join(difflib.unified_diff(base.splitlines(True),off(src).splitlines(True),fromfile='base',tofile='OFF '+f))
 (W/(f.replace('/','_')+'.off.diff')).write_text(diff)
print('OFF source residual diffs retained')
(W/'independent_fields.json').write_text(json.dumps(details,indent=2))
(W/'audit_summary.json').write_text(json.dumps(dict(retained=ordinary,tar=len(F)-ordinary,hash_rows=len(H),hash_only=len(H)-len(F),sidecars=sidecount,patches=patchcount,summaries=summarycount,logpairs=count),indent=2))
print('AUDIT PASS')
