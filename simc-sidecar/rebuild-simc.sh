#!/bin/sh
# Rebuild simc from source with the latest CDN game data.
#
# Optional first argument: path to a user-uploaded DBCache.bin that gets
# layered on top of the public CDN DBC data (Blizzard's hotfix cache,
# which lives only inside an actual WoW client install and is the only
# way to get truly bleeding-edge data ahead of the next simc daily).
#
# Steps:
#   1. ``git pull`` the simc source
#   2. ``casc_extract.py`` downloads the live DBC files from the WoW CDN
#   3. Copy the uploaded DBCache.bin into dbc_extract3/cache/live/ (if any)
#   4. ``dbc_extract3/generate.sh live`` converts everything to simc's
#      internal headers
#   5. ``cmake`` + ``make simc`` rebuilds the binary
#   6. Swap the new binary into /app/SimulationCraft/simc atomically
#
# Stdout/stderr is captured by the caller (the FastAPI sidecar) and
# streamed to the admin UI so the user can see what's happening.

set -eu

SOURCE_DIR=${SIMC_SOURCE_DIR:-/opt/simc-source}
TARGET_BIN=${SIMC_BIN:-/app/SimulationCraft/simc}
DBCACHE_UPLOAD=${1:-}
JOBS=${SIMC_BUILD_JOBS:-}

if [ -z "$JOBS" ]; then
    JOBS=$(nproc 2>/dev/null || echo 4)
fi

log() {
    printf '[rebuild-simc] %s\n' "$*"
}

log "== Step 1/6: refresh simc source =="
cd "$SOURCE_DIR"
# Pull the currently-checked-out branch from the image build. We don't
# blindly bind to ``midnight`` here because an admin might want to
# rebuild the image against a different branch via the Dockerfile
# build arg; honour whatever branch git already has tracked.
TRACKING_BRANCH=$(git symbolic-ref --short HEAD 2>/dev/null || echo midnight)
git fetch --depth 1 origin "$TRACKING_BRANCH" 2>&1 || true
git reset --hard FETCH_HEAD 2>&1
log "simc branch=$TRACKING_BRANCH HEAD=$(git rev-parse --short HEAD)"

log "== Step 2/6: pull live DBC data from WoW CDN =="
# casc_extract downloads a few hundred MB on first run; subsequent
# runs are incremental thanks to the on-disk cache directory.
# ``-m batch --cdn`` reads the file list from ``dbfile`` (next to the
# script) and writes one ``<build>/DBFilesClient/`` + ``<build>/GameTables/``
# subdir under ``-o wow``. The canonical Windows ``WinGenerateSpellData.bat``
# uses exactly this invocation.
cd "$SOURCE_DIR/casc_extract"
python3 casc_extract.py -m batch --cdn -o wow 2>&1 | tail -40

# Output layout: ./wow/<patch-build>/DBFilesClient + ./wow/<patch-build>/GameTables.
# We pick the most-recently-modified <patch-build> directory because casc_extract
# may carry forward older builds it has cached.
LIVE_BUILD_DIR=$(ls -dt "$SOURCE_DIR"/casc_extract/wow/*/ 2>/dev/null | head -1 | sed 's:/$::')
if [ -z "$LIVE_BUILD_DIR" ] || [ ! -d "$LIVE_BUILD_DIR/DBFilesClient" ]; then
    log "ERROR: casc_extract produced no DBFilesClient directory under wow/"
    exit 2
fi
LIVE_BUILD=$(basename "$LIVE_BUILD_DIR")
INPUT_BASE="$SOURCE_DIR/casc_extract/wow"
log "live build: $LIVE_BUILD"
log "live DBC dir: $LIVE_BUILD_DIR/DBFilesClient"

log "== Step 3/6: layer admin-uploaded DBCache.bin (if any) =="
mkdir -p "$SOURCE_DIR/dbc_extract3/cache/live"
if [ -n "$DBCACHE_UPLOAD" ] && [ -f "$DBCACHE_UPLOAD" ]; then
    cp "$DBCACHE_UPLOAD" "$SOURCE_DIR/dbc_extract3/cache/live/DBCache.bin"
    log "DBCache.bin layered ($(stat -c %s "$DBCACHE_UPLOAD") bytes)"
else
    # Remove any leftover from a previous build so we don't accidentally
    # ship stale hotfix data with fresh CDN DBCs.
    rm -f "$SOURCE_DIR/dbc_extract3/cache/live/DBCache.bin"
    log "no DBCache.bin uploaded — using CDN-only data"
fi

log "== Step 4/6: regenerate simc data headers =="
cd "$SOURCE_DIR/dbc_extract3"
# generate.sh signature: ``[ptr] <build> <input_base> [hotfix]``.
# The first positional ``ptr`` is OPTIONAL — for live builds we skip
# it entirely (passing the string ``live`` was my earlier bug; the
# script then treated "live" as the build identifier and crashed on
# the malformed version string). Hotfix path is optional and only
# applied when an admin-uploaded DBCache.bin is present.
if [ -f "$SOURCE_DIR/dbc_extract3/cache/live/DBCache.bin" ]; then
    HOTFIX_ARG="$SOURCE_DIR/dbc_extract3/cache/live/DBCache.bin"
    ./generate.sh "$LIVE_BUILD" "$INPUT_BASE" "$HOTFIX_ARG" 2>&1 | tail -60
else
    ./generate.sh "$LIVE_BUILD" "$INPUT_BASE" 2>&1 | tail -60
fi

log "== Step 5/6: rebuild simc binary =="
cd "$SOURCE_DIR"
mkdir -p build
cd build
# ``BUILD_GUI=OFF`` skips the Qt-based SimulationCraft GUI — we only
# need the CLI binary. Without this, cmake fails on missing Qt6.
cmake -DCMAKE_BUILD_TYPE=Release -DBUILD_GUI=OFF .. 2>&1 | tail -15
make -j"$JOBS" simc 2>&1 | tail -30

NEW_BIN="$SOURCE_DIR/build/simc"
if [ ! -x "$NEW_BIN" ]; then
    log "ERROR: build finished but $NEW_BIN is not executable"
    exit 3
fi

log "== Step 6/6: install new simc binary =="
# Atomic swap via rename: write next to the old binary, then ``mv``.
# Avoids the brief window where the file exists but isn't fully written.
install -m 0755 "$NEW_BIN" "${TARGET_BIN}.new"
mv "${TARGET_BIN}.new" "$TARGET_BIN"
log "installed: $("$TARGET_BIN" spell_query=spell.id=1 2>&1 | head -1)"
log "DONE"
