# 4GPUs reachability record (author's observations; no remote change was attempted)

All attempts used the standard `ssh 4GPUs` route (HostName 130.246.80.58, user `alex`, port 22) with `BatchMode=yes`.

| Time (UTC, approx.) | Observation |
|---|---|
| 17:02-17:39 | Attempts 1 and 2 staged and started normally (leases acquired 17:02:28Z and 17:39:09Z). |
| after 17:39 | A `grep` of attempt 2's `chain.out` timed out; the next probes failed with `connect to host 130.246.80.58 port 22: Operation timed out`. |
| 18:08:01 | `nc -zv 130.246.80.58 22` timed out, `ping` 100% loss, GitHub reachable from the same machine (`HTTP 200`). |
| later | Repeated `ssh` probes (ConnectTimeout 10-20) timed out; one background job polling at 60 s intervals was stopped on parent instruction. No staging, no remote command ran after the first timeout. |

The parent separately confirmed the direct route (`ConnectTimeout=8`, no proxy, no ControlMaster) times out for 4GPUs and cpu64, and reported that a gateway route was refused with a changed host key (ECDSA `known_hosts:41`, new ED25519 `SHA256:7ivKs3aXAYUCaXirrFf7t4Fs2Ytqb4uXvt3KaPf3NI8`). The author did not touch `known_hosts`, host-key checking, routes or VM power state, and did not use any other address.

Consequence: the final-source venue run for `96e7e7be` (archive sha256 `313f671f4af90e227754ec17c6e8a9cae70a7ea5aaca713de62aa1d297b8ea36`) has not started. Attempt 2 (source `94e39570`, started 17:39:09Z) has an unknown outcome and unknown lease state; its logs will be fetched and kept separately once the host is reachable. No candidate producer has run.
