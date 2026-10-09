# Web-cloning pipeline improvement research

Research date: 2026-10-09

See report content in the conversation summary. Current evidence from web-cloning sandbox: reference https://paypers.ai/; reference height ~10,635 CSS px vs clone ~3,595 px at 1280px; only 6/16 required regions covered and 10 missing. The project already has a reference manifest, Playwright capture script, pixel-diff script, structural audit and tests. Highest priority is to implement missing regions, define interaction/state matrix, make capture deterministic, and gate on coverage + behavior + asset health + responsive checks + region-level visual diffs.

## Key findings

| Finding ID | Area | Finding | Why it matters | Official source / standard | Version/date | Implementation impact |
|---|---|---|---|---|---|---|
| MCP-001 | MCP protocol | MCP is JSON-RPC tool/context orchestration, not a visual-cloning algorithm. | Keep orchestration separate from page reconstruction. | https://github.com/modelcontextprotocol/modelcontextprotocol/blob/2026-07-28/docs/specification/2026-07-28/server/tools.mdx | Spec 2026-07-28 | Use typed discover/capture/inspect/compare/repair tools with structured evidence. |
| MCP-002 | MCP SDK | Official TypeScript SDK v2 documents Zod input schemas, registerTool, transports, and stdout-only protocol for stdio. | Prevent invalid tool inputs and protocol corruption. | https://ts.sdk.modelcontextprotocol.io/v2/get-started/first-server | v2 docs checked 2026-10-09 | Keep MCP server separate from clone; validate inputs, use stderr for logs, add timeouts and allowlists. |
| MCP-003 | MCP security | MCP guidance requires input validation and access controls and recommends rate limits, sanitized outputs, timeouts, audit logs and user confirmation. | Browser tools can navigate URLs and mutate files. | https://github.com/modelcontextprotocol/modelcontextprotocol/blob/2026-07-28/docs/specification/2026-07-28/server/tools.mdx | Spec 2026-07-28 | Restrict URL/path scope; separate read-only inspection from mutation. |
| WEB-001 | HTML | HTML is a living standard; the browser parses source into a DOM. | Regex audits cannot prove rendered structure or visibility. | https://html.spec.whatwg.org/multipage/ | Living standard, updated 2026-09-08 | Audit rendered DOM, landmarks, IDs, accessible names, links and image alt text. |
| CSS-001 | Responsive | Media queries support viewport and user preferences including reduced motion. | Desktop parity is not mobile parity. | https://developer.mozilla.org/en-US/docs/Web/CSS/Guides/Media_queries/Using_for_accessibility | Checked 2026-10-09 | Retain four current viewport profiles; add tablet/reduced-motion where needed. |
| VIS-001 | Visual regression | Playwright screenshot assertions wait for stable consecutive screenshots; rendering depends on browser/OS. | Raw pixel scores can be noisy. | https://playwright.dev/docs/test-snapshots | Docs checked 2026-10-09; project pins ^1.64.0 | Pin browser, OS, fonts, DPR, locale, timezone, viewport and state. |
| VIS-002 | Visual metrics | Unequal full-page images distort whole-image mismatch percentage. | Missing page height dominates scores and is not a useful styling signal. | Project compare script + Playwright docs | Reviewed 2026-10-09 | Compare section-aligned crops and bounding-box deltas; keep global diff diagnostic only. |
| BROWSER-001 | Playwright | Role-based locators and retrying assertions reduce selector fragility and timing flakes. | Tests should reflect user-visible behavior. | https://playwright.dev/docs/api/class-locator ; https://playwright.dev/docs/test-assertions | Checked 2026-10-09 | Test menus, tabs, carousels, FAQ, cookie consent, keyboard and mobile navigation. |
| BROWSER-002 | CDP | CDP Network domain exposes requests, responses, headers, bodies and timing. | Asset URL inventory alone misses failed loads and MIME/timing issues. | https://github.com/ChromeDevTools/devtools-protocol/blob/master/pdl/domains/Network.pdl | Living protocol | Record status, MIME, resource type, redirects, timing and failures. |
| STD-001 | Automation standard | WebDriver BiDi is a W3C Working Draft with bidirectional event streaming. | Useful future interoperability, not a reason to replace working Playwright now. | https://www.w3.org/TR/webdriver-bidi/ | Working Draft 2026-10-08 | Keep Playwright default; abstract adapter only if cross-browser requirement demands it. |
| A11Y-001 | Accessibility | WCAG 2.2 is a W3C Recommendation; accessible keyboard state is part of behavior parity. | Visual controls must also expose names, focus and expanded/selected state. | https://www.w3.org/TR/WCAG22/ ; https://www.w3.org/WAI/ARIA/apg/patterns/disclosure/ | WCAG Recommendation 2024-12-12 | Add keyboard, focus, aria-expanded and target-size tests plus manual review. |
| NODE-001 | Runtime | Node recommends Active/Maintenance LTS for production. | Version drift causes build and screenshot changes. | https://nodejs.org/en/about/previous-releases | Node 24 LTS observed in project | Pin Node, lockfile, Playwright browser revision and container. |
| DATA-001 | Manifest | Route/region/asset/state inventory should be canonical and machine-readable. | Generator and verifier otherwise disagree on completeness. | Project manifest and audit evidence | 2026-10-09 | Extend existing manifest with stable IDs, selectors, text fingerprints, bounds, states and acceptance criteria. |
| ASSET-001 | Assets | Exact logo, SVGs, fonts, images and videos materially affect pixels. | Generic substitutes create large visible mismatches. | Live Paypers asset trace; manifest | 2026-10-09 | Verify exact asset, dimensions, crop, font load and fallback; reuse only authorized public assets. |
| STATE-001 | Dynamic UI | Counters, videos, tabs, carousels, FAQ and cookie consent create distinct states. | One screenshot cannot represent behavior or all visuals. | Live interaction trace | 2026-10-09 | Define state matrix and capture/test every important state. |
| PERF-001 | Readiness | DOMContentLoaded alone does not guarantee fonts, lazy media, hydration or layout stability. | Captures may be transient. | https://playwright.dev/docs/test-snapshots | Checked 2026-10-09 | Wait for fonts/assets, explicit app state and stable geometry; save diagnostics on timeout. |
| QA-001 | Acceptance | Build success and HTTP 200 do not establish visual equivalence. | The current clone is incomplete despite having build/audit scripts. | Project artifacts inspection-baseline.json and structure-audit.json | 2026-10-09 | Gate on coverage, assets, behavior, responsive checks and region-level visual thresholds. |
| QA-002 | Coverage | 10/16 required regions are missing; clone height is ~33.8% of reference. | Content omissions dominate fidelity loss. | Project baseline + manifest | 2026-10-09 | Implement all regions in reference order before fine styling. |
| QA-003 | Audit | Current audit uses string/regex heuristics; it cannot establish visible order, geometry or interactivity. | False passes are possible. | scripts/audit-page.js and tests/structure.spec.mjs | Reviewed 2026-10-09 | Use Playwright against rendered DOM and verify visibility, order, text, geometry, links and runtime errors. |
| QA-004 | Repair loop | Whole-page pixel mismatch is hard to turn into actionable fixes. | A score alone doesn't tell the agent what to repair. | scripts/compare-visual.mjs | Reviewed 2026-10-09 | Rank region diffs: missing content > assets > geometry/order > typography > colors > micro-details. |

## Priority plan

1. **P0 — Canonical output:** explicitly designate `project/apps/paypers/` as canonical; resolve its difference from `clones/paypers/`.
2. **P0 — Coverage:** implement all 16 regions; require 16/16 visible, ordered and evidenced.
3. **P0 — State matrix:** menus, carousel/steps, pricing tabs, FAQ, cookie state and video fallback/loaded states each get capture + behavior test.
4. **P0 — Release gate:** fail on missing regions, critical asset failures, page errors, broken links, overflow, failed interactions and visual thresholds.
5. **P1 — Deterministic capture:** pin browser/container/fonts and record viewport, DPR, locale, timezone, color scheme, reduced motion, storage/cookies.
6. **P1 — Region-level diffs:** compare section crops and element geometry; report top mismatches with overlays.
7. **P1 — Asset/network audit:** capture status, MIME, dimensions, crop, font/video readiness and failures.
8. **P1 — Interaction tests:** use role-based Playwright locators and verify state transitions including keyboard.
9. **P2 — Cross-browser tests:** add Firefox/WebKit only after Chromium baseline passes and scope claims accordingly.
10. **P2 — Optional MCP service:** add only if external agents need reusable automation; keep separate from cloned site.

## Recommended pipeline

Discover routes → capture DOM/accessibility/assets/network/screenshots per viewport and state → normalize into canonical manifest → map each region to implementation/assets/interactions/tests → generate/build → audit rendered DOM → run interaction/responsive tests → compare aligned region crops and geometry → repair highest-impact mismatches → publish PASS/INCOMPLETE scorecard with evidence provenance.

## Scorecard (avoid a single score)

- Coverage 100%; critical asset health 100%; mapped interactions 100%.
- No unintended overflow; geometry deltas measured per region.
- Per-region pixel and perceptual diffs calibrated against repeat-capture noise.
- Zero uncaught page errors and unexplained critical network failures.
- Accessibility automated checks plus manual keyboard/focus review.
- Matching environment/state provenance for reference and clone.

## Official / primary sources

- MCP spec/tools: https://github.com/modelcontextprotocol/modelcontextprotocol/blob/2026-07-28/docs/specification/2026-07-28/server/tools.mdx
- MCP TS SDK v2: https://ts.sdk.modelcontextprotocol.io/v2/get-started/first-server
- WHATWG HTML: https://html.spec.whatwg.org/multipage/
- Playwright screenshots: https://playwright.dev/docs/test-snapshots
- Playwright locators: https://playwright.dev/docs/api/class-locator
- CDP Network: https://github.com/ChromeDevTools/devtools-protocol/blob/master/pdl/domains/Network.pdl
- WebDriver BiDi: https://www.w3.org/TR/webdriver-bidi/
- WCAG 2.2: https://www.w3.org/TR/WCAG22/
- WAI-ARIA disclosure: https://www.w3.org/WAI/ARIA/apg/patterns/disclosure/
- MDN media-query accessibility: https://developer.mozilla.org/en-US/docs/Web/CSS/Guides/Media_queries/Using_for_accessibility
- Node releases: https://nodejs.org/en/about/previous-releases
- npm scripts: https://docs.npmjs.com/cli/v11/using-npm/scripts/
- web.dev Web Vitals: https://web.dev/articles/vitals-measurement-getting-started

**Limitations:** Based on the Project_Jupyter workspace, live inspection of https://paypers.ai/, and official documentation checked 2026-10-09. The target can change; universal pixel identity across all browsers/devices/states is not guaranteed. Reuse public assets only where authorized; private/authenticated content is out of scope.
