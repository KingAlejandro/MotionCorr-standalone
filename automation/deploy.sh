#!/usr/bin/env bash
set -euo pipefail

# Always target the hackathon project, regardless of the caller's gcloud default.
PROJECT_ID=ral-harwell26lon-207
REGION=europe-west2
REPOSITORY=motioncorr-agents
JOB=motioncorr-github-agent
SECRET=motioncorr-github-app-key
WORKER_ACCOUNT=motioncorr-agent
SCHEDULER_ACCOUNT=motioncorr-scheduler
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/worker:latest"

if [[ -z "${GITHUB_APP_ID:-}" || -z "${GITHUB_INSTALLATION_ID:-}" ]]; then
  echo "Set GITHUB_APP_ID and GITHUB_INSTALLATION_ID before deployment." >&2
  exit 2
fi

cd "$(dirname "$0")/.."
gcloud projects describe "$PROJECT_ID" --format='value(projectId)' --project="$PROJECT_ID" >/dev/null
gcloud secrets describe "$SECRET" --project="$PROJECT_ID" >/dev/null

gcloud services enable \
  run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  cloudscheduler.googleapis.com secretmanager.googleapis.com aiplatform.googleapis.com \
  --project="$PROJECT_ID"

if ! gcloud artifacts repositories describe "$REPOSITORY" --location="$REGION" --project="$PROJECT_ID" >/dev/null 2>&1; then
  gcloud artifacts repositories create "$REPOSITORY" \
    --repository-format=docker --location="$REGION" --project="$PROJECT_ID"
fi

if ! gcloud iam service-accounts describe "$WORKER_ACCOUNT@$PROJECT_ID.iam.gserviceaccount.com" --project="$PROJECT_ID" >/dev/null 2>&1; then
  gcloud iam service-accounts create "$WORKER_ACCOUNT" --project="$PROJECT_ID" \
    --display-name="MotionCorr GitHub agent"
fi
if ! gcloud iam service-accounts describe "$SCHEDULER_ACCOUNT@$PROJECT_ID.iam.gserviceaccount.com" --project="$PROJECT_ID" >/dev/null 2>&1; then
  gcloud iam service-accounts create "$SCHEDULER_ACCOUNT" --project="$PROJECT_ID" \
    --display-name="MotionCorr agent scheduler"
fi

WORKER_EMAIL="${WORKER_EMAIL_OVERRIDE:-$WORKER_ACCOUNT@$PROJECT_ID.iam.gserviceaccount.com}"
SCHEDULER_EMAIL="$SCHEDULER_ACCOUNT@$PROJECT_ID.iam.gserviceaccount.com"
if [[ -z "${WORKER_EMAIL_OVERRIDE:-}" ]]; then
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$WORKER_EMAIL" --role=roles/aiplatform.user --quiet >/dev/null
fi
gcloud secrets add-iam-policy-binding "$SECRET" --project="$PROJECT_ID" \
  --member="serviceAccount:$WORKER_EMAIL" --role=roles/secretmanager.secretAccessor \
  --quiet >/dev/null

gcloud builds submit . --config=automation/cloudbuild.yaml \
  --substitutions="_IMAGE=$IMAGE" --project="$PROJECT_ID"
gcloud run jobs deploy "$JOB" --image="$IMAGE" --region="$REGION" --project="$PROJECT_ID" \
  --service-account="$WORKER_EMAIL" --tasks=1 --parallelism=1 \
  --max-retries=0 --task-timeout=900s --memory=1Gi --cpu=1 \
  --set-env-vars="GITHUB_REPO=KingAlejandro/MotionCorr-standalone,GITHUB_APP_ID=$GITHUB_APP_ID,GITHUB_INSTALLATION_ID=$GITHUB_INSTALLATION_ID,GOOGLE_CLOUD_PROJECT=$PROJECT_ID,GEMINI_MODEL=gemini-3.6-flash" \
  --set-secrets="GITHUB_APP_PRIVATE_KEY=$SECRET:latest"

gcloud run jobs add-iam-policy-binding "$JOB" --region="$REGION" --project="$PROJECT_ID" \
  --member="serviceAccount:$SCHEDULER_EMAIL" --role=roles/run.invoker --quiet >/dev/null

SCHEDULER_URI="https://run.googleapis.com/v2/projects/$PROJECT_ID/locations/$REGION/jobs/$JOB:run"
if gcloud scheduler jobs describe "$JOB" --location="$REGION" --project="$PROJECT_ID" >/dev/null 2>&1; then
  gcloud scheduler jobs update http "$JOB" --location="$REGION" --project="$PROJECT_ID" \
    --schedule='*/15 * * * *' --time-zone=Europe/London \
    --uri="$SCHEDULER_URI" --http-method=POST \
    --oauth-service-account-email="$SCHEDULER_EMAIL"
else
  gcloud scheduler jobs create http "$JOB" --location="$REGION" --project="$PROJECT_ID" \
    --schedule='*/15 * * * *' --time-zone=Europe/London \
    --uri="$SCHEDULER_URI" --http-method=POST \
    --oauth-service-account-email="$SCHEDULER_EMAIL"
fi

echo "Deployed $JOB in $PROJECT_ID ($REGION)."
