---
description: Force-regenerate one or more assets by name (overwriting the existing PNG + WebP). Useful when you don't like the first pass.
argument-hint: "<name_or_regex> [additional notes to fold into the prompt]"
---

Regenerate the asset(s) matching `$ARGUMENTS` even if they already exist.

Steps:

1. Parse `$ARGUMENTS`:
   - First whitespace-separated token = the name or regex to match against `suggested_name` in `.claude/pending-assets.json` (or against existing filenames in the auto-detected images directory if nothing is pending).
   - Rest of the arguments = extra prompt guidance to fold into the crafted prompt (e.g. *"more muted palette, less crowded"*).

2. Show the candidate list before doing anything: *"Matched 3 assets: hero-home, hero-pricing, hero-about. Proceed? (y / refine / no)"*. If the user says refine, loop until they're happy.

3. For each matched asset:
   - If present in `pending-assets.json`, reuse its `source_file` + `context_snippet` for routing.
   - Else, derive params from the filename alone using `scripts/name_to_params.py`.
   - Refresh `brand-preset.json` if older than 24 h.
   - Craft a fresh prompt (use the 5-component formula from `SKILL.md`), and fold in the user's extra guidance as a style modifier.
   - Generate with `--overwrite`:

     ```bash
     python3 "${CLAUDE_PLUGIN_ROOT}/scripts/generate_image.py" \
       --name "<name>" \
       --prompt "<new prompt>" \
       --context "<context or empty>" \
       --overwrite \
       --project-root "${CLAUDE_PROJECT_DIR}"
     ```

4. Report: for each regenerated asset, show the new file path, the new sha256, the cost, and a one-line diff of what changed in the prompt vs. the original (so the user can see why this pass is different).

Common failure modes:

- Regex matches zero assets → show the list of known suggested names and offer to take a freeform idea instead.
- Source placeholder has since been replaced with a real asset → ask before overwriting.
