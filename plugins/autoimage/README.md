# `autoimage` plugin

Auto-detect missing or placeholder images in frontend files and generate
brand-aligned assets on demand, via Claude Code. The user picks ONE
provider per batch (OpenAI `gpt-image-2` or Google
`gemini-3.1-flash-image-preview`) — both can produce every asset type,
and mixing them within one project is left to explicit opt-in.

## What it does

1. You edit a `.jsx` / `.tsx` / `.html` / `.css` / `.vue` / `.svelte` / `.astro` file.
2. A `PostToolUse` hook runs `scripts/scan_missing.py` against the edited file and appends anything suspect to `.claude/pending-assets.json`:
   - empty `src=""` / `src=''`
   - known placeholder services (picsum, via.placeholder, placehold.co, dummyimage, placekitten, unsplash `/random`, loremflickr, fakeimg, …)
   - local file references that do not resolve on disk
   - `import X from './missing.png'` imports with no file
   - `TODO` / `FIXME` comments mentioning an image
3. When you say *"dobierz obrazy do strony"* / *"przygotuj brakujące obrazy"* / *"fill the missing images"* / *"prepare assets for this page"*, the `auto-image` skill activates:
   - detects brand from `tailwind.config.*`, `package.json`, `README.md`, main layout
   - picks the image provider per the user-driven rules
   - crafts a 5-component prompt per asset using the brand palette, mood, and typography
   - calls the provider, post-processes to exact target dimensions, writes `PNG` + `WebP`
   - patches the source files to reference the new assets
   - logs every generation row to `.claude/generation-log.csv`

## Provider choice — one per batch

Resolution order:

1. **Explicit override** — CLI `--provider openai|gemini`, or natural
   language ("use Gemini", "w OpenAI").
2. **Project preset** — `.claude/brand-preset.json → preferred_provider`.
3. **Single-key auto** — if only one of `OPENAI_API_KEY` /
   `GEMINI_API_KEY` is set, use that.
4. **Both keys, no preference** — the skill asks the user once and
   optionally saves the answer as the project default.

Informational warnings are still surfaced (e.g. "this asset has readable
text; `gpt-image-2` renders baked-in text more reliably"), but they
never override the user's choice.

### Provider strengths (for your own choice)

|  | `gpt-image-2` (OpenAI) | `gemini-3.1-flash-image-preview` (Google) |
| :-- | :-- | :-- |
| Baked-in text | **Very reliable** | Often misspells |
| Native transparency | Yes (`background=transparent`) | No (needs `rembg` post-process) |
| Cost / image (1024² high) | $0.019 | $0.039 |
| Free tier | No (needs $5 billing min.) | Yes |
| Aspect ratios | 3 fixed sizes | 7 aspect ratios |

## Install

From the marketplace:

```
/plugin marketplace add github:Desima-AP/autoimage-claude
/plugin install autoimage@desima-plugins
```

Or for local dev:

```bash
git clone git@github.com:Desima-AP/autoimage-claude.git
claude --plugin-dir /path/to/autoimage-claude/plugins/autoimage
```

## Requirements

- Python ≥ 3.9 with `Pillow` (`pip install Pillow`)
- Optional: `rembg` — only needed for transparent-PNG output via Gemini
- `OPENAI_API_KEY` in `$CLAUDE_PROJECT_DIR/.env` or process env (for `gpt-image-2`)
- `GEMINI_API_KEY` in same (for `gemini-3.1-flash-image-preview`)

Quick check:

```bash
python3 scripts/setup.py
```

## Slash commands

- `/design-scan` — full project audit of missing assets, summary, offer to generate.
- `/design-regen <name|regex>` — force-regenerate a specific asset (overwrites existing file).
- `/design-brand` — interactive editor for `.claude/brand-preset.json`, including `preferred_provider`.

## State files (created in `$CLAUDE_PROJECT_DIR/.claude/`)

| File | Purpose |
| :-- | :-- |
| `pending-assets.json` | Queue of detected missing / placeholder assets |
| `brand-preset.json` | Detected brand (palette, mood, typography, tone, preferred_provider) — editable |
| `generation-log.csv` | One row per generation: timestamp, target, model, prompt, cost est., sha256 |

## Target dimension map (driven by file / variable naming)

| Name pattern | Aspect | Target | Generation size |
| :-- | :-- | :-- | :-- |
| `hero*`, `banner*` | 16:9 | 1920×1080 | 1536×1024 (upscale) |
| `og*`, `og-image*` | ~1.91:1 | 1200×630 | 1536×1024 (crop) |
| `icon*` | 1:1 | 512×512 transparent | 1024×1024 |
| `avatar*` | 1:1 portrait | 512×512 | 1024×1024 |
| `feature*`, `card*` | 4:3 | 1024×768 | 1536×1024 (crop) |
| `bg-*`, `background*` | viewport | 1920×1080 | 1536×1024 high |
| `thumb*` | 16:9 | 1280×720 | 1536×1024 (crop) |
| `logo*` | 1:1 | 1024×1024 transparent | 1024×1024 |
| default | 1:1 | 1024×1024 | 1024×1024 |

## Development

```bash
# run the unit tests
python3 -m unittest discover -s tests

# env check
python3 scripts/setup.py
```

## License

MIT — see the repository `LICENSE` file.
