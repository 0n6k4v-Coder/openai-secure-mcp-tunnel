# Website Clone Subsystem

## Overview

The website clone subsystem enables discovery, inspection, structural analysis, project generation, build verification, and automated repair of websites directly within isolated OpenShell sandboxes using Chrome DevTools Protocol (CDP).

Headless Chrome automation runs strictly inside an isolated OpenShell browser sandbox without exposing interactive browser relay tools.

## Tool Surface (16 Tools)

### Discovery & Inspection
- `discover_site` — Open target URL and detect initial page metadata.
- `inspect_page` — Extract DOM tree and accessibility snapshot.
- `inspect_runtime` — Read runtime readiness, viewport dimensions, and document states.
- `inspect_styles` — Extract computed styles and font definitions for selected elements.
- `trace_assets` — Enumerate stylesheets, images, scripts, fonts, and media.
- `trace_interactions` — Detect interactive elements (links, forms, buttons).
- `capture_screenshot` — Capture JPEG screenshot of the target page for visual reference.

### Analysis & Manifest Creation
- `analyze_structure` — Parse layout hierarchy, navigation, and content sections.
- `build_dependency_graph` — Compute asset and route dependency graph.
- `create_clone_manifest` — Generate complete machine-readable clone specification.

### Code Generation & Build
- `generate_project` — Scaffold static/modern frontend project based on clone manifest.
- `build_project` — Execute build pipeline in sandbox workspace.
- `serve_project` — Start local preview server in sandbox workspace.

### Verification & Repair
- `verify_clone` — Compare clone DOM structure and assets against original evidence.
- `repair_clone` — Apply corrective patches to missing elements, broken styles, or assets.
- `run_clone_workflow` — Orchestrate end-to-end multi-phase cloning workflow.

## Security Boundaries

1. **Isolation:** External web content executes only inside the isolated headless Chrome instance in an OpenShell sandbox container.
2. **URL Validation:** The target URL validator rejects non-HTTP(S) schemes, embedded credentials, loopback addresses (`127.0.0.1`, `localhost`), and private / link-local RFC 1918 / RFC 3927 IP ranges.
3. **Workspace Boundary:** Project files and assets are written exclusively to the sandbox's authorized workspace path.
4. **Sanitization:** Scripts, inline event handlers, `javascript:` / `vbscript:` schemes, and unsafe data URIs are neutralized.
