#!/usr/bin/env bash
# cloud/deploy.sh — Build image and deploy to Cloud Run
#
# Run this after cloud/setup.sh for the first deploy, and whenever you update
# the application code.
#
# Usage:
#   export PROJECT_ID=my-gcp-project
#   bash cloud/deploy.sh
#
# Optional overrides (all have sensible defaults):
#   REGION, BUCKET_NAME, SERVICE_ACCOUNT_NAME, REPOSITORY,
#   SERVICE_NAME, JOB_NAME, SCHEDULER_SCHEDULE

set -euo pipefail

# ── Configuration ──────────────────────────────────────────────────────────────
PROJECT_ID="${PROJECT_ID:?Set PROJECT_ID}"
REGION="${REGION:-us-central1}"
BUCKET_NAME="${BUCKET_NAME:-${PROJECT_ID}-budget-data}"
SERVICE_ACCOUNT_NAME="${SERVICE_ACCOUNT_NAME:-budget-app-sa}"
SERVICE_ACCOUNT="${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
REPOSITORY="${REPOSITORY:-budget-app}"
SERVICE_NAME="${SERVICE_NAME:-budget-dashboard}"
JOB_NAME="${JOB_NAME:-budget-update-transactions}"

# Cron schedule for the background transaction update job (default: 6 AM daily).
SCHEDULER_SCHEDULE="${SCHEDULER_SCHEDULE:-0 6 * * *}"

IMAGE_URL="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/${SERVICE_NAME}"

echo "=== Budget App — Deploy ==="
echo "  Project  : $PROJECT_ID"
echo "  Region   : $REGION"
echo "  Image    : $IMAGE_URL"
echo ""

# ── Authenticate Docker with Artifact Registry ─────────────────────────────────
echo "--- Configuring Docker auth..."
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

# ── Build and push image ───────────────────────────────────────────────────────
echo "--- Building Docker image..."
docker build --platform linux/amd64 -t "$IMAGE_URL" .

echo "--- Pushing image to Artifact Registry..."
docker push "$IMAGE_URL"

# ── Substitute variables in YAML templates ────────────────────────────────────
_render_yaml() {
    local template="$1"
    sed \
        -e "s|PROJECT_ID|${PROJECT_ID}|g" \
        -e "s|REGION|${REGION}|g" \
        -e "s|IMAGE_URL|${IMAGE_URL}|g" \
        -e "s|BUCKET_NAME|${BUCKET_NAME}|g" \
        -e "s|SERVICE_ACCOUNT|${SERVICE_ACCOUNT}|g" \
        "$template"
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Deploy Cloud Run service (dashboard) ───────────────────────────────────────
echo "--- Deploying Cloud Run service '$SERVICE_NAME'..."
_render_yaml "$SCRIPT_DIR/service.yaml" | \
    gcloud run services replace - \
        --region="$REGION" \
        --project="$PROJECT_ID"

# Allow unauthenticated requests — the app enforces its own password auth.
gcloud run services add-iam-policy-binding "$SERVICE_NAME" \
    --region="$REGION" \
    --project="$PROJECT_ID" \
    --member="allUsers" \
    --role="roles/run.invoker"

# ── Deploy Cloud Run Job (background update) ───────────────────────────────────
echo "--- Deploying Cloud Run Job '$JOB_NAME'..."
_render_yaml "$SCRIPT_DIR/job.yaml" | \
    gcloud run jobs replace - \
        --region="$REGION" \
        --project="$PROJECT_ID"

# ── Cloud Scheduler trigger for the update job ─────────────────────────────────
echo "--- Setting up Cloud Scheduler (schedule: '$SCHEDULER_SCHEDULE')..."

# Build the job execution URL from the job name and region.
JOB_URL="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/${JOB_NAME}:run"

SCHEDULER_JOB_NAME="budget-update-transactions-trigger"
if gcloud scheduler jobs describe "$SCHEDULER_JOB_NAME" \
        --location="$REGION" --project="$PROJECT_ID" &>/dev/null; then
    echo "    Scheduler job already exists — updating schedule..."
    gcloud scheduler jobs update http "$SCHEDULER_JOB_NAME" \
        --location="$REGION" \
        --project="$PROJECT_ID" \
        --schedule="$SCHEDULER_SCHEDULE" \
        --uri="$JOB_URL" \
        --http-method=POST \
        --oauth-service-account-email="$SERVICE_ACCOUNT" \
        --quiet
else
    gcloud scheduler jobs create http "$SCHEDULER_JOB_NAME" \
        --location="$REGION" \
        --project="$PROJECT_ID" \
        --schedule="$SCHEDULER_SCHEDULE" \
        --uri="$JOB_URL" \
        --http-method=POST \
        --oauth-service-account-email="$SERVICE_ACCOUNT" \
        --quiet
fi

# Grant the SA permission to trigger Cloud Run Jobs.
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$SERVICE_ACCOUNT" \
    --role="roles/run.invoker" \
    --quiet

# ── Print the service URL ──────────────────────────────────────────────────────
SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" \
    --region="$REGION" \
    --project="$PROJECT_ID" \
    --format="value(status.url)")

echo ""
echo "=== Deploy complete! ==="
echo ""
echo "  Dashboard URL : $SERVICE_URL"
echo "  Update job    : $JOB_NAME (runs at: $SCHEDULER_SCHEDULE)"
echo ""
echo "To trigger the update job immediately:"
echo "  gcloud run jobs execute $JOB_NAME --region=$REGION --project=$PROJECT_ID"
echo ""
echo "To view dashboard logs:"
echo "  gcloud run services logs read $SERVICE_NAME --region=$REGION --project=$PROJECT_ID"
echo ""
