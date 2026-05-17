# SimC sidecar image: wraps the upstream simulationcraftorg/simc image
# with a small Python FastAPI server that exposes /simulate, /version
# and /healthz on :8090. The backend posts simulation requests here so
# the simc binary stays decoupled from the backend image.
#
# We follow whatever the upstream ``simulationcraftorg/simc:latest``
# Hub tag has — typically rebuilt every couple of days with the latest
# WoW DBC data + class-module fixes. Admins bump to a newer image via
# the "Pull latest + recreate" button in the admin UI.

FROM simulationcraftorg/simc:latest

USER root

RUN apk add --no-cache python3 py3-pip ca-certificates

RUN python3 -m pip install --break-system-packages --no-cache-dir \
        "fastapi==0.115.6" \
        "uvicorn[standard]==0.32.1"

WORKDIR /sidecar
COPY server.py /sidecar/server.py

# Override the upstream entrypoint (which exec's simc directly) so our
# FastAPI supervisor is PID 1 and can spawn simc as a child per request.
ENTRYPOINT []
CMD ["python3", "-u", "/sidecar/server.py"]
