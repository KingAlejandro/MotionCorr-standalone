/* Issue #26 scaling controls: separate the machine's achievable scaling from
   MotionCorr's. Same box, same OpenMP runtime, same thread counts.
     cpu  - L1-resident FP, zero memory traffic  -> machine's ideal scaling
     mem  - STREAM triad, 64 MiB/thread          -> memory-bandwidth ceiling
     fft  - 24 x 3888^2 fftwf r2c                -> MotionCorr's actual hot kernel
     fftp - same, but create+destroy a plan per transform inside
            #pragma omp critical, exactly as NewFFT::FloatPlan does
*/
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <omp.h>
#include <fftw3.h>

#define NF 24
#define N  3888

static double bench_cpu(int j) {
    double t = omp_get_wtime();
    double acc = 0;
    #pragma omp parallel for num_threads(j) reduction(+:acc) schedule(static)
    for (int k = 0; k < j * 64; k++) {
        double x = 1.0 + k * 1e-9, s = 0;
        for (long i = 0; i < 3000000; i++) s += exp(-x) * 1.0000001;
        acc += s;
    }
    if (acc == 12345.6789) printf("");
    return omp_get_wtime() - t;
}

static double bench_mem(int j) {
    const size_t n = 8L * 1024 * 1024; /* 64 MiB of doubles per thread */
    double **a = malloc(j * sizeof(double *)), **b = malloc(j * sizeof(double *)), **c = malloc(j * sizeof(double *));
    #pragma omp parallel for num_threads(j) schedule(static)
    for (int t = 0; t < j; t++) { /* first-touch on the owning thread */
        a[t] = malloc(n * sizeof(double)); b[t] = malloc(n * sizeof(double)); c[t] = malloc(n * sizeof(double));
        for (size_t i = 0; i < n; i++) { a[t][i] = 1.0; b[t][i] = 2.0; c[t][i] = 0.0; }
    }
    double t0 = omp_get_wtime();
    #pragma omp parallel num_threads(j)
    {
        int t = omp_get_thread_num();
        for (int r = 0; r < 10; r++)
            for (size_t i = 0; i < n; i++) c[t][i] = a[t][i] + 3.0 * b[t][i];
    }
    double el = omp_get_wtime() - t0;
    for (int t = 0; t < j; t++) { free(a[t]); free(b[t]); free(c[t]); }
    free(a); free(b); free(c);
    printf("    [mem] %.1f GiB/s aggregate\n", (double)j * n * 24.0 * 10 / el / (1 << 30));
    return el;
}

static float *rbuf[NF];
static fftwf_complex *cbuf[NF];

static void alloc_fft(void) {
    for (int f = 0; f < NF; f++) {
        rbuf[f] = fftwf_malloc(sizeof(float) * N * N);
        cbuf[f] = fftwf_malloc(sizeof(fftwf_complex) * N * (N / 2 + 1));
        for (long i = 0; i < (long)N * N; i++) rbuf[f][i] = (float)((i * 1103515245L + f) % 1000) / 1000.0f;
    }
}

static double bench_fft(int j, int per_call_plan) {
    fftwf_plan shared = NULL;
    if (!per_call_plan)
        shared = fftwf_plan_dft_r2c_2d(N, N, rbuf[0], cbuf[0], FFTW_ESTIMATE);
    double t = omp_get_wtime();
    #pragma omp parallel for num_threads(j) schedule(static)
    for (int f = 0; f < NF; f++) {
        if (per_call_plan) {
            fftwf_plan pf, pb;
            /* exactly what NewFFT::FloatPlan does: both directions, under one lock */
            #pragma omp critical(FourierTransformer_fftw_plan)
            {
                pf = fftwf_plan_dft_r2c_2d(N, N, rbuf[f], cbuf[f], FFTW_ESTIMATE);
                pb = fftwf_plan_dft_c2r_2d(N, N, cbuf[f], rbuf[f], FFTW_ESTIMATE);
            }
            fftwf_execute(pf);
            #pragma omp critical(FourierTransformer_fftw_plan)
            {
                fftwf_destroy_plan(pf);
                fftwf_destroy_plan(pb);
            }
        } else {
            fftwf_execute_dft_r2c(shared, rbuf[f], cbuf[f]);
        }
    }
    double el = omp_get_wtime() - t;
    if (shared) fftwf_destroy_plan(shared);
    return el;
}

int main(int argc, char **argv) {
    const char *which = argc > 1 ? argv[1] : "all";
    int js[] = {1, 2, 4, 8, 16, 32}, nj = 6;
    if (!strcmp(which, "fft") || !strcmp(which, "all")) alloc_fft();

    for (int m = 0; m < 4; m++) {
        const char *name = (const char *[]){"cpu", "mem", "fft-sharedplan", "fft-percallplan"}[m];
        if (strcmp(which, "all") && strncmp(which, name, strlen(which))) continue;
        printf("== %s ==\n", name);
        double base = 0;
        for (int i = 0; i < nj; i++) {
            int j = js[i];
            double el = 0;
            if (m == 0) el = bench_cpu(j);
            else if (m == 1) el = bench_mem(j);
            else el = bench_fft(j, m == 3);
            if (i == 0) base = el;
            /* cpu/mem scale the work with j, so those are efficiency-vs-1-thread
               at constant per-thread work; fft is fixed total work (strong scaling) */
            if (m <= 1) printf("  j=%-3d %8.3f s   weak-eff %.2fx\n", j, el, base / el * 1.0);
            else        printf("  j=%-3d %8.3f s   speedup %5.2fx  eff %5.1f%%\n", j, el, base / el, 100.0 * base / el / j);
            fflush(stdout);
        }
    }
    return 0;
}
