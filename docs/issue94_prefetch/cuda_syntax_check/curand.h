#pragma once
typedef struct curandGenerator_st *curandGenerator_t;
typedef int curandStatus_t;
enum { CURAND_STATUS_SUCCESS = 0, CURAND_RNG_PSEUDO_DEFAULT = 100 };
typedef int curandRngType_t;
