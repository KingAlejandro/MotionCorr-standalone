// Precondition test for experiment A (compressed-input lookahead).
//
// Does exactly what the proposed producer thread would do and nothing else:
//   Pass A  - TIFFSetDirectory + tag screen + TIFFRawStripSize for every strip,
//             single-threaded, mirroring cuda_movie_session.cu:1163-1230
//   Pass B' - TIFFReadRawStrip of every strip into a malloc'd buffer, OpenMP with
//             a per-thread TIFFOpen, mirroring the read loop at :1420-1483
// No CUDA, no gain, no mutable movie state. Paced at one movie per --pace ms so it
// imitates the real producer's duty cycle instead of running flat out.
//
// Run alone  -> the stageable work per movie, i.e. A's numerator on this silicon.
// Run alongside an unmodified 24-movie job -> whether the headroom actually exists.
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <tiffio.h>
#include <omp.h>

static double now_ms(void) {
    struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec * 1000.0 + t.tv_nsec / 1e6;
}

int main(int argc, char **argv) {
    int threads = 8; double pace = 340.0; int reps = 1; const char *list = NULL;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--threads") && i + 1 < argc) threads = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--pace") && i + 1 < argc) pace = atof(argv[++i]);
        else if (!strcmp(argv[i], "--reps") && i + 1 < argc) reps = atoi(argv[++i]);
        else list = argv[i];
    }
    if (!list) { fprintf(stderr, "usage: ingest_probe [--threads N] [--pace MS] [--reps N] <filelist>\n"); return 2; }
    TIFFSetWarningHandler(NULL);

    char *files[256]; int nf = 0;
    FILE *fp = fopen(list, "r"); if (!fp) { perror(list); return 2; }
    char line[4096];
    while (nf < 256 && fgets(line, sizeof line, fp)) {
        line[strcspn(line, "\r\n")] = 0;
        if (line[0]) files[nf++] = strdup(line);
    }
    fclose(fp);

    double t_scan_tot = 0, t_read_tot = 0, t_all0 = now_ms();
    long long bytes_tot = 0; int movies = 0;
    printf("movie,scan_ms,read_ms,total_ms,bytes,frames,strips\n");
    for (int r = 0; r < reps; r++)
    for (int m = 0; m < nf; m++) {
        double tm0 = now_ms();
        TIFF *tif = TIFFOpen(files[m], "r");
        if (!tif) { fprintf(stderr, "open failed %s\n", files[m]); continue; }
        int ndir = 0; while (TIFFReadDirectory(tif)) ndir++; ndir++;
        TIFFSetDirectory(tif, 0);
        uint32_t w = 0, h = 0; TIFFGetField(tif, TIFFTAG_IMAGEWIDTH, &w);
        TIFFGetField(tif, TIFFTAG_IMAGELENGTH, &h);
        int nframes = ndir < 24 ? ndir : 24;
        int ny = (int)h;
        uint32_t **raw = malloc(sizeof(uint32_t*) * nframes);
        // ---- Pass A: single-threaded scan, as in the real code ----
        double ta0 = now_ms();
        for (int f = 0; f < nframes; f++) {
            TIFFSetDirectory(tif, f);
            uint16_t bits = 0, comp = 0, planar = 1, samples = 1, pred = 1, sf = 1, fo = 1;
            TIFFGetField(tif, TIFFTAG_BITSPERSAMPLE, &bits);
            TIFFGetField(tif, TIFFTAG_COMPRESSION, &comp);
            TIFFGetFieldDefaulted(tif, TIFFTAG_PLANARCONFIG, &planar);
            TIFFGetFieldDefaulted(tif, TIFFTAG_SAMPLESPERPIXEL, &samples);
            TIFFGetFieldDefaulted(tif, TIFFTAG_PREDICTOR, &pred);
            TIFFGetFieldDefaulted(tif, TIFFTAG_SAMPLEFORMAT, &sf);
            TIFFGetFieldDefaulted(tif, TIFFTAG_FILLORDER, &fo);
            (void)TIFFNumberOfStrips(tif); (void)TIFFStripSize(tif);
            raw[f] = malloc(sizeof(uint32_t) * ny);
            for (int s = 0; s < ny; s++) raw[f][s] = (uint32_t)TIFFRawStripSize(tif, s);
        }
        double ta1 = now_ms();
        TIFFClose(tif);
        // ---- Pass B': parallel raw strip reads, per-thread TIFFOpen ----
        long long bytes = 0;
        double tb0 = now_ms();
        #pragma omp parallel num_threads(threads) reduction(+:bytes)
        {
            TIFF *t = TIFFOpen(files[m], "r");
            if (t) {
                size_t cap = 1 << 20; void *buf = malloc(cap);
                #pragma omp for schedule(dynamic, 1)
                for (int f = 0; f < nframes; f++) {
                    TIFFSetDirectory(t, f);
                    for (int s = 0; s < ny; s++) {
                        uint32_t need = raw[f][s];
                        if (need > cap) { cap = need; buf = realloc(buf, cap); }
                        tmsize_t got = TIFFReadRawStrip(t, s, buf, (tmsize_t)need);
                        if (got > 0) bytes += got;
                    }
                }
                free(buf); TIFFClose(t);
            }
        }
        double tb1 = now_ms();
        for (int f = 0; f < nframes; f++) free(raw[f]);
        free(raw);
        double tm1 = now_ms();
        printf("%s,%.1f,%.1f,%.1f,%lld,%d,%d\n", files[m], ta1-ta0, tb1-tb0, tm1-tm0, bytes, nframes, ny);
        fflush(stdout);
        t_scan_tot += ta1-ta0; t_read_tot += tb1-tb0; bytes_tot += bytes; movies++;
        double spent = now_ms() - tm0;
        if (pace > spent) { struct timespec s = {0, (long)((pace-spent)*1e6)}; nanosleep(&s, NULL); }
    }
    double wall = now_ms() - t_all0;
    fprintf(stderr, "SUMMARY movies=%d threads=%d pace=%.0fms scan=%.1fms/movie read=%.1fms/movie stageable=%.1fms/movie bytes=%lld wall=%.2fs\n",
            movies, threads, pace, t_scan_tot/movies, t_read_tot/movies,
            (t_scan_tot+t_read_tot)/movies, bytes_tot, wall/1000.0);
    return 0;
}
