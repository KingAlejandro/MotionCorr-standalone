// Does cufftExecC2R (2D, batch 1, separate work area) modify its input? Real geometry + others.
#include <cufft.h>
#include <cuda_runtime.h>
#include <cstdio>
#include <vector>
#include <cstdlib>
#include <cstring>
#define CK(x) do{cudaError_t e=(x); if(e!=cudaSuccess){printf("CUDA %s line %d\n",cudaGetErrorString(e),__LINE__);exit(1);}}while(0)
#define FK(x) do{cufftResult e=(x); if(e!=CUFFT_SUCCESS){printf("FFT %d line %d\n",e,__LINE__);exit(1);}}while(0)
int main(int argc,char**argv){
  int sizes[][2]={{3838,3710},{4096,4096},{512,512},{35,29},{32,24},{3710,3838},{7676,7420}};
  for(auto&s:sizes){
    int nx=s[0],ny=s[1],nfx=nx/2+1;
    size_t nc=(size_t)ny*nfx;
    cufftHandle p; FK(cufftCreate(&p)); FK(cufftSetAutoAllocation(p,0));
    size_t wb=0; int n[2]={ny,nx};
    FK(cufftMakePlanMany(p,2,n,NULL,1,ny*nfx,NULL,1,nx*ny,CUFFT_C2R,1,&wb));
    void*w; CK(cudaMalloc(&w,wb?wb:1)); FK(cufftSetWorkArea(p,w));
    std::vector<cufftComplex> h(nc); srand(1);
    for(auto&v:h){v.x=(rand()&65535)/4096.f-8;v.y=(rand()&65535)/4096.f-8;}
    cufftComplex*in; float*out; CK(cudaMalloc(&in,nc*8)); CK(cudaMalloc(&out,(size_t)nx*ny*4));
    CK(cudaMemcpy(in,h.data(),nc*8,cudaMemcpyHostToDevice));
    FK(cufftExecC2R(p,in,out)); CK(cudaDeviceSynchronize());
    std::vector<cufftComplex> g(nc); CK(cudaMemcpy(g.data(),in,nc*8,cudaMemcpyDeviceToHost));
    size_t diff=0,first=(size_t)-1; for(size_t i=0;i<nc;i++) if(memcmp(&g[i],&h[i],8)){diff++; if(first==(size_t)-1)first=i;}
    printf("%dx%d work=%zu MiB input_words_changed=%zu of %zu first=%zd (row %zd col %zd)\n",nx,ny,wb>>20,diff,nc,(ssize_t)first,first==(size_t)-1?-1:(ssize_t)(first/nfx),first==(size_t)-1?-1:(ssize_t)(first%nfx));
    cudaFree(in);cudaFree(out);cudaFree(w);cufftDestroy(p);
  }
  int v; cufftGetVersion(&v); printf("cufft version %d\n",v);
}
