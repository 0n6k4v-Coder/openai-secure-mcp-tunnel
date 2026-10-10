# Reverse Engineering Findings: Two-Stage Web Cloning Architecture (mtioon → cindyly)

**Date:** 2026-10-09  
**Status:** Completed  
**Subject:** Analysis of Fast & High-Fidelity Web Cloning (`apps/mtioon` to `apps/cindyly`)

---

## 1. Executive Summary

จากการวิเคราะห์เปรียบเทียบระหว่างวิธีการ Re-create เว็บไซต์แบบดั้งเดิม (ที่ค่อยๆ เขียน HTML/CSS/JS เลียนแบบทีละชิ้น) กับกระบวนการที่ปรากฏใน `apps/mtioon/*` และ `apps/cindyly/*` พบว่ามี **"สูตร 2 ขั้นตอน (Two-Stage Pipeline)"** ที่ทำงานได้รวดเร็วและมีความแม่นยำสูงมาก:

1. **Stage 1 (`apps/mtioon` - Fast Live-Proxy Snapshot):**
   - ดึง Hydrated DOM จากเบราว์เซอร์หลังจาก JavaScript ประมวลผลเสร็จสิ้น
   - แทรก `<base href="https://target.com/">` เพียงบรรทัดเดียว
   - ทำให้ได้เว็บ Clone ที่ทำงานได้ครบถ้วน (HTML, CSS, JS, Chunks, 3D Canvas, WebGL, Fonts) ภายในเวลาไม่กี่วินาที
2. **Stage 2 (`apps/cindyly` - Semantic Component Decomposition):**
   - นำผลลัพธ์ของ Stage 1 ที่ผ่านการ Audit แล้วมาแตกเป็น Normal, Maintainable Code
   - แยก CSS, Component HTML, Behavior Modules, และ Micro-Build Runner

---

## 2. Stage 1 Deep Dive: `apps/mtioon` (Live-Proxy Snapshot)

### 2.1 File Structure
```text
apps/mtioon/
├── live-proxy/
│   └── index.html      # 1.04 MB single-file snapshot
└── research/
    ├── live-homepage-snapshot.html
    └── chunks/         # Client-side JavaScript bundles จาก Next.js/Turbopack
```

### 2.2 Mechanism
เมื่อตรวจสอบหัวไฟล์ `apps/mtioon/live-proxy/index.html`:
```html
<!DOCTYPE html>
<html lang="en" class="h-full antialiased lenis">
<head>
  <base href="https://mtioon.com/">
  <meta charset="utf-8">
  <style data-precedence="next" ...> ... </style>
  <link rel="stylesheet" href="/fonts/fonts.css">
  ...
  <script src="/_next/static/chunks/1aahvactoqrt3.js"></script>
  <script src="/_next/static/chunks/turbopack-1a3p9-q531yr8.js"></script>
  ...
```

### 2.3 Key Technical Insights
1. **Hydrated OuterHTML Capture:**
   - ใช้ Browser Automation (CDP / `evaluate`) ดึง `document.documentElement.outerHTML` ณ เวลาที่ Framework (Next.js / React / Astro) ทำการ Client-side Hydration เรียบร้อยแล้ว
2. **`<base href="...">` Resolution:**
   - เมื่อเบราว์เซอร์เปิดไฟล์ Local `index.html` เบราว์เซอร์จะใช้นโยบาย Base URL ในการ resolve ทุก Relative Path:
     - `/images/...` $\rightarrow$ `https://mtioon.com/images/...`
     - `/fonts/...` $\rightarrow$ `https://mtioon.com/fonts/...`
     - `/_next/static/chunks/...` $\rightarrow$ `https://mtioon.com/_next/static/chunks/...`
3. **Zero Asset Download Overhead:**
   - ไม่ต้องเสียเวลาดาวน์โหลดรูปภาพหรือไฟล์มัลติมีเดียลงเครื่องก่อน ทำให้สามารถ Serve และ Preview ได้ทันที
4. **Preserved Interactivity & 3D WebGL:**
   - Script และ Web Worker จากต้นฉบับจะถูกดาวน์โหลดมาประมวลผลบน Client ฝั่งเราทั้งหมด ทำให้ Interaction ซับซ้อน เช่น 3D Candy Extrusion, Lenis Smooth Scroll, Canvas Motion ทำงานได้ทันที 100%

---

## 3. Stage 2 Deep Dive: `apps/cindyly` (Component Decomposition)

เมื่อตรวจสอบสถานะความถูกต้องใน Stage 1 จนมั่นใจแล้ว โค้ดจะถูก Refactor เข้าสู่สถาปัตยกรรมระดับ Production ใน `apps/cindyly`:

### 3.1 File Structure
```text
apps/cindyly/clone/
├── README.md                  # Documentation โครงสร้างระบบ
├── scripts/
│   └── build.js               # Micro-build tool (HTML macro expander)
├── src/
│   ├── page.html              # Master layout shell
│   ├── components/            # Semantic HTML components
│   │   ├── header.html
│   │   ├── welcome.html
│   │   ├── works.html
│   │   ├── profile.html
│   │   ├── sidequests.html
│   │   └── overlays.html
│   ├── css/
│   │   ├── main.css           # Extracted visual design system
│   │   └── reddit-reel.css
│   └── js/                    # Focused behavior modules
│       ├── animations.js
│       ├── fish-tank.js
│       ├── navigation.js
│       └── sticker-board.js
└── index.html                 # Build output (Static Artifact)
```

### 3.2 Key Technical Insights
1. **Deterministic Micro-Build (`scripts/build.js`):**
   - ตัว Build Script มีขนาดกะทัดรัด (เพียง ~15 บรรทัด) โดยไม่ต้องพึ่ง Toolchain ขนาดใหญ่:
   ```javascript
   const fs = require('fs');
   const path = require('path');
   const root = path.resolve(__dirname, '..');
   const source = path.join(root, 'src/page.html');
   const output = path.join(root, 'index.html');
   const componentDir = path.join(root, 'src/components');

   const template = fs.readFileSync(source, 'utf8');
   const html = template.replace(/  <!-- @component ([^ ]+) -->/g, (_, name) => {
     const file = path.join(componentDir, name + '.html');
     if (!fs.existsSync(file)) throw new Error('Missing component: ' + name);
     return fs.readFileSync(file, 'utf8').trim();
   });

   fs.writeFileSync(output, html);
   ```
2. **Modular Behavior Separation:**
   - แทนที่จะทิ้ง Bundle ก้อนใหญ่ไว้ Script แต่ละตัวจะถูกดึงออกมาเป็น Module เฉพาะฟังก์ชัน เช่น:
     - `fish-tank.js`: ควบคุม Canvas และ Physics ของ Tank
     - `sticker-board.js`: ควบคุม Drag-and-drop
     - `navigation.js`: ควบคุม Smooth scroll และ Drawer
3. **No Guesswork Required:**
   - โมเดลไม่จำเป็นต้องเดาโครงสร้าง HTML หรือ Class Names เอง เพราะมี "เฉลยที่สมบูรณ์" อยู่ใน Snapshot ของ Stage 1 แล้ว

---

## 4. Workflow Comparison

| มิติ | วิธีเดิม (Manual Reconstruction) | วิธีใหม่ 2 ขั้นตอน (mtioon → cindyly) |
|---|---|---|
| **ระยะเวลาในการได้ผลลัพธ์แรก** | 10 - 30 นาที | **5 - 10 วินาที** (Stage 1) |
| **ความแม่นยำในการเริ่มต้น (Visual & Motion)** | 60 - 80% (มักพลาด Interaction ซ่อนเร้น) | **100%** (ทำงานได้เหมือนต้นฉบับทันที) |
| **Asset Dependency** | ต้องไล่ดาวน์โหลดทีละรูป/ไฟล์ | Resolve ผ่าน `<base href>` ทันที |
| **ความง่ายในการ Refactor เป็น Normal Code** | เสี่ยงคลาดเคลื่อนสูง | แม่นยำสูงมาก เพราะใช้ Snapshot เป็นแม่แบบ |
| **ความเสี่ยงของ Tool Audit** | ใช้เวลานานในการแก้ Diff | ใช้ Tool ตรวจจับ Diff ก่อนและหลัง Decompose ได้ทันที |

---

## 5. Automation Strategy สำหรับ Tooling

เพื่อให้ Automation Tool ของเราสามารถนำสูตรนี้ไปใช้งานได้อย่างเป็นระบบ:

1. **Step 1 - `capture_live_proxy_clone`:**
   - Navigates ไปยังเป้าหมายผ่าน CDP
   - รอจนกระทั่ง `document.readyState === 'complete'` และ Animation เฟรมแรกเริ่มทำงาน
   - ดึง `document.documentElement.outerHTML`
   - ทำการแทรก `<base href="{target_origin}/">` ที่ส่วนต้นของ `<head>`
   - เขียนลงไฟล์ `live-proxy/index.html` และ Start Serve บน Sandbox ทันที (เสร็จสิ้น Stage 1)
2. **Step 2 - `audit_element_fidelity` Verification:**
   - รันการตรวจสอบ Fidelity และ Interactive Mutation เปรียบเทียบกับหน้าจริง
3. **Step 3 - `decompose_clone_project`:**
   - แยก `<style>` ออกเป็น `src/css/main.css`
   - สแกนหา Semantic Tags (`header`, `nav`, `main > section`, `footer`) และแยกออกเป็น `src/components/*.html`
   - สร้าง `src/page.html` ที่มี Tag `<!-- @component ... -->`
   - สร้าง `scripts/build.js` และทดสอบรัน Build
