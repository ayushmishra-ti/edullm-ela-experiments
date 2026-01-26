# Deploying InceptAgentic Skill MCQ Generator to Google Cloud Run

This guide walks through deploying the agentic MCQ generator API to Google Cloud Run.

## Prerequisites

1. Google Cloud account with billing enabled
2. `gcloud` CLI installed and authenticated
3. `ANTHROPIC_API_KEY` for Claude API access

## Quick Deploy Commands

### 1. Set Project
```bash
gcloud config set project eternal-aspect-485115-e3
```

### 2. Enable Required APIs
```bash
gcloud services enable \
  cloudbuild.googleapis.com \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com
```

### 3. Create Artifact Registry Repository (if not exists)
```bash
gcloud artifacts repositories create ccapi-repo \
  --repository-format=docker \
  --location=us-central1 \
  --description="CCAPI Docker images"
```

### 4. Set Up Secret (if not exists)
```bash
# Create the secret
echo -n "YOUR_ANTHROPIC_API_KEY" | gcloud secrets create ANTHROPIC_API_KEY --data-file=-

# Grant Cloud Run access
gcloud secrets add-iam-policy-binding ANTHROPIC_API_KEY \
  --member="serviceAccount:413562643011-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

### 5. Build Docker Image
```bash
cd agent_sdk

gcloud builds submit . \
  --config cloudbuild.yaml \
  --substitutions=_IMAGE_NAME="us-central1-docker.pkg.dev/eternal-aspect-485115-e3/ccapi-repo/inceptagentic-skill-mcq:latest"
```

### 6. Deploy to Cloud Run
```bash
gcloud run deploy inceptagentic-skill-mcq \
  --image us-central1-docker.pkg.dev/eternal-aspect-485115-e3/ccapi-repo/inceptagentic-skill-mcq:latest \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated \
  --memory 2Gi \
  --timeout 300 \
  --set-secrets=ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest
```

Note: Agentic pipeline needs more memory (2Gi) and longer timeout (300s) due to MCP tool calls.

## PowerShell Commands (Windows)

```powershell
# Set project
gcloud config set project eternal-aspect-485115-e3

# Build
gcloud builds submit . --config cloudbuild.yaml --substitutions=_IMAGE_NAME="us-central1-docker.pkg.dev/eternal-aspect-485115-e3/ccapi-repo/inceptagentic-skill-mcq:latest"

# Deploy
gcloud run deploy inceptagentic-skill-mcq --image us-central1-docker.pkg.dev/eternal-aspect-485115-e3/ccapi-repo/inceptagentic-skill-mcq:latest --region us-central1 --platform managed --allow-unauthenticated --memory 2Gi --timeout 300 --set-secrets=ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest
```

## Using deploy.sh Script (Bash/WSL)

```bash
cd agent_sdk
chmod +x scripts/deploy.sh
./scripts/deploy.sh
```

## Testing the Deployed Endpoint

### Health Check
```bash
curl https://inceptagentic-skill-mcq-413562643011.us-central1.run.app/
```

### Generate MCQ
```bash
curl -X POST https://inceptagentic-skill-mcq-413562643011.us-central1.run.app/generate \
  -H "Content-Type: application/json" \
  -d '{
    "grade": "3",
    "subject": "ela",
    "type": "mcq",
    "difficulty": "medium",
    "skills": {
      "substandard_id": "CCSS.ELA-LITERACY.L.3.1.A",
      "substandard_description": "Explain the function of nouns"
    }
  }'
```

## InceptBench Registration

Register on InceptBench with:
- **Name**: `InceptAgentic`
- **Endpoint URL**: `https://inceptagentic-skill-mcq-413562643011.us-central1.run.app/generate`
- **Method**: `POST`
- **Authentication**: None
