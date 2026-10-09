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
    trace_interactions as trace_interactions_impl,
    verify_clone as verify_clone_impl,
)
from .preserve import (
    capture_raw_snapshot as capture_raw_snapshot_impl,
    convert_raw_snapshot as convert_raw_snapshot_impl,
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
