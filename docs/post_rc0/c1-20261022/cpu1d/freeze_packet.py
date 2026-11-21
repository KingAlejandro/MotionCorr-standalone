#!/usr/bin/env python3
"""Export a new, exclusive cpu1d packet only from committed Git blobs.
usage: freeze_packet.py REPO COMMITTED_STARTUP_SHA NEW_PACKET_DIR
Never executes qualification stages or numerical helpers.
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path
repo, rev, out = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
base = 'docs/post_rc0/c1-20261022/'
oldrev = '67beb5f59382a74bbc64b10bfa488ab3d549dc0c'
sha = lambda b: hashlib.sha256(b).hexdigest()
def git(*a):
    return subprocess.check_output(['git','-C',str(repo),*a])
def blob(r,p):
    return git('show',r+':'+p)
def store(p,b):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_bytes(b)
out.mkdir()
oldm = json.loads(blob(rev,base+'cpu1c/freeze/cpu1c-manifest.json'))
paths=git('ls-tree','-r','--name-only',oldrev,base).decode().splitlines()
oldblobs={p:blob(oldrev,p) for p in paths}
provenance={}
for name,h in oldm['tools_sha256'].items():
    matches=[p for p,b in oldblobs.items() if Path(p).name==name and sha(b)==h]
    assert matches, (name,h)
    if name=='cpu1c_prereq.py':
        name='cpu1d_prereq.py'; path=base+'cpu1d/'+name; r=rev; data=blob(r,path)
    else:
        path=sorted(matches)[0]; r=oldrev; data=blob(r,path)
    store(out/'tools'/name,data)
    provenance[name]={'git_commit':r,'git_path':path,'sha256':sha(data)}
assert len(provenance)==32
assert provenance['cpu1c_sums.py']['sha256']=='2efdca7e26a6e78a327cb5eb21284c2b6d3cf4d02d4d8d472e511bbe9832439c'
for name in ['chain-cpu1d.sh','cpu1d-launch-wrapper.sh','cpu1d_prereq.py','namespace_control.py','test_startup.py','freeze_packet.py']:
    store(out/name,blob(rev,base+'cpu1d/'+name))
for name in ['cpu1c_prereq.py','cpu1c-launch-wrapper2.sh']:
    path='cpu1c/'+('freeze/' if 'wrapper' in name else '')+name
    store(out/'old'/name,blob(rev,base+path))
# The only prerequisite changes are startup paths and its namespace predicate.
old=blob(rev,base+'cpu1c/cpu1c_prereq.py').decode()
new=blob(rev,base+'cpu1d/cpu1d_prereq.py').decode()
def without_namespace(s,start):
    a=s.index(start); b=s.index('text = Path(sys.argv[1])',a)
    return s[:a]+s[b:]
assert without_namespace(old,'# the stage wrapper').replace('cpu1c_prereq.py','cpu1d_prereq.py').replace("'t24-cpu1c'","'t24-cpu1d'").replace("'tools-cpu1c-run'","'tools-cpu1d-run'")==without_namespace(new,'# Launch markers')
# Expand argv via a print-only go function: never c1_stage or native execution.
chain=(out/'chain-cpu1d.sh').read_text()
preamble=chain.split('cd $SC\n')[0]
body=chain[chain.index('go cpu1d-prereq'):chain.index('date -u +%FT%TZ > logs/chain-cpu1d.finished')]
printer='go() { printf "%s\\t%s\\t" "$1" "$2"; shift 2; printf "%s " "$@"; printf "\\n"; }\n'
expanded=subprocess.check_output(['bash','-c',preamble+printer+body],text=True)
newstages=[]
for line in expanded.splitlines():
    name,allowed,argv=line.split('\t',2)
    newstages.append({'stage':name,'allowed_exits':allowed,'argv':argv.rstrip()})
assert len(newstages)==17
# Keep helper and frozen identities/pins named cpu1c; all bodies otherwise differ
# only in namespace, deployed-tool path, or T24 directory.
def rename(s):
    return s.replace('cpu1c','cpu1d').replace('cpu1d_sums.py','cpu1c_sums.py').replace('/cpu1d-identities.json','/cpu1c-identities.json').replace('/cpu1d-pins','/cpu1c-pins')
for old,new in zip(oldm['stages'],newstages):
    assert new['stage']==rename(old['stage'])
    assert new['allowed_exits']==old['allowed_exits']
    assert new['argv']==rename(old['argv']),(old,new)
    new['expected_receipts']=[rename(x) for x in old['expected_receipts']]+['logs/'+new['stage']+'.reserved/owner']
expected=''.join(provenance[n]['sha256']+'  '+n+'\n' for n in sorted(provenance))
store(out/'cpu1d-tools-expected.sha256',expected.encode())
store(out/'git-tool-provenance.json',(json.dumps(provenance,indent=2)+'\n').encode())
store(out/'cpu1d-expanded-stages.txt',''.join(s['stage']+'\tallowed='+s['allowed_exits']+'\t'+s['argv']+'\n' for s in newstages).encode())
m={k:oldm[k] for k in ['tested_source_sha','binaries','expected_identities','pins','inputs','lane','pending_not_in_chain','decision_rules']}
m.update(schema='c1-cpu1d-startup/1',startup_git_commit=rev,frozen_cpu1c_tools_commit=oldrev,tools_sha256={k:v['sha256'] for k,v in provenance.items()},tools_count=32,unchanged_tool_bytes=31,chain='chain-cpu1d.sh',chain_sha256=sha((out/'chain-cpu1d.sh').read_bytes()),wrapper_sha256=sha((out/'cpu1d-launch-wrapper.sh').read_bytes()),stage_count=17,stages=newstages,launch_marker='logs/launch-cpu1d-attempt1',launch_gate='logs/chain-cpu1d.go',tools_dir='tools-cpu1d-run',T24_dir='t24-cpu1d',native_status='UNRUN',old_cpu1c_status='prereq RAN/FAIL (24/25); 16 later stages UNRUN; all native UNRUN',scratch_cap_new_bytes=16777216,launch_command='nohup setsid taskset -c 8-9 bash /mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb/cpu1d-launch-wrapper.sh > /mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb/logs/launch-cpu1d-attempt1.outer.out 2>&1 < /dev/null &',aggregate='INCONCLUSIVE remains INCONCLUSIVE even if chain reaches .done; only compare allows 0/1 and decision allows 0/3')
store(out/'cpu1d-manifest.json',(json.dumps(m,indent=2)+'\n').encode())
store(out/'packet.sha256',''.join(sha(p.read_bytes())+'  '+str(p.relative_to(out))+'\n' for p in sorted(out.rglob('*')) if p.is_file()).encode())
print(json.dumps({'packet':str(out),'git':rev,'tools':32,'unchanged_tools':31,'stages':17,'chain_sha256':m['chain_sha256'],'wrapper_sha256':m['wrapper_sha256']}))
