# SimC sidecar image: wraps the upstream simulationcraftorg/simc image with
# a small Python FastAPI server that exposes /simulate, /version and
# /healthz on :8090. The backend pokes this sidecar to run simulations
# without needing Docker socket access on the backend.
#
# The upstream image ships the simc binary at /app/SimulationCraft/simc
# plus the per-spec default profile data. We override the entrypoint to
# run our wrapper instead.
#
# Upstream is Alpine-based (3.23+) so we use ``apk`` and stay on musl.
# A multi-stage build into python:3.13-slim was considered but rejected:
# simc is dynamically linked against Alpine's libstdc++, glibc-targeted
# slim images can't load it without compatibility shims, and using
# Alpine's own python lets the final image stay close to 200 MB rather
# than ballooning past 500 MB.

FROM simulationcraftorg/simc:latest

USER root
# ``--no-cache`` keeps the layer slim — apk's normal cache would persist
# past the build. ``ca-certificates`` is needed for pip's TLS handshake.
RUN apk add --no-cache python3 py3-pip ca-certificates

# Pinned versions so rebuilds are deterministic. ``--break-system-packages``
# is required on python 3.12+ when installing into the system site-packages
# (PEP 668). We don't run untrusted Python in this image so a venv would
# be pure overhead.
RUN python3 -m pip install --break-system-packages --no-cache-dir \
        "fastapi==0.115.6" \
        "uvicorn[standard]==0.32.1"

WORKDIR /sidecar
COPY server.py /sidecar/server.py

# The upstream entrypoint exec's simc directly; drop it so our server is
# PID 1 and can spawn simc as a child per request.
ENTRYPOINT []
CMD ["python3", "-u", "/sidecar/server.py"]
