@echo off
REM AutoEdit GCP Deployment Script (Windows)
REM Deploys Cloud Workflow and Eventarc trigger for automatic video editing

setlocal enabledelayedexpansion

REM --- CONFIGURATION ---
set PROJECT_ID=autoedit-at
set REGION=us-central1
set WORKFLOW_NAME=autoedit-aroll-flow
set BUCKET_NAME=nca-toolkit-autoedit
set SERVICE_ACCOUNT_NAME=workflows-autoedit-sa
set CLOUD_RUN_SERVICE=nca-toolkit
set SA_EMAIL=%SERVICE_ACCOUNT_NAME%@%PROJECT_ID%.iam.gserviceaccount.com

echo ========================================
echo   AutoEdit GCP Deployment
echo ========================================
echo.

REM Set project
echo [1/6] Setting project to %PROJECT_ID%...
call gcloud config set project %PROJECT_ID%

REM 1. Enable required APIs
echo [2/6] Enabling required APIs...
call gcloud services enable workflows.googleapis.com workflowexecutions.googleapis.com eventarc.googleapis.com run.googleapis.com logging.googleapis.com aiplatform.googleapis.com storage.googleapis.com --quiet
if errorlevel 1 (
    echo ERROR: Failed to enable APIs
    exit /b 1
)
echo APIs enabled successfully

REM 2. Create Service Account
echo [3/6] Creating Service Account...
call gcloud iam service-accounts describe %SA_EMAIL% >nul 2>&1
if errorlevel 1 (
    call gcloud iam service-accounts create %SERVICE_ACCOUNT_NAME% --display-name="AutoEdit Workflows Service Account" --description="Service account for AutoEdit Cloud Workflows"
    echo Service Account created: %SA_EMAIL%
) else (
    echo Service Account already exists: %SA_EMAIL%
)

REM 3. Assign IAM Roles
echo [4/6] Assigning IAM roles...
call gcloud projects add-iam-policy-binding %PROJECT_ID% --member="serviceAccount:%SA_EMAIL%" --role="roles/workflows.invoker" --quiet
call gcloud projects add-iam-policy-binding %PROJECT_ID% --member="serviceAccount:%SA_EMAIL%" --role="roles/run.invoker" --quiet
call gcloud projects add-iam-policy-binding %PROJECT_ID% --member="serviceAccount:%SA_EMAIL%" --role="roles/aiplatform.user" --quiet
call gcloud projects add-iam-policy-binding %PROJECT_ID% --member="serviceAccount:%SA_EMAIL%" --role="roles/logging.logWriter" --quiet
call gcloud projects add-iam-policy-binding %PROJECT_ID% --member="serviceAccount:%SA_EMAIL%" --role="roles/storage.objectViewer" --quiet
call gcloud projects add-iam-policy-binding %PROJECT_ID% --member="serviceAccount:%SA_EMAIL%" --role="roles/eventarc.eventReceiver" --quiet
echo IAM roles assigned

REM 4. Configure Storage notifications
echo [4b/6] Configuring Storage notifications...
for /f "tokens=*" %%i in ('gcloud storage service-agent --project=%PROJECT_ID% 2^>nul') do set STORAGE_SA=%%i
call gcloud projects add-iam-policy-binding %PROJECT_ID% --member="serviceAccount:%STORAGE_SA%" --role="roles/pubsub.publisher" --quiet
echo Storage notifications configured

REM 5. Deploy Cloud Workflow
echo [5/6] Deploying Cloud Workflow...
set SCRIPT_DIR=%~dp0
set WORKFLOW_FILE=%SCRIPT_DIR%autoedit-workflow.yaml

if not exist "%WORKFLOW_FILE%" (
    echo ERROR: Workflow file not found at %WORKFLOW_FILE%
    exit /b 1
)

call gcloud workflows deploy %WORKFLOW_NAME% --source="%WORKFLOW_FILE%" --service-account="%SA_EMAIL%" --location=%REGION% --description="AutoEdit A-Roll: Automatic video editing with Whisper + Gemini + FFmpeg"
if errorlevel 1 (
    echo ERROR: Failed to deploy workflow
    exit /b 1
)
echo Workflow deployed: %WORKFLOW_NAME%

REM 6. Create Eventarc Trigger
echo [6/6] Creating Eventarc Trigger...
set TRIGGER_NAME=trigger-%WORKFLOW_NAME%

REM Check if trigger exists and delete it
call gcloud eventarc triggers describe %TRIGGER_NAME% --location=%REGION% >nul 2>&1
if not errorlevel 1 (
    echo Trigger already exists, deleting and recreating...
    call gcloud eventarc triggers delete %TRIGGER_NAME% --location=%REGION% --quiet
)

REM Create the trigger
call gcloud eventarc triggers create %TRIGGER_NAME% --location=%REGION% --destination-workflow=%WORKFLOW_NAME% --destination-workflow-location=%REGION% --event-filters="type=google.cloud.storage.object.v1.finalized" --event-filters="bucket=%BUCKET_NAME%" --service-account="%SA_EMAIL%"
if errorlevel 1 (
    echo ERROR: Failed to create Eventarc trigger
    exit /b 1
)
echo Eventarc trigger created

echo.
echo ========================================
echo   Deployment Complete!
echo ========================================
echo.
echo Project:         %PROJECT_ID%
echo Workflow:        %WORKFLOW_NAME%
echo Trigger:         %TRIGGER_NAME%
echo Bucket:          gs://%BUCKET_NAME%/
echo Service Account: %SA_EMAIL%
echo.
echo To test:
echo   1. Upload an MP4 file to gs://%BUCKET_NAME%/
echo   2. Monitor workflow execution:
echo      gcloud workflows executions list %WORKFLOW_NAME% --location=%REGION%
echo.

endlocal
