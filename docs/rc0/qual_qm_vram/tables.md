### Main matrix (free VRAM measured after the balloon, GPU1)

| Movie | Config | `--ingest` | free GiB (nominal) | exit | route | wall s | products vs unconstrained | outcome |
|---|---|---|---:|---:|---|---:|---|---|
| e10216 | G | auto | 40.0 | 0 | compact | 2.3 | identical | OK compact |
| e10216 | G | auto | 24.0 | 0 | compact | 2.3 | identical | OK compact |
| e10216 | G | auto | 16.0 | 0 | compact | 2.3 | identical | OK compact |
| e10216 | L | auto | 40.0 | 0 | compact | 2.8 | identical | OK compact |
| e10216 | L | auto | 24.0 | 0 | compact | 2.8 | identical | OK compact |
| e10216 | L | auto | 16.0 | 0 | compact | 2.8 | identical | OK compact |
| e10361 | G | auto | 16.0 | 0 | compact | 3.3 | identical | OK compact |
| e10361 | L | auto | 16.0 | 0 | compact | 3.5 | identical | OK compact |
| e10441 | G | auto | 40.0 | 0 | compact | 8.7 | identical | OK compact |
| e10441 | G | auto | 24.0 | 0 | float | 59.6 | identical | OK streaming (session declined) |
| e10441 | G | auto | 16.0 | 1 | float | 29.3 | no products | FAIL (streaming OOM) |
| e10441 | G | compact | 40.0 | 0 | compact | 7.4 | identical | OK compact |
| e10441 | G | compact | 24.0 | 1 | — | 1.1 | no products | FAIL-FAST (pinned compact refused) |
| e10441 | G | compact | 16.0 | 1 | — | 1.1 | no products | FAIL-FAST (pinned compact refused) |
| e10441 | G | float | 40.0 | 0 | float | 12.1 | identical | OK float |
| e10441 | G | float | 24.0 | 0 | float | 53.5 | identical | OK streaming (session declined) |
| e10441 | G | float | 16.0 | 1 | float | 28.7 | no products | FAIL (streaming OOM) |
| e10441 | L | auto | 40.0 | 0 | compact | 8.6 | identical | OK compact |
| e10441 | L | auto | 24.0 | 0 | float | 69.1 | identical | OK streaming (session declined) |
| e10441 | L | auto | 16.0 | 1 | float | 30.9 | no products | FAIL (streaming OOM) |
| e10441 | L | compact | 40.0 | 0 | compact | 7.9 | identical | OK compact |
| e10441 | L | compact | 24.0 | 1 | — | 1.1 | no products | FAIL-FAST (pinned compact refused) |
| e10441 | L | compact | 16.0 | 1 | — | 1.1 | no products | FAIL-FAST (pinned compact refused) |
| e10441 | L | float | 40.0 | 0 | float | 12.4 | identical | OK float |
| e10441 | L | float | 24.0 | 0 | float | 64.1 | identical | OK streaming (session declined) |
| e10441 | L | float | 16.0 | 1 | float | 27.8 | no products | FAIL (streaming OOM) |
| e10474f4 | G | auto | 40.0 | 0 | compact | 12.0 | identical | OK compact |
| e10474f4 | G | auto | 24.0 | 0 | compact | 11.8 | identical | OK compact |
| e10474f4 | G | auto | 16.0 | 0 | float | 38.2 | identical | OK streaming (session declined) |
| e10474f4 | L | auto | 40.0 | 0 | compact | 12.3 | identical | OK compact |
| e10474f4 | L | auto | 24.0 | 0 | compact | 12.2 | identical | OK compact |
| e10474f4 | L | auto | 16.0 | 0 | float | 42.3 | identical | OK streaming (session declined) |
| tutorial | G | auto | 40.0 | 0 | nvcomp | 1.2 | identical | OK nvcomp |
| tutorial | G | auto | 24.0 | 0 | nvcomp | 1.1 | identical | OK nvcomp |
| tutorial | G | auto | 16.0 | 0 | nvcomp | 1.1 | identical | OK nvcomp |
| tutorial | L | auto | 40.0 | 0 | nvcomp | 1.3 | identical | OK nvcomp |
| tutorial | L | auto | 24.0 | 0 | nvcomp | 1.3 | identical | OK nvcomp |
| tutorial | L | auto | 16.0 | 0 | nvcomp | 1.2 | identical | OK nvcomp |

### All constrained probes (main matrix, bisection and scan runs)

Free VRAM in GiB measured after the balloon; outcome as above. `ident` = corrected image, motion STAR and joint STAR identical to the unconstrained run (products-only comparison).

**e10216 G --ingest auto**

| free GiB | exit | route | wall s | host RSS GiB | ident | outcome |
|---:|---:|---|---:|---:|---|---|
| 1.00 | 1 | float | 6.6 | 7.5 | n/a | FAIL (streaming OOM) |
| 3.00 | 1 | float | 6.5 | 7.5 | n/a | FAIL (streaming OOM) |
| 4.00 | 1 | float | 6.6 | 7.5 | n/a | FAIL (streaming OOM) |
| 4.00 | 1 | float | 6.5 | 7.5 | n/a | FAIL (streaming OOM) |
| 5.00 | 0 | float | 12.0 | 7.6 | yes | OK streaming (session declined) |
| 7.00 | 0 | float | 12.0 | 7.6 | yes | OK streaming (session declined) |
| 7.50 | 0 | float | 12.0 | 7.6 | yes | OK streaming (session declined) |
| 8.00 | 0 | compact | 13.8 | 7.6 | yes | OK degraded: CPU-preprocess |
| 8.25 | 0 | compact | 2.1 | 2.1 | yes | OK compact |
| 8.50 | 0 | compact | 2.1 | 2.1 | yes | OK compact |
| 8.50 | 0 | compact | 2.1 | 2.1 | yes | OK compact |
| 10.00 | 0 | compact | 2.2 | 2.1 | yes | OK compact |
| 16.00 | 0 | compact | 2.3 | 2.1 | yes | OK compact |
| 16.00 | 0 | compact | 2.3 | 2.1 | yes | OK compact |
| 24.00 | 0 | compact | 2.3 | 2.1 | yes | OK compact |
| 40.00 | 0 | compact | 2.3 | 2.1 | yes | OK compact |

**e10216 L --ingest auto**

| free GiB | exit | route | wall s | host RSS GiB | ident | outcome |
|---:|---:|---|---:|---:|---|---|
| 1.00 | 1 | float | 6.7 | 7.5 | n/a | FAIL (streaming OOM) |
| 4.00 | 1 | float | 6.6 | 7.5 | n/a | FAIL (streaming OOM) |
| 4.00 | 1 | float | 6.7 | 7.5 | n/a | FAIL (streaming OOM) |
| 5.00 | 0 | float | 13.8 | 7.7 | yes | OK streaming (session declined) |
| 5.50 | 0 | float | 13.8 | 7.7 | yes | OK streaming (session declined) |
| 7.00 | 0 | float | 13.8 | 7.7 | yes | OK streaming (session declined) |
| 7.00 | 0 | float | 14.0 | 7.7 | yes | OK streaming (session declined) |
| 7.50 | 0 | float | 13.9 | 7.7 | yes | OK streaming (session declined) |
| 8.00 | 0 | compact | 15.7 | 7.7 | yes | OK degraded: CPU-preprocess |
| 8.50 | 1 | compact | 5.6 | 4.0 | n/a | FAIL (session admitted, patch-stage OOM) |
| 8.50 | 1 | compact | 5.7 | 4.0 | n/a | FAIL (session admitted, patch-stage OOM) |
| 8.75 | 0 | compact | 2.6 | 2.1 | yes | OK compact |
| 9.00 | 0 | compact | 2.7 | 2.1 | yes | OK compact |
| 10.00 | 0 | compact | 2.7 | 2.1 | yes | OK compact |
| 16.00 | 0 | compact | 2.8 | 2.1 | yes | OK compact |
| 16.00 | 0 | compact | 2.7 | 2.1 | yes | OK compact |
| 24.00 | 0 | compact | 2.8 | 2.1 | yes | OK compact |
| 40.00 | 0 | compact | 2.8 | 2.1 | yes | OK compact |

**e10361 G --ingest auto**

| free GiB | exit | route | wall s | host RSS GiB | ident | outcome |
|---:|---:|---|---:|---:|---|---|
| 16.00 | 0 | compact | 3.3 | 1.5 | yes | OK compact |

**e10361 L --ingest auto**

| free GiB | exit | route | wall s | host RSS GiB | ident | outcome |
|---:|---:|---|---:|---:|---|---|
| 16.00 | 0 | compact | 3.5 | 1.5 | yes | OK compact |

**e10441 G --ingest auto**

| free GiB | exit | route | wall s | host RSS GiB | ident | outcome |
|---:|---:|---|---:|---:|---|---|
| 16.00 | 1 | float | 29.3 | 35.7 | n/a | FAIL (streaming OOM) |
| 16.00 | 1 | float | 28.0 | 35.7 | n/a | FAIL (streaming OOM) |
| 20.00 | 1 | float | 30.2 | 35.7 | n/a | FAIL (streaming OOM) |
| 21.00 | 1 | float | 29.9 | 35.7 | n/a | FAIL (streaming OOM) |
| 22.00 | 0 | float | 52.9 | 36.0 | yes | OK streaming (session declined) |
| 24.00 | 0 | float | 59.6 | 36.0 | yes | OK streaming (session declined) |
| 24.00 | 0 | float | 56.6 | 36.0 | yes | OK streaming (session declined) |
| 24.00 | 0 | float | 56.3 | 36.0 | yes | OK streaming (session declined) |
| 32.00 | 0 | float | 56.8 | 36.0 | yes | OK streaming (session declined) |
| 36.00 | 0 | float | 60.2 | 36.0 | yes | OK streaming (session declined) |
| 36.50 | 0 | float | 58.3 | 36.0 | yes | OK streaming (session declined) |
| 37.00 | 0 | compact | 60.0 | 36.0 | yes | OK degraded: CPU-preprocess |
| 37.50 | 0 | compact | 7.4 | 5.0 | yes | OK compact |
| 38.00 | 0 | compact | 7.2 | 5.0 | yes | OK compact |
| 40.00 | 0 | compact | 8.7 | 5.0 | yes | OK compact |
| 40.00 | 0 | compact | 7.3 | 5.0 | yes | OK compact |

**e10441 G --ingest compact**

| free GiB | exit | route | wall s | host RSS GiB | ident | outcome |
|---:|---:|---|---:|---:|---|---|
| 16.00 | 1 | — | 1.1 | 0.7 | n/a | FAIL-FAST (pinned compact refused) |
| 24.00 | 1 | — | 1.1 | 0.7 | n/a | FAIL-FAST (pinned compact refused) |
| 40.00 | 0 | compact | 7.4 | 5.0 | yes | OK compact |

**e10441 G --ingest float**

| free GiB | exit | route | wall s | host RSS GiB | ident | outcome |
|---:|---:|---|---:|---:|---|---|
| 16.00 | 1 | float | 28.7 | 35.7 | n/a | FAIL (streaming OOM) |
| 24.00 | 0 | float | 53.5 | 36.0 | yes | OK streaming (session declined) |
| 40.00 | 0 | float | 12.1 | 18.5 | yes | OK float |

**e10441 L --ingest auto**

| free GiB | exit | route | wall s | host RSS GiB | ident | outcome |
|---:|---:|---|---:|---:|---|---|
| 16.00 | 1 | float | 30.9 | 35.7 | n/a | FAIL (streaming OOM) |
| 16.00 | 1 | float | 28.4 | 35.7 | n/a | FAIL (streaming OOM) |
| 20.00 | 1 | float | 30.9 | 35.7 | n/a | FAIL (streaming OOM) |
| 21.00 | 1 | float | 31.7 | 35.7 | n/a | FAIL (streaming OOM) |
| 22.00 | 0 | float | 65.7 | 36.4 | yes | OK streaming (session declined) |
| 24.00 | 0 | float | 69.1 | 36.4 | yes | OK streaming (session declined) |
| 24.00 | 0 | float | 61.7 | 36.4 | yes | OK streaming (session declined) |
| 24.00 | 0 | float | 65.1 | 36.4 | yes | OK streaming (session declined) |
| 32.00 | 0 | float | 66.5 | 36.4 | yes | OK streaming (session declined) |
| 36.00 | 0 | float | 65.9 | 36.4 | yes | OK streaming (session declined) |
| 36.50 | 0 | float | 66.4 | 36.4 | yes | OK streaming (session declined) |
| 37.00 | 0 | compact | 68.2 | 36.4 | yes | OK degraded: CPU-preprocess |
| 37.50 | 1 | compact | 22.8 | 18.9 | n/a | FAIL (session admitted, patch-stage OOM) |
| 38.00 | 1 | compact | 22.9 | 18.9 | n/a | FAIL (session admitted, patch-stage OOM) |
| 38.50 | 1 | compact | 22.8 | 18.9 | n/a | FAIL (session admitted, patch-stage OOM) |
| 39.00 | 0 | compact | 7.6 | 5.0 | yes | OK compact |
| 40.00 | 0 | compact | 8.6 | 5.0 | yes | OK compact |
| 40.00 | 0 | compact | 7.5 | 5.0 | yes | OK compact |

**e10441 L --ingest compact**

| free GiB | exit | route | wall s | host RSS GiB | ident | outcome |
|---:|---:|---|---:|---:|---|---|
| 16.00 | 1 | — | 1.1 | 0.7 | n/a | FAIL-FAST (pinned compact refused) |
| 24.00 | 1 | — | 1.1 | 0.7 | n/a | FAIL-FAST (pinned compact refused) |
| 40.00 | 0 | compact | 7.9 | 5.0 | yes | OK compact |

**e10441 L --ingest float**

| free GiB | exit | route | wall s | host RSS GiB | ident | outcome |
|---:|---:|---|---:|---:|---|---|
| 16.00 | 1 | float | 27.8 | 35.7 | n/a | FAIL (streaming OOM) |
| 24.00 | 0 | float | 64.1 | 36.4 | yes | OK streaming (session declined) |
| 40.00 | 0 | float | 12.4 | 18.5 | yes | OK float |

**e10474f4 G --ingest auto**

| free GiB | exit | route | wall s | host RSS GiB | ident | outcome |
|---:|---:|---|---:|---:|---|---|
| 2.00 | 1 | float | 22.2 | 20.9 | n/a | FAIL (streaming OOM) |
| 9.00 | 1 | float | 23.2 | 20.9 | n/a | FAIL (streaming OOM) |
| 11.00 | 1 | float | 24.2 | 20.9 | n/a | FAIL (streaming OOM) |
| 12.00 | 0 | float | 37.4 | 21.0 | yes | OK streaming (session declined) |
| 12.50 | 0 | float | 37.1 | 21.0 | yes | OK streaming (session declined) |
| 16.00 | 0 | float | 38.2 | 21.0 | yes | OK streaming (session declined) |
| 16.00 | 0 | float | 37.4 | 21.0 | yes | OK streaming (session declined) |
| 16.00 | 0 | float | 36.7 | 21.0 | yes | OK streaming (session declined) |
| 18.00 | 0 | float | 37.2 | 21.0 | yes | OK streaming (session declined) |
| 18.50 | 0 | float | 35.0 | 21.0 | yes | OK streaming (session declined) |
| 19.00 | 0 | compact | 11.4 | 7.4 | yes | OK compact |
| 20.00 | 0 | compact | 11.3 | 7.4 | yes | OK compact |
| 24.00 | 0 | compact | 11.8 | 7.4 | yes | OK compact |
| 24.00 | 0 | compact | 11.3 | 7.4 | yes | OK compact |
| 40.00 | 0 | compact | 12.0 | 7.4 | yes | OK compact |

**e10474f4 L --ingest auto**

| free GiB | exit | route | wall s | host RSS GiB | ident | outcome |
|---:|---:|---|---:|---:|---|---|
| 2.00 | 1 | float | 22.5 | 20.9 | n/a | FAIL (streaming OOM) |
| 9.00 | 1 | float | 22.2 | 20.9 | n/a | FAIL (streaming OOM) |
| 11.00 | 1 | float | 23.8 | 20.9 | n/a | FAIL (streaming OOM) |
| 12.00 | 0 | float | 42.5 | 21.3 | yes | OK streaming (session declined) |
| 12.50 | 0 | float | 41.1 | 21.3 | yes | OK streaming (session declined) |
| 16.00 | 0 | float | 42.3 | 21.3 | yes | OK streaming (session declined) |
| 16.00 | 0 | float | 41.0 | 21.3 | yes | OK streaming (session declined) |
| 16.00 | 0 | float | 43.5 | 21.3 | yes | OK streaming (session declined) |
| 18.00 | 0 | float | 41.5 | 21.3 | yes | OK streaming (session declined) |
| 18.50 | 0 | float | 39.0 | 21.3 | yes | OK streaming (session declined) |
| 19.00 | 1 | compact | 19.9 | 12.3 | n/a | FAIL (session admitted, patch-stage OOM) |
| 19.50 | 1 | compact | 19.7 | 12.3 | n/a | FAIL (session admitted, patch-stage OOM) |
| 20.00 | 0 | compact | 11.8 | 7.4 | yes | OK compact |
| 24.00 | 0 | compact | 12.2 | 7.4 | yes | OK compact |
| 24.00 | 0 | compact | 12.0 | 7.4 | yes | OK compact |
| 40.00 | 0 | compact | 12.3 | 7.4 | yes | OK compact |

**tutorial G --ingest auto**

| free GiB | exit | route | wall s | host RSS GiB | ident | outcome |
|---:|---:|---|---:|---:|---|---|
| 1.00 | 1 | float | 2.7 | 2.7 | n/a | FAIL (streaming OOM) |
| 1.00 | 1 | float | 2.7 | 2.7 | n/a | FAIL (streaming OOM) |
| 2.00 | 0 | float | 5.1 | 2.8 | yes | OK streaming (session declined) |
| 3.00 | 0 | float | 5.0 | 2.8 | yes | OK streaming (session declined) |
| 3.00 | 0 | float | 5.0 | 2.8 | yes | OK streaming (session declined) |
| 4.00 | 0 | nvcomp | 1.1 | 0.3 | yes | OK nvcomp |
| 5.00 | 0 | nvcomp | 1.2 | 0.3 | yes | OK nvcomp |
| 8.50 | 0 | nvcomp | 1.1 | 0.3 | yes | OK nvcomp |
| 16.00 | 0 | nvcomp | 1.1 | 0.3 | yes | OK nvcomp |
| 16.00 | 0 | nvcomp | 1.2 | 0.3 | yes | OK nvcomp |
| 24.00 | 0 | nvcomp | 1.1 | 0.3 | yes | OK nvcomp |
| 40.00 | 0 | nvcomp | 1.2 | 0.3 | yes | OK nvcomp |

**tutorial L --ingest auto**

| free GiB | exit | route | wall s | host RSS GiB | ident | outcome |
|---:|---:|---|---:|---:|---|---|
| 1.00 | 1 | float | 2.7 | 2.7 | n/a | FAIL (streaming OOM) |
| 1.00 | 1 | float | 2.7 | 2.7 | n/a | FAIL (streaming OOM) |
| 2.00 | 0 | float | 5.9 | 2.8 | yes | OK streaming (session declined) |
| 3.00 | 0 | float | 5.7 | 2.8 | yes | OK streaming (session declined) |
| 3.00 | 0 | float | 5.9 | 2.8 | yes | OK streaming (session declined) |
| 4.00 | 0 | nvcomp | 1.2 | 0.3 | yes | OK nvcomp |
| 5.00 | 0 | nvcomp | 1.2 | 0.3 | yes | OK nvcomp |
| 8.50 | 0 | nvcomp | 1.2 | 0.3 | yes | OK nvcomp |
| 16.00 | 0 | nvcomp | 1.2 | 0.3 | yes | OK nvcomp |
| 16.00 | 0 | nvcomp | 1.2 | 0.3 | yes | OK nvcomp |
| 24.00 | 0 | nvcomp | 1.3 | 0.3 | yes | OK nvcomp |
| 40.00 | 0 | nvcomp | 1.3 | 0.3 | yes | OK nvcomp |

### Multi-movie jobs

| Job | free GiB | exit | routes (movie 1, 2, 3) | movies with products | per-movie products identical | notes |
|---|---:|---:|---|---|---|---|
| mmA-G | 16.0 | 1 | float,compact | 1/2 | True | session-init-OOM->streaming,device-ingest-declined->host-reader |
| mmA-L | 24.0 | 0 | float,nvcomp | 2/2 | True | session-init-OOM->streaming |
| mmA-L | 16.0 | 1 | float,compact | 1/2 | True | session-init-OOM->streaming,device-ingest-declined->host-reader |
| mmB-L | 24.0 | 0 | float,compact | 2/2 | True | session-init-OOM->streaming |
| mmB-L | 16.0 | 1 | float,compact | 1/2 | True | session-init-OOM->streaming,gain/sum-OOM->CPU-preprocess |
| mmC-L | 24.0 | 0 | float,nvcomp,compact | 3/3 | True | session-init-OOM->streaming |
| mmC-L | 16.0 | 1 | float,compact,compact | 2/3 | True | session-init-OOM->streaming,device-ingest-declined->host-reader |
