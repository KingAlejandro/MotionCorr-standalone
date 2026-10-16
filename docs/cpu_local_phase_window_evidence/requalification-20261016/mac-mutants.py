import pathlib, subprocess, json
root=pathlib.Path.cwd()
out=pathlib.Path('/tmp/fix183')
mutants=[('skip-needed','src/motioncorr_runner.cpp', 'if (is_global || (!(rmsd < tolerance) && iter < max_iter)) {', 'if (is_global) {'),('single-iteration','tests/test_cpu_patch_phase_window.cpp','for (int iterations : {1,5})', 'for (int iterations : {1})')]
results=[]
for name,file,old,new in mutants:
    p=root/file; original=p.read_text(); assert original.count(old)==1
    try:
        p.write_text(original.replace(old,new))
        with (out/f'mac-mutant-{name}-build.log').open('w') as f:
            rc=subprocess.run(['cmake','--build','build','--target','cpu_patch_phase_window','-j4'],stdout=f,stderr=subprocess.STDOUT).returncode
        assert rc==0
        with (out/f'mac-mutant-{name}.log').open('w') as f:
            rc=subprocess.run(['build/cpu_patch_phase_window'],stdout=f,stderr=subprocess.STDOUT).returncode
        results.append(dict(name=name,file=file,old=old,new=new,build_status=0,test_status=rc))
        assert rc!=0
    finally:
        p.write_text(original)
with (out/'mac-mutants.json').open('w') as f: json.dump(results,f,indent=2)
with (out/'mac-restore-build.log').open('w') as f:
    assert subprocess.run(['cmake','--build','build','-j4'],stdout=f,stderr=subprocess.STDOUT).returncode==0
with (out/'mac-restore-test.log').open('w') as f:
    assert subprocess.run(['build/cpu_patch_phase_window'],stdout=f,stderr=subprocess.STDOUT).returncode==0
