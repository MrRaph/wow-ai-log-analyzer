/**
 * Parses a /simc profile paste for the embedded talent loadouts so the
 * Simulate page can offer them as checkboxes instead of forcing the
 * user to copy/paste talent strings by hand.
 *
 * The in-game ``/simc`` command always emits ONE uncommented
 * ``talents=...`` line (the currently-active loadout) plus zero or more
 * commented blocks of the shape:
 *
 *   # Saved Loadout: <name>
 *   # talents=<string>
 *
 * We extract both — the active one carries an "Active" / "Aktiv" hint
 * (so the user knows which the in-game character is currently playing)
 * and the saved ones keep their human-readable label.
 */

export interface DetectedLoadout {
  /** Human-readable label. "Aktiv" / "Active" for the uncommented entry,
   * the saved-loadout name otherwise. */
  name: string;
  /** The ``talents=...`` line in full, including the ``talents=`` prefix
   * so the backend can drop it into the profile as-is. */
  talents: string;
  /** True for the uncommented entry — i.e. the talents the character
   * is currently playing in-game. */
  isActive: boolean;
}

const _ACTIVE_RE = /^\s*talents\s*=\s*\S+\s*$/gm;
// Group 1 = saved-loadout label, Group 2 = the talents string (after `talents=`)
const _SAVED_RE =
  /^\s*#\s*Saved Loadout:\s*(.+?)\s*\r?\n\s*#\s*talents\s*=\s*(\S+)\s*$/gim;

/**
 * Parse a /simc profile for embedded talent loadouts. Returns at most one
 * "active" entry plus every named saved loadout, deduplicated by talent
 * string. Order: active first, then saved in source order.
 */
export function parseSimcLoadouts(profile: string): DetectedLoadout[] {
  if (!profile || !profile.includes("talents=")) return [];

  const seen = new Set<string>();
  const out: DetectedLoadout[] = [];

  // 1) Active (uncommented) talents=… line. There should be at most one
  //    in a clean /simc paste; if a user accidentally pasted multiple
  //    we keep the first as the "Active" one.
  _ACTIVE_RE.lastIndex = 0;
  const activeMatch = _ACTIVE_RE.exec(profile);
  if (activeMatch) {
    const line = activeMatch[0].trim();
    if (!seen.has(line)) {
      seen.add(line);
      out.push({ name: "Active", talents: line, isActive: true });
    }
  }

  // 2) Saved loadout blocks. We DO NOT drop duplicates by code anymore —
  //    users often save the same build under multiple names ("Raid ST",
  //    "Raid Imp", "Raid Dragons" with identical talent codes), and
  //    silently hiding them confuses the picker. Instead, when we see
  //    a code we already have, we *merge* the names so the entry shows
  //    up once with "Raid ST / Raid Imp / Raid Dragons".
  _SAVED_RE.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = _SAVED_RE.exec(profile)) !== null) {
    const rawName = m[1];
    const rawTalents = m[2];
    if (!rawName || !rawTalents) continue;
    const name = rawName.trim();
    const line = `talents=${rawTalents.trim()}`;
    if (seen.has(line)) {
      const existing = out.find((l) => l.talents === line);
      if (!existing) continue;
      if (existing.isActive && existing.name === "Active") {
        // First saved name we see for the active build — replace the
        // generic "Active" label so the row reads e.g. "Raid ST".
        existing.name = name;
      } else if (!existing.name.split(" / ").includes(name)) {
        // Another saved loadout with the same code under a different
        // name — append it so the picker shows all aliases.
        existing.name = `${existing.name} / ${name}`;
      }
      continue;
    }
    seen.add(line);
    out.push({ name, talents: line, isActive: false });
  }

  return out;
}
