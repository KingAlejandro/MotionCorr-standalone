#!/usr/bin/env python3
"""Run the actual CMake mutation helper with mocked targets, never CUDA/build/tests."""
import pathlib,subprocess,hashlib,json,difflib
repo=pathlib.Path(__file__).resolve().parents[3]
# script parent is docs/cuda_cpu_boundary_20261026/ci_repair_20261026
assert (repo/'CMakeLists.txt').is_file()
root=repo/'build/pr288-ci-anchor-20261026';root.mkdir(parents=True,exist_ok=False)
old=subprocess.check_output(['git','show','58cd3a563ac0b0af6999369b60a3377d656abad4:CMakeLists.txt'],cwd=repo,text=True)
new=(repo/'CMakeLists.txt').read_text();source=(repo/'src/acc/cuda/cuda_alignpatch.cu').read_text()
needle='\n        ALIGN_LAUNCH(mc_cuda::projectHermitianColumns((cufftComplex*)d_Fccs, ccf_nx, ccf_ny, n_frames));'
replacement='\n        ALIGN_LAUNCH(cudaSuccess);'
batch='\n            ALIGN_LAUNCH(mc_cuda::projectHermitianColumns((cufftComplex*)d_Fccs, ccf_nx, ccf_ny, n_frames));'
assert source.count(needle)==source.count(batch)==1

def sha(text):return hashlib.sha256(text.encode()).hexdigest()
def parts(cmake):
 start=cmake.index('        function(mc_cuda_mutant ');end=cmake.index('        endfunction()',start)+len('        endfunction()');func=cmake[start:end]
 lines=cmake.splitlines();calls=[]
 for name in ['ccf_perpatch_no_projection','ccf_batched_no_projection']:
  idx=next(i for i,line in enumerate(lines) if 'mc_cuda_mutant(CudaHermitianCCFMutant' in line and name in line);calls.append('\n'.join(lines[idx:idx+3]))
 start=cmake.index('        set(PATCH_BATCH_WRAPS');end=cmake.index(')',start)+1
 return func,cmake[start:end],calls
oldfunc,_,_=parts(old);newfunc,wraps,calls=parts(new);assert oldfunc==newfunc
stub='''cmake_minimum_required(VERSION 3.21)
project(PR288StaticMutant LANGUAGES NONE)
file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/registration.txt" "")
'''
for name in ['add_executable','target_link_libraries','target_include_directories','target_link_options','target_compile_definitions','add_test','set_tests_properties']:
 stub+='function('+name+')\n  file(APPEND "${CMAKE_CURRENT_BINARY_DIR}/registration.txt" "'+name+' ${ARGV}\\n")\nendfunction()\n'
rows=[]
for name,cmake,text,expected in [('original-stale-anchor',old,source,False),('repaired-anchor',new,source,True),('missing-anchor-control',new,source.replace(needle,'\n        /* missing projection for guard control */'),False),('duplicate-anchor-control',new,source+needle+'\n',False)]:
 case=root/name;fixture=case/'fixture';p=fixture/'src/acc/cuda/cuda_alignpatch.cu';p.parent.mkdir(parents=True);p.write_text(text)
 project=case/'project';project.mkdir();func,wrap,statements=parts(cmake)
 (project/'CMakeLists.txt').write_text(stub+'\nset(CMAKE_CURRENT_SOURCE_DIR [=['+str(fixture)+']=])\n'+wrap+'\n'+func+'\n'+'\n'.join(statements)+'\n')
 argv=['cmake','-S',str(project),'-B',str(case/'out')]
 result=subprocess.run(argv,cwd=repo,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT);(case/'configure.log').write_text(result.stdout)
 row={'case':name,'argv':argv,'rc':result.returncode,'expected_configure_success':expected,'cmake_source_sha256':sha(cmake),'CUDA_source_sha256':sha(text),'helper_sha256':sha(func),'log_sha256':sha(result.stdout)}
 assert (result.returncode==0)==expected,(name,result.stdout)
 if not expected:assert 'target line missing or not unique' in result.stdout
 if expected:
  per=(case/'out/mutants/cuda_alignpatch_ccf_perpatch_no_projection.cu').read_text();bat=(case/'out/mutants/cuda_alignpatch_ccf_batched_no_projection.cu').read_text()
  assert per==text.replace(needle,replacement) and per.count(needle)==0 and per.count(batch)==1
  assert 'ALIGN_CUFFT(cufftExecC2R(plan_c2r,' in per and 'ALIGN_CUFFT(cufftExecC2R(w.plan_c2r,' in per
  assert 'capture_device("ifft-input-' in per
  # Unmodified batched anchor still removes its own projection only.
  assert bat.count(needle)==1 and bat.count(batch)==0
  registration=(case/'out/registration.txt').read_text()
  for mutant in ['ccf_perpatch_no_projection','ccf_batched_no_projection']:
   assert f'target_compile_definitions cuda_patch_batch_{mutant};PRIVATE;MC_CHECK_HERMITIAN' in registration
   assert f'add_test NAME;CudaHermitianCCFMutant_{mutant};COMMAND;cuda_patch_batch_{mutant};--expect-invariant-failure' in registration
  row.update(perpatch_mutant_sha256=sha(per),batched_mutant_sha256=sha(bat),registration_sha256=sha(registration),perpatch_exact_single_projection_removal=True,batched_projection_preserved_in_perpatch=True,both_inverse_calls_preserved=True,diagnostic_capture_preserved=True,MC_CHECK_HERMITIAN_and_expected_failure_registration_preserved=True)
  (root/'perpatch-mutant.diff').write_text(''.join(difflib.unified_diff(text.splitlines(True),per.splitlines(True),fromfile='original/cuda_alignpatch.cu',tofile='mutant/cuda_alignpatch.cu')))
  (root/'registration.txt').write_text(registration)
 rows.append(row)
report={'tested_base':'58cd3a563ac0b0af6999369b60a3377d656abad4','cmake_version':subprocess.check_output(['cmake','--version'],text=True).splitlines()[0],'scope':'local actual-CMake helper + registration with mocked targets; not full CUDA configure, compilation, native invariant rejection or science','helper_function_unchanged':True,'production_source_unchanged_since_58cd':subprocess.check_output(['git','diff','58cd3a563ac0b0af6999369b60a3377d656abad4','--','src'],cwd=repo,text=True)=='','cases':rows,'all4_static_cases_pass':True}
(root/'result.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
