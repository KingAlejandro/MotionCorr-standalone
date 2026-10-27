# Supplementary arithmetic (computed after the freeze from the frozen outputs; descriptive, no gate)

| case/arm | patch with largest eta RMS (g1-4) | its share of sum of eta^2 (g1-4) | eta RMS / H RMS per frame g1..g4 |
|---|---|---|---|
| noisy/OFF | (62,79) | 0.682 | 6.915 / 3.101 / 1.858 / 2.888 |
| noisy/ON | (104,15) | 0.354 | 6.255 / 2.127 / 1.352 / 0.721 |
| affine/OFF | (104,15) | 0.433 | 0.465 / 0.482 / 0.476 / 0.456 |
| affine/ON | (104,15) | 0.472 | 0.268 / 0.273 / 0.270 / 0.269 |
| pedestal/OFF | (104,15) | 0.434 | 0.463 / 0.482 / 0.476 / 0.456 |
| pedestal/ON | (104,15) | 0.473 | 0.269 / 0.273 / 0.270 / 0.269 |

Patches whose g=1..4 RMS is larger with full-width ON than with OFF (frames with larger RMS ON: none in every listed quantity unless shown):

- noisy eta: patches (patch, OFF, ON) [((20, 47), 1.3139, 1.4518)]; frames none
- noisy e_tr: patches (patch, OFF, ON) [((20, 47), 1.771, 1.816)]; frames none
- noisy fit:native_runtime_coeff: patches (patch, OFF, ON) none; frames none
- noisy fit:legacy_coeff: patches (patch, OFF, ON) none; frames none
- noisy fit:B2_coeff: patches (patch, OFF, ON) none; frames none
- affine eta: patches (patch, OFF, ON) [((20, 15), 0.0353, 0.0438)]; frames none
- affine e_tr: patches (patch, OFF, ON) [((20, 15), 0.0396, 0.0502)]; frames none
- affine fit:native_runtime_coeff: patches (patch, OFF, ON) [((20, 15), 0.0395, 0.0476), ((62, 47), 0.0147, 0.0248), ((104, 79), 0.0343, 0.0434)]; frames none
- affine fit:legacy_coeff: patches (patch, OFF, ON) [((20, 15), 0.0395, 0.0476), ((62, 47), 0.0147, 0.0248), ((104, 79), 0.0343, 0.0435)]; frames none
- affine fit:B2_coeff: patches (patch, OFF, ON) [((20, 15), 0.03, 0.0361), ((62, 47), 0.0214, 0.0242), ((104, 79), 0.0392, 0.0511)]; frames none
- pedestal eta: patches (patch, OFF, ON) [((20, 15), 0.0345, 0.043)]; frames none
- pedestal e_tr: patches (patch, OFF, ON) [((20, 15), 0.0383, 0.0489)]; frames none
- pedestal fit:native_runtime_coeff: patches (patch, OFF, ON) [((20, 15), 0.0385, 0.0468), ((62, 47), 0.0151, 0.0254), ((104, 79), 0.0347, 0.0436)]; frames none
- pedestal fit:legacy_coeff: patches (patch, OFF, ON) [((20, 15), 0.0385, 0.0468), ((62, 47), 0.0151, 0.0254), ((104, 79), 0.0347, 0.0436)]; frames none
- pedestal fit:B2_coeff: patches (patch, OFF, ON) [((20, 15), 0.03, 0.0357), ((62, 47), 0.0218, 0.0246), ((104, 79), 0.0396, 0.0511)]; frames none
