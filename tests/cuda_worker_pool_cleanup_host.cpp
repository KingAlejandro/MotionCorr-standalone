// Compile the ACTUAL pool implementation against host API doubles. No CUDA
// execution, FFT correctness, real device selection or performance is claimed.
#include "src/acc/cuda/cuda_worker_pool.h"
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>
namespace {
int current = 0, next_plan = 1, frees = 0, destroys = 0, wrong_context = 0;
bool fail_selection = false;
std::map<void*,int> buffers;
std::map<cufftHandle,int> plans;
void require(bool ok, const std::string &message) { if (!ok) throw std::runtime_error(message); }
}
cudaError_t cudaSetDevice(int device) {
 if (fail_selection) return cudaErrorInvalidDevice;
 current = device; return cudaSuccess;
}
cudaError_t cudaPeekAtLastError() { return cudaSuccess; }
cudaError_t cudaMalloc(void **out, std::size_t bytes) {
 *out = std::malloc(bytes ? bytes : 1); if (!*out) return cudaErrorMemoryAllocation;
 buffers[*out] = current; return cudaSuccess;
}
cudaError_t cudaFree(void *p) {
 ++frees;
 if (buffers.count(p) == 0 || buffers.at(p) != current) { ++wrong_context; return cudaErrorInvalidDevice; }
 buffers.erase(p); std::free(p); return cudaSuccess;
}
cudaError_t cudaMemcpy(void *out, const void *in, std::size_t n, cudaMemcpyKind) {
 std::memcpy(out,in,n); return cudaSuccess;
}
cudaError_t cudaEventDestroy(cudaEvent_t) { return cudaSuccess; }
cufftResult cufftCreate(cufftHandle *p) { *p=next_plan++; plans[*p]=current; return CUFFT_SUCCESS; }
cufftResult cufftDestroy(cufftHandle p) {
 ++destroys;
 if (plans.count(p) == 0 || plans.at(p) != current) { ++wrong_context; return CUFFT_INTERNAL_ERROR; }
 plans.erase(p); return CUFFT_SUCCESS;
}
cufftResult cufftSetAutoAllocation(cufftHandle, int) { return CUFFT_SUCCESS; }
cufftResult cufftMakePlanMany(cufftHandle, int, int*, int*, int, int, int*, int, int, cufftType, int, std::size_t *size) { *size=256; return CUFFT_SUCCESS; }
cufftResult cufftSetWorkArea(cufftHandle, void*) { return CUFFT_SUCCESS; }
cufftResult cufftGetSize(cufftHandle, std::size_t *size) { *size=256; return CUFFT_SUCCESS; }
int main() {
 try {
  std::vector<float> gain(80*64,1.0f);
  for (int resource=0;resource<4;++resource) for(int action=0;action<4;++action) {
   mc_cuda::CudaWorkerPool pool; const int token=0;
   auto acquire=[&](bool change,CudaFailureState *failure) {
    int nx=change?80:64, ny=change?64:48; cufftHandle plan=0; std::size_t work=0;
    mc_cuda::GlobalFftLease global;
    if(resource==0) return pool.acquireGain(&token,0,nx,ny,change?2:1,gain.data(),failure)!=nullptr;
    if(resource==1) return pool.acquireGlobalFft(&token,0,nx,ny,nx/2+1,global,failure);
    if(resource==2) return pool.acquirePatchPlan(&token,0,nx/2,ny/2,3,plan,failure);
    return pool.acquireDwPlan(&token,0,nx,ny,plan,work,failure);
   };
   require(pool.acquireLease(&token)&&acquire(false,nullptr),"warmup");
   require(pool.releaseLease(&token),"warm lease release");
   auto before_buffers=buffers; auto before_plans=plans;
   auto bytes=pool.retainedBytes().total(); require(bytes>0,"owned bytes needed");
   current=1; frees=destroys=wrong_context=0; fail_selection=true;
   CudaFailureState failure; bool released=false,clean=false;
   if(action==0) { require(pool.acquireLease(&token),"replace lease"); clean=acquire(true,&failure); require(pool.releaseLease(&token),"replace release"); }
   else if(action==1) clean=pool.evictUnused(&failure,&released);
   else if(action==2) clean=pool.dropAll(&failure);
   else { failure.record(cudaErrorIllegalAddress,"fatal origin",1); clean=pool.retireForFatalContext(0,&failure); }
   std::string at=" resource="+std::to_string(resource)+" action="+std::to_string(action);
   require(!clean&&failure.hasFailed(),"selection failure not reported"+at);
   require(frees==0&&destroys==0&&wrong_context==0,"selection failure issued wrong-context release"+at);
   require(buffers==before_buffers&&plans==before_plans&&pool.retainedBytes().total()==bytes,"pending ownership lost"+at);
   require(!released&&pool.counters().evictions==0,"false eviction"+at);
   if(action!=3) {
    require(pool.acquireLease(&token),"pending lease"); CudaFailureState fresh;
    require(!acquire(false,&fresh)&&fresh.hasFailed(),"stale key served pending entry"+at);
    require(frees==0&&destroys==0,"pending acquire release without selection"+at);
    require(pool.releaseLease(&token),"pending release");
   } else require(pool.retiredFor(0),"retirement not sticky");
   fail_selection=false;
   if(action==1) require(pool.evictUnused(nullptr,&released)&&released,"invalidated entry not retried by eviction"+at);
   else require(pool.dropAll(nullptr),"pending teardown retry"+at);
   require(buffers.empty()&&plans.empty()&&pool.retainedBytes().total()==0,"retry leaks"+at);
   require(pool.dropAll(nullptr),"retry idempotency"+at);
   if(action==3) require(pool.retiredFor(0),"retry resurrected retired pool");
   std::cout<<"PASS host actual-pool cleanup"<<at<<"\n";
  }
  std::cout<<"ALL PASS:16 host ownership controls; native execution UNRUN\n";
 } catch(const std::exception &e) { std::cerr<<"FAIL: "<<e.what()<<"\n";return 1; }
}
