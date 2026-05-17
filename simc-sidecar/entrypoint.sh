#!/bin/sh
# Sidecar entrypoint — pick the newer simc binary (volume-cached or
# image-bundled) before launching the FastAPI server.
#
# Two locations carry a simc:
#
#   /app/SimulationCraft   — volume-mounted. Persists across container
#                            recreates. Receives the self-built binary
#                            when an admin clicks "Rebuild" in the UI.
#
#   /opt/simc-bundled      — frozen at image build. Whatever upstream
#                            ships in simulationcraftorg/simc:latest at
#                            ``docker build`` time. Updated when the
#                            sidecar image itself is rebuilt or pulled.
#
# On every boot we read the version banner from both and use whichever
# carries a newer (hotfix-date, WoW-build) tuple. So:
#   * First boot: volume is empty -> seed from bundled.
#   * After admin "Rebuild": self-built lives in volume, wins on next
#     boot if it's newer than upstream.
#   * After admin "Pull latest + recreate": bundled may be newer than
#     the cached self-built -> bundled wins automatically.
# The user never has to remember which path was last touched; the
# sidecar always runs the freshest binary available to it.
set -eu

BUNDLED=/opt/simc-bundled
ACTIVE=/app/SimulationCraft

if [ ! -f "$ACTIVE/simc" ]; then
    echo "[entrypoint] no simc at $ACTIVE — seeding from $BUNDLED"
    mkdir -p "$ACTIVE"
    cp -a "$BUNDLED"/. "$ACTIVE"/
fi

probe() {
    [ -x "$1" ] || { echo ""; return; }
    "$1" spell_query=spell.id=1 2>/dev/null | head -1 || true
}

ACTIVE_BANNER=$(probe "$ACTIVE/simc")
BUNDLED_BANNER=$(probe "$BUNDLED/simc")
echo "[entrypoint] volume  : ${ACTIVE_BANNER:-<missing>}"
echo "[entrypoint] bundled : ${BUNDLED_BANNER:-<missing>}"

export ACTIVE_BANNER BUNDLED_BANNER
NEWER=$(python3 - <<'PYEOF'
import os
import re


def parse(line: str) -> tuple[str, int]:
    """Pull (hotfix-date, WoW-build) out of a simc version banner. We
    only need a *total order* across the two binaries — exact format
    parsing isn't required, just a stable comparison key. Falls back
    gracefully on banners that don't include the hotfix date so a
    pristine upstream image without that field still gets compared."""
    line = line or ""
    m = re.search(r"hotfix (\d{4}-\d{2}-\d{2})/(\d+)", line)
    if m:
        return (m.group(1), int(m.group(2)))
    m = re.search(r"World of Warcraft \d+\.\d+\.\d+\.(\d+)", line)
    if m:
        return ("0000-00-00", int(m.group(1)))
    return ("0000-00-00", 0)


active = parse(os.environ.get("ACTIVE_BANNER", ""))
bundled = parse(os.environ.get("BUNDLED_BANNER", ""))
print("bundled" if bundled > active else "active")
PYEOF
)

if [ "$NEWER" = "bundled" ]; then
    echo "[entrypoint] image-bundled simc is newer — promoting to active"
    cp -a "$BUNDLED"/. "$ACTIVE"/
else
    echo "[entrypoint] volume-cached simc is current — keeping"
fi

exec python3 -u /sidecar/server.py
