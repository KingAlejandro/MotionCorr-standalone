// Compile this native test as CUDA. The independent reference retains the old
// framewise synchronization, identical batch-1/manual-work plans and exact scale
// kernel. Injection replaces returned codes AFTER real drains, never poisons
// hardware, and is confined to this executable's GNU link wrappers.
#include "src/acc/cuda/cuda_movie_session.h"
#include <cuda_runtime.h>
#include <cufft.h>
#include <algorithm>
#include <cstring>
#include <iostream>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
enum Fault { NONE, SYNC_FATAL, R2C_FAIL_THEN_FATAL, C2R_FAIL_THEN_FATAL,
             COPY_FAIL_THEN_FATAL, INITIAL_MALLOC };
bool active = false, fired = false, queued = false, drain_after_queued = false;
bool pending_fatal = false;
Fault fault = NONE;
int ordinal = 0, syncs = 0, forward_execs = 0, inverse_execs = 0;
int copies = 0, allocations = 0, launches = 0;
std::string trace;
std::set<void*> owned_buffers;
std::set<cufftHandle> owned_plans;
size_t stale = 0;
void arm(Fault kind = NONE, int at = 0) {
    fault = kind; ordinal = at; syncs = forward_execs = inverse_execs = 0;
    copies = allocations = launches = 0; fired = queued = drain_after_queued = false;
    pending_fatal = false; trace.clear(); active = true;
}
void require(bool yes, const char *message) { if (!yes) throw std::runtime_error(message); }
void checked(cudaError_t result) { require(result == cudaSuccess, "test CUDA operation failed"); }
void checked(cufftResult result) { require(result == CUFFT_SUCCESS, "test cuFFT operation failed"); }
void empty() {
    require(owned_buffers.empty() && owned_plans.empty() && stale == 0,
            "session owners leaked or double-released");
}
}
extern "C" {
cudaError_t __real_cudaMalloc(void**, size_t);
cudaError_t __real_cudaFree(void*);
cufftResult __real_cufftCreate(cufftHandle*);
cufftResult __real_cufftDestroy(cufftHandle);
cufftResult __real_cufftExecR2C(cufftHandle, cufftReal*, cufftComplex*);
cufftResult __real_cufftExecC2R(cufftHandle, cufftComplex*, cufftReal*);
cudaError_t __real_cudaMemcpy(void*, const void*, size_t, cudaMemcpyKind);
cudaError_t __real_cudaDeviceSynchronize();
cudaError_t __real_cudaGetLastError();
cudaError_t __wrap_cudaMalloc(void **p, size_t n) {
    if (active && ++allocations == ordinal && fault == INITIAL_MALLOC) {
        *p = nullptr; fired = true; return cudaErrorMemoryAllocation;
    }
    const auto result = __real_cudaMalloc(p,n);
    if (active && result == cudaSuccess) owned_buffers.insert(*p);
    return result;
}
cudaError_t __wrap_cudaFree(void *p) {
    const auto result = __real_cudaFree(p);
    if (active && p && result == cudaSuccess && !owned_buffers.erase(p)) ++stale;
    return result;
}
cufftResult __wrap_cufftCreate(cufftHandle *p) {
    const auto result = __real_cufftCreate(p);
    if (active && result == CUFFT_SUCCESS) owned_plans.insert(*p);
    return result;
}
cufftResult __wrap_cufftDestroy(cufftHandle p) {
    const auto result = __real_cufftDestroy(p);
    if (active && result == CUFFT_SUCCESS && !owned_plans.erase(p)) ++stale;
    return result;
}
cufftResult __wrap_cufftExecR2C(cufftHandle p, cufftReal *in, cufftComplex *out) {
    if (active) {
        ++forward_execs; trace += 'F';
        if (fault == R2C_FAIL_THEN_FATAL && forward_execs == ordinal) {
            fired = pending_fatal = true; trace += '!';
            (void)__real_cudaGetLastError(); // The immediate return has a clean pending slot.
            return CUFFT_EXEC_FAILED;
        }
    }
    const auto result = __real_cufftExecR2C(p,in,out);
    if (active && result == CUFFT_SUCCESS) queued = true;
    return result;
}
cufftResult __wrap_cufftExecC2R(cufftHandle p, cufftComplex *in, cufftReal *out) {
    if (active) {
        ++inverse_execs; trace += 'I';
        if (fault == C2R_FAIL_THEN_FATAL && inverse_execs == ordinal) {
            fired = pending_fatal = true; trace += '!';
            (void)__real_cudaGetLastError();
            return CUFFT_EXEC_FAILED;
        }
    }
    const auto result = __real_cufftExecC2R(p,in,out);
    if (active && result == CUFFT_SUCCESS) queued = true;
    return result;
}
cudaError_t __wrap_cudaMemcpy(void *out, const void *in, size_t n, cudaMemcpyKind kind) {
    if (active && kind == cudaMemcpyDeviceToDevice) {
        ++copies; trace += 'C';
        if (fault == COPY_FAIL_THEN_FATAL && copies == ordinal) {
            fired = pending_fatal = true; trace += '!';
            (void)__real_cudaGetLastError();
            return cudaErrorMemoryAllocation;
        }
    }
    return __real_cudaMemcpy(out,in,n,kind);
}
cudaError_t __wrap_cudaDeviceSynchronize() {
    const auto result = __real_cudaDeviceSynchronize();
    if (!active) return result;
    ++syncs; trace += 'S';
    if (queued) drain_after_queued = true;
    queued = false;
    if (result == cudaSuccess &&
        (pending_fatal || (fault == SYNC_FATAL && syncs == ordinal))) {
        fired = true; pending_fatal = false;
        (void)__real_cudaGetLastError();
        return cudaErrorIllegalAddress;
    }
    return result;
}
cudaError_t __wrap_cudaGetLastError() {
    if (active) ++launches;
    return __real_cudaGetLastError();
}
}
namespace {
__global__ void referenceScale(cufftComplex *data, size_t count, float scale) {
    const size_t idx = (size_t)blockIdx.x * blockDim.x + threadIdx.x;
    if (idx < count) { data[idx].x *= scale; data[idx].y *= scale; }
}
struct Geometry { int x, y, frames; };
std::vector<float> input(const Geometry &g) {
    std::vector<float> values((size_t)g.x*g.y*g.frames);
    for (size_t i=0; i<values.size(); ++i)
        values[i] = (float)((int)((i*37+i/(g.x*g.y)*11)%257)-128)*.125f;
    return values;
}
template<class T> std::vector<T> download(const T *device, size_t n) {
    const bool was_active = active; active = false;
    std::vector<T> result(n);
    checked(cudaMemcpy(result.data(), device, n*sizeof(T), cudaMemcpyDeviceToHost));
    active = was_active; return result;
}
template<class T> void same(const std::vector<T> &a, const std::vector<T> &b,
                           const char *message) {
    require(a.size()==b.size() && std::memcmp(a.data(), b.data(), a.size()*sizeof(T))==0,
            message);
}
struct Reference {
    Geometry g;
    float *real = nullptr;
    cufftComplex *fourier = nullptr, *tile = nullptr;
    void *work = nullptr;
    cufftHandle forward=0, inverse=0;
    std::vector<cufftComplex> unscaled, scaled;
    std::vector<float> reconstructed;
    explicit Reference(Geometry geometry): g(geometry) {
        active = false;
        const size_t nr=(size_t)g.x*g.y*g.frames;
        const size_t nc=(size_t)(g.x/2+1)*g.y*g.frames;
        checked(cudaMalloc(&real,nr*sizeof(float)));
        checked(cudaMalloc(&fourier,nc*sizeof(cufftComplex)));
        checked(cudaMalloc(&tile,(nc/g.frames)*sizeof(cufftComplex)));
        int n[2]={g.y,g.x}; size_t wf=0,wi=0;
        checked(cufftCreate(&forward)); checked(cufftSetAutoAllocation(forward,0));
        checked(cufftMakePlanMany(forward,2,n,nullptr,1,g.x*g.y,nullptr,1,
                                g.y*(g.x/2+1),CUFFT_R2C,1,&wf));
        checked(cufftCreate(&inverse)); checked(cufftSetAutoAllocation(inverse,0));
        checked(cufftMakePlanMany(inverse,2,n,nullptr,1,g.y*(g.x/2+1),nullptr,1,
                                g.x*g.y,CUFFT_C2R,1,&wi));
        checked(cudaMalloc(&work,std::max((size_t)1,std::max(wf,wi))));
        checked(cufftSetWorkArea(forward,work)); checked(cufftSetWorkArea(inverse,work));
        const auto values=input(g);
        checked(cudaMemcpy(real,values.data(),nr*sizeof(float),cudaMemcpyHostToDevice));
        for (int frame=0;frame<g.frames;++frame) {
            checked(cufftExecR2C(forward,real+(nr/g.frames)*frame,
                                fourier+(nc/g.frames)*frame));
            checked(cudaDeviceSynchronize()); // predecessor's per-frame ordering
        }
        unscaled=download(fourier,nc);
        const float inv_size=1.0f/((float)g.x*g.y);
        referenceScale<<<(nc+255)/256,256>>>(fourier,nc,inv_size);
        checked(cudaGetLastError()); checked(cudaDeviceSynchronize());
        scaled=download(fourier,nc);
        for (int frame=0;frame<g.frames;++frame) {
            checked(cudaMemcpy(tile,fourier+(nc/g.frames)*frame,
                               (nc/g.frames)*sizeof(cufftComplex),cudaMemcpyDeviceToDevice));
            checked(cufftExecC2R(inverse,tile,real+(nr/g.frames)*frame));
            checked(cudaDeviceSynchronize());
        }
        reconstructed=download(real,nr);
        same(scaled,download(fourier,nc),"reference preservation tile altered Fourier stack");
    }
    ~Reference() {
        const bool old=active; active=false;
        cufftDestroy(inverse); cufftDestroy(forward);
        cudaFree(work); cudaFree(tile); cudaFree(fourier); cudaFree(real); active=old;
    }
};
struct Fixture {
    Geometry g;
    std::ostringstream log;
    CudaMovieSession movie;
    explicit Fixture(Geometry geometry): g(geometry), movie(g.x,g.y,g.frames,0,log) {
        arm(); require(movie.initialize(),"session initialization failed");
        active=false;
        const auto values=input(g);
        checked(cudaMemcpy(movie.getDeviceRealFrames(),values.data(),values.size()*sizeof(float),
                           cudaMemcpyHostToDevice));
    }
    void release() { active=true; movie.release(); empty(); active=false; }
    ~Fixture() { const bool old=active; active=true; movie.release(); active=old; }
};
void healthy() {
    for (Geometry g : {Geometry{32,40,4}, Geometry{64,48,8}, Geometry{80,72,3}}) {
        Reference reference(g); Fixture f(g);
        arm(); require(f.movie.computeGlobalForwardFFT(),"healthy forward failed");
        require(forward_execs==g.frames && inverse_execs==0 && copies==0 && syncs==2 &&
                launches==1 && trace==std::string(g.frames,'F')+"SS",
                "forward ordering/counts changed or per-frame waits remain");
        same(reference.scaled,download(f.movie.getDeviceFourierFrames(),reference.scaled.size()),
             "forward exact payload differs from synchronized reference");
        arm(); require(f.movie.computeGlobalInverseFFT(),"healthy inverse failed");
        std::string expected; for(int i=0;i<g.frames;++i)expected+="CI"; expected+='S';
        require(forward_execs==0 && inverse_execs==g.frames && copies==g.frames &&
                syncs==1 && trace==expected,"inverse tile ordering/counts changed");
        same(reference.reconstructed,download(f.movie.getDeviceRealFrames(),reference.reconstructed.size()),
             "inverse exact payload differs from synchronized reference");
        same(reference.scaled,download(f.movie.getDeviceFourierFrames(),reference.scaled.size()),
             "inverse tile overwrote resident Fourier frames");
        require(!f.movie.getFailureState().hasFailed(),"healthy transforms recorded failure");
        f.release();
    }
    std::cout<<"PASS: 3 multi-frame exact forward/inverse/preserved-stack controls; forward2/inverse1 sync boundaries\n";
}
void poisonedRefusal(Fixture &f) {
    const auto &failure=f.movie.getFailureState();
    require(failure.isPoisoned() && failure.fatalError()==cudaErrorIllegalAddress,
            "fatal transform status lost");
    checked(cudaGetLastError()); // returned-code injection kept the actual runtime slot clean
    arm();
    require(!f.movie.computeGlobalForwardFFT() && !f.movie.computeGlobalInverseFFT() &&
            forward_execs==0 && inverse_execs==0 && copies==0 && syncs==0 && launches==0,
            "poisoned transform dispatched/reached a later stage");
}
void boundaryFailures(bool forward=true, bool inverse=true) {
    const Geometry g={32,40,4}; Reference reference(g);
    if (forward) for (int boundary : {1,2}) {
        Fixture f(g); arm(SYNC_FATAL,boundary);
        require(!f.movie.computeGlobalForwardFFT() && fired && syncs==boundary &&
                forward_execs==g.frames && launches==(boundary==1?0:1),
                "forward boundary fault did not stop at correct stage");
        const auto &failure=f.movie.getFailureState();
        require(std::string(failure.firstStage())=="computeGlobalForwardFFT" &&
                std::string(failure.fatalStage())=="computeGlobalForwardFFT",
                "forward boundary error attributed to a later stage");
        same(boundary==1?reference.unscaled:reference.scaled,
             download(f.movie.getDeviceFourierFrames(),reference.scaled.size()),
             "failed FFT boundary incorrectly reached/skipped scaling");
        poisonedRefusal(f); f.release();
    }
    if (inverse) {
        Fixture f(g); arm(); require(f.movie.computeGlobalForwardFFT(),"inverse precondition");
        arm(SYNC_FATAL,1);
        require(!f.movie.computeGlobalInverseFFT() && fired && syncs==1 &&
                inverse_execs==g.frames && copies==g.frames,"inverse boundary fault not observed");
        require(std::string(f.movie.getFailureState().fatalStage())=="computeGlobalInverseFFT",
                "inverse boundary attribution lost");
        poisonedRefusal(f); f.release();
    }
    std::cout<<"PASS: "<<(forward?2:0)+(inverse?1:0)<<" checked end-boundary faults (cleared-slot injected codes), exact scaling boundary and fatal refusals\n";
}
void immediateFailures(Fault selected=NONE) {
    const Geometry g={32,40,4};
    for (Fault kind : {R2C_FAIL_THEN_FATAL,C2R_FAIL_THEN_FATAL,COPY_FAIL_THEN_FATAL}) {
        if (selected!=NONE && selected!=kind) continue;
        Fixture f(g);
        if(kind!=R2C_FAIL_THEN_FATAL) { arm(); require(f.movie.computeGlobalForwardFFT(),"inverse precondition"); }
        arm(kind,2);
        const bool result=kind==R2C_FAIL_THEN_FATAL
            ?f.movie.computeGlobalForwardFFT():f.movie.computeGlobalInverseFFT();
        const std::string expected=kind==R2C_FAIL_THEN_FATAL?"FF!S":
                                   kind==C2R_FAIL_THEN_FATAL?"CICI!S":"CIC!S";
        require(!result && fired && syncs==1 && drain_after_queued && !pending_fatal &&
                !queued && launches==0 && trace==expected,
                "immediate transform/copy failure returned without draining earlier queued work");
        const auto &failure=f.movie.getFailureState();
        const char *stage=kind==R2C_FAIL_THEN_FATAL?"computeGlobalForwardFFT":"computeGlobalInverseFFT";
        require(std::string(failure.firstStage())==stage && std::string(failure.fatalStage())==stage,
                "immediate failure or drain attributed to wrong stage");
        require(kind==COPY_FAIL_THEN_FATAL
                ?failure.firstError()==cudaErrorMemoryAllocation
                :failure.firstCufftError()==CUFFT_EXEC_FAILED,
                "drain replaced the original failure provenance");
        poisonedRefusal(f); f.release();
    }
    std::cout<<"PASS: frame2 R2C/C2R/D2D failures drain prior submissions, retain first cause+sync-only fatal, no redispatch\n";
}
void uninitialized() {
    const Geometry g={32,40,4}; std::ostringstream log;
    CudaMovieSession movie(g.x,g.y,g.frames,0,log);
    arm(INITIAL_MALLOC,1);
    require(!movie.initialize() && fired && movie.getFailureState().hasFailed(),
            "initialization negative did not fire");
    arm(); require(!movie.computeGlobalForwardFFT() && !movie.computeGlobalInverseFFT() &&
                   forward_execs==0 && inverse_execs==0 && copies==0 && syncs==0,
                   "uninitialized session dispatched transforms");
    movie.release(); empty(); active=false;
    std::cout<<"PASS: failed initialization refuses both transforms\n";
}
}
int main(int argc, char **argv) {
    if(cudaSetDevice(0)!=cudaSuccess || cudaFree(nullptr)!=cudaSuccess) {
        std::cerr<<"Native CUDA device0 required\n"; return 1;
    }
    std::string selection="all";
    if(argc==3 && std::string(argv[1])=="--case") selection=argv[2];
    else if(argc!=1) { std::cerr<<"Usage: cuda_global_fft_sync [--case NAME]\n";return 2; }
    try {
        if(selection=="all") { healthy(); boundaryFailures(); immediateFailures(); uninitialized(); }
        else if(selection=="healthy") healthy();
        else if(selection=="forward-boundary") boundaryFailures(true,false);
        else if(selection=="inverse-boundary") boundaryFailures(false,true);
        else if(selection=="forward-immediate") immediateFailures(R2C_FAIL_THEN_FATAL);
        else if(selection=="inverse-immediate") immediateFailures(C2R_FAIL_THEN_FATAL);
        else if(selection=="inverse-copy") immediateFailures(COPY_FAIL_THEN_FATAL);
        else if(selection=="init") uninitialized();
        else { std::cerr<<"Unknown control case: "<<selection<<'\n';return 2; }
        empty();
    }
    catch(const std::exception &e) { std::cerr<<"FAIL: "<<e.what()<<'\n';return 1; }
    catch(RelionError &e) { std::cerr<<"Unexpected production exception: "<<e<<'\n';return 1; }
    std::cout<<"PASS: actual production global FFT synchronization matrix\n"; return 0;
}
