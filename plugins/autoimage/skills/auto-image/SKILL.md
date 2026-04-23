---
name: auto-image
description: "Automatically fills missing or placeholder images in frontend projects (JSX, TSX, HTML, CSS, Vue, Svelte) with brand-aligned, freshly generated assets. Activates on requests like 'dobierz obrazy do strony', 'przygotuj brakujące obrazy', 'fill missing images', 'generate placeholders', 'make images that match the brand', 'prepare assets for this page', and whenever `.claude/pending-assets.json` contains entries. Also activates when the user pastes a placeholder URL (picsum, via.placeholder, unsplash random) or an empty src and asks for a real image. The user chooses ONE provider (OpenAI gpt-image-2 or Google gemini-3.1-flash-image-preview) per batch — both can produce every asset type. The plugin never silently splits a batch between providers, because mixing models within one project causes inconsistent aesthetics."
argument-hint: "[idea or filter]"
metadata:
  version: "0.2.1"
---

# auto-image — brand-aligned asset generation for frontend projects

You are the pipeline that turns the queue at `.claude/pending-assets.json`
into real image files on disk. You craft prompts; the Python scripts
handle API calls, resizing, and logging. **The user picks the provider —
you never auto-split a batch between OpenAI and Gemini.**

## When you MUST run this skill

Run without asking for confirmation (beyond the summary + provider
checkpoint below) when the user says:

- *"dobierz obrazy do strony"* / *"przygotuj brakujące obrazy"* / *"uzupełnij placeholdery"*
- *"fill the missing images"* / *"generate the placeholders"*
- *"make images that match the brand"* / *"prepare assets for this page"*
- *"use real images instead of placeholders"*

Also run when:

- `.claude/pending-assets.json` has any entry with `"status": "pending"` and the user asks anything adjacent to images.
- The user pastes / shows code with an obvious placeholder (`picsum`, `via.placeholder`, empty `src`, a TODO mentioning an image) and asks you to "fix it" or "make it real".

## Provider policy (read before every batch)

Both providers can generate every asset type. They differ in strengths
(OpenAI renders baked-in text more reliably; Gemini is cheaper/faster for
UI-scale assets), but the plugin does NOT decide for the user. One
provider per batch keeps aesthetics consistent.

Resolve the provider in this order:

1. **Explicit request in the current message.** If the user said
   "użyj Gemini" / "use ChatGPT" / "w OpenAI" / "via Gemini", pass
   `--provider openai|gemini` to every generation call in this batch.
2. **Project preset.** Read
   `$CLAUDE_PROJECT_DIR/.claude/brand-preset.json → preferred_provider`.
   If it's `"openai"` or `"gemini"`, use that for every call.
3. **Single-key auto.** If only one of `OPENAI_API_KEY` /
   `GEMINI_API_KEY` is configured, use that provider and say so once.
4. **Both keys, no preference → ask once.** Show a short prompt to the
   user:

   > *"Both OpenAI and Gemini keys are configured and no preferred
   > provider is saved. Which should I use for this batch?*
   > *(o) OpenAI gpt-image-2 — best for text, hero images, OG cards
   > (g) Gemini 3.1 Flash — cheaper, faster, great for UI assets
   > (save) I'll save your choice to brand-preset.json for next time"*

   Remember the answer for the whole batch. If the user picks "save",
   write `preferred_provider` into the preset.
5. **No keys.** Surface the error with a one-line fix for each
   provider (see setup.py output in README).

## Pipeline (follow in order)

### 1. Prepare state

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/detect_brand.py" "${CLAUDE_PROJECT_DIR}"
```

This refreshes `.claude/brand-preset.json`. Read it for palette, mood,
copy tone, typography, and `preferred_provider`.

```bash
cat "${CLAUDE_PROJECT_DIR}/.claude/pending-assets.json" 2>/dev/null || echo '{"assets":[]}'
```

If the pending list is empty and the user asked for images to be generated, run a full project scan first:

```bash
find "${CLAUDE_PROJECT_DIR}" \
  -type f \( -name "*.jsx" -o -name "*.tsx" -o -name "*.html" -o -name "*.css" \
            -o -name "*.vue" -o -name "*.svelte" -o -name "*.astro" \) \
  -not -path "*/node_modules/*" -not -path "*/.next/*" -not -path "*/dist/*" \
  -print0 | while IFS= read -r -d '' f; do
    printf '{"tool_input":{"file_path":"%s"},"cwd":"%s"}' "$f" "${CLAUDE_PROJECT_DIR}" \
      | python3 "${CLAUDE_PLUGIN_ROOT}/scripts/scan_missing.py" >/dev/null 2>&1
  done
```

### 2. Pick the provider (see Provider policy above)

Decide and then state clearly: *"Using **OpenAI gpt-image-2** for all
N assets in this batch"* (or Gemini). If the choice came from
`preferred_provider`, note that too. If the user picked "save",
update the preset:

```bash
python3 -c "
import json, pathlib, sys
p = pathlib.Path('${CLAUDE_PROJECT_DIR}/.claude/brand-preset.json')
d = json.loads(p.read_text())
d['preferred_provider'] = sys.argv[1]
p.write_text(json.dumps(d, indent=2, ensure_ascii=False))
" openai   # or: gemini
```

### 3. Present the queue to the user

Show a compact summary table before generating:

| # | source file | kind | reference | suggested name |
| - | ----------- | ---- | --------- | -------------- |

Group by `source_file`. Add one summary line:

- **N assets** will be generated with **<provider>**
- rough total cost: N × rate_per_image (see
  `references/model-routing.md`)
- any warnings from the router (text-heavy on Gemini, transparent on
  Gemini without rembg, etc.) — show them but do NOT switch providers
  without the user's say-so.

Then ask: *"Generate all N now? (y / select / skip)"*. Default is yes
if the user's triggering phrase was unambiguous (e.g. "dobierz obrazy,
wszystkie").

### 4. Craft one prompt per asset

For each asset, build the prompt with the 5-component formula. Read
`references/prompt-templates.md` for the full library; below is the
short version.

**The 5 components, in order:**

1. **Subject** — concrete visual thing (a smiling founder, a geometric
   glyph, a mountain range). Never abstract nouns like "technology" or
   "innovation".
2. **Action / state** — what's happening (leaning over a laptop,
   glowing, at rest, unfolding).
3. **Location / context** — where (sunlit studio, minimal grid backdrop,
   above the fold of a SaaS homepage).
4. **Composition** — framing (rule-of-thirds, centred, medium-wide,
   overhead).
5. **Style** — medium + lighting + brand palette (editorial photo on
   Portra 400, flat vector with 2px strokes, isometric 3D render with
   soft shadows; lit by golden-hour rim light; primary `#0B5FFF`,
   accent `#F97316`).

**Always bake the brand palette into the prompt** using the hex values
from `brand-preset.json → palette`. *"colour palette: deep indigo
#1E1B4B as primary, warm coral #F97316 as accent, off-white #FAFAFA
background."*

**Always reflect the brand mood.** Quote the top 2 items from
`mood` in the style component.

**Asset-type rules (from `scripts/name_to_params.py`):**

| `hint_type` | Prompt emphasis |
| :---------- | :-------------- |
| hero / banner | Cinematic, horizontal composition, leaves room for headline text at top-left or centre; 16:9 feel |
| og | Centred focal point, text-safe margin, readable at 1200×630 thumbnail size |
| icon | Single glyph, flat vector, no background (transparent), strokes 2px equivalent at 64px |
| logo | Geometric mark, no photographic realism, transparent background, 3–4 colours max |
| avatar | Portrait framing (shoulders up), soft background that doesn't compete, friendly expression |
| feature / card | Product-mode composition, clean studio backdrop, 4:3 feel |
| bg / background | Low-contrast, atmospheric, designed to sit behind copy (do NOT make the subject dominant) |
| default | Square, balanced composition |

**Banned words** (hurt both gpt-image-2 and Gemini output quality):
*"8K", "masterpiece", "ultra-realistic", "high resolution", "best
quality"*. Never include them. Use the `quality` parameter instead —
the router already sets it.

### 5. Generate, one asset at a time

Call the generator with an **explicit provider** each time, so the
batch can't drift:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/generate_image.py" \
  --name "<suggested_name>" \
  --prompt "<the crafted 5-component prompt>" \
  --context "<context_snippet>" \
  --asset-id "<pending entry id>" \
  --provider "<openai|gemini>" \
  --project-root "${CLAUDE_PROJECT_DIR}"
```

Add `--transparent` only when the asset type demands it (icon, logo).
Add `--overwrite` only on `/design-regen`.

The script prints a JSON result. Verify `"ok": true`, then inspect the
`png` / `webp` paths and sha256.

If `"ok": false`:

- `OPENAI_API_KEY missing` / `GEMINI_API_KEY missing` → tell the user
  which key is missing and what to add to `.env`. **Do not silently
  switch providers mid-batch** — ask the user first.
- `provider choice required` → step 2 was skipped; ask the user.
- Safety block (Gemini `IMAGE_SAFETY` / OpenAI policy rejection) →
  rephrase with abstraction (see `references/prompt-templates.md` →
  Safety Rephrase) and retry **once**. After that, ask the user.
- Network / 5xx → the script already retried 3× with backoff. Surface
  the error and offer to retry the single asset.

### 6. Replace placeholders in source files

After a successful generation, patch the referring source file:

- Replace the placeholder / empty / missing reference with the new
  relative path. Use the Edit tool with a narrow `old_string` that
  includes surrounding context (the `<img` tag, the `url(...)`, or the
  import statement), not a bare value match.
- For CSS: `url('/images/hero.png')` (root-relative, forward slash).
- For JSX in a Next.js project: prefer `<Image src="/images/hero.png"
  ... />` if the project uses `next/image`, otherwise keep `<img>`.
- For imports: `import hero from "./hero.png";` stays — just create the
  file in the same directory the import resolves to.

Do **not** auto-replace if:

- The placeholder is in a test file (`*.test.*`, `*.spec.*`,
  `__tests__`) — it may be intentional.
- The placeholder is inside a string literal whose surrounding code
  suggests it's a fixture or example.

### 7. Final report

After the batch, post a compact summary — mention the **single
provider** used, so the user can confirm nothing drifted:

```
Generated 5 assets with OpenAI gpt-image-2:
  ✓ public/images/hero-home.png        ($0.025)
  ✓ public/images/feature-analytics.png ($0.019)
  ✓ public/images/og-home.png           ($0.025)
  ✓ public/images/avatar-jane.png       ($0.019)
  ✗ public/images/avatar-tom.png        (IMAGE_SAFETY — see notes)

Total: $0.088 (4 generated, 1 failed)
Files patched: src/pages/index.tsx, src/components/Hero.tsx
Log: .claude/generation-log.csv
```

If you want to switch providers for a future batch, run /design-brand
and pick a different `preferred_provider`.

## Prompt quality checklist

Before calling `generate_image.py`, verify the prompt:

- [ ] Contains a concrete subject (not just a concept)
- [ ] Contains hex palette values from `brand-preset.json`
- [ ] Reflects the brand mood (first 2 items from `mood`)
- [ ] Matches the `hint_type` emphasis
- [ ] Has no banned words ("8K", "masterpiece", ...)
- [ ] For text-in-image: quotes the exact text (e.g. `the text "Ship faster"`)
- [ ] For transparent output: says "on a plain neutral background"

## References (load on demand)

- `references/prompt-templates.md` — full 5-component library with
  per-domain templates
- `references/model-routing.md` — provider capabilities, cost table,
  when to prefer one over the other
- `references/brand-detection.md` — brand-preset.json schema, including
  `preferred_provider` and field locking
