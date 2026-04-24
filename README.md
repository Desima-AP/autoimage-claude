# autoimage-claude

> **Auto-generate brand-aligned images for frontend projects, directly from Claude Code.** A plugin marketplace by [Desima-AP](https://github.com/Desima-AP).

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Claude Code Plugin](https://img.shields.io/badge/Claude_Code-Plugin-6E40C9)](https://code.claude.com/)
[![OpenAI gpt-image-2](https://img.shields.io/badge/OpenAI-gpt--image--2-0B5FFF)](https://developers.openai.com/api/docs/models/gpt-image-2)
[![Gemini 3.1 Flash Image](https://img.shields.io/badge/Gemini-3.1_Flash_Image-4285F4)](https://ai.google.dev/gemini-api/docs/image-generation)

Stop hand-crafting prompts for every missing `<img>` and CSS `background-image`. This plugin watches your frontend code as you edit, catches placeholder URLs, empty `src=""`, broken local imports, and TODO comments about images, then — when you ask — generates real, on-brand assets, post-processes them to exact target dimensions, and wires them into the source files.

Works with **JSX, TSX, HTML, CSS, SCSS, Vue, Svelte, Astro, MDX**. Picks palette and mood from `tailwind.config.*` / `package.json` / `README.md` / your main layout automatically.

![autoimage banner](https://raw.githubusercontent.com/Desima-AP/autoimage-claude/main/docs/banner.webp)

> The banner above was generated **by this plugin**, calling the `autoimage` pipeline against an empty project — one prompt, one provider (`gpt-image-1.5`, auto-fallback from `gpt-image-2` while org verification is pending), post-processed to 1920×1080 and a 1280×640 social-preview variant. `$0.025` round-trip.

---

## Install

```bash
/plugin marketplace add github:Desima-AP/autoimage-claude
/plugin install autoimage@desima-plugins
```

Then restart or `/reload-plugins`. Confirm with `/help` — you should see `autoimage:auto-image` among the skills and the three slash commands below.

### Requirements

- Python ≥ 3.9 with `Pillow` (`pip install Pillow`)
- At least one API key: `OPENAI_API_KEY` and/or `GEMINI_API_KEY` (both is best). See [how to get them](#api-keys).
- Optional: `rembg` for transparent-PNG output when using Gemini (OpenAI does it natively).

Verify setup:

```bash
python3 ~/.claude/plugins/cache/desima-plugins/autoimage/<version>/scripts/setup.py
```

---

## What it does

Once installed, you work normally. The plugin runs in two modes:

**Background (automatic, scan-only).** Every time you `Edit` / `Write` / `MultiEdit` a frontend file, a `PostToolUse` hook scans it for:

- empty `src=""`, `src=''`, `src={""}`
- known placeholder services — `picsum.photos`, `via.placeholder.com`, `placehold.co`, `dummyimage.com`, `placekitten`, `source.unsplash.com`, `loremflickr`, `fakeimg.pl`, etc.
- local paths that don't resolve on disk (`./missing.png`, `/images/not-there.webp`)
- ES imports of missing image files
- `TODO` / `FIXME` comments mentioning an image

Findings land in `.claude/pending-assets.json`. No API calls. No surprise billing. No workflow interruption.

**Foreground (on-demand, generate).** Say one of these and the skill kicks in:

> *"dobierz obrazy do strony"*
> *"przygotuj brakujące obrazy"*
> *"fill the missing images"*
> *"generate the placeholders"*
> *"make images that match the brand"*
> *"prepare assets for this page"*

Claude then:

1. Refreshes the brand preset (palette, mood, typography, tone — detected from your project files).
2. Picks the image provider per user-driven rules (see [Provider choice](#provider-choice--user-driven-one-per-batch)).
3. Crafts a 5-component prompt per asset using your palette and mood.
4. Calls the provider, resizes/crops to exact target dimensions, writes `PNG` + `WebP`.
5. Patches the source files to reference the new assets.
6. Logs every row to `.claude/generation-log.csv`.

---

## Provider choice — user-driven, one per batch

Both providers can generate every asset type. The plugin **never silently splits a batch** between OpenAI and Gemini — mixing two models within one project causes inconsistent aesthetics, which is something you should opt into explicitly.

Resolution order:

1. **Explicit request in the current message** — *"use Gemini for these"*, *"w OpenAI"*, or `--provider openai|gemini` on the CLI.
2. **Project preset** — `.claude/brand-preset.json → preferred_provider` (`"openai"` / `"gemini"` / `null`).
3. **Single-key auto** — if only one of `OPENAI_API_KEY` / `GEMINI_API_KEY` is set, use that.
4. **Both keys, no preference** — the skill asks you once and optionally saves the answer as the project default.

Informational warnings still surface (e.g. *"this asset has readable text; `gpt-image-2` renders baked-in text more reliably"*), but they never override your choice.

### Quick provider strength guide

|  | `gpt-image-2` (OpenAI) | `gemini-3.1-flash-image-preview` (Google) |
| :-- | :-- | :-- |
| Baked-in text | **Very reliable** | Often misspells |
| Native transparency | Yes (`background=transparent`) | No (needs `rembg`) |
| Cost / image (1024² high) | $0.019 | $0.039 |
| Free tier | No (needs $5 billing min.) | Yes |
| Aspect ratios | 3 fixed sizes | 7 aspect ratios |

---

## Slash commands

- **`/design-scan`** — full project audit of missing assets, summary, optional batch generation.
- **`/design-regen <name_or_regex> [extra guidance]`** — force-regenerate a specific asset (overwrites existing file).
- **`/design-brand [show|detect|reset|provider <openai|gemini|null>]`** — interactive editor for `.claude/brand-preset.json`, including `preferred_provider`.

---

## API keys

### OpenAI (`gpt-image-2`, with automatic fallback)

1. Sign up at [platform.openai.com](https://platform.openai.com).
2. Add billing — $5 minimum — at [billing settings](https://platform.openai.com/settings/organization/billing).
3. Create a key at [api-keys](https://platform.openai.com/api-keys). Copy it — it's shown only once.
4. *(Optional, unlocks the flagship model)* **Verify your organization** at [organization settings](https://platform.openai.com/settings/organization/general) — OpenAI requires a one-time Stripe Identity check before new keys can call `gpt-image-2`. Propagates in ~15 minutes.

Without verification, the plugin automatically falls back to `gpt-image-1.5`, then `gpt-image-1` — same request schema, same post-processing, slightly different rendering style. The log records which model actually produced each image.

Cost: $0.019 per 1024² high-quality image on `gpt-image-2`; `gpt-image-1.5` has the same pricing; `gpt-image-1` is roughly 2× more expensive.

### Google Gemini (`gemini-3.1-flash-image-preview`)

1. Open [aistudio.google.com](https://aistudio.google.com), sign in with Google.
2. Click **Get API key** → **Create API key**.
3. No billing required on free tier (a few RPM / several hundred RPD).

Cost beyond free tier: $0.039 per image.

### Where to put the keys

The plugin reads, in this order:

1. Process environment (`export OPENAI_API_KEY=...`).
2. `.env` in the current project directory.

```bash
# in your project root
cat >> .env <<EOF
OPENAI_API_KEY=sk-proj-...
GEMINI_API_KEY=AIzaSy...
EOF
echo ".env" >> .gitignore
```

---

## State files (written to `$CLAUDE_PROJECT_DIR/.claude/`)

| File | Purpose |
| :-- | :-- |
| `pending-assets.json` | Queue of detected missing / placeholder assets |
| `brand-preset.json` | Detected brand (palette, mood, typography, tone, preferred_provider) — editable |
| `generation-log.csv` | One row per generation: timestamp, target, model, prompt, cost est., sha256 |

---

## Target dimension map (driven by naming)

| Name pattern | Target | Notes |
| :-- | :-- | :-- |
| `hero*`, `banner*` | 1920×1080 | Upscaled from 1536×1024 |
| `og*`, `og-image*` | 1200×630 | Centre-cropped |
| `icon*` | 512×512 transparent | Native or rembg |
| `avatar*` | 512×512 | Portrait framing |
| `feature*`, `card*` | 1024×768 | |
| `bg-*`, `background*` | 1920×1080 | High quality, low-contrast |
| `thumb*` | 1280×720 | |
| `logo*` | 1024×1024 transparent | |
| default | 1024×1024 | |

---

## Plugins in this marketplace

| Name | Status | Description |
| :-- | :-- | :-- |
| [`autoimage`](./plugins/autoimage) | **0.2.2** | Auto-generate brand-aligned images for frontend projects |

More plugins from Desima-AP will land here over time — `autocopy-claude`, `autoseo-claude`, and friends are in the queue.

---

## Local development

```bash
git clone git@github.com:Desima-AP/autoimage-claude.git
cd autoimage-claude
claude --plugin-dir ./plugins/autoimage
```

Run the test suite:

```bash
cd plugins/autoimage
python3 -m unittest discover -s tests
```

Environment check:

```bash
python3 plugins/autoimage/scripts/setup.py
```

---

## Contributing

Issues and pull requests welcome. For a meaningful change, please open an issue first — especially for model additions, new hint types, or output-convention changes.

## License

MIT — see [`LICENSE`](./LICENSE). Built for Claude Code by [Desima-AP](https://github.com/Desima-AP).
