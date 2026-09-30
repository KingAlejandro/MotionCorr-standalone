// Corrected ingestion benchmark: same start point (movie bytes requested) and same
// end point (float32 frames resident in VRAM) for every arm, complete pipelines
// repeated end to end, all observations kept, median and range reported.
//
//   A  libtiff decode -> host float32 -> H2D            (current production path)
//   B  libtiff decode -> host uint16  -> H2D -> convert (the #118/#125 direction)
//   C  raw strips -> aligned pinned -> H2D -> nvCOMP -> convert
#include <cstdio>
#include <cstring>
#include <cstdint>
#include <vector>
#include <string>
#include <algorithm>
#include <chrono>
#include <omp.h>
#include <cuda_runtime.h>
#include <tiffio.h>
#include "nvcomp.h"
#include "nvcomp/deflate.h"
#include "src/acc/cuda/cuda_deflate_layout.h"

using namespace mc_tiff_deflate;
#define CK(c) do{ cudaError_t e=(c); if(e!=cudaSuccess){ std::printf("CUDA %s @%d\n", cudaGetErrorString(e), __LINE__); std::exit(1);} }while(0)
static double ms(std::chrono::high_resolution_clock::time_point a,
                 std::chrono::high_resolution_clock::time_point b){
    return std::chrono::duration<double,std::milli>(b-a).count(); }

__global__ void u16tof(const uint16_t*s, float*d, size_t n, size_t pitch_u16, int nx, int ny){
    size_t i = (size_t)blockIdx.x*blockDim.x + threadIdx.x;
    if(i>=n) return;
    size_t f = i/((size_t)nx*ny), r = (i/(size_t)nx)%(size_t)ny, c = i%(size_t)nx;
    d[i] = (float)s[(f*(size_t)ny + r)*pitch_u16 + c];
}

struct Geom { int nx, ny, nf; std::vector<std::vector<uint32_t>> raw; };

static bool geometry(const char*p, Geom&g){
    TIFF*t=TIFFOpen(p,"r"); if(!t) return false;
    uint32_t w=0,h=0; uint16_t b=0,cmp=0;
    TIFFGetField(t,TIFFTAG_IMAGEWIDTH,&w); TIFFGetField(t,TIFFTAG_IMAGELENGTH,&h);
    TIFFGetField(t,TIFFTAG_BITSPERSAMPLE,&b); TIFFGetField(t,TIFFTAG_COMPRESSION,&cmp);
    int nf=0; do{ nf++; }while(TIFFReadDirectory(t));
    g.nx=(int)w; g.ny=(int)h; g.nf=nf; g.raw.assign(nf,{});
    for(int f=0; f<nf; f++){ TIFFSetDirectory(t,f); g.raw[f].resize(g.ny);
        for(int s=0;s<g.ny;s++) g.raw[f][s]=(uint32_t)TIFFRawStripSize(t,s); }
    TIFFClose(t); return b==16 && (cmp==COMPRESSION_DEFLATE||cmp==COMPRESSION_ADOBE_DEFLATE);
}

int main(int argc, char**argv){
    const int nthreads = argc>1 ? atoi(argv[1]) : 8;
    const int nreps    = argc>2 ? atoi(argv[2]) : 5;
    std::vector<std::string> movies;
    for(int i=3;i<argc;i++) movies.push_back(argv[i]);

    nvcompAlignmentRequirements_t al{}; 
    nvcompBatchedDeflateDecompressGetRequiredAlignments(nvcompBatchedDeflateDecompressDefaultOpts,&al);
    const size_t ia = std::max<size_t>(al.input,1), oa = std::max<size_t>(al.output,2);
    std::printf("threads=%d reps=%d movies=%zu  nvcomp_align in=%zu out=%zu\n",
                nthreads,nreps,movies.size(),al.input,al.output);
    std::printf("%-34s %8s %8s %8s %8s %8s %8s\n","movie","A_med","A_min","B_med","B_min","C_med","C_min");

    double sA=0,sB=0,sC=0; int nok=0;
    for(const auto& mv : movies){
        Geom g; if(!geometry(mv.c_str(),g)){ std::printf("skip %s\n",mv.c_str()); continue; }
        const size_t npx=(size_t)g.nx*g.ny*g.nf, bu16=npx*2, bf32=npx*4;
        const size_t rowb=(size_t)g.nx*2, pitchb=alignUp(rowb,oa), pitch_u16=pitchb/2;
        const size_t chunks=(size_t)g.nf*g.ny;

        std::vector<float> hf(npx); std::vector<uint16_t> hu(npx);
        float *dF=nullptr,*dF2=nullptr; uint16_t*dU=nullptr; void*dC=nullptr;
        CK(cudaMalloc(&dF,bf32)); CK(cudaMalloc(&dF2,bf32));
        CK(cudaMalloc(&dU,(size_t)g.nf*g.ny*pitchb)); 

        // aligned staging layout, hoisted out of the timed loop as a session buffer would be
        std::vector<size_t> fbase(g.nf); size_t stage=0;
        for(int f=0;f<g.nf;f++){ fbase[f]=alignUp(stage,ia); stage=fbase[f]+frameStageBytes(g.raw[f].data(),g.ny,ia); }
        void*hstage=nullptr; CK(cudaHostAlloc(&hstage,stage,cudaHostAllocDefault));
        CK(cudaMalloc(&dC,stage));
        void **dCp,**dDp; size_t *dCs,*dDs,*dAs; nvcompStatus_t*dSt;
        CK(cudaMalloc(&dCp,chunks*8)); CK(cudaMalloc(&dCs,chunks*8)); CK(cudaMalloc(&dDp,chunks*8));
        CK(cudaMalloc(&dDs,chunks*8)); CK(cudaMalloc(&dAs,chunks*8)); CK(cudaMalloc(&dSt,chunks*sizeof(nvcompStatus_t)));
        std::vector<void*> hCp(chunks),hDp(chunks); std::vector<size_t> hCs(chunks),hDs(chunks,rowb),hAs(chunks);
        std::vector<nvcompStatus_t> hSt(chunks);
        size_t tmpb=0; nvcompBatchedDeflateDecompressGetTempSizeAsync(chunks,rowb,
            nvcompBatchedDeflateDecompressDefaultOpts,&tmpb,bu16);
        void*dT=nullptr; if(tmpb) CK(cudaMalloc(&dT,tmpb));
        cudaStream_t st; CK(cudaStreamCreate(&st));

        { TIFF*t=TIFFOpen(mv.c_str(),"r"); tmsize_t z=TIFFStripSize(t); std::vector<uint8_t> b(z);
          for(int f=0;f<g.nf;f++){ TIFFSetDirectory(t,f); for(int s=0;s<g.ny;s++) TIFFReadEncodedStrip(t,s,b.data(),z);} TIFFClose(t); }

        std::vector<double> A,B,C;
        for(int r=0;r<nreps;r++){
          for(int which=0; which<3; which++){
            int arm = (r%2==0) ? which : 2-which;     // alternate order across reps
            auto t0=std::chrono::high_resolution_clock::now();
            if(arm<2){
                #pragma omp parallel num_threads(nthreads)
                { TIFF*t=TIFFOpen(mv.c_str(),"r"); tmsize_t z=TIFFStripSize(t);
                  std::vector<uint16_t> sb(z/2);
                  #pragma omp for schedule(dynamic,1)
                  for(int f=0;f<g.nf;f++){ TIFFSetDirectory(t,f);
                    for(int s=0;s<g.ny;s++){ TIFFReadEncodedStrip(t,s,sb.data(),z);
                      size_t o=(size_t)f*g.nx*g.ny+(size_t)s*g.nx;
                      if(arm==0) for(int c=0;c<g.nx;c++) hf[o+c]=(float)sb[c];
                      else       std::memcpy(&hu[o],sb.data(),rowb); } }
                  TIFFClose(t); }
                if(arm==0) CK(cudaMemcpy(dF,hf.data(),bf32,cudaMemcpyHostToDevice));
                else { CK(cudaMemcpy(dU,hu.data(),bu16,cudaMemcpyHostToDevice));
                       u16tof<<<(npx+255)/256,256>>>(dU,dF2,npx,(size_t)g.nx,g.nx,g.ny); CK(cudaDeviceSynchronize()); }
            } else {
                #pragma omp parallel num_threads(nthreads)
                { TIFF*t=TIFFOpen(mv.c_str(),"r");
                  #pragma omp for schedule(dynamic,1)
                  for(int f=0;f<g.nf;f++){ TIFFSetDirectory(t,f); size_t cur=0;
                    for(int s=0;s<g.ny;s++){ size_t rs=g.raw[f][s], slot=stripSlotOffset(cur,ia);
                      TIFFReadRawStrip(t,s,(uint8_t*)hstage+fbase[f]+slot,(tmsize_t)rs);
                      if(!zlibWrapperIsUsable((uint8_t*)hstage+fbase[f]+slot,rs)){ std::printf("bad zlib\n"); std::exit(2);}
                      size_t ch=(size_t)f*g.ny+s;
                      hCp[ch]=(uint8_t*)dC+fbase[f]+slot+2; hCs[ch]=rs-6;
                      hDp[ch]=(uint8_t*)dU+ch*pitchb; cur=slot+rs; } }
                  TIFFClose(t); }
                CK(cudaMemcpyAsync(dC,hstage,stage,cudaMemcpyHostToDevice,st));
                CK(cudaMemcpyAsync(dCp,hCp.data(),chunks*8,cudaMemcpyHostToDevice,st));
                CK(cudaMemcpyAsync(dCs,hCs.data(),chunks*8,cudaMemcpyHostToDevice,st));
                CK(cudaMemcpyAsync(dDp,hDp.data(),chunks*8,cudaMemcpyHostToDevice,st));
                CK(cudaMemcpyAsync(dDs,hDs.data(),chunks*8,cudaMemcpyHostToDevice,st));
                nvcompBatchedDeflateDecompressAsync((const void*const*)dCp,dCs,dDs,dAs,chunks,dT,tmpb,dDp,
                    nvcompBatchedDeflateDecompressDefaultOpts,dSt,st);
                CK(cudaMemcpyAsync(hSt.data(),dSt,chunks*sizeof(nvcompStatus_t),cudaMemcpyDeviceToHost,st));
                CK(cudaMemcpyAsync(hAs.data(),dAs,chunks*8,cudaMemcpyDeviceToHost,st));
                CK(cudaStreamSynchronize(st));
                for(size_t c=0;c<chunks;c++) if(hSt[c]!=nvcompSuccess||hAs[c]!=rowb){ std::printf("nvcomp fail\n"); std::exit(3);}
                u16tof<<<(npx+255)/256,256,0,st>>>(dU,dF2,npx,pitch_u16,g.nx,g.ny);
                CK(cudaStreamSynchronize(st));
            }
            auto t1=std::chrono::high_resolution_clock::now();
            (arm==0?A:arm==1?B:C).push_back(ms(t0,t1));
          }
        }
        auto med=[](std::vector<double> v){ std::sort(v.begin(),v.end()); return v[v.size()/2]; };
        auto mn =[](const std::vector<double>&v){ return *std::min_element(v.begin(),v.end()); };
        std::string nm=mv.substr(mv.find_last_of("/")+1);
        std::printf("%-34s %8.1f %8.1f %8.1f %8.1f %8.1f %8.1f\n",nm.c_str(),med(A),mn(A),med(B),mn(B),med(C),mn(C));
        sA+=med(A); sB+=med(B); sC+=med(C); nok++;
        cudaFree(dF);cudaFree(dF2);cudaFree(dU);cudaFree(dC);cudaFreeHost(hstage);
        cudaFree(dCp);cudaFree(dCs);cudaFree(dDp);cudaFree(dDs);cudaFree(dAs);cudaFree(dSt);
        if(dT)cudaFree(dT); cudaStreamDestroy(st);
    }
    std::printf("\nmedian totals over %d movies (ms): A=%.1f  B=%.1f  C=%.1f\n",nok,sA,sB,sC);
    std::printf("C vs A: %.2fx    C vs B: %.2fx\n", sA/sC, sB/sC);
    return 0;
}
