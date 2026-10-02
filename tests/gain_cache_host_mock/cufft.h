// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <cstddef>
using cufftHandle = int;
struct cufftComplex { float x, y; };
enum cufftResult { CUFFT_SUCCESS, CUFFT_ALLOC_FAILED, CUFFT_INTERNAL_ERROR };
enum cufftType { CUFFT_R2C, CUFFT_C2R };
cufftResult cufftCreate(cufftHandle*);
cufftResult cufftDestroy(cufftHandle);
cufftResult cufftSetAutoAllocation(cufftHandle, int);
cufftResult cufftMakePlanMany(cufftHandle, int, int*, int*, int, int, int*, int, int, cufftType, int, std::size_t*);
cufftResult cufftSetWorkArea(cufftHandle, void*);
cufftResult cufftGetSize(cufftHandle, std::size_t*);
