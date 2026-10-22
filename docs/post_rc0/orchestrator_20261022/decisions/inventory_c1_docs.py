import collections,hashlib,json,pathlib,subprocess
R=pathlib.Path('/Users/alex.konstantinov/.t3/worktrees/MotionCorr/work-272-evaluator-contract-20261022');P=pathlib.Path(__file__).parent
head='e77a51a220cb0d91f4ac3c7fac211876d0c6833f';base='3691374061f782bc84531fd1c79d017ddcb5a7c2'
def git(*a):return subprocess.check_output(['git',*a],cwd=R)
paths=git('diff','--name-only','--diff-filter=ACMR',base,head,'--','docs/').decode().splitlines();tree={}
for line in git('ls-tree','-r','-l',head,'docs/').decode().splitlines():
 meta,path=line.split('\t');mode,typ,oid,size=meta.split();tree[path]={'path':path,'oid':oid,'bytes':int(size)}
rows=[tree[p] for p in paths];archive=[r for r in rows if r['path'].endswith(('.gz','.tgz','.tar','.zip','.xz','.bz2','.zst'))];by={}
for r in rows:
 key='/'.join(r['path'].split('/')[:4]);g=by.setdefault(key,{'files':0,'logical_bytes':0});g['files']+=1;g['logical_bytes']+=r['bytes']
old=json.loads((P/'M2_c1_docs_inventory.json').read_text());d={'kind':'M2 current committed C1 tree inventory; no retention decision/deletion','candidate':head,'main':base,'changed_doc_files':len(rows),'changed_logical_bytes':sum(r['bytes'] for r in rows),'changed_unique_blob_bytes':sum({r['oid']:r['bytes'] for r in rows}.values()),'bulk_archive_files':len(archive),'bulk_archive_logical_bytes':sum(r['bytes'] for r in archive),'largest_archives':sorted(archive,key=lambda r:r['bytes'],reverse=True),'groups':dict(sorted(by.items(),key=lambda kv:kv[1]['logical_bytes'],reverse=True)),'excluded_integration_packet_checks':old['excluded_integration_packet_checks'],'decision':'UNDECIDED; no file removed and no retention policy adopted'}
for n,v in d['excluded_integration_packet_checks'].items():
 v['unique_doc_paths_in_c1']=[p for p in git('diff','--name-only','--diff-filter=A',base,v['head'],'--','docs/').decode().splitlines() if p in tree and p not in git('ls-tree','-r','--name-only',base,'docs/').decode().splitlines() and ((n=='273' and '/parallel_20261022/numerics/' in p) or (n=='274' and '/integration_20261022/' in p))]
 assert not v['unique_doc_paths_in_c1'],v
(P/'M2_c1_docs_inventory_e77a51a2.json').write_text(json.dumps(d,indent=2)+'\n');print(json.dumps({k:v for k,v in d.items() if k not in ('groups','largest_archives')},indent=2))
