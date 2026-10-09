import hashlib, json
from pathlib import Path

root = Path("/workspace/project/captures/20261009t08211791534083z-f34e4bb30233")
manifest_path = root / "manifest.json"
capture_path = root / "capture.json"
capture = json.loads(capture_path.read_text(encoding="utf-8"))
asset_files = sorted((root / "assets").glob("*")) if (root / "assets").exists() else []
asset_bytes = sum(p.stat().st_size for p in asset_files if p.is_file())
capture["asset_inventory_summary"]["asset_bytes_preserved"] = asset_bytes
capture["asset_inventory_summary"]["asset_status"] = "A binary asset exists, but its source URL was not recorded; attribution is unresolved and the inventory is incomplete."
capture["capture"]["limitations"] = [
    "Rendered DOM is not original HTTP response bytes.",
    "One asset binary is present, but its original URL cannot be reliably attributed from the saved metadata.",
    "The remaining discovered resources were not comprehensively downloaded.",
    "Screenshot is viewport-only; full-page PNG capture exceeded screenshot constraints.",
    "Only CSSOM-accessible styles are preserved; JavaScript listeners and private runtime state cannot be completely serialized."
]
capture["unattributed_artifacts"] = []
for p in asset_files:
    if p.is_file():
        b = p.read_bytes()
        capture["unattributed_artifacts"].append({
            "path": p.relative_to(root).as_posix(),
            "bytes": len(b),
            "sha256": hashlib.sha256(b).hexdigest(),
            "source_url": None,
            "status": "captured_unattributed"
        })
capture_path.write_text(json.dumps(capture, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

files = []
for p in sorted(root.rglob("*")):
    if not p.is_file() or p == manifest_path:
        continue
    b = p.read_bytes()
    files.append({
        "path": "captures/" + root.name + "/" + p.relative_to(root).as_posix(),
        "bytes": len(b),
        "sha256": hashlib.sha256(b).hexdigest(),
        "status": "captured"
    })
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
manifest["files"] = files
manifest["asset_bytes_preserved"] = asset_bytes
manifest["asset_count"] = len(asset_files)
manifest["capture"]["limitations"] = [
    "Rendered DOM is not original HTTP response bytes.",
    "One asset binary exists but its original URL was not recorded; asset attribution is unresolved.",
    "Asset bytes were not comprehensively preserved; inspect per-resource statuses before reuse.",
    "Only CSS rules readable through the page CSSOM are preserved."
]
manifest["integrity"] = {
    "algorithm": "sha256",
    "file_hashes_recorded": True,
    "manifest_hash": "not_applicable_self_hash"
}
manifest["status"] = "partial"
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({
    "capture_dir": str(root),
    "files_listed": len(files),
    "files": [{"path": x["path"], "bytes": x["bytes"], "sha256": x["sha256"]} for x in files],
    "asset_bytes_preserved": asset_bytes,
    "unattributed_assets": len(capture["unattributed_artifacts"]),
    "status": manifest["status"]
}, indent=2))
