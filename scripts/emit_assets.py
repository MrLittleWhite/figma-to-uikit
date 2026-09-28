"""Offline packaging of IR image assets into a deterministic asset catalog."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

_SUPPORTED = {"png", "jpg", "jpeg", "pdf"}


def _diagnostic(code: str, ref: str, message: str, level: str = "error") -> dict[str, str]:
    return {"level": level, "code": code, "asset_ref": ref, "message": message}


def _asset_refs(ir: dict[str, Any]) -> tuple[set[str], dict[str, str]]:
    refs: set[str] = set()
    formats: dict[str, str] = {}
    for value in ir.get("assets", []) or []:
        if isinstance(value, str):
            refs.add(value)
    def visit(node: Any) -> None:
        if not isinstance(node, dict):
            return
        asset = node.get("asset")
        if isinstance(asset, dict) and isinstance(asset.get("ref"), str) and asset["ref"]:
            ref = asset["ref"]
            refs.add(ref)
            if asset.get("format") is not None:
                formats[ref] = str(asset["format"]).lower().lstrip(".")
        for child in node.get("children", []) or []:
            visit(child)
    visit(ir.get("root", {}))
    return refs, formats


def _safe_relative(ref: str, root: Path) -> Path | None:
    # Reject both native absolute paths and Windows absolute/drive paths on Unix.
    if not ref or Path(ref).is_absolute() or re.match(r"^[A-Za-z]:[\\/]", ref) or ref.startswith(("\\\\", "//")):
        return None
    parts = PurePosixPath(ref.replace("\\", "/")).parts
    if not parts or ".." in parts or any(part in ("", ".") for part in parts):
        return None
    candidate = root.joinpath(*parts)
    try:
        candidate.resolve().relative_to(root.resolve())
    except ValueError:
        return None
    return candidate


def _safe_name(ref: str) -> str:
    stem = Path(ref.replace("\\", "/")).stem
    stem = re.sub(r"[^A-Za-z0-9]+", "_", stem).strip("_") or "asset"
    if stem[0].isdigit():
        stem = "asset_" + stem
    digest = hashlib.sha256(ref.encode("utf-8")).hexdigest()[:8]
    return f"{stem}_{digest}"


def _contents(filename: str) -> bytes:
    value = {"images": [{"filename": filename, "idiom": "universal", "scale": "1x"}], "info": {"author": "xcode", "version": 1}}
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def plan_assets(ir: dict[str, Any], assets_dir: str | Path) -> tuple[dict[str, bytes], dict[str, str], list[dict[str, str]]]:
    """Plan deterministic, offline asset-catalog files without writing to disk.

    Returns ``(relative_output_path_to_bytes, ref_to_catalog_name, diagnostics)``.
    Only references resolving beneath the explicit ``assets_dir`` are read; no
    network or implicit fallback directory is used.
    """
    root = Path(assets_dir).expanduser()
    refs, formats = _asset_refs(ir)
    files: dict[str, bytes] = {}
    catalog: dict[str, str] = {}
    diagnostics: list[dict[str, str]] = []
    for ref in sorted(refs):
        path = _safe_relative(ref, root)
        hinted = formats.get(ref, "").lower().lstrip(".")
        suffix = Path(ref.replace("\\", "/")).suffix.lower().lstrip(".")
        kind = hinted or suffix
        if kind == "svg" or suffix == "svg":
            diagnostics.append(_diagnostic("unsupported-asset-format", ref, "SVG assets are unsupported; provide PNG, JPEG, or PDF without conversion."))
            continue
        if kind not in _SUPPORTED and suffix not in _SUPPORTED:
            diagnostics.append(_diagnostic("unsupported-asset-format", ref, "Only local PNG, JPEG, and PDF assets are supported."))
            continue
        if path is None:
            diagnostics.append(_diagnostic("unsafe-asset-ref", ref, "Asset reference must be relative and remain beneath assets_dir."))
            continue
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to(root.resolve())
            if not resolved.is_file():
                raise FileNotFoundError
            data = resolved.read_bytes()
        except (FileNotFoundError, OSError, ValueError):
            diagnostics.append(_diagnostic("missing-asset", ref, "Asset resource does not exist beneath assets_dir."))
            continue
        name = _safe_name(ref)
        ext = resolved.suffix.lower()
        if ext == ".jpeg":
            filename = name + ".jpeg"
        elif ext in {".png", ".jpg", ".pdf"}:
            filename = name + ext
        else:
            filename = name + "." + kind
        base = f"Assets.xcassets/{name}.imageset"
        files[f"{base}/{filename}"] = data
        files[f"{base}/Contents.json"] = _contents(filename)
        catalog[ref] = name
    if catalog:
        files["Assets.xcassets/Contents.json"] = (json.dumps(
            {"info": {"author": "xcode", "version": 1}}, indent=2, sort_keys=True) + "\n").encode("utf-8")
    return files, catalog, diagnostics
