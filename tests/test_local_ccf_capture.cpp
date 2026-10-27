// SPDX-License-Identifier: GPL-2.0-or-later
#include "src/local_ccf_capture.h"
#include <iostream>
#include <fstream>
#include <omp.h>

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
        Budget b;bool cap=false;try{exclusiveFile(root/"oversized",nullptr,Budget::limit+1,b);}catch(const std::exception&){cap=true;}check(cap&&!std::filesystem::exists(root/"oversized"),"payload cap not enforced before open");
        std::filesystem::remove_all(root);std::cout<<"PASS actual-temp/API distinction, bit neutrality, two-thread coverage, scope/exclusive writes, fallback/no rejected offsets, budget\n";return 0;
    }catch(const std::exception& e){std::cerr<<e.what()<<"; retained "<<root<<"\n";return 1;}
}
