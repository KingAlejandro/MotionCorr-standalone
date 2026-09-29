/* Microbenchmark for GPU Deflate TIFF Ingestion vs CPU libtiff on NVIDIA A100.
 *
 * Compares:
 * 1. CPU Baseline: libtiff OpenMP decoded strips (TIFFReadEncodedStrip) + PCIe H2D upload (float32).
 * 2. GPU nvCOMP Direct Path: Read raw compressed strips (TIFFReadRawStrip), upload compressed bytes,
 *    batched GPU Deflate decompress (nvcompBatchedDeflateDecompressAsync), cast to float32.
 * 3. Bit-for-bit validation across all pixels.
 */

#include <iostream>
#include <vector>
#include <chrono>
#include <iomanip>
#include <cstring>
#include <cmath>
#include <omp.h>
#include <cuda_runtime.h>
#include <tiffio.h>
#include "nvcomp.h"
#include "nvcomp/deflate.h"

#define CUDA_CHECK(call) do { \
    cudaError_t err = (call); \
    if (err != cudaSuccess) { \
        std::cerr << "CUDA Error: " << cudaGetErrorString(err) \
                  << " at " << __FILE__ << ":" << __LINE__ << std::endl; \
        exit(1); \
    } \
} while (0)

#define NVCOMP_CHECK(call) do { \
    nvcompStatus_t status = (call); \
    if (status != nvcompSuccess) { \
        std::cerr << "nvCOMP Error code " << status \
                  << " at " << __FILE__ << ":" << __LINE__ << std::endl; \
        exit(1); \
    } \
} while (0)

__global__ void u16_to_float_kernel(const uint16_t *src, float *dst, size_t n_elements) {
    size_t idx = blockDim.x * (size_t)blockIdx.x + threadIdx.x;
    if (idx < n_elements) {
        dst[idx] = (float)src[idx];
    }
}

struct StripMeta {
    size_t compressed_offset;   // offset in combined raw buffer
    size_t raw_deflate_offset;  // offset + 2 (skipping zlib header)
    size_t compressed_size;     // total raw strip size
    size_t raw_deflate_size;    // compressed_size - 6
    size_t uncompressed_offset; // offset in uint16 output buffer
    size_t uncompressed_bytes;  // uncompressed bytes (width * 2)
};

int main(int argc, char **argv) {
    const char *tiff_path = (argc > 1) ? argv[1] :
        "/home/vol05/scarf1415/i53-scarf/relion30_tutorial/Movies/20170629_00021_frameImage.tiff";
    int num_threads = (argc > 2) ? std::atoi(argv[2]) : 8;

    std::cout << "===============================================================" << std::endl;
    std::cout << "  TIFF DEFLATE MICROBENCHMARK: CPU vs GPU (nvCOMP) ON NVIDIA A100" << std::endl;
    std::cout << "  Movie: " << tiff_path << std::endl;
    std::cout << "  CPU Threads: " << num_threads << std::endl;
    std::cout << "===============================================================" << std::endl;

    TIFF *tif = TIFFOpen(tiff_path, "r");
    if (!tif) {
        std::cerr << "Failed to open TIFF file: " << tiff_path << std::endl;
        return 1;
    }

    // Inspect geometry across all directories
    uint32_t width = 0, height = 0;
    uint16_t bits = 0, compression = 0;
    TIFFGetField(tif, TIFFTAG_IMAGEWIDTH, &width);
    TIFFGetField(tif, TIFFTAG_IMAGELENGTH, &height);
    TIFFGetField(tif, TIFFTAG_BITSPERSAMPLE, &bits);
    TIFFGetField(tif, TIFFTAG_COMPRESSION, &compression);

    int n_frames = 0;
    do {
        n_frames++;
    } while (TIFFReadDirectory(tif));
    TIFFClose(tif);

    size_t pixels_per_frame = (size_t)width * height;
    size_t total_pixels = pixels_per_frame * n_frames;
    size_t bytes_u16_total = total_pixels * sizeof(uint16_t);
    size_t bytes_f32_total = total_pixels * sizeof(float);

    std::cout << "Geometry: " << width << " x " << height << " x " << n_frames << " frames" << std::endl;
    std::cout << "Total pixels: " << total_pixels << " (" << (bytes_u16_total / 1024.0 / 1024.0) << " MB uint16, "
              << (bytes_f32_total / 1024.0 / 1024.0) << " MB float32)" << std::endl;
    std::cout << "Compression tag: " << compression << " (8 = Deflate)" << std::endl;

    // ------------------------------------------------------------------------
    // Part 1: CPU Baseline Benchmark
    // Current MotionCorr approach: Multi-threaded TIFFReadEncodedStrip into float
    // followed by PCIe cudaMemcpy to GPU.
    // ------------------------------------------------------------------------
    std::cout << "\n--- 1. Running CPU Baseline (libtiff OpenMP decode + PCIe upload) ---" << std::endl;

    std::vector<float> h_cpu_f32(total_pixels);
    float *d_baseline_f32 = nullptr;
    CUDA_CHECK(cudaMalloc(&d_baseline_f32, bytes_f32_total));

    // Warm-up / file cache populate run
    {
        TIFF *t = TIFFOpen(tiff_path, "r");
        TIFFClose(t);
    }

    const int N_REPEATS = 3;
    double cpu_decode_ms_best = 1e9;
    double cpu_upload_ms_best = 1e9;

    for (int rep = 0; rep < N_REPEATS; rep++) {
        auto t0 = std::chrono::high_resolution_clock::now();

        #pragma omp parallel num_threads(num_threads)
        {
            TIFF *thread_tif = TIFFOpen(tiff_path, "r");
            #pragma omp for schedule(dynamic, 1)
            for (int iframe = 0; iframe < n_frames; iframe++) {
                TIFFSetDirectory(thread_tif, iframe);
                uint32_t strips_in_dir = TIFFNumberOfStrips(thread_tif);
                tmsize_t strip_size = TIFFStripSize(thread_tif);
                std::vector<uint16_t> strip_buf(strip_size / sizeof(uint16_t));
                float *frame_dst = h_cpu_f32.data() + (size_t)iframe * pixels_per_frame;

                for (uint32_t s = 0; s < strips_in_dir; s++) {
                    TIFFReadEncodedStrip(thread_tif, s, strip_buf.data(), strip_size);
                    size_t pixels_in_strip = strip_size / sizeof(uint16_t);
                    size_t offset = (size_t)s * pixels_in_strip;
                    for (size_t p = 0; p < pixels_in_strip && (offset + p) < pixels_per_frame; p++) {
                        frame_dst[offset + p] = (float)strip_buf[p];
                    }
                }
            }
            TIFFClose(thread_tif);
        }

        auto t1 = std::chrono::high_resolution_clock::now();
        double decode_ms = std::chrono::duration<double, std::milli>(t1 - t0).count();
        if (decode_ms < cpu_decode_ms_best) cpu_decode_ms_best = decode_ms;

        // Upload to GPU
        auto t2 = std::chrono::high_resolution_clock::now();
        CUDA_CHECK(cudaMemcpy(d_baseline_f32, h_cpu_f32.data(), bytes_f32_total, cudaMemcpyHostToDevice));
        auto t3 = std::chrono::high_resolution_clock::now();
        double upload_ms = std::chrono::duration<double, std::milli>(t3 - t2).count();
        if (upload_ms < cpu_upload_ms_best) cpu_upload_ms_best = upload_ms;
    }

    std::cout << "  CPU Decode Time: " << std::fixed << std::setprecision(2)
              << cpu_decode_ms_best << " ms (Throughput: "
              << (bytes_u16_total / 1e6) / (cpu_decode_ms_best / 1000.0) << " MB/s)" << std::endl;
    std::cout << "  PCIe H2D Upload: " << cpu_upload_ms_best << " ms (Throughput: "
              << (bytes_f32_total / 1e9) / (cpu_upload_ms_best / 1000.0) << " GB/s)" << std::endl;
    std::cout << "  Total Baseline Time to GPU: " << (cpu_decode_ms_best + cpu_upload_ms_best) << " ms" << std::endl;

    // ------------------------------------------------------------------------
    // Part 2: GPU Direct Decompression Benchmark (nvCOMP)
    // ------------------------------------------------------------------------
    std::cout << "\n--- 2. Running GPU Direct Decompression (nvCOMP Batched Deflate) ---" << std::endl;

    std::vector<StripMeta> strip_metas;
    std::vector<uint8_t> all_compressed_bytes;

    auto t_read_comp_start = std::chrono::high_resolution_clock::now();
    {
        TIFF *t = TIFFOpen(tiff_path, "r");
        size_t current_uncomp_offset = 0;
        for (int iframe = 0; iframe < n_frames; iframe++) {
            TIFFSetDirectory(t, iframe);
            uint32_t strips_in_dir = TIFFNumberOfStrips(t);
            tmsize_t uncomp_strip_sz = TIFFStripSize(t);

            for (uint32_t s = 0; s < strips_in_dir; s++) {
                tmsize_t raw_sz = TIFFRawStripSize(t, s);
                size_t comp_offset = all_compressed_bytes.size();
                all_compressed_bytes.resize(comp_offset + raw_sz);
                TIFFReadRawStrip(t, s, all_compressed_bytes.data() + comp_offset, raw_sz);

                StripMeta meta;
                meta.compressed_offset = comp_offset;
                meta.compressed_size = raw_sz;
                // Strip 2-byte zlib header and 4-byte Adler32 trailer
                meta.raw_deflate_offset = comp_offset + 2;
                meta.raw_deflate_size = raw_sz - 6;
                meta.uncompressed_offset = current_uncomp_offset;
                meta.uncompressed_bytes = uncomp_strip_sz;

                strip_metas.push_back(meta);
                current_uncomp_offset += uncomp_strip_sz;
            }
        }
        TIFFClose(t);
    }
    auto t_read_comp_end = std::chrono::high_resolution_clock::now();
    double read_compressed_disk_ms = std::chrono::duration<double, std::milli>(t_read_comp_end - t_read_comp_start).count();

    size_t total_chunks = strip_metas.size();
    size_t total_compressed_bytes = all_compressed_bytes.size();
    std::cout << "  Extracted " << total_chunks << " compressed strips." << std::endl;
    std::cout << "  Total compressed size: " << (total_compressed_bytes / 1024.0 / 1024.0) << " MB" << std::endl;
    std::cout << "  Compression ratio: " << std::setprecision(2)
              << (double)bytes_u16_total / total_compressed_bytes << "x vs u16, "
              << (double)bytes_f32_total / total_compressed_bytes << "x vs f32" << std::endl;
    std::cout << "  Raw compressed read from disk: " << read_compressed_disk_ms << " ms" << std::endl;

    // Allocate GPU buffers
    void *d_compressed = nullptr;
    uint16_t *d_decomp_u16 = nullptr;
    float *d_decomp_f32 = nullptr;
    CUDA_CHECK(cudaMalloc(&d_compressed, total_compressed_bytes));
    CUDA_CHECK(cudaMalloc(&d_decomp_u16, bytes_u16_total));
    CUDA_CHECK(cudaMalloc(&d_decomp_f32, bytes_f32_total));

    // Prepare host chunk pointer and size arrays
    std::vector<void*> h_comp_ptrs(total_chunks);
    std::vector<size_t> h_comp_bytes(total_chunks);
    std::vector<void*> h_decomp_ptrs(total_chunks);
    std::vector<size_t> h_uncomp_buffer_bytes(total_chunks);

    uint8_t *d_comp_base = (uint8_t*)d_compressed;
    uint8_t *d_decomp_base = (uint8_t*)d_decomp_u16;

    for (size_t i = 0; i < total_chunks; i++) {
        h_comp_ptrs[i] = d_comp_base + strip_metas[i].raw_deflate_offset;
        h_comp_bytes[i] = strip_metas[i].raw_deflate_size;
        h_decomp_ptrs[i] = d_decomp_base + strip_metas[i].uncompressed_offset;
        h_uncomp_buffer_bytes[i] = strip_metas[i].uncompressed_bytes;
    }

    // Allocate device arrays for chunk metadata
    void **d_comp_ptrs = nullptr;
    size_t *d_comp_bytes = nullptr;
    void **d_decomp_ptrs = nullptr;
    size_t *d_uncomp_buffer_bytes = nullptr;
    size_t *d_actual_uncomp_bytes = nullptr;
    nvcompStatus_t *d_statuses = nullptr;

    CUDA_CHECK(cudaMalloc(&d_comp_ptrs, sizeof(void*) * total_chunks));
    CUDA_CHECK(cudaMalloc(&d_comp_bytes, sizeof(size_t) * total_chunks));
    CUDA_CHECK(cudaMalloc(&d_decomp_ptrs, sizeof(void*) * total_chunks));
    CUDA_CHECK(cudaMalloc(&d_uncomp_buffer_bytes, sizeof(size_t) * total_chunks));
    CUDA_CHECK(cudaMalloc(&d_actual_uncomp_bytes, sizeof(size_t) * total_chunks));
    CUDA_CHECK(cudaMalloc(&d_statuses, sizeof(nvcompStatus_t) * total_chunks));

    // Copy chunk pointer arrays to device
    CUDA_CHECK(cudaMemcpy(d_comp_ptrs, h_comp_ptrs.data(), sizeof(void*) * total_chunks, cudaMemcpyHostToDevice));
    CUDA_CHECK(cudaMemcpy(d_comp_bytes, h_comp_bytes.data(), sizeof(size_t) * total_chunks, cudaMemcpyHostToDevice));
    CUDA_CHECK(cudaMemcpy(d_decomp_ptrs, h_decomp_ptrs.data(), sizeof(void*) * total_chunks, cudaMemcpyHostToDevice));
    CUDA_CHECK(cudaMemcpy(d_uncomp_buffer_bytes, h_uncomp_buffer_bytes.data(), sizeof(size_t) * total_chunks, cudaMemcpyHostToDevice));

    // Query scratch space for batched decompression
    size_t max_uncomp_chunk = width * 2;
    size_t temp_bytes = 0;
    NVCOMP_CHECK(nvcompBatchedDeflateDecompressGetTempSizeAsync(
        total_chunks, max_uncomp_chunk, nvcompBatchedDeflateDecompressDefaultOpts, &temp_bytes, bytes_u16_total));
    std::cout << "  nvCOMP Scratch Buffer: " << (temp_bytes / 1024.0 / 1024.0) << " MB" << std::endl;

    void *d_temp = nullptr;
    CUDA_CHECK(cudaMalloc(&d_temp, temp_bytes));

    cudaStream_t stream;
    CUDA_CHECK(cudaStreamCreate(&stream));

    // Benchmark GPU Decompress Pipeline
    double upload_comp_ms_best = 1e9;
    double gpu_decomp_ms_best = 1e9;
    double gpu_cast_ms_best = 1e9;

    for (int rep = 0; rep < N_REPEATS; rep++) {
        // 1. Upload compressed bytes
        auto tu0 = std::chrono::high_resolution_clock::now();
        CUDA_CHECK(cudaMemcpyAsync(d_compressed, all_compressed_bytes.data(), total_compressed_bytes, cudaMemcpyHostToDevice, stream));
        CUDA_CHECK(cudaStreamSynchronize(stream));
        auto tu1 = std::chrono::high_resolution_clock::now();
        double u_ms = std::chrono::duration<double, std::milli>(tu1 - tu0).count();
        if (u_ms < upload_comp_ms_best) upload_comp_ms_best = u_ms;

        // 2. GPU Batched Decompress
        auto td0 = std::chrono::high_resolution_clock::now();
        NVCOMP_CHECK(nvcompBatchedDeflateDecompressAsync(
            (const void* const*)d_comp_ptrs,
            d_comp_bytes,
            d_uncomp_buffer_bytes,
            d_actual_uncomp_bytes,
            total_chunks,
            d_temp,
            temp_bytes,
            d_decomp_ptrs,
            nvcompBatchedDeflateDecompressDefaultOpts,
            d_statuses,
            stream));
        CUDA_CHECK(cudaStreamSynchronize(stream));
        auto td1 = std::chrono::high_resolution_clock::now();
        double d_ms = std::chrono::duration<double, std::milli>(td1 - td0).count();
        if (d_ms < gpu_decomp_ms_best) gpu_decomp_ms_best = d_ms;

        // 3. GPU Cast uint16 -> float32
        auto tc0 = std::chrono::high_resolution_clock::now();
        int threads_per_blk = 256;
        int blocks = (int)((total_pixels + threads_per_blk - 1) / threads_per_blk);
        u16_to_float_kernel<<<blocks, threads_per_blk, 0, stream>>>(d_decomp_u16, d_decomp_f32, total_pixels);
        CUDA_CHECK(cudaStreamSynchronize(stream));
        auto tc1 = std::chrono::high_resolution_clock::now();
        double c_ms = std::chrono::duration<double, std::milli>(tc1 - tc0).count();
        if (c_ms < gpu_cast_ms_best) gpu_cast_ms_best = c_ms;
    }

    std::cout << "  PCIe H2D Upload (compressed): " << upload_comp_ms_best << " ms (Throughput: "
              << (total_compressed_bytes / 1e9) / (upload_comp_ms_best / 1000.0) << " GB/s)" << std::endl;
    std::cout << "  GPU nvCOMP Decompress: " << gpu_decomp_ms_best << " ms (Throughput: "
              << (bytes_u16_total / 1e9) / (gpu_decomp_ms_best / 1000.0) << " GB/s uncompressed)" << std::endl;
    std::cout << "  GPU uint16 -> float32 cast: " << gpu_cast_ms_best << " ms" << std::endl;
    double total_gpu_pipeline = upload_comp_ms_best + gpu_decomp_ms_best + gpu_cast_ms_best;
    std::cout << "  Total GPU Transfer + Decompress + Cast: " << total_gpu_pipeline << " ms" << std::endl;

    // ------------------------------------------------------------------------
    // Part 3: Exhaustive Bit-for-Bit Pixel Verification
    // ------------------------------------------------------------------------
    std::cout << "\n--- 3. Verifying Bit-for-Bit Pixel Identity ---" << std::endl;

    std::vector<float> h_gpu_f32(total_pixels);
    CUDA_CHECK(cudaMemcpy(h_gpu_f32.data(), d_decomp_f32, bytes_f32_total, cudaMemcpyDeviceToHost));

    size_t diff_pixels = 0;
    float max_abs_diff = 0.0f;
    for (size_t i = 0; i < total_pixels; i++) {
        float cp = h_cpu_f32[i];
        float gp = h_gpu_f32[i];
        if (cp != gp) {
            diff_pixels++;
            float d = std::fabs(cp - gp);
            if (d > max_abs_diff) max_abs_diff = d;
        }
    }

    std::cout << "  Total pixels compared: " << total_pixels << std::endl;
    std::cout << "  Differing pixels:      " << diff_pixels << std::endl;
    std::cout << "  Max absolute error:    " << max_abs_diff << std::endl;
    if (diff_pixels == 0) {
        std::cout << "  [VERDICT] PASS: 100% BIT-FOR-BIT IDENTICAL!" << std::endl;
    } else {
        std::cout << "  [VERDICT] FAIL: Mismatches detected!" << std::endl;
    }

    // ------------------------------------------------------------------------
    // Part 4: Summary Comparison
    // ------------------------------------------------------------------------
    std::cout << "\n===============================================================" << std::endl;
    std::cout << "                      SUMMARY COMPARISON                       " << std::endl;
    std::cout << "===============================================================" << std::endl;
    std::cout << "Metric                        CPU Baseline      GPU nvCOMP       Speedup" << std::endl;
    std::cout << "---------------------------------------------------------------" << std::endl;
    std::cout << "Data sent across PCIe:        " << std::setw(8) << (bytes_f32_total / 1024.0 / 1024.0) << " MB     "
              << std::setw(8) << (total_compressed_bytes / 1024.0 / 1024.0) << " MB     "
              << std::setw(6) << std::setprecision(1) << (double)bytes_f32_total / total_compressed_bytes << "x less" << std::endl;
    std::cout << "PCIe Transfer Time:           " << std::setw(8) << std::setprecision(2) << cpu_upload_ms_best << " ms     "
              << std::setw(8) << upload_comp_ms_best << " ms     "
              << std::setw(6) << std::setprecision(1) << cpu_upload_ms_best / upload_comp_ms_best << "x faster" << std::endl;
    std::cout << "Decompress / Inflate Time:    " << std::setw(8) << std::setprecision(2) << cpu_decode_ms_best << " ms     "
              << std::setw(8) << (gpu_decomp_ms_best + gpu_cast_ms_best) << " ms     "
              << std::setw(6) << std::setprecision(1) << cpu_decode_ms_best / (gpu_decomp_ms_best + gpu_cast_ms_best) << "x faster" << std::endl;
    double baseline_total = cpu_decode_ms_best + cpu_upload_ms_best;
    std::cout << "Total (Decompress + Upload):  " << std::setw(8) << std::setprecision(2) << baseline_total << " ms     "
              << std::setw(8) << total_gpu_pipeline << " ms     "
              << std::setw(6) << std::setprecision(1) << baseline_total / total_gpu_pipeline << "x faster" << std::endl;
    std::cout << "===============================================================" << std::endl;

    // Cleanup
    cudaFree(d_baseline_f32);
    cudaFree(d_compressed);
    cudaFree(d_decomp_u16);
    cudaFree(d_decomp_f32);
    cudaFree(d_temp);
    cudaFree(d_comp_ptrs);
    cudaFree(d_comp_bytes);
    cudaFree(d_decomp_ptrs);
    cudaFree(d_uncomp_buffer_bytes);
    cudaFree(d_actual_uncomp_bytes);
    cudaFree(d_statuses);
    cudaStreamDestroy(stream);

    return (diff_pixels == 0) ? 0 : 2;
}
