from __future__ import annotations

import pytest

from local_mcp_server.clone import preserve


def test_remote_path_is_rooted_in_project_workspace() -> None:
    assert preserve._remote_path("captures/example/manifest.json") == (
        "/workspace/project/captures/example/manifest.json"
    )


@pytest.mark.parametrize(
    "path",
    [
        "",
        "/tmp/escape",
        "../escape",
        "captures/../escape",
        r"captures\escape",
        "captures//double",
        "captures/./dot",
        "captures/\x00bad",
    ],
)
def test_remote_path_rejects_unsafe_paths(path: str) -> None:
    with pytest.raises(ValueError):
        preserve._remote_path(path)


def test_sha256_matches_standard_digest() -> None:
    assert preserve._sha256(b"abc") == (
        "ba7816bf8f01cfea414140de5dae2223"
        "b00361a396177a9cb410ff61f20015ad"
    )


def test_capture_text_reads_multiple_chunks_and_cleans_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def fake_evaluate(sandbox_name: str, page_id: int, script: str) -> dict[str, object]:
        calls.append(script)
        if "delete window[" in script:
            return {"page_id": page_id, "result": True}
        if "const key =" in script and "let value =" in script:
            return {
                "page_id": page_id,
                "result": {
                    "length": 5,
                    "chunk": "ab",
                    "nextOffset": 2,
                    "meta": {"url": "https://example.com/"},
                },
            }
        if "const value = window[key]" in script:
            return {
                "page_id": page_id,
                "result": {"length": 5, "chunk": "cde", "nextOffset": 5},
            }
        raise AssertionError("Unexpected browser script")

    monkeypatch.setattr(preserve, "evaluate", fake_evaluate)
    value, metadata = preserve._capture_text("clone-test", 7, "html")

    assert value == "abcde"
    assert metadata == {"url": "https://example.com/"}
    assert len(calls) == 3
    assert "delete window[" in calls[-1]


def test_capture_text_rejects_invalid_kind() -> None:
    with pytest.raises(ValueError, match="kind must be"):
        preserve._capture_text("clone-test", 1, "javascript")


def test_capture_text_rejects_oversized_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_evaluate(sandbox_name: str, page_id: int, script: str) -> dict[str, object]:
        if "delete window[" in script:
            return {"page_id": page_id, "result": True}
        return {
            "page_id": page_id,
            "result": {
                "length": preserve._MAX_CAPTURE_CHARS + 1,
                "chunk": "",
                "nextOffset": 0,
                "meta": {},
            },
        }

    monkeypatch.setattr(preserve, "evaluate", fake_evaluate)
    with pytest.raises(ValueError, match="character limit"):
        preserve._capture_text("clone-test", 1, "html")


def test_capture_snapshot_keeps_capture_separate_from_conversion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(preserve, "_create_capture_directory", lambda *args: "/workspace/project/captures/fake")
    monkeypatch.setattr(preserve, "_capture_text", lambda _name, _page, kind: (
        ("<html><body>raw</body></html>" if kind == "html" else "body { color: red; }"),
        {"url": "https://example.com/", "title": "Example"} if kind == "html" else {},
    ))
    monkeypatch.setattr(preserve, "_capture_inventory", lambda *_args: {
        "url": "https://example.com/",
        "title": "Example",
        "assets": ["https://example.com/logo.png"],
        "resources": [],
        "interactions": {"links": [], "buttons": [], "forms": []},
    })
    monkeypatch.setattr(preserve, "_capture_assets", lambda *_args: ([], [], 0))
    written: dict[str, bytes] = {}

    def fake_write_artifact(_name: str, path: str, content: bytes) -> dict[str, object]:
        written[path] = content
        return {
            "path": path,
            "bytes": len(content),
            "sha256": preserve._sha256(content),
            "status": "captured",
        }

    monkeypatch.setattr(preserve, "_write_capture_artifact", fake_write_artifact)
    monkeypatch.setattr(
        preserve,
        "capture_screenshot_artifact",
        lambda *_args, **_kwargs: {
            "status": "captured",
            "bytes": 123,
            "path": "screenshot.png",
        },
    )
    monkeypatch.setattr(preserve, "_remote_sha256", lambda *_args: "a" * 64)
    monkeypatch.setattr(preserve, "_write_new_file", lambda _name, path, content: written.setdefault(path, content))

    result = preserve.capture_raw_snapshot("clone-test", 1)

    assert result["conversion_performed"] is False
    assert result["status"] == "partial"
    assert any(path.endswith("dom.snapshot.html") for path in written)
    assert any(path.endswith("stylesheets.snapshot.css") for path in written)
    assert any(path.endswith("capture.json") for path in written)
    assert any(path.endswith("manifest.json") for path in written)
    assert b"<html><body>raw</body></html>" in written[next(path for path in written if path.endswith("dom.snapshot.html"))]
    assert result["manifest"]["asset_bytes_preserved"] == 0
    assert result["manifest"]["files"][0]["sha256"] == preserve._sha256(
        written[result["manifest"]["files"][0]["path"]]
    )


@pytest.mark.parametrize(
    "capture_dir",
    ["../outside", "/tmp/capture", "captures/../outside", "captures/a/b", "captures/./capture-a"],
)
def test_convert_raw_snapshot_rejects_invalid_capture_directories(capture_dir: str) -> None:
    with pytest.raises(ValueError):
        preserve.convert_raw_snapshot("clone-test", capture_dir)


def test_convert_raw_snapshot_never_writes_into_capture_tree() -> None:
    with pytest.raises(ValueError, match="separate"):
        preserve.convert_raw_snapshot(
            "clone-test", "captures/20261009t120000z-a1b2c3d4e5f6", "captures/output"
        )


def test_convert_raw_snapshot_verifies_hashes_and_uses_saved_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture_id = "20261009t120000z-a1b2c3d4e5f6"
    capture_dir = f"captures/{capture_id}"
    html_path = f"{capture_dir}/dom.snapshot.html"
    css_path = f"{capture_dir}/stylesheets.snapshot.css"
    inventory_path = f"{capture_dir}/capture.json"
    html_text = "<html><body>preserved source</body></html>"
    css_text = "body { color: red; }"
    inventory_text = '{"url":"https://example.com/","title":"Example","assets":[],"interactions":{"links":[],"buttons":[],"forms":[]}}'
    manifest = {
        "schema_version": "1.0.0",
        "capture_id": capture_id,
        "source": {"url": "https://example.com/", "title": "Example", "page_id": 1},
        "files": [
            {"path": html_path, "sha256": "a" * 64, "status": "captured"},
            {"path": css_path, "sha256": "b" * 64, "status": "captured"},
            {"path": inventory_path, "sha256": "c" * 64, "status": "captured"},
        ],
    }
    contents = {
        f"{capture_dir}/manifest.json": __import__("json").dumps(manifest),
        html_path: html_text,
        css_path: css_text,
        inventory_path: inventory_text,
    }
    monkeypatch.setattr(preserve, "_read_artifact_text", lambda _name, path, **_kwargs: contents[path])
    monkeypatch.setattr(preserve, "_remote_sha256", lambda _name, path: next(
        entry["sha256"] for entry in manifest["files"] if entry["path"] == path
    ))
    monkeypatch.setattr(
        preserve,
        "execute_sandbox_argv",
        lambda *_args, **_kwargs: {"stdout": "", "stderr": "", "return_code": 0},
    )
    monkeypatch.setattr(
        preserve,
        "_command",
        lambda _name, argv, **_kwargs: {
            "stdout": "dom.snapshot.html\nstylesheets.snapshot.css\ncapture.json\nmanifest.json\n"
            if argv[0] == "find" else "",
            "stderr": "",
            "return_code": 0,
        },
    )
    seen: dict[str, object] = {}

    def fake_create_manifest(**evidence: object) -> dict[str, object]:
        seen["evidence"] = evidence
        return {"site": {"url": "https://example.com/"}}

    monkeypatch.setattr(preserve, "create_clone_manifest_impl", fake_create_manifest)
    monkeypatch.setattr(
        preserve,
        "generate_project_impl",
        lambda _name, output_dir, clone_manifest: {
            "output_dir": output_dir,
            "manifest": clone_manifest,
        },
    )

    result = preserve.convert_raw_snapshot("clone-test", capture_dir, "clones/test-conversion")

    assert result["status"] == "converted"
    assert result["integrity_verified"] is True
    assert result["conversion_performed"] is True
    assert result["output_dir"] == "clones/test-conversion"
    evidence = seen["evidence"]
    assert isinstance(evidence, dict)
    assert evidence["inspect_page"]["html"] == html_text
    assert evidence["inspect_page"]["css"] == css_text



def test_capture_asset_bytes_decodes_bounded_base64_chunks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_evaluate_result(_name: str, _page_id: int, script: str) -> dict[str, object]:
        if "async () =>" in script:
            return {
                "status": "ready",
                "url": "https://example.com/asset.txt",
                "bytes": 3,
                "base64Length": 4,
                "contentType": "text/plain",
            }
        return {"length": 4, "chunk": "YWJj", "nextOffset": 4}

    monkeypatch.setattr(preserve, "_evaluate", fake_evaluate_result)
    monkeypatch.setattr(preserve, "evaluate", lambda *_args, **_kwargs: {"result": True})
    data, metadata = preserve._capture_asset_bytes(
        "clone-test", 1, "https://example.com/asset.txt"
    )
    assert data == b"abc"
    assert metadata["status"] == "ready"


def test_capture_asset_bytes_records_cross_origin_skip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        preserve,
        "_evaluate",
        lambda *_args, **_kwargs: {
            "status": "skipped_cross_origin",
            "url": "https://cdn.example.net/asset.js",
        },
    )
    monkeypatch.setattr(preserve, "evaluate", lambda *_args, **_kwargs: {"result": True})
    data, metadata = preserve._capture_asset_bytes(
        "clone-test", 1, "https://cdn.example.net/asset.js"
    )
    assert data is None
    assert metadata["status"] == "skipped_cross_origin"


def test_capture_assets_marks_cross_origin_without_attempting_download(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_download(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("Cross-origin assets must be skipped before browser fetch.")

    monkeypatch.setattr(preserve, "_capture_asset_bytes", unexpected_download)
    statuses = [{"url": "https://cdn.example.net/app.js", "status": "inventoried_not_downloaded"}]
    files, failures, total_bytes = preserve._capture_assets(
        "clone-test",
        1,
        "captures/example",
        ["https://cdn.example.net/app.js"],
        statuses,
        "https://example.com/",
    )

    assert files == []
    assert failures == []
    assert total_bytes == 0
    assert statuses[0]["status"] == "skipped_cross_origin"


def test_asset_extension_prefers_known_content_type() -> None:
    assert preserve._asset_extension("https://example.com/asset.bin", "image/png") == ".png"
    assert preserve._asset_extension("https://example.com/app.js", None) == ".js"

