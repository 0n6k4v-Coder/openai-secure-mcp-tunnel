# Clone Visual Verification

## Purpose

The visual tools add repeatable PNG screenshot comparison to the existing website-cloning MCP server. They use the existing Chrome DevTools CLI and OpenShell sandbox execution boundary; no new third-party dependency is required.

Pixel comparison complements structural inspection, asset tracing, build validation, interaction testing, and accessibility evaluation. It does not replace them.

## Tools

### \`capture_screenshot_artifact\`

Captures an already-open browser page as a PNG and writes it under \`/workspace/project\` in the selected sandbox.

Required arguments:
- \`sandbox_name\`: existing browser sandbox name
- \`page_id\`: existing browser page ID
- \`output_path\`: new canonical relative path ending in \`.png\`

Optional argument:
- \`full_page\`: capture the full page; defaults to false

Absolute paths, traversal segments, backslashes, and existing destinations are rejected. The image is validated as a bounded PNG before the tool reports success.

### \`compare_screenshot_artifacts\`

Compares two PNG artifacts in the same sandbox. Dimensions must match; images are not scaled.

Default thresholds:
- \`pixel_threshold = 16\`: per-channel difference above which a pixel counts as changed
- \`max_changed_pixel_ratio = 0.05\`: maximum fraction of changed pixels
- \`max_mean_absolute_error = 8.0\`: maximum average absolute RGB-channel error on a 0–255 scale

The result contains the compared dimensions, pixel count, mean absolute error, changed-pixel count and ratio, thresholds, and pass/fail status.

### \`verify_clone_with_visual\`

Captures two already-open pages, compares them, and combines the visual result with existing structural/build/behavior evidence. The reference and candidate page IDs must differ. The tool does not navigate to arbitrary URLs; use the existing site discovery and browser network policy to open pages.

This operation is explicit. The \`accurate\`, \`forensic\`, and \`verify\` workflows pass structural/build evidence to the existing verifier, but they do not automatically open both pages and invoke visual comparison.

## Limits

The decoder supports non-interlaced, 8-bit RGB and RGBA PNG files. It rejects unsupported PNG modes rather than silently treating them as equivalent.

- Maximum encoded PNG size: 8 MiB.
- Maximum decoded dimensions: 8,000,000 pixels.
- No automatic masking of dynamic content.
- No font-rendering or animation compensation.
- Large full-page screenshots may exceed limits; use viewport screenshots if needed.

For reproducible comparisons, keep viewport size, device scale factor, browser configuration, fonts, scroll position, and page state consistent. Wait for animations and dynamic content to settle. Timestamps, rotating banners, and randomized content may legitimately differ.

## Security

- Screenshot paths are relative to the approved project root.
- Existing destinations are not overwritten.
- Parent directories and resolved artifact paths are checked for symlinks.
- File size and decoded image dimensions are bounded.
- Browser navigation remains governed by the existing browser URL validation and network policy.

Path existence checks and writes are separate sandbox commands, so a concurrent process with write access could race the destination check. Use an isolated sandbox/workspace when multiple untrusted writers may operate concurrently.

## Accessibility and behavior

Pixel similarity does not prove keyboard operability, screen-reader compatibility, semantic correctness, or WCAG conformance. Keep interaction and accessibility checks separate. WCAG 2.2 remains the reference for the accessibility criteria selected by the project.

## Official references

- [Chrome DevTools MCP tool reference](https://github.com/ChromeDevTools/chrome-devtools-mcp/blob/main/docs/tool-reference.md) — documents screenshot capture and its \`png\`, \`jpeg\`, and \`webp\` formats.
- [MCP Python SDK server documentation](https://py.sdk.modelcontextprotocol.io/api/mcp/server/mcpserver/server/) — documents MCP server tool registration and annotations.
- [W3C PNG Specification, Third Edition](https://www.w3.org/TR/png-3/) — normative format and chunk-integrity reference.
- [WCAG 2.2](https://www.w3.org/TR/WCAG/) — accessibility conformance criteria; pixel similarity alone is not a conformance test.
