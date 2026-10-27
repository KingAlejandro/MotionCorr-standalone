import subprocess,pathlib,json,time,hashlib
p=pathlib.Path(__file__).resolve().parent
cmd=['ssh','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=10','-o','ConnectionAttempts=1','4GPUs','python3 -B -']
r=subprocess.run(cmd,input=(p/'remote_readonly.py').read_bytes(),capture_output=True,timeout=120)
(p/'stdout.json').write_bytes(r.stdout);(p/'stderr.txt').write_bytes(r.stderr)
(p/'EXECUTION.json').write_text(json.dumps({'argv':cmd,'rc':r.returncode,'script_sha256':hashlib.sha256((p/'remote_readonly.py').read_bytes()).hexdigest()},indent=2)+'\n')
print('ssh rc',r.returncode)
if r.returncode:
 print(r.stderr.decode()[-2000:]);raise SystemExit(r.returncode)
v=json.loads(r.stdout)
print(json.dumps({'utc':v['utc'],'host':v['hostname'],'loader_matches':{k:x['current_resolutions_equal'] for k,x in v['loader'].items()},'gpus':v['gpus'],'gpu_processes':v['gpu_processes'],'locks':v['locks'],'cpu_busy':v['cpu_busy_fraction'],'disk_free':v['disk_free_bytes']},indent=2))
