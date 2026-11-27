import json,subprocess,pathlib,datetime,os
r=pathlib.Path(__file__).parent
cmd=['/home/alex/.mc-venv/bin/python3',str(r/'run_pilot.py'),'execute',str(r)]
p=subprocess.run(cmd)
(r/'supervisor_exit.json').open('x').write(json.dumps({'argv':cmd,'exit':p.returncode,'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'supervisor_pid':os.getpid()},indent=2))
raise SystemExit(p.returncode)
