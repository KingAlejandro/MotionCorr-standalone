#pragma once
// Host-only stand-ins. These expose production ownership calls, not GPU results.
#include <cstddef>
#define CUDART_VERSION 12080
enum cudaError_t { cudaSuccess, cudaErrorMemoryAllocation, cudaErrorInvalidDevice,
 cudaErrorIllegalAddress, cudaErrorLaunchFailure, cudaErrorLaunchTimeout,
 cudaErrorHardwareStackError, cudaErrorIllegalInstruction, cudaErrorMisalignedAddress,
 cudaErrorInvalidAddressSpace, cudaErrorInvalidPc, cudaErrorECCUncorrectable,
 cudaErrorContextIsDestroyed, cudaErrorDeviceUninitialized, cudaErrorAssert, cudaErrorExternalDevice };
enum cudaMemcpyKind { cudaMemcpyHostToDevice, cudaMemcpyDeviceToHost };
using cudaEvent_t = void*;
cudaError_t cudaSetDevice(int);
cudaError_t cudaPeekAtLastError();
cudaError_t cudaMalloc(void**, std::size_t);
cudaError_t cudaFree(void*);
cudaError_t cudaMemcpy(void*, const void*, std::size_t, cudaMemcpyKind);
cudaError_t cudaEventDestroy(cudaEvent_t);
