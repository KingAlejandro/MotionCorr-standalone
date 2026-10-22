// SPDX-License-Identifier: GPL-2.0-or-later
// Deliberately fake CUDA surface for host interposition controls ONLY.
#pragma once
#include <cstddef>
struct dim3 { unsigned x, y, z; dim3(unsigned a=1, unsigned b=1, unsigned c=1): x(a), y(b), z(c) {} };
using cudaStream_t = void *;
enum cudaError_t { cudaSuccess = 0, cudaErrorUnknown = 999 };
enum cudaMemcpyKind { cudaMemcpyDeviceToHost };
cudaError_t cudaStreamSynchronize(cudaStream_t);
cudaError_t cudaMemcpy(void *, const void *, size_t, cudaMemcpyKind);
