#!/bin/bash
#
# AutoEdit GCP Deployment Script
# Deploys Cloud Workflow and Eventarc trigger for automatic video editing
#
# Prerequisites:
# - gcloud CLI configured with appropriate permissions
# - Cloud Run service 'nca-toolkit' already deployed
# - Required APIs will be enabled automatically

set -e  # Exit on any error

# --- CONFIGURATION ---
export PROJECT_ID="autoedit-at"
export REGION="us-central1"
export WORKFLOW_NAME="autoedit-aroll-flow"
export BUCKET_NAME="nca-toolkit-autoedit"
export SERVICE_ACCOUNT_NAME="workflows-autoedit-sa"
export CLOUD_RUN_SERVICE="nca-toolkit"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  AutoEdit GCP Deployment${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Set project
echo -e "${YELLOW}[1/6] Setting project to ${PROJECT_ID}...${NC}"
gcloud config set project $PROJECT_ID

# 1. Enable required APIs
echo -e "${YELLOW}[2/6] Enabling required APIs...${NC}"
gcloud services enable \
    workflows.googleapis.com \
    workflowexecutions.googleapis.com \
    eventarc.googleapis.com \
    run.googleapis.com \
    logging.googleapis.com \
    aiplatform.googleapis.com \
    storage.googleapis.com \
    --quiet

echo -e "${GREEN}APIs enabled successfully${NC}"

# 2. Create Service Account for Workflow
echo -e "${YELLOW}[3/6] Creating Service Account...${NC}"
SA_EMAIL="${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

if ! gcloud iam service-accounts describe "${SA_EMAIL}" &>/dev/null; then
    gcloud iam service-accounts create $SERVICE_ACCOUNT_NAME \
        --display-name="AutoEdit Workflows Service Account" \
        --description="Service account for AutoEdit Cloud Workflows"
    echo -e "${GREEN}Service Account created: ${SA_EMAIL}${NC}"
else
    echo -e "${YELLOW}Service Account already exists: ${SA_EMAIL}${NC}"
fi

# 3. Assign IAM Roles
echo -e "${YELLOW}[4/6] Assigning IAM roles...${NC}"

# Workflow Invoker (for Eventarc to trigger workflow)
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/workflows.invoker" \
    --quiet

# Cloud Run Invoker (for workflow to call Cloud Run)
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/run.invoker" \
    --quiet

# Vertex AI User (for Gemini API)
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/aiplatform.user" \
    --quiet

# Logging Writer (for workflow logs)
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/logging.logWriter" \
    --quiet

# Storage Object Viewer (to read uploaded files)
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/storage.objectViewer" \
    --quiet

# Eventarc Event Receiver
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/eventarc.eventReceiver" \
    --quiet

echo -e "${GREEN}IAM roles assigned${NC}"

# 4. Grant Storage Service Agent permission to publish Pub/Sub
echo -e "${YELLOW}[4b/6] Configuring Storage notifications...${NC}"
STORAGE_SA=$(gcloud storage service-agent --project=$PROJECT_ID 2>/dev/null || gsutil kms serviceaccount -p $PROJECT_ID)
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${STORAGE_SA}" \
    --role="roles/pubsub.publisher" \
    --quiet

echo -e "${GREEN}Storage notifications configured${NC}"

# 5. Deploy Cloud Workflow
echo -e "${YELLOW}[5/6] Deploying Cloud Workflow...${NC}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKFLOW_FILE="${SCRIPT_DIR}/autoedit-workflow.yaml"

if [ ! -f "$WORKFLOW_FILE" ]; then
    echo -e "${RED}Error: Workflow file not found at ${WORKFLOW_FILE}${NC}"
    exit 1
fi

gcloud workflows deploy $WORKFLOW_NAME \
    --source="$WORKFLOW_FILE" \
    --service-account="${SA_EMAIL}" \
    --location=$REGION \
    --description="AutoEdit A-Roll: Automatic video editing with Whisper + Gemini + FFmpeg"

echo -e "${GREEN}Workflow deployed: ${WORKFLOW_NAME}${NC}"

# 6. Create Eventarc Trigger
echo -e "${YELLOW}[6/6] Creating Eventarc Trigger...${NC}"
TRIGGER_NAME="trigger-${WORKFLOW_NAME}"

# Check if trigger exists
if gcloud eventarc triggers describe $TRIGGER_NAME --location=$REGION &>/dev/null; then
    echo -e "${YELLOW}Trigger already exists, deleting and recreating...${NC}"
    gcloud eventarc triggers delete $TRIGGER_NAME \
        --location=$REGION \
        --quiet
fi

# Create the trigger
gcloud eventarc triggers create $TRIGGER_NAME \
    --location=$REGION \
    --destination-workflow=$WORKFLOW_NAME \
    --destination-workflow-location=$REGION \
    --event-filters="type=google.cloud.storage.object.v1.finalized" \
    --event-filters="bucket=$BUCKET_NAME" \
    --service-account="${SA_EMAIL}"

echo -e "${GREEN}Eventarc trigger created${NC}"

# Summary
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Deployment Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "Project:        ${PROJECT_ID}"
echo -e "Workflow:       ${WORKFLOW_NAME}"
echo -e "Trigger:        ${TRIGGER_NAME}"
echo -e "Bucket:         gs://${BUCKET_NAME}/"
echo -e "Service Account: ${SA_EMAIL}"
echo ""
echo -e "${YELLOW}To test:${NC}"
echo -e "  1. Upload an MP4 file to gs://${BUCKET_NAME}/"
echo -e "  2. Monitor workflow execution:"
echo -e "     gcloud workflows executions list ${WORKFLOW_NAME} --location=${REGION}"
echo ""
echo -e "${YELLOW}To manually trigger:${NC}"
echo -e "  gcloud workflows run ${WORKFLOW_NAME} --location=${REGION} \\"
echo -e "    --data='{\"data\":{\"bucket\":\"${BUCKET_NAME}\",\"name\":\"test.mp4\"}}'"
echo ""
