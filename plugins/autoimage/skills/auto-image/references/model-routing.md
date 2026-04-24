# Provider routing — user-driven

The plugin does NOT silently split a batch between OpenAI and Gemini.
Mixing two models within one project leads to inconsistent aesthetics
(different lighting, different palette interpretation, different text
rendering), so every batch uses **one provider**, chosen by the user.

## Decision precedence

```
IF the user said "use OpenAI" / "use Gemini" in this message
    → use that (explicit override)

ELSE IF brand-preset.json has preferred_provider ∈ {openai, gemini}
    → use that (project default)

ELSE IF only one of OPENAI_API_KEY / GEMINI_API_KEY is available
    → use that (single-key auto)

ELSE (both keys, no preference)
    → ASK the user once; optionally save the answer to the preset

ELSE (no keys at all)
    → surface the missing-key error
```

The router still produces *warnings* about quality trade-offs (e.g.
"text-heavy content on Gemini may render less reliably"), but they are
informational — the user's choice wins.

## What each provider is good at

| | `gpt-image-2` (OpenAI) | `gemini-3.1-flash-image-preview` (Google) |
| :-- | :-- | :-- |
| Baked-in text | **Very reliable** (reads the prompt, plans layout) | Often misspells; works only for short copy |
| Photorealism | Very good | Very good |
| Illustrations / flat vector | Good | **Very good** |
| Icons / glyphs | Good | **Very good, cheaper** |
| Native transparency | **Yes** (`background=transparent`) | No — needs `rembg` post-processing |
| Aspect ratios | Fixed: 1:1, 3:2, 2:3 | Flexible: 1:1, 16:9, 9:16, 4:3, 3:4, 3:2, 2:3 |
| Typical cost (1024² high) | $0.019 | $0.039 |
| Free tier | None — needs $5 billing minimum | Yes — a few RPM / several hundred RPD |

### Rough rule of thumb (for the *user's* choice, not the router's)

- **Lots of hero / banner / OG cards with readable copy** → OpenAI
- **Icon sets, avatars, feature cards, consistent UI assets** → Gemini
- **Transparent output is important and you don't want to install rembg**
  → OpenAI
- **Free tier / low budget / early-stage prototyping** → Gemini
- **Hybrid project where some images need baked text, others are
  decorative** → pick one provider for the whole project *or* split into
  two batches and regenerate each with a different `--provider`

## OpenAI model fallback ladder

OpenAI gates `gpt-image-2` behind a one-time organisation verification
step (ID check via Stripe Identity). Brand-new keys hit HTTP 403 with
*"organization must be verified"* until the user completes it.

When that happens, `openai_client.py` silently retries against
`gpt-image-1.5`, then `gpt-image-1`. All three accept the same request
schema — size, quality, background — so the failover is transparent.
The `fallback.used` field in `generate_image.py`'s JSON output tells
the skill that a substitution happened, and the Final Report in
`SKILL.md` surfaces this to the user with a one-line note + the
verification URL. After the user verifies (propagates in ~15 minutes),
the next request hits `gpt-image-2` again without any code change.

`gpt-image-1.5` shares `gpt-image-2`'s pricing tier; `gpt-image-1` is
roughly 2× the cost at equivalent sizes. The generation log records
whichever model actually produced each image, so cost totals stay
accurate.

## Native output sizes

**gpt-image-2** (OpenAI):
- `1024x1024`, `1536x1024`, `1024x1536`, `auto`
- No other sizes. 1920×1080 / 1200×630 / 512×512 are post-processed
  from the nearest native size.

**gemini-3.1-flash-image-preview** (Google):
- ~1024×1024 default; aspect ratio via
  `generationConfig.imageConfig.aspectRatio` (`1:1`, `16:9`, `9:16`,
  `4:3`, `3:4`, `3:2`, `2:3`).

Target dimensions are always achieved in post-processing — the provider
just needs to get you close.

## Cost table (USD per image, 2026-04 indicative)

| Provider | Model | Size | Quality | Cost |
| :--- | :--- | :--- | :--- | ---: |
| OpenAI | gpt-image-2 | 1024×1024 | high | $0.019 |
| OpenAI | gpt-image-2 | 1024×1024 | medium | $0.010 |
| OpenAI | gpt-image-2 | 1024×1024 | low | $0.005 |
| OpenAI | gpt-image-2 | 1536×1024 | high | $0.025 |
| OpenAI | gpt-image-2 | 1536×1024 | medium | $0.013 |
| Google | gemini-3.1-flash-image-preview | any | — | $0.039 |
| Google | gemini-2.5-flash-image (fallback) | any | — | $0.030 |

Post-processing (resize + WebP encode) is local and free.

## Overriding from the CLI

Force a provider for one call:

```bash
python3 scripts/generate_image.py \
  --name hero-home \
  --prompt "..." \
  --provider openai          # or gemini
```

The override wins over `preferred_provider` in the preset. If the
override's key is missing, `generate_image.py` exits with code 3 and a
clear message — it never falls back silently to the other provider.

## Changing the project default

Via the interactive command:

```
/design-brand
```

Pick option "preferred_provider" and set it to `openai`, `gemini`, or
`null` (ask every batch).

Via JSON edit (equivalent):

```json
{
  "preferred_provider": "gemini",
  "locked": { "preferred_provider": true }
}
```

Locking `preferred_provider` means `detect_brand.py` re-runs won't
clear it (though the default merge already preserves any non-null
choice).
