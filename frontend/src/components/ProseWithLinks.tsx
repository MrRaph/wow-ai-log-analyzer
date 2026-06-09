"use client";

import { Fragment, type ReactNode } from "react";

import { ItemLink } from "@/components/ItemLink";
import { SpellLink } from "@/components/SpellLink";
import type { Locale } from "@/i18n/config";

interface Props {
  text: string | null | undefined;
  locale: Locale;
  /**
   * The ``_localized_names`` map the backend stitches into every
   * structured analysis. Keys look like ``spell:<id>`` / ``item:<id>`` /
   * ``talent:<id>``. Used as the display label when the AI's own label
   * inside the markdown is missing or just the raw id.
   */
  nameMap?: Record<string, string>;
  /**
   * ``_talent_spell_ids``: maps a ``TraitNodeEntry.ID`` (what WCL ships
   * as a "talent id" in combatantInfo.talentTree) to the *spell* ID
   * Wowhead actually understands. Talents render as a /spell/<id>
   * Wowhead link using this map; if a talent has no entry here we
   * fall back to plain bold text (no link) rather than emit a broken
   * /spell/<traitNodeEntryId> URL.
   */
  talentSpellIds?: Record<string, number>;
  /** Game version slug (e.g. "tbc", "wotlk", "classic") for Wowhead URLs. */
  gameVersion?: string;
  className?: string;
}

/**
 * Renders an AI-produced prose block with inline markdown-style
 * references replaced by proper Wowhead-linked components.
 *
 * Supported reference syntax (a strict subset of standard markdown
 * links — we don't try to do general markdown):
 *
 *     [Mana Tea](spell:115151)
 *     [Algari Mana Potion](item:212017)
 *     [Tea Time](talent:124683)
 *
 * Anything else stays as plain text; ``\n`` characters render as
 * line breaks (mirroring the existing ``whitespace-pre-line`` style).
 *
 * Backward-compatible: if the AI's output has no inline references,
 * this is just an identity render of the text.
 */
export function ProseWithLinks({
  text,
  locale,
  nameMap = {},
  talentSpellIds = {},
  gameVersion,
  className,
}: Props) {
  if (!text) return null;
  const segments = parseInlineRefs(text, locale, nameMap, talentSpellIds, gameVersion);
  // Render as ``<span>`` (not ``<p>``) so callers can drop it inside any
  // block element — including headings and table cells — without
  // producing invalid nested-paragraph HTML. The ``whitespace-pre-line``
  // class still honours ``\n`` characters from the AI output.
  return (
    <span
      className={`block whitespace-pre-line ${className ?? "text-sm text-zinc-200"}`}
    >
      {segments.map((seg, i) =>
        typeof seg === "string" ? (
          <Fragment key={i}>{seg}</Fragment>
        ) : (
          <Fragment key={i}>{seg}</Fragment>
        ),
      )}
    </span>
  );
}

/**
 * ``true`` iff the prose contains at least one inline ``[label](kind:id)``
 * reference. Lets callers (specifically the finding card) decide whether
 * to also show the legacy chip-list of ``related_*_ids`` underneath — we
 * show it only as a fallback when no inline refs are present, since
 * showing both is visual clutter.
 */
export function hasInlineRefs(text: string | null | undefined): boolean {
  if (!text) return false;
  return INLINE_REF_REGEX.test(text);
}

// `g` flag on the global pattern is reset between calls via .lastIndex.
const INLINE_REF_REGEX = /\[([^\]\n]+)\]\((spell|item|talent):(\d+)\)/g;

function parseInlineRefs(
  text: string,
  locale: Locale,
  nameMap: Record<string, string>,
  talentSpellIds: Record<string, number>,
  gameVersion?: string,
): ReactNode[] {
  const out: ReactNode[] = [];
  // Local copy of the regex so we don't fight other callers over lastIndex.
  const re = new RegExp(INLINE_REF_REGEX.source, "g");
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) {
      out.push(text.slice(last, m.index));
    }
    const [, rawLabel, kind, idStr] = m;
    const id = Number(idStr);
    // Prefer the AI's own label, fall back to the localised name from
    // the resolver map, and finally to a numeric placeholder. ``nameMap``
    // keys are ``kind:id`` for all three kinds.
    const fallback =
      (rawLabel && rawLabel.trim()) ||
      nameMap[`${kind}:${id}`] ||
      `${kind} #${id}`;
    if (kind === "spell") {
      out.push(
        <SpellLink
          key={`s-${m.index}-${id}`}
          spellId={id}
          locale={locale}
          fallback={fallback}
          gameVersion={gameVersion}
        />,
      );
    } else if (kind === "item") {
      out.push(
        <ItemLink
          key={`i-${m.index}-${id}`}
          itemId={id}
          locale={locale}
          fallback={fallback}
          gameVersion={gameVersion}
        />,
      );
    } else {
      // talent: link via the underlying spell ID if we have one. Without
      // it we'd produce a /spell/<traitNodeEntryId> URL that points to
      // an unrelated MoP-era spell — bold text is safer than a wrong
      // link.
      const spellId = talentSpellIds[String(id)];
      if (spellId) {
        out.push(
          <SpellLink
            key={`t-${m.index}-${id}`}
            spellId={spellId}
            locale={locale}
            fallback={fallback}
            gameVersion={gameVersion}
          />,
        );
      } else {
        out.push(
          <strong
            key={`tb-${m.index}-${id}`}
            className="font-semibold text-zinc-100"
          >
            {fallback}
          </strong>,
        );
      }
    }
    last = re.lastIndex;
  }
  if (last < text.length) {
    out.push(text.slice(last));
  }
  return out;
}
