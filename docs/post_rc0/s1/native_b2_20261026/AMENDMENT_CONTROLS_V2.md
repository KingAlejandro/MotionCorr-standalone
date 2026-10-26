# Controls v1 failure and comparison-only v2 amendment

Before any ON or fullsize movie, controls v1 stopped after zero BASE/OFF: raw aggregate corrected_micrographs.star differs only in the two expected output directory prefixes. `diff -u` retained in the evidence bundle; case zero.star is byte-identical. No numerical/pixel/source/prediction discrepancy found. Original STOP, BASE/OFF producer receipts and outputs are retained unchanged.

Versioned campaign_v2.py normalizes ONLY each output tree's own root to @ROOT@ for STAR text, as pinned PR286 compare_products.py does. Scientific case STAR bytes remain byte-equal; MRC header0:224 and payload1024: are exact, timestamp labels inventoried. V2 reuses the already completed zero BASE/OFF producer outputs, explicitly records their RUN hashes, and does not rerun them. All later producer directories remain exclusive-create. Original STOP stays immutable; V2 uses STOP-v2 for any fresh failure. No tolerance or truth metric change.
