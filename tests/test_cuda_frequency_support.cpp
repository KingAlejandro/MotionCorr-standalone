// Device-free enumeration of the actual CCF reader's index mapping.
#include "src/acc/cuda/cuda_alignpatch_frequency_support.h"
#include <iostream>
#include <set>
#include <stdexcept>
#include <utility>
#include <vector>

int main() {
    try {
        const std::vector<int> sizes={2,4,6,8,16,32,64,192,216,256,288};
        size_t checks=0,cases=0;
        bool caught_midpoint=false,caught_bottom_boundary=false,caught_width=false,caught_offset=false;
        for(int full_ny:sizes) for(int crop_ny:sizes) {
            if(crop_ny>full_ny)continue;
            for(int full_nx:{2,8,64,256}) for(int crop_nx:{2,8,64,192,256}) {
                if(crop_nx>full_nx)continue;
                const int nfx=full_nx/2+1,cf= crop_nx/2+1;
                std::set<std::pair<int,int>> read;
                for(int cy=0;cy<crop_ny;++cy)for(int cx=0;cx<cf;++cx) {
                    int source_y=cy;
                    if(cy>crop_ny/2)source_y=full_ny-(crop_ny-cy);
                    if(!read.emplace(cx,source_y).second)throw std::runtime_error("reader mapping aliases");
                }
                if(read.size()!=(size_t)cf*crop_ny)throw std::runtime_error("reader count mismatch");
                for(int y=0;y<full_ny;++y)for(int x=0;x<nfx;++x) {
                    const bool expected=read.count({x,y})!=0;
                    if(mc_cuda::frequencyIsInCcfSupport(x,y,full_ny,cf,crop_ny)!=expected)
                        throw std::runtime_error("production support predicate differs from enumerated reader at "+
                            std::to_string(x)+","+std::to_string(y)+" full="+std::to_string(full_ny)+
                            " crop="+std::to_string(crop_ny));
                    const int half=crop_ny/2;
                    caught_midpoint |= expected != (x<cf && (y<half || y>full_ny-crop_ny+half));
                    caught_bottom_boundary |= expected != (x<cf && (y<=half || y>=full_ny-crop_ny+half));
                    caught_width |= expected != (x<=cf && (y<=half || y>full_ny-crop_ny+half));
                    caught_offset |= expected != (x<cf && (y<=half || y>full_ny-crop_ny+half+1));
                    ++checks;
                }
                ++cases;
            }
        }
        if(!caught_midpoint || !caught_bottom_boundary || !caught_width || !caught_offset)
            throw std::runtime_error("independent enumeration missed a boundary control");
        std::cout<<"PASS support cases="<<cases<<" coordinates="<<checks<<" boundary_mutations_rejected=4\n";
        return 0;
    } catch(const std::exception &e) {std::cerr<<"FAIL "<<e.what()<<'\n';return 1;}
}
