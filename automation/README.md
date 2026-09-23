# MotionCorr GitHub agents on the hackathon Google Cloud project

This worker runs in **`ral-harwell26lon-207`** as a Cloud Run Job every 15 minutes. It reads only `KingAlejandro/MotionCorr-standalone` and uses the project's Vertex AI Gemini model. It acts only when a maintainer applies one of these labels:

| Label | Action |
| --- | --- |
| `agent:triage` on an issue | Posts a technical assessment and questions. |
| `agent:fix` on an issue | Proposes a small source patch as a **draft** PR. |
| `agent:review` on a PR | Posts a review tied to the current commit. |

The worker neither merges nor approves PRs. Fixes are limited to at most three existing source files. It does not run code from issue text or generated patches. Generated fixes are uncompiled proposals; a human must review them and run the relevant scientific checks.

## One-time setup

1. Create a GitHub App owned by `KingAlejandro` and install it **only** on `MotionCorr-standalone`. Repository permissions: **Contents: Read and write**, **Issues: Read and write**, **Pull requests: Read and write**, **Metadata: Read**. No organization permissions or webhooks are needed. Record its App ID and installation ID. Download its private key and keep it off the repository.
2. In project `ral-harwell26lon-207`, create Secret Manager secret `motioncorr-github-app-key` and add the private key as its first version. Grant access only to the worker service account. Do not add the key to Git, terminal history, or a command argument.
3. Authenticate `gcloud` as the hackathon lab account and confirm that `gcloud projects describe ral-harwell26lon-207` succeeds. Use the lab project as the billing and deployment target. The deployment script passes `--project=ral-harwell26lon-207` explicitly for every Cloud operation.
4. Export `GITHUB_APP_ID` and `GITHUB_INSTALLATION_ID`, then run `bash automation/deploy.sh` from this repository. The script enables required APIs, creates the Artifact Registry repository and service accounts, builds the worker, deploys the Cloud Run Job, and schedules it.
5. Protect `main` with required PR review and relevant CI before enabling `agent:fix` broadly. Apply a label to one issue or PR, then inspect Cloud Run logs and the resulting comment or draft PR.

The job uses `gemini-3.6-flash` by default. If the lab project has access to a different model, change `GEMINI_MODEL` in `deploy.sh` before deployment.

The hackathon account can create Cloud resources but cannot change project IAM. For this lab project, set `WORKER_EMAIL_OVERRIDE=530869384304-compute@developer.gserviceaccount.com` when running `deploy.sh`. That existing default compute account has the project Editor role, which is broader than the dedicated worker account's intended Vertex AI User role. The script skips the project IAM change when an override is set and grants the chosen account access to the GitHub App secret. Use the dedicated worker account if a project administrator can grant it `roles/aiplatform.user`.

## Operational limits

- Processes at most three actions per run. Markers in its own comments/reviews prevent repeat work on unchanged input.
- If a fix patch does not apply cleanly, the job logs that issue and proposes no PR.
- The intended dedicated Cloud Run runtime service account has Vertex AI User plus access to one GitHub App private-key secret. The hackathon deployment uses the existing default compute account as noted above. GitHub installation tokens are short lived and scoped to this repository.
- The worker does not store issue text or model output outside Cloud Run logs and GitHub comments/PRs. It does not log the App key or tokens.
- The GitHub App can write repository contents because draft fixes need a branch. Install it only on this repository, protect `main`, and review its permissions before installation.
