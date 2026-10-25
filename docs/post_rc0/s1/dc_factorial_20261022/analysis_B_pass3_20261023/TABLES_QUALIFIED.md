# Qualified presentation of the frozen Tier B snapshot

DRAFT partial descriptive analysis. Source3eee0a4b; snapshot22:44:59Z. This supplement changes presentation only and preserves the frozen raw tables/JSON. Selected736 records comprise734 EVALUATED experiments and2 CONTROL_ONLY plain CUDA records;68 jobs excluded at freeze. The two CPU plain records were excluded. Plain-vs-none byte controls are UNRUN for Tier B. All734 experiment sampling statuses are VALID. No adoption, science, performance or full-campaign acceptance.

Each complete cell has10 matched noise seeds on one fixed scene/motion field. Several conditions are affine copies of related noise draws; metrics/backends are dependent. Nominal labels use the frozen unadjusted sign rule with no effect-size floor or calibrated none-vs-none CUDA noise. They are descriptive labels, not31 independent findings. Partial-arm medians use unequal seed cohorts and must not be compared as arm effects. The separate common-seed panel below is descriptive only. UNRUN cells display UNRUN throughout.

## Per-arm descriptive metrics

| Condition | Backend | Arm | Evidence | Evaluated / expected | RMS px | P95 px | Worst max px | Transfer | Global nonconv | Local disabled | Outside ROI | Field FAIL | Failure union |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| pedestal32 | cpu | none | COMPLETE | 10/10 | 1.78785 | 3.22608 | 6.54125 | 0.926233 | 10/10 | 10/10 | 0/10 | 10/10 | 10/10 |
| pedestal32 | cpu | global | COMPLETE | 10/10 | 0.893464 | 1.75387 | 3.0514 | 0.993981 | 0/10 | 10/10 | 0/10 | 10/10 | 10/10 |
| pedestal32 | cpu | local | COMPLETE | 10/10 | 1.3012 | 2.69117 | 4.54089 | 0.940589 | 10/10 | 0/10 | 0/10 | 10/10 | 10/10 |
| pedestal32 | cpu | both | COMPLETE | 10/10 | 0.29919 | 0.590533 | 1.55853 | 0.991115 | 0/10 | 0/10 | 0/10 | 9/10 | 9/10 |
| pedestal32 | cuda | none | COMPLETE | 10/10 | 1.73835 | 2.86802 | 5.46714 | 0.930792 | 10/10 | 10/10 | 0/10 | 10/10 | 10/10 |
| pedestal32 | cuda | global | COMPLETE | 10/10 | 0.893464 | 1.75387 | 3.0514 | 0.993981 | 0/10 | 10/10 | 0/10 | 10/10 | 10/10 |
| pedestal32 | cuda | local | COMPLETE | 10/10 | 1.1846 | 2.06822 | 3.81499 | 0.951878 | 10/10 | 0/10 | 0/10 | 10/10 | 10/10 |
| pedestal32 | cuda | both | COMPLETE | 10/10 | 0.299182 | 0.59051 | 1.55848 | 0.991115 | 0/10 | 0/10 | 0/10 | 9/10 | 9/10 |
| pedestal0 | cpu | none | COMPLETE | 10/10 | 0.299184 | 0.590512 | 1.55849 | 0.991115 | 0/10 | 0/10 | 0/10 | 9/10 | 9/10 |
| pedestal0 | cpu | global | COMPLETE | 10/10 | 0.299184 | 0.590512 | 1.55849 | 0.991115 | 0/10 | 0/10 | 0/10 | 9/10 | 9/10 |
| pedestal0 | cpu | local | COMPLETE | 10/10 | 0.299183 | 0.590512 | 1.55849 | 0.991115 | 0/10 | 0/10 | 0/10 | 9/10 | 9/10 |
| pedestal0 | cpu | both | COMPLETE | 10/10 | 0.299183 | 0.590512 | 1.55849 | 0.991115 | 0/10 | 0/10 | 0/10 | 9/10 | 9/10 |
| pedestal0 | cuda | none | COMPLETE | 10/10 | 0.299183 | 0.590512 | 1.55849 | 0.991114 | 0/10 | 0/10 | 0/10 | 9/10 | 9/10 |
| pedestal0 | cuda | global | COMPLETE | 10/10 | 0.299183 | 0.590512 | 1.55849 | 0.991115 | 0/10 | 0/10 | 0/10 | 9/10 | 9/10 |
| pedestal0 | cuda | local | COMPLETE | 10/10 | 0.299183 | 0.590513 | 1.55849 | 0.991115 | 0/10 | 0/10 | 0/10 | 9/10 | 9/10 |
| pedestal0 | cuda | both | COMPLETE | 10/10 | 0.299183 | 0.590512 | 1.55849 | 0.991114 | 0/10 | 0/10 | 0/10 | 9/10 | 9/10 |
| contrast025 | cpu | none | COMPLETE | 10/10 | 0.314163 | 0.616715 | 1.57344 | 0.990817 | 0/10 | 0/10 | 0/10 | 9/10 | 9/10 |
| contrast025 | cpu | global | COMPLETE | 10/10 | 0.307845 | 0.605032 | 1.59813 | 0.991016 | 0/10 | 0/10 | 0/10 | 9/10 | 9/10 |
| contrast025 | cpu | local | COMPLETE | 10/10 | 0.299855 | 0.589481 | 1.53833 | 0.990921 | 0/10 | 0/10 | 0/10 | 9/10 | 9/10 |
| contrast025 | cpu | both | COMPLETE | 10/10 | 0.299184 | 0.590514 | 1.5585 | 0.991115 | 0/10 | 0/10 | 0/10 | 9/10 | 9/10 |
| contrast025 | cuda | none | COMPLETE | 10/10 | 0.297152 | 0.592521 | 1.60521 | 0.990925 | 0/10 | 0/10 | 0/10 | 9/10 | 9/10 |
| contrast025 | cuda | global | COMPLETE | 10/10 | 0.299104 | 0.593048 | 1.58548 | 0.990945 | 0/10 | 0/10 | 0/10 | 9/10 | 9/10 |
| contrast025 | cuda | local | COMPLETE | 10/10 | 0.298288 | 0.593929 | 1.55359 | 0.991071 | 0/10 | 0/10 | 0/10 | 9/10 | 9/10 |
| contrast025 | cuda | both | COMPLETE | 10/10 | 0.299183 | 0.590511 | 1.55849 | 0.991115 | 0/10 | 0/10 | 0/10 | 9/10 | 9/10 |
| contrast4 | cpu | none | COMPLETE | 10/10 | 0.299173 | 0.590498 | 1.5581 | 0.991115 | 0/10 | 0/10 | 0/10 | 9/10 | 9/10 |
| contrast4 | cpu | global | COMPLETE | 10/10 | 0.299198 | 0.590501 | 1.55907 | 0.991115 | 0/10 | 0/10 | 0/10 | 9/10 | 9/10 |
| contrast4 | cpu | local | COMPLETE | 10/10 | 0.299161 | 0.590507 | 1.55815 | 0.991115 | 0/10 | 0/10 | 0/10 | 9/10 | 9/10 |
| contrast4 | cpu | both | COMPLETE | 10/10 | 0.299184 | 0.590513 | 1.55849 | 0.991115 | 0/10 | 0/10 | 0/10 | 9/10 | 9/10 |
| contrast4 | cuda | none | COMPLETE | 10/10 | 0.299168 | 0.59049 | 1.55811 | 0.991114 | 0/10 | 0/10 | 0/10 | 9/10 | 9/10 |
| contrast4 | cuda | global | COMPLETE | 10/10 | 0.299173 | 0.590494 | 1.55829 | 0.991114 | 0/10 | 0/10 | 0/10 | 9/10 | 9/10 |
| contrast4 | cuda | local | COMPLETE | 10/10 | 0.299161 | 0.590474 | 1.55823 | 0.991114 | 0/10 | 0/10 | 0/10 | 9/10 | 9/10 |
| contrast4 | cuda | both | COMPLETE | 10/10 | 0.299183 | 0.590512 | 1.55849 | 0.991115 | 0/10 | 0/10 | 0/10 | 9/10 | 9/10 |
| dose1 | cpu | none | COMPLETE | 10/10 | 0.299201 | 0.5908 | 1.55998 | 0.991112 | 0/10 | 0/10 | 0/10 | 9/10 | 9/10 |
| dose1 | cpu | global | COMPLETE | 10/10 | 0.299057 | 0.590608 | 1.55844 | 0.991122 | 0/10 | 0/10 | 0/10 | 9/10 | 9/10 |
| dose1 | cpu | local | COMPLETE | 10/10 | 0.299063 | 0.590292 | 1.55983 | 0.991108 | 0/10 | 0/10 | 0/10 | 9/10 | 9/10 |
| dose1 | cpu | both | COMPLETE | 10/10 | 0.299183 | 0.590512 | 1.55849 | 0.991115 | 0/10 | 0/10 | 0/10 | 9/10 | 9/10 |
| dose1 | cuda | none | COMPLETE | 10/10 | 0.298942 | 0.589961 | 1.5556 | 0.99112 | 0/10 | 0/10 | 0/10 | 9/10 | 9/10 |
| dose1 | cuda | global | COMPLETE | 10/10 | 0.298785 | 0.58988 | 1.55593 | 0.991115 | 0/10 | 0/10 | 0/10 | 9/10 | 9/10 |
| dose1 | cuda | local | COMPLETE | 10/10 | 0.299258 | 0.590507 | 1.55979 | 0.99111 | 0/10 | 0/10 | 0/10 | 9/10 | 9/10 |
| dose1 | cuda | both | COMPLETE | 10/10 | 0.299183 | 0.590512 | 1.55849 | 0.991115 | 0/10 | 0/10 | 0/10 | 9/10 | 9/10 |
| dose05 | cpu | none | COMPLETE | 10/10 | 0.429694 | 0.793115 | 2.41449 | 0.988417 | 0/10 | 0/10 | 0/10 | 10/10 | 10/10 |
| dose05 | cpu | global | COMPLETE | 10/10 | 0.42941 | 0.79366 | 2.41635 | 0.988417 | 0/10 | 0/10 | 0/10 | 10/10 | 10/10 |
| dose05 | cpu | local | COMPLETE | 10/10 | 0.42966 | 0.793054 | 2.41373 | 0.98844 | 0/10 | 0/10 | 0/10 | 10/10 | 10/10 |
| dose05 | cpu | both | COMPLETE | 10/10 | 0.429984 | 0.793704 | 2.41418 | 0.988435 | 0/10 | 0/10 | 0/10 | 10/10 | 10/10 |
| dose05 | cuda | none | COMPLETE | 10/10 | 0.43045 | 0.792269 | 2.41765 | 0.988453 | 0/10 | 0/10 | 0/10 | 10/10 | 10/10 |
| dose05 | cuda | global | COMPLETE | 10/10 | 0.430336 | 0.793299 | 2.41653 | 0.988424 | 0/10 | 0/10 | 0/10 | 10/10 | 10/10 |
| dose05 | cuda | local | COMPLETE | 10/10 | 0.429949 | 0.793535 | 2.41375 | 0.988463 | 0/10 | 0/10 | 0/10 | 10/10 | 10/10 |
| dose05 | cuda | both | COMPLETE | 10/10 | 0.429984 | 0.793707 | 2.41419 | 0.988435 | 0/10 | 0/10 | 0/10 | 10/10 | 10/10 |
| dose2 | cpu | none | COMPLETE | 10/10 | 0.199375 | 0.380686 | 1.14225 | 0.991455 | 0/10 | 0/10 | 0/10 | 3/10 | 3/10 |
| dose2 | cpu | global | COMPLETE | 10/10 | 0.199313 | 0.380525 | 1.13639 | 0.991458 | 0/10 | 0/10 | 0/10 | 3/10 | 3/10 |
| dose2 | cpu | local | COMPLETE | 10/10 | 0.200176 | 0.381739 | 1.14043 | 0.991455 | 0/10 | 0/10 | 0/10 | 3/10 | 3/10 |
| dose2 | cpu | both | COMPLETE | 10/10 | 0.199961 | 0.380998 | 1.14108 | 0.991454 | 0/10 | 0/10 | 0/10 | 3/10 | 3/10 |
| dose2 | cuda | none | COMPLETE | 10/10 | 0.199514 | 0.379545 | 1.13511 | 0.991439 | 0/10 | 0/10 | 0/10 | 3/10 | 3/10 |
| dose2 | cuda | global | COMPLETE | 10/10 | 0.199349 | 0.37916 | 1.13907 | 0.991457 | 0/10 | 0/10 | 0/10 | 3/10 | 3/10 |
| dose2 | cuda | local | COMPLETE | 10/10 | 0.200099 | 0.381205 | 1.13844 | 0.991443 | 0/10 | 0/10 | 0/10 | 3/10 | 3/10 |
| dose2 | cuda | both | COMPLETE | 10/10 | 0.199961 | 0.381 | 1.14108 | 0.991454 | 0/10 | 0/10 | 0/10 | 3/10 | 3/10 |
| dose4 | cpu | none | COMPLETE | 10/10 | 0.13369 | 0.236973 | 0.612549 | 0.992143 | 0/10 | 0/10 | 0/10 | 0/10 | 0/10 |
| dose4 | cpu | global | COMPLETE | 10/10 | 0.133384 | 0.236561 | 0.609328 | 0.992142 | 0/10 | 0/10 | 0/10 | 0/10 | 0/10 |
| dose4 | cpu | local | COMPLETE | 10/10 | 0.13341 | 0.236528 | 0.61593 | 0.992158 | 0/10 | 0/10 | 0/10 | 0/10 | 0/10 |
| dose4 | cpu | both | COMPLETE | 10/10 | 0.133558 | 0.236306 | 0.61441 | 0.992151 | 0/10 | 0/10 | 0/10 | 0/10 | 0/10 |
| dose4 | cuda | none | COMPLETE | 10/10 | 0.132724 | 0.236051 | 0.618091 | 0.992114 | 0/10 | 0/10 | 0/10 | 0/10 | 0/10 |
| dose4 | cuda | global | COMPLETE | 10/10 | 0.132848 | 0.235733 | 0.612734 | 0.992139 | 0/10 | 0/10 | 0/10 | 0/10 | 0/10 |
| dose4 | cuda | local | COMPLETE | 10/10 | 0.133645 | 0.236716 | 0.619636 | 0.99212 | 0/10 | 0/10 | 0/10 | 0/10 | 0/10 |
| dose4 | cuda | both | COMPLETE | 10/10 | 0.133558 | 0.236306 | 0.614409 | 0.99215 | 0/10 | 0/10 | 0/10 | 0/10 | 0/10 |
| outmodel | cpu | none | PARTIAL: unmatched cohort | 4/10 | 1.04299 | 1.78563 | 3.15341 | 0.962953 | 0/4 | 0/4 | 0/4 | 4/4 | 4/4 |
| outmodel | cpu | global | PARTIAL: unmatched cohort | 4/10 | 1.04303 | 1.78565 | 3.15604 | 0.962963 | 0/4 | 0/4 | 0/4 | 4/4 | 4/4 |
| outmodel | cpu | local | PARTIAL: unmatched cohort | 3/10 | 1.05231 | 1.81156 | 3.15153 | 0.962326 | 0/3 | 0/3 | 0/3 | 3/3 | 3/3 |
| outmodel | cpu | both | PARTIAL: unmatched cohort | 3/10 | 1.05225 | 1.81192 | 3.15336 | 0.962342 | 0/3 | 0/3 | 0/3 | 3/3 | 3/3 |
| outmodel | cuda | none | COMPLETE | 10/10 | 1.0423 | 1.77814 | 3.15557 | 0.961376 | 0/10 | 0/10 | 0/10 | 10/10 | 10/10 |
| outmodel | cuda | global | COMPLETE | 10/10 | 1.04233 | 1.7782 | 3.15616 | 0.961393 | 0/10 | 0/10 | 0/10 | 10/10 | 10/10 |
| outmodel | cuda | local | COMPLETE | 10/10 | 1.0424 | 1.77825 | 3.1519 | 0.961377 | 0/10 | 0/10 | 0/10 | 10/10 | 10/10 |
| outmodel | cuda | both | COMPLETE | 10/10 | 1.04241 | 1.7783 | 3.15336 | 0.961395 | 0/10 | 0/10 | 0/10 | 10/10 | 10/10 |
| nonsquare | cpu | none | UNRUN | 0/10 | UNRUN | UNRUN | UNRUN | UNRUN | UNRUN | UNRUN | UNRUN | UNRUN | UNRUN |
| nonsquare | cpu | global | UNRUN | 0/10 | UNRUN | UNRUN | UNRUN | UNRUN | UNRUN | UNRUN | UNRUN | UNRUN | UNRUN |
| nonsquare | cpu | local | UNRUN | 0/10 | UNRUN | UNRUN | UNRUN | UNRUN | UNRUN | UNRUN | UNRUN | UNRUN | UNRUN |
| nonsquare | cpu | both | UNRUN | 0/10 | UNRUN | UNRUN | UNRUN | UNRUN | UNRUN | UNRUN | UNRUN | UNRUN | UNRUN |
| nonsquare | cuda | none | COMPLETE | 10/10 | 0.245605 | 0.461607 | 1.3246 | 0.990765 | 0/10 | 0/10 | 0/10 | 9/10 | 9/10 |
| nonsquare | cuda | global | COMPLETE | 10/10 | 0.245493 | 0.460438 | 1.32218 | 0.990737 | 0/10 | 0/10 | 0/10 | 9/10 | 9/10 |
| nonsquare | cuda | local | COMPLETE | 10/10 | 0.246162 | 0.4613 | 1.32531 | 0.990768 | 0/10 | 0/10 | 0/10 | 9/10 | 9/10 |
| nonsquare | cuda | both | COMPLETE | 10/10 | 0.246109 | 0.460831 | 1.32249 | 0.990735 | 0/10 | 0/10 | 0/10 | 9/10 | 9/10 |

## Frozen paired comparisons, all 240 retained

Labels and p-values are unadjusted exploratory results with no magnitude floor. Tests cover RMS, maximum field error and two transfer metrics, not every descriptive endpoint. Incomplete cells do not supply a complete10-seed inference.

| Condition | Backend | Arm vs none | Metric | Matched pairs / expected | Median delta | Exact p | Nominal label |
| --- | --- | --- | --- | ---: | ---: | ---: | --- |
| pedestal32 | cpu | global | rms | 10/10 | -0.892836 | 0.00195312 | nominal improves |
| pedestal32 | cpu | global | max | 10/10 | -2.0127 | 0.00195312 | nominal improves |
| pedestal32 | cpu | global | transfer | 10/10 | 0.0674538 | 0.00195312 | nominal improves |
| pedestal32 | cpu | global | transfer_top | 10/10 | 0.301328 | 0.00195312 | nominal improves |
| pedestal32 | cpu | local | rms | 10/10 | -0.644165 | 0.00195312 | nominal improves |
| pedestal32 | cpu | local | max | 10/10 | -1.46707 | 0.0214844 | nominal improves |
| pedestal32 | cpu | local | transfer | 10/10 | 0.0250147 | 0.34375 | neutral/mixed |
| pedestal32 | cpu | local | transfer_top | 10/10 | 0.0917278 | 0.34375 | neutral/mixed |
| pedestal32 | cpu | both | rms | 10/10 | -1.52259 | 0.00195312 | nominal improves |
| pedestal32 | cpu | both | max | 10/10 | -3.80769 | 0.00195312 | nominal improves |
| pedestal32 | cpu | both | transfer | 10/10 | 0.0654552 | 0.00195312 | nominal improves |
| pedestal32 | cpu | both | transfer_top | 10/10 | 0.29107 | 0.00195312 | nominal improves |
| pedestal32 | cuda | global | rms | 10/10 | -0.842397 | 0.00195312 | nominal improves |
| pedestal32 | cuda | global | max | 10/10 | -1.69683 | 0.00195312 | nominal improves |
| pedestal32 | cuda | global | transfer | 10/10 | 0.0639766 | 0.00195312 | nominal improves |
| pedestal32 | cuda | global | transfer_top | 10/10 | 0.331736 | 0.00195312 | nominal improves |
| pedestal32 | cuda | local | rms | 10/10 | -0.602522 | 0.109375 | neutral/mixed |
| pedestal32 | cuda | local | max | 10/10 | -1.83832 | 0.00195312 | nominal improves |
| pedestal32 | cuda | local | transfer | 10/10 | 0.0207179 | 0.34375 | neutral/mixed |
| pedestal32 | cuda | local | transfer_top | 10/10 | 0.0966327 | 0.34375 | neutral/mixed |
| pedestal32 | cuda | both | rms | 10/10 | -1.43781 | 0.00195312 | nominal improves |
| pedestal32 | cuda | both | max | 10/10 | -3.60322 | 0.00195312 | nominal improves |
| pedestal32 | cuda | both | transfer | 10/10 | 0.0611856 | 0.00195312 | nominal improves |
| pedestal32 | cuda | both | transfer_top | 10/10 | 0.313244 | 0.00195312 | nominal improves |
| pedestal0 | cpu | global | rms | 10/10 | 3.42282e-09 | 1 | neutral/mixed |
| pedestal0 | cpu | global | max | 10/10 | 2.33719e-07 | 0.34375 | neutral/mixed |
| pedestal0 | cpu | global | transfer | 10/10 | 1.19457e-09 | 0.34375 | neutral/mixed |
| pedestal0 | cpu | global | transfer_top | 10/10 | 9.91272e-09 | 0.34375 | neutral/mixed |
| pedestal0 | cpu | local | rms | 10/10 | -4.01473e-08 | 0.34375 | neutral/mixed |
| pedestal0 | cpu | local | max | 10/10 | -2.62592e-07 | 0.753906 | neutral/mixed |
| pedestal0 | cpu | local | transfer | 10/10 | 7.63636e-11 | 1 | neutral/mixed |
| pedestal0 | cpu | local | transfer_top | 10/10 | -1.60829e-09 | 0.753906 | neutral/mixed |
| pedestal0 | cpu | both | rms | 10/10 | -8.27968e-08 | 0.34375 | neutral/mixed |
| pedestal0 | cpu | both | max | 10/10 | -3.53163e-07 | 0.34375 | neutral/mixed |
| pedestal0 | cpu | both | transfer | 10/10 | 3.27475e-09 | 0.753906 | neutral/mixed |
| pedestal0 | cpu | both | transfer_top | 10/10 | 2.31906e-08 | 0.753906 | neutral/mixed |
| pedestal0 | cuda | global | rms | 10/10 | 5.0621e-08 | 0.34375 | neutral/mixed |
| pedestal0 | cuda | global | max | 10/10 | -5.17839e-07 | 0.34375 | neutral/mixed |
| pedestal0 | cuda | global | transfer | 10/10 | 6.19307e-09 | 0.753906 | neutral/mixed |
| pedestal0 | cuda | global | transfer_top | 10/10 | -1.69125e-07 | 0.34375 | neutral/mixed |
| pedestal0 | cuda | local | rms | 10/10 | 8.75354e-08 | 0.753906 | neutral/mixed |
| pedestal0 | cuda | local | max | 10/10 | 3.78839e-07 | 0.34375 | neutral/mixed |
| pedestal0 | cuda | local | transfer | 10/10 | 1.08248e-09 | 1 | neutral/mixed |
| pedestal0 | cuda | local | transfer_top | 10/10 | 1.84618e-08 | 1 | neutral/mixed |
| pedestal0 | cuda | both | rms | 10/10 | 1.77717e-08 | 1 | neutral/mixed |
| pedestal0 | cuda | both | max | 10/10 | -1.0236e-08 | 1 | neutral/mixed |
| pedestal0 | cuda | both | transfer | 10/10 | -1.58025e-09 | 0.753906 | neutral/mixed |
| pedestal0 | cuda | both | transfer_top | 10/10 | -2.60461e-08 | 1 | neutral/mixed |
| contrast025 | cpu | global | rms | 10/10 | -0.00387198 | 0.34375 | neutral/mixed |
| contrast025 | cpu | global | max | 10/10 | -0.0297068 | 0.0214844 | nominal improves |
| contrast025 | cpu | global | transfer | 10/10 | 7.45325e-05 | 0.109375 | neutral/mixed |
| contrast025 | cpu | global | transfer_top | 10/10 | 0.000684355 | 0.34375 | neutral/mixed |
| contrast025 | cpu | local | rms | 10/10 | -0.00524047 | 0.109375 | neutral/mixed |
| contrast025 | cpu | local | max | 10/10 | -0.0371786 | 0.109375 | neutral/mixed |
| contrast025 | cpu | local | transfer | 10/10 | 9.88422e-05 | 0.109375 | neutral/mixed |
| contrast025 | cpu | local | transfer_top | 10/10 | 0.00059401 | 0.109375 | neutral/mixed |
| contrast025 | cpu | both | rms | 10/10 | -0.0101412 | 0.0214844 | nominal improves |
| contrast025 | cpu | both | max | 10/10 | -0.0637171 | 0.00195312 | nominal improves |
| contrast025 | cpu | both | transfer | 10/10 | 8.12639e-05 | 0.34375 | neutral/mixed |
| contrast025 | cpu | both | transfer_top | 10/10 | 0.000816924 | 0.34375 | neutral/mixed |
| contrast025 | cuda | global | rms | 10/10 | 0.000202242 | 1 | neutral/mixed |
| contrast025 | cuda | global | max | 10/10 | -0.0153137 | 0.753906 | neutral/mixed |
| contrast025 | cuda | global | transfer | 10/10 | 6.52614e-05 | 0.753906 | neutral/mixed |
| contrast025 | cuda | global | transfer_top | 10/10 | 0.000117493 | 0.753906 | neutral/mixed |
| contrast025 | cuda | local | rms | 10/10 | 0.00310374 | 0.34375 | neutral/mixed |
| contrast025 | cuda | local | max | 10/10 | -0.0189778 | 0.753906 | neutral/mixed |
| contrast025 | cuda | local | transfer | 10/10 | 6.21661e-05 | 0.0214844 | nominal improves |
| contrast025 | cuda | local | transfer_top | 10/10 | 0.00046964 | 0.753906 | neutral/mixed |
| contrast025 | cuda | both | rms | 10/10 | 0.00203103 | 0.753906 | neutral/mixed |
| contrast025 | cuda | both | max | 10/10 | -0.01826 | 0.753906 | neutral/mixed |
| contrast025 | cuda | both | transfer | 10/10 | 0.000216078 | 0.34375 | neutral/mixed |
| contrast025 | cuda | both | transfer_top | 10/10 | 0.000675724 | 0.34375 | neutral/mixed |
| contrast4 | cpu | global | rms | 10/10 | 4.13663e-06 | 0.753906 | neutral/mixed |
| contrast4 | cpu | global | max | 10/10 | 3.61491e-05 | 0.753906 | neutral/mixed |
| contrast4 | cpu | global | transfer | 10/10 | -5.14288e-07 | 0.753906 | neutral/mixed |
| contrast4 | cpu | global | transfer_top | 10/10 | -1.42833e-06 | 0.753906 | neutral/mixed |
| contrast4 | cpu | local | rms | 10/10 | -2.44848e-05 | 0.34375 | neutral/mixed |
| contrast4 | cpu | local | max | 10/10 | -6.71192e-05 | 0.753906 | neutral/mixed |
| contrast4 | cpu | local | transfer | 10/10 | 2.67328e-07 | 0.34375 | neutral/mixed |
| contrast4 | cpu | local | transfer_top | 10/10 | 1.28595e-06 | 0.34375 | neutral/mixed |
| contrast4 | cpu | both | rms | 10/10 | -2.1012e-05 | 0.753906 | neutral/mixed |
| contrast4 | cpu | both | max | 10/10 | -9.0332e-05 | 0.753906 | neutral/mixed |
| contrast4 | cpu | both | transfer | 10/10 | -7.79216e-07 | 0.753906 | neutral/mixed |
| contrast4 | cpu | both | transfer_top | 10/10 | -1.7683e-06 | 0.753906 | neutral/mixed |
| contrast4 | cuda | global | rms | 10/10 | 1.26459e-06 | 0.34375 | neutral/mixed |
| contrast4 | cuda | global | max | 10/10 | 7.1821e-05 | 0.34375 | neutral/mixed |
| contrast4 | cuda | global | transfer | 10/10 | 7.53855e-07 | 0.109375 | neutral/mixed |
| contrast4 | cuda | global | transfer_top | 10/10 | 2.30497e-06 | 0.753906 | neutral/mixed |
| contrast4 | cuda | local | rms | 10/10 | -5.41351e-06 | 0.34375 | neutral/mixed |
| contrast4 | cuda | local | max | 10/10 | -9.62906e-05 | 0.34375 | neutral/mixed |
| contrast4 | cuda | local | transfer | 10/10 | 2.83614e-07 | 0.34375 | neutral/mixed |
| contrast4 | cuda | local | transfer_top | 10/10 | 9.5676e-07 | 0.34375 | neutral/mixed |
| contrast4 | cuda | both | rms | 10/10 | 3.68199e-06 | 1 | neutral/mixed |
| contrast4 | cuda | both | max | 10/10 | -4.6041e-05 | 0.753906 | neutral/mixed |
| contrast4 | cuda | both | transfer | 10/10 | 9.56179e-07 | 0.34375 | neutral/mixed |
| contrast4 | cuda | both | transfer_top | 10/10 | 1.18911e-06 | 0.0214844 | nominal improves |
| dose1 | cpu | global | rms | 10/10 | -0.000238246 | 0.753906 | neutral/mixed |
| dose1 | cpu | global | max | 10/10 | -0.000358142 | 0.34375 | neutral/mixed |
| dose1 | cpu | global | transfer | 10/10 | 7.46452e-06 | 0.0214844 | nominal improves |
| dose1 | cpu | global | transfer_top | 10/10 | 3.35524e-05 | 0.0214844 | nominal improves |
| dose1 | cpu | local | rms | 10/10 | -1.93251e-05 | 1 | neutral/mixed |
| dose1 | cpu | local | max | 10/10 | 0.00116451 | 0.753906 | neutral/mixed |
| dose1 | cpu | local | transfer | 10/10 | -1.11395e-07 | 1 | neutral/mixed |
| dose1 | cpu | local | transfer_top | 10/10 | -2.98221e-06 | 0.753906 | neutral/mixed |
| dose1 | cpu | both | rms | 10/10 | -4.164e-05 | 0.753906 | neutral/mixed |
| dose1 | cpu | both | max | 10/10 | -0.000357367 | 1 | neutral/mixed |
| dose1 | cpu | both | transfer | 10/10 | 1.1394e-05 | 0.753906 | neutral/mixed |
| dose1 | cpu | both | transfer_top | 10/10 | 2.90514e-05 | 0.34375 | neutral/mixed |
| dose1 | cuda | global | rms | 10/10 | 1.15162e-05 | 1 | neutral/mixed |
| dose1 | cuda | global | max | 10/10 | 0.000156811 | 1 | neutral/mixed |
| dose1 | cuda | global | transfer | 10/10 | -4.64467e-06 | 0.753906 | neutral/mixed |
| dose1 | cuda | global | transfer_top | 10/10 | 5.34882e-06 | 0.753906 | neutral/mixed |
| dose1 | cuda | local | rms | 10/10 | 0.000279875 | 0.109375 | neutral/mixed |
| dose1 | cuda | local | max | 10/10 | 0.000604351 | 0.753906 | neutral/mixed |
| dose1 | cuda | local | transfer | 10/10 | -3.5306e-07 | 1 | neutral/mixed |
| dose1 | cuda | local | transfer_top | 10/10 | 8.14443e-06 | 0.753906 | neutral/mixed |
| dose1 | cuda | both | rms | 10/10 | 0.000176751 | 0.753906 | neutral/mixed |
| dose1 | cuda | both | max | 10/10 | -0.000535022 | 1 | neutral/mixed |
| dose1 | cuda | both | transfer | 10/10 | -1.59173e-05 | 0.34375 | neutral/mixed |
| dose1 | cuda | both | transfer_top | 10/10 | -2.32104e-05 | 0.753906 | neutral/mixed |
| dose05 | cpu | global | rms | 10/10 | 2.02583e-05 | 1 | neutral/mixed |
| dose05 | cpu | global | max | 10/10 | 0.000146642 | 0.753906 | neutral/mixed |
| dose05 | cpu | global | transfer | 10/10 | 3.17482e-06 | 0.753906 | neutral/mixed |
| dose05 | cpu | global | transfer_top | 10/10 | 1.20097e-05 | 0.753906 | neutral/mixed |
| dose05 | cpu | local | rms | 10/10 | -0.000157991 | 0.753906 | neutral/mixed |
| dose05 | cpu | local | max | 10/10 | -0.00100961 | 0.0214844 | nominal improves |
| dose05 | cpu | local | transfer | 10/10 | 3.96816e-06 | 0.753906 | neutral/mixed |
| dose05 | cpu | local | transfer_top | 10/10 | 8.98014e-06 | 1 | neutral/mixed |
| dose05 | cpu | both | rms | 10/10 | 5.71889e-05 | 1 | neutral/mixed |
| dose05 | cpu | both | max | 10/10 | -0.000557544 | 0.753906 | neutral/mixed |
| dose05 | cpu | both | transfer | 10/10 | -2.77419e-06 | 0.753906 | neutral/mixed |
| dose05 | cpu | both | transfer_top | 10/10 | 2.03305e-05 | 0.753906 | neutral/mixed |
| dose05 | cuda | global | rms | 10/10 | 0.000329041 | 0.753906 | neutral/mixed |
| dose05 | cuda | global | max | 10/10 | 0.000181803 | 1 | neutral/mixed |
| dose05 | cuda | global | transfer | 10/10 | -2.23045e-05 | 0.753906 | neutral/mixed |
| dose05 | cuda | global | transfer_top | 10/10 | -0.000168424 | 0.753906 | neutral/mixed |
| dose05 | cuda | local | rms | 10/10 | -0.000291263 | 0.34375 | neutral/mixed |
| dose05 | cuda | local | max | 10/10 | -0.000609369 | 1 | neutral/mixed |
| dose05 | cuda | local | transfer | 10/10 | 7.79083e-07 | 1 | neutral/mixed |
| dose05 | cuda | local | transfer_top | 10/10 | 9.82886e-06 | 0.753906 | neutral/mixed |
| dose05 | cuda | both | rms | 10/10 | 0.000133271 | 0.753906 | neutral/mixed |
| dose05 | cuda | both | max | 10/10 | 4.55653e-05 | 1 | neutral/mixed |
| dose05 | cuda | both | transfer | 10/10 | -2.2335e-05 | 0.34375 | neutral/mixed |
| dose05 | cuda | both | transfer_top | 10/10 | -0.000106278 | 0.34375 | neutral/mixed |
| dose2 | cpu | global | rms | 10/10 | -0.000198718 | 0.753906 | neutral/mixed |
| dose2 | cpu | global | max | 10/10 | -0.00028855 | 0.753906 | neutral/mixed |
| dose2 | cpu | global | transfer | 10/10 | 1.1013e-06 | 1 | neutral/mixed |
| dose2 | cpu | global | transfer_top | 10/10 | 1.05529e-06 | 1 | neutral/mixed |
| dose2 | cpu | local | rms | 10/10 | 6.84349e-05 | 0.753906 | neutral/mixed |
| dose2 | cpu | local | max | 10/10 | 0.00207863 | 0.34375 | neutral/mixed |
| dose2 | cpu | local | transfer | 10/10 | 1.70248e-06 | 0.753906 | neutral/mixed |
| dose2 | cpu | local | transfer_top | 10/10 | 5.24374e-06 | 1 | neutral/mixed |
| dose2 | cpu | both | rms | 10/10 | 0.00024501 | 0.753906 | neutral/mixed |
| dose2 | cpu | both | max | 10/10 | 0.00229048 | 0.109375 | neutral/mixed |
| dose2 | cpu | both | transfer | 10/10 | -2.32932e-06 | 1 | neutral/mixed |
| dose2 | cpu | both | transfer_top | 10/10 | 1.76184e-06 | 1 | neutral/mixed |
| dose2 | cuda | global | rms | 10/10 | 0.000125498 | 1 | neutral/mixed |
| dose2 | cuda | global | max | 10/10 | -0.000208954 | 0.34375 | neutral/mixed |
| dose2 | cuda | global | transfer | 10/10 | 3.42656e-06 | 0.34375 | neutral/mixed |
| dose2 | cuda | global | transfer_top | 10/10 | 9.18446e-06 | 0.753906 | neutral/mixed |
| dose2 | cuda | local | rms | 10/10 | 0.000298464 | 0.109375 | neutral/mixed |
| dose2 | cuda | local | max | 10/10 | 0.00203588 | 0.109375 | neutral/mixed |
| dose2 | cuda | local | transfer | 10/10 | 1.08618e-07 | 1 | neutral/mixed |
| dose2 | cuda | local | transfer_top | 10/10 | -6.66436e-07 | 1 | neutral/mixed |
| dose2 | cuda | both | rms | 10/10 | 0.000396909 | 0.109375 | neutral/mixed |
| dose2 | cuda | both | max | 10/10 | 0.00189187 | 0.109375 | neutral/mixed |
| dose2 | cuda | both | transfer | 10/10 | 7.32307e-06 | 0.753906 | neutral/mixed |
| dose2 | cuda | both | transfer_top | 10/10 | 3.60983e-06 | 1 | neutral/mixed |
| dose4 | cpu | global | rms | 10/10 | -0.000195662 | 0.00195312 | nominal improves |
| dose4 | cpu | global | max | 10/10 | 9.2394e-05 | 1 | neutral/mixed |
| dose4 | cpu | global | transfer | 10/10 | 8.16412e-06 | 0.753906 | neutral/mixed |
| dose4 | cpu | global | transfer_top | 10/10 | 5.15255e-05 | 0.34375 | neutral/mixed |
| dose4 | cpu | local | rms | 10/10 | -9.54919e-05 | 0.753906 | neutral/mixed |
| dose4 | cpu | local | max | 10/10 | -0.00153963 | 0.34375 | neutral/mixed |
| dose4 | cpu | local | transfer | 10/10 | 8.58094e-06 | 0.109375 | neutral/mixed |
| dose4 | cpu | local | transfer_top | 10/10 | 4.44196e-05 | 0.109375 | neutral/mixed |
| dose4 | cpu | both | rms | 10/10 | -0.000341402 | 0.34375 | neutral/mixed |
| dose4 | cpu | both | max | 10/10 | 9.86432e-05 | 1 | neutral/mixed |
| dose4 | cpu | both | transfer | 10/10 | 7.50602e-06 | 0.109375 | neutral/mixed |
| dose4 | cpu | both | transfer_top | 10/10 | 4.5802e-05 | 0.109375 | neutral/mixed |
| dose4 | cuda | global | rms | 10/10 | 8.70138e-05 | 0.753906 | neutral/mixed |
| dose4 | cuda | global | max | 10/10 | 0.000344222 | 0.753906 | neutral/mixed |
| dose4 | cuda | global | transfer | 10/10 | 4.44195e-06 | 0.34375 | neutral/mixed |
| dose4 | cuda | global | transfer_top | 10/10 | 2.58733e-05 | 0.34375 | neutral/mixed |
| dose4 | cuda | local | rms | 10/10 | 0.000208542 | 0.753906 | neutral/mixed |
| dose4 | cuda | local | max | 10/10 | 0.00160302 | 0.34375 | neutral/mixed |
| dose4 | cuda | local | transfer | 10/10 | -1.49282e-06 | 0.753906 | neutral/mixed |
| dose4 | cuda | local | transfer_top | 10/10 | -7.02531e-06 | 0.753906 | neutral/mixed |
| dose4 | cuda | both | rms | 10/10 | 0.000102667 | 1 | neutral/mixed |
| dose4 | cuda | both | max | 10/10 | 0.00186218 | 0.753906 | neutral/mixed |
| dose4 | cuda | both | transfer | 10/10 | 7.12668e-06 | 0.753906 | neutral/mixed |
| dose4 | cuda | both | transfer_top | 10/10 | 4.75726e-05 | 0.753906 | neutral/mixed |
| outmodel | cpu | global | rms | 4/10 | 4.33736e-05 | 0.625 | IN_PROGRESS |
| outmodel | cpu | global | max | 4/10 | 0.000273862 | 1 | IN_PROGRESS |
| outmodel | cpu | global | transfer | 4/10 | 9.91792e-06 | 0.625 | IN_PROGRESS |
| outmodel | cpu | global | transfer_top | 4/10 | 6.50797e-05 | 0.625 | IN_PROGRESS |
| outmodel | cpu | local | rms | 3/10 | -0.000228176 | 0.25 | IN_PROGRESS |
| outmodel | cpu | local | max | 3/10 | -0.00187241 | 0.25 | IN_PROGRESS |
| outmodel | cpu | local | transfer | 3/10 | -2.75488e-06 | 1 | IN_PROGRESS |
| outmodel | cpu | local | transfer_top | 3/10 | -1.50307e-05 | 1 | IN_PROGRESS |
| outmodel | cpu | both | rms | 3/10 | -0.000222932 | 1 | IN_PROGRESS |
| outmodel | cpu | both | max | 3/10 | -4.2248e-05 | 0.25 | IN_PROGRESS |
| outmodel | cpu | both | transfer | 3/10 | 1.31158e-05 | 1 | IN_PROGRESS |
| outmodel | cpu | both | transfer_top | 3/10 | 5.94343e-05 | 1 | IN_PROGRESS |
| outmodel | cuda | global | rms | 10/10 | 2.66429e-05 | 0.0214844 | nominal harms |
| outmodel | cuda | global | max | 10/10 | 0.000114494 | 1 | neutral/mixed |
| outmodel | cuda | global | transfer | 10/10 | 9.36799e-06 | 0.34375 | neutral/mixed |
| outmodel | cuda | global | transfer_top | 10/10 | 3.55379e-05 | 0.34375 | neutral/mixed |
| outmodel | cuda | local | rms | 10/10 | -0.000134472 | 0.109375 | neutral/mixed |
| outmodel | cuda | local | max | 10/10 | -0.00088659 | 0.34375 | neutral/mixed |
| outmodel | cuda | local | transfer | 10/10 | 1.24948e-05 | 0.109375 | neutral/mixed |
| outmodel | cuda | local | transfer_top | 10/10 | 6.13376e-05 | 0.34375 | neutral/mixed |
| outmodel | cuda | both | rms | 10/10 | -0.000106107 | 0.34375 | neutral/mixed |
| outmodel | cuda | both | max | 10/10 | -0.000777591 | 0.34375 | neutral/mixed |
| outmodel | cuda | both | transfer | 10/10 | 1.98567e-05 | 0.00195312 | nominal improves |
| outmodel | cuda | both | transfer_top | 10/10 | 0.000101869 | 0.0214844 | nominal improves |
| nonsquare | cpu | global | rms | 0/10 | UNRUN | UNRUN | UNRUN |
| nonsquare | cpu | global | max | 0/10 | UNRUN | UNRUN | UNRUN |
| nonsquare | cpu | global | transfer | 0/10 | UNRUN | UNRUN | UNRUN |
| nonsquare | cpu | global | transfer_top | 0/10 | UNRUN | UNRUN | UNRUN |
| nonsquare | cpu | local | rms | 0/10 | UNRUN | UNRUN | UNRUN |
| nonsquare | cpu | local | max | 0/10 | UNRUN | UNRUN | UNRUN |
| nonsquare | cpu | local | transfer | 0/10 | UNRUN | UNRUN | UNRUN |
| nonsquare | cpu | local | transfer_top | 0/10 | UNRUN | UNRUN | UNRUN |
| nonsquare | cpu | both | rms | 0/10 | UNRUN | UNRUN | UNRUN |
| nonsquare | cpu | both | max | 0/10 | UNRUN | UNRUN | UNRUN |
| nonsquare | cpu | both | transfer | 0/10 | UNRUN | UNRUN | UNRUN |
| nonsquare | cpu | both | transfer_top | 0/10 | UNRUN | UNRUN | UNRUN |
| nonsquare | cuda | global | rms | 10/10 | -0.000259869 | 0.34375 | neutral/mixed |
| nonsquare | cuda | global | max | 10/10 | -0.000486636 | 1 | neutral/mixed |
| nonsquare | cuda | global | transfer | 10/10 | -1.29728e-05 | 0.34375 | neutral/mixed |
| nonsquare | cuda | global | transfer_top | 10/10 | -5.4224e-05 | 0.34375 | neutral/mixed |
| nonsquare | cuda | local | rms | 10/10 | -6.6002e-05 | 0.34375 | neutral/mixed |
| nonsquare | cuda | local | max | 10/10 | -9.90061e-06 | 1 | neutral/mixed |
| nonsquare | cuda | local | transfer | 10/10 | 1.22742e-06 | 1 | neutral/mixed |
| nonsquare | cuda | local | transfer_top | 10/10 | -1.55372e-06 | 1 | neutral/mixed |
| nonsquare | cuda | both | rms | 10/10 | -9.76664e-05 | 1 | neutral/mixed |
| nonsquare | cuda | both | max | 10/10 | -0.00122966 | 0.34375 | neutral/mixed |
| nonsquare | cuda | both | transfer | 10/10 | -9.86404e-06 | 0.109375 | neutral/mixed |
| nonsquare | cuda | both | transfer_top | 10/10 | -7.82497e-05 | 0.109375 | neutral/mixed |

## Partial outmodel CPU, common seeds only

The original per-arm cohorts have4/4/3/3 observations. On common seeds00–02 only, the medians below avoid that cohort mismatch. No new hypothesis test or acceptance gate is defined.

| Arm | Common groups | Median RMS px |
| --- | --- | ---: |
| none | outmodel-s00, outmodel-s01, outmodel-s02 | 1.052634 |
| global | outmodel-s00, outmodel-s01, outmodel-s02 | 1.052718 |
| local | outmodel-s00, outmodel-s01, outmodel-s02 | 1.052310 |
| both | outmodel-s00, outmodel-s01, outmodel-s02 | 1.052250 |

## Interpretation and limits

- Frozen category counts:30 nominal improves,1 nominal harms,185 neutral/mixed,12 IN_PROGRESS,12 UNRUN. All878 per-seed regressions remain in the original JSON;685 are below1e-3 in their metric units. Magnitudes are descriptive, not a newly adopted floor. Without correctness replicates, small CUDA deltas cannot be attributed to arm effects versus run variation.
- The single harms label is outmodel CUDA global RMS: median+2.664e-5px on a roughly1.04px field,9 losses/1 win,p=.021484375,no failure transition. No calibrated harm claim follows.
- At n10 the minimum two-sided sign p is.001953125. None survives Bonferroni across216 complete comparisons. The reviewer reports21 BH q<.05 entries; dependence assumptions are unvalidated, so no adjusted-inference conclusion is adopted. Fixed-scene/correlated conditions do not by themselves prove violation of every positive-dependence condition. The hypothetical independent-all-null expected4.6 nominal hits is not this experiment's calibrated null model.
- Pedestal32 both improves the descriptive medians and global/local convergence counts. For EACH backend, none→both global nonconvergence10→0, local-disabled10→0, field-distance FAIL10→9, failure union10→9. The union's fixed1/new0 hides the component changes;9/10 field failures remain. Local-only has real per-seed regressions and is mixed.
- Seed draws vary Poisson noise, not scene or motion-field identity. Results do not generalize to other scenes/motions or held-out science. No none-vs-none correctness replicate exists here. Timing/cost and Tier C are not evaluated by this snapshot.
- Frozen failure handling has a latent issue for non-EVALUATED records (review F8); none occurs among these734 experiment records. A separately versioned fix is required before a full-campaign summary, without changing this receipt. There is no adoption-ready M3 packet.
