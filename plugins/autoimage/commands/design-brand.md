---
description: Interactively review and edit the project's brand preset (.claude/brand-preset.json), including which AI provider the project uses for image generation.
argument-hint: "[show|detect|reset|provider <openai|gemini|null>]"
---

Review and/or edit the brand preset used by auto-image prompts.

Dispatch on `$ARGUMENTS`:

- `show` (default) — print `.claude/brand-preset.json` as a readable summary: project name, palette swatches as hex, mood, copy tone, typography, **preferred_provider**, which fields are locked, `updated_at`.

- `detect` — re-run `scripts/detect_brand.py`. Any field marked `locked: true` stays as-is. A non-null `preferred_provider` is also preserved automatically (it can't be inferred from code). Show a diff of what changed.

- `reset` — confirm first. Then delete `.claude/brand-preset.json` and rerun detection. `preferred_provider` returns to `null`, so the next batch will ask the user again.

- `provider <openai|gemini|null>` — direct shortcut: set `preferred_provider` without entering the interactive menu. Example: `provider gemini`.

Otherwise start the interactive dialog:

> *"Which field should I adjust?"*
>
> 1. Palette (primary / secondary / accent / neutral / extras)
> 2. Mood (comma-separated list, e.g. `editorial, minimal, warm`)
> 3. Copy tone (`corporate-confident` / `warm-casual` / `technical-precise` / `editorial-refined` / `neutral`)
> 4. Typography (primary_font, display_font — any string)
> 5. **preferred_provider** (`openai` / `gemini` / `null` — the default for image generation; null means ask every batch)
> 6. Lock / unlock a field so re-detection skips it
> 7. Nothing — I'm done

For each chosen field:

- Show the current value.
- Ask for the new value (with examples).
- Validate:
  - Palette: `#RRGGBB` or `#RGB`.
  - `copy_tone`: one of the allowed values.
  - `preferred_provider`: one of `openai`, `gemini`, `null`. Anything else is rejected with a hint.
  - Others: non-empty string.
- Write the updated JSON back.

Loop until the user picks option 7.

When the user changes `preferred_provider`, also surface which API key will be needed going forward (e.g. "set OPENAI_API_KEY in `.env` or shell env") and run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/setup.py"` to confirm the key is visible.

On exit, print a short summary of what changed and remind: "Next generation batch will use the updated preset — no need to rerun detection."
