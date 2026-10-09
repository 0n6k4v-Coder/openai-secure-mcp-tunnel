from __future__ import annotations

import json
from typing import Any

from .chrome import (
    BrowserError,
    evaluate,
    extract_clone_payload,
    inspect_selector,
    list_pages,
    open_page,
    screenshot,
    take_snapshot,
)
from ..infrastructure.openshell.sandbox import execute_sandbox_argv
from ..infrastructure.openshell.sandbox_files import create_sandbox_workspace_directory, write_sandbox_file
from ..sandbox.policy import validate_name
from .workflow.engine import WorkflowEngine


def discover_site(sandbox_name: str, url: str) -> dict[str, Any]:
    validate_name(sandbox_name)
    opened = open_page(sandbox_name, url)
    return {"url": url, "page_id": opened.get("page_id"), "pages": list_pages(sandbox_name)}


def inspect_page(sandbox_name: str, page_id: int, selector: str | None = None) -> dict[str, Any]:
    if selector:
        return inspect_selector(sandbox_name, page_id, selector)
    return take_snapshot(sandbox_name, page_id, verbose=True)


def inspect_runtime(sandbox_name: str, page_id: int) -> dict[str, Any]:
    script = """() => ({
      url: location.href,
      readyState: document.readyState,
      title: document.title,
      viewport: {width: innerWidth, height: innerHeight, dpr: devicePixelRatio},
      bodyClass: document.body?.className || '',
      htmlClass: document.documentElement?.className || '',
      scroll: {x: scrollX, y: scrollY, height: document.documentElement.scrollHeight},
      scripts: [...document.scripts].map(s => s.src).filter(Boolean),
      stylesheets: [...document.styleSheets].map(s => s.href).filter(Boolean),
    })"""
    return evaluate(sandbox_name, page_id, script)["result"]


def inspect_styles(sandbox_name: str, page_id: int, selector: str = "body") -> dict[str, Any]:
    script = f"""() => {{
      const el = document.querySelector({json.dumps(selector)});
      if (!el) return {{found:false, selector:{json.dumps(selector)}}};
      const s = getComputedStyle(el);
      return {{found:true, selector:{json.dumps(selector)}, computed:Object.fromEntries([
        'display','position','width','height','margin','padding','fontFamily','fontSize','fontWeight',
        'lineHeight','letterSpacing','color','backgroundColor','border','borderRadius','boxShadow','transform'
      ].map(k => [k, s[k]]))}};
    }}"""
    return evaluate(sandbox_name, page_id, script)["result"]


def trace_assets(sandbox_name: str, page_id: int) -> dict[str, Any]:
    script = """() => ({
      images: [...document.images].map(x => ({src:x.currentSrc || x.src, width:x.naturalWidth, height:x.naturalHeight})),
      videos: [...document.querySelectorAll('video,source')].map(x => x.currentSrc || x.src).filter(Boolean),
      fonts: [...document.fonts].map(x => x.family),
      stylesheets: [...document.querySelectorAll('link[rel~="stylesheet"]')].map(x => x.href).filter(Boolean),
      scripts: [...document.scripts].map(x => x.src).filter(Boolean),
    })"""
    return evaluate(sandbox_name, page_id, script)["result"]


def trace_interactions(sandbox_name: str, page_id: int) -> dict[str, Any]:
    script = """() => ({
      links: [...document.querySelectorAll('a[href]')].map(x => ({text:(x.innerText||'').trim().slice(0,200), href:x.href})),
      buttons: [...document.querySelectorAll('button,[role="button"]')].map(x => ({text:(x.innerText||x.getAttribute('aria-label')||'').trim().slice(0,200), id:x.id||null, className:typeof x.className==='string'?x.className:null})),
      inlineHandlers: [...document.querySelectorAll('*')].flatMap(x => [...x.attributes].filter(a => a.name.startsWith('on')).map(a => ({tag:x.tagName, event:a.name}))).slice(0,500),
      forms: [...document.forms].map(x => ({action:x.action, method:x.method}))
    })"""
    return evaluate(sandbox_name, page_id, script)["result"]


def capture_screenshot(sandbox_name: str, page_id: int, full_page: bool = True) -> dict[str, Any]:
    data = screenshot(sandbox_name, page_id, full_page=full_page)
    return {"page_id": page_id, "mime_type": "image/jpeg", "bytes": len(data)}


def analyze_structure(**evidence: Any) -> dict[str, Any]:
    return {
        "kind": "clone_structure",
        "evidence_keys": sorted(evidence),
        "pages": evidence.get("discover", {}).get("pages", []) if isinstance(evidence.get("discover"), dict) else [],
    }


def build_dependency_graph(**evidence: Any) -> dict[str, Any]:
    return {"nodes": [], "edges": [], "source_steps": sorted(evidence)}


def create_clone_manifest(**evidence: Any) -> dict[str, Any]:
    manifest = {
        "version": "1",
        "site": evidence.get("discover", {}),
        "inspection": {key: value for key, value in evidence.items() if key != "discover"},
        "structure": evidence.get("analyze", {}),
        "dependencies": evidence.get("dependencies", {}),
    }
    return manifest


import base64


import gzip


def generate_project(sandbox_name: str, output_dir: str = "clones", manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    name = validate_name(sandbox_name)
    manifest = manifest or {}
    manifest_bytes = json.dumps(manifest, indent=2, default=str).encode("utf-8")
    index_bytes = b"<!doctype html><html><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>Clone</title></head><body><main id=\"app\"></main></body></html>"

    try:
        create_sandbox_workspace_directory(name, output_dir)
        write_sandbox_file(name, f"{output_dir}/clone-manifest.json", manifest_bytes.decode("utf-8"))
        write_sandbox_file(name, f"{output_dir}/index.html", index_bytes.decode("utf-8"))
    except Exception:
        # Fallback for environments lacking python runtime (e.g. browser containers with node/shell)
        compressed_manifest = gzip.compress(manifest_bytes)
        cmd = f"""
mkdir -p /workspace/{output_dir}
gzip -d > /workspace/{output_dir}/clone-manifest.json
cat << 'EOF' > /workspace/{output_dir}/index.html
<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Clone</title></head><body><main id="app"></main></body></html>
EOF
"""
        result = execute_sandbox_argv(name, ["sh", "-lc", cmd], stdin=compressed_manifest, timeout_seconds=30)
        if int(result.get("return_code", 1)) != 0:
            raise RuntimeError(str(result.get("stderr") or "Failed to generate project."))

    return {"output_dir": output_dir, "manifest": f"{output_dir}/clone-manifest.json", "entrypoint": f"{output_dir}/index.html"}


def build_project(sandbox_name: str, project_dir: str = "clones") -> dict[str, Any]:
    result = execute_sandbox_argv(validate_name(sandbox_name), ["sh", "-lc", f"cd /workspace/{project_dir} 2>/dev/null || cd {project_dir}; if [ -f package.json ]; then npm run build; else test -f index.html; fi"], timeout_seconds=120)
    return {"project_dir": project_dir, "return_code": result.get("return_code"), "stdout": result.get("stdout", ""), "stderr": result.get("stderr", "")}


def serve_project(sandbox_name: str, project_dir: str = "clones", port: int = 4173) -> dict[str, Any]:
    name = validate_name(sandbox_name)
    node_server = f"""
const http = require('http');
const fs = require('fs');
const path = require('path');
const dir = path.resolve('/workspace/{project_dir}');
const port = {int(port)};
const server = http.createServer((req, res) => {{
  let p = path.join(dir, req.url.split('?')[0]);
  if (fs.existsSync(p) && fs.statSync(p).isDirectory()) p = path.join(p, 'index.html');
  if (!fs.existsSync(p)) {{ res.writeHead(404); return res.end('Not Found'); }}
  res.writeHead(200);
  fs.createReadStream(p).pipe(res);
}});
server.listen(port, '0.0.0.0');
"""
    node_b64 = base64.b64encode(node_server.encode("utf-8")).decode("ascii")
    command = f"""
if command -v python >/dev/null 2>&1; then
  cd /workspace/{project_dir} 2>/dev/null || cd {project_dir}; nohup python -m http.server {int(port)} >/tmp/clone-{int(port)}.log 2>&1 & echo $!
elif command -v python3 >/dev/null 2>&1; then
  cd /workspace/{project_dir} 2>/dev/null || cd {project_dir}; nohup python3 -m http.server {int(port)} >/tmp/clone-{int(port)}.log 2>&1 & echo $!
elif command -v node >/dev/null 2>&1; then
  nohup node -e "$(printf '%s' '{node_b64}' | base64 -d)" >/tmp/clone-{int(port)}.log 2>&1 & echo $!
else
  echo "No server runtime found (python or node required)" >&2
  exit 1
fi
"""
    result = execute_sandbox_argv(name, ["sh", "-lc", command], timeout_seconds=15)
    return {"project_dir": project_dir, "port": port, "pid": str(result.get("stdout", "")).strip(), "url": f"http://127.0.0.1:{port}"}


def verify_clone(**evidence: Any) -> dict[str, Any]:
    return {"status": "requires_review", "structural": None, "visual": None, "assets": None, "behavior": None, "evidence_keys": sorted(evidence)}


def repair_clone(**evidence: Any) -> dict[str, Any]:
    return {"status": "no_automatic_repairs", "reason": "Repair strategies are not enabled until verification produces actionable mismatch records.", "evidence_keys": sorted(evidence)}


def _operations() -> dict[str, Any]:
    return {
        "discover_site": discover_site,
        "inspect_page": inspect_page,
        "inspect_runtime": inspect_runtime,
        "inspect_styles": inspect_styles,
        "trace_assets": trace_assets,
        "trace_interactions": trace_interactions,
        "capture_screenshot": capture_screenshot,
        "analyze_structure": analyze_structure,
        "build_dependency_graph": build_dependency_graph,
        "create_clone_manifest": create_clone_manifest,
        "generate_project": generate_project,
        "build_project": build_project,
        "serve_project": serve_project,
        "verify_clone": verify_clone,
        "repair_clone": repair_clone,
    }


def run_clone_workflow(workflow: str, inputs: dict[str, Any]) -> dict[str, Any]:
    result = WorkflowEngine(_operations()).run(workflow, inputs)
    return {"run_id": result.run_id, "workflow": result.workflow, "status": result.status, "steps": [step.__dict__ for step in result.steps], "output": result.output}
