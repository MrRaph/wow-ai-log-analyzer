# SimC sidecar image: wraps the upstream simulationcraftorg/simc image with
# a small Python FastAPI server that exposes /simulate, /version and
# /healthz on :8090. The backend pokes this sidecar to run simulations
# without needing Docker socket access on the backend.
#
# The upstream image ships the simc binary and the per-spec default
# profiles. We override the entrypoint to run our wrapper instead.

FROM simulationcraftorg/simc:latest

# Upstream is Ubuntu/Debian-based. Add python + pip.
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-pip ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Pinned to keep behaviour stable across rebuilds.
RUN python3 -m pip install --break-system-packages --no-cache-dir \
        "fastapi==0.115.6" \
        "uvicorn[standard]==0.32.1"

WORKDIR /sidecar
COPY server.py /sidecar/server.py

# The upstream entrypoint exec's simc directly; we drop it so our server
# is PID 1 and can spawn simc as a child per request.
ENTRYPOINT []
CMD ["python3", "-u", "/sidecar/server.py"]
