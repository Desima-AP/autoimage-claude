# Changelog

All notable changes to the `autoimage` plugin are documented here.
This project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] — 2026-04-23

### Changed
- **User-driven provider choice.** The router no longer silently splits a
  batch between OpenAI and Gemini based on asset type. Both providers can
  produce every asset type; the user picks one per batch (via CLI
  `--provider`, via natural language, or via `preferred_provider` in
  `.claude/brand-preset.json`). Mixing two models within one project
  causes inconsistent aesthetics, which is something the user should opt
  into explicitly.
- `brand-preset.json` gains a `preferred_provider` field
  (`"openai" | "gemini" | null`, default `null`).
- Warnings about quality trade-offs (e.g. text-heavy content on Gemini)
  are surfaced informationally but never override the user's choice.

### Added
- `/design-brand provider <openai|gemini|null>` shortcut to set the
  project default without entering the interactive menu.
- Router tests for explicit override, preset preference, single-key
  auto, and ambiguity scenarios.

## [0.1.0] — 2026-04-23

### Added
- Initial release.
- `PostToolUse` hook + `scan_missing.py` detecting empty `src=""`,
  placeholder URLs (picsum, via.placeholder, unsplash random, …),
  missing local files, and TODO/FIXME comments mentioning images in
  JSX / TSX / HTML / CSS / Vue / Svelte / Astro / MDX.
- `auto-image` skill orchestrating brand detection, prompt crafting
  (5-component formula), generation, resize/crop, WebP sibling, and
  generation-log CSV.
- Clients for OpenAI `gpt-image-2` and Google
  `gemini-3.1-flash-image-preview` (stdlib `urllib` only, no `requests`
  dependency).
- Three slash commands: `/design-scan`, `/design-regen`, `/design-brand`.
- Tailwind/package.json/README brand detection with field locking.
- Minimum-effort test suite (unittest, 67+ tests) covering scanner,
  name→params mapping, router, brand detection, and post-processing.
