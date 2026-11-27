import hashlib,json,pathlib,subprocess,sys
s=pathlib.Path(sys.argv[1]);m=json.load(open(s/'source-blobs.json'));bad=[]
for name,want in m['blobs'].items():
 p=s/'src'/name;b=p.read_bytes();got=hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
 if got!=want:bad.append(name)
def val(cmd):return subprocess.check_output(cmd,text=True).strip()
cache=(s/'build/CMakeCache.txt').read_text();flags=(s/'build/CMakeFiles/motioncorr_core.dir/flags.make').read_text()
r={'source_sha':m['source_sha'],'source_files_checked':len(m['blobs']),'source_mismatches':bad,'hostname':val(['hostname']),'binary_sha256':hashlib.sha256((s/'build/motioncorr').read_bytes()).hexdigest(),'gcc':val(['gcc','--version']).splitlines()[0],'fftw':val(['pkg-config','--modversion','fftw3','fftw3f']).splitlines(),'release_flags':[l for l in flags.splitlines() if l.startswith(('CXX_FLAGS','CUDA_FLAGS'))],'cache_selection':[l for l in cache.splitlines() if l.startswith(('CMAKE_BUILD_TYPE:','CUDA:BOOL','USE_NVCOMP:BOOL','CMAKE_CUDA_COMPILER:','Python3_EXECUTABLE:'))],'source_archive_initial_sha256':hashlib.sha256((s/'source.tar.gz').read_bytes()).hexdigest(),'source_archive_note':'Initial archive was 97fd8107; motioncorr_runner.cpp was updated to afba50a4; every src blob and CMakeLists.txt is verified above.'}
assert not bad,bad
assert 'CMAKE_BUILD_TYPE:STRING=Release' in cache and '-O3 -DNDEBUG' in flags
json.dump(r,open(s/'source-validation.json','w'),indent=1);print(json.dumps(r))
