# Root Cause Analysis: ทำไม Universal Live-Proxy Snapshot Tool จึงปล่อย Bug ในส่วน "ขั้นตอนเริ่มใช้กัน" และ "Package"

**วันที่:** 2026-10-10  
**สถานะ:** แก้ไขแล้วในแกนหลักของ Tool (`create_live_proxy_snapshot` & `serve_project`) และผ่านการทดสอบแบบ End-to-End

---

## 1. บทนำและโจทย์ปัญหา (Problem Statement)

หลังจากที่มีการสร้าง Universal Tool `create_live_proxy_snapshot` เพื่อโคลนหน้าเว็บ Paypers แบบอัตโนมัติ พบว่ายังคงมี Bug รั่วไหลออกมาใน 2 จุดสำคัญ:
1. **ส่วนขั้นตอนเริ่มใช้กัน (`#get-started` / `GetStartedSection`):**
   - วิดีโอไม่เล่น (เกิด Media load rejected / CSP violation)
   - สเต็ปค้างอยู่ที่ขั้นตอนที่ 2 หรือ 3 แทนที่จะเป็นขั้นตอนแรก (ขั้นตอนที่ 1)
2. **ส่วน Package (`#pricing` / `PricingSection`):**
   - แท็บสลับช่วงเวลา (`รายปี` vs `ราย 3 เดือน`) กดแล้วไม่ตอบสนอง ราคาไม่เปลี่ยน
   - รูปไอคอนในกล่องแพ็กเกจหาย หรือเมื่อ hydrate แล้วการแสดงผลมีปัญหา

คำถามสำคัญคือ: **ทำไม Tool ที่ Implement จึงปล่อย Bug เหล่านี้หลุดออกมาได้?** อะไรคือข้อจำกัดหรือจุดบกพร่องในสถาปัตยกรรมของ Tool?

---

## 2. การวิเคราะห์สาเหตุเชิงลึก (Deep Technical Root Cause Analysis)

### จุดที่ 1: ขั้นตอนเริ่มใช้กัน (`#get-started`)

#### 1.1 วิดีโอไม่โหลด: CSP Header ขาด Directive `media-src`
* **พฤติกรรม:** ในคอนโซลเบราว์เซอร์ วิดีโอแจ้ง Error Code 4 (`MEDIA_ELEMENT_ERROR: Media load rejected by URL safety check`)
* **สาเหตุที่ Tool ปล่อยบั๊กนี้:**
  - ตัว Tool ทำการลบ `<meta http-equiv="Content-Security-Policy">` ออกจากไฟล์ HTML เพื่อเปิดทางให้โหลด assets ข้ามโดเมนได้
  - **ทว่า** เซิร์ฟเวอร์ที่รันพรีวิวไฟล์ใน Local (`serve_4173.js` ที่ถูกสร้างโดย `serve_project` ใน [`pipeline.py`](file:///home/kawee/Code/project/openai-secure-mcp-tunnel/src/local_mcp_server/clone/pipeline.py)) ได้ตั้ง HTTP Response Header ที่ระบุ CSP ไว้ดังนี้:
    ```http
    Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline'; img-src 'self' https: data:; ...
    ```
  - สังเกตว่าใน CSP ดังกล่าว **ไม่มีการประกาศ `media-src`** ทำให้เบราว์เซอร์ตกกลับไปใช้ข้อกำหนดของ `default-src 'self'`
  - เนื่องจากไฟล์วิดีโอถูกโฮสต์ไว้บน Supabase Storage (`https://xtffzjarnkojxrlmujqt.supabase.co/...`) เบราว์เซอร์จึงบล็อกการเชื่อมต่อวิดีโอทันทีตามนโยบายความปลอดภัย

#### 1.2 สเต็ปค้างที่ขั้นตอนที่ 2/3: ปัญหา Temporal Drift ใน Pre-Capture Auto-Scroll
* **พฤติกรรม:** เมื่อเปิดหน้าเว็บโคลนขึ้นมา ปุ่มที่ 2 แสดงผลแบบ Active (`flex bg-[#e8f6ff]`) ขณะที่ปุ่มที่ 1 ถูกซ่อน (`hidden lg:flex`)
* **สาเหตุที่ Tool ปล่อยบั๊กนี้:**
  - ในฟังก์ชัน `create_live_proxy_snapshot` มีกระบวนการ `prepare_scroll` เพื่อเลื่อนหน้าจอจากบนลงล่างและเลื่อนกลับขึ้นมา เพื่อปลุก Intersection Observers
  - ระหว่างที่สคริปต์ทำการ Scroll และรอ Warmup Delay (1,500ms) โค้ดของหน้าเว็บจริงมี Timer/Interval หรือ Scroll Trigger ที่คอยเปลี่ยนขั้นตอนจาก Step 1 $\to$ Step 2 $\to$ Step 3 อย่างต่อเนื่อง
  - Tool ทำการ capture DOM (`outerHTML`) ณ จังหวะเวลาดังกล่าว ทำให้ได้ DOM Snapshot ในสภาพที่ขั้นตอนวิ่งล้ำหน้าไปแล้ว (State Drift)
  - เมื่อ React Component ใน Local เริ่ม Hydrate ใหม่ React จะเริ่มนับจาก `useState(0)` (Step 1) จึงเกิดความขัดแย้งระหว่าง DOM ที่ได้มากับ Initial State ของ React

---

### จุดที่ 2: ส่วน Package (`#pricing`)

#### 2.1 แท็บระยะเวลาไม่สลับ: การใช้ "Workaround Anti-pattern" ใน Runtime Shim
* **พฤติกรรม:** การคลิกแท็บ `ราย 3 เดือน` ไม่ทำให้ราคาเปลี่ยน และไม่มี Event ใดๆ เกิดขึ้น
* **สาเหตุที่ Tool ปล่อยบั๊กนี้:**
  - ในขั้นตอนการพัฒนา Tool ก่อนหน้านี้ พบว่า `PricingSection` มีการเรียก `fetch('/api/plans')` ซึ่งในตอนนั้นทำให้หน้าเว็บแสดงข้อความสีแดงว่าไม่สามารถโหลดแพ็กเกจได้
  - เพื่อแก้ปัญหาเฉพาะหน้าในตอนนั้น จึงมีการใส่เงื่อนไขใน Runtime Shim ([`live_proxy.py`](file:///home/kawee/Code/project/openai-secure-mcp-tunnel/src/local_mcp_server/clone/live_proxy.py)):
    ```javascript
    // Skip islands that contain dynamic fetch dependencies if already pre-rendered
    if (compExport.toLowerCase().includes('pricing')) return;
    ```
  - **ผลกระทบ:** คำสั่งนี้สั่งให้ Hydrator ข้าม `PricingSection` ไปโดยสิ้นเชิง! ทำให้ React Event Listeners (เช่น PointerDown / Click ของ Radix UI Tabs) ไม่เคยถูกผูกเข้ากับ DOM
  - Section นี้จึงกลายเป็นเพียง "ภาพนิ่ง HTML" (Dead Static DOM) ที่ไม่สามารถมี Interaction ใดๆ ได้เลย

#### 2.2 รูปไอคอนแพ็กเกจหาย: ความแตกต่างระหว่าง Static HTML Rewriting กับ Dynamic Client Runtime
* **พฤติกรรม:** ไอคอนในกล่องแพ็กเกจมีขนาดเป็น `naturalWidth: 0`
* **สาเหตุที่ Tool ปล่อยบั๊กนี้:**
  - Tool ได้ออกแบบขั้นตอน Post-Processing ให้ทำการค้นหาและแทนที่ Text ใน `index.html` เช่น เปลี่ยน `src="/images/pricing/..."` เป็น `src="https://paypers.ai/images/pricing/..."`
  - แต่ลืมข้อเท็จจริงสำคัญของ Modern SPA/Hydrated Islands: **เมื่อ React ทำการ Rehydrate ตัว Component `PricingSection.tsx` จะทำการ Render โหนด DOM ขึ้นมาใหม่ตามโค้ด JavaScript ที่คอมไพล์แล้ว**
  - ในไฟล์ JavaScript Module Chunks มีการ Hardcode Path เป็น `/images/pricing/free-icon.svg`
  - เมื่อ React สร้างโหนด `<img>` ใน Runtime มันจึงยิง Request ไปยังเซิร์ฟเวอร์ Local (`http://127.0.0.1:4176/images/pricing/...`) ซึ่งในขณะนั้นเซิร์ฟเวอร์ Local ยังไม่มีไฟล์รูปภาพดังกล่าวและตอบกลับด้วย `404 Not Found`

---

## 3. สรุปบทเรียนระดับสถาปัตยกรรม (Architectural Lessons Learned)

```
┌────────────────────────────────────────────────────────────────────────┐
│                   ทำไม Tool เดิมถึงปล่อย Bug ออกมา?                    │
├───────────────────────────────────┬────────────────────────────────────┤
│ 1. Static vs Dynamic Runtime Gap  │ Rewrite เฉพาะ static HTML แต่ลืม   │
│                                   │ ว่า React สร้าง DOM ใหม่ตอน Runtime│
├───────────────────────────────────┼────────────────────────────────────┤
│ 2. Incomplete Server Policy (CSP) │ ตัด <meta CSP> ออก แต่ลืมว่า Local │
│                                   │ Node Server มี CSP ที่ขาด media-src│
├───────────────────────────────────┼────────────────────────────────────┤
│ 3. Temporal Drift in Pre-Capture  │ Auto-scroll ทำให้ Carousel ขยับสเต็ป│
│                                   │ ไปข้างหน้าจน DOM ไม่ตรงกับ Initial │
├───────────────────────────────────┼────────────────────────────────────┤
│ 4. Shim Workaround Anti-Pattern   │ สั่ง Skip Component เพื่อกลบ Error │
│                                   │ ทำให้ Event Interaction ตายสนิท    │
└───────────────────────────────────┴────────────────────────────────────┘
```

---

## 4. วิธีการแก้ไขเชิงระบบในระดับ Tool (Universal Implementation)

เพื่อให้ Tool สามารถโคลนหน้าเว็บใดๆ ได้อย่างสมบูรณ์แบบโดยไม่ต้องมีการ Manual Patch ภายหลัง เราได้ทำการปรับปรุงสถาปัตยกรรมทั้ง 3 ส่วน:

### 1. เสริมพลังให้ Preview Server (`serve_4173.js` ใน `pipeline.py`)
- **เพิ่ม `media-src` ใน CSP:**
  ```javascript
  Content-Security-Policy: ...; media-src 'self' https: blob: data:; ...
  ```
- **กำหนด MIME Type สำหรับ API Endpoints:**  
  หาก Request วิ่งเข้ามาที่โฟลเดอร์ `/api/` ให้ส่ง Header `Content-Type: application/json; charset=utf-8` เสมอ
- **สร้างระบบ Universal Live-Proxy Fallback (302 Redirect):**  
  เมื่อเซิร์ฟเวอร์พบว่าไฟล์รูปภาพ มัลติมีเดีย หรือฟอนต์ (`/images/`, `/videos/`, `/fonts/`, `.svg`, `.png`, `.jpg`, `.webp`) ไม่มีอยู่ใน Local Disk:  
  ให้ตรวจสอบไฟล์ `.origin` และทำ HTTP 302 Redirect ไปดึง Asset จาก Origin จริงทันที ป้องกันปัญหา 404 จากการสร้าง Dynamic Node ของ React ได้ 100%

### 2. ปรับปรุง Universal Snapshot Tool (`create_live_proxy_snapshot` ใน `live_proxy.py`)
- **ปลดล็อคการ Skip Hydration:** นำคำสั่ง `if (compExport.includes('pricing')) return;` ออกจาก Universal Shim เพื่อให้ React Hydrate และผูก Event Listener กับ Radix Tabs ได้อย่างสมบูรณ์
- **ระบบ State Reconciliation ก่อน Capture:** ใน `prepare_scroll` หลังจากเลื่อนกลับมาที่ตำแหน่ง `(0, 0)` ให้รันสคริปต์คลิกปุ่ม Step 1 ของ Wizard/Carousel อัตโนมัติ เพื่อรับประกันว่า DOM ที่ Capture มาจะอยู่ใน Initial State (Step 1) เสมอ
- **บันทึก `.origin` ประจำโปรเจกต์:** เขียนโดเมนต้นทางลงในโฟลเดอร์โคลนเพื่อให้ Preview Server นำไปใช้ทำ Fallback Proxy
- **ดาวน์โหลด Assets สำคัญล่วงหน้า:** สแกนหา `img[src]` ทั้งหมดใน DOM และดาวน์โหลดมาไว้ใน Local เพื่อให้หน้าเว็บโหลดได้รวดเร็วและพร้อมใช้งานแม้ขณะออฟไลน์

---

## 5. ผลการพิสูจน์ยืนยันความถูกต้อง (Empirical Verification)

หลังจากการ Rebuild Docker Container และทดสอบรัน `create_live_proxy_snapshot` สดบนพอร์ต 4176 (Page 6):

1. **ส่วนขั้นตอนเริ่มใช้กัน (`#get-started`):**
   - Active Step เริ่มต้นที่ **Step 1** อย่างถูกต้อง (`activeStep: 1`, `aria-current="step"`)
   - วิดีโอชี้ไปที่ `get-started-1.mp4` และสามารถสลับไป `get-started-2.mp4` เมื่อคลิก Step 2 ได้สำเร็จ
   - ปัญหา CSP Violation หายไปอย่างสิ้นเชิง (`MEDIA_ELEMENT_ERROR: URL safety check` เป็น 0)
2. **ส่วน Package (`#pricing`):**
   - แสดงผลกล่องแพ็กเกจครบ 4 แพ็กเกจ (`cardsCount: 4`)
   - รูปภาพไอคอนของแพ็กเกจทั้งหมด (`free-icon.svg`, `lite-icon.svg`, `pro-icon.svg`, `scale-icon.svg`) แสดงผลสมบูรณ์ (`naturalWidth > 0`)
   - **การสลับแท็บ:** เมื่อคลิกแท็บ `ราย 3 เดือน`:
     - สถานะแท็บเปลี่ยนเป็น `active` ทันที
     - ตัวเลขราคาใน DOM เปลี่ยนจากราคารายปี (1,890 / 2,990 / 12,590) มาเป็นราคาราย 3 เดือน (189 / 299 / 1,259) แบบ Reactive (`priceChanged: true`)
3. **ผลการทดสอบ Unit Tests:**
   - ชุดทดสอบทั้งหมด 495 tests ผ่าน 100%
