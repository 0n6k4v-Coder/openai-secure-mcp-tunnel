from __future__ import annotations

import html
import json
import posixpath
import re
import time
from html.parser import HTMLParser
import urllib.parse
from typing import Any

from .chrome import (
    ensure_subresource_endpoints_allowed,
    evaluate,
    extract_clone_payload,
    inspect_selector,
    list_pages,
    open_page,
    screenshot,
    take_snapshot,
)
from ..infrastructure.openshell.sandbox import execute_sandbox_argv
from ..sandbox.policy import validate_name
from ..workspace.formatting import format_text_in_sandbox
from .workflow.engine import WorkflowEngine


def discover_site(sandbox_name: str, url: str) -> dict[str, Any]:
    validate_name(sandbox_name)
    opened = open_page(sandbox_name, url)
    return {
        "url": url,
        "page_id": opened.get("page_id"),
        "pages": list_pages(sandbox_name),
    }


def inspect_page(
    sandbox_name: str, page_id: int, selector: str | None = None
) -> dict[str, Any]:
    if selector:
        return inspect_selector(sandbox_name, page_id, selector)

    snapshot_res = take_snapshot(sandbox_name, page_id, verbose=True)
    res: dict[str, Any] = {
        "page_id": page_id,
        "snapshot": snapshot_res.get("snapshot")
        if isinstance(snapshot_res, dict)
        else snapshot_res,
    }

    try:
        payload = extract_clone_payload(sandbox_name, page_id)
        if isinstance(payload, dict) and payload.get("found"):
            for key in (
                "url",
                "title",
                "html",
                "css",
                "externalStylesheets",
                "assets",
            ):
                if key in payload:
                    res[key] = payload[key]
    except Exception:
        pass

    return res


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


def inspect_styles(
    sandbox_name: str, page_id: int, selector: str = "body"
) -> dict[str, Any]:
    script = f"""() => {{
      const el = document.querySelector({json.dumps(selector)});
      if (!el) return {{found:false, selector:{json.dumps(selector)}}};
      const s = getComputedStyle(el);
      const rect = el.getBoundingClientRect();
      const children = Array.from(el.children).slice(0, 10).map(c => ({{
        tag: c.tagName.toLowerCase(),
        id: c.id || null,
        className: (typeof c.className === 'string' ? c.className : '').slice(0, 100),
        rect: {{ width: Math.round(c.getBoundingClientRect().width), height: Math.round(c.getBoundingClientRect().height) }}
      }}));
      return {{
        found: true,
        selector: {json.dumps(selector)},
        rect: {{ x: Math.round(rect.x), y: Math.round(rect.y), width: Math.round(rect.width), height: Math.round(rect.height) }},
        childrenCount: el.children.length,
        textPreview: (el.innerText || '').trim().slice(0, 200),
        children: children,
        computed: Object.fromEntries([
          'display','position','width','height','margin','padding','fontFamily','fontSize','fontWeight',
          'lineHeight','letterSpacing','color','backgroundColor','border','borderRadius','boxShadow','transform'
        ].map(k => [k, s[k]]))
      }};
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
    res = evaluate(sandbox_name, page_id, script)["result"]
    if isinstance(res, dict):
        urls_to_allow: list[str] = []
        for img in res.get("images", []):
            if isinstance(img, dict) and img.get("src"):
                urls_to_allow.append(img["src"])
        for vid in res.get("videos", []):
            if isinstance(vid, str):
                urls_to_allow.append(vid)
        for sheet in res.get("stylesheets", []):
            if isinstance(sheet, str):
                urls_to_allow.append(sheet)
        for s in res.get("scripts", []):
            if isinstance(s, str):
                urls_to_allow.append(s)
        if urls_to_allow:
            try:
                ensure_subresource_endpoints_allowed(sandbox_name, urls_to_allow)
            except Exception:
                pass
    return res


def audit_rendered_assets(sandbox_name: str, page_id: int) -> dict[str, Any]:
    """Audit all rendered media, SVGs, background images, and out-of-flow absolute/fixed elements."""
    script = """() => {
      const images = [...document.querySelectorAll('img')].map(img => ({
        src: img.currentSrc || img.src,
        naturalWidth: img.naturalWidth,
        naturalHeight: img.naturalHeight,
        renderedWidth: Math.round(img.getBoundingClientRect().width),
        renderedHeight: Math.round(img.getBoundingClientRect().height),
        visible: img.getBoundingClientRect().width > 0 && img.getBoundingClientRect().height > 0
      }));

      const svgs = [...document.querySelectorAll('svg')].map(svg => ({
        width: Math.round(svg.getBoundingClientRect().width),
        height: Math.round(svg.getBoundingClientRect().height),
        visible: svg.getBoundingClientRect().width > 0 && svg.getBoundingClientRect().height > 0
      }));

      // Detect all out-of-flow decorative and floating elements (position: absolute / fixed)
      const outOfFlow = [...document.querySelectorAll('*')].filter(el => {
        const pos = window.getComputedStyle(el).position;
        return pos === 'absolute' || pos === 'fixed';
      }).map(el => {
        const rect = el.getBoundingClientRect();
        return {
          tag: el.tagName.toLowerCase(),
          id: el.id || null,
          className: (typeof el.className === 'string' ? el.className : '').slice(0, 100),
          rect: { x: Math.round(rect.x), y: Math.round(rect.y), width: Math.round(rect.width), height: Math.round(rect.height) },
          visible: rect.width > 0 && rect.height > 0
        };
      }).slice(0, 100);

      return {
        imageCount: images.length,
        visibleImageCount: images.filter(i => i.visible).length,
        svgCount: svgs.length,
        visibleSvgCount: svgs.filter(s => s.visible).length,
        outOfFlowCount: outOfFlow.length,
        images: images,
        outOfFlowElements: outOfFlow
      };
    }"""
    return evaluate(sandbox_name, page_id, script)["result"]


def audit_element_fidelity(
    sandbox_name: str,
    reference_page_id: int,
    candidate_page_id: int,
    selector: str = "body",
    *,
    check_motion: bool = True,
    check_interactions: bool = True,
    sample_interval_ms: int = 500,
    max_depth: int = 15,
) -> dict[str, Any]:
    """Unified element audit and comparison: verifies DOM hierarchy, layout, text, interactive elements, continuous motion, and entrance transition specs."""
    # 1. Structural, text, and interactive comparison
    dom_result = compare_dom_trees(
        sandbox_name,
        reference_page_id,
        candidate_page_id,
        selector=selector,
        max_depth=max_depth,
    )

    diffs = list(dom_result.get("diffs", []))

    # 2. Motion and animation audit
    motion_audit: dict[str, Any] = {}
    if check_motion:
        motion_script = f"""async () => {{
          const root = document.querySelector({json.dumps(selector)}) || document.body;
          const elements = [root, ...root.querySelectorAll('*')].slice(0, 200);

          // Web animations API
          const webAnims = (document.getAnimations ? document.getAnimations() : []).filter(a => {{
            try {{ return a.effect && a.effect.target && elements.includes(a.effect.target); }} catch(e) {{ return false; }}
          }}).map(a => {{
            const el = a.effect.target;
            const timing = a.effect.getTiming ? a.effect.getTiming() : {{}};
            return {{
              tag: el.tagName.toLowerCase(),
              id: el.id || null,
              className: (typeof el.className === 'string' ? el.className : '').slice(0, 60),
              playState: a.playState,
              duration: timing.duration,
              delay: timing.delay,
              isEntrance: (timing.iterations === 1 || timing.iterations === undefined) && (timing.duration > 0)
            }};
          }});

          // Framework / Transition metadata (Astro islands, Framer Motion, etc.)
          const islandTransitions = Array.from(root.querySelectorAll('astro-island, [data-framer-name], [data-transition]')).map(isl => ({{
            tag: isl.tagName.toLowerCase(),
            component: isl.getAttribute('component-export') || isl.getAttribute('data-framer-name') || null,
            props: isl.getAttribute('props') || isl.getAttribute('data-props') || null
          }}));

          // Inline dynamic styles indicating entrance state (e.g. opacity: 1; transform: none)
          const motionStyleNodes = elements.filter(el => {{
            const s = el.getAttribute('style') || '';
            return s.includes('opacity') && (s.includes('transform') || s.includes('translate'));
          }}).map(el => ({{
            tag: el.tagName.toLowerCase(),
            className: (typeof el.className === 'string' ? el.className : '').slice(0, 60),
            style: el.getAttribute('style')
          }}));

          // Time sampling for continuous dynamic motion
          const getSnapshot = () => elements.map(el => {{
            const rect = el.getBoundingClientRect();
            const cs = window.getComputedStyle(el);
            return {{
              tag: el.tagName.toLowerCase(),
              id: el.id || null,
              className: (typeof el.className === 'string' ? el.className : '').slice(0, 60),
              rect: {{ x: Math.round(rect.x), y: Math.round(rect.y), width: Math.round(rect.width), height: Math.round(rect.height) }},
              transform: cs.transform,
              opacity: cs.opacity,
              animationName: cs.animationName
            }};
          }});

          const t0 = getSnapshot();
          await new Promise(r => setTimeout(r, {max(100, min(3000, sample_interval_ms))}));
          const t1 = getSnapshot();

          const movingElements = [];
          for (let i = 0; i < t0.length; i++) {{
            const a = t0[i];
            const b = t1[i];
            if (!a || !b) continue;

            const dx = b.rect.x - a.rect.x;
            const dy = b.rect.y - a.rect.y;
            const dw = b.rect.width - a.rect.width;
            const dh = b.rect.height - a.rect.height;
            const transformChanged = a.transform !== b.transform;
            const opacityChanged = a.opacity !== b.opacity;

            const isMoving = Math.abs(dx) > 1 || Math.abs(dy) > 1 || Math.abs(dw) > 1 || Math.abs(dh) > 1 || transformChanged || opacityChanged;
            const hasCssAnimation = a.animationName && a.animationName !== 'none';

            if (isMoving || hasCssAnimation) {{
              movingElements.push({{
                tag: a.tag,
                id: a.id,
                className: a.className,
                delta: {{ x: dx, y: dy, width: dw, height: dh }},
                transformBefore: a.transform,
                transformAfter: b.transform,
                hasCssAnimation: hasCssAnimation,
                animationName: a.animationName
              }});
            }}
          }}

          return {{
            webAnimsCount: webAnims.length,
            webAnims: webAnims,
            islandTransitionsCount: islandTransitions.length,
            islandTransitions: islandTransitions,
            motionStyleNodesCount: motionStyleNodes.length,
            motionStyleNodes: motionStyleNodes,
            movingCount: movingElements.length,
            movingElements: movingElements.slice(0, 30)
          }};
        }}"""

        ref_motion = evaluate(sandbox_name, reference_page_id, motion_script)["result"]
        cand_motion = evaluate(sandbox_name, candidate_page_id, motion_script)["result"]

        motion_audit = {
            "reference": ref_motion,
            "candidate": cand_motion,
        }

        # Check motion mismatch
        if ref_motion.get("movingCount", 0) > 0 and cand_motion.get("movingCount", 0) == 0:
            diffs.append({
                "category": "continuous_motion_missing",
                "message": f"Continuous motion detected on reference ({ref_motion['movingCount']} elements moving) but none on candidate",
                "reference_moving": ref_motion["movingCount"],
                "candidate_moving": 0,
            })

        # Check entrance / island transition hints
        ref_transitions = ref_motion.get("islandTransitionsCount", 0)
        cand_transitions = cand_motion.get("islandTransitionsCount", 0)
        if ref_transitions > 0 and cand_transitions == 0 and cand_motion.get("motionStyleNodesCount", 0) == 0:
            diffs.append({
                "category": "entrance_transitions_missing",
                "message": f"Entrance/interactive transitions detected on reference ({ref_transitions} components) but missing on candidate",
                "reference_transitions": ref_motion.get("islandTransitions"),
            })

    # 3. Interactive state mutation probing (Generic click & state delta comparison)
    interaction_audit: dict[str, Any] = {}
    if check_interactions:
        probe_script = f"""async () => {{
          const root = document.querySelector({json.dumps(selector)}) || document.body;
          const interactiveTargets = Array.from(root.querySelectorAll('button, [role="tab"], [role="button"], input[type="radio"], [data-state], [aria-expanded]')).slice(0, 15);

          const getElementSnapshot = (el) => {{
            const cs = window.getComputedStyle(el);
            return {{
              className: (typeof el.className === 'string' ? el.className : ''),
              ariaExpanded: el.getAttribute('aria-expanded'),
              dataState: el.getAttribute('data-state'),
              active: el.getAttribute('data-active') || el.classList.contains('active'),
              style: el.getAttribute('style') || ''
            }};
          }};

          const getSubtreeMediaSnapshot = () => {{
            const videos = Array.from(root.querySelectorAll('video')).map(v => ({{ src: v.currentSrc || v.src || '', paused: v.paused }}));
            const imgs = Array.from(root.querySelectorAll('img')).map(i => ({{ src: i.currentSrc || i.src || '' }}));
            return {{ videos, imgs }};
          }};

          const probeResults = [];
          for (let i = 0; i < interactiveTargets.length; i++) {{
            const btn = interactiveTargets[i];
            const beforeBtn = getElementSnapshot(btn);
            const beforeMedia = getSubtreeMediaSnapshot();

            // Simulate full click lifecycle
            btn.dispatchEvent(new MouseEvent('mousedown', {{ bubbles: true, cancelable: true }}));
            btn.dispatchEvent(new MouseEvent('mouseup', {{ bubbles: true, cancelable: true }}));
            btn.dispatchEvent(new MouseEvent('click', {{ bubbles: true, cancelable: true }}));

            await new Promise(r => setTimeout(r, 150));

            const afterBtn = getElementSnapshot(btn);
            const afterMedia = getSubtreeMediaSnapshot();

            const btnChanged = beforeBtn.className !== afterBtn.className ||
                               beforeBtn.ariaExpanded !== afterBtn.ariaExpanded ||
                               beforeBtn.dataState !== afterBtn.dataState ||
                               beforeBtn.active !== afterBtn.active;

            const mediaChanged = JSON.stringify(beforeMedia) !== JSON.stringify(afterMedia);

            probeResults.push({{
              index: i,
              tag: btn.tagName.toLowerCase(),
              text: (btn.innerText || '').trim().slice(0, 40),
              hasMutation: btnChanged || mediaChanged,
              btnChanged,
              mediaChanged,
              beforeMedia,
              afterMedia
            }});
          }}

          return {{
            targetCount: interactiveTargets.length,
            mutatedCount: probeResults.filter(p => p.hasMutation).length,
            probes: probeResults
          }};
        }}"""

        ref_probe = evaluate(sandbox_name, reference_page_id, probe_script)["result"]
        cand_probe = evaluate(sandbox_name, candidate_page_id, probe_script)["result"]

        interaction_audit = {
            "reference": ref_probe,
            "candidate": cand_probe,
        }

        # Compare mutation responsiveness
        ref_mutations = ref_probe.get("mutatedCount", 0)
        cand_mutations = cand_probe.get("mutatedCount", 0)

        if ref_mutations > 0 and cand_mutations == 0:
            diffs.append({
                "category": "interaction_unresponsive",
                "message": f"Interactive elements responded to clicks on reference ({ref_mutations} buttons mutated DOM/state) but candidate had 0 mutations (completely static)",
                "reference_mutated_count": ref_mutations,
                "candidate_mutated_count": 0,
                "mutated_elements_sample": [p for p in ref_probe.get("probes", []) if p.get("hasMutation")][:5]
            })

    return {
        "status": "pass" if not diffs else "diff_detected",
        "selector": selector,
        "diff_count": len(diffs),
        "diffs": diffs,
        "dom_analysis": {
            "reference_node_count": dom_result.get("reference_node_count"),
            "candidate_node_count": dom_result.get("candidate_node_count"),
            "reference_rect": dom_result.get("reference_rect"),
            "candidate_rect": dom_result.get("candidate_rect"),
        },
        "motion_audit": motion_audit,
        "interaction_audit": interaction_audit,
    }


def audit_motion(
    sandbox_name: str,
    page_id: int,
    sample_interval_ms: int = 500,
    selector: str = "body",
) -> dict[str, Any]:
    """Sample elements over time to detect animations, transitions, and dynamic motion (e.g. floating, sliding, pulsing)."""
    script = f"""async () => {{
      const root = document.querySelector({json.dumps(selector)}) || document.body;
      const getSnapshot = () => {{
        const elements = [root, ...root.querySelectorAll('*')].slice(0, 200);
        return elements.map(el => {{
          const rect = el.getBoundingClientRect();
          const style = window.getComputedStyle(el);
          return {{
            tag: el.tagName.toLowerCase(),
            id: el.id || null,
            className: (typeof el.className === 'string' ? el.className : '').slice(0, 60),
            rect: {{ x: Math.round(rect.x), y: Math.round(rect.y), width: Math.round(rect.width), height: Math.round(rect.height) }},
            transform: style.transform,
            opacity: style.opacity,
            animationName: style.animationName,
            transition: style.transition
          }};
        }});
      }};

      const t0 = getSnapshot();
      await new Promise(r => setTimeout(r, {max(100, min(3000, sample_interval_ms))}));
      const t1 = getSnapshot();

      const movingElements = [];
      for (let i = 0; i < t0.length; i++) {{
        const a = t0[i];
        const b = t1[i];
        if (!a || !b) continue;

        const dx = b.rect.x - a.rect.x;
        const dy = b.rect.y - a.rect.y;
        const dw = b.rect.width - a.rect.width;
        const dh = b.rect.height - a.rect.height;
        const transformChanged = a.transform !== b.transform;
        const opacityChanged = a.opacity !== b.opacity;

        const isMoving = Math.abs(dx) > 1 || Math.abs(dy) > 1 || Math.abs(dw) > 1 || Math.abs(dh) > 1 || transformChanged || opacityChanged;
        const hasCssAnimation = a.animationName && a.animationName !== 'none';

        if (isMoving || hasCssAnimation) {{
          movingElements.push({{
            tag: a.tag,
            id: a.id,
            className: a.className,
            delta: {{ x: dx, y: dy, width: dw, height: dh }},
            transformBefore: a.transform,
            transformAfter: b.transform,
            hasCssAnimation: hasCssAnimation,
            animationName: a.animationName
          }});
        }}
      }}

      return {{
        totalSampled: t0.length,
        movingCount: movingElements.length,
        hasMotion: movingElements.length > 0,
        movingElements: movingElements.slice(0, 30)
      }};
    }}"""
    return evaluate(sandbox_name, page_id, script)["result"]


def compare_dom_trees(
    sandbox_name: str,
    reference_page_id: int,
    candidate_page_id: int,
    selector: str = "body",
    max_depth: int = 15,
) -> dict[str, Any]:
    """Compare DOM tree structures, node counts, interactive elements, text content, and computed layout between two pages."""
    extract_script = f"""() => {{
      const root = document.querySelector({json.dumps(selector)});
      if (!root) return {{ found: false, selector: {json.dumps(selector)} }};

      function extractNode(el, depth) {{
        if (!el || depth > {max(1, min(30, max_depth))}) return null;
        const rect = el.getBoundingClientRect();
        const cs = window.getComputedStyle(el);
        const children = [];
        for (let c of el.children) {{
          const childNode = extractNode(c, depth + 1);
          if (childNode) children.push(childNode);
        }}

        // Direct text
        let directText = '';
        for (let n of el.childNodes) {{
          if (n.nodeType === 3) directText += n.textContent;
        }}
        directText = directText.trim().replace(/\\s+/g, ' ');

        return {{
          tag: el.tagName.toLowerCase(),
          id: el.id || null,
          className: (typeof el.className === 'string' ? el.className : '').trim().slice(0, 100),
          directText: directText.slice(0, 150),
          fullText: (el.innerText || '').trim().replace(/\\s+/g, ' ').slice(0, 200),
          rect: {{ x: Math.round(rect.x), y: Math.round(rect.y), width: Math.round(rect.width), height: Math.round(rect.height) }},
          style: {{
            display: cs.display,
            position: cs.position,
            opacity: cs.opacity,
            transform: cs.transform,
            animationName: cs.animationName,
            transition: cs.transition
          }},
          childCount: children.length,
          children: children
        }};
      }}

      // Count interactive and media elements in subtree
      const images = Array.from(root.querySelectorAll('img')).map(i => ({{
        src: (i.currentSrc || i.src || '').split('/').pop(),
        alt: i.alt || '',
        renderedWidth: Math.round(i.getBoundingClientRect().width),
        renderedHeight: Math.round(i.getBoundingClientRect().height)
      }}));

      const links = Array.from(root.querySelectorAll('a')).map(a => ({{
        text: (a.innerText || '').trim(),
        href: a.href || ''
      }}));

      const buttons = Array.from(root.querySelectorAll('button')).map(b => ({{
        text: (b.innerText || b.getAttribute('aria-label') || '').trim()
      }}));

      return {{
        found: true,
        selector: {json.dumps(selector)},
        tree: extractNode(root, 0),
        images: images,
        links: links,
        buttons: buttons
      }};
    }}"""

    ref_data = evaluate(sandbox_name, reference_page_id, extract_script)["result"]
    cand_data = evaluate(sandbox_name, candidate_page_id, extract_script)["result"]

    if not ref_data.get("found"):
        return {"status": "error", "message": f"Selector not found on reference page: {selector}"}
    if not cand_data.get("found"):
        return {"status": "error", "message": f"Selector not found on candidate page: {selector}"}

    diffs: list[dict[str, Any]] = []

    # 1. Compare node counts
    def count_nodes(node: dict[str, Any] | None) -> int:
        if not node:
            return 0
        return 1 + sum(count_nodes(c) for c in node.get("children", []))

    ref_node_count = count_nodes(ref_data.get("tree"))
    cand_node_count = count_nodes(cand_data.get("tree"))
    if ref_node_count != cand_node_count:
        diffs.append({
            "category": "dom_node_count",
            "message": f"DOM node count mismatch: reference has {ref_node_count} nodes, candidate has {cand_node_count} nodes",
            "reference": ref_node_count,
            "candidate": cand_node_count
        })

    # 2. Compare interactive elements
    ref_links = ref_data.get("links", [])
    cand_links = cand_data.get("links", [])
    if len(ref_links) != len(cand_links):
        diffs.append({
            "category": "links_count",
            "message": f"Link count mismatch: reference has {len(ref_links)}, candidate has {len(cand_links)}",
            "reference": ref_links,
            "candidate": cand_links
        })

    ref_buttons = ref_data.get("buttons", [])
    cand_buttons = cand_data.get("buttons", [])
    if len(ref_buttons) != len(cand_buttons):
        diffs.append({
            "category": "buttons_count",
            "message": f"Button count mismatch: reference has {len(ref_buttons)}, candidate has {len(cand_buttons)}",
            "reference": ref_buttons,
            "candidate": cand_buttons
        })

    # 3. Compare images in selector
    ref_imgs = [i.get("src") for i in ref_data.get("images", []) if i.get("src")]
    cand_imgs = [i.get("src") for i in cand_data.get("images", []) if i.get("src")]
    missing_imgs = set(ref_imgs) - set(cand_imgs)
    if missing_imgs:
        diffs.append({
            "category": "images_missing",
            "message": f"Images missing in candidate: {sorted(missing_imgs)}",
            "missing": sorted(missing_imgs)
        })

    # 4. Compare root dimensions
    ref_rect = ref_data.get("tree", {}).get("rect", {})
    cand_rect = cand_data.get("tree", {}).get("rect", {})
    if (
        abs(ref_rect.get("width", 0) - cand_rect.get("width", 0)) > 2
        or abs(ref_rect.get("height", 0) - cand_rect.get("height", 0)) > 2
    ):
        diffs.append({
            "category": "bounding_box",
            "message": f"Root dimensions mismatch: reference is {ref_rect.get('width')}x{ref_rect.get('height')}, candidate is {cand_rect.get('width')}x{cand_rect.get('height')}",
            "reference": ref_rect,
            "candidate": cand_rect
        })

    # 5. Compare text content
    ref_text = ref_data.get("tree", {}).get("fullText", "")
    cand_text = cand_data.get("tree", {}).get("fullText", "")
    if ref_text != cand_text:
        diffs.append({
            "category": "text_mismatch",
            "message": "Subtree text content differs between reference and candidate",
            "reference_text": ref_text[:200],
            "candidate_text": cand_text[:200]
        })

    return {
        "status": "pass" if not diffs else "diff_detected",
        "selector": selector,
        "diff_count": len(diffs),
        "diffs": diffs,
        "reference_node_count": ref_node_count,
        "candidate_node_count": cand_node_count,
        "reference_rect": ref_rect,
        "candidate_rect": cand_rect
    }


def audit_page_spec(
    sandbox_name: str,
    page_id: int,
    *,
    include_structured_data: bool = True,
    include_resource_hints: bool = True,
    include_meta: bool = True,
) -> dict[str, Any]:
    """Audit complete page-level shell specification: preloads, preconnects, stylesheets, icons, meta tags, and JSON-LD structured data."""
    script = f"""() => {{
      const result = {{}};

      if ({str(include_resource_hints).lower()}) {{
        const links = Array.from(document.querySelectorAll('link')).map(l => ({{
          rel: l.rel,
          href: l.href,
          as: l.as || null,
          type: l.type || null,
          crossorigin: l.crossOrigin || null
        }}));

        result.totalLinks = links.length;
        result.preloads = links.filter(h => h.rel === 'preload');
        result.preloadsCount = result.preloads.length;
        result.preconnects = links.filter(h => h.rel === 'preconnect');
        result.preconnectsCount = result.preconnects.length;
        result.stylesheets = links.filter(h => h.rel === 'stylesheet');
        result.stylesheetsCount = result.stylesheets.length;
        result.icons = links.filter(h => h.rel && h.rel.includes('icon'));
        result.iconsCount = result.icons.length;
      }}

      if ({str(include_meta).lower()}) {{
        const metas = Array.from(document.querySelectorAll('meta')).map(m => ({{
          name: m.getAttribute('name') || m.getAttribute('property') || null,
          content: m.getAttribute('content') || null
        }})).filter(m => m.name && m.content);
        result.metaTags = metas;
        result.metaCount = metas.length;
        result.title = document.title;
      }}

      if ({str(include_structured_data).lower()}) {{
        const structuredData = Array.from(document.querySelectorAll('script[type="application/ld+json"]')).map(s => {{
          try {{ return JSON.parse(s.textContent); }} catch (_) {{ return {{ raw: s.textContent.slice(0, 100) }}; }}
        }});
        result.structuredData = structuredData;
        result.structuredDataCount = structuredData.length;
        result.structuredDataTypes = structuredData.map(d => d['@type'] || 'unknown');
      }}

      return result;
    }}"""
    return evaluate(sandbox_name, page_id, script)["result"]


def audit_resource_hints(
    sandbox_name: str,
    page_id: int,
) -> dict[str, Any]:
    """Backward compatibility wrapper for audit_page_spec."""
    return audit_page_spec(sandbox_name, page_id)


def trace_interactions(sandbox_name: str, page_id: int) -> dict[str, Any]:
    script = """() => ({
      links: [...document.querySelectorAll('a[href]')].map(x => ({text:(x.innerText||'').trim().slice(0,200), href:x.href})),
      buttons: [...document.querySelectorAll('button,[role="button"]')].map(x => ({text:(x.innerText||x.getAttribute('aria-label')||'').trim().slice(0,200), id:x.id||null, className:typeof x.className==='string'?x.className:null})),
      inlineHandlers: [...document.querySelectorAll('*')].flatMap(x => [...x.attributes].filter(a => a.name.startsWith('on')).map(a => ({tag:x.tagName, event:a.name}))).slice(0,500),
      forms: [...document.forms].map(x => ({action:x.action, method:x.method}))
    })"""
    return evaluate(sandbox_name, page_id, script)["result"]


def capture_screenshot(
    sandbox_name: str, page_id: int, full_page: bool = True
) -> dict[str, Any]:
    data = screenshot(sandbox_name, page_id, full_page=full_page)
    return {"page_id": page_id, "mime_type": "image/jpeg", "bytes": len(data)}


def _extract_site_url(evidence: dict[str, Any]) -> str:
    for key in ("discover", "inspect_runtime", "inspect", "inspect_page"):
        val = evidence.get(key)
        if isinstance(val, dict) and val.get("url"):
            return str(val["url"])
    if isinstance(evidence.get("url"), str):
        return evidence["url"]
    return ""


def _extract_site_title(evidence: dict[str, Any], url: str) -> str:
    for key in ("inspect_runtime", "inspect", "inspect_page", "discover"):
        val = evidence.get(key)
        if isinstance(val, dict) and val.get("title"):
            t = str(val["title"]).strip()
            if t:
                return t
    if isinstance(evidence.get("title"), str) and evidence["title"].strip():
        return evidence["title"].strip()
    try:
        host = urllib.parse.urlparse(url).hostname or "Site"
        clean = host.replace("www.", "").split(".")[0].capitalize()
        return clean
    except Exception:
        return "Site"


def _extract_theme(evidence: dict[str, Any]) -> dict[str, Any]:
    styles = evidence.get("inspect_styles", {})
    comp = styles.get("computed", {}) if isinstance(styles, dict) else {}
    return {
        "fontFamily": comp.get("fontFamily")
        or "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
        "fontSize": comp.get("fontSize") or "16px",
        "lineHeight": comp.get("lineHeight") or "1.5",
        "color": comp.get("color") or "rgb(15, 23, 42)",
        "backgroundColor": comp.get("backgroundColor") or "rgb(255, 255, 255)",
    }


def analyze_structure(**evidence: Any) -> dict[str, Any]:
    url = _extract_site_url(evidence)
    title = _extract_site_title(evidence, url)
    theme = _extract_theme(evidence)

    # Extract interactions
    interactions = evidence.get("trace_interactions", {})
    links_data = (
        interactions.get("links", []) if isinstance(interactions, dict) else []
    )
    buttons_data = (
        interactions.get("buttons", []) if isinstance(interactions, dict) else []
    )

    # Extract HTML and CSS if captured
    html_content = ""
    css_content = ""
    external_stylesheets: list[str] = []
    for inspect_key in ("inspect", "inspect_page", "payload", "extract_clone_payload"):
        insp = evidence.get(inspect_key)
        if isinstance(insp, dict):
            if not html_content and (insp.get("html") or insp.get("source_html")):
                html_content = str(insp.get("html") or insp.get("source_html"))
            if not css_content and (insp.get("css") or insp.get("source_css")):
                css_content = str(insp.get("css") or insp.get("source_css"))
            if not external_stylesheets and (insp.get("externalStylesheets") or insp.get("external_stylesheets")):
                external_stylesheets = list(insp.get("externalStylesheets") or insp.get("external_stylesheets") or [])

    # Discovered internal routes
    base_host = urllib.parse.urlparse(url).netloc
    internal_routes: list[dict[str, str]] = []
    seen_routes: set[str] = set()

    for item in links_data:
        if not isinstance(item, dict):
            continue
        href = item.get("href", "")
        text = item.get("text", "").strip()
        if not href or href.startswith("#") or href.startswith("javascript:"):
            continue
        parsed = urllib.parse.urlparse(href)
        if not parsed.netloc or parsed.netloc == base_host:
            route = parsed.path or "/"
            if route not in seen_routes and route != "/":
                seen_routes.add(route)
                clean_text = (
                    text
                    or route.strip("/").replace("-", " ").replace("_", " ").title()
                )
                internal_routes.append({"route": route, "title": clean_text})

    sections = [
        {"id": "header", "type": "header", "name": "ส่วนหัวและการนำทาง (Header & Navigation)"},
        {"id": "hero", "type": "hero", "name": "ส่วนไฮไลท์หลัก (Hero Section)"},
        {"id": "features", "type": "features", "name": "ฟีเจอร์และความสามารถของระบบ (Features)"},
        {"id": "cta", "type": "cta", "name": "ส่วนเริ่มต้นใช้งาน (Call to Action)"},
        {"id": "footer", "type": "footer", "name": "ส่วนท้ายและลิงก์ (Footer)"},
    ]

    components = [
        {"id": "navbar", "name": "Navbar", "elements": len(links_data)},
        {"id": "hero_banner", "name": "HeroBanner", "elements": 1},
        {
            "id": "feature_grid",
            "name": "FeatureGrid",
            "elements": max(3, len(buttons_data)),
        },
        {"id": "action_buttons", "name": "ActionButtons", "elements": len(buttons_data)},
        {"id": "footer_block", "name": "FooterBlock", "elements": 1},
    ]

    pages = [
        {
            "route": "/",
            "title": title,
            "url": url,
            "sections": sections,
            "components": components,
            "layout": "default",
        }
    ]

    for sub in internal_routes[:5]:
        pages.append(
            {
                "route": sub["route"],
                "title": f"{sub['title']} - {title}",
                "url": urllib.parse.urljoin(url, sub["route"]),
                "sections": [
                    {"id": "header", "type": "header", "name": "ส่วนหัว"},
                    {"id": "content", "type": "content", "name": sub["title"]},
                    {"id": "footer", "type": "footer", "name": "ส่วนท้าย"},
                ],
                "components": components,
                "layout": "default",
            }
        )

    return {
        "kind": "clone_structure",
        "evidence_keys": sorted(evidence),
        "site": {
            "title": title,
            "url": url,
        },
        "pages": pages,
        "sections": sections,
        "components": components,
        "theme": theme,
        "source_html": html_content,
        "source_css": css_content,
        "external_stylesheets": external_stylesheets,
    }


def build_dependency_graph(**evidence: Any) -> dict[str, Any]:
    structure = evidence.get("analyze")
    if not isinstance(structure, dict) or not structure.get("pages"):
        clean_evidence = {k: v for k, v in evidence.items() if k != "analyze"}
        structure = analyze_structure(**clean_evidence)

    assets = evidence.get("trace_assets", {})
    interactions = evidence.get("trace_interactions", {})

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    # 1. Page nodes
    for p in structure.get("pages", []):
        p_id = f"page:{p['route']}"
        nodes.append(
            {
                "id": p_id,
                "type": "page",
                "label": p.get("title", p["route"]),
                "route": p["route"],
            }
        )
        if p["route"] != "/":
            edges.append(
                {
                    "source": "page:/",
                    "target": p_id,
                    "relationship": "links_to",
                }
            )

    # 2. Component nodes
    for comp in structure.get("components", []):
        c_id = f"component:{comp['id']}"
        nodes.append(
            {
                "id": c_id,
                "type": "component",
                "label": comp.get("name", comp["id"]),
            }
        )
        edges.append(
            {
                "source": "page:/",
                "target": c_id,
                "relationship": "renders",
            }
        )

    # 3. Asset nodes
    if isinstance(assets, dict):
        for i, sheet in enumerate(assets.get("stylesheets", [])[:10]):
            a_id = f"asset:css:{i}"
            nodes.append(
                {
                    "id": a_id,
                    "type": "stylesheet",
                    "label": "Stylesheet",
                    "url": sheet,
                }
            )
            edges.append(
                {
                    "source": "page:/",
                    "target": a_id,
                    "relationship": "imports",
                }
            )

        for i, font in enumerate(assets.get("fonts", [])[:5]):
            f_id = f"asset:font:{i}"
            nodes.append(
                {
                    "id": f_id,
                    "type": "font",
                    "label": font,
                }
            )
            edges.append(
                {
                    "source": "page:/",
                    "target": f_id,
                    "relationship": "uses_font",
                }
            )

        for i, img in enumerate(assets.get("images", [])[:10]):
            src = img.get("src") if isinstance(img, dict) else img
            if src:
                img_id = f"asset:img:{i}"
                nodes.append(
                    {
                        "id": img_id,
                        "type": "image",
                        "label": "Image Asset",
                        "src": src,
                    }
                )
                edges.append(
                    {
                        "source": "component:hero_banner",
                        "target": img_id,
                        "relationship": "displays",
                    }
                )

    # 4. Interaction nodes
    if isinstance(interactions, dict):
        for i, btn in enumerate(interactions.get("buttons", [])[:10]):
            text = btn.get("text") if isinstance(btn, dict) else "Action"
            b_id = f"interaction:btn:{i}"
            nodes.append(
                {
                    "id": b_id,
                    "type": "interaction",
                    "label": text or "Button",
                }
            )
            edges.append(
                {
                    "source": "component:action_buttons",
                    "target": b_id,
                    "relationship": "triggers",
                }
            )

    return {
        "kind": "dependency_graph",
        "total_nodes": len(nodes),
        "total_edges": len(edges),
        "nodes": nodes,
        "edges": edges,
        "source_steps": sorted(evidence),
    }


def create_clone_manifest(**evidence: Any) -> dict[str, Any]:
    clean_evidence = {k: v for k, v in evidence.items() if k != "analyze"}
    structure = evidence.get("analyze")
    if not isinstance(structure, dict) or not structure.get("pages"):
        structure = analyze_structure(**clean_evidence)

    dependencies = evidence.get("dependencies")
    if not isinstance(dependencies, dict) or not dependencies.get("nodes"):
        dependencies = build_dependency_graph(analyze=structure, **clean_evidence)

    url = _extract_site_url(evidence)
    if not url or urllib.parse.urlsplit(url).scheme.lower() not in {"http", "https"} or not urllib.parse.urlsplit(url).hostname:
        raise ValueError("Could not establish a valid HTTP(S) source URL from the collected evidence.")
    title = _extract_site_title(evidence, url)

    source_html = structure.get("source_html") or ""
    source_css = structure.get("source_css") or ""
    external_stylesheets = list(structure.get("external_stylesheets") or [])

    for k in ("inspect_page", "inspect", "payload", "extract_clone_payload"):
        item = evidence.get(k)
        if isinstance(item, dict):
            if not source_html and (item.get("html") or item.get("source_html")):
                source_html = str(item.get("html") or item.get("source_html"))
            if not source_css and (item.get("css") or item.get("source_css")):
                source_css = str(item.get("css") or item.get("source_css"))
            if not external_stylesheets and (item.get("externalStylesheets") or item.get("external_stylesheets")):
                external_stylesheets = list(item.get("externalStylesheets") or item.get("external_stylesheets") or [])

    manifest = {
        "version": "1.0.0",
        "site": {
            "title": title,
            "url": url,
            "captured_from": evidence.get("discover", {}).get("url") or url,
        },
        "structure": structure,
        "pages": structure.get("pages", []),
        "components": structure.get("components", []),
        "theme": structure.get("theme", {}),
        "dependencies": dependencies,
        "assets": evidence.get("trace_assets", {}),
        "interactions": evidence.get("trace_interactions", {}),
        "source_html": source_html,
        "source_css": source_css,
        "external_stylesheets": external_stylesheets,
    }
    return manifest


_PROJECT_ROOT = "/workspace/project"
_ALLOWED_HTML_TAGS = frozenset({
    "a", "abbr", "article", "aside", "b", "blockquote", "br", "button", "caption",
    "code", "dd", "del", "details", "div", "dl", "dt", "em", "figcaption", "figure",
    "footer", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "i", "img", "input",
    "label", "li", "main", "nav", "ol", "option", "p", "picture", "pre", "section", "select",
    "small", "source", "span", "strong", "sub", "summary", "sup", "table", "tbody", "td",
    "textarea", "th", "thead", "tr", "u", "ul", "video", "audio",
})
_VOID_HTML_TAGS = frozenset({"br", "hr", "img", "input", "source"})
_DROP_CONTENT_TAGS = frozenset({"script", "style", "iframe", "object", "embed", "template", "svg", "math", "noscript"})
_ALLOWED_HTML_ATTRS = frozenset({
    "alt", "aria-label", "aria-hidden", "class", "colspan", "controls", "disabled", "for",
    "height", "href", "id", "label", "name", "placeholder", "poster", "role", "rowspan",
    "selected", "src", "target", "title", "type", "value", "width",
})


def _safe_relative_project_path(value: str, *, field: str = "project_dir") -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise ValueError(f"{field} must be a non-empty relative path.")
    normalized = posixpath.normpath(value.strip())
    if normalized in {".", ".."} or normalized.startswith("../") or normalized.startswith("/") or "\\" in normalized:
        raise ValueError(f"{field} must stay within /workspace/project.")
    if any(part in {"", ".", ".."} for part in normalized.split("/")):
        raise ValueError(f"{field} contains an unsafe path segment.")
    return normalized


def _safe_http_url(value: object) -> str | None:
    if not isinstance(value, str) or not value or any(ord(c) < 32 for c in value):
        return None
    candidate = value.strip()
    parsed = urllib.parse.urlsplit(candidate)
    if parsed.scheme and parsed.scheme.lower() not in {"http", "https"}:
        return None
    if parsed.scheme and not parsed.netloc:
        return None
    if candidate.startswith("//") or "\\" in candidate:
        return None
    if parsed.username is not None or parsed.password is not None:
        return None
    return candidate


class _SafeHTML(HTMLParser):
    """Allowlist sanitizer for captured website markup."""
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.drop_depth = 0
        self.open_tags: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if self.drop_depth:
            if tag in _DROP_CONTENT_TAGS:
                self.drop_depth += 1
            return
        if tag in _DROP_CONTENT_TAGS:
            self.drop_depth = 1
            return
        if tag not in _ALLOWED_HTML_TAGS:
            return
        safe_attrs: list[str] = []
        for key, value in attrs:
            key = key.lower()
            if value is None or (key not in _ALLOWED_HTML_ATTRS and not key.startswith("aria-")):
                continue
            if key.startswith("on") or key == "style":
                continue
            if key in {"href", "src", "poster"}:
                value = _safe_http_url(value)
                if value is None:
                    continue
            if key == "target" and value not in {"_blank", "_self"}:
                continue
            safe_attrs.append(f' {key}="{html.escape(value, quote=True)}"')
        if tag == "a" and any(attr.startswith(' target="_blank"') for attr in safe_attrs):
            safe_attrs.append(' rel="noopener noreferrer"')
        self.parts.append("<" + tag + "".join(safe_attrs) + ">")
        if tag not in _VOID_HTML_TAGS:
            self.open_tags.append(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self.drop_depth:
            if tag in _DROP_CONTENT_TAGS:
                self.drop_depth -= 1
            return
        if tag in self.open_tags:
            while self.open_tags:
                current = self.open_tags.pop()
                self.parts.append(f"</{current}>")
                if current == tag:
                    break

    def handle_data(self, data: str) -> None:
        if not self.drop_depth:
            self.parts.append(html.escape(data))

    def result(self) -> str:
        while self.open_tags:
            self.parts.append(f"</{self.open_tags.pop()}>")
        return "".join(self.parts)


def _sanitize_html_fragment(source: str) -> str:
    parser = _SafeHTML()
    try:
        parser.feed(source)
        parser.close()
        return parser.result()
    except Exception:
        return html.escape(source)


def _render_html_document(manifest: dict[str, Any]) -> str:
    site = manifest.get("site", {})
    site_url = site.get("url", "") if isinstance(site, dict) else ""
    title = str(site.get("title") or urllib.parse.urlsplit(str(site_url)).hostname or "Untitled site")
    safe_title = html.escape(title, quote=True)
    interactions = manifest.get("interactions", {})
    links = interactions.get("links", []) if isinstance(interactions, dict) else []
    buttons = (
        interactions.get("buttons", []) if isinstance(interactions, dict) else []
    )
    ext_styles = manifest.get("external_stylesheets", [])
    structure = manifest.get("structure", {})
    observed_sections = structure.get("sections", []) if isinstance(structure, dict) else []
    section_cards = "\n".join(
        f'<article class="card feature-card"><h3>{html.escape(str(section.get("name") or section.get("id") or "Observed section"))}</h3></article>'
        for section in observed_sections[:12]
        if isinstance(section, dict)
    )
    if not section_cards:
        section_cards = '<p>Section details were not captured from the source page.</p>'

    # Check for live captured HTML
    source_html = manifest.get("source_html") or ""
    if source_html and len(source_html) > 100:
        # Wrap or clean live DOM
        body_match = re.search(r"<body[^>]*>(.*?)</body>", source_html, re.DOTALL | re.IGNORECASE)
        body_content = body_match.group(1) if body_match else source_html

        head_styles = "\n  ".join(
            f'<link rel="stylesheet" href="{html.escape(safe_url, quote=True)}">'
            for href in ext_styles
            if (safe_url := _safe_http_url(href))
        )

        return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{safe_title}</title>
  {head_styles}
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  {_sanitize_html_fragment(body_content)}
</body>
</html>"""

    # Generate a clearly labeled fallback from captured metadata only
    nav_links = ""
    seen_texts: set[str] = set()
    for link in links[:6]:
        txt = str(link.get("text", "")).strip() if isinstance(link, dict) else ""
        href = _safe_http_url(link.get("href", "#")) if isinstance(link, dict) else "#"
        if txt and href and txt not in seen_texts:
            seen_texts.add(txt)
            nav_links += f'<a href="{html.escape(href, quote=True)}" class="nav-link">{html.escape(txt)}</a>\n        '

    primary_btn = html.escape(str(buttons[0].get("text", "Get started"))) if buttons and isinstance(buttons[0], dict) else "Get started"
    secondary_btn = html.escape(str(buttons[1].get("text", "Learn more"))) if len(buttons) > 1 and isinstance(buttons[1], dict) else "Learn more"

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{safe_title}</title>
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap">
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <header class="site-header">
    <div class="container header-container">
      <div class="logo">
        <span class="logo-badge">✦</span>
        <span class="logo-text">{safe_title}</span>
      </div>
      <nav class="main-nav">
        {nav_links or '<a href="#features" class="nav-link">ฟีเจอร์</a><a href="#pricing" class="nav-link">ราคา</a><a href="#contact" class="nav-link">ติดต่อเรา</a>'}
      </nav>
      <div class="header-actions">
        <a href="#cta" class="btn btn-primary">{primary_btn}</a>
      </div>
    </div>
  </header>

  <main>
    <section class="hero-section">
      <div class="container hero-container">
        <div class="hero-badge">Explore the site</div>
        <h1 class="hero-title">{safe_title}</h1>
        <p class="hero-subtitle">A locally generated preview based on the available source evidence.</p>
        <div class="hero-actions">
          <a href="#cta" class="btn btn-primary btn-lg">{primary_btn}</a>
          <a href="#features" class="btn btn-secondary btn-lg">{secondary_btn}</a>
        </div>
      </div>
    </section>

    <section id="structure" class="features-section">
      <div class="container">
        <h2 class="section-title">Observed page structure</h2>
        <div class="features-grid">
          {section_cards}
        </div>
      </div>
    </section>

    <section id="cta" class="cta-section">
      <div class="container cta-container">
        <h2>Explore {safe_title}</h2>
        <p>This preview is generated from the evidence collected so far.</p>
        <div class="cta-actions">
          <button class="btn btn-light btn-lg">{primary_btn}</button>
        </div>
      </div>
    </section>
  </main>

  <footer class="site-footer">
    <div class="container footer-container">
      <p>&copy; 2026 {safe_title}. All rights reserved</p>
      <div class="footer-links">
        <a href="#">Privacy</a>
        <a href="#">Terms</a>
      </div>
    </div>
  </footer>
</body>
</html>"""


def _safe_css_token(value: object, fallback: str) -> str:
    if not isinstance(value, str) or any(ch in value for ch in "{};<>\\\n\\r"):
        return fallback
    lowered = value.lower()
    if "url(" in lowered or "expression" in lowered or "@import" in lowered or "javascript:" in lowered:
        return fallback
    return value


def _sanitize_css(source: str) -> str:
    # Captured styles are untrusted; drop import rules and legacy executable CSS.
    source = re.sub(r"@import\s+[^;]+;?", "", source, flags=re.IGNORECASE)
    source = re.sub(r"expression\s*\([^)]*\)", "", source, flags=re.IGNORECASE)
    source = re.sub(r"url\s*\(\s*(['\"]?)\s*javascript:[^)]*\)", "none", source, flags=re.IGNORECASE)
    return source


def _render_css_document(manifest: dict[str, Any]) -> str:
    theme = manifest.get("theme", {})
    font = _safe_css_token(theme.get("fontFamily"), "system-ui, sans-serif")
    color = _safe_css_token(theme.get("color"), "#0f172a")
    bg = _safe_css_token(theme.get("backgroundColor"), "#ffffff")
    source_css = _sanitize_css(str(manifest.get("source_css") or ""))

    base_css = f"""/* Cloned Site Base Stylesheet */
:root {{
  --font-family: {font};
  --color-text: {color};
  --color-bg: {bg};
  --color-primary: #2563eb;
  --color-primary-hover: #1d4ed8;
  --color-secondary: #f1f5f9;
  --color-border: #e2e8f0;
}}

* {{
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}}

body {{
  font-family: var(--font-family);
  color: var(--color-text);
  background-color: var(--color-bg);
  line-height: 1.6;
}}

.container {{
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 1.5rem;
}}

.site-header {{
  border-bottom: 1px solid var(--color-border);
  padding: 1.25rem 0;
  background: #ffffff;
  position: sticky;
  top: 0;
  z-index: 50;
}}

.header-container {{
  display: flex;
  align-items: center;
  justify-content: space-between;
}}

.logo {{
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: 700;
  font-size: 1.25rem;
}}

.logo-badge {{
  color: var(--color-primary);
}}

.main-nav {{
  display: flex;
  gap: 1.5rem;
}}

.nav-link {{
  color: #64748b;
  text-decoration: none;
  font-weight: 500;
  transition: color 0.2s;
}}

.nav-link:hover {{
  color: var(--color-primary);
}}

.btn {{
  display: inline-block;
  padding: 0.625rem 1.25rem;
  font-size: 0.95rem;
  font-weight: 600;
  border-radius: 0.5rem;
  text-decoration: none;
  cursor: pointer;
  border: none;
  transition: all 0.2s;
}}

.btn-primary {{
  background-color: var(--color-primary);
  color: #ffffff;
}}

.btn-primary:hover {{
  background-color: var(--color-primary-hover);
}}

.btn-secondary {{
  background-color: var(--color-secondary);
  color: var(--color-text);
}}

.btn-light {{
  background-color: #ffffff;
  color: var(--color-primary);
}}

.btn-lg {{
  padding: 0.875rem 1.75rem;
  font-size: 1.1rem;
}}

.hero-section {{
  padding: 5rem 0;
  text-align: center;
  background: linear-gradient(180deg, #f8fafc 0%, #ffffff 100%);
}}

.hero-badge {{
  display: inline-block;
  padding: 0.25rem 0.75rem;
  background: #dbeafe;
  color: #1e40af;
  border-radius: 9999px;
  font-size: 0.875rem;
  font-weight: 600;
  margin-bottom: 1.5rem;
}}

.hero-title {{
  font-size: 2.75rem;
  font-weight: 800;
  letter-spacing: -0.025em;
  line-height: 1.25;
  margin-bottom: 1.25rem;
}}

.hero-subtitle {{
  font-size: 1.25rem;
  color: #64748b;
  max-width: 720px;
  margin: 0 auto 2rem;
}}

.hero-actions {{
  display: flex;
  justify-content: center;
  gap: 1rem;
}}

.features-section {{
  padding: 5rem 0;
}}

.section-title {{
  text-align: center;
  font-size: 2rem;
  font-weight: 700;
  margin-bottom: 3rem;
}}

.features-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 2rem;
}}

.card {{
  padding: 2rem;
  border: 1px solid var(--color-border);
  border-radius: 0.75rem;
  background: #ffffff;
  box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05);
}}

.card-icon {{
  font-size: 2rem;
  margin-bottom: 1rem;
}}

.card h3 {{
  font-size: 1.25rem;
  margin-bottom: 0.75rem;
}}

.card p {{
  color: #64748b;
}}

.cta-section {{
  padding: 4rem 0;
  background: var(--color-primary);
  color: #ffffff;
  text-align: center;
}}

.cta-container h2 {{
  font-size: 2.25rem;
  font-weight: 700;
  margin-bottom: 1rem;
}}

.cta-container p {{
  font-size: 1.15rem;
  opacity: 0.9;
  margin-bottom: 2rem;
}}

.site-footer {{
  padding: 2.5rem 0;
  border-top: 1px solid var(--color-border);
  font-size: 0.9rem;
  color: #94a3b8;
}}

.footer-container {{
  display: flex;
  justify-content: space-between;
  align-items: center;
}}

.footer-links {{
  display: flex;
  gap: 1.5rem;
}}

.footer-links a {{
  color: inherit;
  text-decoration: none;
}}
"""
    if source_css:
        return f"{base_css}\n\n/* Inlined Source Styles */\n{source_css}"
    return base_css


def generate_project(
    sandbox_name: str,
    output_dir: str = "clones",
    manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    name = validate_name(sandbox_name)
    output_dir = _safe_relative_project_path(output_dir, field="output_dir")
    manifest = manifest or {}
    site = manifest.get("site", {})
    source_url = site.get("url") if isinstance(site, dict) else None
    parsed_source_url = urllib.parse.urlsplit(source_url) if isinstance(source_url, str) else None
    if parsed_source_url is None or parsed_source_url.scheme.lower() not in {"http", "https"} or not parsed_source_url.hostname:
        raise ValueError("Manifest must include a valid HTTP(S) source URL before project generation.")

    manifest_json = json.dumps(manifest, indent=2, default=str)
    html_code = _render_html_document(manifest)
    css_code = _render_css_document(manifest)
    package_json = json.dumps(
        {
            "name": "cloned-site",
            "version": "1.0.0",
            "private": True,
            "scripts": {
                "build": "test -f index.html && test -f styles.css && echo 'Build verification passed.'",
                "serve": "node /tmp/serve_4173.js",
            },
        },
        indent=2,
    )
    readme_md = f"""# Cloned Website

Generated from: {manifest.get('site', {}).get('url', 'N/A')}
Title: {manifest.get('site', {}).get('title', 'Untitled site')}

## Artifacts
- `index.html`: Rendered semantic markup
- `styles.css`: Stylesheet and responsive layout rules
- `clone-manifest.json`: Full canonical manifest specification
- `package.json`: Project scripts
"""

    files = {
        "clone-manifest.json": manifest_json,
        "index.html": html_code,
        "styles.css": css_code,
        "package.json": package_json,
        "README.md": readme_md,
    }

    # Use argv-only file operations and keep all artifacts under one approved root.
    remote_dir = f"{_PROJECT_ROOT}/{output_dir}"
    mkdir_result = execute_sandbox_argv(name, ["mkdir", "-p", remote_dir], timeout_seconds=30)
    if int(mkdir_result.get("return_code", 1)) != 0:
        raise RuntimeError(f"Could not create clone output directory: {mkdir_result.get('stderr', '')}")
    resolved = execute_sandbox_argv(name, ["realpath", "-e", remote_dir], timeout_seconds=10)
    if int(resolved.get("return_code", 1)) != 0 or str(resolved.get("stdout", "")).strip() != remote_dir:
        raise ValueError("Clone output directory resolves outside its approved path or contains a symlink.")

    formatting_results: dict[str, str] = {}
    for fname, content in list(files.items()):
        formatted, status = format_text_in_sandbox(name, f"{output_dir}/{fname}", content)
        files[fname] = formatted
        if status is not None:
            formatting_results[fname] = status

    for fname, content in files.items():
        written = execute_sandbox_argv(
            name, ["tee", f"{remote_dir}/{fname}"],
            stdin=content.encode("utf-8"), timeout_seconds=30,
        )
        if int(written.get("return_code", 1)) != 0:
            raise RuntimeError(f"Could not write clone artifact {fname}: {written.get('stderr', '')}")

    return {
        "output_dir": output_dir,
        "manifest": f"{output_dir}/clone-manifest.json",
        "entrypoint": f"{output_dir}/index.html",
        "files_generated": list(files.keys()),
        "formatting": formatting_results,
        "html_size_bytes": len(files["index.html"].encode("utf-8")),
    }


def build_project(
    sandbox_name: str, project_dir: str = "clones"
) -> dict[str, Any]:
    name = validate_name(sandbox_name)
    project_dir = _safe_relative_project_path(project_dir)
    remote_dir = f"{_PROJECT_ROOT}/{project_dir}"
    script = r"""
set -eu
DIR=$(realpath -e -- "$1")
case "$DIR" in /workspace/project/*) ;; *) echo "Project path escapes the approved root" >&2; exit 2 ;; esac
[ -f "$DIR/index.html" ] || { echo "Missing index.html" >&2; exit 1; }
[ -f "$DIR/clone-manifest.json" ] || { echo "Missing clone-manifest.json" >&2; exit 1; }
[ -f "$DIR/styles.css" ] || { echo "Missing styles.css" >&2; exit 1; }
HTML_SIZE=$(wc -c < "$DIR/index.html")
[ "$HTML_SIZE" -ge 50 ] || { echo "Validation failed: index.html is too small ($HTML_SIZE bytes)" >&2; exit 1; }
if [ -f "$DIR/package.json" ] && command -v npm >/dev/null 2>&1; then
  (cd "$DIR" && npm run build)
fi
printf 'Build check passed: index.html (%s bytes), styles.css, and clone-manifest.json verified.\n' "$HTML_SIZE"
"""
    result = execute_sandbox_argv(name, ["sh", "-c", script, "sh", remote_dir], timeout_seconds=120)
    ret_code = int(result.get("return_code", 1))
    stdout = str(result.get("stdout", ""))
    stderr = str(result.get("stderr", ""))
    success = ret_code == 0
    return {
        "project_dir": project_dir,
        "return_code": ret_code,
        "status": "success" if success else "failed",
        "stdout": stdout,
        "stderr": stderr,
        "artifacts": {key: success for key in ("index.html", "clone-manifest.json", "styles.css")},
    }


def serve_project(
    sandbox_name: str, project_dir: str = "clones", port: int = 4173
) -> dict[str, Any]:
    name = validate_name(sandbox_name)
    project_dir = _safe_relative_project_path(project_dir)
    if isinstance(port, bool) or not isinstance(port, int) or not 1024 <= port <= 65535:
        raise ValueError("port must be an integer between 1024 and 65535")
    remote_dir = f"{_PROJECT_ROOT}/{project_dir}"
    server_path = f"/tmp/serve_{port}.js"
    pid_path = f"/tmp/serve_{port}.pid"
    log_path = f"/tmp/serve_{port}.log"
    execute_sandbox_argv(name, ["sh", "-c", 'pkill -f "$1" 2>/dev/null || true', "sh", f"node {server_path}"], timeout_seconds=5)
    root_literal = json.dumps(remote_dir)
    pid_literal = json.dumps(pid_path)
    server_js = f"""
const http = require('http');
const fs = require('fs');
const path = require('path');
const allowedRoot = fs.realpathSync('/workspace/project');
const root = fs.realpathSync({root_literal});
const rootRel = path.relative(allowedRoot, root);
if (rootRel === '..' || rootRel.startsWith('..' + path.sep) || path.isAbsolute(rootRel) || root === allowedRoot) process.exit(2);
const port = {port};
let originUrl = '';
try {{
  const originFile = path.join(root, '.origin');
  if (fs.existsSync(originFile)) originUrl = fs.readFileSync(originFile, 'utf8').trim().replace(/\\/+$/, '');
}} catch (_) {{}}
const mime = {{'.html':'text/html; charset=utf-8','.css':'text/css; charset=utf-8','.js':'application/javascript; charset=utf-8','.json':'application/json; charset=utf-8','.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.webp':'image/webp','.gif':'image/gif','.svg':'image/svg+xml','.ico':'image/x-icon','.woff2':'font/woff2','.mp4':'video/mp4'}};
const server = http.createServer((req, res) => {{
  let decoded;
  try {{ decoded = decodeURIComponent((req.url || '/').split('?')[0]); }} catch (_) {{ res.writeHead(400); return res.end('Bad Request'); }}
  if (decoded.includes(String.fromCharCode(92)) || decoded.includes(String.fromCharCode(0))) {{ res.writeHead(400); return res.end('Bad Request'); }}
  const candidate = path.resolve(root, '.' + (decoded.startsWith('/') ? decoded : '/' + decoded));
  const rel = path.relative(root, candidate);
  if (rel === '..' || rel.startsWith('..' + path.sep) || path.isAbsolute(rel)) {{ res.writeHead(403); return res.end('Forbidden'); }}
  let target = candidate;
  try {{
    if (fs.existsSync(target) && fs.statSync(target).isDirectory()) target = path.join(target, 'index.html');
    const actual = fs.realpathSync(target);
    const actualRel = path.relative(root, actual);
    if (actualRel === '..' || actualRel.startsWith('..' + path.sep) || path.isAbsolute(actualRel) || !fs.statSync(actual).isFile()) {{ res.writeHead(403); return res.end('Forbidden'); }}
    const ext = path.extname(actual).toLowerCase();
    const contentType = mime[ext] || (actual.includes(path.sep + 'api' + path.sep) ? 'application/json; charset=utf-8' : 'application/octet-stream');
    res.writeHead(200, {{'Content-Type': contentType, 'X-Content-Type-Options':'nosniff', 'Content-Security-Policy': "default-src 'self'; script-src 'self' 'unsafe-inline'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; img-src 'self' https: data:; media-src 'self' https: blob: data:; style-src 'self' https: 'unsafe-inline'; font-src 'self' https: data:; connect-src 'self' https:;"}});
    fs.createReadStream(actual).pipe(res);
  }} catch (_) {{
    if (originUrl && (decoded.startsWith('/images/') || decoded.startsWith('/videos/') || decoded.startsWith('/fonts/') || /\\.(svg|png|jpe?g|webp|gif|mp4|woff2?)$/i.test(decoded))) {{
      res.writeHead(302, {{'Location': originUrl + (decoded.startsWith('/') ? decoded : '/' + decoded)}});
      return res.end();
    }}
    res.writeHead(404, {{'Content-Type':'text/plain; charset=utf-8','X-Content-Type-Options':'nosniff'}}); res.end('Not Found');
  }}
}});
server.on('error', err => {{ console.error('Server error:', err.message); process.exit(1); }});
server.listen(port, '0.0.0.0', () => {{ fs.writeFileSync({pid_literal}, String(process.pid), {{mode: 0o600}}); }});
"""
    server_js, server_formatting = format_text_in_sandbox(
        name, f"{project_dir}/serve_4173.js", server_js
    )
    execute_sandbox_argv(name, ["tee", server_path], stdin=server_js.encode("utf-8"), timeout_seconds=10)
    execute_sandbox_argv(name, ["sh", "-c", 'nohup node "$1" </dev/null >"$2" 2>&1 &', "sh", server_path, log_path], timeout_seconds=5)
    healthy = False
    pid = ""
    for _ in range(12):
        time.sleep(0.3)
        check = execute_sandbox_argv(name, ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", f"http://127.0.0.1:{port}/"], timeout_seconds=3)
        if str(check.get("stdout", "")).strip() == "200":
            healthy = True
            pid_res = execute_sandbox_argv(name, ["cat", pid_path], timeout_seconds=3)
            pid = str(pid_res.get("stdout", "")).strip()
            break
    return {
        "project_dir": project_dir,
        "port": port,
        "pid": pid,
        "url": f"http://127.0.0.1:{port}",
        "healthy": healthy,
        "formatting": server_formatting,
    }


def verify_clone(**evidence: Any) -> dict[str, Any]:
    structure = evidence.get("analyze", {})
    pages = structure.get("pages", []) if isinstance(structure, dict) else []
    build = evidence.get("build", {})
    serve = evidence.get("serve", {})
    mismatches: list[str] = []
    checks: dict[str, str] = {"structural": "not_evaluated", "assets": "not_evaluated", "visual": "not_evaluated", "behavior": "not_evaluated"}

    if not isinstance(structure, dict) or not pages:
        mismatches.append("Structure analysis returned no pages")
    else:
        checks["structural"] = "pass"

    if isinstance(build, dict) and build:
        if build.get("return_code") == 0 and build.get("status") == "success":
            artifacts = build.get("artifacts", {})
            if isinstance(artifacts, dict) and all(artifacts.get(k) is True for k in ("index.html", "clone-manifest.json", "styles.css")):
                checks["assets"] = "pass"
            else:
                checks["assets"] = "fail"
                mismatches.append("Build output did not confirm all required artifacts")
        else:
            checks["assets"] = "fail"
            mismatches.append(f"Build step failed with return_code {build.get('return_code')}")

    if isinstance(serve, dict) and serve:
        if serve.get("healthy") is True:
            checks["behavior"] = "partial"
        else:
            checks["behavior"] = "fail"
            mismatches.append(f"Preview server at {serve.get('url', 'local port')} is unreachable")

    all_required_pass = all(checks[key] == "pass" for key in ("structural", "assets", "visual", "behavior"))
    return {
        "status": "passed" if all_required_pass and not mismatches else "incomplete" if not mismatches else "failed",
        "score": None,
        "structural": {"status": checks["structural"], "pages_verified": len(pages) if isinstance(pages, list) else 0},
        "assets": {"status": checks["assets"]},
        "visual": {"status": "not_evaluated", "reason": "No reference-versus-preview screenshot comparison was performed."},
        "behavior": {"status": checks["behavior"], "reason": "Server health is not a substitute for interaction replay."},
        "mismatches": mismatches,
        "evidence_keys": sorted(evidence),
    }


def repair_clone(**evidence: Any) -> dict[str, Any]:
    verification = evidence.get("verification", {})
    mismatches = verification.get("mismatches", []) if isinstance(verification, dict) else []
    if not isinstance(mismatches, list):
        mismatches = []
    if not mismatches:
        return {
            "status": "no_actionable_repairs",
            "reason": "No reported mismatches were supplied. No files were changed and no repair is claimed.",
            "repairs_applied": 0,
            "evidence_keys": sorted(evidence),
        }
    return {
        "status": "manual_action_required",
        "reason": "Automated patching is not implemented for these mismatches; no files were changed.",
        "repairs_applied": 0,
        "actionable_mismatches": [str(item) for item in mismatches],
        "evidence_keys": sorted(evidence),
    }


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
    return {
        "run_id": result.run_id,
        "workflow": result.workflow,
        "status": result.status,
        "steps": [step.__dict__ for step in result.steps],
        "output": result.output,
    }
