#!/usr/bin/env bash
# cloud/setup.sh — One-time GCP infrastructure setup
#
# Run this once before your first deployment.  It is safe to re-run
# (all commands are idempotent).
#
# Prerequisites:
#   - gcloud CLI installed and authenticated  (gcloud auth login)
#   - Billing enabled on the project
#   - The following APIs will be enabled automatically by this script
#
# Usage:
#   export PROJECT_ID=my-gcp-project
#   export SIMPLEFIN_AUTH="https://..."    # your SimpleFin bridge URL
#   export APP_PASSWORD="your-password"   # dashboard login password
#   bash cloud/setup.sh

set -euo pipefail

# ── Configuration ──────────────────────────────────────────────────────────────
PROJECT_ID="${PROJECT_ID:?Set PROJECT_ID}"
REGION="${REGION:-us-central1}"
BUCKET_NAME="${BUCKET_NAME:-${PROJECT_ID}-budget-data}"
SERVICE_ACCOUNT_NAME="${SERVICE_ACCOUNT_NAME:-budget-app-sa}"
SERVICE_ACCOUNT="${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
REPOSITORY="${REPOSITORY:-budget-app}"

SIMPLEFIN_AUTH="${SIMPLEFIN_AUTH:?Set SIMPLEFIN_AUTH}"
APP_PASSWORD="${APP_PASSWORD:?Set APP_PASSWORD}"

echo "=== Budget App — One-time GCP Setup ==="
echo "  Project : $PROJECT_ID"
echo "  Region  : $REGION"
echo "  Bucket  : $BUCKET_NAME"
echo ""

# ── Enable required APIs ───────────────────────────────────────────────────────
echo "--- Enabling APIs..."
gcloud services enable \
    run.googleapis.com \
    artifactregistry.googleapis.com \
    secretmanager.googleapis.com \
    cloudscheduler.googleapis.com \
    storage.googleapis.com \
    --project "$PROJECT_ID"

# ── Artifact Registry repository ──────────────────────────────────────────────
echo "--- Creating Artifact Registry repository..."
gcloud artifacts repositories create "$REPOSITORY" \
    --repository-format=docker \
    --location="$REGION" \
    --project="$PROJECT_ID" \
    --quiet \
    2>/dev/null || echo "    (repository already exists — skipping)"

# ── GCS bucket for persistent data ────────────────────────────────────────────
echo "--- Creating GCS bucket gs://$BUCKET_NAME ..."
gcloud storage buckets create "gs://$BUCKET_NAME" \
    --project="$PROJECT_ID" \
    --location="$REGION" \
    --uniform-bucket-level-access \
    2>/dev/null || echo "    (bucket already exists — skipping)"

# ── Service account ────────────────────────────────────────────────────────────
echo "--- Creating service account $SERVICE_ACCOUNT ..."
gcloud iam service-accounts create "$SERVICE_ACCOUNT_NAME" \
    --display-name="Budget App Service Account" \
    --project="$PROJECT_ID" \
    2>/dev/null || echo "    (service account already exists — skipping)"

# Grant Storage Object Admin so the SA can read/write the bucket.
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET_NAME" \
    --member="serviceAccount:$SERVICE_ACCOUNT" \
    --role="roles/storage.objectAdmin"

# Grant Secret Manager Secret Accessor so the SA can read secrets at runtime.
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$SERVICE_ACCOUNT" \
    --role="roles/secretmanager.secretAccessor"

# ── Secrets ────────────────────────────────────────────────────────────────────
echo "--- Storing secrets in Secret Manager..."

store_secret() {
    local name="$1"
    local value="$2"
    if gcloud secrets describe "$name" --project="$PROJECT_ID" &>/dev/null; then
        echo "    $name exists — adding new version..."
        echo -n "$value" | gcloud secrets versions add "$name" \
            --data-file=- --project="$PROJECT_ID"
    else
        echo "    Creating $name..."
        echo -n "$value" | gcloud secrets create "$name" \
            --data-file=- --project="$PROJECT_ID" --replication-policy="automatic"
    fi
}

store_secret "simplefin-auth"       "$SIMPLEFIN_AUTH"
store_secret "budget-app-password"  "$APP_PASSWORD"

echo ""
echo "=== Setup complete! ==="
echo ""
echo "Next steps:"
echo "  1. Upload your config.json to the bucket:"
echo "     gcloud storage cp config.json gs://$BUCKET_NAME/config.json"
echo ""
echo "  2. Run the deploy script to build and deploy the app:"
echo "     bash cloud/deploy.sh"
echo ""
