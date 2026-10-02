// Opt-in scheduling experiment. The reference calls the production movie session.
// This file is not linked into motioncorr and does not define an acceptance gate.
#include "src/acc/cuda/cuda_movie_session.h"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <vector>

namespace {
void ck(cudaError_t e) {
    if (e != cudaSuccess) throw std::runtime_error(cudaGetErrorString(e));
}
void ck(cufftResult e) {
    if (e != CUFFT_SUCCESS) throw std::runtime_error("cuFFT status " + std::to_string(e));
}
using Clock = std::chrono::steady_clock;
double ms(Clock::time_point a) {
    return std::chrono::duration<double, std::milli>(Clock::now() - a).count();
}
struct Buffer {
    void *p = nullptr;
    ~Buffer() { if (p) cudaFree(p); }
    void alloc(size_t n) { ck(cudaMalloc(&p, std::max(size_t(1), n))); }
    float *real() { return static_cast<float*>(p); }
    cufftComplex *complex() { return static_cast<cufftComplex*>(p); }
};
struct Plan {
    cufftHandle h = 0;
    size_t bytes = 0;
    ~Plan() { if (h) cufftDestroy(h); }
    void init(int x, int y, int batch, cufftType type) {
        ck(cufftCreate(&h));
        ck(cufftSetAutoAllocation(h, 0));
        int n[] = {y, x};
        int real = x*y, fourier = y*(x/2+1);
        ck(cufftMakePlanMany(h, 2, n, nullptr, 1,
            type == CUFFT_R2C ? real : fourier, nullptr, 1,
            type == CUFFT_R2C ? fourier : real, type, batch, &bytes));
    }
};
__device__ float signal(size_t i) {
    unsigned h = unsigned(i) * 747796405u + 2891336453u;
    h = ((h >> ((h >> 28u) + 4u)) ^ h) * 277803737u;
    return float((h ^ (h >> 22u)) & 65535u) / 256.0f - 64.0f;
}
__global__ void fill(float *p, size_t n) {
    size_t i = size_t(blockIdx.x)*blockDim.x + threadIdx.x;
    if (i < n) p[i] = signal(i);
}
// Same two scalar multiplies as production scaleComplexKernel.
__global__ void scale(cufftComplex *p, size_t n, float s) {
    size_t i = size_t(blockIdx.x)*blockDim.x + threadIdx.x;
    if (i < n) { p[i].x *= s; p[i].y *= s; }
}
struct Difference {
    unsigned long long bits = 0, nonfinite = 0;
    unsigned long long digest = 0;
    unsigned max_abs = 0;
    double sum_sq = 0;
};
__global__ void compare(const float *p, const float *q, size_t n, Difference *d) {
    size_t i = size_t(blockIdx.x)*blockDim.x + threadIdx.x;
    __shared__ Difference block[256];
    Difference v;
    if (i < n) {
        float a = p[i], b = q ? q[i] : signal(i);
        v.nonfinite = !isfinite(a) || !isfinite(b);
        v.bits = __float_as_uint(a) != __float_as_uint(b);
        double delta = double(a)-b;
        v.max_abs = __float_as_uint(float(fabs(delta)));
        v.sum_sq = delta*delta;
        unsigned long long h = (static_cast<unsigned long long>(__float_as_uint(a)) << 32) ^ i;
        h = (h ^ (h >> 30)) * 0xbf58476d1ce4e5b9ull;
        h = (h ^ (h >> 27)) * 0x94d049bb133111ebull;
        v.digest = h ^ (h >> 31);
    }
    block[threadIdx.x] = v;
    __syncthreads();
    for (unsigned stride=128;stride;stride/=2) {
        if (threadIdx.x < stride) {
            Difference &a=block[threadIdx.x], &b=block[threadIdx.x+stride];
            a.bits+=b.bits; a.nonfinite+=b.nonfinite; a.digest^=b.digest;
            a.max_abs=max(a.max_abs,b.max_abs); a.sum_sq+=b.sum_sq;
        }
        __syncthreads();
    }
    if (!threadIdx.x) {
        atomicAdd(&d->bits,block[0].bits); atomicAdd(&d->nonfinite,block[0].nonfinite);
        atomicXor(&d->digest,block[0].digest); atomicMax(&d->max_abs,block[0].max_abs);
        atomicAdd(&d->sum_sq,block[0].sum_sq);
    }
}
Difference difference(float *p, float *q, size_t n, Buffer &scratch) {
    ck(cudaMemset(scratch.p, 0, sizeof(Difference)));
    compare<<<(n+255)/256,256>>>(p,q,n,static_cast<Difference*>(scratch.p));
    ck(cudaGetLastError());
    Difference d;
    ck(cudaMemcpy(&d,scratch.p,sizeof(d),cudaMemcpyDeviceToHost));
    if (d.nonfinite) throw std::runtime_error("nonfinite comparison");
    return d;
}
void print_diff(const char *name, Difference d, size_t n) {
    float maximum;
    std::memcpy(&maximum, &d.max_abs, sizeof(maximum));
    std::cout << ",\"" << name << "_different\":" << d.bits
              << ",\"" << name << "_max_abs\":" << maximum
              << ",\"" << name << "_rmse\":" << std::sqrt(d.sum_sq/n);
}
struct Candidate {
    int x,y,frames,batch;
    size_t nr,nc,work_bytes=0;
    bool per_frame;
    Buffer real, fourier, tile, work;
    Plan r2c, c2r, tail_r2c, tail_c2r; // destroyed before workspace
    Candidate(int x_,int y_,int f,int b,bool sync)
        : x(x_),y(y_),frames(f),batch(std::min(b,f)),nr(size_t(x)*y),
          nc(size_t(x/2+1)*y),per_frame(sync) {}
    void init() {
        real.alloc(nr*frames*sizeof(float));
        fourier.alloc(nc*frames*sizeof(cufftComplex));
        tile.alloc(nc*batch*sizeof(cufftComplex));
        r2c.init(x,y,batch,CUFFT_R2C); c2r.init(x,y,batch,CUFFT_C2R);
        work_bytes = std::max(r2c.bytes,c2r.bytes);
        if (frames%batch) {
            tail_r2c.init(x,y,frames%batch,CUFFT_R2C);
            tail_c2r.init(x,y,frames%batch,CUFFT_C2R);
            work_bytes = std::max({work_bytes,tail_r2c.bytes,tail_c2r.bytes});
        }
        work.alloc(work_bytes);
        for (Plan *p : {&r2c,&c2r,&tail_r2c,&tail_c2r})
            if (p->h) ck(cufftSetWorkArea(p->h,work.p));
    }
    void forward() {
        for(int f=0;f<frames;f+=batch) {
            Plan &p = frames-f < batch ? tail_r2c : r2c;
            ck(cufftExecR2C(p.h,real.real()+f*nr,fourier.complex()+f*nc));
            if (per_frame) ck(cudaDeviceSynchronize());
        }
        scale<<<(nc*frames+255)/256,256>>>(fourier.complex(),nc*frames,1.0f/(float(x)*y));
        ck(cudaGetLastError()); ck(cudaDeviceSynchronize());
    }
    void inverse() {
        for(int f=0;f<frames;f+=batch) {
            const int count=std::min(batch,frames-f);
            Plan &p = count < batch ? tail_c2r : c2r;
            if (per_frame)
                ck(cudaMemcpy(tile.p,fourier.complex()+f*nc,nc*count*sizeof(cufftComplex),cudaMemcpyDeviceToDevice));
            else
                ck(cudaMemcpyAsync(tile.p,fourier.complex()+f*nc,nc*count*sizeof(cufftComplex),cudaMemcpyDeviceToDevice,0));
            ck(cufftExecC2R(p.h,tile.complex(),real.real()+f*nr));
            if (per_frame) ck(cudaDeviceSynchronize());
        }
        ck(cudaDeviceSynchronize());
    }
    size_t owned() { return nr*frames*4+nc*frames*8+nc*batch*8+std::max(size_t(1),work_bytes); }
};
}

int main(int argc,char **argv) try {
    if (argc!=5) throw std::runtime_error("usage: movie_fft_bench nx ny frames rounds");
    int x=std::stoi(argv[1]),y=std::stoi(argv[2]),f=std::stoi(argv[3]),rounds=std::stoi(argv[4]);
    if (x<2 || y<2 || f<1 || rounds<1 || size_t(x)*y>100000000)
        throw std::runtime_error("invalid bounded benchmark dimensions");
    ck(cudaSetDevice(0)); ck(cudaFree(nullptr));
    size_t nr=size_t(x)*y*f,nc=size_t(x/2+1)*y*f;
    Buffer ref_real,ref_fft,diff;
    ref_real.alloc(nr*4); ref_fft.alloc(nc*8); diff.alloc(sizeof(Difference));
    std::ostringstream log;
    auto reset=[&](float *p) {
        fill<<<(nr+255)/256,256>>>(p,nr);
        ck(cudaGetLastError()); ck(cudaDeviceSynchronize());
    };
    {
        CudaMovieSession reference(x,y,f,0,log);
        if (!reference.initialize()) throw std::runtime_error(log.str());
        reset(reference.getDeviceRealFrames());
        if (!reference.computeGlobalForwardFFT() || !reference.computeGlobalInverseFFT())
            throw std::runtime_error(log.str());
        ck(cudaMemcpy(ref_real.p,reference.getDeviceRealFrames(),nr*4,cudaMemcpyDeviceToDevice));
        ck(cudaMemcpy(ref_fft.p,reference.getDeviceFourierFrames(),nc*8,cudaMemcpyDeviceToDevice));
    }
    // A deliberately different signal must be observed by the comparator.
    Buffer control; control.alloc(nr*4); reset(control.real());
    ck(cudaMemset(control.p,0,4));
    if (!difference(control.real(),nullptr,nr,diff).bits)
        throw std::runtime_error("comparison negative control failed");
    ck(cudaFree(control.p)); control.p=nullptr;
    const char *names[]={"production","mirror_b1","stage_b1","stage_b2","stage_b4"};
    for(int round=0;round<rounds;++round) {
        std::vector<int> order={0,1,2,3,4};
        std::rotate(order.begin(),order.begin()+round%5,order.end());
        if (round%2) std::reverse(order.begin(),order.end());
        for(int arm:order) {
            auto start=Clock::now();
            std::unique_ptr<CudaMovieSession> product;
            std::unique_ptr<Candidate> candidate;
            float *r; cufftComplex *c;
            if (arm==0) {
                product=std::make_unique<CudaMovieSession>(x,y,f,0,log);
                if (!product->initialize()) throw std::runtime_error(log.str());
                r=product->getDeviceRealFrames(); c=product->getDeviceFourierFrames();
            } else {
                candidate=std::make_unique<Candidate>(x,y,f,arm<3?1:(arm==3?2:4),arm==1);
                candidate->init(); r=candidate->real.real(); c=candidate->fourier.complex();
            }
            ck(cudaDeviceSynchronize()); double setup=ms(start);
            auto forward=[&]() {
                if (product) { if(!product->computeGlobalForwardFFT()) throw std::runtime_error(log.str()); }
                else candidate->forward();
            };
            auto inverse=[&]() {
                if (product) { if(!product->computeGlobalInverseFFT()) throw std::runtime_error(log.str()); }
                else candidate->inverse();
            };
            reset(r); forward(); inverse(); // per-plan warmup, not measured
            reset(r); start=Clock::now(); forward(); double fw=ms(start);
            // Check spectrum before C2R, then check that C2R preserved it below.
            Difference pre=difference(reinterpret_cast<float*>(c),ref_fft.real(),nc*2,diff);
            start=Clock::now(); inverse(); double inv=ms(start);
            Difference real=difference(r,ref_real.real(),nr,diff);
            Difference fourier=difference(reinterpret_cast<float*>(c),ref_fft.real(),nc*2,diff);
            Difference rt=difference(r,nullptr,nr,diff);
            if (arm<=2 && (real.bits || fourier.bits)) throw std::runtime_error("batch-one control differs from production");
            if (pre.digest!=fourier.digest)
                throw std::runtime_error("Fourier preservation check failed");
            std::cout << "{\"nx\":"<<x<<",\"ny\":"<<y<<",\"frames\":"<<f
                      <<",\"round\":"<<round<<",\"arm\":\""<<names[arm]<<"\",\"setup_ms\":"<<setup
                      <<",\"forward_ms\":"<<fw<<",\"inverse_ms\":"<<inv;
            if(candidate) std::cout<<",\"owned_bytes\":"<<candidate->owned()<<",\"work_bytes\":"<<candidate->work_bytes;
            print_diff("real",real,nr); print_diff("fourier",fourier,nc*2); print_diff("roundtrip",rt,nr);
            std::cout << "}" << std::endl;
        }
    }
    return 0;
} catch(const std::exception &e) { std::cerr<<e.what()<<std::endl; return 1; }
