import pathlib,subprocess,json
root=pathlib.Path('/home/ubuntu/fix183-20261016'); src=root/'candidate'; log=root/'logs'
mutants=[('debug-old-witness','tests/test_cpu_patch_phase_window.cpp','phase_calls.fetch_add(1,std::memory_order_relaxed); return __real_sin','return __real_sin'),('release-full-local','src/motioncorr_runner.cpp','is_global ? 0 : ccf_nfx, is_global ? 0 : ccf_nfy','0, 0'),('release-dead-final','src/motioncorr_runner.cpp','if (is_global || (!(rmsd < tolerance) && iter < max_iter)) {','if (true) {')]
rows=[]
def run(cmd,path):
    with path.open('w') as f:
        return subprocess.run(cmd,cwd=src,stdout=f,stderr=subprocess.STDOUT).returncode
for name,file,old,new in mutants:
    build='build-debug' if name.startswith('debug') else 'build-release'
    p=src/file; original=p.read_text(); assert old in original
    try:
        # The fallback prefix matches double and float, deliberately disabling both.
        p.write_text(original.replace(old,new))
        rc=run(['/home/ubuntu/.mc-venv/bin/cmake','--build',build,'--target','cpu_patch_phase_window','-j4'],log/f'{name}-build.log'); assert rc==0
        rc=run([str(src/build/'cpu_patch_phase_window')],log/f'{name}-test.log')
        rows.append(dict(name=name,build=build,file=file,old=old,new=new,build_status=0,test_status=rc)); assert rc!=0
    finally: p.write_text(original)
    assert run(['/home/ubuntu/.mc-venv/bin/cmake','--build',build,'-j4'],log/f'{name}-restore-build.log')==0
    assert run([str(src/build/'cpu_patch_phase_window')],log/f'{name}-restore-test.log')==0
(log/'linux-mutants.json').write_text(json.dumps(rows,indent=2)+'\n')
print('PASS fallback-witness, full-local and dead-final mutants rejected; sources/binaries restored')
