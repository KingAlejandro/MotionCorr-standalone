// SPDX-License-Identifier: GPL-2.0-or-later
// Standalone characterization of OUT-OF-CONTRACT inputs, not a cuFFT gate.
#include <cuda_runtime.h>
#include <cufft.h>
#include <fftw3.h>
#include <vector>
#include <complex>
#include <cmath>
#include <cstdio>
#include <stdexcept>
#include <algorithm>
#include <initializer_list>
#include <utility>
using C = std::complex<float>;
void ck(cudaError_t e) { if(e!=cudaSuccess) throw std::runtime_error(cudaGetErrorString(e)); }
void cf(cufftResult e) { if(e!=CUFFT_SUCCESS) throw std::runtime_error("cuFFT error "+std::to_string(int(e))); }
int main() { try {
 int version=0; cf(cufftGetVersion(&version)); cudaDeviceProp prop; ck(cudaGetDeviceProperties(&prop,0));
 printf("device=%s cufft=%d fftw=%s\n",prop.name,version,fftwf_version);
 puts("nx,ny,plan,injection,const_coefficient,alternating_coefficient,residual_rms,residual_max,difference_max,projected_difference_max,fftw_projection_max");
 for(auto dims : std::vector<std::pair<int,int>>{{4096,4096},{3710,3838},{3838,3710},{4092,5760},{5760,4092},{1024,1024},{742,768},{4096,1}}) {
  const int nx=dims.first,ny=dims.second,nf=nx/2+1; const size_t nc=size_t(nf)*ny,nr=size_t(nx)*ny;
  std::vector<C> in(nc),tmp(nc),projected(nc); std::vector<float> fw(nr),gpu(nr),gp(nr),fp(nr);
  cufftComplex *di=nullptr;float *dr=nullptr;ck(cudaMalloc((void**)&di,nc*sizeof(C)));ck(cudaMalloc((void**)&dr,nr*sizeof(float)));
  auto p= ny==1 ? fftwf_plan_dft_c2r_1d(nx,(fftwf_complex*)tmp.data(),fw.data(),FFTW_ESTIMATE) : fftwf_plan_dft_c2r_2d(ny,nx,(fftwf_complex*)tmp.data(),fw.data(),FFTW_ESTIMATE);
  if(!p) throw std::runtime_error("FFTW plan failed");
  for(int plan_kind=0;plan_kind<2;++plan_kind) {
   cufftHandle q;
   if(plan_kind==0) { if(ny==1) cf(cufftPlan1d(&q,nx,CUFFT_C2R,1));else cf(cufftPlan2d(&q,ny,nx,CUFFT_C2R)); }
   else { cf(cufftCreate(&q));int n[2]={ny,nx};size_t work;cf(cufftMakePlanMany(q,2,n,nullptr,1,0,nullptr,1,0,CUFFT_C2R,1,&work)); }
   const char* names[]={"nyquist","dc","both","nyquist_corner","dc_corner","nyquist_ycorner","dc_ycorner"};
   for(int test=0;test<7;++test) {
    std::fill(in.begin(),in.end(),C(0,0)); int ka=ny==1?0:3,kb=ny==1?0:5;bool a=false,b=false;
    if(test==0)b=true; if(test==1)a=true; if(test==2)a=b=true;
    if(test>=3) {ka=kb=test>=5?ny/2:0; a=(test==4||test==6);b=!a;}
    if(a)in[size_t(ka)*nf]=C(0,1);if(b)in[size_t(kb)*nf+nx/2]=C(0,1);
    tmp=in;fftwf_execute_dft_c2r(p,(fftwf_complex*)tmp.data(),fw.data());
    ck(cudaMemcpy(di,in.data(),nc*sizeof(C),cudaMemcpyHostToDevice));cf(cufftExecC2R(q,di,dr));ck(cudaDeviceSynchronize());ck(cudaMemcpy(gpu.data(),dr,nr*sizeof(float),cudaMemcpyDeviceToHost));
    projected=in;
    for(int x : {0,nx/2}) for(int y=0;y<=ny/2;++y) {size_t i=size_t(y)*nf+x,j=size_t((ny-y)%ny)*nf+x;C h=0.5f*(in[i]+std::conj(in[j]));projected[i]=h;projected[j]=std::conj(h);}
    tmp=projected;fftwf_execute_dft_c2r(p,(fftwf_complex*)tmp.data(),fp.data());
    ck(cudaMemcpy(di,projected.data(),nc*sizeof(C),cudaMemcpyHostToDevice));cf(cufftExecC2R(q,di,dr));ck(cudaDeviceSynchronize());ck(cudaMemcpy(gp.data(),dr,nr*sizeof(float),cudaMemcpyDeviceToHost));
    double dotc=0,dota=0,normc=0,norma=0,dm=0,pm=0,fm=0;
    for(int y=0;y<ny;++y) {double ca=cos(2*acos(-1.)*ka*y/ny),cb=cos(2*acos(-1.)*kb*y/ny);for(int x=0;x<nx;++x) {size_t i=size_t(y)*nx+x;double d=double(gpu[i])-fw[i];double pc=b?cb:0,pa=a?((x%2)?-ca:ca):0;dotc+=pc*d;dota+=pa*d;normc+=pc*pc;norma+=pa*pa;dm=std::max(dm,std::abs(d));pm=std::max(pm,std::abs(double(gp[i])-fp[i]));fm=std::max(fm,std::abs(double(fw[i])-fp[i]));}}
    double bc=normc?dotc/normc:0,ba=norma?dota/norma:0,rs=0,rm=0;
    for(int y=0;y<ny;++y) {double ca=cos(2*acos(-1.)*ka*y/ny),cb=cos(2*acos(-1.)*kb*y/ny);for(int x=0;x<nx;++x) {size_t i=size_t(y)*nx+x;double e=(double(gpu[i])-fw[i])-bc*(b?cb:0)-ba*(a?((x%2)?-ca:ca):0);rs+=e*e;rm=std::max(rm,std::abs(e));}}
    printf("%d,%d,%s,%s,%.10g,%.10g,%.10g,%.10g,%.10g,%.10g,%.10g\n",nx,ny,plan_kind?"many":"simple",names[test],bc,ba,sqrt(rs/nr),rm,dm,pm,fm);fflush(stdout);
   }
   cf(cufftDestroy(q));
  }
  fftwf_destroy_plan(p);ck(cudaFree(di));ck(cudaFree(dr));
 }
 return 0;
 }catch(const std::exception&e){fprintf(stderr,"%s\n",e.what());return 1;}}
