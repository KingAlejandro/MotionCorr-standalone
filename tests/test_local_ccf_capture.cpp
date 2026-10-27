// SPDX-License-Identifier: GPL-2.0-or-later
#include "src/local_ccf_capture.h"
#include <iostream>
#include <fstream>
#include <omp.h>
#include <functional>

using namespace LocalCcfDiagnostic;
static void check(bool v,const char* s){if(!v)throw std::runtime_error(s);}
static bool equal(const MultidimArray<fComplex>& a,const MultidimArray<fComplex>& b){return a.xdim==b.xdim&&a.ydim==b.ydim&&std::memcmp(a.data,b.data,size_t(a.xdim)*a.ydim*sizeof(fComplex))==0;}
int main(){
    std::filesystem::path root=std::filesystem::temp_directory_path()/("mc-ccf-unit-"+std::to_string(getpid()));
    try {
        check(!std::filesystem::exists(root),"test namespace exists");
        MultidimArray<float> input(32,42);for(size_t i=0;i<1344;++i)input.data[i]=float(std::sin(.13*i)+.3*std::cos(.037*i));
        MultidimArray<fComplex> ft;NewFFT::FourierTransform(input,ft);const MultidimArray<fComplex> original=ft;
        MultidimArray<float> without,with;NewFFT::inverseFourierTransform(ft,without);
        Frame observer;observer.allocate(42,32);NewFFT::inverseFourierTransform(ft,with,NewFFT::FwdOnly,true,&observer);
        check(observer.before&&observer.after&&!observer.bad,"actual C2R callbacks missing");check(equal(ft,original),"preserveInput API argument mutated");
        check(std::memcmp(with.data,without.data,1344*sizeof(float))==0,"observer changed inverse output bits");
        std::vector<float> bits(32*22*2);complexCopy(original,bits);check(bits==observer.temporary_before,"observer did not receive actual C2R input");
        bool badscope=false;try{LocalCcfCaptureSession bad(root.string(),"synthetic",129,96,5);}catch(const std::exception&){badscope=true;}check(badscope&&!std::filesystem::exists(root),"bad geometry accepted or created root");
        LocalCcfCaptureSession session(root.string(),"synthetic-unit-matrix",128,96,5);
        bool duplicate=false;try{LocalCcfCaptureSession again(root.string(),"synthetic",128,96,5);}catch(const std::exception&){duplicate=true;}check(duplicate,"existing root accepted");
        std::vector<RFLOAT> zero(5,0);check(!session.patch(0,42,0,32,20,15,zero,zero),"unselected patch captured");
        for(int cy:{47,79}){
            auto c=session.patch(42,84,cy-15,cy+17,62,cy,zero,zero);
            std::vector<MultidimArray<fComplex>> fs(5,ft);MultidimArray<fComplex> ref=ft;MultidimArray<float> weight(32,22);weight.initConstant(1);
            #pragma omp parallel for num_threads(2)
            for(int i=0;i<5;++i)c->clipped(i,input);
            c->configure(fs,42,32,15,1,1,150,weight);c->begin(1,fs,ref,zero,zero);
            #pragma omp parallel for num_threads(2)
            for(int i=0;i<5;++i){
                MultidimArray<fComplex> spectrum=ft;MultidimArray<float> map;c->preDc(i,spectrum);spectrum.data[0]=fComplex(0,0);c->postDc(i,spectrum);
                NewFFT::inverseFourierTransform(spectrum,map,NewFFT::FwdOnly,true,c->fftObserver(i));
                auto& p=c->peak(i);p.posx=0;p.posy=0;p.maxval=map.data[0];p.verdict=1;
                // Retain an unbracketed fallback beyond the coupled accepted range.
                p.separable_x=p.raw_x=p.scaled_x=23.5;p.separable_y=p.raw_y=p.scaled_y=-19.25;
                c->result(i,spectrum,map);
            }
            c->rawResults();c->end(fs,zero,zero,zero,zero,.1,.5);c->finish(true,1,zero,zero);c->reported(zero,zero,zero,zero);
            bool again=false;try{c->rawResults();}catch(const std::exception&){again=true;}check(again,"same-state overwrite accepted");
            std::ifstream f(root/("patch-62-"+std::to_string(cy))/"iter1-frame0-peak.json");std::string text((std::istreambuf_iterator<char>(f)),{});
            check(text.find("23.5")!=std::string::npos&&text.find("\"coupled_offset_ccf\":null")!=std::string::npos,"fallback clipped or rejected offsets published");
        }
        session.finish();check(std::filesystem::exists(root/"COMPLETE.json"),"completion missing");
        // ---- Mode::Legacy bytes preserved (selection, session.json, no full-width metadata)
        auto slurp=[](const std::filesystem::path& q){std::ifstream f(q,std::ios::binary);return std::string((std::istreambuf_iterator<char>(f)),{});};
        auto listing=[](const std::filesystem::path& d){std::vector<std::string> v;for(auto& e:std::filesystem::directory_iterator(d))v.push_back(e.path().filename().string());std::sort(v.begin(),v.end());return v;};
        check(slurp(root/"session.json")=="{\"schema\":\"local-ccf-capture/1\",\"movie\":\"synthetic-unit-matrix\",\"native_truth_input\":false,\"selected_centres\":[[62,47],[62,79]],\"scope\":\"CPU UP-only group1 bin1 max_iter5 tolerance0.5; actual executed iterations\"}\n","legacy session.json bytes changed");
        check(slurp(root/"patch-62-79"/"patch.json").find("capture_mode")==std::string::npos&&slurp(root/"patch-62-79"/"fft-config.json").find("capture_mode")==std::string::npos,"legacy files carry full-width metadata");
        { // legacy session never selects the full-width coordinate
            auto r=std::filesystem::temp_directory_path()/("mc-ccf-unit-lg-"+std::to_string(getpid()));
            LocalCcfCaptureSession lg(r.string(),"synthetic",128,96,5);std::vector<RFLOAT> z(5,0);
            check(!lg.patch(84,126,0,32,104,15,z,z),"legacy mode captured the full-width coordinate");std::filesystem::remove_all(r);
        }
        // ---- Mode::FullWidthPair
        auto fresh=[&](const char* tag){return std::filesystem::temp_directory_path()/(std::string("mc-ccf-unit-")+tag+"-"+std::to_string(getpid()));};
        auto drive=[&](LocalCcfCaptureSession& ses,int xs,int xe,int ys,int ye,int cx,int cy,double xnorm){
            std::unique_ptr<LocalCcfCapture> c=ses.patch(xs,xe,ys,ye,cx,cy,zero,zero);if(!c)return false;
            std::vector<MultidimArray<fComplex>> fs(5,ft);MultidimArray<fComplex> ref=ft;MultidimArray<float> weight(32,22);weight.initConstant(1);
            #pragma omp parallel for num_threads(2)
            for(int i=0;i<5;++i)c->clipped(i,input);
            c->configure(fs,42,32,15,1,1,150,weight,xnorm);c->begin(1,fs,ref,zero,zero);
            #pragma omp parallel for num_threads(2)
            for(int i=0;i<5;++i){
                MultidimArray<fComplex> spectrum=ft;MultidimArray<float> map;c->preDc(i,spectrum);spectrum.data[0]=fComplex(0,0);c->postDc(i,spectrum);
                NewFFT::inverseFourierTransform(spectrum,map,NewFFT::FwdOnly,true,c->fftObserver(i));
                auto& p=c->peak(i);p.posx=0;p.posy=0;p.maxval=map.data[0];p.verdict=(i%2)?1:-1;
                p.separable_x=p.raw_x=p.scaled_x=23.5;p.separable_y=p.raw_y=p.scaled_y=-19.25;
                c->result(i,spectrum,map);
            }
            c->rawResults();c->end(fs,zero,zero,zero,zero,.1,.5);c->finish(true,1,zero,zero);c->reported(zero,zero,zero,zero);return true;
        };
        const std::vector<std::array<int,6>> fw_geometry={{84,126,0,32,104,15},{42,84,64,96,62,79}}; // xs,xe,ys,ye,cx,cy
        {
            auto r=fresh("fw");
            {
                LocalCcfCaptureSession fw(r.string(),"synthetic-fw",128,96,5,Mode::FullWidthPair);
                const std::string sj=slurp(r/"session.json");
                check(sj.find("\"schema\":\"local-ccf-capture/2\"")!=std::string::npos&&sj.find("\"capture_mode\":\"local_full_width_pair\"")!=std::string::npos&&sj.find("\"selected_centres\":[[104,15],[62,79]]")!=std::string::npos&&sj.find("pnx=42")!=std::string::npos,"full-width session.json metadata missing");
                check(!fw.patch(42,84,32,64,62,47,zero,zero)&&!fw.patch(0,42,0,32,20,15,zero,zero)&&!fw.patch(42,84,0,32,62,15,zero,zero),"unselected patch captured in full-width mode");
                for(auto& g:fw_geometry)check(drive(fw,g[0],g[1],g[2],g[3],g[4],g[5],42),"selected full-width patch not captured");
                fw.finish();check(std::filesystem::exists(r/"COMPLETE.json"),"full-width completion missing");
            }
            check(std::filesystem::exists(r/"patch-104-15")&&std::filesystem::exists(r/"patch-62-79")&&!std::filesystem::exists(r/"patch-62-47"),"full-width patch directories wrong");
            check(listing(r/"patch-104-15")==listing(r/"patch-62-79")&&listing(r/"patch-62-79")==listing(root/"patch-62-79"),"full-width file set differs from the legacy file set");
            for(const char* d:{"patch-104-15","patch-62-79"}){
                const std::string cfg=slurp(r/d/"fft-config.json"),pj=slurp(r/d/"patch.json");
                check(cfg.find("\"weight_x_norm\":42,")!=std::string::npos&&cfg.find("\"capture_mode\":\"local_full_width_pair\"")!=std::string::npos&&pj.find("\"local_full_width_weight\":true")!=std::string::npos,"actual weight normalisation or mode metadata missing");
                const std::string peak=slurp(r/d/"iter1-frame0-peak.json");check(peak.find("23.5")!=std::string::npos&&peak.find("\"coupled_offset_ccf\":null")!=std::string::npos,"fallback clipped or rejected offsets published in full-width mode");
            }
            std::filesystem::remove_all(r);
        }
        // ---- failure modes, each with a passing control
        auto throws=[&](const std::function<void()>& f){try{f();}catch(const std::exception&){return true;}return false;};
        {
            auto r=fresh("f1");LocalCcfCaptureSession ses(r.string(),"s",128,96,5,Mode::FullWidthPair);
            check(throws([&]{drive(ses,84,126,0,31,104,15,42);}),"wrong extents accepted");std::filesystem::remove_all(r);
            auto r2=fresh("f1c");LocalCcfCaptureSession c2(r2.string(),"s",128,96,5,Mode::FullWidthPair);check(drive(c2,84,126,0,32,104,15,42),"control: correct extents rejected");std::filesystem::remove_all(r2);
        }
        {
            auto r=fresh("f2");LocalCcfCaptureSession ses(r.string(),"s",128,96,5,Mode::FullWidthPair);
            check(throws([&]{drive(ses,85,127,0,32,104,15,42);}),"centre/extent mismatch accepted");std::filesystem::remove_all(r);
        }
        {
            auto r=fresh("f3");LocalCcfCaptureSession ses(r.string(),"s",128,96,5,Mode::FullWidthPair);
            check(drive(ses,84,126,0,32,104,15,42),"control: first selected patch rejected");
            check(throws([&]{ses.patch(84,126,0,32,104,15,zero,zero);}),"duplicate selected patch accepted");std::filesystem::remove_all(r);
        }
        {
            auto r=fresh("f4");LocalCcfCaptureSession ses(r.string(),"s",128,96,5,Mode::FullWidthPair);
            check(drive(ses,42,84,64,96,62,79,42),"control: selected patch rejected");
            check(throws([&]{ses.finish();})&&!std::filesystem::exists(r/"COMPLETE.json"),"missing selected patch accepted at finish");std::filesystem::remove_all(r);
        }
        for(double bad:{22.0,0.0,41.0}){
            auto r=fresh("f5");LocalCcfCaptureSession ses(r.string(),"s",128,96,5,Mode::FullWidthPair);
            check(throws([&]{drive(ses,84,126,0,32,104,15,bad);}),"inherited weight normalisation accepted in full-width capture");std::filesystem::remove_all(r);
        }
        { // legacy keeps ignoring the declared normalisation (flag-off runs always use nfx)
            auto r=fresh("f6");LocalCcfCaptureSession ses(r.string(),"s",128,96,5);check(drive(ses,42,84,64,96,62,79,22),"legacy mode rejected the inherited normalisation");std::filesystem::remove_all(r);
        }
        Budget b;bool cap=false;try{exclusiveFile(root/"oversized",nullptr,Budget::limit+1,b);}catch(const std::exception&){cap=true;}check(cap&&!std::filesystem::exists(root/"oversized"),"payload cap not enforced before open");
        std::filesystem::remove_all(root);std::cout<<"PASS actual-temp/API distinction, bit neutrality, two-thread coverage, scope/exclusive writes, fallback/no rejected offsets, budget, legacy bytes, full-width pair selection/metadata/failures\n";return 0;
    }catch(const std::exception& e){std::cerr<<e.what()<<"; retained "<<root<<"\n";return 1;}
}
