# Brand detection & editing

Load when the user asks why a certain palette was chosen, wants to
override a field, or needs to "lock" a value so re-detection doesn't
overwrite it.

## What gets detected

`scripts/detect_brand.py` writes `.claude/brand-preset.json` with:

```json
{
  "version": 1,
  "project_name": "acme-docs",
  "short_description": "Lightning-fast documentation for makers.",
  "palette": {
    "primary":   "#0B5FFF",
    "secondary": "#1E1B4B",
    "accent":    "#F97316",
    "neutral":   "#F5F5F4",
    "extras":    ["#10B981", "#EC4899"]
  },
  "mood":      ["technical", "minimal", "warm"],
  "copy_tone": "warm-casual",
  "typography": {
    "primary_font": "Inter",
    "display_font": "Space Grotesk"
  },
  "preferred_provider": "openai",
  "locked":    {
    "palette": false, "mood": false, "copy_tone": false,
    "typography": false, "preferred_provider": false
  },
  "updated_at": "2026-04-23T11:18:52+00:00"
}
```

### `preferred_provider`

Controls which image model the whole project uses:

- `"openai"` — every asset goes to `gpt-image-2`.
- `"gemini"` — every asset goes to `gemini-3.1-flash-image-preview`.
- `null` — ask the user once per batch (default for a fresh project).

This is the knob that keeps aesthetics consistent across a project. The
plugin does NOT route hero → OpenAI and icons → Gemini automatically,
because the seam between two models is visible in a design system.

A non-null value is **always preserved** on re-detection, even without
the corresponding lock — `detect_brand.py` has no way to infer it from
project files, so the user's choice is the ground truth.

### Sources read (in this order)

1. `tailwind.config.{js,ts,mjs,cjs}` — hex values in order of appearance
   fill the palette slots.
2. If no Tailwind config, scan `src/index.css`, `app/globals.css`,
   `styles/globals.css` for hex colours.
3. `package.json` — `name` → `project_name`, `description` →
   `short_description` (if no meta tag).
4. `README.md` (first 2000 chars) → mood keywords + tone via keyword
   matching.
5. Main layout (`app/layout.*`, `src/App.*`, `pages/_app.*`,
   `index.html`) → `<meta name="description">` overrides package
   description; `next/font/google(Inter)` import or `font-family:`
   CSS rule seeds typography.

### Palette slotting heuristic

- `primary`, `secondary`, `accent` = first three unique hex values.
- `neutral` = the colour with the smallest R/G/B channel spread among
  the first 16 hexes (only assigned if its spread < 30).
- `extras` = remaining up to 8 hexes.

This is a heuristic — always worth sanity-checking against the project's
design tokens.

### Mood inference

Keyword groups in `scripts/detect_brand.py → MOOD_KEYWORDS`. Top 4
matches by frequency become the mood list. "neutral" is the fallback
when nothing matches.

### Tone inference

Picks one of: `corporate-confident`, `warm-casual`, `technical-precise`,
`editorial-refined`, `neutral` — based on keyword signals in README +
description + meta.

## Editing the preset

### Manual edit

`.claude/brand-preset.json` is plain JSON. Edit any field, save, and the
next generation uses the new values.

### Locking a field

Set `locked.<field>: true` to prevent re-detection from overwriting it:

```json
"palette": { "primary": "#FF006E", ... },
"locked":  { "palette": true, "mood": false, ... }
```

Now if someone updates `tailwind.config.js` and re-runs
`scripts/detect_brand.py`, the palette stays pinned at `#FF006E`.

Run `/design-brand` for an interactive editor.

### Re-detecting from scratch

Delete the file (or a subset of fields) and re-run:

```bash
rm "${CLAUDE_PROJECT_DIR}/.claude/brand-preset.json"
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/detect_brand.py" "${CLAUDE_PROJECT_DIR}"
```

## Using the preset in a prompt

Quote the hex values verbatim in the style component:

> *"Colour palette: primary `#0B5FFF`, accent `#F97316`, neutral backdrop
> `#F5F5F4`. Typography reference: Inter for body, Space Grotesk for
> display. Mood: technical, minimal, warm."*

**Don't** paraphrase ("a blue-orange palette"). Hex values are specific;
natural-language colour names aren't.

## What the preset does NOT capture

- **Logo marks** — you have to describe them yourself.
- **Photographic treatment** (film stock, grain) — derive from mood.
- **Grid / layout system** — outside the preset's scope.
- **Copy length / voice examples** — only tonal class.

If any of these matter for the asset, add them explicitly to the prompt.
