# Troubleshooting & Engineering Findings: Fast Live-Proxy Snapshot Artifacts

**Date:** 2026-10-09  
**Status:** Resolved  
**Subject:** Root Cause Analysis of Hidden Sections (`#pricing`) & Asset/Script Resolution in Fast Live-Proxy Snapshots (`apps/paypers2`)

---

## 1. Problem Statement

ในการทดสอบสร้าง Web Clone ด้วยสูตร **Fast Live-Proxy Snapshot** ในโปรเจกต์ `apps/paypers2/clone`:
- หน้าเว็บโครงสร้างส่วนใหญ่แสดงผลได้รวดเร็วและรูปภาพโหลดครบ
- แต่พบอาการผิดปกติ: **Section Package / ราคาสมาชิก (`#pricing`) ไม่แสดงผล (กลายเป็นพื้นที่ว่างสีขาวขนาดใหญ่)** ทั้งที่ใน DOM มี Elements อยู่ครบถ้วน

---

## 2. Root Cause Analysis (สาเหตุที่แท้จริง)

จากการสืบค้น Computed Styles, Inline Attributes, และกลไกของ Modern Frameworks (Astro + React / Framer Motion):

### 2.1 Scroll-Triggered Entrance Animation Trap
1. **Timing of Capture:**
   - เมื่อ Snapshot ถูกดึงมาจากเบราว์เซอร์ (`document.documentElement.outerHTML`) ในขณะที่หน้าเว็บยังอยู่ที่ตำแหน่งบนสุด (Top of Page / ScrollY = 0)
2. **Pre-Scroll Hidden State:**
   - Framework ใช้ Component เช่น `StaggerGrid` หรือ `RevealOnScroll` (Framer Motion) โดยกำหนด Inline Style สำหรับ Animation Entrance ไว้ว่า:
     ```html
     <div style="opacity: 0; transform: translateY(16px);">
     ```
   - ค่า `opacity: 0` นี้มีจุดประสงค์เพื่อซ่อน Element ไว้ล่วงหน้า และรอให้ผู้ใช้ Scroll หน้าจอลงมาถึงตำแหน่งนั้นก่อน จึงค่อยยิง IntersectionObserver ไป trigger ให้กลายเป็น `opacity: 1`
3. **Static Snapshot Frozen State:**
   - เมื่อนำ OuterHTML ดังกล่าวมาเซฟเป็นไฟล์ Static `index.html` การ์ดแพ็กเกจทั้ง 4 ใบ (ฟรี, ไลท์, โปร, สเกล) จึงถูก **แช่แข็ง (Frozen)** ไว้ที่สถานะเริ่มต้น (`opacity: 0`)
   - ส่งผลให้ Layout มีความสูงจองพื้นที่ไว้เต็ม (~1251px) แต่สายตามองไม่เห็นเนื้อหาใดๆ เลย

### 2.2 Browser Module Import & CORS Restriction on `<base href>`
1. **ES Module Resolution Policy:**
   - เมื่อใส่ `<base href="https://target.com/">` เบราว์เซอร์จะพยายาม Resolve Dynamic ES Module (`import('./module.js')`) ไปที่ Origin ปลายทาง
   - หาก CDN หรือเซิร์ฟเวอร์ปลายทางไม่มี Header `Access-Control-Allow-Origin: *` สำหรับ JavaScript Modules เบราว์เซอร์จะบล็อกการโหลดโมดูลด้วยข้อผิดพลาด CORS ทันที
2. **ทางออกของ Fast Snapshot:**
   - ใช้ Root-Relative Resource Rewriting หรือดาวน์โหลด JS Chunks ที่จำเป็นมาไว้ที่ Local directory (`/_astro/...`) เพื่อให้ Browser โหลดได้โดยไม่ติด CORS Policy

---

## 3. Resolution & Verification

### 3.1 Solution Applied
1. **Unlock Hidden Entrance State:**
   - ทำการ Normalise ค่า Inline Style ของ Elements ที่ติด Entrance State ใน [apps/paypers2/clone/index.html](file:///home/kawee/Code/project/web-app-reverse-engineering-lab/apps/paypers2/clone/index.html):
     - แทนที่ `style="opacity: 0; transform: translateY(16px);"` ด้วย `style="opacity: 1; transform: translateY(0);"`
2. **Attach Interaction Controller:**
   - เชื่อมต่อตัวควบคุม [main.js](file:///home/kawee/Code/project/web-app-reverse-engineering-lab/apps/paypers2/clone/src/js/main.js) เพื่อรองรับการสลับรอบบิล (รายปี / ราย 3 เดือน)

### 3.2 Verification Results via Chrome DevTools Protocol
หลังแก้ไข ทำการตรวจสอบสถานะการแสดงผลของ Card ทั้ง 4 ใบ:

```json
[
  { "index": 0, "title": "ฟรี", "opacity": "1", "display": "block", "width": 290.25, "height": 733.58 },
  { "index": 1, "title": "ไลท์", "opacity": "1", "display": "block", "width": 290.25, "height": 733.58 },
  { "index": 2, "title": "โปร", "opacity": "1", "display": "block", "width": 290.25, "height": 733.58 },
  { "index": 3, "title": "สเกล", "opacity": "1", "display": "block", "width": 290.25, "height": 733.58 }
]
```

- **สถานะ:** การ์ดทั้ง 4 ใบแสดงผลชัดเจน 100%
- **Fidelity Audit (`audit_element_fidelity`):** ผ่านการตรวจสอบ Status: `pass`, Diff: `0`

---

## 4. Key Takeaway & Best Practices สำหรับ Automation Tools

เมื่อสร้าง Tool สำหรับทำ Fast Live-Proxy Snapshot โดยอัตโนมัติ ต้องมีขั้นตอนป้องกันปัญหานี้ (Sanitization Rules):

1. **Auto-Scroll Pre-warm:**
   - ก่อนสั่งดึง `outerHTML` ให้รันสคริปต์เลื่อนหน้าจอลงไปล่างสุด (`window.scrollTo(0, document.body.scrollHeight)`) แล้วเลื่อนกลับขึ้นมาบนสุด เพื่อบังคับให้ IntersectionObserver และ Scroll Animations ทั้งหมด Trigger เป็นสถานะ Visible ให้เรียบร้อย
2. **Inline Style Sanitizer:**
   - กวาดล้าง Inline Styles ที่มี `opacity: 0` หรือ `visibility: hidden` ที่เกิดจาก Entrance Animation Library (เช่น Framer Motion, AOS, GSAP ScrollTrigger) ให้เป็นสถานะ Fully Revealed เสมอ
