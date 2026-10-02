// Measures H2D on THIS device for the exact payload MotionCorr moves per movie
// (1,434,806,904 B in 24 frame-sized chunks), pageable vs pinned, same chunking
// and the same synchronous cudaMemcpy the application uses.
#include <cstdio>
#include <cstdlib>
#include <cuda_runtime.h>
#define CK(x) do{cudaError_t e=(x); if(e!=cudaSuccess){printf("ERR %s @%d\n",cudaGetErrorString(e),__LINE__);exit(1);} }while(0)

int main(){
    const size_t CHUNK = 59783620;   // ~57 MiB, one 3838x5760 float frame
    const int    N     = 24;
    const size_t TOT   = CHUNK*(size_t)N;
    void *d; CK(cudaMalloc(&d, CHUNK));
    cudaEvent_t a,b; CK(cudaEventCreate(&a)); CK(cudaEventCreate(&b));

    for (int mode=0; mode<2; ++mode){
        const char *nm = mode? "PINNED  (cudaHostAlloc)" : "PAGEABLE (malloc)";
        void *h;
        if (mode) CK(cudaHostAlloc(&h, CHUNK, cudaHostAllocDefault));
        else      h = malloc(CHUNK);
        memset(h, 1, CHUNK);                       // first-touch, like decoded frames
        CK(cudaMemcpy(d,h,CHUNK,cudaMemcpyHostToDevice));   // warm
        float best=1e30f, sum=0;
        for (int r=0;r<3;++r){
            CK(cudaEventRecord(a));
            for (int i=0;i<N;++i) CK(cudaMemcpy(d,h,CHUNK,cudaMemcpyHostToDevice));
            CK(cudaEventRecord(b)); CK(cudaEventSynchronize(b));
            float ms; CK(cudaEventElapsedTime(&ms,a,b));
            sum+=ms; if(ms<best) best=ms;
        }
        printf("  %-24s %12zu B in %d chunks: best %7.2f ms = %5.2f GB/s   (mean %7.2f ms = %5.2f GB/s)\n",
               nm, TOT, N, best, TOT/(best*1e6), sum/3, TOT/((sum/3)*1e6));
        if (mode) CK(cudaFreeHost(h)); else free(h);
    }
    CK(cudaFree(d));
    return 0;
}
