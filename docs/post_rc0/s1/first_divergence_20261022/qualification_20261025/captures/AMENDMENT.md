# W4 CPU capture version3: narrow log-neutrality amendment

Version2 attempt on25October remains FAIL after one native process (selector1,1). All numerical state, MRC and STAR checks passed. The only log differences are the new output path and wall time0.014vs0.015seconds. The original output is retained on theVM and in a hash-addressed local archive. Seven selectors did not run.

Version3 validates and replaces exactly one complete output-path line, which must name that arm's own affine.mrc, and exactly one finite nonnegative wall-time line. Missing, duplicate, malformed or wrong-path fields refuse. Every other byte/line (including all iteration, RMSD, acceptance and fit data) remains exact. No numerical gate/tolerance, source, binary, input, capture, cleanup, lease or resource rule changes. This is a logging-contract repair, not a production policy change.

A separate read-only v3grade may qualify the existing selector1,1 capture under this explicit contract without changing its original FAIL. Then one new namespace may execute only the seven remaining selectors, once each, under CPU13/one thread, original64MiBcap and120s/child limit. No selector or originalnamespace is retried or overwritten. NativeCUDA capture remains UNRUN; capture qualification itself is not motion accuracy or science qualification.
