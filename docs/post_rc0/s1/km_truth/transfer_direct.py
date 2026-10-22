#!/usr/bin/env python3
"""Run on cpu64 through ssh -A -J ccp4-gateway; direct verified host-to-host streaming."""
import hashlib,json,pathlib,re,subprocess,time
ROOT=pathlib.Path('/home/ubuntu/mc-km-truth-20261021')
GPU='/mnt/clathrin/alex-motioncorr-km-truth'
SSH=['ssh','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=15','alex@130.246.80.58']

def remote(cmd): return subprocess.check_output(SSH+[cmd],text=True)

def main():
 copied=set(); deadline=time.time()+12*3600
 while len(copied)<100:
  if time.time()>deadline: raise TimeoutError('copy deadline')
  for receipt in sorted((ROOT/'fixtures').glob('*/RECEIPT.json')):
   name=receipt.parent.name
   if name in copied: continue
   if not re.fullmatch(r'[a-z0-9]+-s[0-9]{2}',name): raise ValueError(name)
   ready=remote(f'if test -f {GPU}/fixtures/{name}/RECEIPT.json; then echo ready; elif test -d {GPU}/fixtures/{name}; then echo partial; else echo absent; fi').strip()
   # A pre-existing in-flight gateway stream is allowed to finish; never overwrite it.
   if ready=='partial': continue
   record=json.loads(receipt.read_text())
   start=time.time()
   if ready=='absent':
    source=subprocess.Popen(['taskset','-c','56-63','tar','-C',str(ROOT/'fixtures'),'-I','zstd -1 -T4','-cf','-',name+'/input.star',name+'/movie.mrcs',name+'/RECEIPT.json'],stdout=subprocess.PIPE)
    dest=subprocess.Popen(SSH+[f'taskset -c 104-111 tar -C {GPU}/fixtures -I zstd -xf -'],stdin=source.stdout);source.stdout.close()
    dr=dest.wait();sr=source.wait()
    if dr or sr: raise RuntimeError((name,sr,dr))
   got=remote(f'sha256sum {GPU}/fixtures/{name}/movie.mrcs').split()[0]
   if got!=record['files']['movie.mrcs']:raise RuntimeError('copy hash mismatch')
   marker=json.dumps(dict(movie_sha256=got,copy_verified=True))+'\n'
   subprocess.run(SSH+[f'cat >{GPU}/fixtures/{name}/TRANSFER_VERIFIED.json'],input=marker,text=True,check=True)
   (receipt.parent/'GPU_COPY_VERIFIED.json').write_text(marker)
   copied.add(name);print(json.dumps(dict(fixture=name,sha256=got,seconds=time.time()-start,copied=len(copied))),flush=True)
  time.sleep(5)

if __name__=='__main__':main()
