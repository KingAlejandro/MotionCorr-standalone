// SPDX-License-Identifier: GPL-2.0-or-later
// Test-build observation overlay only. No numerical switches or device writes.
#ifndef MC_RESIDUAL_CAPTURE_H
#define MC_RESIDUAL_CAPTURE_H
#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>
namespace residual {
inline int patch = -1, patch_x = 1, batch_base = 0, sequence = 0;
inline const char *directory() { return std::getenv("MC_CCF_CAPTURE"); }
inline void checked(bool ok) { if (!ok) { std::perror("residual capture"); std::abort(); } }
inline FILE *open(const std::string &p, const char *mode) { FILE *f=std::fopen(p.c_str(),mode); checked(f!=nullptr); return f; }
inline void raw(const std::string &stem, int it, const char *kind, const void *p, size_t bytes) {
    if (stem.empty()) return;
    FILE *f=open(stem+"-i"+std::to_string(it)+"-"+kind+".bin","wb");
    checked(std::fwrite(p,1,bytes,f)==bytes); checked(std::fclose(f)==0);
}
inline std::string begin(const char *tag, int label, int nx,int ny,int cx,int cy,int n,int search,double sx,double sy,double B) {
    if (!directory()) return {};
    int iy=label<0?0:label/patch_x+1, ix=label<0?0:label%patch_x+1;
    const char *selected=std::getenv("MC_CCF_PATCH");
    if (label>=0 && (!selected || std::to_string(iy)+","+std::to_string(ix)!=selected)) return {};
    std::string stem=std::string(directory())+"/c"+std::to_string(++sequence);
    FILE *f=open(stem+".json","w");
    std::fprintf(f,"{\"tag\":\"%s\",\"patch_yx\":[%d,%d],\"call\":%d,\"patch_nxy\":[%d,%d],\"ccf_nxy\":[%d,%d],\"frames\":%d,\"search\":%d,\"scale_xy\":[%.17g,%.17g],\"B\":%.17g}\n",tag,iy,ix,sequence,nx,ny,cx,cy,n,search,sx,sy,B);
    checked(std::fclose(f)==0); return stem;
}
template<class T> inline void shifts(const std::string &stem,int it,const char *kind,const std::vector<T>&x,const std::vector<T>&y) {
    if(stem.empty()) return;
    std::vector<double> both; for(size_t f=0;f<x.size();++f) {both.push_back(x[f]);both.push_back(y[f]);}
    raw(stem,it,kind,both.data(),both.size()*sizeof(double));
}
#ifdef __CUDACC__
inline void device(const std::string &stem,int it,const char *kind,const void *p,size_t bytes) {
    if(stem.empty()) return;
    std::vector<unsigned char> h(bytes);
    checked(cudaMemcpy(h.data(),p,bytes,cudaMemcpyDeviceToHost)==cudaSuccess);
    raw(stem,it,kind,h.data(),bytes);
}
inline void input(const std::string &stem,int it,const float2 *p,int n,int dx,int dy,int cx,int cy) {
    if(stem.empty()) return;
    std::vector<float2> h(size_t(n)*dx*dy), cropped(size_t(n)*cx*cy);
    checked(cudaMemcpy(h.data(),p,h.size()*sizeof(float2),cudaMemcpyDeviceToHost)==cudaSuccess);
    for(int f=0;f<n;++f) for(int y=0;y<cy;++y) for(int x=0;x<cx;++x)
        cropped[(size_t(f)*cy+y)*cx+x]=h[(size_t(f)*dy+(y>cy/2?y-cy+dy:y))*dx+x];
    raw(stem,it,"input",cropped.data(),cropped.size()*sizeof(float2));
}
#endif
}
#endif
