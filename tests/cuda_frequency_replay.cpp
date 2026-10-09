// Optional native experiment, never part of the default processing route.
// Exact equality is checked over every Fourier scalar and iteration field.
#include "src/acc/cuda/cuda_alignpatch.h"
#include "src/error.h"
#include <cuda_runtime.h>
#include <fftw3.h>
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
using Mode = GlobalFrequencyExperimentMode;
using Trace = GlobalFrequencyExperimentTrace;
enum class Signal { Motion, Identical, Weak, Zero };
struct Case {
    const char *name;
    int nx, ny, frames, iterations, ccf_nx, ccf_ny;
    RFLOAT B, downsample;
    Signal signal;
    unsigned seed;
};
struct Result {
    bool converged = false;
    std::vector<RFLOAT> x, y;
    std::vector<cufftComplex> fourier;
    Trace trace;
};
void require(bool ok, const std::string &message) {
    if (!ok) throw std::runtime_error(message);
}
void gpu(cudaError_t status, const char *message) {
    require(status == cudaSuccess, std::string(message) + ": " + cudaGetErrorString(status));
}
template<class T> bool same(const T &a, const T &b) {
    return std::memcmp(&a, &b, sizeof(T)) == 0;
}
template<class T> bool same(const std::vector<T> &a, const std::vector<T> &b) {
    return a.size() == b.size() && (a.empty() || std::memcmp(a.data(), b.data(), a.size()*sizeof(T)) == 0);
}
template<class T> void finite(const std::vector<T> &values, const char *name) {
    for (T value : values) require(std::isfinite(value), std::string("nonfinite ") + name);
}
// Independent reader enumeration, deliberately not the candidate's predicate.
std::vector<bool> support(const Case &c) {
    const int nfx = c.nx/2 + 1;
    std::vector<bool> mask((size_t)nfx*c.ny, false);
    for (int cy = 0; cy < c.ccf_ny; ++cy) {
        const int source_y = cy > c.ccf_ny/2 ? cy - c.ccf_ny + c.ny : cy;
        for (int cx = 0; cx <= c.ccf_nx/2; ++cx)
            mask[(size_t)source_y*nfx+cx] = true;
    }
    return mask;
}

// Start with a real periodic image and shifted copies, then R2C with FFTW.
// Zeroing crop boundaries is an explicit real-valued spectral projection:
// C2R Nyquist planes cannot carry an arbitrary complex phase. A source Nyquist
// plane outside that crop is retained to exercise replay's original coordinates.
// The projection leaves nonzero frequencies on both sides of the CCF boundary.
std::vector<cufftComplex> fixture(const Case &c) {
    const size_t pixels = (size_t)c.nx*c.ny, stride = (size_t)(c.nx/2+1)*c.ny;
    std::vector<float> base(pixels), real(pixels);
    unsigned state = c.seed;
    for (size_t i = 0; i < pixels; ++i) {
        state ^= state << 13; state ^= state >> 17; state ^= state << 5;
        base[i] = (float)((int)(state & 65535u) - 32768) / 32768.0f;
    }
    std::vector<cufftComplex> out(stride*c.frames);
    fftwf_plan plan = fftwf_plan_dft_r2c_2d(c.ny, c.nx, real.data(),
        reinterpret_cast<fftwf_complex*>(out.data()), FFTW_ESTIMATE | FFTW_UNALIGNED);
    require(plan != nullptr, "FFTW fixture plan failed");
    const int dx[] = {0, 3, -2, 1, -3, 2, 4};
    const int dy[] = {0, -2, 3, 2, -1, -3, 1};
    for (int f = 0; f < c.frames; ++f) {
        const bool moving = c.signal == Signal::Motion || c.signal == Signal::Weak;
        const int sx = moving ? dx[f%7] : 0, sy = moving ? dy[f%7] : 0;
        for (int y = 0; y < c.ny; ++y) for (int x = 0; x < c.nx; ++x) {
            const int xx = (x-sx+c.nx)%c.nx, yy = (y-sy+c.ny)%c.ny;
            real[(size_t)y*c.nx+x] = c.signal == Signal::Zero ? 0.0f :
                base[(size_t)yy*c.nx+xx] * (c.signal == Signal::Weak ? 0.0001f : 1.0f);
        }
        cufftComplex *frame = out.data()+f*stride;
        fftwf_execute_dft_r2c(plan, real.data(), reinterpret_cast<fftwf_complex*>(frame));
        const int nfx = c.nx/2+1;
        for (int y = 0; y < c.ny; ++y) for (int x = 0; x < nfx; ++x) {
            auto &v = frame[(size_t)y*nfx+x];
            v.x /= (float)pixels; v.y /= (float)pixels;
            if (x == c.ccf_nx/2 || y == c.ccf_ny/2 || y == c.ny-c.ccf_ny/2)
                v = {0.0f, 0.0f};
        }
        // FFTW's real transform is Hermitian mathematically. Make the stored
        // x=0 boundary exact, including signed conjugation, before GPU C2R.
        for (int x : {0,c.nx/2}) {
            frame[x].y = 0.0f; frame[(size_t)(c.ny/2)*nfx+x].y = 0.0f;
            for (int y = 1; y < c.ny/2; ++y)
                frame[(size_t)(c.ny-y)*nfx+x] = {frame[(size_t)y*nfx+x].x, -frame[(size_t)y*nfx+x].y};
        }
    }
    fftwf_destroy_plan(plan);
    return out;
}

void validateFixture(const Case &c, const std::vector<cufftComplex> &input) {
    const int nfx = c.nx/2+1;
    const size_t stride = (size_t)nfx*c.ny;
    const auto selected = support(c);
    bool signal_in = false, signal_out = false;
    for (int f = 0; f < c.frames; ++f) {
        const auto *p = input.data()+f*stride;
        for (size_t i = 0; i < stride; ++i) {
            require(std::isfinite(p[i].x) && std::isfinite(p[i].y), "fixture nonfinite");
            if (p[i].x != 0 || p[i].y != 0) (selected[i] ? signal_in : signal_out) = true;
        }
        for (int y = 0; y < c.ny; ++y) {
            for (int x : {0,c.nx/2}) {
                const auto a=p[(size_t)y*nfx+x],b=p[(size_t)((c.ny-y)%c.ny)*nfx+x];
                require(a.x==b.x && a.y==-b.y,"fixture boundary is not Hermitian");
            }
            require(p[(size_t)y*nfx+c.ccf_nx/2].x == 0 && p[(size_t)y*nfx+c.ccf_nx/2].y == 0,
                    "cropped Nyquist boundary is not zero");
        }
    }
    if (c.signal != Signal::Zero) require(signal_in, "fixture has no alignment signal");
    if (c.signal != Signal::Zero && (c.ccf_nx != c.nx || c.ccf_ny != c.ny))
        require(signal_out, "cropped fixture has no omitted high-frequency signal");
}

Result run(const Case &c, const std::vector<cufftComplex> &input, Mode mode, bool shipped=false) {
    cufftComplex *device = nullptr;
    gpu(cudaMalloc(&device, input.size()*sizeof(cufftComplex)), "fixture allocation");
    Result result;
    result.x.assign(c.frames, 0); result.y.assign(c.frames, 0);
    result.fourier.resize(input.size());
    std::ostringstream log;
    try {
        gpu(cudaMemcpy(device, input.data(), input.size()*sizeof(cufftComplex), cudaMemcpyHostToDevice), "fixture upload");
        if(shipped)
            result.converged=cudaAlignPatchDevice(device,c.frames,c.nx,c.ny,c.B,result.x,result.y,
                c.iterations,c.downsample,0,log,true);
        else
            result.converged = cudaAlignGlobalFrequencyExperiment(device, c.frames, c.nx, c.ny,
                c.B, result.x, result.y, c.iterations, c.downsample, 0, log, mode, result.trace);
        gpu(cudaMemcpy(result.fourier.data(), device, input.size()*sizeof(cufftComplex), cudaMemcpyDeviceToHost), "result download");
        gpu(cudaFree(device), "fixture release"); device = nullptr;
    } catch (...) { if (device) (void)cudaFree(device); throw; }
    if(shipped) return result;
    require(result.trace.completed, std::string(c.name)+": completion missing");
    require(result.trace.ccf_nx == c.ccf_nx && result.trace.ccf_ny == c.ccf_ny,
            std::string(c.name)+": actual CCF geometry differs from declared fixture");
    require(result.trace.converged == result.converged, "return/convergence trace mismatch");
    require(!result.trace.iterations.empty() && result.trace.iterations.size() <= (size_t)c.iterations,
            "iteration trace absent or oversized");
    finite(result.x, "xshifts"); finite(result.y, "yshifts");
    for (const auto &v : result.fourier)
        require(std::isfinite(v.x) && std::isfinite(v.y), "nonfinite final spectrum");
    for (size_t i = 0; i < result.trace.iterations.size(); ++i) {
        const auto &t = result.trace.iterations[i];
        const std::vector<float> *fields[] = {&t.candidate_x,&t.candidate_y,&t.relative_x,&t.relative_y,&t.normalized_x,&t.normalized_y};
        for (auto p : fields) { require(p->size() == (size_t)c.frames, "short iteration field"); finite(*p,"iteration"); }
        require(t.cumulative_x.size() == (size_t)c.frames && t.cumulative_y.size() == (size_t)c.frames,
                "short cumulative field");
        finite(t.cumulative_x,"cumulative_x"); finite(t.cumulative_y,"cumulative_y");
        require(std::isfinite(t.rmsd) && t.rmsd >= 0 && t.converged == (t.rmsd < RFLOAT(0.5)), "invalid convergence decision");
        require(i+1 == result.trace.iterations.size() || !t.converged, "iterations continued after convergence");
        require(t.relative_x[0] == 0 && t.relative_y[0] == 0 &&
                t.cumulative_x[0] == 0 && t.cumulative_y[0] == 0, "frame-zero origin changed");
    }
    require(result.trace.iterations.back().converged == result.converged, "final decision differs");
    const size_t frame_bytes = (size_t)(c.nx/2+1)*c.ny*sizeof(cufftComplex);
    require(std::memcmp(input.data(),result.fourier.data(),frame_bytes) == 0, "frame zero was modified");
    return result;
}

// Return the first mismatched scientific field. Time/addresses are excluded.
std::string difference(const Result &a, const Result &b) {
    if (a.converged != b.converged || a.trace.converged != b.trace.converged) return "convergence";
    if (!a.trace.completed || !b.trace.completed) return "completion";
    if (a.trace.ccf_nx != b.trace.ccf_nx || a.trace.ccf_ny != b.trace.ccf_ny) return "CCF geometry";
    if (!same(a.x,b.x) || !same(a.y,b.y)) return "final shifts";
    if (a.trace.iterations.size() != b.trace.iterations.size()) return "iteration count";
    for (size_t i = 0; i < a.trace.iterations.size(); ++i) {
        const auto &x = a.trace.iterations[i], &y = b.trace.iterations[i];
#define FIELD(f) if (!same(x.f,y.f)) return std::string(#f)+" iteration="+std::to_string(i+1)
        FIELD(candidate_x); FIELD(candidate_y); FIELD(relative_x); FIELD(relative_y);
        FIELD(normalized_x); FIELD(normalized_y); FIELD(cumulative_x); FIELD(cumulative_y);
        FIELD(rmsd); FIELD(converged);
#undef FIELD
    }
    if (!same(a.fourier,b.fourier)) return "full Fourier payload";
    return {};
}
void exact(const Result &a, const Result &b, const std::string &case_name) {
    const auto why = difference(a,b);
    require(why.empty(), "FREQUENCY_REPLAY_MISMATCH case="+case_name+" field="+why);
}
int comparatorControls(const Case &c, const std::vector<cufftComplex> &input, const Result &r) {
    require(difference(r,r).empty(), "positive comparator control failed");
    int count = 0;
    auto reject = [&](const Result &m, const char *name) {
        require(!difference(r,m).empty(), std::string("comparator missed ")+name); ++count;
    };
    Result m = r; m.fourier.back().y = std::nextafter(m.fourier.back().y, INFINITY); reject(m,"Fourier scalar");
    m = r; m.fourier.pop_back(); reject(m,"truncated Fourier payload");
    m = r; m.x[0] = 1; reject(m,"final x shift");
    m = r; m.y[0] = 1; reject(m,"final y shift");
    m = r; m.trace.completed = false; reject(m,"missing completion");
    m = r; m.trace.ccf_ny += 2; reject(m,"CCF geometry");
    m = r; m.trace.iterations.pop_back(); reject(m,"missing iteration");
    m = r; m.trace.converged = !m.trace.converged; reject(m,"final convergence");
#define CHANGE(f) m=r; m.trace.iterations[0].f[0] += 1; reject(m,#f)
    CHANGE(candidate_x); CHANGE(candidate_y); CHANGE(relative_x); CHANGE(relative_y);
    CHANGE(normalized_x); CHANGE(normalized_y); CHANGE(cumulative_x); CHANGE(cumulative_y);
#undef CHANGE
    m=r; m.trace.iterations[0].rmsd += 1; reject(m,"RMSD");
    m=r; m.trace.iterations[0].converged = !m.trace.iterations[0].converged; reject(m,"iteration convergence");
    // This calibrates the comparator's ability to detect an omitted replay.
    // A compiled source mutant is a separate required native mechanism check.
    m=r; const auto selected = support(c); size_t changed = 0;
    for (size_t i=selected.size(); i<m.fourier.size(); ++i) if (!selected[i%selected.size()]) {
        if (!same(m.fourier[i],input[i])) ++changed;
        m.fourier[i]=input[i];
    }
    require(changed > 0, "replay sensitivity fixture did not change complement");
    reject(m,"omitted complement replay");
    size_t midpoint_changed=0;
    const size_t stride=selected.size(); const int nfx=c.nx/2+1;
    for(int f=1;f<c.frames;++f) for(int x=1;x<nfx;++x) {
        const size_t i=(size_t)f*stride+(size_t)(c.ny/2)*nfx+x;
        if(!same(input[i],r.fourier[i]))++midpoint_changed;
    }
    require(midpoint_changed>0,"original midpoint complement phase is not exercised");
    return count;
}

template<class T> void jsonArray(std::ostream &out, const std::vector<T> &v) {
    out << '['; for (size_t i=0;i<v.size();++i) {if(i)out<<','; out<<v[i];} out<<']';
}
void jsonCase(std::ostream &out, const Case &c, const Result &r, bool first) {
    if (!first) out << ",\n";
    out << "{\"name\":\"" << c.name << "\",\"shape\":[" << c.nx << ',' << c.ny << ',' << c.frames
        << "],\"ccf_shape\":[" << r.trace.ccf_nx << ',' << r.trace.ccf_ny
        << "],\"exact\":true,\"shipped_entry_exact\":true,\"converged\":" << (r.converged?"true":"false") << ",\"iterations\":[";
    for(size_t i=0;i<r.trace.iterations.size();++i) {
        if(i)out<<','; const auto &t=r.trace.iterations[i]; out<<'{';
#define ARRAY(f) out << "\"" #f "\":"; jsonArray(out,t.f); out << ','
        ARRAY(candidate_x); ARRAY(candidate_y); ARRAY(relative_x); ARRAY(relative_y);
        ARRAY(normalized_x); ARRAY(normalized_y); ARRAY(cumulative_x); ARRAY(cumulative_y);
#undef ARRAY
        out << "\"rmsd\":" << t.rmsd << ",\"converged\":" << (t.converged?"true":"false") << '}';
    }
    out << "]}";
}
} // namespace

int main(int argc, char **argv) {
    std::string json_path, only_case;
    for(int i=1;i<argc;++i) {
        const std::string arg=argv[i];
        if ((arg=="--json" || arg=="--case") && i+1<argc) {
            (arg=="--json"?json_path:only_case)=argv[++i];
        } else { std::cerr << "Usage: cuda_frequency_replay [--json PATH] [--case NAME]\n"; return 2; }
    }
    try {
        int devices=0;
        gpu(cudaGetDeviceCount(&devices),"CUDA device enumeration");
        require(devices>0,"Native CUDA device 0 required; this is not a skipped pass");
        gpu(cudaSetDevice(0),"CUDA device selection");
        cudaDeviceProp prop{}; gpu(cudaGetDeviceProperties(&prop,0),"device properties");
        int runtime=0,driver=0; gpu(cudaRuntimeGetVersion(&runtime),"CUDA runtime version");
        gpu(cudaDriverGetVersion(&driver),"CUDA driver version");
        char bus[64]{}; gpu(cudaDeviceGetPCIBusId(bus,sizeof(bus),0),"CUDA PCI identity");
        std::ostringstream uuid;
        for(unsigned char byte:prop.uuid.bytes)uuid<<std::hex<<std::setw(2)<<std::setfill('0')<<(unsigned)byte;
        std::cout << "Device: " << prop.name << '\n';
        // findGoodSizeCuda has a 192 minimum, so a 128-square fixture would
        // silently exercise full support. The declared CCF dimensions are checked.
        const std::vector<Case> cases={
            {"cropped_motion",256,256,5,8,192,192,20,0.5,Signal::Motion,7},
            {"full_support",256,256,5,8,256,256,20,1,Signal::Motion,7},
            {"nonsquare",384,288,4,8,192,192,10,0.5,Signal::Motion,17},
            {"automatic_B",384,256,5,8,192,192,80,-1,Signal::Motion,29},
            {"automatic_B_changed",384,256,5,8,288,192,20,-1,Signal::Motion,29},
            {"same_geometry_changed_input",256,256,5,8,192,192,20,0.5,Signal::Motion,101},
            {"early_convergence",256,256,4,8,192,192,0,0.5,Signal::Identical,7},
            {"max_iter_exhaustion",256,256,5,1,192,192,20,0.5,Signal::Motion,7},
            {"single_frame",256,288,1,4,192,192,20,0.5,Signal::Motion,23},
            {"zero_tied_peaks",256,256,3,4,192,192,20,0.5,Signal::Zero,7},
            {"weak_signal",288,256,5,8,192,192,5,0.5,Signal::Weak,31},
            {"cropped_motion_repeat",256,256,5,8,192,192,20,0.5,Signal::Motion,7}
        };
        std::ostringstream report;
        report << std::setprecision(std::numeric_limits<RFLOAT>::max_digits10)
               << "{\"schema\":1,\"backend\":\"native_cuda\",\"device_uuid_hex\":\""<<uuid.str()
               <<"\",\"pci_bus_id\":\""<<bus<<"\",\"runtime_version\":"<<runtime
               <<",\"driver_version\":"<<driver<<",\"cases\":[\n";
        int ran=0, controls=0; bool repeated=false; Result first_result;
        for(const auto &c:cases) {
            if(!only_case.empty() && only_case!=c.name)continue;
            const auto input=fixture(c); validateFixture(c,input);
            const auto shipped=run(c,input,Mode::Reference,true);
            const auto reference=run(c,input,Mode::Reference);
            const auto candidate=run(c,input,Mode::DeferredComplement);
            require(shipped.converged==reference.converged && same(shipped.x,reference.x) &&
                    same(shipped.y,reference.y) && same(shipped.fourier,reference.fourier),
                    std::string("FREQUENCY_REPLAY_MISMATCH case=")+c.name+" field=shipped entry versus instrumented reference");
            exact(reference,candidate,c.name);
            if(std::string(c.name)=="early_convergence")
                require(reference.converged && reference.trace.iterations.size()==1,"early convergence control missed its branch");
            if(std::string(c.name)=="max_iter_exhaustion")
                require(!reference.converged && reference.trace.iterations.size()==1,"max-iteration control did not exhaust");
            if(std::string(c.name)=="cropped_motion") {
                controls=comparatorControls(c,input,reference); first_result=candidate;
            }
            if(std::string(c.name)=="cropped_motion_repeat" && only_case.empty()) {
                exact(first_result,candidate,"mixed_geometry_call_isolation"); repeated=true;
            }
            jsonCase(report,c,candidate,ran==0); ++ran;
            std::cout << "PASS " << c.name << " iterations=" << candidate.trace.iterations.size()
                      << " converged=" << candidate.converged << " exact_full_spectrum_and_trace=yes\n";
        }
        require(ran>0,"requested case not found");
        if(only_case.empty())require(controls==19 && repeated,"required comparator/isolation controls missing");
        report << "\n],\"comparator_mutations_rejected\":" << controls << ",\"compiled_replay_mutants\":\"not_run_by_this_binary\"}\n";
        if(!json_path.empty()) {
            std::ofstream out(json_path); require(bool(out),"cannot open JSON output");
            out << report.str(); out.close(); require(bool(out),"cannot complete JSON output");
        }
        std::cout << "PASS cases=" << ran << " comparator_mutations_rejected=" << controls << '\n';
        return 0;
    } catch(const RelionError &e) {std::cerr<<"FAIL CUDA/RELION: "<<e.msg<<'\n';}
      catch(const std::exception &e) {std::cerr<<"FAIL "<<e.what()<<'\n';}
    return 1;
}
