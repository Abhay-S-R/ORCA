# The Render image: backend/Dockerfile plus the gitignored data/ baked in, because Render
# builds from git (which has no data/) and its free plan has no disk to copy data onto.
# Build from the repo root, after the base image — docs/ORCA_Deployment.md §2:
#   docker build -t orca-backend backend
#   docker build -f infra/render/Dockerfile -t <dockerhub-user>/orca-backend:render .
# The code resolves data/ and scripts/ three levels above orca/agents/, i.e. /data, /scripts.
ARG BASE=orca-backend
FROM ${BASE}
COPY scripts/refresh_fishing_ban_order.py /scripts/
COPY data /data
# Off on Render free (512 MB): no local model is ever loaded (orca/local_models.py).
# Set ORCA_LOCAL_MODELS=1 in the Render dashboard on a plan with >= 2 GB to turn them on.
ENV ORCA_LOCAL_MODELS=0
