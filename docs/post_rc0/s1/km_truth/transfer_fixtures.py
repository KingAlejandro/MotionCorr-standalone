#!/usr/bin/env python3
"""Stream generated fixtures cpu64 -> 4GPUs; keep only verified duplicates eligible for cleanup."""
import json
from pathlib import Path
import re
import shlex
import subprocess
import time
CPU='/home/ubuntu/mc-km-truth-20261021'
GPU='/mnt/clathrin/alex-motioncorr-km-truth'
SSH=['ssh','-J','ccp4-gateway','-o','BatchMode=yes','-o','ConnectTimeout=15']

def remote(host,cmd):
 return subprocess.check_output(SSH+[host,cmd],text=True)


def main():
 copied=set()
 # Bounded campaign, polling available receipts only; never duplicate active transfer.
 deadline=time.time()+12*3600
 while len(copied)<100:
  if time.time()>deadline: raise TimeoutError('transfer campaign deadline')
  names=remote('cpu64',f'find {CPU}/fixtures -name RECEIPT.json -printf "%h\\n"').splitlines()
  for path in names:
   name=Path(path).name
   if name in copied: continue
   if not re.fullmatch(r'[a-z0-9]+-s[0-9]{2}',name): raise ValueError(name)
   receipt=json.loads(remote('cpu64',f'cat {CPU}/fixtures/{name}/RECEIPT.json'))
   q=shlex.quote(name)
   source=subprocess.Popen(SSH+['cpu64',f'taskset -c 56-63 tar -C {CPU}/fixtures -czf - {q}/input.star {q}/movie.mrcs {q}/RECEIPT.json'],stdout=subprocess.PIPE)
   dest=subprocess.Popen(SSH+['4GPUs',f'tar -C {GPU}/fixtures -xzf -'],stdin=source.stdout)
   source.stdout.close()
   dr=dest.wait(); sr=source.wait()
   if dr or sr: raise RuntimeError((name,sr,dr))
   got=remote('4GPUs',f'sha256sum {GPU}/fixtures/{q}/movie.mrcs').split()[0]
   if got!=receipt['files']['movie.mrcs']: raise RuntimeError('GPU copy hash mismatch')
   marker=json.dumps({'movie_sha256':got,'copy_verified':True})+'\n'
   # Store acknowledgements only after verifying the full payload on its retained host.
   for host,root,fn in [('cpu64',CPU,'GPU_COPY_VERIFIED.json'),('4GPUs',GPU,'TRANSFER_VERIFIED.json')]:
    subprocess.run(SSH+[host,f'cat > {root}/fixtures/{q}/{fn}'],input=marker,text=True,check=True)
   copied.add(name); print(json.dumps(dict(fixture=name,sha256=got,copied=len(copied))),flush=True)
  time.sleep(5)

if __name__=='__main__': main()
