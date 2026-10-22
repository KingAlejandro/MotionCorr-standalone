#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Generate an additions-only test patch against pinned PR273. Never edit checkout source."""
import difflib, hashlib, json, pathlib, subprocess, sys
HERE=pathlib.Path(__file__).resolve().parent
BASE='805d9de27898b4a10e6212e65098d5995a40fdb1'
out=pathlib.Path(sys.argv[1]);out.mkdir(exist_ok=False)
files=['src/motioncorr_runner.cpp','src/acc/cuda/cuda_alignpatch.cu','src/acc/cuda/cuda_movie_session.cu']
before={p:subprocess.check_output(['git','show',BASE+':'+p]).decode() for p in files}
after=dict(before)
def add(p,needle,extra,before=False):
    assert after[p].count(needle)==1,(p,needle,after[p].count(needle))
    after[p]=after[p].replace(needle,extra+needle if before else needle+extra)
r=files[0];c=files[1];m=files[2]
for p in files: after[p]='#include "src/residual_capture.h" // retained test-build overlay only\n'+after[p] if p==r else after[p]
# CUDA types/runtime must be visible before capture header.
for p,needle in [(c,'#include "src/acc/cuda/cuda_alignpatch.h"'),(m,'#include "src/acc/cuda/cuda_movie_session.h"')]: add(p,needle,'\n#include "src/residual_capture.h"')
add(r,'\tRCTOC(TIMING_GLOBAL_ALIGNMENT);','''
    if (const char *dir=std::getenv("MC_CCF_STATE")) {
        FILE *f=residual::open(std::string(dir)+"/global.txt","w");
        for(size_t i=0;i<xshifts.size();++i) std::fprintf(f,"%zu %.17g %.17g\\n",i+1,double(xshifts[i]),double(yshifts[i]));
        residual::checked(std::fclose(f)==0);
    }
''')
add(r,'\t\t\tmovie_session->alignPatchesBatched(boxes,','            residual::patch_x=patch_x;\n',True)
add(r,'\t\tint ipatch = 1;','\n        residual::patch_x=patch_x;')
add(r,'\t\t\t\tint x_center = (x_start + x_end - 1) / 2, y_center = (y_start + y_end - 1) / 2;','                residual::patch=iy*patch_x+ix;\n',True)
add(m,'        cudaAlignPatchBatchDevice(workspace, count, n_groups, patch_w, patch_h, scaled_B,','        residual::batch_base=first;\n',True)
add(r,'skip_fitting:','''
    if(const char *dir=std::getenv("MC_CCF_STATE")) {
        FILE *f=residual::open(std::string(dir)+"/model.txt","w");
        const auto *poly=dynamic_cast<const ThirdOrderPolynomialModel*>(mic.model);
        std::fprintf(f,"geometry %d %d %d %.17g %d model %d\\n",nx,ny,n_frames,double(prescaling),first_frame_sum,poly?1:0);
        if(poly) for(int i=0;i<18;++i) std::fprintf(f,"%d %.17g %.17g\\n",i,double(poly->coeffX(i)),double(poly->coeffY(i)));
        residual::checked(std::fclose(f)==0);
    }
''')
# CPU call-local storage, original arithmetic untouched.
needle='\tfor (int iter = 1; iter\t<= max_iter; iter++) {'
add(r,needle,'''
    const std::string cap=residual::begin(is_global?"cpu-global":"cpu",is_global?-1:residual::patch,pnx,pny,ccf_nx,ccf_ny,n_frames,search_range,ccf_scale_x,ccf_scale_y,scaled_B);
    residual::raw(cap,0,"weight",weight.data,size_t(ccf_nfy)*ccf_nfx*sizeof(float));
''',True)
add(r,needle,'''
        residual::shifts(cap,iter,"before",xshifts,yshifts);
        if(!cap.empty()) {
            std::vector<fComplex> in(size_t(n_frames)*ccf_nfy*ccf_nfx);
            for(int f=0;f<n_frames;++f) for(int y=0;y<ccf_nfy;++y) for(int x=0;x<ccf_nfx;++x)
                in[(size_t(f)*ccf_nfy+y)*ccf_nfx+x]=DIRECT_A2D_ELEM(Fframes[f],y>ccf_nfy_half?y-ccf_nfy+nfy:y,x);
            residual::raw(cap,iter,"input",in.data(),in.size()*sizeof(fComplex));
        }
''')
add(r,'\t\tRCTOC(TIMING_MAKE_REF);','\n        residual::raw(cap,iter,"reference",Fref.data,size_t(ccf_nfy)*ccf_nfx*sizeof(fComplex));')
add(r,'\t\t\tNewFFT::inverseFourierTransform(Fccs[tid], Iccs[tid]());','''
            if(!cap.empty()) residual::raw(cap,iter,("map-f"+std::to_string(iframe)).c_str(),Iccs[tid]().data,size_t(ccf_ny)*ccf_nx*sizeof(float));
''')
add(r,'\t\t\tNewFFT::inverseFourierTransform(Fccs[tid], Iccs[tid]());','''
            if(!cap.empty()) residual::raw(cap,iter,("spectrum-f"+std::to_string(iframe)).c_str(),Fccs[tid].data,size_t(ccf_nfy)*ccf_nfx*sizeof(fComplex));
''',True)
add(r,'\t\t// Set origin','        residual::shifts(cap,iter,"candidate",cur_xshifts,cur_yshifts);\n',True)
add(r,'\t\t// Apply shifts','        residual::shifts(cap,iter,"after",xshifts,yshifts);\n',True)
# Device per-call and batched paths.
add(c,'    for (int iter = 1; iter <= max_iter; iter++) {','''
    const std::string cap=residual::begin(is_global?"cuda-global":(windowed?"cuda-window":"cuda-full"),is_global?-1:residual::patch,pnx,pny,ccf_nx,ccf_ny,n_frames,search_range,float(ccf_scale_x),float(ccf_scale_y),scaled_B);
    residual::device(cap,0,"weight",d_weight,size_t(ccf_nfx)*ccf_nfy*sizeof(float));
''',True)
add(c,'    for (int iter = 1; iter <= max_iter; iter++) {','''
        residual::shifts(cap,iter,"before",xshifts,yshifts);
        residual::input(cap,iter,d_Fframes,n_frames,data_nfx,data_nfy,ccf_nfx,ccf_nfy);
''')
add(c,'        ALIGN_CUFFT(cufftExecC2R(plan_c2r, (cufftComplex*)d_Fccs, (cufftReal*)d_Iccs));','''
        residual::device(cap,iter,"reference",d_Fref,size_t(ccf_nfx)*ccf_nfy*sizeof(float2));
        residual::device(cap,iter,"spectrum",d_Fccs,size_t(n_frames)*ccf_nfx*ccf_nfy*sizeof(float2));
''',True)
add(c,'        const RFLOAT rmsd = updatePatchShifts(h_cur_xshifts.data(), h_cur_yshifts.data(),','''
        residual::device(cap,iter,"map",d_Iccs,size_t(n_frames)*ccf_nx*ccf_ny*sizeof(float));
        residual::shifts(cap,iter,"candidate",h_cur_xshifts,h_cur_yshifts);
''',True)
add(c,'            h_shiftx.data(), h_shifty.data(), xshifts, yshifts, n_frames, pnx, pny);','\n        residual::shifts(cap,iter,"after",xshifts,yshifts);')
add(c,'    for (int iter = 1; iter <= max_iter && !active.empty(); iter++) {','''
    std::vector<std::string> caps(n_patches);
    for(int p=0;p<n_patches;++p) {
        caps[p]=residual::begin("cuda-batched",residual::batch_base+p,pnx,pny,ccf_nx,ccf_ny,n_frames,search_range,float(w.geo.ccf_scale_x),float(w.geo.ccf_scale_y),scaled_B);
        residual::device(caps[p],0,"weight",w.d_weight,size_t(ccf_nfx)*ccf_nfy*sizeof(float));
    }
''',True)
add(c,'            // Window slots: the frame dims are the window\'s, the remap the identity.','''
            residual::shifts(caps[p],iter,"before",xshifts[p],yshifts[p]);
            residual::input(caps[p],iter,d_Fframes,n_frames,ccf_nfx,ccf_nfy,ccf_nfx,ccf_nfy);
''',True)
add(c,'            ALIGN_CUFFT(cufftExecC2R(w.plan_c2r, (cufftComplex*)d_Fccs, (cufftReal*)d_Iccs));','''
            residual::device(caps[p],iter,"reference",d_Fref,size_t(ccf_nfx)*ccf_nfy*sizeof(float2));
            residual::device(caps[p],iter,"spectrum",d_Fccs,size_t(n_frames)*ccf_nfx*ccf_nfy*sizeof(float2));
''',True)
add(c,'        // The iteration\'s one wait, for every active patch at once.','''
        for(const int p:active) residual::device(caps[p],iter,"map",w.d_Iccs+p*w.slots.iccs,size_t(n_frames)*ccf_nx*ccf_ny*sizeof(float));
''',True)
add(c,'            const RFLOAT rmsd = updatePatchShifts(h_cur_x + p * n, h_cur_y + p * n,','''
            if(!caps[p].empty()) {
                std::vector<float> x(h_cur_x+p*n,h_cur_x+(p+1)*n), y(h_cur_y+p*n,h_cur_y+(p+1)*n);
                residual::shifts(caps[p],iter,"candidate",x,y);
            }
''',True)
add(c,'                n_frames, pnx, pny);','\n            residual::shifts(caps[p],iter,"after",xshifts[p],yshifts[p]);')
after['src/residual_capture.h']=(HERE/'capture.h').read_text()
patch=''
for p,b in after.items():
    a=before.get(p,'')
    patch+=''.join(difflib.unified_diff(a.splitlines(True),b.splitlines(True),fromfile='a/'+p if a else '/dev/null',tofile='b/'+p))
    target=out/p; target.parent.mkdir(parents=True,exist_ok=True); target.write_text(b)
(HERE/'diagnostic.patch').write_text(patch)
(HERE/'overlay-binding.json').write_text(json.dumps(dict(base=BASE,base_files={p:hashlib.sha256(v.encode()).hexdigest() for p,v in before.items()},overlay_files={p:hashlib.sha256(v.encode()).hexdigest() for p,v in after.items()},patch_sha256=hashlib.sha256(patch.encode()).hexdigest()),indent=2)+'\n')
print(out)
