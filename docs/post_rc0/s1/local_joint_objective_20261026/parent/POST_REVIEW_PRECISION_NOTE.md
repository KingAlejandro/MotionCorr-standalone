# Precision and interpretation note

The retained Opus report's statement that removing a constant DC term cannot change argmax or quadratic fitting is an exact-arithmetic statement. Actual float32 map formation and subtraction can change peaks, ties and fitted offsets; the earlier CUDA/DC experiments already distinguish this. This raw-coherence diagnostic explicitly zeros DC and does not contradict those finite-precision results.

The native update has no general joint-ascent guarantee, but both captured steps INCREASE this defined J on both patches. No observed joint-objective decrease is claimed here. Stronger optimization raises J a little further while the selected all-five-frame physical trajectory error worsens. The narrower conclusion is that stronger optimization alone does not repair this retained case under this unchanged objective.

The raw objective is periodic; wrapped diagnostics are supplementary. Physical unwrapped point-center errors remain primary and are not full fixed-ROI field scores. The support-mean mapping and within-patch spread characterize one limitation of a rigid patch representation; they neither subtract a floor nor establish a universal optimum for noisy, windowed, nonrigid data. No source/default, image-pixel, native, CUDA, STAR or scientific qualification is claimed by this calculation.
