# Browser + Clone MCP App

## V1

The browser feature uses the existing browser OpenShell sandbox and the existing
chrome_devtools service. It does not introduce a second browser automation
stack.

### Tool surface

- browser_open — MCP App-bound tool that opens an HTTP(S) URL and launches the Browser App.
- browser_pages — list browser pages.
- browser_navigate — navigate a page.
- browser_snapshot — accessibility snapshot with DevTools element UIDs.
- browser_screenshot — image result from the isolated browser.
- browser_inspect — inspect a CSS-selected DOM element.
- browser_evaluate — bounded DevTools JavaScript evaluation.
- clone_preview — inspect clone scope without writing files.
- clone_region — write a sanitized static clone of a selected DOM region.
- clone_page — write a sanitized static clone of the current page.

## Security boundary

Arbitrary websites are untrusted content. The source page is rendered only in
the isolated Chrome browser; it is never inserted directly into the MCP App
iframe.

The browser URL validator rejects:

- non-HTTP(S) URLs
- embedded credentials
- localhost / loopback
- private, link-local, reserved, and multicast IP literals

The browser sandbox uses OpenShell network policy. By default it allows public
HTTP/HTTPS endpoints (*:80, *:443). Deployments can replace this with an
explicit BROWSER_ALLOWED_ENDPOINTS allowlist.

Clone output is written only through the sandbox workspace file API. The V1
clone removes executable elements (script, iframe, object, embed), inline event
handlers, refresh meta tags, and dangerous javascript:, vbscript:, and
HTML data URLs.

## Clone scope

V1 is a static clone. It inlines CSS rules that the browser can read and
reports external stylesheets/assets, but does not yet download/re-host every
asset or reproduce backend/API behavior.

The intended next iteration is:

preview -> user approval -> extract assets -> re-host assets -> build -> open clone -> visual diff -> fix
