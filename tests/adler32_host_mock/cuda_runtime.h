#pragma once
// Explicit single-thread CPU execution of the ACTUAL kernel body. This does not
// emulate GPU execution, nvCOMP or synchronization; native coverage is separate.
#define __global__
#define __shared__
struct McAdlerDim { unsigned x; };
inline McAdlerDim blockIdx{0}, threadIdx{0}, blockDim{1};
inline void __syncthreads() {}
