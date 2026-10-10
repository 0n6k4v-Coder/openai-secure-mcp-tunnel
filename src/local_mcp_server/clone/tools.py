from __future__ import annotations

from typing import Any

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from .pipeline import (
    analyze_structure as analyze_structure_impl,
    build_dependency_graph as build_dependency_graph_impl,
    build_project as build_project_impl,
    capture_screenshot as capture_screenshot_impl,
    create_clone_manifest as create_clone_manifest_impl,
    discover_site as discover_site_impl,
    generate_project as generate_project_impl,
    inspect_page as inspect_page_impl,
    inspect_runtime as inspect_runtime_impl,
    inspect_styles as inspect_styles_impl,
    repair_clone as repair_clone_impl,
    run_clone_workflow as run_clone_workflow_impl,
    serve_project as serve_project_impl,
    trace_assets as trace_assets_impl,
    audit_rendered_assets as audit_rendered_assets_impl,
    audit_motion as audit_motion_impl,
    compare_dom_trees as compare_dom_trees_impl,
    audit_resource_hints as audit_resource_hints_impl,
    audit_page_spec as audit_page_spec_impl,
    audit_element_fidelity as audit_element_fidelity_impl,
    trace_interactions as trace_interactions_impl,
    verify_clone as verify_clone_impl,
)
from .preserve import (
    capture_raw_snapshot as capture_raw_snapshot_impl,
    convert_raw_snapshot as convert_raw_snapshot_impl,
)
from .live_proxy import create_live_proxy_snapshot as create_live_proxy_snapshot_impl
from .decomposition import (
    decompose_live_proxy as decompose_live_proxy_impl,
    audit_decomposition_fidelity as audit_decomposition_fidelity_impl,
)
from .visual import (
    capture_screenshot_artifact as capture_screenshot_artifact_impl,
    compare_screenshot_artifacts as compare_screenshot_artifacts_impl,
    verify_clone_with_visual as verify_clone_with_visual_impl,
)


def register_tools(mcp: MCPServer) -> None:
    """Register the new website-cloning pipeline tools."""

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
    def discover_site(sandbox_name: str, url: str) -> dict[str, Any]:
        """Discover a site's entry page and browser page topology."""
        return discover_site_impl(sandbox_name, url)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
    def inspect_page(sandbox_name: str, page_id: int, selector: str | None = None) -> dict[str, Any]:
        """Inspect the live page accessibility/DOM structure or a selected element."""
        return inspect_page_impl(sandbox_name, page_id, selector)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
    def inspect_runtime(sandbox_name: str, page_id: int) -> dict[str, Any]:
        """Inspect live JavaScript/runtime state for a page."""
        return inspect_runtime_impl(sandbox_name, page_id)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
    def inspect_styles(sandbox_name: str, page_id: int, selector: str = "body") -> dict[str, Any]:
        """Inspect computed styles for a live DOM element."""
        return inspect_styles_impl(sandbox_name, page_id, selector)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
    def trace_assets(sandbox_name: str, page_id: int) -> dict[str, Any]:
        """Trace images, fonts, stylesheets, scripts, and media used by a page."""
        return trace_assets_impl(sandbox_name, page_id)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
    def audit_rendered_assets(sandbox_name: str, page_id: int) -> dict[str, Any]:
        """Audit rendered media, SVGs, background images, and out-of-flow absolute/fixed elements on the live DOM."""
        return audit_rendered_assets_impl(sandbox_name, page_id)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
    def audit_element_fidelity(
        sandbox_name: str,
        reference_page_id: int,
        candidate_page_id: int,
        selector: str = "body",
        check_motion: bool = True,
        check_interactions: bool = True,
        sample_interval_ms: int = 500,
        max_depth: int = 15,
    ) -> dict[str, Any]:
        """Unified element audit and comparison: verifies DOM hierarchy, layout, text, interactive elements, continuous motion, and entrance transition specs."""
        return audit_element_fidelity_impl(
            sandbox_name,
            reference_page_id,
            candidate_page_id,
            selector=selector,
            check_motion=check_motion,
            check_interactions=check_interactions,
            sample_interval_ms=sample_interval_ms,
            max_depth=max_depth,
        )

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
    def audit_page_spec(
        sandbox_name: str,
        page_id: int,
        include_structured_data: bool = True,
        include_resource_hints: bool = True,
        include_meta: bool = True,
    ) -> dict[str, Any]:
        """Audit complete page-level shell specification: preloads, preconnects, stylesheets, icons, meta tags, and JSON-LD structured data."""
        return audit_page_spec_impl(
            sandbox_name,
            page_id,
            include_structured_data=include_structured_data,
            include_resource_hints=include_resource_hints,
            include_meta=include_meta,
        )

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
    def audit_motion(
        sandbox_name: str,
        page_id: int,
        sample_interval_ms: int = 500,
        selector: str = "body",
    ) -> dict[str, Any]:
        """Sample elements over time to detect animations, transitions, and dynamic motion (e.g. floating, sliding, pulsing)."""
        return audit_motion_impl(
            sandbox_name, page_id, sample_interval_ms=sample_interval_ms, selector=selector
        )

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
    def compare_dom_trees(
        sandbox_name: str,
        reference_page_id: int,
        candidate_page_id: int,
        selector: str = "body",
        max_depth: int = 15,
    ) -> dict[str, Any]:
        """Compare DOM tree structures, node counts, interactive elements, text content, and computed layout between two pages."""
        return compare_dom_trees_impl(
            sandbox_name, reference_page_id, candidate_page_id, selector=selector, max_depth=max_depth
        )

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
    def audit_resource_hints(sandbox_name: str, page_id: int) -> dict[str, Any]:
        """Audit resource hints (preload, preconnect, prefetch, stylesheet, icon, meta) in document head."""
        return audit_resource_hints_impl(sandbox_name, page_id)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
    def trace_interactions(sandbox_name: str, page_id: int) -> dict[str, Any]:
        """Trace discoverable links, buttons, forms, and inline interaction handlers."""
        return trace_interactions_impl(sandbox_name, page_id)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
    def capture_screenshot(sandbox_name: str, page_id: int, full_page: bool = True) -> dict[str, Any]:
        """Capture a reference screenshot of the live page."""
        return capture_screenshot_impl(sandbox_name, page_id, full_page)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True))
    def capture_raw_snapshot(
        sandbox_name: str,
        page_id: int,
        full_page_screenshot: bool = True,
    ) -> dict[str, Any]:
        """Preserve rendered DOM, accessible CSS, runtime inventory, and screenshot without conversion."""
        return capture_raw_snapshot_impl(
            sandbox_name,
            page_id,
            full_page_screenshot=full_page_screenshot,
        )

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False))
    def convert_raw_snapshot(
        sandbox_name: str,
        capture_dir: str,
        output_dir: str = "clones/from-raw-snapshot",
    ) -> dict[str, Any]:
        """Convert a saved raw snapshot after verifying its manifest and file hashes."""
        return convert_raw_snapshot_impl(sandbox_name, capture_dir, output_dir)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
    def analyze_structure(evidence: dict[str, Any]) -> dict[str, Any]:
        """Analyze collected inspection evidence into clone structure."""
        return analyze_structure_impl(**evidence)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
    def build_dependency_graph(evidence: dict[str, Any]) -> dict[str, Any]:
        """Build component, asset, style, and behavior dependency relationships."""
        return build_dependency_graph_impl(**evidence)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
    def create_clone_manifest(evidence: dict[str, Any]) -> dict[str, Any]:
        """Create the canonical Clone Manifest used by project generation."""
        return create_clone_manifest_impl(**evidence)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False))
    def generate_project(sandbox_name: str, output_dir: str = "clones", manifest: dict[str, Any] | None = None) -> dict[str, Any]:
        """Generate an editable clone project from a Clone Manifest."""
        return generate_project_impl(sandbox_name, output_dir, manifest)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False))
    def build_project(sandbox_name: str, project_dir: str = "clones") -> dict[str, Any]:
        """Build or validate a generated clone project inside the sandbox."""
        return build_project_impl(sandbox_name, project_dir)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False))
    def serve_project(sandbox_name: str, project_dir: str = "clones", port: int = 4173) -> dict[str, Any]:
        """Serve a generated clone project locally for verification."""
        return serve_project_impl(sandbox_name, project_dir, port)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
    def verify_clone(evidence: dict[str, Any]) -> dict[str, Any]:
        """Verify a clone against collected source evidence and return mismatch categories."""
        return verify_clone_impl(**evidence)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))
    def repair_clone(evidence: dict[str, Any]) -> dict[str, Any]:
        """Repair a clone from actionable verification mismatches when safe strategies exist."""
        return repair_clone_impl(**evidence)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=True))
    def run_clone_workflow(workflow: str, inputs: dict[str, Any]) -> dict[str, Any]:
        """Run a named clone workflow: quick, accurate, forensic, or verify."""
        return run_clone_workflow_impl(workflow, inputs)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False))
    def capture_screenshot_artifact(
        sandbox_name: str,
        page_id: int,
        output_path: str,
        full_page: bool = False,
    ) -> dict[str, Any]:
        """Capture a PNG from an existing page into a new relative workspace path."""
        return capture_screenshot_artifact_impl(
            sandbox_name, page_id, output_path, full_page=full_page
        )

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
    def compare_screenshot_artifacts(
        sandbox_name: str,
        reference_path: str,
        candidate_path: str,
        pixel_threshold: int = 16,
        max_changed_pixel_ratio: float = 0.05,
        max_mean_absolute_error: float = 8.0,
    ) -> dict[str, Any]:
        """Compare two saved PNG screenshots using pixel difference metrics."""
        return compare_screenshot_artifacts_impl(
            sandbox_name,
            reference_path,
            candidate_path,
            pixel_threshold=pixel_threshold,
            max_changed_pixel_ratio=max_changed_pixel_ratio,
            max_mean_absolute_error=max_mean_absolute_error,
        )

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False))
    def verify_clone_with_visual(
        sandbox_name: str,
        reference_page_id: int,
        candidate_page_id: int,
        evidence: dict[str, Any] | None = None,
        output_dir: str = "research/visual-comparison",
        full_page: bool = False,
        pixel_threshold: int = 16,
        max_changed_pixel_ratio: float = 0.05,
        max_mean_absolute_error: float = 8.0,
    ) -> dict[str, Any]:
        """Capture two already-open pages and combine visual comparison with clone evidence."""
        return verify_clone_with_visual_impl(
            sandbox_name,
            reference_page_id,
            candidate_page_id,
            evidence,
            output_dir=output_dir,
            full_page=full_page,
            pixel_threshold=pixel_threshold,
            max_changed_pixel_ratio=max_changed_pixel_ratio,
            max_mean_absolute_error=max_mean_absolute_error,
        )

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=True))
    def create_live_proxy_snapshot(
        sandbox_name: str,
        page_id: int,
        output_dir: str,
        prepare_scroll: bool = True,
        warmup_wait_ms: int = 1500,
        download_module_chunks: bool = True,
        max_chunk_downloads: int = 40,
        max_image_downloads: int = 150,
    ) -> dict[str, Any]:
        """Capture a universal high-fidelity Live-Proxy Snapshot (Stage 1).

        Auto-scrolls to trigger observers, extracts hydrated DOM, normalizes assets to origin URLs,
        downloads dynamic module chunks, auto-mocks active API endpoints, and injects runtime shims
        for instant local preview.
        """
        return create_live_proxy_snapshot_impl(
            sandbox_name,
            page_id,
            output_dir,
            prepare_scroll=prepare_scroll,
            warmup_wait_ms=warmup_wait_ms,
            download_module_chunks=download_module_chunks,
            max_chunk_downloads=max_chunk_downloads,
            max_image_downloads=max_image_downloads,
        )

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=True))
    def decompose_live_proxy(
        sandbox_name: str,
        source_dir: str,
        output_dir: str,
        format_code: bool = True,
        print_width: int = 120,
        tab_width: int = 2,
        serve_port: int | None = None,
    ) -> dict[str, Any]:
        """Execute Stage 2 Component Decomposition with balanced code formatting.

        Extracts semantic components, decouples inline CSS into src/css/inline-head.css,
        generates master template src/page.html with component slots, formats components
        using balanced vertical rules, and builds index.html.
        """
        return decompose_live_proxy_impl(
            sandbox_name,
            source_dir,
            output_dir,
            format_code=format_code,
            print_width=print_width,
            tab_width=tab_width,
            serve_port=serve_port,
        )

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
    def audit_decomposition_fidelity(
        sandbox_name: str,
        source_dir: str,
        decomposition_dir: str,
        check_dom_parity: bool = True,
        check_assets: bool = True,
        check_formatting_metrics: bool = True,
        max_line_length_threshold: int = 500,
    ) -> dict[str, Any]:
        """Audit Stage 2 Decomposition fidelity, code formatting, and asset integrity.

        Verifies that components exist and are non-empty, formatting is balanced (no minified
        single-line files), local assets like phone frames are present, and DOM landmarks match.
        """
        return audit_decomposition_fidelity_impl(
            sandbox_name,
            source_dir,
            decomposition_dir,
            check_dom_parity=check_dom_parity,
            check_assets=check_assets,
            check_formatting_metrics=check_formatting_metrics,
            max_line_length_threshold=max_line_length_threshold,
        )
