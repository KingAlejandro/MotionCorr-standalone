// Diagnostic scalar image metrics; same formula as compare_motioncorr.py.
#include <fstream>
#include <vector>
#include <iostream>
#include <iomanip>
#include <cmath>
#include <cstdint>
#include <stdexcept>
std::vector<float> read(const char* p) {
 std::ifstream f(p,std::ios::binary); int32_t h[256]; f.read((char*)h,1024);
 if(!f || h[3]!=2 || h[0]<=0 || h[1]<=0 || h[2]<=0 || h[23]<0) throw std::runtime_error("MRC header");
 size_t n=size_t(h[0])*h[1]*h[2]; std::vector<float> a(n); f.seekg(1024+h[23]);f.read((char*)a.data(),n*4);
 if(!f)throw std::runtime_error("MRC truncated");return a;
}
int main(int argc,char**argv) {try {
 if(argc!=3) return 2; auto a=read(argv[1]),b=read(argv[2]);if(a.size()!=b.size())return 2;
 long double sum=0,ss=0,dd=0;double mx=0;size_t neq=0;
 for(size_t i=0;i<a.size();++i){if(!std::isfinite(a[i]) || !std::isfinite(b[i]))return 2;sum+=a[i];}
 long double mean=sum/a.size();
 for(size_t i=0;i<a.size();++i){long double v=a[i]-mean;ss+=v*v;double d=double(b[i])-a[i];dd+=(long double)d*d;mx=std::max(mx,std::abs(d));neq+=a[i]!=b[i];}
 double rms=std::sqrt(dd/a.size()),sd=std::sqrt(ss/a.size());
 std::cout<<std::setprecision(17)<<"{\"num_pixels\":"<<a.size()<<",\"pixel_identical\":"<<(neq?"false":"true")<<",\"max_abs_pixel_error\":"<<mx<<",\"rmse\":"<<rms<<",\"ref_std\":"<<sd<<",\"relative_rmse\":"<<rms/std::max(sd,1e-12)<<"}\n";
 return 0;
 }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 2;}}
