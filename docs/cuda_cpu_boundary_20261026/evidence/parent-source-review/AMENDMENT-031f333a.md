# Follow-up source review

Fix revision: `031f333a2863218c74951117989c84423ad9c92e`.

The CUDA inverse batch now explicitly initializes every complex element to `(0,0)` before loading frames 0 and 4. The new `inverse-valid` arm compares the complete input bytes before and after native Hermitian projection and fails if projection changes them. These changes resolve the two source/interpretation concerns recorded in REVIEW.md for bounded replay use.

Source finding: **resolved**. This is parent read-only diff review, not a native rerun. The owner reports 12 versioned inverse-only processes exiting zero, 39/39 v2 checks, and projection no-op for the valid controls; those execution results were not independently recomputed by this source review. The original inverse attempts retain their undefined full-batch provenance even where selected outputs happen to match v2. No movie or capture retry was requested.

Forward/window replay and capture-source neutrality remain separate evidence. No inverse-transform correctness verdict or estimator/scientific acceptance follows from source clearance alone.
