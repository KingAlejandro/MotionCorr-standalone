// Default-off B2 research fit. GPL-2.0-or-later, like MotionCorr.
#ifndef MOTIONCORR_LOCAL_B2_FIT_H
#define MOTIONCORR_LOCAL_B2_FIT_H
#include <algorithm>
#include <array>
#include <cmath>
#include <limits>
#include <map>
#include <set>
#include <stdexcept>
#include <vector>
namespace LocalB2 {
using Row = std::vector<double>;
// Column-scaled, column-pivoted Householder QR. No normal equations.
inline std::vector<Row> qr(std::vector<Row> a, std::vector<Row> b) {
    const size_t m=a.size(), n=a.at(0).size(), r=b.at(0).size();
    if(m<n) throw std::runtime_error("B2 rank deficient: fewer rows than columns");
    Row scale(n); std::vector<size_t> perm(n);
    for(size_t j=0;j<n;++j) {
        perm[j]=j;
        for(size_t i=0;i<m;++i) scale[j]=std::hypot(scale[j],a[i][j]);
        if(!(scale[j]>0) || !std::isfinite(scale[j])) throw std::runtime_error("B2 rank deficient/nonfinite column");
        for(size_t i=0;i<m;++i) a[i][j]/=scale[j];
    }
    const double tol=64*std::numeric_limits<double>::epsilon()*std::max(m,n);
    for(size_t k=0;k<n;++k) {
        size_t pivot=k; double best=-1;
        for(size_t j=k;j<n;++j) { double norm=0; for(size_t i=k;i<m;++i) norm=std::hypot(norm,a[i][j]); if(norm>best){best=norm;pivot=j;} }
        if(!(best>tol)) throw std::runtime_error("B2 rank deficient after nuisance projection");
        for(size_t i=0;i<m;++i) std::swap(a[i][k],a[i][pivot]);
        std::swap(perm[k],perm[pivot]);
        Row v(m-k); for(size_t i=k;i<m;++i) v[i-k]=a[i][k];
        const double alpha=-std::copysign(best,v[0]); v[0]-=alpha;
        double vn=0; for(double x:v) vn=std::hypot(vn,x); for(double &x:v) x/=vn;
        for(size_t j=k;j<n;++j) { double dot=0; for(size_t i=k;i<m;++i) dot+=v[i-k]*a[i][j]; for(size_t i=k;i<m;++i) a[i][j]-=2*v[i-k]*dot; }
        for(size_t j=0;j<r;++j) { double dot=0; for(size_t i=k;i<m;++i) dot+=v[i-k]*b[i][j]; for(size_t i=k;i<m;++i) b[i][j]-=2*v[i-k]*dot; }
        a[k][k]=alpha;
    }
    std::vector<Row> x(n,Row(r)), out(n,Row(r));
    for(size_t kk=n;kk-->0;) for(size_t j=0;j<r;++j) { double val=b[kk][j]; for(size_t k=kk+1;k<n;++k) val-=a[kk][k]*x[k][j]; x[kk][j]=val/a[kk][kk]; }
    for(size_t k=0;k<n;++k) for(size_t j=0;j<r;++j) { out[perm[k]][j]=x[k][j]/scale[perm[k]]; if(!std::isfinite(out[perm[k]][j])) throw std::runtime_error("B2 nonfinite solution"); }
    return out;
}
inline Row spatial(double u,double v){return {1,u,u*u,v,v*v,u*v};}
inline Row design(double u,double v,double g){Row a;for(double s:spatial(u,v)){a.push_back(s*g);a.push_back(s*g*g);a.push_back(s*g*g*g);}return a;}
struct Observation { double u,v,g,x,y; };
struct Fit { std::array<double,18> x{},y{}; std::vector<std::array<double,2>> nuisance; };
inline Fit fit(const std::vector<Observation>& obs) {
    if(obs.empty()) throw std::runtime_error("B2 has no observations");
    std::map<std::pair<double,double>,std::vector<size_t>> patches;
    for(size_t i=0;i<obs.size();++i){const auto&o=obs[i];for(double v:{o.u,o.v,o.g,o.x,o.y})if(!std::isfinite(v))throw std::runtime_error("B2 nonfinite observation");if(o.g<0 || o.g!=std::floor(o.g))throw std::runtime_error("B2 requires integer group times");patches[{o.u,o.v}].push_back(i);}
    std::vector<Row> s;
    for(const auto&p:patches){s.push_back(spatial(p.first.first,p.first.second));std::set<double> times;for(size_t i:p.second)times.insert(obs[i].g);if(times.size()<4)throw std::runtime_error("B2 requires >=4 distinct times per patch");}
    qr(s,std::vector<Row>(s.size(),Row(1))); // spatial rank 6
    std::vector<Row> a,b; for(const auto&o:obs){a.push_back(design(o.u,o.v,o.g));b.push_back({o.x,o.y});}
    const auto original_a=a, original_b=b;
    // Orthogonal projection off the disjoint patch indicator columns. Rank of
    // [A, indicators] is npatch + rank(projected A), so this checks full rank.
    for(const auto&p:patches){Row ma(18),mb(2);for(size_t i:p.second){for(size_t j=0;j<18;++j)ma[j]+=a[i][j]/p.second.size();for(size_t j=0;j<2;++j)mb[j]+=b[i][j]/p.second.size();}for(size_t i:p.second){for(size_t j=0;j<18;++j)a[i][j]-=ma[j];for(size_t j=0;j<2;++j)b[i][j]-=mb[j];}}
    const auto c=qr(a,b);Fit out;out.nuisance.resize(obs.size());for(size_t j=0;j<18;++j){out.x[j]=c[j][0];out.y[j]=c[j][1];}
    for(const auto&p:patches){std::array<double,2> mean{};for(size_t i:p.second)for(size_t axis=0;axis<2;++axis){double residual=original_b[i][axis];for(size_t j=0;j<18;++j)residual-=original_a[i][j]*c[j][axis];mean[axis]+=residual/p.second.size();}for(size_t i:p.second)out.nuisance[i]=mean;}
    return out;
}
}
#endif
