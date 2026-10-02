// Isolated native harness for the CUDA Graph question on the dose-weighted
// reconstruction region. Not part of the product build; no production file is
// modified by it. The device code is lifted verbatim from
// src/acc/cuda/cuda_realspace_dw.cu at build time (see extract_kernels.py), so
// every arm runs the shipped kernels with the shipped launch geometry.
//
// Arms
//   prod   replica of the current loop: legacy stream, synchronous D2D copy,
//          three cudaEventSynchronize per frame (the telemetry the product reads)
//   async  same operations and order on one non-blocking stream, async copies,
//          one synchronization at the end
//   g1     one-frame graph, instantiated once, replayed once per frame with
//          per-frame node updates
//   g0     whole-movie graph captured, instantiated, launched and destroyed
//          inside the timed region (graph construction charged to the candidate)
//   greuse whole-movie graph built once and replayed per movie after node
//          updates (the stable-resource case)
//
// Operation order is identical in every arm: memset, then for each frame in
// ascending order a D2D copy, the dose-weight kernel, the C2R transform and the
// accumulation kernel, all stream-ordered, then one D2H of the sum.

#include <cuda_runtime.h>
#include <cufft.h>

#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <unistd.h>
#include <map>
#include <string>
#include <vector>

#include "dw_kernels_generated.cuh"

// ---------------------------------------------------------------- utilities

static bool g_abort_on_error = true;

#define CK(cmd) do { cudaError_t e_ = (cmd); if (e_ != cudaSuccess) { \
    fprintf(stderr, "CUDA %s:%d %s -> %s\n", __FILE__, __LINE__, #cmd, cudaGetErrorString(e_)); \
    if (g_abort_on_error) exit(2); } } while (0)

#define FK(cmd) do { cufftResult r_ = (cmd); if (r_ != CUFFT_SUCCESS) { \
    fprintf(stderr, "cuFFT %s:%d %s -> %d\n", __FILE__, __LINE__, #cmd, (int)r_); \
    if (g_abort_on_error) exit(2); } } while (0)

static double wall_s() {
    struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec + 1e-9 * t.tv_nsec;
}
static double cpu_s() {
    struct timespec t; clock_gettime(CLOCK_THREAD_CPUTIME_ID, &t);
    return t.tv_sec + 1e-9 * t.tv_nsec;
}

static unsigned long long fnv1a(const void *p, size_t n) {
    const unsigned char *b = (const unsigned char *)p;
    unsigned long long h = 1469598103934665603ULL;
    for (size_t i = 0; i < n; ++i) { h ^= b[i]; h *= 1099511628211ULL; }
    return h;
}

// ------------------------------------------------------------------ context

struct Ctx {
    int nx = 0, ny = 0, n_frames = 0;
    int nfx = 0, nfy = 0, nfy_half = 0;
    float nfx2 = 0.f, nfy2 = 0.f, apix = 1.f;
    size_t sz_fframe = 0, sz_iframe = 0, total_pixels = 0;

    float2 *d_Fframes = nullptr;   // persistent aligned Fourier frames
    float2 *d_Fframe  = nullptr;   // per-frame scratch (C2R destroys its input)
    float  *d_Iframe  = nullptr;
    float  *d_Isum    = nullptr;
    float  *d_doses   = nullptr;

    cufftHandle plan = 0;
    const ProbeModel *model = nullptr;   // null => accumulateDirectKernel

    dim3 blockDW, gridDW, blockInterp, gridInterp;
    int block1D = 256, grid1D = 0;

    std::vector<float> h_out;
};

static void ctx_build(Ctx &c, int nx, int ny, int n_frames, float apix,
                      const ProbeModel *model, const std::vector<float> &doses) {
    c.nx = nx; c.ny = ny; c.n_frames = n_frames; c.apix = apix; c.model = model;
    c.nfx = nx / 2 + 1; c.nfy = ny; c.nfy_half = c.nfy / 2;
    c.nfy2 = (float)c.nfy * (float)c.nfy;
    c.nfx2 = (float)(c.nfx - 1) * (float)(c.nfx - 1) * 4.0f;
    c.sz_fframe = (size_t)c.nfy * c.nfx * sizeof(float2);
    c.sz_iframe = (size_t)ny * nx * sizeof(float);
    c.total_pixels = (size_t)ny * nx;

    CK(cudaMalloc((void **)&c.d_Fframes, c.sz_fframe * n_frames));
    CK(cudaMalloc((void **)&c.d_Fframe, c.sz_fframe));
    CK(cudaMalloc((void **)&c.d_Iframe, c.sz_iframe));
    CK(cudaMalloc((void **)&c.d_Isum, c.sz_iframe));
    CK(cudaMalloc((void **)&c.d_doses, n_frames * sizeof(float)));
    CK(cudaMemcpy(c.d_doses, doses.data(), n_frames * sizeof(float), cudaMemcpyHostToDevice));

    // Deterministic, frame-dependent synthetic Fourier content.
    std::vector<float2> h(c.sz_fframe / sizeof(float2));
    for (int f = 0; f < n_frames; ++f) {
        for (size_t i = 0; i < h.size(); ++i) {
            unsigned int s = (unsigned int)(i * 2654435761u + (unsigned int)f * 40503u);
            h[i].x = (float)((int)(s % 20001) - 10000) * 1e-3f;
            h[i].y = (float)((int)((s >> 7) % 20001) - 10000) * 1e-3f;
        }
        CK(cudaMemcpy(c.d_Fframes + (size_t)f * c.nfy * c.nfx, h.data(), c.sz_fframe,
                      cudaMemcpyHostToDevice));
    }

    int n[2] = {ny, nx};
    size_t work = 0;
    FK(cufftCreate(&c.plan));
    FK(cufftMakePlanMany(c.plan, 2, n, NULL, 1, 0, NULL, 1, 0, CUFFT_C2R, 1, &work));

    c.blockDW = dim3(16, 16);
    c.gridDW = dim3((c.nfx + 15) / 16, (c.nfy + 15) / 16);
    c.blockInterp = dim3(16, 16);
    c.gridInterp = dim3((nx + 15) / 16, (ny + 15) / 16);
    c.grid1D = (int)((c.total_pixels + c.block1D - 1) / c.block1D);
    c.h_out.resize(c.total_pixels);
}

static void ctx_free(Ctx &c) {
    if (c.plan) cufftDestroy(c.plan);
    cudaFree(c.d_Fframes); cudaFree(c.d_Fframe); cudaFree(c.d_Iframe);
    cudaFree(c.d_Isum); cudaFree(c.d_doses);
}

// ---------------------------------------------------- one frame's submission

// sync_copy selects the product's blocking cudaMemcpy; everything else is
// stream-ordered on `s`. The op sequence is the same either way.
static void submit_frame(Ctx &c, int iframe, cudaStream_t s, bool sync_copy) {
    const float2 *src = c.d_Fframes + (size_t)iframe * c.nfy * c.nfx;
    if (sync_copy) {
        CK(cudaMemcpy(c.d_Fframe, src, c.sz_fframe, cudaMemcpyDeviceToDevice));
    } else {
        CK(cudaMemcpyAsync(c.d_Fframe, src, c.sz_fframe, cudaMemcpyDeviceToDevice, s));
    }

    applyDoseWeightKernel<<<c.gridDW, c.blockDW, 0, s>>>(
        c.d_Fframe, c.nfx, c.nfy, c.nfy_half, c.nfx2, c.nfy2, c.apix,
        c.d_doses, c.n_frames, iframe);

    FK(cufftExecC2R(c.plan, (cufftComplex *)c.d_Fframe, (cufftReal *)c.d_Iframe));

    if (c.model != nullptr) {
        const FramePolynomial k = polynomialForFrame(*c.model, iframe);
        interpolateAndAccumulatePolynomialKernel<<<c.gridInterp, c.blockInterp, 0, s>>>(
            c.d_Isum, nullptr, c.d_Iframe, c.nx, c.ny,
            k.x[0], k.x[1], k.x[2], k.x[3], k.x[4], k.x[5],
            k.y[0], k.y[1], k.y[2], k.y[3], k.y[4], k.y[5]);
    } else {
        accumulateDirectKernel<<<c.grid1D, c.block1D, 0, s>>>(
            c.d_Isum, nullptr, c.d_Iframe, c.total_pixels);
    }
}

// --------------------------------------------------------------- node index

// Our own nodes, in the topological order of the captured chain. cuFFT nodes are
// opaque and are never touched.
struct NodeIndex {
    std::vector<cudaGraphNode_t> memcpy_nodes;   // one per frame
    std::vector<cudaGraphNode_t> dw_nodes;       // one per frame
    std::vector<cudaGraphNode_t> acc_nodes;      // one per frame
};

static bool topo_sort(cudaGraph_t g, std::vector<cudaGraphNode_t> &order) {
    size_t num_nodes = 0, num_edges = 0;
    CK(cudaGraphGetNodes(g, nullptr, &num_nodes));
    CK(cudaGraphGetEdges(g, nullptr, nullptr, &num_edges));
    std::vector<cudaGraphNode_t> nodes(num_nodes);
    CK(cudaGraphGetNodes(g, nodes.data(), &num_nodes));
    std::vector<cudaGraphNode_t> from(num_edges), to(num_edges);
    if (num_edges) CK(cudaGraphGetEdges(g, from.data(), to.data(), &num_edges));

    std::map<cudaGraphNode_t, int> idx;
    for (size_t i = 0; i < num_nodes; ++i) idx[nodes[i]] = (int)i;
    std::vector<std::vector<int>> adj(num_nodes);
    std::vector<int> indeg(num_nodes, 0);
    for (size_t e = 0; e < num_edges; ++e) {
        adj[idx[from[e]]].push_back(idx[to[e]]);
        indeg[idx[to[e]]]++;
    }
    // Deterministic tie-break on the runtime's node enumeration order; our own
    // nodes form a strict chain, so their relative order is fixed regardless.
    std::vector<int> ready;
    for (size_t i = 0; i < num_nodes; ++i) if (indeg[i] == 0) ready.push_back((int)i);
    order.clear();
    while (!ready.empty()) {
        std::sort(ready.begin(), ready.end());
        int v = ready.front();
        ready.erase(ready.begin());
        order.push_back(nodes[v]);
        for (int w : adj[v]) if (--indeg[w] == 0) ready.push_back(w);
    }
    return order.size() == num_nodes;
}

static bool index_nodes(Ctx &c, cudaGraph_t g, NodeIndex &ni, int expect) {
    std::vector<cudaGraphNode_t> order;
    if (!topo_sort(g, order)) { fprintf(stderr, "graph is not a DAG\n"); return false; }
    void *dw_fn = (void *)applyDoseWeightKernel;
    void *acc_fn = c.model ? (void *)interpolateAndAccumulatePolynomialKernel
                           : (void *)accumulateDirectKernel;
    for (cudaGraphNode_t n : order) {
        cudaGraphNodeType t;
        CK(cudaGraphNodeGetType(n, &t));
        if (t == cudaGraphNodeTypeMemcpy) {
            ni.memcpy_nodes.push_back(n);
        } else if (t == cudaGraphNodeTypeKernel) {
            cudaKernelNodeParams p{};
            if (cudaGraphKernelNodeGetParams(n, &p) != cudaSuccess) { cudaGetLastError(); continue; }
            if (p.func == dw_fn) ni.dw_nodes.push_back(n);
            else if (p.func == acc_fn) ni.acc_nodes.push_back(n);
        }
    }
    if ((int)ni.memcpy_nodes.size() != expect || (int)ni.dw_nodes.size() != expect ||
        (int)ni.acc_nodes.size() != expect) {
        fprintf(stderr, "node index mismatch: expected %d each, got memcpy=%zu dw=%zu acc=%zu\n",
                expect, ni.memcpy_nodes.size(), ni.dw_nodes.size(), ni.acc_nodes.size());
        return false;
    }
    return true;
}

// Rewrite the per-frame parameters of an instantiated graph. `frame_base` lets a
// one-frame graph be replayed for any frame.
struct FrameArgs {
    // storage must outlive the SetParams call
    float2 *d_Fframe; int nfx, nfy, nfy_half; float nfx2, nfy2, apix;
    float *d_doses; int n_frames; int iframe;
    float *d_Isum, *d_sub, *d_Iframe; int nx, ny;
    FramePolynomial k;
    size_t total_pixels;
    void *dw_args[10];
    void *acc_args[17];
};

static void fill_args(Ctx &c, FrameArgs &a, int iframe, const ProbeModel *model) {
    a.d_Fframe = c.d_Fframe; a.nfx = c.nfx; a.nfy = c.nfy; a.nfy_half = c.nfy_half;
    a.nfx2 = c.nfx2; a.nfy2 = c.nfy2; a.apix = c.apix;
    a.d_doses = c.d_doses; a.n_frames = c.n_frames; a.iframe = iframe;
    a.d_Isum = c.d_Isum; a.d_sub = nullptr; a.d_Iframe = c.d_Iframe;
    a.nx = c.nx; a.ny = c.ny; a.total_pixels = c.total_pixels;
    void *dw[] = {&a.d_Fframe, &a.nfx, &a.nfy, &a.nfy_half, &a.nfx2, &a.nfy2,
                  &a.apix, &a.d_doses, &a.n_frames, &a.iframe};
    memcpy(a.dw_args, dw, sizeof(dw));
    if (model) {
        a.k = polynomialForFrame(*model, iframe);
        void *ac[] = {&a.d_Isum, &a.d_sub, &a.d_Iframe, &a.nx, &a.ny,
                      &a.k.x[0], &a.k.x[1], &a.k.x[2], &a.k.x[3], &a.k.x[4], &a.k.x[5],
                      &a.k.y[0], &a.k.y[1], &a.k.y[2], &a.k.y[3], &a.k.y[4], &a.k.y[5]};
        memcpy(a.acc_args, ac, sizeof(ac));
    } else {
        void *ac[] = {&a.d_Isum, &a.d_sub, &a.d_Iframe, &a.total_pixels};
        memcpy(a.acc_args, ac, sizeof(ac));
    }
}

static void update_frame_nodes(Ctx &c, cudaGraphExec_t exec, const NodeIndex &ni,
                               int node_slot, int iframe, const ProbeModel *model,
                               FrameArgs &a) {
    fill_args(c, a, iframe, model);

    cudaMemcpy3DParms mp{};
    mp.srcPtr = make_cudaPitchedPtr((void *)(c.d_Fframes + (size_t)iframe * c.nfy * c.nfx),
                                    c.sz_fframe, c.sz_fframe, 1);
    mp.dstPtr = make_cudaPitchedPtr((void *)c.d_Fframe, c.sz_fframe, c.sz_fframe, 1);
    mp.extent = make_cudaExtent(c.sz_fframe, 1, 1);
    mp.kind = cudaMemcpyDeviceToDevice;
    CK(cudaGraphExecMemcpyNodeSetParams(exec, ni.memcpy_nodes[node_slot], &mp));

    cudaKernelNodeParams dwp{};
    dwp.func = (void *)applyDoseWeightKernel;
    dwp.gridDim = c.gridDW; dwp.blockDim = c.blockDW; dwp.sharedMemBytes = 0;
    dwp.kernelParams = a.dw_args;
    CK(cudaGraphExecKernelNodeSetParams(exec, ni.dw_nodes[node_slot], &dwp));

    cudaKernelNodeParams ap{};
    if (model) {
        ap.func = (void *)interpolateAndAccumulatePolynomialKernel;
        ap.gridDim = c.gridInterp; ap.blockDim = c.blockInterp;
    } else {
        ap.func = (void *)accumulateDirectKernel;
        ap.gridDim = dim3(c.grid1D); ap.blockDim = dim3(c.block1D);
    }
    ap.sharedMemBytes = 0;
    ap.kernelParams = a.acc_args;
    CK(cudaGraphExecKernelNodeSetParams(exec, ni.acc_nodes[node_slot], &ap));
}

// ------------------------------------------------------------------ results

struct Timing {
    double wall = 0, submit_cpu = 0;
    double capture = 0, instantiate = 0, update = 0, launch = 0, sync = 0, destroy = 0;
    unsigned long long digest = 0;
    int graph_nodes = 0, graph_edges = 0;
};

static void finish_and_read(Ctx &c, Timing &t, cudaStream_t s) {
    double t0 = wall_s();
    CK(cudaStreamSynchronize(s));
    t.sync += wall_s() - t0;
    CK(cudaMemcpy(c.h_out.data(), c.d_Isum, c.sz_iframe, cudaMemcpyDeviceToHost));
    t.digest = fnv1a(c.h_out.data(), c.sz_iframe);
}

// ------------------------------------------------------------------- arm run

static Timing run_prod(Ctx &c) {
    Timing t;
    cudaEvent_t e[6];
    for (int i = 0; i < 6; ++i) CK(cudaEventCreate(&e[i]));
    double w0 = wall_s(), p0 = cpu_s();
    CK(cudaMemset(c.d_Isum, 0, c.sz_iframe));
    for (int f = 0; f < c.n_frames; ++f) {
        const float2 *src = c.d_Fframes + (size_t)f * c.nfy * c.nfx;
        CK(cudaMemcpy(c.d_Fframe, src, c.sz_fframe, cudaMemcpyDeviceToDevice));
        CK(cudaEventRecord(e[0]));
        applyDoseWeightKernel<<<c.gridDW, c.blockDW>>>(
            c.d_Fframe, c.nfx, c.nfy, c.nfy_half, c.nfx2, c.nfy2, c.apix,
            c.d_doses, c.n_frames, f);
        CK(cudaGetLastError());
        CK(cudaEventRecord(e[1]));
        CK(cudaEventSynchronize(e[1]));
        float ms; CK(cudaEventElapsedTime(&ms, e[0], e[1]));

        CK(cudaEventRecord(e[2]));
        FK(cufftExecC2R(c.plan, (cufftComplex *)c.d_Fframe, (cufftReal *)c.d_Iframe));
        CK(cudaEventRecord(e[3]));
        CK(cudaEventSynchronize(e[3]));
        CK(cudaEventElapsedTime(&ms, e[2], e[3]));

        CK(cudaEventRecord(e[4]));
        if (c.model) {
            const FramePolynomial k = polynomialForFrame(*c.model, f);
            interpolateAndAccumulatePolynomialKernel<<<c.gridInterp, c.blockInterp>>>(
                c.d_Isum, nullptr, c.d_Iframe, c.nx, c.ny,
                k.x[0], k.x[1], k.x[2], k.x[3], k.x[4], k.x[5],
                k.y[0], k.y[1], k.y[2], k.y[3], k.y[4], k.y[5]);
        } else {
            accumulateDirectKernel<<<c.grid1D, c.block1D>>>(
                c.d_Isum, nullptr, c.d_Iframe, c.total_pixels);
        }
        CK(cudaGetLastError());
        CK(cudaEventRecord(e[5]));
        CK(cudaEventSynchronize(e[5]));
        CK(cudaEventElapsedTime(&ms, e[4], e[5]));
    }
    t.submit_cpu = cpu_s() - p0;
    finish_and_read(c, t, 0);
    t.wall = wall_s() - w0;
    for (int i = 0; i < 6; ++i) CK(cudaEventDestroy(e[i]));
    return t;
}

static Timing run_async(Ctx &c, cudaStream_t s) {
    Timing t;
    FK(cufftSetStream(c.plan, s));
    double w0 = wall_s(), p0 = cpu_s();
    CK(cudaMemsetAsync(c.d_Isum, 0, c.sz_iframe, s));
    for (int f = 0; f < c.n_frames; ++f) submit_frame(c, f, s, false);
    t.submit_cpu = cpu_s() - p0;
    finish_and_read(c, t, s);
    t.wall = wall_s() - w0;
    FK(cufftSetStream(c.plan, 0));
    return t;
}

// Capture the whole movie (memset + every frame) into one graph.
static cudaGraph_t capture_movie(Ctx &c, cudaStream_t s, const ProbeModel *model) {
    const ProbeModel *saved = c.model;
    c.model = model;
    cudaGraph_t g = nullptr;
    FK(cufftSetStream(c.plan, s));
    CK(cudaStreamBeginCapture(s, cudaStreamCaptureModeThreadLocal));
    CK(cudaMemsetAsync(c.d_Isum, 0, c.sz_iframe, s));
    for (int f = 0; f < c.n_frames; ++f) submit_frame(c, f, s, false);
    CK(cudaStreamEndCapture(s, &g));
    FK(cufftSetStream(c.plan, 0));
    c.model = saved;
    return g;
}

// Capture the movie with every frame slot carrying one frame's parameters. Used
// to build a graph that is deliberately wrong, so that the node-update path has
// something observable to correct.
static cudaGraph_t capture_movie_fixed(Ctx &c, cudaStream_t s, const ProbeModel *model,
                                       int fixed) {
    const ProbeModel *saved = c.model;
    c.model = model;
    cudaGraph_t g = nullptr;
    FK(cufftSetStream(c.plan, s));
    CK(cudaStreamBeginCapture(s, cudaStreamCaptureModeThreadLocal));
    CK(cudaMemsetAsync(c.d_Isum, 0, c.sz_iframe, s));
    for (int f = 0; f < c.n_frames; ++f) submit_frame(c, fixed, s, false);
    CK(cudaStreamEndCapture(s, &g));
    FK(cufftSetStream(c.plan, 0));
    c.model = saved;
    return g;
}

static cudaGraph_t capture_one_frame(Ctx &c, cudaStream_t s) {
    cudaGraph_t g = nullptr;
    FK(cufftSetStream(c.plan, s));
    CK(cudaStreamBeginCapture(s, cudaStreamCaptureModeThreadLocal));
    submit_frame(c, 0, s, false);
    CK(cudaStreamEndCapture(s, &g));
    FK(cufftSetStream(c.plan, 0));
    return g;
}

static void graph_size(cudaGraph_t g, Timing &t) {
    size_t n = 0, e = 0;
    CK(cudaGraphGetNodes(g, nullptr, &n));
    CK(cudaGraphGetEdges(g, nullptr, nullptr, &e));
    t.graph_nodes = (int)n; t.graph_edges = (int)e;
}

// g0: everything (capture, instantiate, launch, destroy) inside the timed region.
static Timing run_g0(Ctx &c, cudaStream_t s) {
    Timing t;
    double w0 = wall_s(), p0 = cpu_s();
    double a = wall_s();
    cudaGraph_t g = capture_movie(c, s, c.model);
    t.capture = wall_s() - a;
    graph_size(g, t);
    a = wall_s();
    cudaGraphExec_t exec = nullptr;
    CK(cudaGraphInstantiate(&exec, g, 0));
    t.instantiate = wall_s() - a;
    a = wall_s();
    CK(cudaGraphLaunch(exec, s));
    t.launch = wall_s() - a;
    t.submit_cpu = cpu_s() - p0;
    finish_and_read(c, t, s);
    a = wall_s();
    CK(cudaGraphExecDestroy(exec));
    CK(cudaGraphDestroy(g));
    t.destroy = wall_s() - a;
    t.wall = wall_s() - w0;
    FK(cufftSetStream(c.plan, 0));
    return t;
}

// g1: a one-frame graph replayed n_frames times, parameters rewritten per frame.
struct OneFrameGraph {
    cudaGraph_t g = nullptr; cudaGraphExec_t exec = nullptr; NodeIndex ni;
};
static void build_one_frame(Ctx &c, cudaStream_t s, OneFrameGraph &G, Timing &t) {
    double a = wall_s();
    G.g = capture_one_frame(c, s);
    t.capture = wall_s() - a;
    graph_size(G.g, t);
    if (!index_nodes(c, G.g, G.ni, 1)) exit(3);
    a = wall_s();
    CK(cudaGraphInstantiate(&G.exec, G.g, 0));
    t.instantiate = wall_s() - a;
}
static Timing run_g1(Ctx &c, cudaStream_t s, OneFrameGraph &G) {
    Timing t;
    FrameArgs a{};
    double w0 = wall_s(), p0 = cpu_s();
    CK(cudaMemsetAsync(c.d_Isum, 0, c.sz_iframe, s));
    for (int f = 0; f < c.n_frames; ++f) {
        double u = wall_s();
        update_frame_nodes(c, G.exec, G.ni, 0, f, c.model, a);
        t.update += wall_s() - u;
        double l = wall_s();
        CK(cudaGraphLaunch(G.exec, s));
        t.launch += wall_s() - l;
    }
    t.submit_cpu = cpu_s() - p0;
    finish_and_read(c, t, s);
    t.wall = wall_s() - w0;
    return t;
}

// greuse: whole-movie graph built once, replayed per movie after node updates.
struct MovieGraph {
    cudaGraph_t g = nullptr; cudaGraphExec_t exec = nullptr; NodeIndex ni;
};
static void build_movie(Ctx &c, cudaStream_t s, MovieGraph &G, Timing &t,
                        const ProbeModel *build_model, int fixed_frame = -1) {
    double a = wall_s();
    G.g = (fixed_frame < 0) ? capture_movie(c, s, build_model)
                            : capture_movie_fixed(c, s, build_model, fixed_frame);
    t.capture = wall_s() - a;
    graph_size(G.g, t);
    if (!index_nodes(c, G.g, G.ni, c.n_frames)) exit(3);
    a = wall_s();
    CK(cudaGraphInstantiate(&G.exec, G.g, 0));
    t.instantiate = wall_s() - a;
}
static Timing run_greuse(Ctx &c, cudaStream_t s, MovieGraph &G, bool do_update) {
    Timing t;
    std::vector<FrameArgs> args(c.n_frames);
    double w0 = wall_s(), p0 = cpu_s();
    if (do_update) {
        double u = wall_s();
        for (int f = 0; f < c.n_frames; ++f)
            update_frame_nodes(c, G.exec, G.ni, f, f, c.model, args[f]);
        t.update = wall_s() - u;
    }
    double l = wall_s();
    CK(cudaGraphLaunch(G.exec, s));
    t.launch = wall_s() - l;
    t.submit_cpu = cpu_s() - p0;
    finish_and_read(c, t, s);
    t.wall = wall_s() - w0;
    return t;
}

// ------------------------------------------------------------ failure probes

// Each probe drives one failure class and reports whether the graph path
// detected it and whether a sum could still have been published.
static void run_failure_controls(Ctx &c, cudaStream_t s) {
    g_abort_on_error = false;
    printf("{\"section\":\"failure_controls\",\"cases\":[\n");
    bool first = true;
    auto emit = [&](const char *name, const char *detected_at, int rc,
                    const char *errstr, const char *publishable, const char *note) {
        printf("%s {\"case\":\"%s\",\"detected_at\":\"%s\",\"rc\":%d,"
               "\"error\":\"%s\",\"publish_allowed\":\"%s\",\"note\":\"%s\"}\n",
               first ? " " : ",", name, detected_at, rc, errstr, publishable, note);
        fflush(stdout);
        first = false;
    };

    // 1a. The telemetry the product reads today: an event record plus
    //     cudaEventSynchronize inside the captured region. This is the
    //     prohibited operation that actually applies to this code.
    {
        cudaGraph_t g = nullptr;
        cudaEvent_t ev; cudaEventCreate(&ev);
        FK(cufftSetStream(c.plan, s));
        cudaStreamBeginCapture(s, cudaStreamCaptureModeThreadLocal);
        submit_frame(c, 0, s, false);
        cudaEventRecord(ev, s);
        cudaError_t esync = cudaEventSynchronize(ev);
        cudaError_t end = cudaStreamEndCapture(s, &g);
        emit("event_synchronize_inside_capture",
             esync != cudaSuccess ? "cudaEventSynchronize"
                                  : (end != cudaSuccess ? "cudaStreamEndCapture" : "undetected"),
             (int)end, cudaGetErrorString(end),
             (esync != cudaSuccess || end != cudaSuccess) ? "no" : "YES-BUG",
             g == nullptr ? "null graph returned" : "non-null graph");
        cudaGetLastError(); cudaEventDestroy(ev);
        if (g) cudaGraphDestroy(g);
        FK(cufftSetStream(c.plan, 0));
    }

    // 1b. A blocking synchronous copy during capture. Prohibited only when the
    //     capture stream is a blocking stream, because the legacy stream then
    //     encompasses it. Both variants are measured.
    for (int nonblocking = 1; nonblocking >= 0; --nonblocking) {
        cudaStream_t cs = nullptr;
        cudaStreamCreateWithFlags(&cs, nonblocking ? cudaStreamNonBlocking : cudaStreamDefault);
        cudaGraph_t g = nullptr;
        FK(cufftSetStream(c.plan, cs));
        cudaStreamBeginCapture(cs, cudaStreamCaptureModeThreadLocal);
        submit_frame(c, 0, cs, false);
        cudaError_t bad = cudaMemcpy(c.d_Iframe, c.d_Iframe, c.sz_iframe,
                                     cudaMemcpyDeviceToDevice);
        cudaError_t end = cudaStreamEndCapture(cs, &g);
        size_t n = 0; if (g) cudaGraphGetNodes(g, nullptr, &n);
        char note[96];
        snprintf(note, sizeof(note), "memcpy_rc=%d captured_nodes=%zu", (int)bad, n);
        emit(nonblocking ? "sync_memcpy_during_capture_nonblocking_stream"
                         : "sync_memcpy_during_capture_blocking_stream",
             (bad != cudaSuccess) ? "cudaMemcpy"
                                  : (end != cudaSuccess ? "cudaStreamEndCapture" : "undetected"),
             (int)end, cudaGetErrorString(end),
             (bad != cudaSuccess || end != cudaSuccess) ? "no" : "allowed-by-contract", note);
        cudaGetLastError();
        if (g) cudaGraphDestroy(g);
        cudaStreamDestroy(cs);
        FK(cufftSetStream(c.plan, 0));
    }

    // 2. Instantiation refused. Injected through an invalid flag word: a
    //    natural instantiation failure needs a graph the driver cannot realise,
    //    which this geometry does not produce.
    {
        cudaGraph_t g = capture_movie(c, s, c.model);
        cudaGraphExec_t exec = nullptr;
        cudaError_t r = cudaGraphInstantiateWithFlags(&exec, g, 0xFFFFULL);
        emit("instantiate_invalid_flags",
             r != cudaSuccess ? "cudaGraphInstantiateWithFlags" : "undetected", (int)r,
             cudaGetErrorString(r), r != cudaSuccess ? "no" : "YES-BUG",
             "injected, not a natural failure");
        cudaGetLastError();
        if (exec) cudaGraphExecDestroy(exec);
        cudaGraphDestroy(g);
    }

    // 3. Launch refused into a stream that is itself being captured.
    {
        cudaGraph_t g = capture_movie(c, s, c.model);
        cudaGraphExec_t exec = nullptr;
        cudaError_t i = cudaGraphInstantiate(&exec, g, 0);
        cudaStream_t cap = nullptr;
        cudaStreamCreateWithFlags(&cap, cudaStreamNonBlocking);
        cudaStreamBeginCapture(cap, cudaStreamCaptureModeThreadLocal);
        cudaError_t r = cudaGraphLaunch(exec, cap);
        cudaGraph_t junk = nullptr;
        cudaStreamEndCapture(cap, &junk);
        if (junk) cudaGraphDestroy(junk);
        cudaStreamDestroy(cap);
        emit("launch_into_capturing_stream",
             r != cudaSuccess ? "cudaGraphLaunch" : "undetected", (int)r,
             cudaGetErrorString(r), r != cudaSuccess ? "no" : "captured-as-child-node",
             i == cudaSuccess ? "instantiate ok" : "instantiate failed");
        cudaGetLastError();
        if (exec) cudaGraphExecDestroy(exec);
        cudaGraphDestroy(g);
    }

    // 4. cuFFT refuses to be captured when its stream is not the capture stream.
    {
        cudaGraph_t g = nullptr;
        FK(cufftSetStream(c.plan, 0));
        cudaStreamBeginCapture(s, cudaStreamCaptureModeThreadLocal);
        cufftResult fr = cufftExecC2R(c.plan, (cufftComplex *)c.d_Fframe,
                                      (cufftReal *)c.d_Iframe);
        cudaError_t end = cudaStreamEndCapture(s, &g);
        size_t ncap = 0; if (g) cudaGraphGetNodes(g, nullptr, &ncap);
        char buf[96];
        snprintf(buf, sizeof(buf), "cufft=%d captured_nodes=%zu", (int)fr, ncap);
        emit("cufft_plan_on_foreign_stream_during_capture",
             (fr != CUFFT_SUCCESS) ? "cufftExecC2R"
                                   : (end != cudaSuccess ? "cudaStreamEndCapture" : "undetected"),
             (int)end, buf,
             (fr != CUFFT_SUCCESS || end != cudaSuccess) ? "no" : "SILENT-ESCAPE",
             g == nullptr ? "null graph" : "non-null graph");
        cudaGetLastError();
        if (g) cudaGraphDestroy(g);
        FK(cufftSetStream(c.plan, s));
    }

    // 5. Illegal launch geometry rejected at capture time.
    {
        cudaGraph_t g = nullptr;
        cudaStreamBeginCapture(s, cudaStreamCaptureModeThreadLocal);
        applyDoseWeightKernel<<<dim3(0, 0), c.blockDW, 0, s>>>(
            c.d_Fframe, c.nfx, c.nfy, c.nfy_half, c.nfx2, c.nfy2, c.apix,
            c.d_doses, c.n_frames, 0);
        cudaError_t le = cudaGetLastError();
        cudaError_t end = cudaStreamEndCapture(s, &g);
        emit("zero_grid_kernel_during_capture",
             le != cudaSuccess ? "cudaGetLastError"
                               : (end != cudaSuccess ? "cudaStreamEndCapture" : "undetected"),
             (int)le, cudaGetErrorString(le),
             (le != cudaSuccess || end != cudaSuccess) ? "no" : "YES-BUG", "");
        cudaGetLastError();
        if (g) cudaGraphDestroy(g);
    }

    // 6. Out-of-range memcpy node update rejected before any launch.
    {
        MovieGraph G; Timing t;
        build_movie(c, s, G, t, c.model);
        cudaMemcpy3DParms mp{};
        mp.srcPtr = make_cudaPitchedPtr((void *)0x10, c.sz_fframe, c.sz_fframe, 1);
        mp.dstPtr = make_cudaPitchedPtr((void *)c.d_Fframe, c.sz_fframe, c.sz_fframe, 1);
        mp.extent = make_cudaExtent(c.sz_fframe, 1, 1);
        mp.kind = cudaMemcpyDeviceToDevice;
        cudaError_t r = cudaGraphExecMemcpyNodeSetParams(G.exec, G.ni.memcpy_nodes[0], &mp);
        emit("memcpy_node_update_invalid_pointer",
             r != cudaSuccess ? "cudaGraphExecMemcpyNodeSetParams" : "undetected",
             (int)r, cudaGetErrorString(r), r != cudaSuccess ? "no" : "deferred-to-launch", "");
        cudaGetLastError();
        cudaGraphExecDestroy(G.exec); cudaGraphDestroy(G.g);
    }

    // 7. Late failure: a device fault inside a replayed graph must be reported by
    //    the terminal synchronization, with no sum published.
    {
        MovieGraph G; Timing t;
        build_movie(c, s, G, t, c.model);
        FrameArgs a{};
        fill_args(c, a, 0, c.model);
        // Point the dose-weight kernel's output at an unmapped address.
        float2 *bad = (float2 *)0xdeadbeef000ULL;
        a.d_Fframe = bad;
        cudaKernelNodeParams dwp{};
        dwp.func = (void *)applyDoseWeightKernel;
        dwp.gridDim = c.gridDW; dwp.blockDim = c.blockDW; dwp.kernelParams = a.dw_args;
        cudaError_t up = cudaGraphExecKernelNodeSetParams(G.exec, G.ni.dw_nodes[0], &dwp);
        cudaError_t lr = cudaGraphLaunch(G.exec, s);
        cudaError_t sr = cudaStreamSynchronize(s);
        emit("device_fault_inside_replay",
             sr != cudaSuccess ? "cudaStreamSynchronize"
                               : (lr != cudaSuccess ? "cudaGraphLaunch" : "undetected"),
             (int)sr, cudaGetErrorString(sr),
             (sr != cudaSuccess || lr != cudaSuccess) ? "no" : "YES-BUG",
             up == cudaSuccess ? "node update accepted" : "node update refused");
        // The context is now poisoned; this probe is run last on purpose.
        printf("]}\n");
        fflush(stdout);
        _exit(0);
    }
}

// ----------------------------------------------------------- correctness run

static void print_timing(const char *arm, int rep, const Timing &t) {
    printf("{\"arm\":\"%s\",\"rep\":%d,\"wall_ms\":%.6f,\"submit_cpu_ms\":%.6f,"
           "\"capture_ms\":%.6f,\"instantiate_ms\":%.6f,\"update_ms\":%.6f,"
           "\"launch_ms\":%.6f,\"sync_ms\":%.6f,\"destroy_ms\":%.6f,"
           "\"nodes\":%d,\"edges\":%d,\"digest\":\"%016llx\"}\n",
           arm, rep, t.wall * 1e3, t.submit_cpu * 1e3, t.capture * 1e3,
           t.instantiate * 1e3, t.update * 1e3, t.launch * 1e3, t.sync * 1e3,
           t.destroy * 1e3, t.graph_nodes, t.graph_edges, t.digest);
}

int main(int argc, char **argv) {
    int nx = 3838, ny = 5760, frames = 24, reps = 5, warmup = 1, device = 0;
    int warmup_ms = 0;
    float apix = 0.885f;
    std::string model_kind = "poly", mode = "bench", dose_kind = "ramp", only = "";
    for (int i = 1; i < argc; ++i) {
        std::string a = argv[i];
        auto nextv = [&]() { return std::string(argv[++i]); };
        if (a == "--nx") nx = atoi(nextv().c_str());
        else if (a == "--ny") ny = atoi(nextv().c_str());
        else if (a == "--frames") frames = atoi(nextv().c_str());
        else if (a == "--reps") reps = atoi(nextv().c_str());
        else if (a == "--warmup") warmup = atoi(nextv().c_str());
        else if (a == "--warmup_ms") warmup_ms = atoi(nextv().c_str());
        else if (a == "--device") device = atoi(nextv().c_str());
        else if (a == "--apix") apix = (float)atof(nextv().c_str());
        else if (a == "--model") model_kind = nextv();
        else if (a == "--dose") dose_kind = nextv();
        else if (a == "--mode") mode = nextv();
        else if (a == "--only") only = nextv();
        else { fprintf(stderr, "unknown arg %s\n", a.c_str()); return 1; }
    }
    if (nx % 2 != 0) { fprintf(stderr, "nx must be even for C2R\n"); return 1; }
    CK(cudaSetDevice(device));

    std::vector<float> doses(frames);
    for (int i = 0; i < frames; ++i) {
        if (dose_kind == "ramp") doses[i] = 1.277f * (i + 1);
        else if (dose_kind == "zero") doses[i] = 0.0f;
        else if (dose_kind == "high") doses[i] = 6.0f * (i + 1) + 40.0f;
        else doses[i] = (float)atof(dose_kind.c_str()) * (i + 1);
    }

    ProbeModel m0{}, m1{};
    for (int i = 0; i < 18; ++i) {
        m0.cx[i] = 0.37 * std::sin(0.7 * i) ; m0.cy[i] = -0.23 * std::cos(0.41 * i);
        m1.cx[i] = -0.91 * std::cos(0.19 * i); m1.cy[i] = 0.55 * std::sin(1.13 * i);
    }
    const ProbeModel *model = (model_kind == "poly") ? &m0 : nullptr;

    Ctx c;
    ctx_build(c, nx, ny, frames, apix, model, doses);

    cudaStream_t s;
    CK(cudaStreamCreateWithFlags(&s, cudaStreamNonBlocking));

    printf("{\"section\":\"config\",\"nx\":%d,\"ny\":%d,\"frames\":%d,\"model\":\"%s\","
           "\"apix\":%.6f,\"dose\":\"%s\",\"reps\":%d,\"device\":%d}\n",
           nx, ny, frames, model_kind.c_str(), apix, dose_kind.c_str(), reps, device);

    // Force cuFFT module load and first-touch allocation before any capture, and
    // keep the device busy long enough that the SM clock is not still ramping
    // when the first measured rep starts (persistence mode is off on this host).
    for (int i = 0; i < warmup + 1; ++i) { Timing w = run_async(c, s); (void)w; }
    if (warmup_ms > 0) {
        const double until = wall_s() + warmup_ms * 1e-3;
        while (wall_s() < until) { Timing w = run_async(c, s); (void)w; }
    }
    CK(cudaDeviceSynchronize());

    if (mode == "faults") { run_failure_controls(c, s); return 0; }

    if (mode == "exact") {
        Timing tp = run_prod(c);
        std::vector<float> ref = c.h_out;
        print_timing("prod", 0, tp);

        Timing ta = run_async(c, s);
        print_timing("async", 0, ta);
        bool ok_async = memcmp(ref.data(), c.h_out.data(), c.sz_iframe) == 0;

        Timing t0 = run_g0(c, s);
        print_timing("g0", 0, t0);
        bool ok_g0 = memcmp(ref.data(), c.h_out.data(), c.sz_iframe) == 0;

        OneFrameGraph G1; Timing b1;
        build_one_frame(c, s, G1, b1);
        Timing t1 = run_g1(c, s, G1);
        print_timing("g1", 0, t1);
        bool ok_g1 = memcmp(ref.data(), c.h_out.data(), c.sz_iframe) == 0;

        MovieGraph GM; Timing bm;
        build_movie(c, s, GM, bm, model);
        Timing tm = run_greuse(c, s, GM, true);
        print_timing("greuse", 0, tm);
        bool ok_gm = memcmp(ref.data(), c.h_out.data(), c.sz_iframe) == 0;

        // Control: the reused graph must respond to node updates. The graph is
        // built with every frame slot carrying frame 0's parameters, so a graph
        // that ignored updates would sum frame 0 n_frames times. At n_frames==1
        // that graph is already correct, so the control cannot observe anything
        // and is reported as inapplicable rather than as a pass.
        bool ok_ctrl = true, ctrl_applicable = (frames >= 2);
        unsigned long long stale_digest = 0, updated_digest = 0;
        if (ctrl_applicable) {
            MovieGraph GS; Timing bs;
            build_movie(c, s, GS, bs, model, 0);
            Timing ts = run_greuse(c, s, GS, false); // no update -> must differ
            stale_digest = ts.digest;
            Timing tu = run_greuse(c, s, GS, true);  // update -> must match ref
            updated_digest = tu.digest;
            ok_ctrl = (stale_digest != tp.digest) &&
                      (memcmp(ref.data(), c.h_out.data(), c.sz_iframe) == 0);
            cudaGraphExecDestroy(GS.exec); cudaGraphDestroy(GS.g);
        }

        printf("{\"section\":\"exact\",\"ref_digest\":\"%016llx\",\"async\":%s,"
               "\"g0\":%s,\"g1\":%s,\"greuse\":%s,\"update_control_applicable\":%s,"
               "\"update_control\":%s,\"stale_digest\":\"%016llx\",\"updated_digest\":\"%016llx\"}\n",
               tp.digest, ok_async ? "true" : "false", ok_g0 ? "true" : "false",
               ok_g1 ? "true" : "false", ok_gm ? "true" : "false",
               ctrl_applicable ? "true" : "false", ok_ctrl ? "true" : "false",
               stale_digest, updated_digest);

        cudaGraphExecDestroy(G1.exec); cudaGraphDestroy(G1.g);
        cudaGraphExecDestroy(GM.exec); cudaGraphDestroy(GM.g);
        bool all = ok_async && ok_g0 && ok_g1 && ok_gm && ok_ctrl;
        ctx_free(c); cudaStreamDestroy(s);
        return all ? 0 : 4;
    }

    // bench: arms interleaved within each rep so drift hits all of them.
    OneFrameGraph G1; Timing b1;
    build_one_frame(c, s, G1, b1);
    print_timing("g1_build", -1, b1);
    MovieGraph GM; Timing bm;
    build_movie(c, s, GM, bm, model);
    print_timing("greuse_build", -1, bm);

    auto want = [&](const char *n) { return only.empty() || only == n; };
    for (int r = 0; r < reps; ++r) {
        if (want("prod"))   print_timing("prod", r, run_prod(c));
        if (want("async"))  print_timing("async", r, run_async(c, s));
        if (want("g0"))     print_timing("g0", r, run_g0(c, s));
        if (want("g1"))     print_timing("g1", r, run_g1(c, s, G1));
        if (want("greuse")) print_timing("greuse", r, run_greuse(c, s, GM, true));
        if (want("greuse_noupdate"))
            print_timing("greuse_noupdate", r, run_greuse(c, s, GM, false));
    }

    cudaGraphExecDestroy(G1.exec); cudaGraphDestroy(G1.g);
    cudaGraphExecDestroy(GM.exec); cudaGraphDestroy(GM.g);
    ctx_free(c); cudaStreamDestroy(s);
    return 0;
}
