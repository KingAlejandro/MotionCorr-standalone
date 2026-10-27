// SPDX-License-Identifier: GPL-2.0-or-later
// Default-off, call-scoped observation of the two fixed K267 CPU patches.
#ifndef MOTIONCORR_LOCAL_CCF_CAPTURE_H
#define MOTIONCORR_LOCAL_CCF_CAPTURE_H
#include "src/jaz/single_particle/new_ft.h"
#include <array>
#include <algorithm>
#include <cmath>
#include <utility>
#include <cerrno>
#include <cstring>
#include <filesystem>
#include <fcntl.h>
#include <iomanip>
#include <limits>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unistd.h>
#include <vector>

namespace LocalCcfDiagnostic {
inline void require(bool ok, const std::string& what) {
    if (!ok) throw std::runtime_error("local CCF capture: " + what);
}
inline std::string quote(const std::string& value) {
    std::ostringstream s; s << '"';
    for (unsigned char c : value) {
        if (c == '"' || c == '\\') s << '\\' << c;
        else if (c < 32) s << "\\u00" << std::hex << std::setw(2) << std::setfill('0') << int(c) << std::dec;
        else s << c;
    }
    s << '"'; return s.str();
}
struct Budget { size_t bytes = 0; static constexpr size_t limit = 64 * 1024 * 1024; };
inline void exclusiveFile(const std::filesystem::path& p, const void* data, size_t bytes, Budget& budget) {
    require(bytes <= Budget::limit - budget.bytes, "64 MiB payload limit");
    const int fd = ::open(p.c_str(), O_WRONLY | O_CREAT | O_EXCL, 0600);
    require(fd >= 0, "exclusive open failed: " + p.string() + ": " + std::strerror(errno));
    size_t done = 0;
    while (done < bytes) {
        const ssize_t n = ::write(fd, static_cast<const char*>(data) + done, bytes - done);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) { const int error = errno; ::close(fd); throw std::runtime_error("local CCF capture write failed: " + p.string() + ": " + std::strerror(error)); }
        done += size_t(n);
    }
    require(::close(fd) == 0, "close failed: " + p.string()); budget.bytes += bytes;
}
inline void textFile(const std::filesystem::path& p, const std::string& text, Budget& b) {
    exclusiveFile(p, text.data(), text.size(), b);
}
inline std::string prefixType(const char* type) {
    const unsigned short marker = 1;
    return std::string(*reinterpret_cast<const unsigned char*>(&marker) ? "<" : ">") + type;
}
inline void complexCopy(const MultidimArray<fComplex>& a, std::vector<float>& out) noexcept {
    for (size_t i = 0; i < out.size() / 2; ++i) { out[2*i] = a.data[i].real; out[2*i+1] = a.data[i].imag; }
}
struct Frame : NewFFT::FloatInverseObserver {
    int nx = 0, ny = 0;
    bool clipped = false, before = false, after = false, filled = false, bad = false;
    std::vector<float> samples, pre_dc, post_dc, api_after, temporary_before, temporary_after, map;
    int posx = 0, posy = 0, verdict = -1;
    double maxval = 0, separable_x = 0, separable_y = 0, coupled_dx = 0, coupled_dy = 0;
    double raw_x = 0, raw_y = 0, scaled_x = 0, scaled_y = 0;
    bool compatible(const MultidimArray<fComplex>& a) const noexcept {
        return a.xdim == nx/2+1 && a.ydim == ny && a.zdim == 1 && a.ndim == 1;
    }
    void beforeC2R(const MultidimArray<fComplex>& a) noexcept override {
        if (!compatible(a)) { bad = true; return; }
        complexCopy(a,temporary_before); before = true;
    }
    void afterC2R(const MultidimArray<fComplex>& a) noexcept override {
        if (!compatible(a)) { bad = true; return; }
        complexCopy(a,temporary_after); after = true;
    }
    void allocate(int x, int y) {
        nx=x; ny=y; const size_t n=size_t(y)*(x/2+1)*2;
        pre_dc.resize(n); post_dc.resize(n); api_after.resize(n);
        temporary_before.resize(n); temporary_after.resize(n); map.resize(size_t(x)*y);
    }
    void reset() noexcept { before=after=filled=bad=false; verdict=-1; coupled_dx=coupled_dy=0; }
};
struct Status { bool alignment=false, reported=false, converged=false; int iterations=0; };
}

class LocalCcfCapture {
    using Frame = LocalCcfDiagnostic::Frame;
    std::filesystem::path dir;
    std::shared_ptr<LocalCcfDiagnostic::Budget> budget;
    std::shared_ptr<LocalCcfDiagnostic::Status> status;
    int width, height, ccf_x=0, ccf_y=0, search=0, iteration=0;
    std::vector<Frame> frame;
    std::vector<std::string> files;
    void text(const std::string& name, const std::string& value) {
        LocalCcfDiagnostic::textFile(dir/name,value,*budget); files.push_back(name);
    }
    template<class T> void array(const std::string& name, const std::vector<T>& values,
                                 std::initializer_list<size_t> shape, const std::string& stage, bool allow_nonfinite = false) {
        using namespace LocalCcfDiagnostic;
        size_t count=1; for(size_t v:shape) count*=v;
        require(count==values.size(), "array shape differs: " + name);
        if (!allow_nonfinite) for(T v:values) require(std::isfinite(v), "nonfinite capture: " + name);
        exclusiveFile(dir/(name+".bin"),values.data(),values.size()*sizeof(T),*budget); files.push_back(name+".bin");
        std::ostringstream m; m << "{\"dtype\":" << quote(prefixType(sizeof(T)==4?"f4":"f8"))
          << ",\"shape\":["; bool first=true; for(size_t v:shape){m<<(first?"":",")<<v;first=false;}
        m << "],\"serialized_byte_strides\":["; std::vector<size_t> dims(shape), strides(dims.size()); size_t stride=sizeof(T);
        for(size_t j=dims.size();j-->0;){strides[j]=stride;stride*=dims[j];}
        for(size_t j=0;j<strides.size();++j)m<<(j?",":"")<<strides[j];
        m << "],\"order\":\"C; x fastest, complex last axis real/imag\",\"bytes\":" << values.size()*sizeof(T)
          << ",\"stage\":" << quote(stage) << "}\n";
        text(name+".json",m.str());
    }
    void complexArray(const std::string& name, const MultidimArray<fComplex>& a, const std::string& stage) {
        std::vector<float> v(size_t(a.xdim)*a.ydim*2); LocalCcfDiagnostic::complexCopy(a,v);
        array(name,v,{size_t(a.ydim),size_t(a.xdim),2},stage);
    }
    template<class T> void shifts(const std::string& name,const std::vector<T>& x,const std::vector<T>& y,const std::string& stage) {
        std::vector<double> a(2*x.size()); for(size_t i=0;i<x.size();++i){a[2*i]=x[i];a[2*i+1]=y[i];}
        array(name,a,{x.size(),2},stage);
    }
    std::string tag(int f) const { return "iter"+std::to_string(iteration)+"-frame"+std::to_string(f); }
    std::string hermitian(const std::vector<float>& a) const {
        bool finite=true; double residual=0, self=0; const int nfx=ccf_x/2+1;
        for(float v:a)finite=finite&&std::isfinite(v);
        if(finite)for(int x:{0,ccf_x/2})for(int y=0;y<ccf_y;++y){const size_t i=2*(size_t(y)*nfx+x),j=2*(size_t((ccf_y-y)%ccf_y)*nfx+x);residual=std::max(residual,std::hypot(double(a[i])-a[j],double(a[i+1])+a[j+1]));if(y==0||y==ccf_y/2)self=std::max(self,std::abs(double(a[i+1])));}
        std::ostringstream s;s<<std::setprecision(17)<<"{\"all_finite\":"<<(finite?"true":"false")<<",\"x0_xNyquist_conjugacy_max\":";
        if(finite)s<<residual;else s<<"null";s<<",\"self_imag_max\":";if(finite)s<<self;else s<<"null";s<<"}";return s.str();
    }
public:
    LocalCcfCapture(const std::filesystem::path& p,int xs,int xe,int ys,int ye,int cx,int cy,
                    const std::vector<RFLOAT>& gx,const std::vector<RFLOAT>& gy,
                    std::shared_ptr<LocalCcfDiagnostic::Budget> b,std::shared_ptr<LocalCcfDiagnostic::Status> st)
        :dir(p),budget(std::move(b)),status(std::move(st)),width(xe-xs),height(ye-ys),frame(5) {
        using namespace LocalCcfDiagnostic;
        static_assert(sizeof(float)==4 && sizeof(double)==8 && std::numeric_limits<float>::is_iec559,"capture requires IEEE float32/64");
        require(width==42&&height==32&&cx==62&&(cy==47||cy==79)&&gx.size()==5&&gy.size()==5,"unsupported patch geometry");
        require(std::filesystem::create_directory(dir),"patch directory exists");
        for(auto& f:frame)f.samples.resize(size_t(width)*height);
        std::ostringstream s;s<<"{\"centre\":["<<cx<<","<<cy<<"],\"extents_xy_halfopen\":["<<xs<<","<<xe<<","<<ys<<","<<ye<<"],\"patch_shape_yx\":[32,42],\"frame_index\":\"zero based group/movie; saved STAR frame=group+1\",\"native_RF_scalars_bytes\":"<<sizeof(RFLOAT)<<",\"native_complex_bytes\":"<<sizeof(fComplex)<<",\"native_complex_component_bytes\":"<<sizeof(frame[0].samples[0])<<",\"native_real_and_weight_dtype\":\"float32\",\"native_real_xy_byte_strides\":[4,168],\"native_half_complex_xy_byte_strides\":[8,176],\"raw_arrays\":\"host endian; dtype in each metadata file; contiguous x then y\"}\n";
        text("patch.json",s.str());shifts("global-shifts",gx,gy,"existing global trajectory before patch clipping, original movie pixels");
    }
    void clipped(int f,const MultidimArray<float>& a) noexcept {
        auto& d=frame[f];if(a.xdim!=width||a.ydim!=height||a.zdim!=1||a.ndim!=1){d.bad=true;return;}
        std::copy(a.data,a.data+d.samples.size(),d.samples.begin());d.clipped=true;
    }
    void configure(const std::vector<MultidimArray<fComplex>>& f,int nx,int ny,int range,RFLOAT sx,RFLOAT sy,RFLOAT scaled_B,const MultidimArray<float>& weight) {
        using namespace LocalCcfDiagnostic;require(f.size()==5&&nx==42&&ny==32&&range==15,"unsupported CCF geometry");
        ccf_x=nx;ccf_y=ny;search=range;
        for(int i=0;i<5;++i){require(frame[i].clipped&&!frame[i].bad,"clipped sample capture missing");frame[i].allocate(nx,ny);array("initial-frame"+std::to_string(i)+"-samples",frame[i].samples,{32,42},"actual clipped globally aligned samples immediately before patch FFT");complexArray("initial-frame"+std::to_string(i)+"-fft",f[i],"actual patch FFT output entering alignPatch");}
        std::vector<float> w(weight.data,weight.data+size_t(ny)*(nx/2+1));array("weights",w,{size_t(ny),size_t(nx/2+1)},"actual native float B-factor weights");
        std::ostringstream s;s<<std::setprecision(17)<<"{\"ccf_shape_yx\":["<<ny<<","<<nx<<"],\"half_shape_yx\":["<<ny<<","<<nx/2+1<<"],\"search_range\":"<<range<<",\"scale_xy\":["<<sx<<","<<sy<<"],\"scaled_B\":"<<scaled_B<<",\"forward_norm\":\"NewFFT FwdOnly: divide forward by patch area1344\",\"inverse_norm\":\"FwdOnly: fftwf C2R unnormalized\",\"search_tie\":\"strict greater, y outer then x ascending\",\"hermitian_projection\":\"not applied by diagnostic; no assumption about opaque native FFT handling\",\"primary_oracle_input\":\"actual native real map\",\"shifter\":\"multiply entering spectrum by exp(-2pi i(kx delta_x/42 + signedky delta_y/32)) after frame0 anchor subtraction\",\"native_preserveInput\":true}\n";text("fft-config.json",s.str());
    }
    void begin(int iter,const std::vector<MultidimArray<fComplex>>& f,const MultidimArray<fComplex>& ref,const std::vector<RFLOAT>& x,const std::vector<RFLOAT>& y) {
        iteration=iter;for(auto& d:frame)d.reset();
        shifts("iter"+std::to_string(iter)+"-enter-shifts",x,y,"cumulative applied shifts entering this iteration");
        complexArray("iter"+std::to_string(iter)+"-reference",ref,"actual summed windowed reference used by native CCF expression");
        for(int i=0;i<5;++i){complexArray(tag(i)+"-enter-fft",f[i],"actual full spectrum entering iteration");
            std::vector<float> window(size_t(ccf_y)*(ccf_x/2+1)*2),other(window.size()),raw(window.size());
            for(int yy=0;yy<ccf_y;++yy){int ly=yy>ccf_y/2?yy-ccf_y+int(f[i].ydim):yy;for(int xx=0;xx<ccf_x/2+1;++xx){size_t j=2*(size_t(yy)*(ccf_x/2+1)+xx);const auto z=DIRECT_A2D_ELEM(f[i],ly,xx);const auto o=DIRECT_A2D_ELEM(ref,yy,xx)-z;const auto r=o*z.conj();window[j]=z.real;window[j+1]=z.imag;other[j]=o.real;other[j+1]=o.imag;raw[j]=r.real;raw[j+1]=r.imag;}}
            array(tag(i)+"-window-fft",window,{size_t(ccf_y),size_t(ccf_x/2+1),2},"actual entering bins selected by native window indices");
            array(tag(i)+"-sum-of-others",other,{size_t(ccf_y),size_t(ccf_x/2+1),2},"observation-only recomputation ref minus same-state frame; no stored native intermediate");
            array(tag(i)+"-raw-product",raw,{size_t(ccf_y),size_t(ccf_x/2+1),2},"observation-only recomputation (ref-frame)*conj(frame), before weight; native expression unchanged");}
    }
    void preDc(int i,const MultidimArray<fComplex>& a) noexcept {auto& f=frame[i];if(!f.compatible(a)){f.bad=true;return;}LocalCcfDiagnostic::complexCopy(a,f.pre_dc);}
    void postDc(int i,const MultidimArray<fComplex>& a) noexcept {auto& f=frame[i];if(!f.compatible(a)){f.bad=true;return;}LocalCcfDiagnostic::complexCopy(a,f.post_dc);}
    NewFFT::FloatInverseObserver* fftObserver(int i) noexcept {return &frame[i];}
    Frame& peak(int i) noexcept {return frame[i];}
    void result(int i,const MultidimArray<fComplex>& api,const MultidimArray<float>& map) noexcept {
        auto& f=frame[i];if(!f.compatible(api)||map.xdim!=ccf_x||map.ydim!=ccf_y){f.bad=true;return;}
        LocalCcfDiagnostic::complexCopy(api,f.api_after);std::copy(map.data,map.data+f.map.size(),f.map.begin());f.filled=true;
    }
    void rawResults() {
        using namespace LocalCcfDiagnostic;
        for(int i=0;i<5;++i){auto& f=frame[i];require(!f.bad&&f.before&&f.after&&f.filled,"per-frame C2R/peak capture missing");
            for(auto item:{std::make_pair("weighted-pre-dc",&f.pre_dc),std::make_pair("weighted-api-consumed",&f.post_dc),std::make_pair("c2r-temporary-before",&f.temporary_before),std::make_pair("c2r-temporary-after",&f.temporary_after),std::make_pair("weighted-api-after",&f.api_after)})array(tag(i)+"-"+item.first,*item.second,{size_t(ccf_y),size_t(ccf_x/2+1),2},std::string(item.first)+"; API argument and actual C2R temporary are distinct snapshots", std::string(item.first)=="c2r-temporary-after");
            array(tag(i)+"-real-map",f.map,{size_t(ccf_y),size_t(ccf_x)},"actual native float32 CCF inverse output before peak search; primary oracle input");
            std::vector<float> neighbourhood;for(int dy=-1;dy<=1;++dy)for(int dx=-1;dx<=1;++dx)neighbourhood.push_back(f.map[size_t((f.posy+dy+ccf_y)%ccf_y)*ccf_x+(f.posx+dx+ccf_x)%ccf_x]);array(tag(i)+"-peak3x3",neighbourhood,{3,3},"actual native wrapped neighbourhood around selected integer peak");
            int ties=0;for(int yy=-search;yy<=search;++yy)for(int xx=-search;xx<=search;++xx)if(f.map[size_t((yy+ccf_y)%ccf_y)*ccf_x+(xx+ccf_x)%ccf_x]==f.maxval)++ties;
            require(std::isfinite(f.maxval)&&std::isfinite(f.separable_x)&&std::isfinite(f.separable_y)&&(f.verdict!=0||(std::isfinite(f.coupled_dx)&&std::isfinite(f.coupled_dy)))&&std::isfinite(f.raw_x)&&std::isfinite(f.raw_y)&&std::isfinite(f.scaled_x)&&std::isfinite(f.scaled_y),"nonfinite native peak");
            std::ostringstream s;s<<std::setprecision(17)<<"{\"iteration\":"<<iteration<<",\"frame\":"<<i<<",\"integer_xy\":["<<f.posx<<","<<f.posy<<"],\"max_value\":"<<f.maxval<<",\"equal_max_ties_in_search\":"<<ties<<",\"separable_xy_ccf\":["<<f.separable_x<<","<<f.separable_y<<"],\"coupled_verdict\":"<<f.verdict<<",\"coupled_offset_ccf\":";
            if(f.verdict==0)s<<"["<<f.coupled_dx<<","<<f.coupled_dy<<"]";else s<<"null";
            s<<",\"raw_selected_xy_ccf\":["<<f.raw_x<<","<<f.raw_y<<"],\"raw_scaled_xy_movie\":["<<f.scaled_x<<","<<f.scaled_y<<"],\"offsets_clipped_by_diagnostic\":false,\"pre_dc_Hermitian\":"<<hermitian(f.pre_dc)<<",\"API_consumed_Hermitian\":"<<hermitian(f.post_dc)<<",\"actual_C2R_input_Hermitian\":"<<hermitian(f.temporary_before)<<",\"actual_C2R_after_Hermitian\":"<<hermitian(f.temporary_after)<<"}\n";text(tag(i)+"-peak.json",s.str());}
    }
    void end(const std::vector<MultidimArray<fComplex>>& f,const std::vector<RFLOAT>& dx,const std::vector<RFLOAT>& dy,const std::vector<RFLOAT>& x,const std::vector<RFLOAT>& y,RFLOAT rms,RFLOAT tolerance) {
        LocalCcfDiagnostic::require(std::isfinite(rms)&&std::isfinite(tolerance), "nonfinite stopping state");
        shifts("iter"+std::to_string(iteration)+"-applied-deltas",dx,dy,"actual frame0-anchor-adjusted deltas applied to native shifts; never clipped");
        shifts("iter"+std::to_string(iteration)+"-exit-shifts",x,y,"actual cumulative applied shifts after update");
        for(int i=0;i<5;++i)complexArray(tag(i)+"-exit-fft",f[i],"actual spectra after native Fourier shifts; frame0 unshifted");
        std::ostringstream s;s<<std::setprecision(17)<<"{\"iteration\":"<<iteration<<",\"rms_increment_px\":"<<rms<<",\"tolerance_px\":"<<tolerance<<",\"strict_stop\":"<<(rms<tolerance?"true":"false")<<"}\n";text("iter"+std::to_string(iteration)+"-stop.json",s.str());
    }
    void finish(bool converged,int iterations,const std::vector<RFLOAT>& x,const std::vector<RFLOAT>& y) {
        status->alignment=true;status->converged=converged;status->iterations=iterations;
        shifts("final-local-shifts",x,y,"native local cumulative shifts before interpolateShifts/recentering");
        text("alignment-complete.json",std::string("{\"converged\":")+(converged?"true":"false")+",\"iterations\":"+std::to_string(iterations)+"}\n");
    }
    void reported(const std::vector<RFLOAT>& x,const std::vector<RFLOAT>& y,const std::vector<RFLOAT>& ix,const std::vector<RFLOAT>& iy) {
        std::vector<RFLOAT> ox(x.size()),oy(y.size());for(size_t i=0;i<x.size();++i){ox[i]=x[i]-ix[0];oy[i]=y[i]-iy[0];}
        shifts("reported-observations",ox,oy,"same expression later stored at group midpoint g+0.5; STAR frame is integer(g+1.5)");
        shifts("interpolated-shifts",ix,iy,"native interpolateShifts result; frame0 used as reported-observation anchor");status->reported=true;
        std::ostringstream s;s<<"{\"files\":[";for(size_t i=0;i<files.size();++i)s<<(i?",":"")<<LocalCcfDiagnostic::quote(files[i]);s<<"]}\n";text("patch-files.json",s.str());
    }
};

class LocalCcfCaptureSession {
    std::filesystem::path root;
    std::shared_ptr<LocalCcfDiagnostic::Budget> budget=std::make_shared<LocalCcfDiagnostic::Budget>();
    std::vector<std::shared_ptr<LocalCcfDiagnostic::Status>> states;
    bool seen47=false,seen79=false;
public:
    LocalCcfCaptureSession(const std::string& path,const std::string& movie,int nx,int ny,int nf) :root(path) {
        using namespace LocalCcfDiagnostic;
        require(root.is_absolute()&&nx==128&&ny==96&&nf==5,"unsupported movie/path scope");
        require(std::filesystem::create_directory(root),"capture root exists");
        textFile(root/"session.json","{\"schema\":\"local-ccf-capture/1\",\"movie\":"+quote(movie)+",\"native_truth_input\":false,\"selected_centres\":[[62,47],[62,79]],\"scope\":\"CPU UP-only group1 bin1 max_iter5 tolerance0.5; actual executed iterations\"}\n",*budget);
    }
    std::unique_ptr<LocalCcfCapture> patch(int xs,int xe,int ys,int ye,int cx,int cy,const std::vector<RFLOAT>& gx,const std::vector<RFLOAT>& gy) {
        if(cx!=62||(cy!=47&&cy!=79))return nullptr;
        bool& seen=cy==47?seen47:seen79;LocalCcfDiagnostic::require(!seen,"duplicate selected patch");seen=true;
        auto status=std::make_shared<LocalCcfDiagnostic::Status>();states.push_back(status);
        return std::make_unique<LocalCcfCapture>(root/("patch-"+std::to_string(cx)+"-"+std::to_string(cy)),xs,xe,ys,ye,cx,cy,gx,gy,budget,status);
    }
    void finish() {
        using namespace LocalCcfDiagnostic;require(seen47&&seen79&&states.size()==2,"selected patch coverage missing");
        for(const auto& s:states)require(s->alignment&&(!s->converged||s->reported),"selected patch completion missing");
        textFile(root/"COMPLETE.json","{\"selected_patches\":2,\"frames_per_patch_iteration\":5,\"bytes_before_complete\":"+std::to_string(budget->bytes)+",\"payload_limit_bytes\":67108864}\n",*budget);
    }
};
#endif
