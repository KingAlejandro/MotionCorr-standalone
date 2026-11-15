import pathlib,sys,time,traceback,json
root=pathlib.Path(sys.argv[1]);sys.path[:0]=[str(root/'v2/tools'),str(root/'v2/test-data')]
import check_realistic_motion as check
for run in sorted((root/'results').glob('*/*/RUN.json')):
 out=run.parent
 if (out/'metrics.json').exists():continue
 row=json.loads(run.read_text());r=json.loads((root/'fixtures'/out.parent.name/'RECEIPT.json').read_text())['recipe']
 if row['exit']:
  (out/'analysis_error.json').write_text(json.dumps(dict(reason='PROCESS_FAILURE',exit=row['exit'])));continue
 try:
  star=out/'output/movie.star';check.validate_star_rows(star,r);s=check.read_motion_star(star)
  result=check.evaluate(r,json.loads((out/'runtime.json').read_text()),s)
  result['convergence']=check.convergence(out/'output/movie.log')
  result['identity']={str(p.relative_to(root)):check.gen.digest(p) for p in [run,out/'runtime.json',star,out/'output/movie.log']}
  (out/'metrics.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
 except Exception:
  (out/'analysis_error.txt').write_text(traceback.format_exc())
  print(out,traceback.format_exc(),flush=True)
