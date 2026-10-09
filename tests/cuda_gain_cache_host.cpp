// SPDX-License-Identifier: GPL-2.0-or-later
// Actual production gain ownership header against host API doubles. No GPU work.
#include "src/acc/cuda/cuda_plan_pool.h"
#include <cstdlib>
#include <iostream>
#include <map>
#include <stdexcept>
#include <string>
namespace {
int current=0, free_calls=0, wrong_context=0;
bool fail_selection=false;
std::map<void*,int> owners;
void require(bool ok,const char *message) { if(!ok) throw std::runtime_error(message); }
void populate(mc_cuda::CudaWorkerPlanPool &pool) {
 current=0; float *p=nullptr; require(cudaMalloc(reinterpret_cast<void**>(&p),4096)==cudaSuccess,"fixture allocation failed");
 pool.gain.ptr=p;pool.gain.bytes=4096;pool.gain.generation=7;pool.gain.nx=32;pool.gain.ny=32;pool.gain.device_id=0;
 free_calls=wrong_context=0;
}
void selection() {
 mc_cuda::CudaWorkerPlanPool pool;populate(pool);float *owned=pool.gain.ptr;
 current=1;fail_selection=true;CudaFailureState failure;
 bool ok=pool.gain.drop(&failure);
 require(!ok&&failure.firstError()==cudaErrorInvalidDevice,"selection failure was not recorded");
 require(free_calls==0&&wrong_context==0,"selection failure freed owned gain");
 require(pool.gain.ptr==owned&&pool.retainedBytes()==4096&&pool.gain.generation==0,"selection failure lost invalidated gain ownership");
 require(current==1,"selection failure changed caller device");
 fail_selection=false;
 require(pool.gain.drop(&failure),"pending gain release retry failed");
 require(current==1&&free_calls==1&&owners.empty(),"pending gain release did not restore caller and free once");
 require(pool.gain.drop(&failure)&&free_calls==1&&pool.retainedBytes()==0,"gain release retry not idempotent");
 require(failure.firstError()==cudaErrorInvalidDevice,"release retry erased original failure");
}
#ifndef GAIN_SELECTION_ONLY
void lease() {
 mc_cuda::CudaWorkerPlanPool pool;populate(pool);int a=1,b=2;float *owned=pool.gain.ptr;
 require(pool.acquireLease(&a,0),"first gain lease failed");
 require(pool.acquireLease(&a,0),"same holder gain lease failed");
 require(!pool.acquireLease(&b,0),"second session acquired live gain lease");
 CudaFailureState blocked;
 require(!pool.dropAll(&blocked,&b)&&blocked.firstError()==cudaErrorNotReady,"second session evicted live gain lease");
 require(pool.gain.ptr==owned&&free_calls==0&&pool.retainedBytes()==4096,"second session changed borrowed gain");
 require(!pool.releaseLease(&b),"second session released another holder lease");
 require(!pool.acquireLease(&b,0),"wrong holder release exposed gain");
 require(pool.releaseLease(&a)&&pool.acquireLease(&b,0),"released gain lease unavailable to next session");
 require(pool.dropAll(nullptr,&b)&&pool.releaseLease(&b),"next session could not retire its gain");
 require(owners.empty()&&free_calls==1,"lease control leaked gain");
}
void sticky() {
 mc_cuda::CudaWorkerPlanPool pool;populate(pool);int a=1;
 require(pool.acquireLease(&a,0),"fatal fixture lease failed");
 CudaFailureState original;
 original.record(cudaErrorMemoryAllocation,"first recoverable",1);original.record(cudaErrorIllegalAddress,"fatal original",2);
 require(pool.retire(0,&original,&a),"fatal gain retirement failed");
 require(pool.releaseLease(&a),"fatal holder release failed");
 CudaFailureState fresh;
 require(pool.retiredFor(0)&&pool.retiredFor(1),"worker retirement not sticky across devices");
 require(pool.retiredErrorFor(0)==cudaErrorIllegalAddress&&pool.retiredErrorFor(1)==cudaErrorIllegalAddress,"worker retirement lost original fatal code");
 require(!pool.acquireLease(&a,0)&&!pool.acquireLease(&a,1),"fresh failure state revived retired gain worker");
 require(!fresh.hasFailed(),"fresh state fixture was not fresh");
 CudaFailureState later;later.record(cudaErrorLaunchFailure,"later fatal",3);
 require(pool.retire(1,&later,&a),"repeat retirement failed");
 require(pool.retiredErrorFor(0)==cudaErrorIllegalAddress&&pool.retiredErrorFor(1)==cudaErrorIllegalAddress,"later retirement replaced original fatal code");
 require(pool.dropAll()&&pool.retiredFor(0)&&free_calls==1&&owners.empty(),"checked cleanup revived retired gain worker");
 require(original.firstError()==cudaErrorMemoryAllocation&&original.fatalError()==cudaErrorIllegalAddress,"retirement changed failure provenance");
}
#endif
}
cudaError_t cudaGetDevice(int *d){*d=current;return cudaSuccess;}
cudaError_t cudaSetDevice(int d){if(fail_selection)return cudaErrorInvalidDevice;current=d;return cudaSuccess;}
cudaError_t cudaPeekAtLastError(){return cudaSuccess;}
cudaError_t cudaMalloc(void **p,std::size_t n){*p=std::malloc(n?n:1);if(!*p)return cudaErrorMemoryAllocation;owners[*p]=current;return cudaSuccess;}
cufftResult cufftDestroy(cufftHandle){return CUFFT_SUCCESS;}
cudaError_t cudaFree(void *p){++free_calls;auto it=owners.find(p);if(it==owners.end()||it->second!=current){++wrong_context;return cudaErrorInvalidDevice;}owners.erase(it);std::free(p);return cudaSuccess;}
int main(int argc,char **argv){
 try{
  require(argc==1||(argc==3&&std::string(argv[1])=="--case"), "invalid host case arguments");
  std::string which=argc==3&&std::string(argv[1])=="--case"?argv[2]:"all";
  require(which=="all"||which=="selection"||which=="lease"||which=="sticky", "unknown host case selector");
  if(which=="all"||which=="selection")selection();
#ifndef GAIN_SELECTION_ONLY
  if(which=="all"||which=="lease")lease();
  if(which=="all"||which=="sticky")sticky();
#endif
  std::cout<<"PASS: actual gain header host controls case="<<which<<"; native UNRUN\n";
 }catch(const std::exception &e){std::cerr<<"FAIL: "<<e.what()<<'\n';return 1;}
}
