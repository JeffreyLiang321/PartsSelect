# Backend image for the Hugging Face Docker Space.
#
# Build context is the repo root (locally: docker build -f deploy/hf-space/Dockerfile .).
# deploy.sh uploads the same paths to the Space, with this file at the Space root.
# Secrets (OPENAI_API_KEY) are injected at runtime by the Space — never baked in.

FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    ANONYMIZED_TELEMETRY=False

# HF Spaces run containers as uid 1000
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH
WORKDIR $HOME/app

COPY --chown=user deploy/hf-space/requirements-server.txt ./
RUN pip install --user -r requirements-server.txt

COPY --chown=user main.py ./
COPY --chown=user backend ./backend
# Read-only at runtime, but Chroma opens its sqlite file read-write, so the
# data directory must be owned by the app user.
COPY --chown=user data/parts.db data/repair_guides.json data/blogs.json ./data/
COPY --chown=user data/chroma ./data/chroma

# HF's proxy appends one X-Forwarded-For hop
ENV TRUSTED_PROXY_HOPS=1

EXPOSE 7860
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
