#ifdef _METAL_ENABLED

#define UInt MacUInt
#define Boolean MacBoolean
#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#undef UInt
#undef Boolean

#include "src/acc/metal/metal_resample.h"
#include "src/error.h"
#include <iostream>
#include <iomanip>
#include <cmath>
#include <chrono>
#include <vector>

static const char *resample_metal_kernel_source = R"(
#include <metal_stdlib>
using namespace metal;

inline float lin_interp(float a, float l, float h) {
    return l + (h - l) * a;
}

kernel void realSpaceInterpolationKernel(
    device const float *d_Iframes [[buffer(0)]],
    device float *d_Iref [[buffer(1)]],
    constant float *coeffX [[buffer(2)]],
    constant float *coeffY [[buffer(3)]],
    constant int &nx [[buffer(4)]],
    constant int &ny [[buffer(5)]],
    constant int &n_frames [[buffer(6)]],
    constant int &has_weights [[buffer(7)]],
    device const float *d_frame_weights [[buffer(8)]],
    uint2 gid [[thread_position_in_grid]])
{
    int ix = gid.x;
    int iy = gid.y;
    if (ix >= nx || iy >= ny) {
        return;
    }

    float x = (float)ix / (float)nx - 0.5f;
    float y = (float)iy / (float)ny - 0.5f;

    float accum = 0.0f;
    size_t frame_stride = (size_t)nx * ny;

    for (int iframe = 0; iframe < n_frames; iframe++) {
        float x_src, y_src;

        if (iframe == 0) {
            // Deterministic origin anchoring: frame 0 shift is identically 0.0
            x_src = (float)ix;
            y_src = (float)iy;
        } else {
            float z = (float)iframe;
            float z2 = z * z;
            float z3 = z * z2;

            float x_C0 = coeffX[0]  * z + coeffX[1]  * z2 + coeffX[2]  * z3;
            float x_C1 = coeffX[3]  * z + coeffX[4]  * z2 + coeffX[5]  * z3;
            float x_C2 = coeffX[6]  * z + coeffX[7]  * z2 + coeffX[8]  * z3;
            float x_C3 = coeffX[9]  * z + coeffX[10] * z2 + coeffX[11] * z3;
            float x_C4 = coeffX[12] * z + coeffX[13] * z2 + coeffX[14] * z3;
            float x_C5 = coeffX[15] * z + coeffX[16] * z2 + coeffX[17] * z3;

            float y_C0 = coeffY[0]  * z + coeffY[1]  * z2 + coeffY[2]  * z3;
            float y_C1 = coeffY[3]  * z + coeffY[4]  * z2 + coeffY[5]  * z3;
            float y_C2 = coeffY[6]  * z + coeffY[7]  * z2 + coeffY[8]  * z3;
            float y_C3 = coeffY[9]  * z + coeffY[10] * z2 + coeffY[11] * z3;
            float y_C4 = coeffY[12] * z + coeffY[13] * z2 + coeffY[14] * z3;
            float y_C5 = coeffY[15] * z + coeffY[16] * z2 + coeffY[17] * z3;

            // Horner evaluation matching CPU polynomial trajectory
            float x_fitted = x_C0 + (x_C1 + x_C2 * x) * x + (x_C3 + x_C4 * y + x_C5 * x) * y;
            float y_fitted = y_C0 + (y_C1 + y_C2 * x) * x + (y_C3 + y_C4 * y + y_C5 * x) * y;

            x_src = (float)ix - x_fitted;
            y_src = (float)iy - y_fitted;
        }

        int x0 = (int)floor(x_src);
        int y0 = (int)floor(y_src);
        int x1 = x0 + 1;
        int y1 = y0 + 1;

        // Edge clamping identical to RELION CPU realSpaceInterpolation
        bool valid = true;
        if (x0 < 0 || x1 < 0) { x0 = 0; valid = false; }
        if (y0 < 0 || y1 < 0) { y0 = 0; valid = false; }
        if (x1 >= nx || x0 >= nx - 1) { x0 = nx - 1; valid = false; }
        if (y1 >= ny || y0 >= ny - 1) { y0 = ny - 1; valid = false; }

        device const float *frame_ptr = d_Iframes + (size_t)iframe * frame_stride;
        float val;
        if (!valid) {
            val = frame_ptr[y0 * nx + x0];
        } else {
            float fx = x_src - (float)x0;
            float fy = y_src - (float)y0;

            float d00 = frame_ptr[y0 * nx + x0];
            float d01 = frame_ptr[y0 * nx + x1];
            float d10 = frame_ptr[y1 * nx + x0];
            float d11 = frame_ptr[y1 * nx + x1];

            float dx0 = lin_interp(fx, d00, d01);
            float dx1 = lin_interp(fx, d10, d11);
            val = lin_interp(fy, dx0, dx1);
        }

        float weight = (has_weights != 0) ? d_frame_weights[iframe] : 1.0f;
        accum += val * weight;
    }

    d_Iref[iy * nx + ix] = accum;
}

kernel void doseWeightingKernel(
    device float2 *d_Fframes [[buffer(0)]],
    constant float *doses [[buffer(1)]],
    constant float &apix [[buffer(2)]],
    constant int &nfx [[buffer(3)]],
    constant int &nfy [[buffer(4)]],
    constant int &nfy_half [[buffer(5)]],
    constant int &n_frames [[buffer(6)]],
    uint2 gid [[thread_position_in_grid]])
{
    int x = gid.x;
    int y = gid.y;
    if (x >= nfx || y >= nfy) return;

    int ly = (y > nfy_half) ? (y - nfy) : y;
    float nfy2 = (float)nfy * (float)nfy;
    float nfx2 = (float)(nfx - 1) * (float)(nfx - 1) * 4.0f;

    float ly2 = (float)ly * (float)ly / nfy2;
    float dinv2 = ly2 + (float)x * (float)x / nfx2;

    const float A = 0.245f, B = -1.665f, C = 2.81f;
    size_t frame_stride = (size_t)nfy * nfx;

    if (dinv2 <= 0.0f) {
        float inv_norm = 1.0f / sqrt((float)n_frames);
        for (int iframe = 0; iframe < n_frames; iframe++) {
            size_t idx = (size_t)iframe * frame_stride + y * nfx + x;
            d_Fframes[idx] *= inv_norm;
        }
        return;
    }

    float dinv = sqrt(dinv2) / apix;
    float Ne = (A * pow(dinv, B) + C) * 2.0f;
    float sum_weight_sq = 0.0f;

    for (int iframe = 0; iframe < n_frames; iframe++) {
        float w = exp(- doses[iframe] / Ne);
        sum_weight_sq += w * w;
    }

    float inv_sum = 1.0f / sqrt(sum_weight_sq);
    for (int iframe = 0; iframe < n_frames; iframe++) {
        size_t idx = (size_t)iframe * frame_stride + y * nfx + x;
        float w = exp(- doses[iframe] / Ne);
        d_Fframes[idx] *= (w * inv_sum);
    }
}
)";

bool metalRealSpaceInterpolationRaw(
    const float *h_Iframes,
    float *h_Isum,
    const float *coeffX,
    const float *coeffY,
    const int nx, const int ny, const int n_frames,
    const int device_id,
    std::ostream &logfile,
    const float *frame_weights
) {
    @autoreleasepool {
        auto t_start = std::chrono::high_resolution_clock::now();

        if (nx <= 0 || ny <= 0 || n_frames <= 0) {
            REPORT_ERROR("Invalid dimensions for metalRealSpaceInterpolationRaw");
        }
        if (!h_Iframes || !h_Isum || !coeffX || !coeffY) {
            REPORT_ERROR("Null pointer passed to metalRealSpaceInterpolationRaw");
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
        id<MTLLibrary> library = [device newLibraryWithSource:[NSString stringWithUTF8String:resample_metal_kernel_source]
                                                      options:nil
                                                        error:&error];
        if (!library) {
            std::string errDesc = error ? [[error localizedDescription] UTF8String] : "Unknown library error";
            REPORT_ERROR("Metal execution failed: Resample kernel library compilation error: " + errDesc);
        }

        id<MTLFunction> fnResample = [library newFunctionWithName:@"realSpaceInterpolationKernel"];
        id<MTLComputePipelineState> psoResample = [device newComputePipelineStateWithFunction:fnResample error:&error];
        if (!psoResample) {
            std::string errDesc = error ? [[error localizedDescription] UTF8String] : "Unknown pipeline error";
            REPORT_ERROR("Metal execution failed: Resample pipeline creation error: " + errDesc);
        }

        const size_t frame_pixels = (size_t)nx * ny;
        const size_t total_frame_bytes = (size_t)n_frames * frame_pixels * sizeof(float);
        const size_t out_bytes = frame_pixels * sizeof(float);

        id<MTLBuffer> bufIframes = [device newBufferWithBytes:h_Iframes
                                                       length:total_frame_bytes
                                                      options:MTLResourceStorageModeShared];
        id<MTLBuffer> bufIref = [device newBufferWithLength:out_bytes
                                                    options:MTLResourceStorageModeShared];
        id<MTLBuffer> bufCoeffX = [device newBufferWithBytes:coeffX
                                                      length:18 * sizeof(float)
                                                     options:MTLResourceStorageModeShared];
        id<MTLBuffer> bufCoeffY = [device newBufferWithBytes:coeffY
                                                      length:18 * sizeof(float)
                                                     options:MTLResourceStorageModeShared];

        int has_weights = (frame_weights != nullptr) ? 1 : 0;
        id<MTLBuffer> bufWeights = nil;
        if (has_weights) {
            bufWeights = [device newBufferWithBytes:frame_weights
                                             length:n_frames * sizeof(float)
                                            options:MTLResourceStorageModeShared];
        } else {
            bufWeights = [device newBufferWithLength:sizeof(float)
                                             options:MTLResourceStorageModeShared];
        }

        if (!bufIframes || !bufIref || !bufCoeffX || !bufCoeffY || !bufWeights) {
            REPORT_ERROR("Metal execution failed: Buffer allocation failed on device " + device_name);
        }

        id<MTLCommandBuffer> cmdBuffer = [queue commandBuffer];
        id<MTLComputeCommandEncoder> encoder = [cmdBuffer computeCommandEncoder];
        [encoder setComputePipelineState:psoResample];

        [encoder setBuffer:bufIframes offset:0 atIndex:0];
        [encoder setBuffer:bufIref offset:0 atIndex:1];
        [encoder setBuffer:bufCoeffX offset:0 atIndex:2];
        [encoder setBuffer:bufCoeffY offset:0 atIndex:3];
        [encoder setBytes:&nx length:sizeof(int) atIndex:4];
        [encoder setBytes:&ny length:sizeof(int) atIndex:5];
        [encoder setBytes:&n_frames length:sizeof(int) atIndex:6];
        [encoder setBytes:&has_weights length:sizeof(int) atIndex:7];
        [encoder setBuffer:bufWeights offset:0 atIndex:8];

        MTLSize threadgroupSize = MTLSizeMake(16, 16, 1);
        MTLSize threadgroups = MTLSizeMake((nx + 15) / 16, (ny + 15) / 16, 1);
        [encoder dispatchThreadgroups:threadgroups threadsPerThreadgroup:threadgroupSize];
        [encoder endEncoding];

        [cmdBuffer commit];
        [cmdBuffer waitUntilCompleted];

        if ([cmdBuffer status] == MTLCommandBufferStatusError) {
            std::string errDesc = [cmdBuffer error] ? [[[cmdBuffer error] localizedDescription] UTF8String] : "Unknown command buffer error";
            REPORT_ERROR("Metal execution failed during realSpaceInterpolation execution: " + errDesc);
        }

        std::memcpy(h_Isum, [bufIref contents], out_bytes);

        auto t_end = std::chrono::high_resolution_clock::now();
        double elapsed_sec = std::chrono::duration<double>(t_end - t_start).count();

        logfile << "[Metal Real-Space Resampling Profile]" << std::endl;
        logfile << "Device: " << device_name << std::endl;
        logfile << "Frames: " << n_frames << " (" << nx << "x" << ny << ")" << std::endl;
        logfile << "Kernel Wall Time: " << std::fixed << std::setprecision(4) << elapsed_sec << " s" << std::endl;

        return true;
    }
}

bool metalRealSpaceInterpolation(
    Image<float> &Isum,
    const std::vector<Image<float> > &Iframes,
    const std::vector<float> &coeffX,
    const std::vector<float> &coeffY,
    const int device_id,
    std::ostream &logfile,
    const std::vector<float> &frame_weights
) {
    if (Iframes.empty()) {
        REPORT_ERROR("Iframes vector is empty in metalRealSpaceInterpolation");
    }
    if (coeffX.size() != 18 || coeffY.size() != 18) {
        REPORT_ERROR("Model coefficients must have exactly 18 elements per dimension");
    }

    const int n_frames = static_cast<int>(Iframes.size());
    const int nx = XSIZE(Iframes[0]());
    const int ny = YSIZE(Iframes[0]());

    Isum().initZeros(ny, nx);

    std::vector<float> h_Iframes((size_t)n_frames * nx * ny);
    const size_t frame_bytes = (size_t)nx * ny * sizeof(float);
    for (int iframe = 0; iframe < n_frames; iframe++) {
        std::memcpy(h_Iframes.data() + (size_t)iframe * nx * ny, Iframes[iframe]().data, frame_bytes);
    }

    const float *p_weights = frame_weights.empty() ? nullptr : frame_weights.data();
    return metalRealSpaceInterpolationRaw(
        h_Iframes.data(),
        Isum().data,
        coeffX.data(),
        coeffY.data(),
        nx, ny, n_frames,
        device_id,
        logfile,
        p_weights
    );
}

bool metalRealSpaceInterpolation(
    Image<float> &Isum,
    const std::vector<Image<float> > &Iframes,
    const ThirdOrderPolynomialModel &model,
    const int device_id,
    std::ostream &logfile,
    const std::vector<float> &frame_weights
) {
    std::vector<float> cx(18), cy(18);
    for (int i = 0; i < 18; i++) {
        cx[i] = static_cast<float>(model.coeffX(i));
        cy[i] = static_cast<float>(model.coeffY(i));
    }
    return metalRealSpaceInterpolation(Isum, Iframes, cx, cy, device_id, logfile, frame_weights);
}

bool metalDoseWeighting(
    std::vector<MultidimArray<fComplex> > &Fframes,
    const std::vector<float> &doses,
    const float apix,
    const int device_id,
    std::ostream &logfile
) {
    @autoreleasepool {
        auto t_start = std::chrono::high_resolution_clock::now();

        if (Fframes.empty()) {
            REPORT_ERROR("Fframes vector is empty in metalDoseWeighting");
        }
        const int n_frames = static_cast<int>(Fframes.size());
        if (static_cast<int>(doses.size()) < n_frames) {
            REPORT_ERROR("Doses size does not match frame count in metalDoseWeighting");
        }

        const int nfx = XSIZE(Fframes[0]);
        const int nfy = YSIZE(Fframes[0]);
        const int nfy_half = nfy / 2;

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
        id<MTLLibrary> library = [device newLibraryWithSource:[NSString stringWithUTF8String:resample_metal_kernel_source]
                                                      options:nil
                                                        error:&error];
        if (!library) {
            std::string errDesc = error ? [[error localizedDescription] UTF8String] : "Unknown library error";
            REPORT_ERROR("Metal execution failed: Dose weighting library compilation error: " + errDesc);
        }

        id<MTLFunction> fnDose = [library newFunctionWithName:@"doseWeightingKernel"];
        id<MTLComputePipelineState> psoDose = [device newComputePipelineStateWithFunction:fnDose error:&error];
        if (!psoDose) {
            std::string errDesc = error ? [[error localizedDescription] UTF8String] : "Unknown pipeline error";
            REPORT_ERROR("Metal execution failed: Dose weighting pipeline creation error: " + errDesc);
        }

        const size_t frame_elements = (size_t)nfy * nfx;
        const size_t total_bytes = (size_t)n_frames * frame_elements * sizeof(fComplex);

        id<MTLBuffer> bufFframes = [device newBufferWithLength:total_bytes options:MTLResourceStorageModeShared];
        for (int iframe = 0; iframe < n_frames; iframe++) {
            std::memcpy(
                static_cast<char*>([bufFframes contents]) + (size_t)iframe * frame_elements * sizeof(fComplex),
                Fframes[iframe].data,
                frame_elements * sizeof(fComplex)
            );
        }

        id<MTLBuffer> bufDoses = [device newBufferWithBytes:doses.data()
                                                     length:n_frames * sizeof(float)
                                                    options:MTLResourceStorageModeShared];

        id<MTLCommandBuffer> cmdBuffer = [queue commandBuffer];
        id<MTLComputeCommandEncoder> encoder = [cmdBuffer computeCommandEncoder];
        [encoder setComputePipelineState:psoDose];

        [encoder setBuffer:bufFframes offset:0 atIndex:0];
        [encoder setBuffer:bufDoses offset:0 atIndex:1];
        [encoder setBytes:&apix length:sizeof(float) atIndex:2];
        [encoder setBytes:&nfx length:sizeof(int) atIndex:3];
        [encoder setBytes:&nfy length:sizeof(int) atIndex:4];
        [encoder setBytes:&nfy_half length:sizeof(int) atIndex:5];
        [encoder setBytes:&n_frames length:sizeof(int) atIndex:6];

        MTLSize threadgroupSize = MTLSizeMake(16, 16, 1);
        MTLSize threadgroups = MTLSizeMake((nfx + 15) / 16, (nfy + 15) / 16, 1);
        [encoder dispatchThreadgroups:threadgroups threadsPerThreadgroup:threadgroupSize];
        [encoder endEncoding];

        [cmdBuffer commit];
        [cmdBuffer waitUntilCompleted];

        if ([cmdBuffer status] == MTLCommandBufferStatusError) {
            std::string errDesc = [cmdBuffer error] ? [[[cmdBuffer error] localizedDescription] UTF8String] : "Unknown command buffer error";
            REPORT_ERROR("Metal execution failed during doseWeighting execution: " + errDesc);
        }

        for (int iframe = 0; iframe < n_frames; iframe++) {
            std::memcpy(
                Fframes[iframe].data,
                static_cast<const char*>([bufFframes contents]) + (size_t)iframe * frame_elements * sizeof(fComplex),
                frame_elements * sizeof(fComplex)
            );
        }

        auto t_end = std::chrono::high_resolution_clock::now();
        double elapsed_sec = std::chrono::duration<double>(t_end - t_start).count();

        logfile << "[Metal Dose Weighting Profile]" << std::endl;
        logfile << "Device: " << device_name << std::endl;
        logfile << "Frames: " << n_frames << " (" << nfx << "x" << nfy << ")" << std::endl;
        logfile << "Kernel Wall Time: " << std::fixed << std::setprecision(4) << elapsed_sec << " s" << std::endl;

        return true;
    }
}

#endif // _METAL_ENABLED
