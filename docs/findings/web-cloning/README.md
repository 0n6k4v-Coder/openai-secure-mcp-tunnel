# Engineering Findings: Web Cloning & Rehydration Analysis

เอกสารรวบรวมผลการ Reverse Engineering, การแก้ปัญหาทางเทคนิค (Root Cause Analysis), และแนวทางการทำ High-Fidelity Web Cloning

---

## สารบัญเอกสาร (Table of Contents)

1. [Two-Stage Web Cloning Architecture (`mtioon` → `cindyly`)](file:///home/kawee/Code/project/openai-secure-mcp-tunnel/docs/findings/web-cloning/two-stage-cloning-architecture.md)
   - สรุปสถาปัตยกรรมการโคลนแบบ 2 ขั้นตอน (Stage 1: Fast Live-Proxy Snapshot สู่ Stage 2: Semantic Component Decomposition)
   - เทคนิค Base URL Resolution และการลด Overhead การดาวน์โหลด Asset ให้เหลือ 0 วินาที
   - การจัดการ Dynamic Modules และ CORS

2. [Hidden Package / Pricing Section Resolution](file:///home/kawee/Code/project/openai-secure-mcp-tunnel/docs/findings/web-cloning/hidden-package-section-resolution.md)
   - การแก้ปัญหา Section Package / Pricing (`#pricing`) ไม่แสดงผล (`opacity: 0` / หายไปจากหน้าจอ)
   - ผลกระทบของ Intersection Observer และ Scroll-Triggered Animation ในสภาวะ Snapshot
   - การ Reconciliation สถานะ CSS ระหว่าง Live Site และ Local Snapshot

3. [Package Cards Loading Failure & Cookie Consent Banner Interaction](file:///home/kawee/Code/project/openai-secure-mcp-tunnel/docs/findings/web-cloning/package-cards-and-cookie-banner-resolution.md)
   - การแก้ปัญหาข้อความสีแดง "ไม่สามารถโหลดข้อมูลแพ็กเกจได้" (เกิดจาก Network dependency `/api/plans` ที่ติด CORS/404)
   - การแก้ปัญหาแถบ Cookie Consent Bar ไม่ตอบสนองต่อการคลิกปิด (เกิดจาก DOM duplication & event decoupling ใน snapshot)
   - การ Mock Endpoint ร่วมกับ Freeze Rendered DOM และ Native Event Binding

4. [Hero Section Animation & Initial Effects Rehydration](file:///home/kawee/Code/project/openai-secure-mcp-tunnel/docs/findings/web-cloning/hero-animation-hydration-findings.md)
   - สาเหตุที่ Hero Floating Objects (`Float`) หยุดนิ่ง และ Initial Effects (`FadeUp`) ไม่ Transition
   - พฤติกรรมของ Astro Islands ในโหมด Post-Hydration Snapshot (`removeAttribute("ssr")`)
   - Guard Check ของ React Hydrator และการสร้าง **Snapshot Hydration Shim** เพื่อ Re-trigger Animation Loop ได้ 100%

5. [Universal Live-Proxy Snapshot Tool Implementation](file:///home/kawee/Code/project/openai-secure-mcp-tunnel/docs/findings/web-cloning/universal-live-proxy-snapshot-tool.md)
   - เอกสารสถาปัตยกรรมและการสร้าง Tool MCP `create_live_proxy_snapshot` ตัวจริง
   - การรวม 4 ขั้นตอน (Pre-Capture Auto-Scroll, Chunk Localization, Auto API Mocking, และ Universal Runtime Shim Injection) ให้ทำงานอัตโนมัติภายในคำสั่งเดียว

6. [Root Cause Analysis: Why Tool Allowed Get-Started & Package Bugs](file:///home/kawee/Code/project/openai-secure-mcp-tunnel/docs/findings/web-cloning/why-live-proxy-tool-allowed-bugs-rca.md)
   - การวิเคราะห์เชิงลึกว่าทำไม Universal Tool จึงปล่อย Bug ในส่วน "ขั้นตอนเริ่มใช้กัน" และ "Package"
   - ช่องว่างระหว่าง Static HTML Rewriting กับ Dynamic Client-side JavaScript Runtime
   - การแก้ปัญหาที่ระดับโครงสร้างของ Tool เพื่อให้ระบบพรีวิวและโคลนมีความสมบูรณ์ 100%

7. [Balanced Code Formatting in Component Decomposition](file:///home/kawee/Code/project/openai-secure-mcp-tunnel/docs/findings/web-cloning/decomposition-balanced-formatting-architecture.md)
   - การแก้ปัญหา Horizontal Formatting (Single-line over-compression) ที่เกิดจาก Blink DOM Serialization
   - กับดัก Over-split vs Over-compress ในยุค Tailwind CSS และการสร้าง Balanced Formatting Profile
   - โครงสร้างสถาปัตยกรรมถาวร 4 เสาหลัก: AST-Aware Slicing, Native Formatting Gateway, Balanced Config, และ DOM Invariant Guard

8. [Human-AI Cloning Loop](file:///home/kawee/Code/project/openai-secure-mcp-tunnel/docs/findings/web-cloning/clone-loop.md)
   - ลำดับขั้นตอนการทำงานร่วมกันระหว่าง Human และ AI ในการ Clone และ Decompose เว็บไซต์
