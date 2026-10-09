# Web-cloning pipeline improvement research

Research date: 2026-10-09  
Implementation source of truth: Project_Jupyter workspace `project/apps/paypers/`; browser inspection sandbox: `web-cloning`.  
Reference: https://paypers.ai/

## Executive summary

The dominant failure is missing page coverage, not insufficient CSS precision. The baseline records a reference height of about **10,635 CSS px** versus **3,595 CSS px** locally at a nominal 1280 px viewport; only **6 of 16 required regions** have evidence markers, leaving 10 required regions uncovered. The missing regions include product demos, document/accounting examples, Drive/Sheets, workflow, solo/group usage, onboarding, trust, testimonials, pricing/credits, and FAQ.

Highest-return path: inventory and model all regions/states → deterministic browser capture → canonical manifest → implement in reference order → verify assets, behavior, responsive layout and per-region visuals → repair by highest-impact mismatch. Do not migrate frameworks first. MCP is orchestration, not a cloning algorithm. Define “1:1” for a specific URL, browser, viewport, DPR, locale, font set, storage/cookie state and interaction state; universal pixel identity across all browsers and dynamic states is not an unconditional guarantee.

## Current-state evidence

| Evidence ID | Observation | Evidence path / source | Consequence |
|---|---|---|---|
| OBS-01 | Reference is https://paypers.ai/; live inspection at 1280 CSS px reports page height around 10,630 px. | `apps/paypers/artifacts/inspection-baseline.json`; live browser runtime | Pin URL, timestamp, viewport, DPR, browser and state in every run. |
| OBS-02 | Clone height was about 3,595 px (33.8% of reference) in the baseline. | `inspection-baseline.json` | Missing content dominates mismatch; implement coverage before micro-styling. |
| OBS-03 | 6/16 regions covered; 10 missing. | `artifacts/structure-audit.json`; `src/data/reference-manifest.json` | Coverage must be a hard gate. |
| OBS-04 | Reference uses branded images, SVGs, IBM Plex Sans Thai, and video assets including Supabase-hosted media. | Live asset trace; manifest | Track response status, intrinsic size, crop/fit, font load and fallback. |
| OBS-05 | Stateful controls include menus, mobile nav, carousels/steps, billing tabs, FAQ, cookie consent, counters and videos. | Live DOM/accessibility and interaction trace | Screenshot-only QA cannot prove behavior parity. |
| OBS-06 | Existing project already has manifest, audit, Playwright capture, pixel diff and tests. | `apps/paypers/` scripts/tests | Improve existing pipeline rather than rebuilding it. |
| OBS-07 | Capture script uses four viewport profiles and records geometry, headings, images, links, buttons and failed requests. | `scripts/capture-visual.mjs` | Add state-specific captures, response statuses, console errors and stable-readiness predicates. |
| OBS-08 | Pixel comparison pads unequal images and reports whole-image mismatch; script warns page-height mismatch distorts full-page scores. | `scripts/compare-visual.mjs` | Add section-aligned comparisons and geometry deltas. |
| OBS-09 | Audit relies on HTML string/regex markers; tests cover landmarks, overflow, anchor targets, image alt/loading and mobile menu. | `scripts/audit-page.js`; `tests/structure.spec.mjs` | Use browser-parsed DOM checks and expand state/keyboard coverage. |
| OBS-10 | Separate `clones/paypers/` is a generic landing page with a title-only manifest, unlike the richer `project/apps/paypers/` project. | `clones/paypers/` | Explicitly declare canonical project/output to avoid repairing the wrong target. |

## Research findings

| Finding ID | Area | Finding | Why it matters | Source / Standard | Version / Date checked | Implementation impact |
|---|---|---|---|---|---|---|
| MCP-001 | MCP protocol | MCP is a JSON-RPC protocol for tools/context, not a visual-cloning algorithm. | Separate orchestration from reconstruction. | [MCP tools spec](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/2026-07-28/docs/specification/2026-07-28/server/tools.mdx) | Spec 2026-07-28; checked 2026-10-09 | Use typed discover/capture/inspect/compare/repair tools returning structured evidence. |
| MCP-002 | MCP SDK | Official TypeScript SDK v2 uses Zod schemas, `registerTool`, documented transports; stdio stdout is protocol-only. | Avoid invalid calls and protocol corruption. | [Official SDK v2 first server](https://ts.sdk.modelcontextprotocol.io/v2/get-started/first-server) | v2 docs checked 2026-10-09 | Keep server separate from cloned site; validate inputs, log to stderr, add timeouts and allowlists. |
| MCP-003 | MCP security | Guidance emphasizes input validation, access controls, rate limits, sanitized outputs, timeouts and user safeguards. | Browser tools can navigate arbitrary URLs and mutate files. | [MCP tools/security](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/2026-07-28/docs/specification/2026-07-28/server/tools.mdx) | Spec 2026-07-28 | Restrict URL/path scope; separate read-only inspection from mutation; redact secrets. |
| WEB-001 | HTML | HTML is a living standard; browsers parse markup into a DOM. | Regex audits cannot prove rendered structure or visibility. | [WHATWG HTML](https://html.spec.whatwg.org/multipage/) | Living Standard updated 2026-09-08 | Audit rendered DOM: landmarks, headings, IDs, links, names, alt text and semantic controls. |
| CSS-001 | Responsive CSS | Media queries adapt layout to viewport and user preferences including reduced motion. | Desktop parity does not imply mobile parity. | [MDN accessibility media queries](https://developer.mozilla.org/en-US/docs/Web/CSS/Guides/Media_queries/Using_for_accessibility); [W3C reduced motion](https://www.w3.org/WAI/WCAG22/Techniques/css/C39.html) | Checked 2026-10-09 | Keep four current viewport profiles; add tablet/reduced-motion profiles as needed. |
| VIS-001 | Visual regression | Playwright screenshot assertions wait for consecutive stable screenshots; output depends on browser/OS/rendering environment. | Raw pixel scores are noisy. | [Playwright visual comparisons](https://playwright.dev/docs/test-snapshots) | Docs checked 2026-10-09; project uses ^1.64.0 | Pin browser/container/fonts/DPR/locale/timezone/viewport; record provenance and mask only documented dynamic regions. |
| VIS-002 | Visual metrics | Unequal full-page images distort whole-image mismatch percentage. | Missing height overwhelms styling signal. | Project `compare-visual.mjs`; Playwright docs | Reviewed 2026-10-09 | Compare region crops and element bounds; use global diff as diagnostic only. |
| BROWSER-001 | Playwright | Role-based locators and retrying assertions reduce selector fragility and timing flakes. | Tests should reflect user-visible behavior. | [Locators](https://playwright.dev/docs/api/class-locator); [assertions](https://playwright.dev/docs/test-assertions) | Checked 2026-10-09 | Test menu, tabs, carousel, FAQ, cookie banner, keyboard and mobile navigation. |
| BROWSER-002 | Browser instrumentation | CDP Network exposes requests, responses, headers, bodies and timing. | Asset URLs alone miss failed loads and MIME/timing issues. | [CDP Network domain](https://github.com/ChromeDevTools/devtools-protocol/blob/master/pdl/domains/Network.pdl) | Living protocol | Record status, MIME, resource type, redirects, timing and failures. |
| STD-001 | Automation standard | WebDriver BiDi defines bidirectional browser automation, but remains a Working Draft. | Future interoperability context; not a reason to replace Playwright now. | [W3C WebDriver BiDi](https://www.w3.org/TR/webdriver-bidi/) | Working Draft 2026-10-08 | Keep Playwright default; abstract adapter only if cross-browser needs justify it. |
| A11Y-001 | Accessibility | WCAG 2.2 is a W3C Recommendation; keyboard state is part of functional parity. | Controls must expose accessible names, focus and expanded/selected state. | [WCAG 2.2](https://www.w3.org/TR/WCAG22/); [ARIA disclosure pattern](https://www.w3.org/WAI/ARIA/apg/patterns/disclosure/) | Recommendation 2024-12-12 | Test focus, keyboard, aria-expanded/selected, target sizes; add manual checks. |
| NODE-001 | Runtime | Node recommends Active/Maintenance LTS for production. | Version drift causes build/screenshot drift. | [Node.js releases](https://nodejs.org/en/about/previous-releases) | Node 24 LTS observed in project | Pin Node, lockfile, Playwright and browser revision, container. |
| NPM-001 | Reproducibility | npm scripts make build/audit/capture/compare/test repeatable. | Repeatability enables safe iteration. | [npm scripts](https://docs.npmjs.com/cli/v11/using-npm/scripts/) | npm v11 docs checked 2026-10-09 | Add one QA command: build → audit → interaction tests → capture → compare → acceptance report. |
| DATA-001 | Manifest | Routes, regions, assets, states and interactions need one canonical machine-readable manifest. | Scattered evidence makes generator/verifier disagree. | Project manifest and audit results | 2026-10-09 | Extend existing JSON with stable IDs, selectors, text fingerprints, bounds, states and acceptance criteria. |
| DATA-002 | Provenance | Live pages change; today’s asset/section inventory is not timeless. | Stale evidence can recreate outdated pages. | Dated project manifest and live inspection | Captured 2026-10-09 | Version evidence with timestamp, URL, browser, viewport/DPR, locale, cookies, response metadata and content hashes. |
| ASSET-001 | Assets | Exact logo, SVGs, fonts, images and videos materially affect pixels. | Generic substitutes create large mismatches. | Live Paypers asset trace and manifest | Observed 2026-10-09 | Match exact asset, dimensions, crop and font; reuse only authorized public assets. |
| STATE-001 | Dynamic UI | Counters, videos, tabs, carousels, FAQ and cookie consent create multiple render states. | One screenshot cannot represent all visuals/behavior. | Live interaction trace | Observed 2026-10-09 | Build state matrix and capture/test each important state. |
| PERF-001 | Readiness | DOMContentLoaded alone does not ensure fonts, lazy media, hydration or layout stability. | Captures can be transient. | [Playwright visual guidance](https://playwright.dev/docs/test-snapshots); [web.dev measurement](https://web.dev/articles/vitals-measurement-getting-started) | Checked 2026-10-09 | Wait for fonts/assets, expected state and stable geometry; save diagnostics on timeout. |
| QA-001 | Acceptance | Build success and HTTP 200 do not establish visual equivalence. | Valid HTML can still omit most of the source. | Project baseline and structure audit | Observed 2026-10-09 | Gate on coverage, assets, behavior, responsive checks and visual thresholds. |
| QA-002 | Coverage | 10/16 regions are missing; clone height is ~33.8% of reference. | Content omissions dominate fidelity loss. | `inspection-baseline.json`, `structure-audit.json` | Observed 2026-10-09 | Implement all regions in reference order before fine styling. |
| QA-003 | Audit quality | String/regex heuristics cannot prove visible order, geometry or interactivity. | A marker can pass while a region is hidden or misplaced. | `scripts/audit-page.js`; `tests/structure.spec.mjs` | Reviewed 2026-10-09 | Use Playwright to verify visibility/order/text/geometry/links and runtime errors. |
| QA-004 | Repair loop | Whole-page mismatch is hard to turn into actionable fixes. | One score does not tell the agent what to repair. | `scripts/compare-visual.mjs` | Reviewed 2026-10-09 | Rank issues: missing content > assets > geometry/order > typography > colors > micro-details. |

## Recommended pipeline

Discover routes → capture screenshots, DOM/accessibility, text, geometry, assets, network and interactions for each viewport/state → normalize into canonical manifest → map region IDs to components/assets/tests → generate/build → rendered-DOM audit → interaction/responsive tests → region-aligned visual comparison → repair highest-impact mismatch → publish PASS/INCOMPLETE scorecard with provenance.

## Prioritized plan

| Priority | Work item | Acceptance condition |
|---|---|---|
| P0 | Declare `project/apps/paypers/` canonical; reconcile its difference from `clones/paypers/`. | All tools report and use the intended project/output path. |
| P0 | Implement all 16 reference regions. | 16/16 present, visible, correctly ordered and evidenced. |
| P0 | Add state matrix for menus, carousel/steps, pricing tabs, FAQ, cookies, video states. | Each state has capture and behavior test. |
| P0 | Add release gate for coverage, critical asset failures, page errors, broken links, overflow, interaction and visual thresholds. | No false “complete” status when a critical gate fails. |
| P1 | Pin browser/container/fonts and capture viewport, DPR, locale, timezone, color scheme, reduced motion and storage. | Repeated captures have low unexplained diff; metadata saved. |
| P1 | Add region-level diff and bounding-box report. | Report names top divergent regions and includes overlays. |
| P1 | Add asset/network audit and role-based interaction tests. | No unexplained critical asset failure; all mapped interactions pass. |
| P2 | Add Firefox/WebKit after Chromium baseline passes if needed. | Browser support is explicitly scoped. |
| P2 | Add Lighthouse/Web Vitals as a separate quality gate. | Performance is reported separately from visual fidelity. |
| P2 | Add separate MCP service only if multiple clients need the pipeline. | Validated inputs, safe URL scope, bounded retries, audit logs. |

## Acceptance scorecard (do not collapse to one percentage)

- Coverage 100%; critical asset health 100%; mapped interactions 100%.
- No unintended overflow; measure per-region bounding-box deltas.
- Per-region pixel/perceptual diff calibrated against repeat-capture noise.
- Zero uncaught page errors and unexplained critical network failures.
- Automated accessibility checks plus manual keyboard/focus review.
- Reference and clone captured in matching environment and state.

## Official / primary sources

- MCP tools/security: https://github.com/modelcontextprotocol/modelcontextprotocol/blob/2026-07-28/docs/specification/2026-07-28/server/tools.mdx
- MCP TypeScript SDK v2: https://ts.sdk.modelcontextprotocol.io/v2/get-started/first-server
- WHATWG HTML: https://html.spec.whatwg.org/multipage/
- Playwright visual comparisons: https://playwright.dev/docs/test-snapshots
- Playwright locators: https://playwright.dev/docs/api/class-locator
- Chrome DevTools Protocol Network: https://github.com/ChromeDevTools/devtools-protocol/blob/master/pdl/domains/Network.pdl
- WebDriver BiDi: https://www.w3.org/TR/webdriver-bidi/
- WCAG 2.2: https://www.w3.org/TR/WCAG22/
- WAI-ARIA disclosure: https://www.w3.org/WAI/ARIA/apg/patterns/disclosure/
- MDN media queries: https://developer.mozilla.org/en-US/docs/Web/CSS/Guides/Media_queries/Using_for_accessibility
- Node.js release schedule: https://nodejs.org/en/about/previous-releases
- npm scripts: https://docs.npmjs.com/cli/v11/using-npm/scripts/
- web.dev Web Vitals: https://web.dev/articles/vitals-measurement-getting-started

Limitations: based on Project_Jupyter workspace, live inspection of https://paypers.ai/, and official docs checked 2026-10-09. The target can change; universal pixel identity across all browsers/devices/states is not guaranteed. Reuse public assets only where authorized; private/authenticated content is out of scope.
