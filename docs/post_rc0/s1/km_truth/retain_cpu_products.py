#!/usr/bin/env python3
"""Archive CPU sums on designated GPU scratch, verify bytes, release CPU duplicates."""
import hashlib,json,pathlib,re,subprocess,time
ROOT=pathlib.Path('/home/ubuntu/mc-km-truth-20261021')
GPU='/mnt/clathrin/alex-motioncorr-km-truth/retained-cpu-products'
SSH=['ssh','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','alex@130.246.80.58']

def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()


def main():
 subprocess.run(SSH+[f'mkdir -p {GPU}'],check=True)
 stage=ROOT/'product-archives';stage.mkdir(exist_ok=True);done=set();deadline=time.time()+12*3600
 while len(done)<100:
  if time.time()>deadline:raise TimeoutError('product retention deadline')
  for marker in sorted((ROOT/'results').glob('*/cpu.done.json')):
   name=marker.parent.name
   if name in done:continue
   if not re.fullmatch('[a-z0-9]+-s[0-9]{2}',name):raise ValueError(name)
   receipt=marker.parent/'cpu-products-retained.json'
   if receipt.exists():done.add(name);continue
   files=sorted(marker.parent.glob('cpu-*/output/movie.mrc'))
   if len(files)!=5:raise ValueError((name,'missing published sum'))
   hashes={str(p.relative_to(ROOT)):digest(p) for p in files}
   archive=stage/(name+'.tar.zst')
   subprocess.run(['taskset','-c','56-63','tar','-C',str(ROOT),'-I','zstd -1 -T2','-cf',str(archive),*hashes],check=True)
   subprocess.run(['tar','-C',str(ROOT),'-I','zstd','-df',str(archive)],check=True)
   ah=digest(archive);target=GPU+'/'+archive.name
   with archive.open('rb') as f:subprocess.run(SSH+[f'cat >{target}'],stdin=f,check=True)
   got=subprocess.check_output(SSH+[f'sha256sum {target}'],text=True).split()[0]
   if got!=ah:raise ValueError('product archive transfer mismatch')
   record=dict(archive=target,archive_sha256=ah,files=hashes,verified='tar --compare against source, then remote archive SHA256')
   text=json.dumps(record,indent=2)+'\n'
   receipt.write_text(text);subprocess.run(SSH+[f'cat >{target}.json'],input=text,text=True,check=True)
   for p in files:
    if digest(p)!=hashes[str(p.relative_to(ROOT))]:raise ValueError('sum changed before duplicate cleanup')
    p.unlink()
   archive.unlink();done.add(name);print(name,'retained',len(done),flush=True)
  time.sleep(5)

if __name__=='__main__':main()
