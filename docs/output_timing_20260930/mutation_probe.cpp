// Mutation probe: exercises the REAL MultidimArray methods from src/, with the
// same case list as tests/test_runner_numerics.cpp's mrc_stats mode.
#include "src/multidim_array.h"
#include <cstring>
#include <cstdint>
#include <limits>
#include <iostream>
#include <vector>
#include <string>

static uint64_t bits(RFLOAT v){uint64_t u;std::memcpy(&u,&v,sizeof u);return u;}

int main(){
    const float qnan=std::numeric_limits<float>::quiet_NaN();
    const float finf=std::numeric_limits<float>::infinity();
    struct Case{const char*name;std::vector<float> v;};
    std::vector<Case> cases={
        {"empty",{}},{"single",{3.5f}},{"two",{-1.25f,4.75f}},
        {"three",{2.0f,-8.0f,5.5f}},
        {"strictly increasing",{1,2,3,4,5}},{"strictly decreasing",{5,4,3,2,1}},
        {"constant",std::vector<float>(1000,-2.75f)},
        {"all negative",{-1,-7,-3,-2}},
        {"NaN middle",{1.0f,qnan,-4.0f,9.0f}},{"NaN first",{qnan,1.0f,-4.0f}},
        {"infinities",{finf,-finf,0.0f,1.0f}},{"negative zero",{-0.0f,0.0f}}};
    {std::vector<float> big(1<<18);uint32_t st=0x13572468u;
     for(size_t i=0;i<big.size();i++){st=st*1664525u+1013904223u;
        big[i]=static_cast<float>(static_cast<int32_t>(st))*1e-6f;}
     cases.push_back({"262144 pseudo-random",big});}
    int failures=0;
    for(const Case&c:cases){
        MultidimArray<float> a;
        if(!c.v.empty()){a.resize(1,1,1,(long)c.v.size());
            for(size_t i=0;i<c.v.size();i++) DIRECT_MULTIDIM_ELEM(a,i)=c.v[i];}
        const float wmin=a.computeMin(),wmax=a.computeMax();
        const RFLOAT wavg=a.computeAvg(),wsd=a.computeStddev();
        float gmin,gmax;RFLOAT gavg,gsd;
        a.computeMinMaxAvgStddev(gmin,gmax,gavg,gsd);
        const char*which=nullptr;
        if(bits(gmin)!=bits(wmin))which="min";
        else if(bits(gmax)!=bits(wmax))which="max";
        else if(bits(gavg)!=bits(wavg))which="avg";
        else if(bits(gsd)!=bits(wsd))which="stddev";
        if(which){failures++;std::cout<<"FAIL "<<c.name<<": "<<which<<"\n";}
    }
    std::cout<<(failures?"RESULT: DETECTED":"RESULT: agrees")<<" ("<<failures<<" cases)\n";
    return failures?1:0;
}
