/* Measurement-only sub-timers for the output stage (issue: output write speed).
 * Active only in a -DTIMING build; compiles to nothing otherwise.
 * The globals are defined in motioncorr_runner.cpp next to MCtimer. */
#ifndef OUTPUT_TIMING_H_
#define OUTPUT_TIMING_H_

#ifdef TIMING
#include "src/time.h"
extern Timer MCtimer;
extern int TIMING_W_OPEN;
extern int TIMING_W_STATS;
extern int TIMING_W_HEADER;
extern int TIMING_W_PAYLOAD;
extern int TIMING_W_CLOSE;
#define OTIC(label) (MCtimer.tic(label))
#define OTOC(label) (MCtimer.toc(label))
#else
#define OTIC(label)
#define OTOC(label)
#endif

#endif
