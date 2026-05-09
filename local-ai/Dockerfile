# Local-AI sidecar image: wraps the upstream llama.cpp server-cuda image
# with a small Python supervisor on :8081 that spawns llama-server as a
# child on :8080 and lets the backend drive model switches, cache cleanup
# and start/stop without needing Docker socket access.

FROM ghcr.io/ggml-org/llama.cpp:server-cuda

# Upstream is Ubuntu-based but minimal — we add Python + pip ourselves.
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-pip ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Pinned to keep behaviour stable across rebuilds. huggingface_hub gives
# us resumable downloads with a tqdm-compatible progress callback.
RUN python3 -m pip install --break-system-packages --no-cache-dir \
        "fastapi==0.115.6" \
        "uvicorn[standard]==0.32.1" \
        "huggingface-hub==0.27.0" \
        "httpx==0.28.1"

WORKDIR /app
COPY supervisor.py /app/supervisor.py

# Override the upstream entrypoint (which exec's llama-server directly).
# The supervisor decides when and how to spawn it.
ENTRYPOINT []
CMD ["python3", "/app/supervisor.py"]
