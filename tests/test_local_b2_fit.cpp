#include "src/local_b2_fit.h"
#include <iostream>
using namespace LocalB2;
void require(bool ok,const char* msg){if(!ok)throw std::runtime_error(msg);}
double value(const std::array<double,18>&c,double u,double v,double g){auto a=design(u,v,g);double z=0;for(int j=0;j<18;++j)z+=a[j]*c[j];return z;}
int main(){try{
 for(int degree=1;degree<=4;++degree){
  std::array<double,18> c{};for(int j=0;j<18;++j)if(degree==4 || j%3==degree-1)c[j]=std::sin(j+1)*.003/(1+j%3);
  std::vector<Observation> obs;int patch=0;
  for(double u:{-.4,-.2,0.,.2,.4})for(double v:{-.4,-.2,0.,.2,.4}){++patch;for(int g=0;g<40;++g){double z=value(c,u,v,g)+.5*value(c,u,v,1);obs.push_back({u,v,double(g),z,z*-.7});}}
  auto fit0=fit(obs);double error=0;
  for(double u:{-.5,-.13,.5})for(double v:{-.5,.23,.5})for(int g=0;g<40;++g)error=std::max(error,std::abs(value(fit0.x,u,v,g)-value(c,u,v,g)));
  require(error<1e-8,"analytic full-field exactness");require(value(fit0.x,.3,.2,0)==0,"exact zero gauge");
  // B1 = B2 + .5*S in every temporal column: the extra term is patch-constant.
  auto shifted=obs;for(auto&o:shifted){double constant=0;auto s=spatial(o.u,o.v);for(int j=0;j<18;++j)constant+=.5*s[j/3]*c[j];o.x+=constant+std::sin(12*o.u+7*o.v)*9;o.y-=constant;}
  auto fit1=fit(shifted);for(int j=0;j<18;++j){require(std::abs(fit0.x[j]-fit1.x[j])<1e-8,"nuisance/B1 invariance");require(std::abs(fit0.y[j]-fit1.y[j])<1e-8,"axis offset invariance");}
  // Wrong midpoint arm fits q(g+.5); publishing q(f) must fail degree >=2.
  auto wrong=obs;for(auto&o:wrong)o.g+=.5;
  // qr directly since the native fit intentionally refuses noninteger time.
  std::vector<Row>a,b;for(auto&o:wrong){auto row=design(o.u,o.v,o.g);row.resize(18+25);size_t p=&o-&wrong[0];row[18+p/40]=1;a.push_back(row);b.push_back({o.x});}auto q=qr(a,b);std::array<double,18> qc{};for(int j=0;j<18;++j)qc[j]=q[j][0];
  if(degree==2 || degree==3)require(std::abs(value(qc,.3,.2,39)-value(c,.3,.2,39))>1e-3,"wrong midpoint mutant escaped");
 }
 // Independent augmented designs on noisy data: nuisance elimination vs B1
 // and transformed midpoint C, including both axes and the full-border field.
 std::vector<Observation> noisy;
 for(double u:{-.4,-.2,0.,.2,.4})for(double v:{-.4,-.2,0.,.2,.4})for(int g=0;g<40;++g)
  noisy.push_back({u,v,double(g),std::sin(g*.19+u*3+v*7)+u*g*.01,std::cos(g*.31+u*2-v*5)});
 auto b2=fit(noisy);
 for(int arm=0;arm<2;++arm){std::vector<Row>a,b;size_t i=0;for(const auto&o:noisy){auto row=design(o.u,o.v,o.g+(arm?.5:0));if(!arm){auto s=spatial(o.u,o.v);for(int j=0;j<18;++j)row[j]+=.5*s[j/3];}row.resize(43);row[18+i/40]=1;a.push_back(row);b.push_back({o.x,o.y});++i;}auto q=qr(a,b);
  for(int axis=0;axis<2;++axis){std::array<double,18> c{};for(int j=0;j<18;++j)c[j]=q[j][axis];if(arm)for(int j=0;j<18;j+=3){c[j]=q[j][axis]+q[j+1][axis]+.75*q[j+2][axis];c[j+1]=q[j+1][axis]+1.5*q[j+2][axis];}
   for(double u:{-.5,.11,.5})for(double v:{-.5,.23,.5})for(int g=0;g<40;++g)require(std::abs(value(c,u,v,g)-value(axis?b2.y:b2.x,u,v,g))<1e-8,"noisy augmented B1/C vs projected B2");
  }
 }
 for(double bad:{std::numeric_limits<double>::infinity(),std::numeric_limits<double>::quiet_NaN()}){auto invalid=noisy;invalid[5].x=bad;bool rejected=false;try{fit(invalid);}catch(const std::runtime_error&){rejected=true;}require(rejected,"nonfinite accepted");}
 for(int mode=0;mode<2;++mode){std::vector<Observation> obs;for(double u:{-.4,0.,.4})for(double v:{-.4,0.,.4})for(int g=0;g<(mode?3:5);++g)obs.push_back({u,mode?v:0.,double(g),0,0});bool rejected=false;try{fit(obs);}catch(const std::runtime_error&){rejected=true;}require(rejected,"rank deficient accepted");}
 std::cout<<"PASS analytic linear/quadratic/cubic/full18, gauge, offset/B1 invariance, midpoint mutants, spatial/three-time/nonfinite rejection, noisy augmented B1/C equivalence\n";
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
