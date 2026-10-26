// SPDX-License-Identifier: GPL-2.0-or-later
// Diagnostic only: actual NewFFT and native CUDA windowed operator on saved inputs.
#include "src/boundary_capture.h"
#include "src/acc/cuda/cuda_alignpatch.h"
#include "src/acc/cuda/cuda_movie_session.h"
#include "src/acc/cuda/cuda_hermitian.cuh"
#include "src/jaz/single_particle/new_ft.h"
#include <fstream>
#include <map>
#include <iostream>
#include <vector>
#include <cstring>
#include <cmath>
static void ck(cudaError_t e) { if(e!=cudaSuccess) throw std::runtime_error(cudaGetErrorString(e)); }
static void cf(cufftResult e) { if(e!=CUFFT_SUCCESS) throw std::runtime_error("cuFFT error "+std::to_string(e)); }
static void load(const std::string& p,void* v,size_t n) {
 std::ifstream f(p,std::ios::binary); if(!f.read((char*)v,n) || f.peek()!=EOF) throw std::runtime_error("size/read "+p);
}
int main(int argc,char** argv) try {
 if(argc!=5) throw std::runtime_error("replay window|inverse input out cpu|cuda");
 std::string mode=argv[1],in=argv[2],out=argv[3],backend=argv[4];
 if(backend!="cpu" && backend!="cuda") throw std::runtime_error("bad backend");
 setenv("MC_BOUNDARY_DIR",out.c_str(),1);
 std::ifstream g(in+"/geometry.txt"); std::map<std::string,double> v; std::string key;double val;
 while(g>>key>>val) v[key]=val;
 int nx=v.at("nx"),ny=v.at("ny"),n=v.at("nframes"),cx=v.at("ccf_nx"),cy=v.at("ccf_ny"),r=v.at("search_range");double b=v.at("bfactor");
 if(nx<=0||ny<=0||n!=24||cx<=0||cy<=0)throw std::runtime_error("bad geometry");
 size_t count=(size_t)cy*(cx/2+1),bytes=count*sizeof(fComplex);
 if(mode=="forward") {
  if(backend=="cpu") {
   for(int f:{0,4}) {MultidimArray<float> real(ny,nx);MultidimArray<fComplex> fft(ny,nx/2+1);
    load(in+"/pre-"+std::to_string(f)+".f32",real.data,(size_t)nx*ny*sizeof(float));
    NewFFT::FloatPlan plan(real,fft);char* desc=fftwf_sprint_plan(plan.getForward());std::cout<<"FFTW_ESTIMATE single-thread plan "<<desc<<'\n';fftwf_free(desc);
    NewFFT::FourierTransform(real,fft);mc_boundary::write("fft-"+std::to_string(f)+".c64",fft.data,fft.nzyxdim*sizeof(fComplex));}
  } else {
   CudaMovieSession session(nx,ny,n,0,std::cout);if(!session.initialize())throw std::runtime_error("session initialize");
   ck(cudaMemset(session.getDeviceRealFrames(),0,(size_t)n*nx*ny*sizeof(float)));
   std::vector<float> real((size_t)nx*ny);for(int f:{0,4}) {load(in+"/pre-"+std::to_string(f)+".f32",real.data(),real.size()*sizeof(float));
    ck(cudaMemcpy(session.getDeviceRealFrames()+(size_t)f*nx*ny,real.data(),real.size()*sizeof(float),cudaMemcpyHostToDevice));}
   if(!session.computeGlobalForwardFFT())throw std::runtime_error("native resident forward failed");
   std::vector<fComplex> fft((size_t)ny*(nx/2+1));for(int f:{0,4}) {
    ck(cudaMemcpy(fft.data(),session.getDeviceFourierFrames()+(size_t)f*fft.size(),fft.size()*sizeof(fComplex),cudaMemcpyDeviceToHost));
    mc_boundary::write("fft-"+std::to_string(f)+".c64",fft.data(),fft.size()*sizeof(fComplex));}
   session.release();
  }
 } else if(mode=="window" && backend=="cuda") {
  std::vector<fComplex> stack(n*count);for(int f=0;f<n;++f)load(in+"/input-"+std::to_string(f)+".c64",stack.data()+f*count,bytes);
  cufftComplex* d=nullptr;ck(cudaMalloc(&d,n*bytes));ck(cudaMemcpy(d,stack.data(),n*bytes,cudaMemcpyHostToDevice));
  PatchAlignmentWorkspace w;w.setSpectrumWindowed(true);std::vector<RFLOAT>x(n,0),y(n,0);
  cudaAlignPatchDeviceWithWorkspace(w,d,n,nx,ny,b,x,y,1,0,0,std::cout,true);
  if(!w.release())throw std::runtime_error("workspace release");ck(cudaFree(d));
 } else if(mode=="window" && backend=="cpu") {
  mc_boundary::geometry(nx,ny,n,cx,cy,r,b);
  MultidimArray<fComplex> ref(cy,cx/2+1);ref.initZeros();std::vector<MultidimArray<fComplex>> inputs(n);
  for(int f=0;f<n;++f){inputs[f].reshape(cy,cx/2+1);load(in+"/input-"+std::to_string(f)+".c64",inputs[f].data,bytes);
   for(size_t k=0;k<count;++k)ref.data[k]+=inputs[f].data[k];}
  MultidimArray<float> weight(cy,cx/2+1);
  for(int y=0;y<cy;++y){int ly=y>cy/2?y-cy:y;RFLOAT ly2=ly*(RFLOAT)ly/(ny*(RFLOAT)ny);
   for(int x=0;x<cx/2+1;++x){RFLOAT dist2=ly2+x*(RFLOAT)x/((nx/2+1)*(RFLOAT)(nx/2+1));DIRECT_A2D_ELEM(weight,y,x)=exp(-2*dist2*b);}}
  mc_boundary::write("reference.c64",ref.data,bytes);mc_boundary::write("weight.f32",weight.data,count*sizeof(float));
  for(int f:{0,4}){MultidimArray<fComplex> spec(cy,cx/2+1);MultidimArray<float> map(cy,cx);
   for(size_t k=0;k<count;++k)spec.data[k]=(ref.data[k]-inputs[f].data[k])*inputs[f].data[k].conj()*weight.data[k];
   mc_boundary::write("spectrum-"+std::to_string(f)+".c64",spec.data,bytes);
   NewFFT::inverseFourierTransform(spec,map);mc_boundary::write("map-"+std::to_string(f)+".f32",map.data,(size_t)cx*cy*sizeof(float));}
 } else if(mode=="inverse" && backend=="cpu") {
  for(int f:{0,4}){MultidimArray<fComplex> spec(cy,cx/2+1);MultidimArray<float> map(cy,cx);
   load(in+"/spectrum-"+std::to_string(f)+".c64",spec.data,bytes);NewFFT::inverseFourierTransform(spec,map);
   mc_boundary::write("map-"+std::to_string(f)+".f32",map.data,(size_t)cx*cy*sizeof(float));}
 } else if(mode=="inverse" && backend=="cuda") {
  std::vector<fComplex> stack(n*count);for(int f:{0,4})load(in+"/spectrum-"+std::to_string(f)+".c64",stack.data()+f*count,bytes);
  cufftComplex* d=nullptr;float* real=nullptr;ck(cudaMalloc(&d,n*bytes));ck(cudaMalloc(&real,(size_t)n*cx*cy*sizeof(float)));
  ck(cudaMemcpy(d,stack.data(),n*bytes,cudaMemcpyHostToDevice));ck(mc_cuda::projectHermitianColumns(d,cx,cy,n));
  ck(cudaMemcpy(stack.data(),d,n*bytes,cudaMemcpyDeviceToHost));
  for(int f:{0,4})mc_boundary::write("projected-spectrum-"+std::to_string(f)+".c64",stack.data()+f*count,bytes);
  int dims[2]={cy,cx};cufftHandle plan;cf(cufftCreate(&plan));size_t work=0;
  cf(cufftMakePlanMany(plan,2,dims,nullptr,1,count,nullptr,1,cx*cy,CUFFT_C2R,n,&work));cf(cufftExecC2R(plan,d,real));
  std::vector<float> h((size_t)cx*cy);for(int f:{0,4}){ck(cudaMemcpy(h.data(),real+(size_t)f*cx*cy,h.size()*sizeof(float),cudaMemcpyDeviceToHost));mc_boundary::write("map-"+std::to_string(f)+".f32",h.data(),h.size()*sizeof(float));}
  cf(cufftDestroy(plan));ck(cudaFree(real));ck(cudaFree(d));
 } else throw std::runtime_error("bad mode");
 mc_boundary::check();return 0;
} catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
