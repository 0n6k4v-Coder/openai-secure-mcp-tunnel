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
