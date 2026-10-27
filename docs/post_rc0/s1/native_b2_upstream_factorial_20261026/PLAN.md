# Frozen K267 upstream × B2 factorial, before new producers

Sealed first task/reference: e28ffb10c9189a5a5054bf7e6e51027f560766a6, unchanged. Sole writer of PR287; evidence-only follow-up. Production326f03a0 and binary531a1b0984dfbb39bd1b43afa23561091365a4d0459967ef5ee24ca69344c2eb unchanged. PINS.json was live-verified before this freeze: same retained fixtures/truth as the sealed first task, source/tool hashes, and hashes of all reused OFF/B2 outputs. No new native producer has run. No code/default/gate/publication/policy change.

## Question, design and predictions

Does repairing upstream CCF observations remove the gross late-patch discrepancies and N5 B2 harm, or does the endpoint fit still transmit remaining errors? Raw STAR-observation row-L2 gain is not generic alignment-noise variance. Gemini's common-grid N5 endpoint identity hhat4=y4-y0=L4 holds before spatial projection, with its stated covariance/model limitations.

2×2 factors: upstream OFF / existing DCboth+coupledall; B2 OFF / ON. Reuse sealed 8-case OFF and B2-alone outputs, never rerun them. Only16 new tiny native producers: UP then UP+B2 for each of8 cases. Fixed order: noisy, affine, pedestal, zero, integer, fractional, flat, repeated. Each case uses the existing fixture command: use_own, j2, bin1/group1, seed1, skip_defect, save_noDW, first1/last5, skip_logfile; patch3×3 on noisy/affine/pedestal, patch1 otherwise. Production stop only max_iter5/default0.5px. UP adds exactly --experimental_coupled_peak all and MC_EXPERIMENT_CCF_DC_ARM=both; UP+B2 adds exactly --experimental_local_b2. Other experiment flags off. No GPU/fullsize/full100/new seed/long budget.

- **P1:** compound keeps all5 UP gate-role PASS cases (zero, integer, fractional, affine, pedestal), runtime AND real STAR.
- **P2:** noisy compound improves over sealed B2-alone on EACH RMS/p95/max AND does not worsen UP-only on ANY of those3 metrics, runtime AND real STAR. Strict inequalities for improvement; nonincrease for no-worsening, no discretionary numeric tolerance. All numeric increases including PASS→PASS reported.
- Flat/repeated remain checker UNIDENTIFIABLE; field-only numeric distances are separate. No noisy promotion claim even if one comparison improves.

Scientific prediction failure is a falsified characterization result, retained without tuning or extension. All8 cases are predeclared; do not silently omit failed rows. Original e28 noisy harm remains a promotion blocker. No automatic merge, qualification, full100 or old CUDA-port revival. H7 falsified generic DC+coupled production benefit; no-CUDA-port branch remains. N controls are global-only: reuse the sealed B2 neutrality plus prior PR286 N/H6 evidence with global/local limitations; no N rerun or new joint qualification claim.

## Execution, captures and stop rules

Dedicated scratch /tmp/motioncorr-b2-factorial-20261026, exclusive-create run directories, all failures retained, no producer retry. Same binary/source/input hash verified before each native launch. Runtime coefficients/global captured through the existing compiled hook, actual STAR/log/sum retained. Existing comparator/comparator copy-negatives reused for any identity check, root normalization only as already reviewed; no expectation of equal image/coeff products between B2 arms.

For every UP pair require identical global runtime trajectory, raw serialized global block, raw local observations, patch convergence/acceptance states, DC and coupled-guard manipulation counters. Record local_enabled/model rejection separately because B2 fit-RMS intentionally has a different estimand. Require DC arm both, N/N global and N/N eligible local CCF frames zeroed, coupled peaks global/patch as applicable, guard counts accounted. No eligible local peaks is global-only, not a failed manipulation. Finite complete producer output plus checker classes and numeric runtime/actualSTAR field metrics must be recorded.

Exit, nonfinite, input/source/binary hash, lease/resource, unsupported configuration, capture/precision/identity/manipulation failures stop the affected execution; retain diagnostics before any versioned amendment. A common infrastructure failure blocks remaining native launches. Scientific FAIL/prediction falsification does not skip the rest of the predeclared characterization matrix. No silent fallback, no tolerance relaxation. Reused base outputs retain their original classes/failed records.

cpu64 only; whole-chain affinity32-47, native2 OpenMP threads, total budget≤16. Append-open every known compatible overlapping MotionCorr lease plus mandatory canonical /tmp/motioncorr-cpu64-bench.lock; reuse sealed lane guard. Fresh per-producer occupancy assessment and affinity/lease/scratch check (25GiB combined task scratch cap). Reject observed foreign >50% CPU compute on allocated cores; no job stopped/signalled. Record walls/RSS/commands as receipts only; no timing/performance claim, profile, or extension.

## Frozen independent cross-feed and mechanism analysis

Only after UP-only observations are fixed, apply the unchanged W8 OFF operator (g+.5/no intercept) and B2 operator (integer g/free patch constant) to those SAME stored UP observations/accepted coordinates/global. Verify spatial rank6,≥4 times, full18+npatch rank when local enabled; retain all actual accepted coordinates and report dropped patches. No observations invented for global-only cases. Compare predicted physical fields with native UP/UP+B2 and native-vs-realSTAR separately. Derive diagnostic rounding bounds from actual design pseudoinverse/physical field basis and pinned writer's≤5e-6px per-axis signed rounding, +1e-8px arithmetic margin; not a scientific gate or relaxation. Native-vs-predicted discrepancy outside that bound stops that affected analysis for diagnosis.

For base and UP observation sets, reconstruct L(p,g)=obs(p,g)-obs(p,0), g=1..4, with frame0=0. Report every patch/frame vector η=L−(truth(p,g)−G[g]), every norm, per-frame RMS/p95/max and maximum vector discrepancy at g4 (both all-accepted and predeclared common-coordinate comparison). Explicitly list dropped coordinates and their base discrepancies; a changed acceptance set is not pure peak-error repair. No outlier threshold/removal, ROI/mask/gauge change or convenient observation exclusion.

As the Gemini challenge, use the unchanged truth field to define its spatial constant trajectory Gtruth and residual; verify spatial/temporal representation error rather than assuming it. For each frozen operator H and actual accepted geometry decompose the rounded-observation error exactly:

E = U + M + P,
U = (G−Gtruth) + H Tr[−(G−Gtruth)],
M = Gtruth + H Tr[Tpatch−Gtruth] − T,
P = H (obs−Tr[Tpatch−G]).

U is the conditional unabsorbed global term; M is truth-only convention/polynomial/spatial projection residual; P is propagated observation discrepancy, not isolated stochastic noise. Also split P into Trη and the residual induced by rounded observations' Tr constraint. Report ROI and full-border standalone mean squares, ALL cross terms and algebraic closure, plus the native-minus-rounded-fit precision remainder. Cross terms/norm ratios/counterfactuals are not causal percentages. Fixed-observation U improvement cannot exclude indirect upstream nonconvergence effects. Physical h0 correctness is not general accuracy.

Use unchanged checker ROI and .20/.40/.80Å limits; checker accuracy/identifiability/sampling/application classes separate from field-only metrics. Final report includes4-arm metrics, all regressions, P1/P2 dispositions, stage counters, coverage/rank, cross-feed fields/bounds and decomposition. Commit/push evidence-only update and one brief PR287 comment; return smallest next experiment or explicit NO-GO. No new producer beyond these16.
