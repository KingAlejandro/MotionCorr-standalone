from pathlib import Path
import json, hashlib, datetime
p=Path(__file__).resolve().parent
wt=Path('/Users/alex.konstantinov/.t3/worktrees/MotionCorr/t3-9c391c37')
pins_path=wt/'docs/post_rc0/ccf_dc_native_compat_20261026/evidence/stageC/STAGEC_PINS.json'
pins=json.loads(pins_path.read_text())
sha=lambda f:hashlib.sha256(Path(f).read_bytes()).hexdigest()
driver=wt/'tools/ccf_dc_stagec_driver.py'
assert sha(driver)=='b45481459d414f56d37872d3c27c2b4b6854d16f8132dfdd52a58019187adf3d'
assert sha(pins_path)=='c6f6e154161e92fbb6de1b60ffc6a91b2dd3f943c0d6d14a8486f5cd633352f3'
review=Path('/tmp/mc-native-dc-stagec-opus-delta-review-20261027-r2/REPORT.md')
assert sha(review)=='83c04d6c611bff82c8b47659f82401d6e2ea5edbce7012a2e24ed44016312dc0'
pre=Path('/tmp/mc-native-dc-parent-preflight-20261027-r2/stdout.json')
v=json.loads(pre.read_text())
assert v['hostname']=='4-gpu-vm'
assert v['fixtures_verified']=={'k267':33,'n':26}
assert all(x['current_resolutions_equal'] for x in v['loader'].values())
assert all(not x['matching_proc_lock_lines'] for x in v['locks'].values())
assert max(v['cpu_busy_fraction'].values())==0
g=[line.split(', ') for line in v['gpus']['stdout'].splitlines()]
gpu=[r for r in g if r[1]==pins['gpu']['uuid']]
assert len(gpu)==1 and gpu[0][3]=='0'
assert all(line.split(', ')[0]=='3983855' for line in v['gpu_processes']['stdout'].splitlines() if pins['gpu']['uuid'] in line)
now=datetime.datetime.now(datetime.timezone.utc)
stamp=datetime.datetime.fromisoformat(v['utc'].replace('Z','+00:00'))
assert (now-stamp).total_seconds()<600
index={'schema':'stagec-parent-release-index/1','created_utc':now.isoformat(),
 'tooling_head':'047aa7a51381ca074dcf4c468581108ce551c3ed','compiled_source':pins['source'],
 'files':{'driver':{'path':str(driver),'sha256':sha(driver)},'pins':{'path':str(pins_path),'sha256':sha(pins_path)},
 'delta_review':{'path':str(review),'sha256':sha(review)},'initial_review':{'path':'/tmp/mc-native-dc-stagec-opus-review-20261027-r1/REPORT.md','sha256':sha('/tmp/mc-native-dc-stagec-opus-review-20261027-r1/REPORT.md')},
 'parent_readonly_preflight':{'path':str(pre),'sha256':sha(pre),'utc':v['utc']}},
 'fresh_resource_grant':{'host':'4GPUs / 4-gpu-vm','cpu_affinity':pins['cpus'],'gpu_uuid':pins['gpu']['uuid'],'foreign_context_pid':3983855,'mode':'shared correctness only; GPU3 untouched; no timing/exclusivity claim','scratch_cap_bytes':20*2**30,'initial_locks':v['locks'],'initial_gpu_utilization_percent':0,'per_job_guard_required':True},
 'counts':{'producers_max':160,'pairs':96,'repro':16,'M_jobs_held':16},
 'conditions':['Single run/output directory only. STOP is terminal; no retry, rerun, overwrite or continuation without a new parent disposition.','Recheck GPU2 at 0% with only declared foreign context immediately before driver; acquire all three pinned lock inodes nonblocking and retain through seal.','Stage only reviewed driver/guard/pins at exact hashes. Preserve replaced task-owned preparation bytes additively; never edit compiled or scorer files.','Verify source/archive/binaries/modules/fixtures/loader pins before execution; driver checks per job.','Verify final release_copy.json and final_status release hash equal this parent release; final ledger/status authoritative.','Re-hash all 59 input/truth files after final grading and preserve mismatch as invalid evidence, never a score pass.'],
 'limitations':['Historical Stage B dynamic loader resolution was not retained; current full/scrub resolutions match and every resolved library plus ELF interpreter was independently hashed.','ldd does not resolve runtime dlopen libcuda.so.1; no claim that ldd identifies runtime CUDA driver loading.','Truth is rehashed before each producer, not during or between exit and grade; final rehash cannot exclude transient edits.','Known SIGHUP/SIGKILL/SIGTERM-sealing and guard-timeout limits remain. Launch non-tty/setsid; do not change semantics mid-run.','GPU OBSERVED requires actual UUID readback before device attribution. Process samples do not prove all short-lived threads.']}
with open(p/'PARENT_RELEASE_INDEX.json','x') as f:json.dump(index,f,indent=2);f.write('\n')
rel={'schema':'stagec-release/1','driver_sha256':sha(driver),'pins_sha256':sha(pins_path),'ledger_sha256':pins['ledger']['sha256'],'source_commit':pins['source']['commit'],
 'outdir':'/home/alex/mc-dcnative-stagec-20261027-r1/runs','test_fixture':False,'authorized_by':'parent','run_id':'native-dc-stagec-20261027-r1',
 'review_report_sha256':sha(review),'release_index_sha256':sha(p/'PARENT_RELEASE_INDEX.json'),'fresh_resource_grant':index['fresh_resource_grant'],'native_producers_max':160,'M_jobs_authorized':0}
with open(p/'PARENT_RELEASE.json','x') as f:json.dump(rel,f,indent=2);f.write('\n')
print(json.dumps({'release_sha256':sha(p/'PARENT_RELEASE.json'),'index_sha256':sha(p/'PARENT_RELEASE_INDEX.json'),'outdir':rel['outdir'],'jobs':160}))
