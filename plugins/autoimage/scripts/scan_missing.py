#!/usr/bin/env python3
"""
scan_missing.py — PostToolUse hook entry point.

Reads Claude Code hook JSON on stdin, extracts the edited file path, and
scans its contents for:

  * empty `src=""` / `src=''` / `src={""}`
  * known placeholder image services (picsum, placehold, via.placeholder,
    dummyimage, placekitten, unsplash `/random`, loremflickr, etc.)
  * local file references that do not resolve on disk
  * TODO / FIXME comments mentioning an image

Findings are deduplicated and persisted to
`$CLAUDE_PROJECT_DIR/.claude/pending-assets.json`. A one-line summary is
printed to stdout so Claude can surface it in-session.

The script is intentionally side-effect-light: no network, no image
generation — it only scans and logs.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FRONTEND_EXTENSIONS = {
    ".jsx", ".tsx", ".js", ".ts",
    ".html", ".htm",
    ".css", ".scss", ".sass", ".less",
    ".vue", ".svelte", ".astro",
    ".mdx",
}

MAX_FILE_BYTES = 512 * 1024  # 512 KB — skip larger files for speed

PLACEHOLDER_HOSTS = (
    "placeholder.com",
    "via.placeholder.com",
    "placehold.it",
    "placehold.co",
    "placekitten.com",
    "placeimg.com",
    "dummyimage.com",
    "picsum.photos",
    "loremflickr.com",
    "source.unsplash.com",
    "unsplash.com/random",
    "fillmurray.com",
    "fakeimg.pl",
    "lorempixel.com",
)

# src="..." or src='...'  (including self-closing forms and attribute order variations)
SRC_ATTR_RE = re.compile(
    r"""(?P<attr>src|srcset|poster|data-src|href)\s*=\s*(?P<quote>["'])(?P<value>.*?)(?P=quote)""",
    re.IGNORECASE,
)

# background-image: url(...) / url('...') / url("...")
CSS_URL_RE = re.compile(
    r"""url\(\s*(?P<quote>["']?)(?P<value>.*?)(?P=quote)\s*\)""",
    re.IGNORECASE,
)

# ES imports of image assets
IMPORT_ASSET_RE = re.compile(
    r"""^\s*import\s+\S+\s+from\s+["'](?P<value>[^"']+\.(?:png|jpe?g|gif|svg|webp|avif))["']""",
    re.MULTILINE | re.IGNORECASE,
)

# TODO / FIXME comments mentioning an image concept
TODO_IMAGE_RE = re.compile(
    r"""(?://|/\*|<!--|#)\s*(?:TODO|FIXME|XXX|HACK)\b[^\n]{0,200}?\b(image|img|hero|icon|avatar|banner|photo|picture|og[-_:]?image|placeholder|illustration|thumbnail)\b""",
    re.IGNORECASE,
)

# Data URIs are fine — not placeholders
DATA_URI_RE = re.compile(r"^\s*data:", re.IGNORECASE)

# Tokens that indicate a JSX/TS expression we cannot statically resolve
UNRESOLVABLE_MARKERS = ("{", "$", "`")

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".avif", ".ico")


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def read_hook_stdin() -> dict[str, Any]:
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def project_dir(hook_payload: dict[str, Any]) -> Path:
    cwd = hook_payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    return Path(cwd).resolve()


def pending_path(project_root: Path) -> Path:
    return project_root / ".claude" / "pending-assets.json"


def load_pending(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "updated_at": None, "assets": []}
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict) or "assets" not in data:
            return {"version": 1, "updated_at": None, "assets": []}
        return data
    except (json.JSONDecodeError, OSError):
        return {"version": 1, "updated_at": None, "assets": []}


def save_pending(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    tmp.replace(path)


# ---------------------------------------------------------------------------
# Scanning primitives
# ---------------------------------------------------------------------------

def is_unresolvable_expression(value: str) -> bool:
    return any(marker in value for marker in UNRESOLVABLE_MARKERS)


def is_placeholder_url(value: str) -> bool:
    v = value.lower()
    if "unsplash.com/random" in v or "source.unsplash.com" in v:
        return True
    return any(host in v for host in PLACEHOLDER_HOSTS)


def is_external(value: str) -> bool:
    return value.startswith(("http://", "https://", "//"))


def candidate_local_paths(project_root: Path, source_file: Path, ref: str) -> list[Path]:
    """Return candidate on-disk locations for a local asset reference."""
    if DATA_URI_RE.match(ref):
        return []
    if is_external(ref):
        return []
    ref = ref.split("?", 1)[0].split("#", 1)[0]
    if not ref:
        return []

    candidates: list[Path] = []
    if ref.startswith("/"):
        for base in ("public", "static", "assets", "src/assets", ""):
            candidates.append(project_root / base / ref.lstrip("/"))
    else:
        candidates.append((source_file.parent / ref).resolve())
        candidates.append(project_root / ref)
        candidates.append(project_root / "public" / ref)
        candidates.append(project_root / "src" / "assets" / ref)
    return candidates


def resolves_on_disk(paths: list[Path]) -> bool:
    return any(p.exists() for p in paths)


def ext_looks_like_image(value: str) -> bool:
    v = value.lower().split("?", 1)[0].split("#", 1)[0]
    return v.endswith(IMAGE_EXTENSIONS)


def line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def context_snippet(text: str, offset: int, before: int = 60, after: int = 120) -> tuple[str, int]:
    """Return a (snippet, mid_offset) tuple.

    `mid_offset` is the position of `offset` within the returned snippet
    after leading whitespace is stripped — the scanners use it to scope
    attribute searches to the current tag.
    """
    start = max(0, offset - before)
    end = min(len(text), offset + after)
    raw = text[start:end].replace("\n", " ")
    mid_in_raw = offset - start
    lstripped = raw.lstrip()
    leading = len(raw) - len(lstripped)
    snippet = lstripped.rstrip()
    mid_in_snippet = max(0, min(mid_in_raw - leading, len(snippet)))
    return snippet, mid_in_snippet


_ALT_OR_LABEL_RE = re.compile(
    r"""(?:alt|aria-label|title|data-name)\s*=\s*["']([^"']{2,80})["']""",
    re.IGNORECASE,
)


def _slugify(value: str, fallback: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-").lower()
    return value or fallback


def _current_tag_scope(context: str, mid: int) -> str:
    """Return the substring of `context` that belongs to the JSX/HTML tag
    surrounding position `mid` (the location of the reference we're
    inspecting). We bound the scope by the nearest `<` before `mid` and
    the next `<` after it — prevents picking up a neighbour's alt.
    """
    mid = max(0, min(mid, len(context)))
    # Walk back to the opening of the current tag.
    left = context.rfind("<", 0, mid)
    if left < 0:
        left = 0
    # The next `<` after mid marks the start of another tag.
    right = context.find("<", mid + 1)
    if right < 0:
        right = len(context)
    # Advance past any whitespace and tag name to start at the first attr
    return context[left:right]


def _name_from_context(context: str, mid: Optional[int] = None) -> Optional[str]:
    """Extract a meaningful name from the alt / aria-label of the tag
    surrounding position `mid` in `context`. Fall back to scanning the
    whole context if nothing scoped matches.
    """
    mid = mid if mid is not None else len(context) // 2
    scope = _current_tag_scope(context, mid)
    for source in (scope, context):
        m = _ALT_OR_LABEL_RE.search(source)
        if m:
            words = m.group(1).split()[:4]
            slug = _slugify(" ".join(words), "")
            if slug:
                return slug
    return None


def _is_garbage_name(name: str) -> bool:
    """Bare digits (e.g. 1080 from picsum/1920/1080) or empty → garbage."""
    if not name:
        return True
    if name.isdigit():
        return True
    if len(name) < 3 and name.isalpha():
        return True
    return False


def suggest_name(
    ref: str,
    fallback: str = "asset",
    context: str = "",
    context_mid: Optional[int] = None,
) -> str:
    ref = ref.split("?", 1)[0].split("#", 1)[0]
    base = os.path.basename(ref) or ""
    base = re.sub(r"\.[a-zA-Z0-9]+$", "", base)
    slug = _slugify(base, "")

    if _is_garbage_name(slug):
        from_ctx = _name_from_context(context, context_mid)
        if from_ctx:
            return from_ctx
        return fallback

    return slug or fallback


# ---------------------------------------------------------------------------
# Finding types
# ---------------------------------------------------------------------------

def scan_src_attrs(text: str, project_root: Path, source_file: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for m in SRC_ATTR_RE.finditer(text):
        value = m.group("value")
        attr = m.group("attr")
        if attr.lower() == "href" and not ext_looks_like_image(value):
            continue
        ctx, mid = context_snippet(text, m.start())
        line = line_of(text, m.start())

        if not value:
            findings.append({
                "kind": "empty_src", "reference": "",
                "line": line, "context": ctx,
                "suggested_name": _name_from_context(ctx, mid) or "asset",
            })
            continue
        if is_unresolvable_expression(value):
            continue
        if is_placeholder_url(value):
            findings.append({
                "kind": "placeholder_url", "reference": value,
                "line": line, "context": ctx,
                "suggested_name": suggest_name(value, "placeholder", context=ctx, context_mid=mid),
            })
            continue
        if is_external(value):
            continue
        if not ext_looks_like_image(value):
            continue
        candidates = candidate_local_paths(project_root, source_file, value)
        if candidates and not resolves_on_disk(candidates):
            findings.append({
                "kind": "missing_file", "reference": value,
                "line": line, "context": ctx,
                "suggested_name": suggest_name(value, context=ctx, context_mid=mid),
            })
    return findings


def scan_css_urls(text: str, project_root: Path, source_file: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for m in CSS_URL_RE.finditer(text):
        value = m.group("value").strip()
        if not value or DATA_URI_RE.match(value):
            continue
        ctx, mid = context_snippet(text, m.start())
        line = line_of(text, m.start())

        if is_placeholder_url(value):
            findings.append({
                "kind": "placeholder_url", "reference": value,
                "line": line, "context": ctx,
                "suggested_name": suggest_name(value, "placeholder", context=ctx, context_mid=mid),
            })
            continue
        if is_external(value):
            continue
        if not ext_looks_like_image(value):
            continue
        candidates = candidate_local_paths(project_root, source_file, value)
        if candidates and not resolves_on_disk(candidates):
            findings.append({
                "kind": "missing_file", "reference": value,
                "line": line, "context": ctx,
                "suggested_name": suggest_name(value, context=ctx, context_mid=mid),
            })
    return findings


def scan_imports(text: str, project_root: Path, source_file: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for m in IMPORT_ASSET_RE.finditer(text):
        value = m.group("value")
        if is_external(value):
            continue
        candidates = candidate_local_paths(project_root, source_file, value)
        if candidates and not resolves_on_disk(candidates):
            ctx, mid = context_snippet(text, m.start())
            findings.append({
                "kind": "missing_file", "reference": value,
                "line": line_of(text, m.start()), "context": ctx,
                "suggested_name": suggest_name(value, context=ctx, context_mid=mid),
            })
    return findings


def scan_todos(text: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for m in TODO_IMAGE_RE.finditer(text):
        ctx, _ = context_snippet(text, m.start())
        findings.append({
            "kind": "todo_comment",
            "reference": m.group(0).strip(),
            "line": line_of(text, m.start()),
            "context": ctx,
            "suggested_name": "todo-image",
        })
    return findings


# ---------------------------------------------------------------------------
# Main flow
# ---------------------------------------------------------------------------

def stable_id(source_file: str, kind: str, reference: str, line: int) -> str:
    payload = f"{source_file}::{kind}::{reference}::{line}".encode("utf-8")
    return hashlib.sha1(payload).hexdigest()[:16]


def scan_file(project_root: Path, source_file: Path, text: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    findings.extend(scan_src_attrs(text, project_root, source_file))
    findings.extend(scan_css_urls(text, project_root, source_file))
    findings.extend(scan_imports(text, project_root, source_file))
    findings.extend(scan_todos(text))
    return findings


def main() -> int:
    payload = read_hook_stdin()
    tool_input = payload.get("tool_input") or {}
    file_path_str = tool_input.get("file_path")

    # Allow standalone CLI use: `scan_missing.py <file>` for testing
    if not file_path_str and len(sys.argv) > 1:
        file_path_str = sys.argv[1]

    if not file_path_str:
        return 0

    file_path = Path(file_path_str)
    if file_path.suffix.lower() not in FRONTEND_EXTENSIONS:
        return 0
    if not file_path.exists():
        return 0
    try:
        if file_path.stat().st_size > MAX_FILE_BYTES:
            return 0
    except OSError:
        return 0

    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0

    project_root = project_dir(payload)
    try:
        rel_source = str(file_path.resolve().relative_to(project_root))
    except ValueError:
        rel_source = str(file_path.resolve())

    findings = scan_file(project_root, file_path, text)

    pending_file = pending_path(project_root)
    data = load_pending(pending_file)

    # Remove any entries for this file — scan result is authoritative for it
    existing = [a for a in data["assets"] if a.get("source_file") != rel_source]
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    for f in findings:
        entry = {
            "id": stable_id(rel_source, f["kind"], f["reference"], f["line"]),
            "source_file": rel_source,
            "line": f["line"],
            "kind": f["kind"],
            "reference": f["reference"],
            "suggested_name": f["suggested_name"],
            "context_snippet": f["context"],
            "detected_at": now,
            "status": "pending",
        }
        existing.append(entry)

    data["assets"] = existing
    save_pending(pending_file, data)

    if findings:
        kinds = ", ".join(sorted({f["kind"] for f in findings}))
        print(
            f"[auto-image] {len(findings)} pending asset(s) in {rel_source} "
            f"({kinds}). Ask me to generate them or run /design-scan."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
