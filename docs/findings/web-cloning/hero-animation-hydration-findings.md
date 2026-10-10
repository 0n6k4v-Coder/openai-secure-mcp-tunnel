# Root Cause Analysis: Hero Section Animation Freeze in Live-Proxy Snapshot

## 1. Problem Statement
เมื่อทำ Live-Proxy Snapshot โคลนหน้าเว็บ Paypers (`apps/paypers2/clone`) พบว่า:
1. **Hero Floating Animation:** Object ที่ควรจะลอยขึ้น-ลงเรื่อยๆ (component `Float` เช่น รูปไอคอนรอบๆ Hero) กลับหยุดนิ่ง
2. **Initial Effect:** เอฟเฟกต์ Fade/Slide เข้ามาตอนโหลดหน้าเว็บ (component `FadeUp`) ไม่แสดงการ Transition เคลื่อนไหว

---

## 2. Technical Investigation & Root Cause

จากการตรวจสอบลึกถึงระดับ DOM, Astro Island Runtime, และ React Hydrator:

### สาเหตุที่ 1: การจับ Snapshot สภาพ Hydrated DOM (Post-Hydration Capture)
- สถาปัตยกรรมของเว็บไซต์เป้าหมายสร้างด้วย **Astro Islands** ร่วมกับ **React + Framer Motion**:
  - `<astro-island uid="..." component-export="Float" ...>`
  - `<astro-island uid="..." component-export="FadeUp" ...>`
- เมื่อเราจับ Live DOM snapshot จากเบราว์เซอร์ที่เปิดอยู่ (`document.documentElement.outerHTML`):
  1. Component เหล่านี้ถูก hydrate และเล่น animation เสร็จสมบูรณ์ไปแล้ว
  2. สไตล์ที่เป็น inline style ถูก freeze ค้างไว้ใน DOM เช่น:
     - `Float`: ค้างอยู่ที่ `style="transform: translateY(-0.646937px);"`
     - `FadeUp`: ค้างอยู่ที่สถานะปลายทาง `style="opacity: 1; transform: none;"`

### สาเหตุที่ 2: Astro Custom Element `astro-island` ลบ Attribute `ssr` ทิ้ง
- เมื่อ Astro Island hydrate ตัวเองสำเร็จใน runtime ดั้งเดิม โค้ดของ Astro จะรันคำสั่ง:
  ```javascript
  await this.hydrator(this)(this.Component, props, slots, ...);
  this.removeAttribute("ssr"); // <-- ลบ attribute ssr ออกจาก DOM
  ```
- ส่งผลให้ใน Captured HTML ไม่มี attribute `ssr` ติดมาด้วย:
  ```html
  <!-- ก่อน hydrate ใน SSR ปกติ -->
  <astro-island uid="ZBdQM6" ssr component-export="Float" ...>
  
  <!-- หลัง hydrate ที่ถูก capture มา -->
  <astro-island uid="ZBdQM6" component-export="Float" ...> <!-- ไม่มี ssr -->
  ```

### สาเหตุที่ 3: React Hydrator มี Guard Check ป้องกัน Re-hydration หากไม่มี `ssr`
เมื่อเปิดหน้า snapshot ขึ้นมาใหม่:
1. Custom element `astro-island` ทำงาน
2. ฟังก์ชัน hydrator ของ Astro React (`@astrojs/react`) มีโค้ด Guard Check บรรทัดแรกสุดดังนี้:
   ```javascript
   (el) => (Component, props, slots, opts) => {
     if (!el.hasAttribute("ssr")) return; // <-- ติดตรงนี้! หยุดทำงานทันที
     ...
     ReactDOMClient.hydrateRoot(el, ...);
   }
   ```
3. เนื่องจาก `hasAttribute("ssr") === false` Hydrator จึง **abort การทำงานทันที** และไม่ยอม Mount/Hydrate React Component อีกเลย ทำให้ Framer Motion runtime ไม่ถูก initialize ใหม่

---

## 3. Resolution & Fix

เราทำการแก้ไขผ่าน [main.js](file:///home/kawee/Code/project/openai-secure-mcp-tunnel/project/apps/paypers2/clone/src/js/main.js) โดยเพิ่ม **Snapshot Hydration Shim**:

```javascript
(function() {
  function hydrateAllIslands() {
    const islands = document.querySelectorAll('astro-island');
    islands.forEach(async (island) => {
      const compExport = island.getAttribute('component-export');

      // 1. Reset initial styles สำหรับ entrance animations (FadeUp) ให้เริ่มที่เฟรม 0
      if (compExport === 'FadeUp') {
        const directDiv = island.firstElementChild;
        if (directDiv && directDiv.tagName === 'DIV') {
          directDiv.style.opacity = '0';
          directDiv.style.transform = 'translateY(20px)';
        }
      }

      // 2. เติม attribute 'ssr' กลับเข้าไปเพื่อให้ React Hydrator ยอมรับการ mount
      if (!island.hasAttribute('ssr')) {
        island.setAttribute('ssr', '');
      }

      // 3. สั่ง hydrate() ตัวเกาะ
      if (typeof island.hydrate === 'function') {
        try {
          await island.hydrate();
        } catch (e) {
          console.warn('[AutoHydrate] Failed for', compExport, e);
        }
      }
    });
  }

  if (document.readyState === 'complete') {
    setTimeout(hydrateAllIslands, 50);
  } else {
    window.addEventListener('load', () => setTimeout(hydrateAllIslands, 50));
  }
})();
```

---

## 4. Verification

ตรวจสอบผ่าน Chrome DevTools บน Page 5 (`http://127.0.0.1:4175/`):
- **Float Animation:**
  - $T_0$: `translateY(-13.8261px)`
  - $T_{1s}$: `translateY(-2.88771px)`
  - สถานะ: `isMoving: true` (ขยับลอยต่อเนื่องแบบ smooth 100% ตรงกับต้นฉบับ)
- **FadeUp Entrance:**
  - เริ่มต้นจาก `opacity: 0, translateY(20px)` และ animate เข้ามาเป็น `opacity: 1, transform: none` อย่างถูกต้อง
