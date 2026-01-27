#!/bin/bash
# Deploy InceptAgentic Skill MCQ Generator to Google Cloud Run

set -e

PROJECT_ID="eternal-aspect-485115-e3"
REGION="us-central1"
SERVICE_NAME="inceptagentic-skill-mcq"
IMAGE_NAME="us-central1-docker.pkg.dev/${PROJECT_ID}/ccapi-repo/inceptagentic-skill-mcq:latest"

echo "Building Docker image..."
gcloud builds submit . \
  --config cloudbuild.yaml \
  --substitutions=_IMAGE_NAME="${IMAGE_NAME}"

echo "Deploying to Cloud Run..."
gcloud run deploy "${SERVICE_NAME}" \
  --image "${IMAGE_NAME}" \
  --region "${REGION}" \
  --platform managed \
  --allow-unauthenticated \
  --memory 2Gi \
  --timeout 300 \
  --set-secrets=ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest

echo "Deployment complete!"
echo "Service URL: https://${SERVICE_NAME}-413562643011.${REGION}.run.app"
