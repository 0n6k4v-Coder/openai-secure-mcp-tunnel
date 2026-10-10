from __future__ import annotations

from local_mcp_server.clone.pipeline import (
    analyze_structure,
    build_dependency_graph,
    create_clone_manifest,
    _render_html_document,
    _render_css_document,
    verify_clone,
    repair_clone,
)


def test_analyze_structure_generates_pages_and_components():
    evidence = {
        "discover": {
            "url": "https://paypers.ai/",
            "page_id": 2,
            "pages": [{"id": 2, "url": "https://paypers.ai/", "selected": True}],
        },
        "inspect_runtime": {
            "url": "https://paypers.ai/",
            "title": "Paypers - Automated AI Payments",
            "readyState": "complete",
        },
        "inspect_styles": {
            "found": True,
            "computed": {
                "fontFamily": "Inter, sans-serif",
                "color": "rgb(15, 23, 42)",
                "backgroundColor": "rgb(255, 255, 255)",
            },
        },
        "trace_interactions": {
            "links": [
                {"text": "Features", "href": "https://paypers.ai/features"},
                {"text": "Pricing", "href": "https://paypers.ai/pricing"},
                {"text": "Docs", "href": "https://docs.paypers.ai"},
            ],
            "buttons": [
                {"text": "Get Started", "id": "cta-btn"},
                {"text": "Sign In", "id": "login-btn"},
            ],
        },
        "trace_assets": {
            "stylesheets": ["https://paypers.ai/assets/index.css"],
            "fonts": ["Inter"],
            "images": [{"src": "https://paypers.ai/logo.svg"}],
        },
    }

    structure = analyze_structure(**evidence)
    assert structure["kind"] == "clone_structure"
    assert len(structure["pages"]) >= 1
    assert structure["pages"][0]["route"] == "/"
    assert structure["pages"][0]["title"] == "Paypers - Automated AI Payments"
    assert len(structure["sections"]) >= 4
    assert len(structure["components"]) >= 3
    assert structure["theme"]["fontFamily"] == "Inter, sans-serif"


def test_build_dependency_graph_generates_nodes_and_edges():
    evidence = {
        "discover": {"url": "https://paypers.ai/"},
        "inspect_runtime": {"title": "Paypers"},
        "trace_assets": {
            "stylesheets": ["https://paypers.ai/style.css"],
            "fonts": ["Inter"],
            "images": [{"src": "https://paypers.ai/logo.png"}],
        },
        "trace_interactions": {
            "buttons": [{"text": "Start Free"}],
            "links": [{"text": "Pricing", "href": "https://paypers.ai/pricing"}],
        },
    }

    graph = build_dependency_graph(**evidence)
    assert graph["kind"] == "dependency_graph"
    assert len(graph["nodes"]) > 0
    assert len(graph["edges"]) > 0
    node_ids = {n["id"] for n in graph["nodes"]}
    assert "page:/" in node_ids
    assert "component:navbar" in node_ids
    assert "component:hero_banner" in node_ids
    assert "asset:css:0" in node_ids


def test_create_clone_manifest_includes_all_specs():
    evidence = {
        "discover": {"url": "https://paypers.ai/"},
        "inspect_runtime": {"title": "Paypers"},
        "trace_interactions": {"links": [], "buttons": [{"text": "Join"}]},
    }
    manifest = create_clone_manifest(**evidence)
    assert manifest["version"] == "1.0.0"
    assert manifest["site"]["title"] == "Paypers"
    assert len(manifest["pages"]) >= 1
    assert len(manifest["components"]) >= 1
    assert len(manifest["dependencies"]["nodes"]) > 0


def test_render_html_and_css_produces_rich_markup():
    manifest = {
        "site": {"title": "Paypers - AI Payments", "url": "https://paypers.ai/"},
        "theme": {"fontFamily": "Inter, sans-serif", "color": "#0f172a"},
        "interactions": {
            "links": [{"text": "Features", "href": "#features"}],
            "buttons": [{"text": "Get Started"}],
        },
    }
    html = _render_html_document(manifest)
    css = _render_css_document(manifest)

    assert "<!doctype html>" in html
    assert "<title>Paypers - AI Payments</title>" in html
    assert '<link rel="stylesheet" href="styles.css">' in html
    assert "Get Started" in html
    assert "Features" in html
    assert "container" in css
    assert "hero-section" in css


def test_verify_and_repair_clone():
    verification = verify_clone(analyze={"sections": [1, 2], "pages": [1]})
    assert verification["status"] == "incomplete"
    assert verification["score"] is None
    assert verification["visual"]["status"] == "not_evaluated"

    repair = repair_clone(verification=verification)
    assert repair["status"] == "no_actionable_repairs"
    assert repair["repairs_applied"] == 0


def test_captured_html_is_sanitized_before_rendering():
    from local_mcp_server.clone.pipeline import _sanitize_html_fragment

    sanitized = _sanitize_html_fragment(
        '<h1 onclick="alert(1)">Hello</h1><script>alert(2)</script>'
        '<a href="javascript:alert(3)" onmouseover="alert(4)">link</a>'
        '<img src="https://example.com/logo.png" onerror="alert(5)">'
    )
    assert '<h1>Hello</h1>' in sanitized
    assert '<script' not in sanitized
    assert 'onclick=' not in sanitized
    assert 'onmouseover=' not in sanitized
    assert 'onerror=' not in sanitized
    assert 'javascript:' not in sanitized
    assert 'https://example.com/logo.png' in sanitized


def test_project_path_rejects_absolute_and_parent_paths():
    import pytest
    from local_mcp_server.clone.pipeline import _safe_relative_project_path

    for path in ('../etc', '/tmp/escape', 'clones/../../etc', r'clones\..\escape', ''):
        with pytest.raises(ValueError):
            _safe_relative_project_path(path)
    assert _safe_relative_project_path('clones/site-a') == 'clones/site-a'


def test_verification_does_not_claim_unperformed_checks_passed():
    result = verify_clone(analyze={'pages': [{'route': '/'}], 'sections': []})
    assert result['status'] == 'incomplete'
    assert result['score'] is None
    assert result['assets']['status'] == 'not_evaluated'
    assert result['visual']['status'] == 'not_evaluated'
    assert result['behavior']['status'] == 'not_evaluated'


def test_failed_build_cannot_pass_verification():
    result = verify_clone(
        analyze={'pages': [{'route': '/'}]},
        build={'return_code': 1, 'status': 'failed', 'artifacts': {}},
    )
    assert result['status'] == 'failed'
    assert result['assets']['status'] == 'fail'
    assert any('Build step failed' in mismatch for mismatch in result['mismatches'])


def test_repair_never_claims_unapplied_patches():
    result = repair_clone(verification={'mismatches': ['Missing screenshot comparison']})
    assert result['status'] == 'manual_action_required'
    assert result['repairs_applied'] == 0
    assert result['actionable_mismatches'] == ['Missing screenshot comparison']


def test_generate_project_formats_each_generated_text_file(monkeypatch):
    from local_mcp_server.clone import pipeline

    formatted_paths = []

    def fake_format(sandbox_name, relative_path, content):
        formatted_paths.append(relative_path)
        return content, "formatted with test formatter"

    def fake_exec(sandbox_name, argv, *, stdin=None, timeout_seconds=120):
        if argv[0] == "realpath":
            return {
                "stdout": "/workspace/project/clones/test",
                "stderr": "",
                "return_code": 0,
            }
        return {"stdout": "", "stderr": "", "return_code": 0}

    monkeypatch.setattr(pipeline, "format_text_in_sandbox", fake_format)
    monkeypatch.setattr(pipeline, "execute_sandbox_argv", fake_exec)

    result = pipeline.generate_project(
        "focused",
        "clones/test",
        {"site": {"url": "https://example.com", "title": "Example"}},
    )

    assert set(formatted_paths) == {
        "clones/test/clone-manifest.json",
        "clones/test/index.html",
        "clones/test/styles.css",
        "clones/test/package.json",
        "clones/test/README.md",
    }
    assert result["formatting"] == {
        path.rsplit("/", 1)[-1]: "formatted with test formatter"
        for path in formatted_paths
    }


def test_compare_dom_trees_detects_mismatches(monkeypatch):
    from local_mcp_server.clone import pipeline

    ref_payload = {
        "found": True,
        "selector": "#hero",
        "tree": {
            "tag": "section",
            "rect": {"width": 1200, "height": 500},
            "fullText": "Hero Headline",
            "children": [
                {"tag": "h1", "rect": {"width": 600, "height": 80}, "children": []},
                {"tag": "p", "rect": {"width": 600, "height": 40}, "children": []},
                {"tag": "a", "rect": {"width": 120, "height": 40}, "children": []},
            ],
        },
        "images": [{"src": "logo.png"}],
        "links": [{"text": "CTA", "href": "https://example.com"}],
        "buttons": [],
    }

    cand_payload = {
        "found": True,
        "selector": "#hero",
        "tree": {
            "tag": "section",
            "rect": {"width": 1200, "height": 500},
            "fullText": "Hero Headline",
            "children": [
                {"tag": "h1", "rect": {"width": 600, "height": 80}, "children": []},
            ],
        },
        "images": [],
        "links": [],
        "buttons": [],
    }

    def fake_evaluate(sandbox_name, page_id, script):
        if page_id == 2:
            return {"result": ref_payload}
        return {"result": cand_payload}

    monkeypatch.setattr(pipeline, "evaluate", fake_evaluate)

    res = pipeline.compare_dom_trees("test-box", 2, 4, selector="#hero")
    assert res["status"] == "diff_detected"
    assert res["diff_count"] >= 3
    categories = [d["category"] for d in res["diffs"]]
    assert "dom_node_count" in categories
    assert "links_count" in categories
    assert "images_missing" in categories


def test_audit_resource_hints_detects_preloads(monkeypatch):
    from local_mcp_server.clone import pipeline

    hints_payload = {
        "totalLinks": 5,
        "preloadsCount": 2,
        "preloads": [{"rel": "preload", "href": "https://example.com/icon.png", "as": "image"}],
        "preconnectsCount": 1,
        "preconnects": [{"rel": "preconnect", "href": "https://fonts.googleapis.com"}],
        "stylesheetsCount": 1,
        "iconsCount": 1,
        "structuredDataCount": 2,
        "structuredDataTypes": ["Organization", "WebPage"],
    }

    monkeypatch.setattr(pipeline, "evaluate", lambda s, p, sc: {"result": hints_payload})

    res = pipeline.audit_resource_hints("test-box", 2)
    assert res["preloadsCount"] == 2
    assert res["preloads"][0]["href"] == "https://example.com/icon.png"
    assert res["structuredDataTypes"] == ["Organization", "WebPage"]


def test_audit_page_spec_unified(monkeypatch):
    from local_mcp_server.clone import pipeline

    spec_payload = {
        "totalLinks": 5,
        "preloadsCount": 2,
        "preloads": [{"rel": "preload", "href": "https://example.com/icon.png", "as": "image"}],
        "preconnectsCount": 1,
        "preconnects": [{"rel": "preconnect", "href": "https://fonts.googleapis.com"}],
        "stylesheetsCount": 1,
        "iconsCount": 1,
        "metaTags": [{"name": "description", "content": "Test description"}],
        "metaCount": 1,
        "title": "Test Page",
        "structuredDataCount": 1,
        "structuredDataTypes": ["Organization"],
    }

    monkeypatch.setattr(pipeline, "evaluate", lambda s, p, sc: {"result": spec_payload})

    res = pipeline.audit_page_spec("test-box", 2, include_structured_data=True, include_resource_hints=True)
    assert res["preloadsCount"] == 2
    assert res["title"] == "Test Page"
    assert res["metaCount"] == 1
    assert "Organization" in res["structuredDataTypes"]


def test_audit_element_fidelity_unified(monkeypatch):
    from local_mcp_server.clone import pipeline

    dom_res = {
        "status": "pass",
        "selector": "#hero",
        "diff_count": 0,
        "diffs": [],
        "reference_node_count": 10,
        "candidate_node_count": 10,
        "reference_rect": {"width": 1000, "height": 400},
        "candidate_rect": {"width": 1000, "height": 400},
    }

    ref_motion_payload = {
        "webAnimsCount": 1,
        "webAnims": [],
        "islandTransitionsCount": 2,
        "islandTransitions": [{"tag": "astro-island", "component": "FadeUp"}],
        "motionStyleNodesCount": 2,
        "motionStyleNodes": [],
        "movingCount": 4,
        "movingElements": [],
        "targetCount": 4,
        "mutatedCount": 3,
        "probes": [{"hasMutation": True}],
    }

    cand_motion_payload = {
        "webAnimsCount": 0,
        "webAnims": [],
        "islandTransitionsCount": 0,
        "islandTransitions": [],
        "motionStyleNodesCount": 0,
        "motionStyleNodes": [],
        "movingCount": 0,
        "movingElements": [],
        "targetCount": 4,
        "mutatedCount": 0,
        "probes": [],
    }

    monkeypatch.setattr(pipeline, "compare_dom_trees", lambda *a, **k: dom_res)

    def fake_evaluate(sandbox_name, page_id, script):
        if page_id == 2:
            return {"result": ref_motion_payload}
        return {"result": cand_motion_payload}

    monkeypatch.setattr(pipeline, "evaluate", fake_evaluate)

    res = pipeline.audit_element_fidelity("test-box", 2, 4, selector="#hero", check_motion=True, check_interactions=True)
    assert res["status"] == "diff_detected"
    categories = [d["category"] for d in res["diffs"]]
    assert "continuous_motion_missing" in categories
    assert "entrance_transitions_missing" in categories
    assert "interaction_unresponsive" in categories

