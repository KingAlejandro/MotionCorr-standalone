#ifdef _METAL_ENABLED

#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#import <MetalPerformanceShaders/MetalPerformanceShaders.h>
#import <MetalPerformanceShadersGraph/MetalPerformanceShadersGraph.h>

#include "src/acc/metal/metal_alignpatch.h"
#include "src/error.h"
#include <iostream>
#include <iomanip>
#include <cmath>
#include <chrono>
#include <vector>

static const char *metal_kernel_source = R"(
#include <metal_stdlib>
using namespace metal;

kernel void computeWeightsKernel(
    device float *d_weight [[buffer(0)]],
    constant int &ccf_nfx [[buffer(1)]],
    constant int &ccf_nfy [[buffer(2)]],
    constant int &ccf_nfy_half [[buffer(3)]],
    constant int &nfx [[buffer(4)]],
    constant int &nfy [[buffer(5)]],
    constant float &scaled_B [[buffer(6)]],
    uint2 gid [[thread_position_in_grid]])
{
    int x = gid.x;
    int y = gid.y;
    if (x < ccf_nfx && y < ccf_nfy) {
        int ly = (y > ccf_nfy_half) ? (y - ccf_nfy) : y;
        float ly2 = (float)ly * (float)ly / ((float)nfy * (float)nfy);
        float dist2 = ly2 + (float)x * (float)x / ((float)nfx * (float)nfx);
        d_weight[y * ccf_nfx + x] = exp(-2.0f * dist2 * scaled_B);
    }
}

kernel void computeReferenceKernel(
    device const float2 *d_Fframes [[buffer(0)]],
    device float2 *d_Fref [[buffer(1)]],
    constant int &ccf_nfx [[buffer(2)]],
    constant int &ccf_nfy [[buffer(3)]],
    constant int &ccf_nfy_half [[buffer(4)]],
    constant int &nfx [[buffer(5)]],
    constant int &nfy [[buffer(6)]],
    constant int &n_frames [[buffer(7)]],
    uint2 gid [[thread_position_in_grid]])
{
    int x = gid.x;
    int y = gid.y;
    if (x < ccf_nfx && y < ccf_nfy) {
        int ly = (y > ccf_nfy_half) ? (y - ccf_nfy + nfy) : y;
        float sum_r = 0.0f;
        float sum_i = 0.0f;
        size_t frame_stride = (size_t)nfy * nfx;
        for (int iframe = 0; iframe < n_frames; iframe++) {
            float2 val = d_Fframes[iframe * frame_stride + ly * nfx + x];
            sum_r += val.x;
            sum_i += val.y;
        }
        d_Fref[y * ccf_nfx + x] = float2(sum_r, sum_i);
    }
}

kernel void computeCCFKernel(
    device const float2 *d_Fframes [[buffer(0)]],
    device const float2 *d_Fref [[buffer(1)]],
    device const float *d_weight [[buffer(2)]],
    device float2 *d_Fccs [[buffer(3)]],
    constant int &ccf_nfx [[buffer(4)]],
    constant int &ccf_nfy [[buffer(5)]],
    constant int &ccf_nfy_half [[buffer(6)]],
    constant int &nfx [[buffer(7)]],
    constant int &nfy [[buffer(8)]],
    constant int &n_frames [[buffer(9)]],
    uint3 gid [[thread_position_in_grid]])
{
    int x = gid.x;
    int y = gid.y;
    int iframe = gid.z;
    if (x < ccf_nfx && y < ccf_nfy && iframe < n_frames) {
        int ly = (y > ccf_nfy_half) ? (y - ccf_nfy + nfy) : y;
        float2 fref = d_Fref[y * ccf_nfx + x];
        float2 fframe = d_Fframes[iframe * ((size_t)nfy * nfx) + ly * nfx + x];
        float w = d_weight[y * ccf_nfx + x];

        float dr = fref.x - fframe.x;
        float di = fref.y - fframe.y;

        float ccf_r = (dr * fframe.x + di * fframe.y) * w;
        float ccf_i = (di * fframe.x - dr * fframe.y) * w;

        d_Fccs[iframe * ((size_t)ccf_nfy * ccf_nfx) + y * ccf_nfx + x] = float2(ccf_r, ccf_i);
    }
}

kernel void findPeakAndInterpolateKernel(
    device const float *d_Iccs [[buffer(0)]],
    device float *d_cur_xshifts [[buffer(1)]],
    device float *d_cur_yshifts [[buffer(2)]],
    constant int &ccf_nx [[buffer(3)]],
    constant int &ccf_ny [[buffer(4)]],
    constant int &search_range [[buffer(5)]],
    constant float &ccf_scale_x [[buffer(6)]],
    constant float &ccf_scale_y [[buffer(7)]],
    constant int &n_frames [[buffer(8)]],
    uint tid [[thread_position_in_threadgroup]],
    uint iframe [[threadgroup_position_in_grid]],
    threadgroup float *s_max [[threadgroup(0)]],
    threadgroup int *s_posx [[threadgroup(1)]],
    threadgroup int *s_posy [[threadgroup(2)]])
{
    if (iframe >= (uint)n_frames) return;

    size_t frame_offset = (size_t)iframe * ccf_ny * ccf_nx;
    int range_len = 2 * search_range + 1;
    int total_pts = range_len * range_len;

    float local_max = -1e30f;
    int local_posx = 0;
    int local_posy = 0;

    for (int idx = tid; idx < total_pts; idx += 256) {
        int sy = idx / range_len - search_range;
        int sx = idx % range_len - search_range;
        int iy = (sy < 0) ? ccf_ny + sy : sy;
        int ix = (sx < 0) ? ccf_nx + sx : sx;
        float val = d_Iccs[frame_offset + iy * ccf_nx + ix];
        if (val > local_max) {
            local_max = val;
            local_posx = sx;
            local_posy = sy;
        }
    }

    s_max[tid] = local_max;
    s_posx[tid] = local_posx;
    s_posy[tid] = local_posy;
    threadgroup_barrier(mem_flags::mem_threadgroup);

    for (uint stride = 128; stride > 0; stride >>= 1) {
        if (tid < stride) {
            if (s_max[tid + stride] > s_max[tid]) {
                s_max[tid] = s_max[tid + stride];
                s_posx[tid] = s_posx[tid + stride];
                s_posy[tid] = s_posy[tid + stride];
            }
        }
        threadgroup_barrier(mem_flags::mem_threadgroup);
    }

    if (tid == 0) {
        float maxval = s_max[0];
        int posx = s_posx[0];
        int posy = s_posy[0];

        int ipx_n = posx - 1; if (ipx_n < 0) ipx_n = ccf_nx + ipx_n;
        int ipx   = posx;     if (ipx < 0)   ipx   = ccf_nx + ipx;
        int ipx_p = posx + 1; if (ipx_p < 0) ipx_p = ccf_nx + ipx_p;
        int ipy_n = posy - 1; if (ipy_n < 0) ipy_n = ccf_ny + ipy_n;
        int ipy   = posy;     if (ipy < 0)   ipy   = ccf_ny + ipy;
        int ipy_p = posy + 1; if (ipy_p < 0) ipy_p = ccf_ny + ipy_p;

        const float EPS = 1e-15f;
        float vp_x = d_Iccs[frame_offset + ipy * ccf_nx + ipx_p];
        float vn_x = d_Iccs[frame_offset + ipy * ccf_nx + ipx_n];
        float denom_x = vp_x + vn_x - 2.0f * maxval;
        float cur_x = (abs(denom_x) > EPS) ? (posx - 0.5f * (vp_x - vn_x) / denom_x) : posx;

        float vp_y = d_Iccs[frame_offset + ipy_p * ccf_nx + ipx];
        float vn_y = d_Iccs[frame_offset + ipy_n * ccf_nx + ipx];
        float denom_y = vp_y + vn_y - 2.0f * maxval;
        float cur_y = (abs(denom_y) > EPS) ? (posy - 0.5f * (vp_y - vn_y) / denom_y) : posy;

        d_cur_xshifts[iframe] = cur_x * ccf_scale_x;
        d_cur_yshifts[iframe] = cur_y * ccf_scale_y;
    }
}

kernel void fourierShiftKernel(
    device float2 *d_Fframes [[buffer(0)]],
    device const float *d_shiftx [[buffer(1)]],
    device const float *d_shifty [[buffer(2)]],
    constant int &nfx [[buffer(3)]],
    constant int &nfy [[buffer(4)]],
    constant int &nfy_half [[buffer(5)]],
    constant int &n_frames [[buffer(6)]],
    uint3 gid [[thread_position_in_grid]])
{
    int x = gid.x;
    int y = gid.y;
    int iframe = gid.z + 1; // frames 1 .. n_frames - 1

    if (x < nfx && y < nfy && iframe < n_frames) {
        int ly = (y > nfy_half) ? (y - nfy) : y;
        float sx = d_shiftx[iframe];
        float sy = d_shifty[iframe];
        float phase = 2.0f * M_PI_F * (x * sx + ly * sy);
        float cos_p;
        float sin_p = sincos(phase, cos_p);

        size_t idx = iframe * ((size_t)nfy * nfx) + y * nfx + x;
        float2 val = d_Fframes[idx];
        d_Fframes[idx] = float2(
            cos_p * val.x - sin_p * val.y,
            sin_p * val.x + cos_p * val.y
        );
    }
}
)";

static int findGoodSizeMetal(int request) {
    const int good_numbers[] = {192, 216, 256, 288, 324,
                                384, 432, 486, 512, 576, 648,
                                768, 800, 864, 972, 1024,
                                1296, 1536, 1728, 1944,
                                2048, 2304, 2592, 3072, 3200,
                                3456, 3888, 4096, 4608, 5000, 5184,
                                6144, 6250, 6400, 6912, 7776, 8192,
                                9216, 10240, 12288, 12500, -1};
    for (int i = 0; good_numbers[i] != -1; i++) {
        if (good_numbers[i] < request) continue;
        else return good_numbers[i];
    }
    return request;
}

int metalGetDeviceCount() {
    @autoreleasepool {
        NSArray<id<MTLDevice>> *devices = MTLCopyAllDevices();
        if (!devices) {
            return 0;
        }
        return static_cast<int>([devices count]);
    }
}

std::string metalGetDeviceName(int device_id) {
    @autoreleasepool {
        NSArray<id<MTLDevice>> *devices = MTLCopyAllDevices();
        if (!devices || device_id < 0 || device_id >= static_cast<int>([devices count])) {
            REPORT_ERROR("Invalid Metal device ID " + integerToString(device_id));
        }
        id<MTLDevice> device = devices[device_id];
        return std::string([[device name] UTF8String]);
    }
}

bool metalAlignPatch(
    std::vector<MultidimArray<fComplex> > &Fframes,
    const int pnx, const int pny,
    const RFLOAT scaled_B,
    std::vector<RFLOAT> &xshifts,
    std::vector<RFLOAT> &yshifts,
    const int max_iter,
    const RFLOAT ccf_downsample,
    const int device_id,
    std::ostream &logfile
) {
    @autoreleasepool {
        auto t_total_start = std::chrono::high_resolution_clock::now();

        if (pny % 2 == 1 || pnx % 2 == 1) {
            REPORT_ERROR("Patch size must be even");
        }
        if (Fframes.empty()) {
            REPORT_ERROR("Metal execution failed: Empty frame vector provided to metalAlignPatch");
        }

        const int n_frames = static_cast<int>(xshifts.size());
        if (n_frames <= 0) {
            REPORT_ERROR("Metal execution failed: Trajectory size is zero");
        }

        NSArray<id<MTLDevice>> *devices = MTLCopyAllDevices();
        if (!devices || device_id < 0 || device_id >= static_cast<int>([devices count])) {
            REPORT_ERROR("Metal execution failed: Invalid Metal device ID " + integerToString(device_id));
        }
        id<MTLDevice> device = devices[device_id];
        std::string device_name = [[device name] UTF8String];

        id<MTLCommandQueue> queue = [device newCommandQueue];
        if (!queue) {
            REPORT_ERROR("Metal execution failed: Could not create MTLCommandQueue on device " + device_name);
        }

        NSError *error = nil;
        id<MTLLibrary> library = [device newLibraryWithSource:[NSString stringWithUTF8String:metal_kernel_source]
                                                      options:nil
                                                        error:&error];
        if (!library) {
            std::string errDesc = error ? [[error localizedDescription] UTF8String] : "Unknown library error";
            REPORT_ERROR("Metal execution failed: Kernel library compilation error: " + errDesc);
        }

        id<MTLFunction> fnWeight = [library newFunctionWithName:@"computeWeightsKernel"];
        id<MTLFunction> fnRef = [library newFunctionWithName:@"computeReferenceKernel"];
        id<MTLFunction> fnCCF = [library newFunctionWithName:@"computeCCFKernel"];
        id<MTLFunction> fnPeak = [library newFunctionWithName:@"findPeakAndInterpolateKernel"];
        id<MTLFunction> fnShift = [library newFunctionWithName:@"fourierShiftKernel"];

        id<MTLComputePipelineState> psoWeight = [device newComputePipelineStateWithFunction:fnWeight error:&error];
        id<MTLComputePipelineState> psoRef = [device newComputePipelineStateWithFunction:fnRef error:&error];
        id<MTLComputePipelineState> psoCCF = [device newComputePipelineStateWithFunction:fnCCF error:&error];
        id<MTLComputePipelineState> psoPeak = [device newComputePipelineStateWithFunction:fnPeak error:&error];
        id<MTLComputePipelineState> psoShift = [device newComputePipelineStateWithFunction:fnShift error:&error];

        if (!psoWeight || !psoRef || !psoCCF || !psoPeak || !psoShift) {
            std::string errDesc = error ? [[error localizedDescription] UTF8String] : "Unknown pipeline error";
            REPORT_ERROR("Metal execution failed: Compute pipeline creation error: " + errDesc);
        }

        const int nfx = XSIZE(Fframes[0]);
        const int nfy = YSIZE(Fframes[0]);
        const int nfy_half = nfy / 2;

        float ccf_requested_scale = (float)ccf_downsample;
        if (ccf_downsample <= 0) {
            ccf_requested_scale = std::sqrt(-std::log(1e-8f) / (2.0f * (float)scaled_B));
        }

        int ccf_nx = findGoodSizeMetal(int(pnx * ccf_requested_scale));
        int ccf_ny = findGoodSizeMetal(int(pny * ccf_requested_scale));
        if (ccf_nx > pnx) ccf_nx = pnx;
        if (ccf_ny > pny) ccf_ny = pny;
        if (ccf_nx % 2 == 1) ccf_nx++;
        if (ccf_ny % 2 == 1) ccf_ny++;

        const int ccf_nfx = ccf_nx / 2 + 1;
        const int ccf_nfy = ccf_ny;
        const int ccf_nfy_half = ccf_ny / 2;
        const float ccf_scale_x = (float)pnx / (float)ccf_nx;
        const float ccf_scale_y = (float)pny / (float)ccf_ny;

        int search_range = 50;
        search_range /= (ccf_scale_x > ccf_scale_y) ? ccf_scale_x : ccf_scale_y;
        if (search_range * 2 + 1 > ccf_nx) search_range = ccf_nx / 2 - 1;
        if (search_range * 2 + 1 > ccf_ny) search_range = ccf_ny / 2 - 1;

        // Construct MPSGraph 2D C2R IFFT
        MPSGraph *graph = [[MPSGraph alloc] init];
        MPSGraphTensor *inTensor = [graph placeholderWithShape:@[@(n_frames), @(ccf_nfy), @(ccf_nfx)]
                                                      dataType:MPSDataTypeComplexFloat32
                                                          name:@"in"];
        MPSGraphFFTDescriptor *desc = [MPSGraphFFTDescriptor descriptor];
        desc.inverse = YES;
        desc.scalingMode = MPSGraphFFTScalingModeNone;
        desc.roundToOddHermitean = NO;

        MPSGraphTensor *outTensor = [graph HermiteanToRealFFTWithTensor:inTensor
                                                                  axes:@[@1, @2]
                                                            descriptor:desc
                                                                  name:@"ifft"];

        // Memory allocation
        const size_t bytes_frames = (size_t)n_frames * nfy * nfx * sizeof(float) * 2;
        const size_t bytes_ref = (size_t)ccf_nfy * ccf_nfx * sizeof(float) * 2;
        const size_t bytes_weight = (size_t)ccf_nfy * ccf_nfx * sizeof(float);
        const size_t bytes_Fccs = (size_t)n_frames * ccf_nfy * ccf_nfx * sizeof(float) * 2;
        const size_t bytes_Iccs = (size_t)n_frames * ccf_ny * ccf_nx * sizeof(float);
        const size_t bytes_shifts = (size_t)n_frames * sizeof(float);

        const size_t peak_memory_bytes = bytes_frames + bytes_ref + bytes_weight + bytes_Fccs + bytes_Iccs + 4 * bytes_shifts;

        id<MTLBuffer> d_Fframes = [device newBufferWithLength:bytes_frames options:MTLResourceStorageModeShared];
        id<MTLBuffer> d_Fref = [device newBufferWithLength:bytes_ref options:MTLResourceStorageModeShared];
        id<MTLBuffer> d_weight = [device newBufferWithLength:bytes_weight options:MTLResourceStorageModeShared];
        id<MTLBuffer> d_Fccs = [device newBufferWithLength:bytes_Fccs options:MTLResourceStorageModeShared];
        id<MTLBuffer> d_Iccs = [device newBufferWithLength:bytes_Iccs options:MTLResourceStorageModeShared];
        id<MTLBuffer> d_cur_xshifts = [device newBufferWithLength:bytes_shifts options:MTLResourceStorageModeShared];
        id<MTLBuffer> d_cur_yshifts = [device newBufferWithLength:bytes_shifts options:MTLResourceStorageModeShared];
        id<MTLBuffer> d_shiftx = [device newBufferWithLength:bytes_shifts options:MTLResourceStorageModeShared];
        id<MTLBuffer> d_shifty = [device newBufferWithLength:bytes_shifts options:MTLResourceStorageModeShared];

        if (!d_Fframes || !d_Fref || !d_weight || !d_Fccs || !d_Iccs ||
            !d_cur_xshifts || !d_cur_yshifts || !d_shiftx || !d_shifty) {
            REPORT_ERROR("Metal execution failed: Out of memory allocating buffers (" +
                         integerToString((long long)(peak_memory_bytes / 1024 / 1024)) + " MiB requested)");
        }

        // Host-to-Device transfer
        auto t_h2d_0 = std::chrono::high_resolution_clock::now();
        char *d_frames_ptr = (char*)[d_Fframes contents];
        const size_t frame_bytes = (size_t)nfy * nfx * sizeof(float) * 2;
        for (int iframe = 0; iframe < n_frames; iframe++) {
            memcpy(d_frames_ptr + (size_t)iframe * frame_bytes, Fframes[iframe].data, frame_bytes);
        }
        auto t_h2d_1 = std::chrono::high_resolution_clock::now();
        float h2d_ms = std::chrono::duration<float, std::milli>(t_h2d_1 - t_h2d_0).count();

        // Stage 1a: Weight computation
        auto t_k_start = std::chrono::high_resolution_clock::now();
        float scaled_B_f = (float)scaled_B;
        {
            id<MTLCommandBuffer> cb = [queue commandBuffer];
            id<MTLComputeCommandEncoder> enc = [cb computeCommandEncoder];
            [enc setComputePipelineState:psoWeight];
            [enc setBuffer:d_weight offset:0 atIndex:0];
            [enc setBytes:&ccf_nfx length:sizeof(int) atIndex:1];
            [enc setBytes:&ccf_nfy length:sizeof(int) atIndex:2];
            [enc setBytes:&ccf_nfy_half length:sizeof(int) atIndex:3];
            [enc setBytes:&nfx length:sizeof(int) atIndex:4];
            [enc setBytes:&nfy length:sizeof(int) atIndex:5];
            [enc setBytes:&scaled_B_f length:sizeof(float) atIndex:6];
            MTLSize tg = MTLSizeMake(16, 16, 1);
            MTLSize grid = MTLSizeMake((ccf_nfx + 15) / 16 * 16, (ccf_nfy + 15) / 16 * 16, 1);
            [enc dispatchThreads:grid threadsPerThreadgroup:tg];
            [enc endEncoding];
            [cb commit];
            [cb waitUntilCompleted];
        }
        auto t_k_end = std::chrono::high_resolution_clock::now();
        float accumulated_kernel_ms = std::chrono::duration<float, std::milli>(t_k_end - t_k_start).count();

        std::vector<float> h_cur_xshifts(n_frames, 0.0f);
        std::vector<float> h_cur_yshifts(n_frames, 0.0f);
        std::vector<float> h_shiftx(n_frames, 0.0f);
        std::vector<float> h_shifty(n_frames, 0.0f);

        bool converged = false;
        float accumulated_ifft_ms = 0.0f;
        float accumulated_d2h_ms = 0.0f;
        const float tolerance = 0.5f;

        for (int iter = 1; iter <= max_iter; iter++) {
            // Stage 1b: Reference computation
            auto t_k0 = std::chrono::high_resolution_clock::now();
            {
                id<MTLCommandBuffer> cb = [queue commandBuffer];
                id<MTLComputeCommandEncoder> enc = [cb computeCommandEncoder];
                [enc setComputePipelineState:psoRef];
                [enc setBuffer:d_Fframes offset:0 atIndex:0];
                [enc setBuffer:d_Fref offset:0 atIndex:1];
                [enc setBytes:&ccf_nfx length:sizeof(int) atIndex:2];
                [enc setBytes:&ccf_nfy length:sizeof(int) atIndex:3];
                [enc setBytes:&ccf_nfy_half length:sizeof(int) atIndex:4];
                [enc setBytes:&nfx length:sizeof(int) atIndex:5];
                [enc setBytes:&nfy length:sizeof(int) atIndex:6];
                [enc setBytes:&n_frames length:sizeof(int) atIndex:7];
                MTLSize tg = MTLSizeMake(16, 16, 1);
                MTLSize grid = MTLSizeMake((ccf_nfx + 15) / 16 * 16, (ccf_nfy + 15) / 16 * 16, 1);
                [enc dispatchThreads:grid threadsPerThreadgroup:tg];
                [enc endEncoding];
                [cb commit];
                [cb waitUntilCompleted];
            }

            // Stage 1c: CCF computation
            {
                id<MTLCommandBuffer> cb = [queue commandBuffer];
                id<MTLComputeCommandEncoder> enc = [cb computeCommandEncoder];
                [enc setComputePipelineState:psoCCF];
                [enc setBuffer:d_Fframes offset:0 atIndex:0];
                [enc setBuffer:d_Fref offset:0 atIndex:1];
                [enc setBuffer:d_weight offset:0 atIndex:2];
                [enc setBuffer:d_Fccs offset:0 atIndex:3];
                [enc setBytes:&ccf_nfx length:sizeof(int) atIndex:4];
                [enc setBytes:&ccf_nfy length:sizeof(int) atIndex:5];
                [enc setBytes:&ccf_nfy_half length:sizeof(int) atIndex:6];
                [enc setBytes:&nfx length:sizeof(int) atIndex:7];
                [enc setBytes:&nfy length:sizeof(int) atIndex:8];
                [enc setBytes:&n_frames length:sizeof(int) atIndex:9];
                MTLSize tg = MTLSizeMake(16, 16, 1);
                MTLSize grid = MTLSizeMake((ccf_nfx + 15) / 16 * 16, (ccf_nfy + 15) / 16 * 16, n_frames);
                [enc dispatchThreads:grid threadsPerThreadgroup:tg];
                [enc endEncoding];
                [cb commit];
                [cb waitUntilCompleted];
            }
            auto t_k1 = std::chrono::high_resolution_clock::now();
            accumulated_kernel_ms += std::chrono::duration<float, std::milli>(t_k1 - t_k0).count();

            // Stage 2: MPSGraph C2R IFFT
            auto t_i0 = std::chrono::high_resolution_clock::now();
            {
                MPSGraphTensorData *inData = [[MPSGraphTensorData alloc] initWithMTLBuffer:d_Fccs
                                                                                     shape:@[@(n_frames), @(ccf_nfy), @(ccf_nfx)]
                                                                                  dataType:MPSDataTypeComplexFloat32];
                NSDictionary *feeds = @{ inTensor: inData };
                NSDictionary *results = [graph runWithMTLCommandQueue:queue
                                                                feeds:feeds
                                                        targetTensors:@[outTensor]
                                                     targetOperations:nil];
                MPSGraphTensorData *outData = results[outTensor];
                MPSNDArray *arr = [outData mpsndarray];
                id<MTLCommandBuffer> cb = [queue commandBuffer];
                [arr exportDataWithCommandBuffer:cb
                                        toBuffer:d_Iccs
                             destinationDataType:MPSDataTypeFloat32
                                          offset:0
                                      rowStrides:nil];
                [cb commit];
                [cb waitUntilCompleted];
            }
            auto t_i1 = std::chrono::high_resolution_clock::now();
            accumulated_ifft_ms += std::chrono::duration<float, std::milli>(t_i1 - t_i0).count();

            // Stage 3: Peak finding + Jasenko subpixel interpolation
            auto t_pk0 = std::chrono::high_resolution_clock::now();
            {
                id<MTLCommandBuffer> cb = [queue commandBuffer];
                id<MTLComputeCommandEncoder> enc = [cb computeCommandEncoder];
                [enc setComputePipelineState:psoPeak];
                [enc setBuffer:d_Iccs offset:0 atIndex:0];
                [enc setBuffer:d_cur_xshifts offset:0 atIndex:1];
                [enc setBuffer:d_cur_yshifts offset:0 atIndex:2];
                [enc setBytes:&ccf_nx length:sizeof(int) atIndex:3];
                [enc setBytes:&ccf_ny length:sizeof(int) atIndex:4];
                [enc setBytes:&search_range length:sizeof(int) atIndex:5];
                [enc setBytes:&ccf_scale_x length:sizeof(float) atIndex:6];
                [enc setBytes:&ccf_scale_y length:sizeof(float) atIndex:7];
                [enc setBytes:&n_frames length:sizeof(int) atIndex:8];
                [enc setThreadgroupMemoryLength:256 * sizeof(float) atIndex:0];
                [enc setThreadgroupMemoryLength:256 * sizeof(int) atIndex:1];
                [enc setThreadgroupMemoryLength:256 * sizeof(int) atIndex:2];
                MTLSize tg = MTLSizeMake(256, 1, 1);
                MTLSize grid = MTLSizeMake(256 * n_frames, 1, 1);
                [enc dispatchThreads:grid threadsPerThreadgroup:tg];
                [enc endEncoding];
                [cb commit];
                [cb waitUntilCompleted];
            }
            auto t_pk1 = std::chrono::high_resolution_clock::now();
            accumulated_kernel_ms += std::chrono::duration<float, std::milli>(t_pk1 - t_pk0).count();

            // Read back shifts
            auto t_d2h_0 = std::chrono::high_resolution_clock::now();
            float *cur_x_ptr = (float*)[d_cur_xshifts contents];
            float *cur_y_ptr = (float*)[d_cur_yshifts contents];
            for (int iframe = 0; iframe < n_frames; iframe++) {
                h_cur_xshifts[iframe] = cur_x_ptr[iframe];
                h_cur_yshifts[iframe] = cur_y_ptr[iframe];
            }
            auto t_d2h_1 = std::chrono::high_resolution_clock::now();
            accumulated_d2h_ms += std::chrono::duration<float, std::milli>(t_d2h_1 - t_d2h_0).count();

            // Origin anchoring (frame 0)
            RFLOAT x_sumsq = 0.0, y_sumsq = 0.0;
            for (int iframe = n_frames - 1; iframe >= 0; iframe--) {
                h_cur_xshifts[iframe] -= h_cur_xshifts[0];
                h_cur_yshifts[iframe] -= h_cur_yshifts[0];
                x_sumsq += (RFLOAT)h_cur_xshifts[iframe] * h_cur_xshifts[iframe];
                y_sumsq += (RFLOAT)h_cur_yshifts[iframe] * h_cur_yshifts[iframe];
            }
            h_cur_xshifts[0] = 0.0f;
            h_cur_yshifts[0] = 0.0f;

            for (int iframe = 0; iframe < n_frames; iframe++) {
                xshifts[iframe] += h_cur_xshifts[iframe];
                yshifts[iframe] += h_cur_yshifts[iframe];
                h_shiftx[iframe] = -h_cur_xshifts[iframe] / (float)pnx;
                h_shifty[iframe] = -h_cur_yshifts[iframe] / (float)pny;
            }

            // Stage 4: Apply Fourier phase shifts on GPU
            if (n_frames > 1) {
                float *sx_ptr = (float*)[d_shiftx contents];
                float *sy_ptr = (float*)[d_shifty contents];
                for (int iframe = 0; iframe < n_frames; iframe++) {
                    sx_ptr[iframe] = h_shiftx[iframe];
                    sy_ptr[iframe] = h_shifty[iframe];
                }
                auto t_sh0 = std::chrono::high_resolution_clock::now();
                {
                    id<MTLCommandBuffer> cb = [queue commandBuffer];
                    id<MTLComputeCommandEncoder> enc = [cb computeCommandEncoder];
                    [enc setComputePipelineState:psoShift];
                    [enc setBuffer:d_Fframes offset:0 atIndex:0];
                    [enc setBuffer:d_shiftx offset:0 atIndex:1];
                    [enc setBuffer:d_shifty offset:0 atIndex:2];
                    [enc setBytes:&nfx length:sizeof(int) atIndex:3];
                    [enc setBytes:&nfy length:sizeof(int) atIndex:4];
                    [enc setBytes:&nfy_half length:sizeof(int) atIndex:5];
                    [enc setBytes:&n_frames length:sizeof(int) atIndex:6];
                    MTLSize tg = MTLSizeMake(16, 16, 1);
                    MTLSize grid = MTLSizeMake((nfx + 15) / 16 * 16, (nfy + 15) / 16 * 16, n_frames - 1);
                    [enc dispatchThreads:grid threadsPerThreadgroup:tg];
                    [enc endEncoding];
                    [cb commit];
                    [cb waitUntilCompleted];
                }
                auto t_sh1 = std::chrono::high_resolution_clock::now();
                accumulated_kernel_ms += std::chrono::duration<float, std::milli>(t_sh1 - t_sh0).count();
            }

            // Convergence check
            RFLOAT rmsd = std::sqrt((x_sumsq + y_sumsq) / n_frames);
            logfile << " Iteration " << iter << ": RMSD = " << rmsd << " px" << std::endl;

            if (rmsd < tolerance) {
                converged = true;
                break;
            }
        }

        // Final transfer: copy shifted Fframes back to host
        auto t_final_0 = std::chrono::high_resolution_clock::now();
        for (int iframe = 0; iframe < n_frames; iframe++) {
            memcpy(Fframes[iframe].data, d_frames_ptr + (size_t)iframe * frame_bytes, frame_bytes);
        }
        auto t_final_1 = std::chrono::high_resolution_clock::now();
        accumulated_d2h_ms += std::chrono::duration<float, std::milli>(t_final_1 - t_final_0).count();

        auto t_total_end = std::chrono::high_resolution_clock::now();
        float total_ms = std::chrono::duration<float, std::milli>(t_total_end - t_total_start).count();

        // Emit profile markers adhering to regression test contract
        logfile << " [Metal Global Alignment Profile]" << std::endl;
        logfile << "   Host-to-Device transfer time: " << std::fixed << std::setprecision(2) << h2d_ms << " ms" << std::endl;
        logfile << "   Custom kernel execution time: " << std::fixed << std::setprecision(2) << accumulated_kernel_ms << " ms" << std::endl;
        logfile << "   MPSGraph FFT execution time:  " << std::fixed << std::setprecision(2) << accumulated_ifft_ms << " ms" << std::endl;
        logfile << "   Device-to-Host transfer time: " << std::fixed << std::setprecision(2) << accumulated_d2h_ms << " ms" << std::endl;
        logfile << "   Total Metal alignment time:   " << std::fixed << std::setprecision(2) << total_ms << " ms" << std::endl;
        logfile << "   Peak GPU memory allocated:    " << std::fixed << std::setprecision(2) << (peak_memory_bytes / (1024.0 * 1024.0)) << " MiB" << std::endl;

        return converged;
    }
}

#endif // _METAL_ENABLED
