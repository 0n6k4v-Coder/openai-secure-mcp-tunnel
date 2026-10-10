from __future__ import annotations

import json
import posixpath
import re
from typing import Any

from ..infrastructure.openshell.sandbox import execute_sandbox_argv
from ..sandbox.policy import validate_name

_PROJECT_ROOT = "/workspace/project"

# Node.js runner script for semantic decomposition & balanced formatting
_DECOMPOSITION_RUNNER = r"""
const fs = require('fs');
const path = require('path');

let options = {};
try {
  const stdinData = fs.readFileSync(0, 'utf8');
  options = JSON.parse(stdinData);
} catch (_) {
  const rawArg = (process.argv[1] && process.argv[1] !== '--' ? process.argv[1] : (process.argv[2] || '{}'));
  options = JSON.parse(rawArg);
}

const sourceDir = options.sourceDir;
const targetDir = options.targetDir;
const formatCode = options.formatCode !== false;
const printWidth = options.printWidth || 120;
const tabWidth = options.tabWidth || 2;

// 1. Balanced CSS Formatter
function formatCSS(css) {
  let out = '';
  let indent = 0;
  css = css.replace(/\s+/g, ' ').trim();
  for (let i = 0; i < css.length; i++) {
    const ch = css[i];
    if (ch === '{') {
      out = out.trimEnd() + ' {\n';
      indent++;
      out += ' '.repeat(indent * tabWidth);
    } else if (ch === '}') {
      out = out.trimEnd() + '\n';
      indent = Math.max(0, indent - 1);
      out += ' '.repeat(indent * tabWidth) + '}\n';
      if (indent === 0) out += '\n';
      out += ' '.repeat(indent * tabWidth);
    } else if (ch === ';') {
      out += ';\n' + ' '.repeat(indent * tabWidth);
    } else {
      out += ch;
    }
  }
  return out.trim() + '\n';
}

// 2. Balanced HTML Formatter
function formatHTML(html, maxLineLen = 120, tabSize = 2) {
  const voidTags = new Set(['area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr']);
  const inlineTags = new Set(['a', 'abbr', 'b', 'bdo', 'cite', 'code', 'dfn', 'em', 'i', 'img', 'kbd', 'mark', 'q', 's', 'samp', 'small', 'span', 'strong', 'sub', 'sup', 'time', 'u', 'var', 'svg', 'path', 'circle', 'rect']);

  const tokens = [];
  let idx = 0;
  const len = html.length;

  while (idx < len) {
    if (html.startsWith('<!--', idx)) {
      const end = html.indexOf('-->', idx);
      const text = end === -1 ? html.slice(idx) : html.slice(idx, end + 3);
      tokens.push({ type: 'comment', value: text.trim() });
      idx = end === -1 ? len : end + 3;
    } else if (html.startsWith('<!', idx) || html.startsWith('<?', idx)) {
      const end = html.indexOf('>', idx);
      const text = end === -1 ? html.slice(idx) : html.slice(idx, end + 1);
      tokens.push({ type: 'doctype', value: text.trim() });
      idx = end === -1 ? len : end + 1;
    } else if (html[idx] === '<') {
      const isClosing = html[idx + 1] === '/';
      const end = html.indexOf('>', idx);
      if (end === -1) {
        tokens.push({ type: 'text', value: html.slice(idx).trim() });
        break;
      }
      const raw = html.slice(idx, end + 1);
      const tagNameMatch = raw.match(/^<\/?([a-zA-Z0-9\-]+)/);
      const tagName = tagNameMatch ? tagNameMatch[1].toLowerCase() : '';
      const isSelfClosing = raw.endsWith('/>') || voidTags.has(tagName);

      if (!isClosing && !isSelfClosing && (tagName === 'script' || tagName === 'style' || tagName === 'pre')) {
        const closeTag = '</' + tagName + '>';
        const closeIdx = html.indexOf(closeTag, end + 1);
        if (closeIdx !== -1) {
          const body = html.slice(end + 1, closeIdx);
          tokens.push({ type: 'rawTag', name: tagName, open: raw, body: body, close: closeTag });
          idx = closeIdx + closeTag.length;
          continue;
        }
      }

      tokens.push({
        type: isClosing ? 'close' : 'open',
        name: tagName,
        raw: raw,
        isSelfClosing: !isClosing && isSelfClosing
      });
      idx = end + 1;
    } else {
      const nextOpen = html.indexOf('<', idx);
      const text = nextOpen === -1 ? html.slice(idx) : html.slice(idx, nextOpen);
      const cleaned = text.replace(/\s+/g, ' ');
      if (cleaned.trim().length > 0) {
        tokens.push({ type: 'text', value: cleaned.trim() });
      }
      idx = nextOpen === -1 ? len : nextOpen;
    }
  }

  let out = [];
  let indent = 0;
  const pad = () => ' '.repeat(indent * tabSize);

  for (let i = 0; i < tokens.length; i++) {
    const t = tokens[i];
    if (t.type === 'comment' || t.type === 'doctype') {
      out.push(pad() + t.value);
    } else if (t.type === 'rawTag') {
      out.push(pad() + t.open);
      const bodyLines = t.body.trim().split('\n');
      bodyLines.forEach(l => out.push(' '.repeat((indent + 1) * tabSize) + l.trim()));
      out.push(pad() + t.close);
    } else if (t.type === 'open') {
      let isSingleLineCandidate = false;
      if (inlineTags.has(t.name) || ['h1','h2','h3','h4','h5','h6','p','button','label','li','title'].includes(t.name)) {
        let depth = 1;
        let subTokens = [];
        for (let j = i + 1; j < tokens.length; j++) {
          if (tokens[j].type === 'open' && tokens[j].name === t.name && !tokens[j].isSelfClosing) depth++;
          if (tokens[j].type === 'close' && tokens[j].name === t.name) depth--;
          subTokens.push(tokens[j]);
          if (depth === 0) break;
        }
        if (depth === 0 && subTokens.length > 0 && subTokens.length <= 6) {
          const joined = t.raw + subTokens.map(st => st.raw || st.value || '').join(' ');
          if (joined.length <= maxLineLen && !joined.includes('\n')) {
            isSingleLineCandidate = true;
            out.push(pad() + joined);
            i += subTokens.length;
            continue;
          }
        }
      }

      out.push(pad() + t.raw);
      if (!t.isSelfClosing) {
        indent++;
      }
    } else if (t.type === 'close') {
      indent = Math.max(0, indent - 1);
      out.push(pad() + t.raw);
    } else if (t.type === 'text') {
      out.push(pad() + t.value);
    }
  }

  return out.join('\n') + '\n';
}

// 3. Execution Pipeline
try {
  // Clean up and ensure target directories exist
  fs.rmSync(path.join(targetDir, 'src/components'), { recursive: true, force: true });
  fs.mkdirSync(path.join(targetDir, 'src/components'), { recursive: true });
  fs.mkdirSync(path.join(targetDir, 'src/css'), { recursive: true });
  fs.mkdirSync(path.join(targetDir, 'scripts'), { recursive: true });

  // Read source HTML
  const sourceHtmlPath = path.join(sourceDir, 'index.html');
  if (!fs.existsSync(sourceHtmlPath)) {
    throw new Error('Source index.html not found: ' + sourceHtmlPath);
  }
  let html = fs.readFileSync(sourceHtmlPath, 'utf8');

  // Normalize absolute media URLs to local paths
  html = html.replace(/https:\/\/[^"'\s]+\/videos\//g, '/videos/');
  html = html.replace(/https:\/\/[^"'\s]+\/images\//g, '/images/');

  // Extract inline <style> blocks in <head>
  let combinedCss = '';
  html = html.replace(/<style\b[^>]*>([\s\S]*?)<\/style>/gi, (full, cssBody) => {
    combinedCss += cssBody + '\n';
    return '';
  });

  const formattedCss = formatCode ? formatCSS(combinedCss) : combinedCss;
  fs.writeFileSync(path.join(targetDir, 'src/css/inline-head.css'), formattedCss, 'utf8');

  // Ensure <link rel="stylesheet" href="/src/css/inline-head.css"> in <head>
  if (!html.includes('/src/css/inline-head.css')) {
    html = html.replace('</head>', '  <link rel="stylesheet" href="/src/css/inline-head.css">\n</head>');
  }

  // Identify semantic landmark sections
  // Common landmarks: nav, header, section, footer, overlays/dialogs, scripts
  const landmarkRegex = /<(nav|header|section|footer)\b[^>]*>/gi;
  let match;
  const sections = [];
  const registeredNames = new Set();

  function slugify(text) {
    return text.toLowerCase()
      .replace(/[^a-z0-9\-]/g, '-')
      .replace(/-+/g, '-')
      .replace(/^-|-$/g, '')
      .slice(0, 30);
  }

  function getSectionName(tagOpen) {
    const idMatch = tagOpen.match(/id=["']([^"']+)["']/i);
    if (idMatch) return idMatch[1];

    const ariaMatch = tagOpen.match(/aria-label=["']([^"']+)["']/i);
    if (ariaMatch) {
      const label = ariaMatch[1];
      if (label.includes('บันทึก')) return 'demo-record';
      if (label.includes('ตรวจสอบ')) return 'demo-verify';
      if (label.includes('เดี่ยวหรือกลุ่ม')) return 'group-single';
      if (label.includes('ขั้นตอน')) return 'get-started';
      if (label.includes('ประโยชน์')) return 'benefits';
      if (label.includes('คำถาม')) return 'faq';
      if (label.includes('ราคา') || label.includes('แพ็กเกจ')) return 'pricing';
      const slug = slugify(label);
      if (slug) return slug;
    }

    const tagType = tagOpen.match(/^<([a-z0-9\-]+)/i)[1].toLowerCase();
    if (tagType === 'nav') return 'nav';
    if (tagType === 'footer') return 'footer';
    if (tagOpen.includes('pt-0 pb-10')) return 'stat-logos';
    if (tagOpen.includes('py-16 bg-white')) return 'google-cert';
    return tagType + '-' + (sections.length + 1);
  }

  // Find tags and their closing tag counterparts
  let searchIdx = 0;
  while ((match = landmarkRegex.exec(html)) !== null) {
    const openTag = match[0];
    const tagType = match[1].toLowerCase();
    const startIdx = match.index;

    // find matching end tag
    const closeTag = '</' + tagType + '>';
    let depth = 1;
    let curIdx = startIdx + openTag.length;
    let endIdx = -1;

    while (depth > 0 && curIdx < html.length) {
      const nextOpen = html.indexOf('<' + tagType, curIdx);
      const nextClose = html.indexOf(closeTag, curIdx);

      if (nextClose === -1) break;

      if (nextOpen !== -1 && nextOpen < nextClose) {
        depth++;
        curIdx = nextOpen + 1;
      } else {
        depth--;
        curIdx = nextClose + closeTag.length;
        if (depth === 0) {
          endIdx = curIdx;
          break;
        }
      }
    }

    if (endIdx !== -1 && endIdx > startIdx) {
      let baseName = getSectionName(openTag);
      let compName = baseName;
      let counter = 1;
      while (registeredNames.has(compName)) {
        compName = `${baseName}-${++counter}`;
      }
      registeredNames.add(compName);

      sections.push({
        name: compName,
        start: startIdx,
        end: endIdx,
        raw: html.slice(startIdx, endIdx)
      });
      landmarkRegex.lastIndex = endIdx;
    }
  }

  // Also extract Overlays / Dialogs and Trailing Scripts
  // Replace sections in master template from end to start to maintain indices
  let masterPage = html;
  const emittedComponents = [];

  for (let i = sections.length - 1; i >= 0; i--) {
    const sec = sections[i];
    masterPage = masterPage.slice(0, sec.start) + `<!-- @component ${sec.name} -->` + masterPage.slice(sec.end);
    
    // Save component
    const compContent = formatCode ? formatHTML(sec.raw, printWidth, tabWidth) : sec.raw;
    const compPath = path.join(targetDir, 'src/components', `${sec.name}.html`);
    fs.writeFileSync(compPath, compContent, 'utf8');

    const lines = compContent.split('\n').filter(Boolean);
    const maxLineLen = lines.reduce((max, l) => Math.max(max, l.length), 0);
    emittedComponents.unshift({
      name: sec.name,
      path: `src/components/${sec.name}.html`,
      bytes: Buffer.byteLength(compContent, 'utf8'),
      lines: lines.length,
      maxLineLength: maxLineLen
    });
  }

  // Save master template
  const formattedMasterPage = formatCode ? formatHTML(masterPage, printWidth, tabWidth) : masterPage;
  fs.writeFileSync(path.join(targetDir, 'src/page.html'), formattedMasterPage, 'utf8');

  // Generate scripts/build.js
  const buildScript = `const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const source = path.join(root, 'src/page.html');
const output = path.join(root, 'index.html');
const componentDir = path.join(root, 'src/components');

const template = fs.readFileSync(source, 'utf8');
const html = template.replace(/<!-- @component ([^ ]+) -->/g, (_, name) => {
  const file = path.join(componentDir, name + '.html');
  if (!fs.existsSync(file)) throw new Error('Missing component: ' + name);
  return fs.readFileSync(file, 'utf8').trim();
});

fs.writeFileSync(output, html);
console.log('Built index.html successfully from src/page.html + src/components/*.html');
`;
  fs.writeFileSync(path.join(targetDir, 'scripts/build.js'), buildScript, 'utf8');

  // Execute build.js to generate output index.html
  const buildCmd = require('child_process').spawnSync('node', ['scripts/build.js'], { cwd: targetDir, encoding: 'utf8' });
  if (buildCmd.status !== 0) {
    throw new Error('Build failed: ' + (buildCmd.stderr || buildCmd.stdout));
  }

  const outputIndexPath = path.join(targetDir, 'index.html');
  const indexBytes = fs.existsSync(outputIndexPath) ? fs.statSync(outputIndexPath).size : 0;

  process.stdout.write(JSON.stringify({
    success: true,
    componentsCount: emittedComponents.length,
    components: emittedComponents,
    masterPage: 'src/page.html',
    cssFile: 'src/css/inline-head.css',
    cssBytes: Buffer.byteLength(formattedCss, 'utf8'),
    indexHtmlBytes: indexBytes,
    formatted: formatCode
  }));
} catch (err) {
  process.stderr.write(err.stack || String(err));
  process.exit(1);
}
"""


def _normalize_relative_path(path: str) -> str:
    if (
        not isinstance(path, str)
        or not path
        or path.startswith("/")
        or "\\" in path
        or "\x00" in path
        or any(part in {"", ".", ".."} for part in path.split("/"))
    ):
        raise ValueError("Target directory must be a canonical relative path.")
    normalized = posixpath.normpath(path)
    if normalized != path:
        raise ValueError("Target directory must be canonical.")
    return normalized


def decompose_live_proxy(
    sandbox_name: str,
    source_dir: str,
    output_dir: str,
    *,
    format_code: bool = True,
    print_width: int = 120,
    tab_width: int = 2,
    serve_port: int | None = None,
) -> dict[str, Any]:
    """Execute Stage 2 Component Decomposition with balanced code formatting.

    Extracts semantic components (nav, hero, features, pricing, etc.), decouples inline
    CSS into src/css/inline-head.css, generates master template src/page.html with component
    slots, applies balanced code formatting to preserve hierarchy without oversplitting,
    and builds index.html.
    """
    name = validate_name(sandbox_name)
    norm_source = _normalize_relative_path(source_dir)
    norm_output = _normalize_relative_path(output_dir)

    remote_source = posixpath.join(_PROJECT_ROOT, norm_source)
    remote_output = posixpath.join(_PROJECT_ROOT, norm_output)

    # 1. Verify source exists
    check_source = execute_sandbox_argv(
        name,
        ["test", "-f", f"{remote_source}/index.html"],
    )
    if int(check_source.get("return_code", 1)) != 0:
        raise FileNotFoundError(f"Source index.html not found in {norm_source}")

    # 2. Prepare target directories
    execute_sandbox_argv(
        name,
        ["mkdir", "-p", remote_output],
    )

    # 3. Synchronize static runtime assets (_astro, api, images, videos, .origin)
    copy_script = f"""
cd {remote_source}
for item in _astro api images videos .origin; do
  if [ -e "$item" ]; then
    cp -r "$item" "{remote_output}/"
  fi
done

# Sync any missing image assets from other sibling clones (e.g. apps/paypers/live-proxy/images)
mkdir -p "{remote_output}/images"
for cand_app in /workspace/project/apps/*; do
  if [ -d "$cand_app/live-proxy/images" ]; then
    cp -rn "$cand_app/live-proxy/images/"* "{remote_output}/images/" 2>/dev/null || true
  fi
done
# Also back-sync to source_dir so live-proxy remains self-contained
cp -rn "{remote_output}/images/"* "{remote_source}/images/" 2>/dev/null || true

# Check if videos/frame.png or island.svg is missing and copy from sibling apps if available
mkdir -p "{remote_output}/videos"
for cand in /workspace/project/apps/*/live-proxy/videos /workspace/project/apps/*/decomposition/videos; do
  if [ -f "$cand/frame.png" ]; then
    cp -rn "$cand/"* "{remote_output}/videos/" 2>/dev/null || true
    break
  fi
done
cp -rn "{remote_output}/videos/"* "{remote_source}/videos/" 2>/dev/null || true
"""
    execute_sandbox_argv(name, ["sh", "-c", copy_script])

    # 4. Execute Decomposition & Formatting Runner
    options_json = json.dumps({
        "sourceDir": remote_source,
        "targetDir": remote_output,
        "formatCode": format_code,
        "printWidth": print_width,
        "tabWidth": tab_width,
    })

    runner_res = execute_sandbox_argv(
        name,
        ["node", "-e", _DECOMPOSITION_RUNNER],
        stdin=options_json.encode("utf-8"),
        timeout_seconds=60,
    )

    if int(runner_res.get("return_code", 1)) != 0:
        err = runner_res.get("stderr", "") or runner_res.get("stdout", "")
        raise RuntimeError(f"Decomposition runner failed: {err}")

    raw_stdout = runner_res.get("stdout", "").strip()
    try:
        report = json.loads(raw_stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"Invalid runner output: {raw_stdout}")

    # 5. Start serving if requested
    server_info = None
    if serve_port:
        serve_js = f"""
const http = require('http');
const fs = require('fs');
const path = require('path');

const mime = {{
  '.html': 'text/html',
  '.js': 'application/javascript',
  '.css': 'text/css',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.json': 'application/json'
}};

http.createServer((req, res) => {{
  let reqPath = req.url.split('?')[0];
  if (reqPath === '/') reqPath = '/index.html';
  const filePath = path.join('{remote_output}', reqPath);
  if (fs.existsSync(filePath) && fs.statSync(filePath).isFile()) {{
    const ext = path.extname(filePath);
    res.writeHead(200, {{ 'Content-Type': mime[ext] || 'application/octet-stream', 'Access-Control-Allow-Origin': '*' }});
    fs.createReadStream(filePath).pipe(res);
  }} else {{
    res.writeHead(404);
    res.end('Not Found');
  }}
}}).listen({serve_port}, '0.0.0.0', () => console.log('Serving {remote_output} on {serve_port}'));
"""
        execute_sandbox_argv(
            name,
            ["sh", "-c", f"cat > /tmp/serve_{serve_port}.js && node /tmp/serve_{serve_port}.js > /tmp/serve_{serve_port}.log 2>&1 &"],
            stdin=serve_js.encode("utf-8"),
        )
        server_info = {"port": serve_port, "url": f"http://127.0.0.1:{serve_port}/"}

    report["sandbox_name"] = name
    report["source_dir"] = norm_source
    report["output_dir"] = norm_output
    if server_info:
        report["server"] = server_info

    return report


def audit_decomposition_fidelity(
    sandbox_name: str,
    source_dir: str,
    decomposition_dir: str,
    *,
    check_dom_parity: bool = True,
    check_assets: bool = True,
    check_formatting_metrics: bool = True,
    max_line_length_threshold: int = 500,
) -> dict[str, Any]:
    """Audit Stage 2 Decomposition fidelity, code formatting, and asset integrity.

    Verifies that all components exist and are non-empty, code formatting adheres to
    balanced vertical standards (no 1-line minified files), local assets (such as
    phone frames and videos) are present, and DOM landmarks match the source live-proxy.
    """
    name = validate_name(sandbox_name)
    norm_source = _normalize_relative_path(source_dir)
    norm_decomp = _normalize_relative_path(decomposition_dir)

    remote_source = posixpath.join(_PROJECT_ROOT, norm_source)
    remote_decomp = posixpath.join(_PROJECT_ROOT, norm_decomp)

_AUDIT_RUNNER = r"""
const fs = require('fs');
const path = require('path');

let options = {};
try {
  options = JSON.parse(fs.readFileSync(0, 'utf8'));
} catch (_) {
  options = {};
}

const srcDir = options.sourceDir || '';
const decDir = options.targetDir || '';
const maxLineThreshold = options.maxLineThreshold || 500;

const result = {
  passed: true,
  score: 1.0,
  checks: {},
  formatting: {},
  assets: {},
  domParity: {},
  warnings: [],
  errors: []
};

// 1. Structure & Files Verification
const requiredFiles = ['src/page.html', 'src/css/inline-head.css', 'scripts/build.js', 'index.html'];
const missingFiles = requiredFiles.filter(f => !fs.existsSync(path.join(decDir, f)));
result.checks.requiredFiles = missingFiles.length === 0;
if (missingFiles.length > 0) {
  result.errors.push('Missing required files: ' + missingFiles.join(', '));
}

const compDir = path.join(decDir, 'src/components');
const componentsExist = fs.existsSync(compDir);
result.checks.componentsDirectory = componentsExist;

const components = componentsExist ? fs.readdirSync(compDir).filter(f => f.endsWith('.html')) : [];
result.checks.componentsCount = components.length;
if (components.length === 0) {
  result.errors.push('No HTML components found in src/components');
}

// 2. Formatting Metrics Audit
const unformattedComponents = [];
const componentStats = [];
let totalLines = 0;
let maxComponentLine = 0;

for (const comp of components) {
  const content = fs.readFileSync(path.join(compDir, comp), 'utf8');
  const lines = content.split('\n').filter(Boolean);
  const maxLine = lines.reduce((m, l) => Math.max(m, l.length), 0);
  totalLines += lines.length;
  maxComponentLine = Math.max(maxComponentLine, maxLine);

  componentStats.push({
    name: comp,
    bytes: Buffer.byteLength(content, 'utf8'),
    lines: lines.length,
    maxLineLength: maxLine
  });

  // Flag if component is 1 line or has markup line longer than threshold (ignoring data props)
  const isSingleLine = lines.length <= 1;
  const hasExceedingMarkup = lines.some(l => {
    if (l.length <= maxLineThreshold) return false;
    if (l.includes('props="') || l.includes("props='") || l.includes('data-') || l.includes('<astro-island')) {
      return false;
    }
    return true;
  });

  if (isSingleLine || hasExceedingMarkup) {
    unformattedComponents.push(comp);
  }
}

result.formatting = {
  totalComponents: components.length,
  totalLines: totalLines,
  maxLineLengthObserved: maxComponentLine,
  unformattedComponents: unformattedComponents,
  isBalanced: unformattedComponents.length === 0
};

if (unformattedComponents.length > 0) {
  result.warnings.push('Unformatted / single-line components found: ' + unformattedComponents.join(', '));
}

// 3. Asset Integrity Audit
const phoneFramePath = path.join(decDir, 'videos/frame.png');
const phoneIslandPath = path.join(decDir, 'videos/island.svg');
const hasFrame = fs.existsSync(phoneFramePath);
const hasIsland = fs.existsSync(phoneIslandPath);

// Gather all asset references from components, master layout, and index.html
const allHtmlFiles = [
  path.join(decDir, 'src/page.html'),
  path.join(decDir, 'index.html'),
  ...components.map(c => path.join(compDir, c))
];

const referencedAssets = new Set();
const assetRegex = /(?:src|href|poster)=["'](\/(?:images|illustrations|videos)\/[^"']+)["']/g;

for (const f of allHtmlFiles) {
  if (fs.existsSync(f)) {
    const text = fs.readFileSync(f, 'utf8');
    let m;
    while ((m = assetRegex.exec(text)) !== null) {
      const cleanPath = m[1].split('?')[0].split('#')[0];
      referencedAssets.add(cleanPath);
    }
  }
}

const missingAssets = [];
const verifiedAssets = [];

for (const relAsset of referencedAssets) {
  const localTarget = path.join(decDir, relAsset.replace(/^\//, ''));
  if (fs.existsSync(localTarget)) {
    verifiedAssets.push(relAsset);
  } else {
    missingAssets.push(relAsset);
  }
}

result.assets = {
  phoneFrameExists: hasFrame,
  phoneIslandExists: hasIsland,
  _astroExists: fs.existsSync(path.join(decDir, '_astro')),
  imagesExists: fs.existsSync(path.join(decDir, 'images')),
  totalReferencedAssets: referencedAssets.size,
  verifiedAssetsCount: verifiedAssets.length,
  missingAssetsCount: missingAssets.length,
  missingAssets: missingAssets,
  allReferencedAssetsExist: missingAssets.length === 0
};

if (!hasFrame) {
  result.warnings.push('Phone frame asset missing: videos/frame.png');
}
if (!hasIsland) {
  result.warnings.push('Phone dynamic island asset missing: videos/island.svg');
}
if (missingAssets.length > 0) {
  result.warnings.push('Missing referenced local assets (' + missingAssets.length + '): ' + missingAssets.join(', '));
}

// 4. DOM Landmark Parity
const srcIndex = fs.existsSync(path.join(srcDir, 'index.html')) ? fs.readFileSync(path.join(srcDir, 'index.html'), 'utf8') : '';
const decIndex = fs.existsSync(path.join(decDir, 'index.html')) ? fs.readFileSync(path.join(decDir, 'index.html'), 'utf8') : '';

const srcSections = (srcIndex.match(/<section\b[^>]*>/gi) || []).length;
const decSections = (decIndex.match(/<section\b[^>]*>/gi) || []).length;
const srcNavs = (srcIndex.match(/<nav\b[^>]*>/gi) || []).length;
const decNavs = (decIndex.match(/<nav\b[^>]*>/gi) || []).length;

result.domParity = {
  sourceSections: srcSections,
  decompositionSections: decSections,
  sourceNavs: srcNavs,
  decompositionNavs: decNavs,
  sectionsMatch: srcSections === decSections,
  navsMatch: srcNavs === decNavs
};

if (srcSections !== decSections) {
  result.warnings.push('Section count mismatch: source has ' + srcSections + ', decomposition has ' + decSections);
}

// Compute Final Score
let deductions = 0;
if (!result.checks.requiredFiles) deductions += 0.3;
if (components.length === 0) deductions += 0.4;
if (unformattedComponents.length > 0) deductions += 0.15;
if (!hasFrame || !hasIsland) deductions += 0.1;
if (missingAssets.length > 0) deductions += 0.15;
if (!result.domParity.sectionsMatch) deductions += 0.05;

result.score = Math.max(0, Math.round((1.0 - deductions) * 100) / 100);
result.passed = result.errors.length === 0 && result.score >= 0.85;

process.stdout.write(JSON.stringify(result));
"""


def audit_decomposition_fidelity(
    sandbox_name: str,
    source_dir: str,
    decomposition_dir: str,
    *,
    check_dom_parity: bool = True,
    check_assets: bool = True,
    check_formatting_metrics: bool = True,
    max_line_length_threshold: int = 500,
) -> dict[str, Any]:
    """Audit Stage 2 Decomposition fidelity, code formatting, and asset integrity.

    Verifies that all components exist and are non-empty, code formatting adheres to
    balanced vertical standards (no 1-line minified files), local assets (such as
    phone frames and videos) are present, and DOM landmarks match the source live-proxy.
    """
    name = validate_name(sandbox_name)
    norm_source = _normalize_relative_path(source_dir)
    norm_decomp = _normalize_relative_path(decomposition_dir)

    remote_source = posixpath.join(_PROJECT_ROOT, norm_source)
    remote_decomp = posixpath.join(_PROJECT_ROOT, norm_decomp)

    options_json = json.dumps({
        "sourceDir": remote_source,
        "targetDir": remote_decomp,
        "maxLineThreshold": max_line_length_threshold,
    })

    audit_res = execute_sandbox_argv(
        name,
        ["node", "-e", _AUDIT_RUNNER],
        stdin=options_json.encode("utf-8"),
        timeout_seconds=30,
    )

    if int(audit_res.get("return_code", 1)) != 0:
        err = audit_res.get("stderr", "") or audit_res.get("stdout", "")
        raise RuntimeError(f"Audit runner failed: {err}")

    raw_stdout = audit_res.get("stdout", "").strip()
    try:
        data = json.loads(raw_stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"Invalid audit output: {raw_stdout}")

    data["sandbox_name"] = name
    data["source_dir"] = norm_source
    data["decomposition_dir"] = norm_decomp
    return data
