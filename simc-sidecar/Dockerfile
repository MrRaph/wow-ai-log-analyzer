# SimC sidecar image: wraps the upstream simulationcraftorg/simc image with
# a small Python FastAPI server that exposes /simulate, /version, /healthz
# and (when an admin triggers it) a *rebuild-from-source* path so the
# sidecar can run against fresher game data than the upstream stable
# image ships with.
#
# Two data planes:
# - Upstream-prebuilt simc binary + community-default profiles ship in
#   ``/app/SimulationCraft/`` — works immediately after first start.
# - On demand the sidecar pulls the latest simc source, downloads fresh
#   DBC files from the public WoW CDN (via ``casc_extract``), optionally
#   layers an admin-uploaded ``DBCache.bin`` hotfix file on top
#   (``dbc_extract3/cache/live/``), regenerates simc's internal data
#   headers and rebuilds the binary. Result is dropped over the
#   upstream binary; the next ``/simulate`` call picks it up.
#
# Image cost: the build-toolchain layer adds ~250 MB on top of the
# base. We keep it in the runtime image (rather than multi-stage) so
# the rebuild path works from inside the running container — no Docker
# socket needed.
#
# Alpine 3.23 (matches the upstream base) — apk for everything.

FROM simulationcraftorg/simc:latest

USER root

# ``--no-cache`` keeps the layer slim. ca-certificates is needed for
# pip's TLS handshake + git's HTTPS clone of the simc source.
# build-base / cmake / make / git / linux-headers are required for
# the rebuild path; they idle at zero CPU when not used and the
# disk cost is modest (~200 MB on top of the upstream image).
RUN apk add --no-cache \
        python3 py3-pip ca-certificates \
        git make cmake build-base linux-headers \
        curl-dev openssl-dev

# Pin the Python deps for our FastAPI wrapper + the simc data
# pipeline (casc_extract.py + dbc_extract3 share ``requests``).
RUN python3 -m pip install --break-system-packages --no-cache-dir \
        "fastapi==0.115.6" \
        "uvicorn[standard]==0.32.1" \
        "python-multipart==0.0.20" \
        "requests==2.32.3" \
        "fixedint==0.2.0" \
        "bitarray==3.0.0"

# Clone the simc source at image build time so the first rebuild
# doesn't have to download ~50 MB of repo on a user-triggered call.
# Pin to the active expansion branch — currently ``midnight`` (WoW 12.0.x
# "The Last Titan"-era). When Blizzard ships the next expansion the
# branch name will change and SIMC_SOURCE_BRANCH should be bumped.
# Note: ``dragonflight`` (previous expansion) carries stale CASC parser
# data and crashes on the current CDN layout — do NOT pin to it.
ARG SIMC_SOURCE_BRANCH=midnight
RUN git clone --depth 1 --branch ${SIMC_SOURCE_BRANCH} \
        https://github.com/simulationcraft/simc.git /opt/simc-source

WORKDIR /sidecar
COPY server.py rebuild-simc.sh /sidecar/
RUN chmod +x /sidecar/rebuild-simc.sh

# Override the upstream entrypoint (which exec's simc directly).
# The supervisor decides when and how to spawn it.
ENTRYPOINT []
CMD ["python3", "-u", "/sidecar/server.py"]
