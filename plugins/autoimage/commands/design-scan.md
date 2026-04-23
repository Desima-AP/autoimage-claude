---
description: Full project audit — scan every frontend file for missing or placeholder images, refresh brand-preset.json, and summarise the queue.
argument-hint: "[--generate]  (append to immediately generate all pending assets)"
---

Run a full `auto-image` scan over the project and show me the queue.

Steps to perform:

1. Refresh the brand preset:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/detect_brand.py" "${CLAUDE_PROJECT_DIR}"
   ```

2. Scan every frontend source file in the project, excluding `node_modules`, `.next`, `dist`, `build`, `.astro`, `.svelte-kit`:

   ```bash
   find "${CLAUDE_PROJECT_DIR}" \
     -type f \( -name "*.jsx" -o -name "*.tsx" -o -name "*.html" -o -name "*.css" \
               -o -name "*.scss" -o -name "*.vue" -o -name "*.svelte" -o -name "*.astro" \) \
     -not -path "*/node_modules/*" -not -path "*/.next/*" -not -path "*/dist/*" \
     -not -path "*/build/*" -not -path "*/.svelte-kit/*" \
     -print0 | while IFS= read -r -d '' f; do
       printf '{"tool_input":{"file_path":"%s"},"cwd":"%s"}' "$f" "${CLAUDE_PROJECT_DIR}" \
         | python3 "${CLAUDE_PLUGIN_ROOT}/scripts/scan_missing.py" >/dev/null 2>&1
     done
   ```

3. Show the resulting `.claude/pending-assets.json` as a readable table, grouped by `source_file`. Columns: kind, reference, suggested_name, status. Include the row count at the top.

4. For each pending entry, use `scripts/router.py` to determine the provider + cost, and add a "route" column + a running "total estimated cost" at the bottom.

5. If the user passed `--generate` as an argument (`$ARGUMENTS`), continue straight into the auto-image pipeline (Step 3 of `SKILL.md`) and generate everything. Otherwise, ask: *"Generate all N? Select specific names? Or just show the queue?"*

Briefly flag any `status: "error"` entries from prior runs so we can retry them or drop them.
