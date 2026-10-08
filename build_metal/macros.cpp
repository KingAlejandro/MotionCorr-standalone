#include "src/macros.h"

// This is necessary because we cannot directly concatenate string 
// literals in the preprocessor
#define RELION_VERSION_SUFFIX "-motioncorr-standalone"
#define RELION_LONG_VERSION (RELION_SHORT_VERSION RELION_VERSION_SUFFIX)

const char *g_RELION_VERSION = RELION_LONG_VERSION;
