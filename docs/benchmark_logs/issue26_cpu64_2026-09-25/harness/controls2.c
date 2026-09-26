/* Hardened scaling controls for Issue #26.
   Every kernel is written so the compiler cannot hoist or eliminate the work,
   and each uses several independent dependency chains so a single thread
   already saturates the core's FP pipelines (otherwise SMT flatters itself). */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <omp.h>

volatile double sink;

/* 8 independent FMA chains: pure register throughput, zero memory traffic. */
static double k_fma(long iters) {
    double a0=1.1,a1=1.2,a2=1.3,a3=1.4,a4=1.5,a5=1.6,a6=1.7,a7=1.8;
    const double m=1.0000000001, c=1e-12;
    for (long i=0;i<iters;i++){
        a0=a0*m+c; a1=a1*m+c; a2=a2*m+c; a3=a3*m+c;
        a4=a4*m+c; a5=a5*m+c; a6=a6*m+c; a7=a7*m+c;
    }
    return a0+a1+a2+a3+a4+a5+a6+a7;
}

/* exp() throughput with a non-hoistable argument (mirrors doseWeighting). */
static double k_exp(long iters) {
    double x0=0.1,x1=0.2,x2=0.3,x3=0.4,s=0;
    for (long i=0;i<iters;i++){
        x0+=1e-9; x1+=1e-9; x2+=1e-9; x3+=1e-9;
        s += exp(-x0)+exp(-x1)+exp(-x2)+exp(-x3);
    }
    return s;
}

int main(int argc,char**argv){
    const char *kind = argc>1?argv[1]:"fma";
    long iters = argc>2?atol(argv[2]):20000000L;
    int js[]={1,2,4,8,16,32,64}; int nj=7;
    printf("== %s (iters=%ld per thread, work scales with j: perfect = flat time) ==\n",kind,iters);
    printf("   OMP_PROC_BIND=%s OMP_PLACES=%s\n",
           getenv("OMP_PROC_BIND")?:"(unset)", getenv("OMP_PLACES")?:"(unset)");
    double base=0;
    for(int i=0;i<nj;i++){
        int j=js[i];
        double t=omp_get_wtime(); double acc=0;
        #pragma omp parallel for num_threads(j) reduction(+:acc) schedule(static)
        for(int t2=0;t2<j;t2++) acc += strcmp(kind,"exp")? k_fma(iters) : k_exp(iters);
        double el=omp_get_wtime()-t;
        sink=acc;
        if(i==0) base=el;
        printf("  j=%-3d %8.3f s   per-thread throughput vs j=1: %5.1f%%   aggregate %5.2fx\n",
               j, el, 100.0*base/el, j*base/el);
        fflush(stdout);
    }
    return 0;
}
