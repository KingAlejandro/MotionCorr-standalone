// Exact CPU controls for local-only phase updates. Reference retains upstream
// GPL notice in cpu_patch_phase_reference.h.
#include "src/motioncorr_runner.h"
#include "src/jaz/single_particle/new_ft.h"
#include "tests/cpu_patch_phase_reference.h"

#include <chrono>
#include <atomic>
#include <cstdio>
#include <cstring>
#include <sstream>
#include <stdexcept>
#include <vector>
#include <omp.h>

#ifdef MC_PHASE_COUNT_TRIG
static std::atomic<unsigned long long> phase_calls{0};
// Count one sine evaluation per phase, whether the compiler fuses sin+cos
// or leaves the macros.h fallback as separate calls (e.g. Debug/-O0).
extern "C" double __real_sin(double);
extern "C" float __real_sinf(float);
extern "C" double __wrap_sin(double a) {
    phase_calls.fetch_add(1,std::memory_order_relaxed); return __real_sin(a);
}
extern "C" float __wrap_sinf(float a) {
    phase_calls.fetch_add(1,std::memory_order_relaxed); return __real_sinf(a);
}
extern "C" void __real_sincos(double,double*,double*);
extern "C" void __real_sincosf(float,float*,float*);
extern "C" void __wrap_sincos(double a,double *s,double *c) {
    phase_calls.fetch_add(1,std::memory_order_relaxed); __real_sincos(a,s,c);
}
extern "C" void __wrap_sincosf(float a,float *s,float *c) {
    phase_calls.fetch_add(1,std::memory_order_relaxed); __real_sincosf(a,s,c);
}
#endif

struct MotioncorrRunnerTestAccess {
    static void shift(MotioncorrRunner &r, MultidimArray<fComplex> &f,
                      RFLOAT x, RFLOAT y, int wx = 0, int wy = 0) {
        r.shiftNonSquareImageInFourierTransform(f, x, y, wx, wy);
    }
    static bool align(MotioncorrRunner &r, std::vector<MultidimArray<fComplex>> &f,
                      int nx, int ny, std::vector<RFLOAT> &x, std::vector<RFLOAT> &y,
                      std::ostream &log, bool global, RFLOAT scaled_B) {
        return r.alignPatch(f, nx, ny, scaled_B, x, y, log, global);
    }
    static int ccfSize(MotioncorrRunner &r, int n, float scale) {
        int size=r.findGoodSize(int(n*scale));
        if(size>n) size=n;
        if(size%2) ++size;
        return size;
    }
};

namespace {
void require(bool ok, const char *message) {
    if (!ok) throw std::runtime_error(message);
}
bool same(const fComplex &a, const fComplex &b) { return std::memcmp(&a, &b, sizeof a) == 0; }
bool same(const std::vector<RFLOAT> &a, const std::vector<RFLOAT> &b) {
    return a.size() == b.size() && std::memcmp(a.data(), b.data(), a.size()*sizeof(RFLOAT)) == 0;
}
MultidimArray<fComplex> spectrum(int nfx, int ny) {
    MultidimArray<fComplex> f(ny, nfx);
    unsigned state = 471;
    for (int y = 0; y < ny; ++y) for (int x = 0; x < nfx; ++x) {
        state = state*1664525u + 1013904223u;
        const float a = (int(state >> 8) % 65537 - 32768) / 8192.0f;
        state = state*1664525u + 1013904223u;
        const float b = (int(state >> 8) % 65537 - 32768) / 8192.0f;
        DIRECT_A2D_ELEM(f,y,x) = fComplex(a,b);
    }
    DIRECT_A2D_ELEM(f,0,0) = fComplex(-0.0f,0.0f);
    return f;
}
void checkWindow(const MultidimArray<fComplex> &candidate,
                 const MultidimArray<fComplex> &reference,
                 const MultidimArray<fComplex> &initial, int wx, int wy) {
    const int ny = YSIZE(initial), nx = XSIZE(initial);
    for (int y = 0; y < ny; ++y) for (int x = 0; x < nx; ++x) {
        // The positive CCF Nyquist row belongs to the positive half, even
        // when the half-size is odd. Negative rows retain full-patch coords.
        const bool retained = x < wx && (y <= wy/2 || y > ny - (wy-1)/2 - 1);
        require(same(DIRECT_A2D_ELEM(candidate,y,x),
                     DIRECT_A2D_ELEM(retained ? reference : initial,y,x)),
                retained ? "retained phase differs from frozen full shift" : "discarded bin was changed");
    }
}
void phaseControls() {
    MotioncorrRunner r;
    int cases = 0;
    for (int nx : {7, 17, 33, 130}) for (int ny : {15,16,17,32,34}) {
        const auto initial = spectrum(nx,ny);
        for (int wx : {1, nx/2, nx}) for (int wy : {1,2,7,ny-1,ny}) {
            if (wy > ny) continue;
            auto full = initial, limited = initial;
            for (int k=0; k<5; ++k) {
                const RFLOAT sx = (k-2)*0.007139, sy = (3-k)*-0.009731;
                fullPhaseReference(full,sx,sy);
#ifdef MC_PHASE_COUNT_TRIG
                phase_calls=0;
#endif
                MotioncorrRunnerTestAccess::shift(r,limited,sx,sy,wx,wy);
#ifdef MC_PHASE_COUNT_TRIG
                require(phase_calls == static_cast<unsigned long long>(wx+wy),
                        "production phase table evaluations do not match window");
#endif
                checkWindow(limited,full,initial,wx,wy);
            }
            ++cases;
        }
        auto expected = initial, global = initial;
        fullPhaseReference(expected,0.0137,-0.0031);
#ifdef MC_PHASE_COUNT_TRIG
        phase_calls=0;
#endif
        MotioncorrRunnerTestAccess::shift(r,global,0.0137,-0.0031);
#ifdef MC_PHASE_COUNT_TRIG
        require(phase_calls == static_cast<unsigned long long>(nx+ny),
                "global default phase evaluations are not full geometry");
#endif
        require(std::memcmp(expected.data,global.data,nx*ny*sizeof(fComplex)) == 0,
                "default global full-spectrum helper changed");
    }
    std::printf("PASS %d window geometries, five successive phase updates; global defaults exact\n",cases);
#ifdef MC_PHASE_COUNT_TRIG
    std::puts("PASS GNU/ELF production sine count witness (separate or fused): window wx+wy, global nfx+nfy");
#else
    std::puts("SKIP (UNRUN) sine count witness: MC_PHASE_COUNT_TRIG is not compiled on this platform (needs GNU ld --wrap)");
#endif
}
void alignControls() {
    int cases=0, cropped_multi_iteration_cases=0;
    for (const auto shape : {std::pair<int,int>{256,256},{648,600},{194,198}})
    for (double downsample : {0.7,1.0,0.0})
    for (int groups : {2,4,7}) for (int threads : {1,4}) for (int iterations : {1,5}) {
        MotioncorrRunner r;
        r.use_gpu=false; r.gpu_id=0; r.n_threads=threads;
        r.ccf_downsample=downsample; r.max_iter=iterations;
        // A large B-factor weights the outer CCF columns below float rounding
        // in Iccs, so a window short of ccf_nfx would pass. Keep the explicit
        // downsample cases nearly flat so those columns reach the shifts.
        const RFLOAT scaled_B=downsample==0 ? 150.0 : 0.01;
        const int nx=shape.first, ny=shape.second;
        MultidimArray<float> image(ny,nx);
        unsigned state=812;
        for (int i=0;i<nx*ny;++i) {
            state=state*1664525u+1013904223u;
            image.data[i]=(int(state >> 8)%65537-32768)/32768.0f;
        }
        MultidimArray<fComplex> base;
        NewFFT::FourierTransform(image,base);
        std::vector<MultidimArray<fComplex>> local(groups),full(groups);
        for (int k=0;k<groups;++k) {
            full[k]=base;
            // A group is a spectrum of summed frames. Scale it by group size
            // to include unequal final groups without changing the FFT itself.
            const int group_size=k+1;
            for (int i=0;i<XSIZE(base)*YSIZE(base);++i) full[k].data[i] *= group_size;
            fullPhaseReference(full[k],k*2.125/nx,-k*1.375/ny);
        }
        local=full;
        std::vector<RFLOAT> lx(groups,0.125),ly(groups,-0.25),fx=lx,fy=ly;
        std::ostringstream ll,fl;
#ifdef MC_PHASE_COUNT_TRIG
        phase_calls=0;
#endif
        const bool a=MotioncorrRunnerTestAccess::align(r,local,nx,ny,lx,ly,ll,false,scaled_B);
#ifdef MC_PHASE_COUNT_TRIG
        const auto local_calls=phase_calls.load();
        phase_calls=0;
#endif
        const bool b=MotioncorrRunnerTestAccess::align(r,full,nx,ny,fx,fy,fl,true,scaled_B);
        require(a == b && same(lx,fx) && same(ly,fy) && ll.str() == fl.str(),
                "local versus full production alignment shifts/logs differ");
        unsigned iterations_run=0;
        for(std::size_t pos=0;(pos=ll.str().find(" Iteration ",pos)) != std::string::npos;pos+=11)
            ++iterations_run;
        const float scale=downsample<=0 ? std::sqrt(-std::log(1E-8)/(2*scaled_B)) : downsample;
        const int ccf_nx=MotioncorrRunnerTestAccess::ccfSize(r,nx,scale);
        const int ccf_ny=MotioncorrRunnerTestAccess::ccfSize(r,ny,scale);
        require(iterations_run > 0, "alignment iteration log was not exercised");
        if (ccf_nx < nx && ccf_ny < ny && iterations_run >= 2)
            ++cropped_multi_iteration_cases;
#ifdef MC_PHASE_COUNT_TRIG
        const unsigned long long local_groups=(groups-1)*(iterations_run-1);
        const unsigned long long global_groups=(groups-1)*iterations_run;
        require(local_calls == local_groups*(ccf_nx/2+1+ccf_ny),
                "local alignPatch must update CCF support only before a subsequent read");
        require(phase_calls == global_groups*(nx/2+1+ny),
                "actual global alignPatch did not retain full phase tables");
#endif
        ++cases;
    }
    require(cropped_multi_iteration_cases > 0,
            "no cropped alignment exercised a needed phase update (>=2 iterations)");
    std::printf("PASS %d production local/full alignments, %d cropped multi-iteration cases, unequal group amplitudes, j1/j4, iteration limits 1/5\n",cases,cropped_multi_iteration_cases);
#ifndef MC_PHASE_COUNT_TRIG
    std::puts("SKIP (UNRUN) alignPatch sine count witness: MC_PHASE_COUNT_TRIG is not compiled on this platform");
#endif
}
double elapsed(std::chrono::steady_clock::time_point start) {
    return std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();
}
void benchmark(int threads) {
    const int nx=768,ny=742,wx=97,wy=192,groups=24,repeats=20;
    MotioncorrRunner r;
    const auto initial=spectrum(nx/2+1,ny);
    std::vector<MultidimArray<fComplex>> frames(groups,initial);
    struct Result {double seconds; std::vector<fComplex> retained;};
    auto arm=[&](bool window) {
        for (auto &f:frames) f=initial;
        auto start=std::chrono::steady_clock::now();
        for (int repeat=0;repeat<repeats;++repeat) {
            #pragma omp parallel for num_threads(threads)
            for (int k=1;k<groups;++k) {
                if(window)
                    MotioncorrRunnerTestAccess::shift(r,frames[k],(k+1)*0.0013,(k+1)*-0.0017,wx,wy);
                else
                    fullPhaseReference(frames[k],(k+1)*0.0013,(k+1)*-0.0017);
            }
        }
        Result result;
        result.seconds=elapsed(start);
        // The timer ends before copying retained output. Compare every complex
        // bit for either run order instead of relying on an aggregate checksum.
        result.retained.reserve(groups*wx*wy);
        for(const auto &f:frames) for(int row=0;row<wy;++row) {
            const int y=row>wy/2 ? row-wy+ny : row;
            for(int x=0;x<wx;++x) result.retained.push_back(DIRECT_A2D_ELEM(f,y,x));
        }
        return result;
    };
    arm(false); arm(true);
    for (int pair=0;pair<6;++pair) {
        Result full,window;
        if(pair%2) {window=arm(true);full=arm(false);} else {full=arm(false);window=arm(true);}
        require(full.retained.size()==window.retained.size() &&
                std::memcmp(full.retained.data(),window.retained.data(),full.retained.size()*sizeof(fComplex))==0,
                "benchmark retained output differs");
        std::printf("{\"pair\":%d,\"threads\":%d,\"full_seconds\":%.9f,\"window_seconds\":%.9f,\"updates\":%d,\"nx\":%d,\"ny\":%d,\"window_nfx\":%d,\"window_nfy\":%d,\"retained_complex_exact\":%zu}\n",
                    pair,threads,full.seconds,window.seconds,(groups-1)*repeats,nx,ny,wx,wy,full.retained.size());
    }
}
}
int main(int argc,char **argv) {
    try {
        if (argc==3 && std::string(argv[1])=="--bench") benchmark(std::stoi(argv[2]));
        else {phaseControls();alignControls();}
    } catch(const std::exception &e) {std::fprintf(stderr,"FAIL %s\n",e.what());return 1;}
}
