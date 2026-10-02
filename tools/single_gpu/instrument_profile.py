#!/usr/bin/env python3
"""Add NVTX ranges to a DISPOSABLE profile source copy; never benchmark this build."""
from pathlib import Path
import re, sys
root = Path(sys.argv[1])
header = '''#include <nvtx3/nvToolsExt.h>
#include <cufft.h>
struct McProfileScope {
 explicit McProfileScope(const char *name) { nvtxRangePushA(name); }
 ~McProfileScope() { nvtxRangePop(); }
};
template<class F> auto mcProfileCall(const char *name, F fn) -> decltype(fn()) {
 McProfileScope scope(name); return fn();
}
#define cufftCreate(...) mcProfileCall("cufftCreate", [&]() { return (cufftCreate)(__VA_ARGS__); })
#define cufftMakePlanMany(...) mcProfileCall("cufftMakePlanMany", [&]() { return (cufftMakePlanMany)(__VA_ARGS__); })
#define cufftMakePlan2d(...) mcProfileCall("cufftMakePlan2d", [&]() { return (cufftMakePlan2d)(__VA_ARGS__); })
#define cufftPlanMany(...) mcProfileCall("cufftPlanMany", [&]() { return (cufftPlanMany)(__VA_ARGS__); })
#define cufftPlan2d(...) mcProfileCall("cufftPlan2d", [&]() { return (cufftPlan2d)(__VA_ARGS__); })
#define cufftDestroy(...) mcProfileCall("cufftDestroy", [&]() { return (cufftDestroy)(__VA_ARGS__); })
'''
for rel in ['src/motioncorr_runner.cpp','src/acc/cuda/cuda_movie_session.cu','src/acc/cuda/cuda_alignpatch.cu','src/acc/cuda/cuda_realspace_dw.cu']:
 p=root/rel;t=p.read_text();t=header+t
 if rel.endswith('motioncorr_runner.cpp'):
  t=t.replace('#define RCTIC(label)\n', '#define RCTIC(label) nvtxRangePushA(#label);\n')
  t=t.replace('#define RCTOC(label)\n', '#define RCTOC(label) nvtxRangePop();\n')
  for marker,name in [('void MotioncorrRunner::read(', 'CLI'),('void MotioncorrRunner::initialise(', 'startup'),('bool MotioncorrRunner::executeOwnMotionCorrection(', 'movie'),('void MotioncorrRunner::submitOutput(', 'output submit/wait'),('void MotioncorrRunner::writeModel(', 'STAR write'),('void MotioncorrRunner::plotShifts(', 'EPS write')]:
   start=t.find(marker)
   if start>=0:
    brace=t.index('{',start);t=t[:brace+1]+'\n McProfileScope mc_profile_scope("'+name+'");'+t[brace+1:]
  t=t.replace('output_writer->drain();','{ McProfileScope mc_drain("writer drain"); output_writer->drain(); }')
 elif rel.endswith('cuda_movie_session.cu'):
  t=re.sub(r'((?:bool|void|cudaError_t|cufftResult) CudaMovieSession::(\w+)\([^{}]*?\)\s*(?:noexcept\s*)?\{)',lambda m:m[1]+'\n McProfileScope mc_profile_scope("session:'+m[2]+'");',t)
  t=t.replace('HANDLE_ERROR(cudaMemcpyAsync(v.comp, h_stage, stage_used, cudaMemcpyHostToDevice, stream));','nvtxRangePushA("compressed H2D");\n        HANDLE_ERROR(cudaMemcpyAsync(v.comp, h_stage, stage_used, cudaMemcpyHostToDevice, stream));\n        nvtxRangePop();')
  t=t.replace('size_t stage_used = 0;', 'nvtxRangePushA("compressed read/repack");\n        size_t stage_used = 0;')
  t=t.replace('nvtxRangePushA("compressed H2D");','nvtxRangePop();\n        nvtxRangePushA("compressed H2D");')
 elif rel.endswith('cuda_alignpatch.cu'):
  entry='bool cudaAlignPatchDeviceWithWorkspace(' if 'bool cudaAlignPatchDeviceWithWorkspace(' in t else 'bool cudaAlignPatchDevice('
  start=t.index(entry);brace=t.index('{',start);t=t[:brace+1]+'\n McProfileScope mc_profile_scope(is_global ? "global align" : "patch align");'+t[brace+1:]

 elif rel.endswith('cuda_realspace_dw.cu'):
  line = 'HANDLE_ERROR(cudaMemcpy(Isum().data, d_Isum, sz_iframe, cudaMemcpyDeviceToHost));'
  t=t.replace(line, '{ McProfileScope mc_final_copy("final D2H"); '+line+' }')
 p.write_text(t)
p=root/'src/output_timing.h'; t=p.read_text()
t=t.replace('#define OTIC(label)\n','#define OTIC(label) nvtxRangePushA(#label);\n')
t=t.replace('#define OTOC(label)\n','#define OTOC(label) nvtxRangePop();\n')
p.write_text('#include <nvtx3/nvToolsExt.h>\n'+t)
