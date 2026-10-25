import importlib.util,pathlib,tempfile,unittest
P=pathlib.Path(__file__).resolve().parent
sp=importlib.util.spec_from_file_location('capture_v3',P/'capture_cpu_v3.py');m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
OLD=pathlib.Path('/mnt/clathrin/alex-motioncorr-residual-ccf-20261022-805d9de2/runs/cpu-affine-on/out')
NEW=pathlib.Path('/mnt/clathrin/alex-motioncorr-w4-cpu13-20261025-d3e1b33e-1082-478e-815a-032ea5f3a83e/campaign/patch-1-1/out')
BASE=(P/'retained-affine.log').read_text();ACT=(P/'attempt1-affine.log').read_text()
class LogContract(unittest.TestCase):
 def check_log(self,text,root=NEW):
  with tempfile.TemporaryDirectory() as d:
   f=pathlib.Path(d)/'log';f.write_text(text);return m.normalized_log(f,root)
 def test_actual_two_field_difference_passes(self):
  self.assertNotEqual(BASE,ACT);self.assertEqual(self.check_log(BASE,OLD),self.check_log(ACT))
 def test_iteration_numeric_change_still_differs(self):
  changed=ACT.replace('Polynomial fit RMSD: X = 0.129612','Polynomial fit RMSD: X = 0.229612');self.assertNotEqual(changed,ACT)
  self.assertNotEqual(self.check_log(BASE,OLD),self.check_log(changed))
 def test_wrong_output_path_refuses(self):
  with self.assertRaises(RuntimeError):self.check_log(ACT.replace(str(NEW/'affine.mrc'),'/tmp/wrong.mrc'))
 def test_duplicate_wall_refuses(self):
  with self.assertRaises(RuntimeError):self.check_log(ACT+'Full movie wall time: 0.014 s\n')
 def test_missing_wall_refuses(self):
  with self.assertRaises(RuntimeError):self.check_log(''.join(x for x in ACT.splitlines(True) if not x.startswith('Full movie wall time:')))
 def test_nonfinite_wall_refuses(self):
  with self.assertRaises(RuntimeError):self.check_log(ACT.replace('Full movie wall time: 0.014 s','Full movie wall time: nan s'))
if __name__=='__main__':unittest.main()
