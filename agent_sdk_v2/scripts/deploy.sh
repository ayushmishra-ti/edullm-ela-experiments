#!/bin/bash
# Deploy ELA SDK v2 to Google Cloud Run (NEW separate service)

set -e

PROJECT_ID="eternal-aspect-485115-e3"
REGION="us-central1"
SERVICE_NAME="ela-sdk-v2"
IMAGE_NAME="us-central1-docker.pkg.dev/${PROJECT_ID}/ccapi-repo/ela-sdk-v2:latest"

echo "=============================================="
echo "Deploying ELA SDK v2 (NEW service)"
echo "=============================================="
echo ""
echo "Endpoints:"
echo "  POST /generate              - Generate ELA questions"
echo "  POST /populate-curriculum   - Populate curriculum data"
echo ""

echo "Building Docker image..."
gcloud builds submit . \
  --config cloudbuild.yaml \
  --substitutions=_IMAGE_NAME="${IMAGE_NAME}"

echo ""
echo "Deploying to Cloud Run..."
gcloud run deploy "${SERVICE_NAME}" \
  --image "${IMAGE_NAME}" \
  --region "${REGION}" \
  --platform managed \
  --allow-unauthenticated \
  --memory 2Gi \
  --timeout 300 \
  --set-secrets=ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest

echo ""
echo "=============================================="
echo "Deployment complete!"
echo "=============================================="
SERVICE_URL=$(gcloud run services describe ${SERVICE_NAME} --region ${REGION} --format 'value(status.url)')
echo "Service URL: ${SERVICE_URL}"
echo ""
echo "Test endpoints:"
echo "  curl ${SERVICE_URL}/"
echo "  curl -X POST ${SERVICE_URL}/generate -H 'Content-Type: application/json' -d '{...}'"
echo "  curl -X POST ${SERVICE_URL}/populate-curriculum -H 'Content-Type: application/json' -d '{...}'"
