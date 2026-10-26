"""Copy-only negative controls of the pinned established comparator, no native jobs."""
import json,shutil,subprocess,sys,tempfile
from pathlib import Path
comparator=Path(sys.argv[1]);out=Path(sys.argv[2]);rows=[]
with tempfile.TemporaryDirectory(prefix='b2-comparator-') as t:
 root=Path(t);a=root/'A';a.mkdir();(a/'case.star').write_text('data_case\n1.000000\n');(a/'case.mrc').write_bytes(bytes(1024)+b'payload')
 (a/'corrected_micrographs.star').write_text(str(a/'case.mrc')+' '+str(a/'case.star')+' 1 0.000000\n')
 for label,expected in [('root-only',0),('numeric',1),('basename',1),('missing',1),('extra',1)]:
  b=root/label;shutil.copytree(a,b);p=b/'corrected_micrographs.star';p.write_text(p.read_text().replace(str(a),str(b)))
  if label=='numeric':(b/'case.star').write_text('data_case\n1.000001\n')
  if label=='basename':p.write_text(p.read_text().replace('case.mrc','wrong.mrc'))
  if label=='missing':(b/'case.star').unlink()
  if label=='extra':(b/'unexpected.txt').write_text('unexpected output')
  receipt=root/(label+'.json');cp=subprocess.run([sys.executable,str(comparator),str(a),str(b),str(receipt)],capture_output=True,text=True)
  row=dict(control=label,expected_exit=expected,exit=cp.returncode,result=json.loads(receipt.read_text()));rows.append(row)
  assert cp.returncode==expected,(label,cp.stdout,cp.stderr)
out.write_text(json.dumps(rows,indent=2)+'\n');print('PASS root-only identity; numeric/basename/missing/extra rejected')
