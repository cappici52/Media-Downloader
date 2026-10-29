# Media Downloader

เว็บส่วนตัวสำหรับบันทึกวิดีโอและรูปภาพจาก YouTube, Facebook, Instagram, X และ TikTok
รันบน localhost ด้วย Python/FastAPI ใช้ yt-dlp สำหรับวิดีโอ, gallery-dl สำหรับรูป
และ ffmpeg สำหรับรวมภาพ/เสียงหรือแปลง MP3 เลือกสื่อทั้งสองชนิดจากโพสต์เดียวกันได้
หลายรายการรวมเป็น ZIP ส่วนวิดีโอใช้ MKV เพื่อรองรับ codec ต้นฉบับโดยไม่แปลงภาพใหม่

ใช้เฉพาะเนื้อหาของตัวเองหรือที่ได้รับอนุญาต รองรับโพสต์สาธารณะ และโพสต์ส่วนตัว
ที่บัญชีในเบราว์เซอร์ของคุณมีสิทธิ์ดูผ่าน session ที่ล็อกอินอยู่
ไม่มีระบบเลี่ยง DRM, paywall หรือสิทธิ์การเข้าถึงโพสต์

## รันด้วย Docker (แนะนำ)

ติดตั้ง Docker Desktop/Engine พร้อม Docker Compose แล้วรันจากโฟลเดอร์ repository:

```sh
git clone https://github.com/cappici52/Media-Downloader.git
cd Media-Downloader
docker compose up --build -d
```

เปิด [http://localhost:8000](http://localhost:8000) และดูสัญญา API ที่
[http://localhost:8000/openapi.json](http://localhost:8000/openapi.json)
อิมเมจมี ffmpeg, ffprobe และ Node.js 22 สำหรับตัวแก้ JavaScript challenge ของ YouTube
พร้อม dependency `yt-dlp-ejs` ไม่ต้องติดตั้งเครื่องมือเหล่านี้บน host
ปิด Swagger UI ที่พึ่ง CDN เพื่อรักษา CSP ที่ไม่โหลด third-party script
ใช้ OpenAPI JSON หรือ curl สำหรับตรวจสัญญา API

```sh
docker compose logs -f app
docker compose down
```

พอร์ตเปิดเฉพาะ `127.0.0.1` บน host อย่าเปลี่ยนเป็นพอร์ตสาธารณะ
ระบบไม่มีบัญชีผู้ใช้หรือระบบยืนยันตัวตน จึงไม่เหมาะกับการเผยแพร่บนอินเทอร์เน็ต
หากต้องเข้าจากนอกเครื่อง ให้ใช้ SSH tunnel หรือระบบเข้าถึงส่วนตัวที่ยืนยันตัวตน
และยังส่ง hostname/origin เป็น localhost ห้ามเปิดเว็บนี้เป็นบริการสาธารณะ

## รันด้วย Python บน Windows

ใช้ Python 3.12 ขึ้นไป ติดตั้ง [ffmpeg และ ffprobe](https://ffmpeg.org/download.html)
และ [Node.js 22 ขึ้นไป](https://nodejs.org/en/download) ลง PATH ก่อน
ตรวจด้วย `ffmpeg -version`, `ffprobe -version` และ `node --version`

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --workers 1
```

บน Linux/macOS ใช้ `.venv/bin/python` แทน `.venv\Scripts\python`
หากใช้ Linux ให้ติดตั้ง ffmpeg ผ่าน package manager ของระบบด้วย
ต้องใช้ ASGI worker **เพียง 1 process** เพราะคิวงานอยู่ในหน่วยความจำ

## วิธีใช้

1. วางลิงก์โพสต์หรือวิดีโอแล้วกด **ตรวจสอบ**
2. เลือกรูป/วิดีโอ และคุณภาพวิดีโอหรือ **เสียงอย่างเดียว MP3**
3. กด **ดาวน์โหลดที่เลือก** แล้วรอจนงานเสร็จ
4. กด **บันทึกไฟล์ลงเครื่อง** ก่อนหมดอายุ

หลังตรวจสอบลิงก์ กล่อง **เลือกสื่อที่จะบันทึก** จะแสดง thumbnail ของทุกรายการ
กดภาพเพื่อขยาย หรือกดคลิปเพื่อเล่นตัวอย่าง เลือกด้วย checkbox และกด **เสร็จแล้ว**
เพื่อกลับมาดาวน์โหลดรายการที่เลือก เปิดกล่องซ้ำได้จาก **ดูตัวอย่างและเลือกสื่อ**
มือถือแสดง 2 คอลัมน์และ desktop 4 คอลัมน์ ปิดด้วย Escape หรือกดนอกกล่องได้

คลิปตัวอย่างสตรีมผ่าน backend แบบ HTTP Range โดยไม่สร้างงานดาวน์โหลดและไม่เขียน
วิดีโอทั้งไฟล์ลง disk จำกัดครั้งละ 8 MB/60 วินาที และยุติ worker เมื่อปิดตัวอย่าง
ตัวอย่างต้องมีไฟล์ MP4/WebM ที่ browser เล่นได้; สื่อที่มีเฉพาะ HLS/DASH หรือ codec
ที่ browser ไม่รองรับอาจดูตัวอย่างไม่ได้ แต่ยังเลือกดาวน์โหลดได้ตามเดิม
บางคลิปมีตัวอย่างวิดีโอแบบไม่มีเสียง หน้าเว็บจะแจ้งให้ทราบ

รีเฟรชหน้าได้: browser เก็บเฉพาะ job ID ใน sessionStorage เพื่อกลับมาติดตามงาน
ไม่เก็บ URL ต้นทางหรือ cookies ใน browser storage การเริ่มเซิร์ฟเวอร์ใหม่ทำให้
ประวัติงานหาย และระบบจะลบโฟลเดอร์ชั่วคราว UUID ของงานเก่าที่อยู่ใน DOWNLOAD_DIR
อย่านำไฟล์ส่วนตัวมาใส่ในโฟลเดอร์ดังกล่าว

## ขีดจำกัดและการตั้งค่า

คัดลอก `.env.example` เป็น `.env` เพื่อปรับค่าใน Docker Compose
การรัน native ต้องส่ง environment variables เอง หรือเพิ่ม `--env-file .env` ให้ uvicorn

| ตัวแปร | ค่าเริ่มต้น | ความหมาย |
|---|---:|---|
| `MAX_FILE_MB` | 500 | ขนาดรวมต่อ directory งาน รวมไฟล์ระหว่างแปลงและ ZIP |
| `MAX_DURATION_SECONDS` | 0 | `0` = ไม่จำกัดความยาววิดีโอ; ใส่ค่าบวกหากต้องการกำหนดเพดานเอง |
| `MAX_ITEMS` | 100 | จำนวนสื่อรวมสูงสุดต่อโพสต์/งาน |
| `MAX_CONCURRENT_JOBS` | 2 | จำนวน process ดึงสื่อสูงสุด รวมการตรวจสอบลิงก์และ thumbnail |
| `MAX_QUEUED_JOBS` | 10 | จำนวนงานรอในคิว |
| `MAX_STORAGE_MB` | 2048 | เพดานพื้นที่เก็บไฟล์รวม |
| `MAX_JOB_HISTORY` | 100 | เพดานจำนวนงานที่ยังไม่หมดอายุ |
| `FILE_TTL_SECONDS` | 3600 | อายุไฟล์/ประวัติงานหลังเสร็จหรือผิดพลาด |
| `JOB_TIMEOUT_SECONDS` | 1800 | เวลาทำงานสูงสุดต่องาน |
| `INFO_TIMEOUT_SECONDS` | 120 | เวลาดึงข้อมูลสูงสุด |
| `DOWNLOAD_DIR` | `downloads` | ตำแหน่งไฟล์ชั่วคราวสำหรับ native |
| `COOKIES_BROWSER` | ว่าง | เปิดใช้ cookies จากเบราว์เซอร์เจ้าของเครื่องเมื่อจำเป็น |

watchdog ตรวจพื้นที่ทุก 250 ms; อาจมีข้อมูลเพิ่มเล็กน้อยระหว่างรอบตรวจ
งานที่เกินขนาดจะถูกหยุดและล้างไฟล์ การแปลงวิดีโอสงวนพื้นที่ output ไม่เกินครึ่งหนึ่ง
ของเพดานงานเพื่อเหลือพื้นที่ให้ไฟล์ input ดังนั้นวิดีโอบางไฟล์อาจชนเพดานก่อน 500 MB
เพิ่ม `MAX_FILE_MB` และ `MAX_STORAGE_MB` พร้อมกันหากต้องการไฟล์ใหญ่ขึ้น
TTL ตรวจทุกไม่เกิน 60 วินาที และเลื่อนการลบออกไประหว่างที่กำลังส่งไฟล์ให้ browser
ภาพ preview รับต้นฉบับไม่เกิน 12 MB/20 ล้านพิกเซล ย่อเหลือไม่เกิน 1280px
ตรวจไฟล์ภาพจริง ลบ EXIF และลบไฟล์ชั่วคราวหลังส่งเสร็จ

Docker Compose ส่งต่อค่าหลักจาก `.env`; หากต้องการเปลี่ยนตัวแปรอื่น ให้เพิ่มใน
`environment` ของ `compose.yaml` อย่าเพิ่ม `COOKIES_BROWSER` ใน Docker เป็นค่าเริ่มต้น

## Cookies จากเครื่องตัวเอง (ตัวเลือกสำหรับ native)

### เปิดหน้าแอปบน Chrome พร้อมใช้ session ล็อกอิน

backend อ่าน cookies จาก browser ตอนเริ่มเซิร์ฟเวอร์ แล้วเก็บเฉพาะโดเมนแพลตฟอร์ม
ที่รองรับไว้ใน RAM สูงสุด 6 ชั่วโมง Worker รับ session ผ่าน stdin ภายใน process
ไม่อ่านฐานข้อมูล Chrome ซ้ำ ไม่เขียนไฟล์ cookies และไม่ส่งค่า cookies ไปหน้าเว็บ
ดังนั้นหลังเตรียม session แล้วสามารถเปิด Chrome ใช้หน้าแอปได้ตามปกติ

บน Windows ให้ปิด Chrome เฉพาะตอนเตรียม session ครั้งแรก แล้วรัน:

```powershell
.\scripts\start_chrome.ps1
```

สคริปต์เตรียม session และเปิด Chrome ที่ localhost ให้ เมื่อ session ยังใช้ได้
รันซ้ำได้โดยไม่ต้องปิด Chrome หรือเริ่มเซิร์ฟเวอร์ใหม่ ต้องเก็บ backend ให้ทำงานอยู่
หากปิด backend/restart/session หมดอายุ ให้ปิด Chrome อีกครั้งแล้วรันสคริปต์ใหม่
สคริปต์ไม่บังคับปิด browser ไม่แก้ระบบเข้ารหัส และไม่เปลี่ยน security settings ของ Chrome

`GET /session` แสดงเฉพาะสถานะและเวลา ไม่มีข้อมูลล็อกอิน
`POST /session/refresh` ไม่รับ body และอ่านใหม่จาก browser ที่เจ้าของเครื่องตั้งค่าไว้
ใช้หลังปิด Chrome เพื่ออัปเดต session โดยไม่ต้อง restart backend
ตั้ง `BROWSER_SESSION_TTL_SECONDS` เพื่อเปลี่ยนอายุ cache ได้ (ค่าเริ่มต้น 21600)
การเตรียม session ไม่ได้รับประกันว่า cookies จะยังล็อกอินอยู่หรือเข้าถึงทุกโพสต์ได้

ค่าเริ่มต้นปิด cookies ไม่มีช่องหรือ API สำหรับอัปโหลด cookies
ระบบจะลองดึงโพสต์สาธารณะแบบไม่ใช้ cookies ก่อน แม้ตั้ง `COOKIES_BROWSER` ไว้
ยกเว้นโปรไฟล์ Instagram และ TikTok ที่มี session พร้อมอยู่ จะใช้ session นั้นก่อน
จึงไม่ต้องปิด Chrome สำหรับโพสต์ที่ดึงแบบสาธารณะได้ หากแพลตฟอร์มขอให้ล็อกอิน
หรือบล็อกการดึงแบบสาธารณะ จึงลองใช้ cookies ของ browser ที่ตั้งค่าไว้
ลิงก์ X ที่ลงท้าย `/photo/1` หรือ `/video/1` จะตรวจทั้งโพสต์เพื่อให้เลือกสื่อทั้งหมดได้
X อาจส่งสถานะ unavailable/TweetTombstone หรือ "No video could be found" แม้ยังเปิด
โพสต์ใน browser ได้ ระบบจะลอง session ของ browser ที่ตั้งค่าไว้เมื่อจำเป็น และแสดง
ปัญหาอ่าน cookies แยกจากปัญหาโพสต์ ไม่สรุปว่าโพสต์ถูกลบจากข้อมูลที่ไม่เพียงพอ
สำหรับ Instagram หาก endpoint เดิมส่งไปหน้าล็อกอิน ระบบจะลอง API โพสต์สาธารณะ
ด้วย session ใหม่ที่ไม่ใช้ browser cookies ก่อน แล้วส่งข้อมูลให้ gallery-dl/yt-dlp
ประมวลผลรูปและวิดีโอ รองรับ carousel และตัด tracking parameters ออกจากลิงก์
API สำรองนี้ยังขึ้นกับ Instagram และ query ID อาจเปลี่ยนได้ จึงไม่รับประกันทุกโพสต์
หากแพลตฟอร์มต้องล็อกอินแม้เป็นโพสต์สาธารณะ สามารถระบุ browser ในเครื่องตัวเอง:

```powershell
$env:COOKIES_BROWSER = "firefox"
.\.venv\Scripts\python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --workers 1
```

รองรับ firefox, chrome, chromium, edge, brave, opera, vivaldi และ safari ตามระบบ
ใช้ browser profile เริ่มต้นของผู้ใช้ที่รัน backend; ไม่รับชื่อ profile หรือ path จาก API
บาง browser/OS อาจอ่านหรือถอดรหัส cookies ไม่ได้ ให้แสดง error แทนการส่งออก cookies
อย่านำ cookies ไปใส่ใน repository
โพสต์ส่วนตัวต้องมี session ที่ยังไม่หมดอายุของแพลตฟอร์มนั้น และ extractor ต้องดึง
metadata ของสื่อสำเร็จด้วยสิทธิ์บัญชีของคุณ การตั้งชื่อ browser เพียงอย่างเดียวไม่ถือว่าล็อกอิน
หากบัญชีไม่มีสิทธิ์ดูหรือแพลตฟอร์มปฏิเสธการเข้าถึง ระบบจะแสดง error ภาษาไทย
ระบบไม่ข้ามข้อจำกัดสิทธิ์ ไม่รองรับ paywall/สมาชิกแบบเสียเงิน หรือ DRM
การดึงแบบไม่ใช้ cookies และ Instagram API สำรองยังรับเฉพาะโพสต์สาธารณะ
ลิงก์ Instagram ส่วนตัวที่มีรหัสยาวจะส่งให้ extractor เดิมโดยรักษารหัสไว้ครบ
ลิงก์ Story แบบ `/stories/USERNAME/STORY_ID/` รองรับทั้งรูปและวิดีโอผ่าน session
Instagram ที่ล็อกอิน โดยอ่านเฉพาะรหัสสื่อในลิงก์
ลิงก์รวม `/stories/USERNAME/` จะแสดง Story ปัจจุบันที่บัญชีมีสิทธิ์ดูให้เลือกดาวน์โหลด
รวมถึง Close Friends เมื่อเจ้าของให้สิทธิ์บัญชีนั้นแล้ว โดยยังใช้ขีดจำกัดจำนวนสื่อเดิม
Highlights แบบ `/stories/highlights/HIGHLIGHT_ID/` จะแสดงสื่อในอัลบั้มให้เลือกเช่นกัน
ระบบใช้ reel ID ของ Highlights และอ่าน query จากหน้า Highlights ของอัลบั้มนั้น
ระบบอ่าน query ของรายการ Story จากหน้า Story โดยตรง เพราะหน้าโปรไฟล์อาจไม่มี query นี้
Story ต้องยังไม่หมดอายุ/ถูกลบ และบัญชีต้องมีสิทธิ์ดู; การบล็อกของแพลตฟอร์มยังทำให้โหลดไม่ได้
Facebook Story แบบ `/stories/OWNER_ID/STORY_ID/` อ่านข้อมูลสื่อจากหน้า Story
โดยเลือกเฉพาะ Story ID ในลิงก์ เพื่อไม่หยิบสื่อจาก Story อื่นในถาดมาดาวน์โหลด
ใช้ session Chrome ของบัญชีที่มีสิทธิ์ดูเมื่อจำเป็น และใช้ parser ของ yt-dlp สำหรับวิดีโอ
ตัว parser แยกรูปจาก attachment แบบ Photo; การรองรับรูปทดสอบด้วย fixture
รองรับลิงก์ชุด Story/Highlights แบบ `/stories/BUCKET_ID/?source=profile_highlight`
โดยอ่านเฉพาะ card ที่เป็นสมาชิกของ BUCKET_ID นั้น รวมวิดีโอและรูปที่ Facebook ส่งมาในหน้า
ไม่ดึง Story ของบัญชีอื่นจากถาดข้างเคียง และไม่ไล่หน้าถัดไปของชุดที่ Facebook ส่งมาไม่ครบ
วิดีโอที่ไม่ระบุความละเอียดเลือกคุณภาพดีที่สุดตามลำดับ format ของต้นทาง โดยไม่ตั้งค่า resolution ขึ้นเอง
ยังไม่รองรับการไล่โหลด Facebook Story ทั้งถาดหรือ Story ที่หมดอายุ/เข้าไม่ถึง
สื่อที่มี license/ธง DRM จะถูกปฏิเสธ ส่วน certificate ทั่วไปอย่างเดียวไม่ถือว่าเข้ารหัส
Docker ไม่มี profile browser ของ host และคู่มือนี้ไม่แนะนำให้ mount profile เข้า container

## API

ตัวอย่าง PowerShell:

```powershell
$body = @{ url = "https://www.youtube.com/watch?v=VIDEO_ID" } | ConvertTo-Json
Invoke-RestMethod http://localhost:8000/info -Method Post -ContentType application/json -Body $body
```

`POST /info` รับ `{"url":"..."}` คืน `type` (`video`, `image`, `carousel`),
`title`, `thumbnail`, `duration`, `qualities`, `images` และ `items`
โพสต์ผสมใช้ `type: carousel` โดยแต่ละ item มี `type: video` หรือ `image`
รายการคุณภาพคืนตามต้นทางจริง thumbnail เป็น URL ภายในแอปที่หมดอายุได้

วิดีโอเลือกไฟล์ MKV (ค่าเริ่มต้น), MP4 หรือ MOV ได้จากหน้าดาวน์โหลด
ทุกแบบใช้สื่อความละเอียดและเฟรมเรตสูงสุดจากต้นทางก่อน ไม่ย่อภาพหรือปรับลด FPS
ระบบพยายาม remux โดยไม่เข้ารหัสใหม่ หาก MP4/MOV ไม่รองรับ codec เดิม
จะลองแปลงเฉพาะเสียงเป็น AAC ก่อน แล้วจึงแปลงภาพเป็น H.264 เมื่อจำเป็น
การแปลง codec มีการสูญเสียได้และใช้เวลาเพิ่ม; MKV เก็บ codec ภาพ/เสียงเดิม
การแปลงภาพใช้ libx264 CRF 18 หรือ libopenh264 bitrate อย่างน้อย 8 Mbps
หาก ffmpeg ไม่มี encoder ที่รองรับ จะแสดง error ให้เลือก MKV แทน
MP4 ที่เก็บ VP9/AV1 เดิมอาจเปิดไม่ได้ในโปรแกรมรุ่นเก่า ขึ้นกับ codec ที่โปรแกรมรองรับ
ตัวเลือกนี้ใช้กับทุกวิดีโอใน ZIP รวมถึงดาวน์โหลดโปรไฟล์ รูปภาพและ MP3 ไม่เปลี่ยนรูปแบบ

`POST /download` รับ:

```json
{
  "url": "https://x.com/OWNER/status/POST_ID",
  "video_format": "mp4",
  "selections": [
    {"id": "video-0", "quality": "best"},
    {"id": "image-0"}
  ]
}
```

คืน HTTP 202 พร้อม `job_id` และ `status_url`
`GET /jobs/{id}` คืน `status`: queued/running/completed/failed,
`progress` 0–100, `phase`, `error` และ `file_url` เมื่อเสร็จ
เปอร์เซ็นต์เป็นสัดส่วนโดยประมาณจากการโหลดแต่ละรายการ; ช่วงตรวจข้อมูลหรือแปลงไฟล์
อาจไม่มีเปอร์เซ็นต์ใหม่ หน้าเว็บจึงแสดงชื่อขั้นตอนประกอบ
`GET /files/{id}` ส่ง attachment เมื่อพร้อม หลายสื่อเป็น ZIP
`GET /health` สำหรับ health check และ `GET /openapi.json` สำหรับรายละเอียด schema
แต่ละ video item ใน `/info` มี `preview_url` เมื่อดูตัวอย่างได้
`GET /streams/{ticket}/{index}` รองรับ Range/206 สำหรับ player; ticket หมดอายุตาม TTL
ไม่รับ URL สื่ออิสระจาก client และไม่ส่ง URL CDN หรือ cookies ไปยัง browser
ข้อผิดพลาดใช้ `{"error":{"code":"...","message":"ข้อความภาษาไทย"}}`
HTTP 400/422 สำหรับลิงก์หรือตัวเลือกไม่ถูกต้อง, 429 คิวเต็ม/ไม่ว่าง, 507 พื้นที่ไม่พอ

## ความปลอดภัย

- รับ URL เฉพาะ HTTP/HTTPS, พอร์ตมาตรฐาน และ 7 โดเมนที่กำหนด รวม subdomain จริง
- ปฏิเสธ userinfo, IP literal, โดเมนคล้าย, control character และ URL กำกวม
- ตรวจ DNS ทุกคำตอบและ IP ที่ส่งให้ socket.connect จริงทุกครั้ง รวมหลัง redirect
  เพื่อกัน private/loopback/link-local/reserved/multicast และ DNS rebinding
- คำขอ CDN ไม่จำกัดอยู่แค่โดเมนแพลตฟอร์ม แต่ใช้กฎ IP/พอร์ตเดียวกัน
- socket guard อยู่เฉพาะ worker process และบังคับ yt-dlp ใช้ urllib
  ปิด proxy และ native curl/impersonation; ปิด ffmpeg network downloader fallback
- ffmpeg/ffprobe เปิดเฉพาะไฟล์ local ด้วย `file,pipe` protocol whitelist
  เรียก subprocess เป็น argument list ไม่มี shell interpolation
- thumbnail ผ่าน worker ที่ใช้ guard เช่นกัน browser ไม่ตาม URL CDN โดยตรง
- ไม่อ่าน configuration ของ extractor จากผู้ใช้ และไม่รับ cookies/options/path ผ่าน API
- จำกัดจำนวนงาน เวลา ขนาดไฟล์ พื้นที่รวม ขนาด request body และประวัติ พร้อมล้าง TTL
- ตรวจ Host/Origin และ Fetch Metadata; ไม่มี wildcard CORS; มี CSP และ nosniff
- Docker รันด้วย non-root user, read-only filesystem, จำกัด RAM/CPU/PID และไม่มี capabilities

socket guard เป็นการป้องกันในแอป ไม่ใช่ OS sandbox สำหรับโค้ด third-party ที่ถูกเจาะ
ใช้เฉพาะบนเครื่องที่ไว้ใจได้ และอัปเดต dependency/อิมเมจสม่ำเสมอ

## อัปเดต extractor

สำหรับ native หลังติดตั้ง test dependencies:

```powershell
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python scripts/update_extractors.py
```

สคริปต์อัปเดต yt-dlp พร้อม default dependencies และ gallery-dl รัน tests
แล้วบันทึกเวอร์ชันที่ผ่านใน `requirements.txt` หาก tests ล้มเหลวจะไม่แก้ไฟล์ requirements
แต่ package ใน venv ถูกอัปเดตแล้ว; สร้าง venv ใหม่จาก requirements เดิมหากต้องการย้อนกลับ

สำหรับ Docker โดยไม่ต้องมี Python บน host:

```powershell
$env:UPGRADE_EXTRACTORS = "1"
docker compose build --no-cache
docker compose up -d
```

บน Linux/macOS ใช้ `UPGRADE_EXTRACTORS=1 docker compose build --no-cache`
ตัวเลือกนี้ดึง extractor ล่าสุดตอน build และไม่แก้ pins ใน repository
ควรทดสอบลิงก์ของตัวเองหลังอัปเดตทุกครั้ง

## ทดสอบ

```powershell
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python -m unittest discover -s tests -v
node --check frontend/app.js
node --test tests/test_frontend_api.cjs
```

tests ใช้ fixture/mocks เพื่อทดสอบ URL, SSRF guard, adapter, คิว, TTL และ API
โดยไม่ดาวน์โหลดเนื้อหาจริงจากโซเชียล ชุดทดสอบแปลงสื่อจะทำงานเมื่อพบ ffmpeg/ffprobe
การทดสอบ UI แยกตรวจ desktop 1440×1000 และ mobile 390×844 รวม keyboard,
เลือกหลายสื่อ, MP3, progress, error, offline และกู้สถานะงานหมดอายุ

## ข้อจำกัด

- โพสต์ส่วนตัวต้องใช้บัญชีที่มีสิทธิ์ดู; โพสต์ที่ถูกลบ อยู่หลัง paywall หรือมี DRM ไม่รองรับ
- ไม่รองรับ livestream และ playlist; โปรไฟล์ Instagram อ่านเป็นหน้าและเลือกดาวน์โหลดเป็นชุด
- Facebook/Instagram/X อาจบังคับล็อกอินหรือบล็อก extractor ได้แม้โพสต์เป็นสาธารณะ
- รองรับเฉพาะรูปแบบที่โหลดผ่าน HTTP/HTTPS และ native HLS/DASH ได้อย่างปลอดภัย
  รูปแบบที่ต้องใช้ impersonation หรือ ffmpeg เชื่อมเครือข่ายจะถูกปฏิเสธ
- ไม่มี retry งานดาวน์โหลดอัตโนมัติจากหน้าเว็บ เพื่อป้องกันสร้างงานซ้ำเมื่อเครือข่ายขาด
- คิวและประวัติไม่คงอยู่หลัง restart ไม่รองรับหลาย ASGI workers หรือหลายเครื่อง

แหล่งอ้างอิง: [yt-dlp embedding](https://github.com/yt-dlp/yt-dlp#embedding-yt-dlp),
[YouTube JavaScript runtime](https://github.com/yt-dlp/yt-dlp/wiki/EJS),
[gallery-dl](https://github.com/mikf/gallery-dl),
[OWASP SSRF prevention](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html)

## ดาวน์โหลดจากโปรไฟล์ Instagram

วางลิงก์ `https://www.instagram.com/USERNAME/` เพื่ออ่านโพสต์หน้าแรก
เลือกโพสต์ในกริด หรือกดภาพปกเพื่อดูสื่อในโพสต์นั้น แล้วกลับมาเลือกโพสต์ต่อได้
กด **โหลดเพิ่ม** หรือ **อ่านโพสต์ทั้งหมด** เพื่ออ่านทีละหน้าจนสุด กด **หยุดอ่าน** ได้
โดยรายการที่อ่านแล้วและตัวเลือกเดิมจะยังอยู่ การอ่านล้มเหลวจะไม่แสดงว่าอ่านครบ

หลายโพสต์รวมเป็น `profile.zip` แยกโฟลเดอร์ตามโพสต์และไม่สร้าง ZIP ซ้อนกัน
วิดีโอเลือกคุณภาพสูงสุดที่ต้นทางเปิดให้ดึง พร้อมเสียงคุณภาพสูงสุดที่รองรับ
ใช้การ remux โดยไม่ลดหรือขยายความละเอียดภาพ

- บัญชีส่วนตัวต้องมี session ของบัญชีที่ได้รับสิทธิ์ดูแล้ว
- อ่านได้สูงสุด 1,000 โพสต์หรือ 100 หน้าต่อรอบ ไม่รับประกันโพสต์ที่ถูกซ่อน/ลบ
- `MAX_ITEMS` และ `MAX_FILE_MB` นับรวมสื่อทั้งหมดในงาน ไม่ใช่เฉพาะจำนวนโพสต์
- หากเกินขีดจำกัดหรือ `JOB_TIMEOUT_SECONDS` ให้แบ่งดาวน์โหลดเป็นชุดเล็กลง
- Instagram อาจจำกัดคำขอหรือเปลี่ยน query ได้ รายการที่อ่านแล้วจะยังอยู่ให้ลองใหม่
- `/info` รับ `cursor` สำหรับหน้าถัดไป ใช้ค่าที่ API คืนมาโดยตรงโดยไม่แก้ไข
- `/download` รับ selection `{"id":"post-POST_CODE"}` เมื่อ URL เป็นโปรไฟล์

ตัวอ่านโปรไฟล์ใช้ metadata query ของหน้าเว็บและรองรับ JSON stream/cursor
เนื่องจาก Instagram เปลี่ยน relay parameters บ่อย ดูรายงานต้นทาง
[gallery-dl #9829](https://github.com/mikf/gallery-dl/issues/9829) สำหรับข้อจำกัดของ extractor

## TikTok

รองรับโพสต์วิดีโอและโพสต์รูปภาพ รวมหลายรูปเป็น ZIP ผ่านช่องลิงก์เดิม
รองรับ `tiktok.com` และ subdomain เช่น `www.`, `m.`, `vt.`, `vm.` รวมถึง `/t/CODE/`
ลิงก์สั้นจะถูกตรวจ HTTP/HTTPS, DNS/IP และโดเมนทุกครั้งที่ redirect
ไม่เพิ่ม `tiktokv.com`, Douyin หรือเว็บดาวน์โหลดภายนอกเข้า allowlist

- ใช้ gallery-dl อ่านข้อมูลโพสต์และรูปภาพ แล้วใช้ parser ของ yt-dlp สำหรับวิดีโอ
- ลิงก์ `/photo/ID` และ `/video/ID` ใช้ข้อมูลโพสต์ชุดเดียวกัน
- เพลงประกอบโพสต์รูปภาพจะไม่ถูกแสดงเป็นคลิปวิดีโอแยก ส่วนคลิปจริงยังเลือก MP3 ได้
- พรีวิว คุณภาพวิดีโอ คิวงาน ขนาดไฟล์ ระยะเวลา จำนวนสื่อ และ TTL ใช้ระบบเดิม
- ยังไม่รองรับ TikTok LIVE; โปรไฟล์อ่านทีละหน้าและเลือกดาวน์โหลดเป็นชุดได้
- โพสต์ที่เข้าไม่ถึง จำกัดภูมิภาค หรือถูกแพลตฟอร์มบล็อกจะแสดง error ไม่ข้าม DRM/paywall
- หากตั้ง `COOKIES_BROWSER` ใช้ได้เฉพาะ session จากเบราว์เซอร์ในเครื่องตามเดิม

TikTok ที่มี session พร้อมจะใช้ session นั้นก่อน และเก็บ cookies ของหน้าต้นทางไว้ใน RAM
การโหลดวิดีโอและพรีวิวรักษากฎโดเมน/path/secure/วันหมดอายุของ CookieJar
ค่า cookies ไม่ถูกส่งกลับใน `/info` หรือใส่ใน DOM; พรีวิวใช้ proxy ฝั่ง backend เดิม
บางลิงก์ยังอาจถูก CDN ปฏิเสธได้ แอปไม่เปิดใช้ transport ที่ข้าม socket guard เพื่อเลี่ยงการบล็อก


### เลือกโพสต์จากโปรไฟล์ TikTok

วางลิงก์ `https://www.tiktok.com/@USERNAME` ได้โดยตรง (ตัด query เช่น `lang` อัตโนมัติ)
แอปอ่านประมาณ 15 โพสต์ต่อหน้า ใช้ **โหลดเพิ่ม**, **อ่านโพสต์ทั้งหมด** และ **หยุดอ่าน**
ในกล่องเลือกสื่อเดียวกับ Instagram หากรูปตัวอย่างใช้ช่องงานเต็ม หน้าเว็บจะรออ่านข้อมูล
ได้ถึง 20 วินาที โดยไม่เพิ่มจำนวนงานพร้อมกัน กดภาพปกเพื่อเปิดสื่อในโพสต์ เล่นคลิปหรือดูรูป
แล้วกด **กลับไปเลือกโพสต์ในโปรไฟล์** เพื่อคืนรายการและตัวเลือกเดิม

เลือกหลายโพสต์เพื่อรวมเป็น `profile.zip` แยกโฟลเดอร์ตามโพสต์ ไม่สร้าง ZIP ซ้อน
คลิปเลือกคุณภาพสูงสุดที่ต้นทางมีให้ดึง รูปภาพเก็บทุกภาพในโพสต์ที่เลือก
`MAX_ITEMS`, `MAX_FILE_MB`, เวลา timeout และ TTL ยังคงนับรวมทั้งงาน

- อ่านได้สูงสุด 1,000 โพสต์หรือ 100 หน้าต่อรอบ รายการซ้ำจะรวมเป็นรายการเดียว
- อ่านเฉพาะโพสต์ของเจ้าของโปรไฟล์ ไม่รวม repost, liked, saved หรือ LIVE
- `/info` รับ cursor แบบ `tt1.` ซึ่งผูกกับชื่อโปรไฟล์ ใช้ค่าที่ API คืนมาโดยไม่แก้ไข
- ใช้ gallery-dl อ่านข้อมูลและ cursor ผ่าน transport ภายใน worker ที่มี socket guard เดิม
- ไม่รับประกันว่าจะอ่านได้ทุกโพสต์: TikTok อาจซ่อนโพสต์ จำกัดคำขอ หรือส่งหน้าว่าง
  หากอ่านต่อไม่สำเร็จ รายการและตัวเลือกที่อ่านแล้วจะยังอยู่ และไม่แสดงว่าอ่านครบ
- โปรไฟล์ส่วนตัวต้องใช้ session ของบัญชีที่ได้รับสิทธิ์ดูแล้ว ไม่ข้ามข้อจำกัดการเข้าถึง

บัญชี TikTok ส่วนตัวอาจส่ง `videoCount=0` แม้มีโพสต์ แอปจะตรวจรายการด้วย session
ที่มีสิทธิ์อีกครั้ง หากยังไม่ส่งรายการจะแสดงข้อความเรื่อง session/สิทธิ์แทนผลสำเร็จว่าง
หาก Chrome ดูได้แต่แอปอ่านไม่ได้ ให้ปิด Chrome ชั่วคราวแล้วรีเฟรช session ผ่านหน้าแอป
ก่อนเปิด Chrome กลับ การเปลี่ยนบัญชีหรือเพิ่งได้รับสิทธิ์ดูอาจต้องเตรียม session ใหม่


## ธีม pixel art และภาษา

หน้าเว็บใช้ธีมมืดแบบ pixel art ทั้งหน้าหลัก กล่องเลือกสื่อ และพรีวิว
ไอคอนแมวขาวตาซ้ายฟ้า–ตาขวาทอง อ้าปากปล่อยภาพ/คลิป ใช้ร่วมกันเป็น favicon
กด **EN** หรือ **ไทย** ที่มุมหน้าหลักหรือในกล่องเลือกสื่อเพื่อเปลี่ยนภาษา
ระบบจำเฉพาะภาษาที่เลือกใน localStorage และเปลี่ยนข้อความโดยไม่รีเซ็ต
รายการที่เลือก ตัวเลือกเสียง คลิปที่กำลังเล่น หรืองานดาวน์โหลด
ชื่อโพสต์และคำบรรยายต้นทางไม่ถูกแปล ฟอนต์ Silkscreen และ license เก็บในโปรเจกต์
ไม่มีการโหลดฟอนต์หรือบริการแปลจากภายนอก

ตรวจ browser regression แบบ opt-in (ต้องมี Playwright และ Chrome):

```powershell
$env:MEDIA_UI_URL = 'http://127.0.0.1:8002'
.\.venv\Scripts\python -m pytest tests/test_pixel_ui.py -q
```

ใช้เซิร์ฟเวอร์ทดสอบแยกและ fixture สำหรับ metadata, ภาพ, progress และงานดาวน์โหลด
หากมีคลิปทดสอบ `pixel-ui-preview.webm` ในโฟลเดอร์ TEMP จะตรวจ playback ต่อเนื่องด้วย
ชุดทดสอบหลักจะข้าม browser test เมื่อไม่ได้ตั้ง `MEDIA_UI_URL`


## คุณภาพต้นฉบับและความยาววิดีโอ

หน้าเว็บเลือกคุณภาพสูงสุดที่ต้นทางมีให้ดาวน์โหลดอัตโนมัติ ไม่มีเมนูเลือกความละเอียด
ทั้งคลิปเดี่ยวและหลายโพสต์ใช้แนวทางเดียวกัน รวมวิดีโอกับเสียงโดยคัดลอก stream ต้นทาง
ไม่ upscale และไม่บีบอัดภาพใหม่ หากแพลตฟอร์มส่งมาเฉพาะไฟล์ที่บีบอัดแล้ว
แอปไม่สามารถกู้ไฟล์ก่อนอัปโหลดหรือรายละเอียดที่ต้นทางไม่ส่งให้ได้
เลือก **เสียงอย่างเดียว MP3** ได้เมื่อต้องการไฟล์เสียงแทนคลิป (แปลงเป็น 192 kbps)

`POST /download` รับ `quality: "best"` หรือไม่ระบุ quality เพื่อเลือกวิดีโอสูงสุด
ยังรับค่าเดิม เช่น `720p` และ `mp3` สำหรับผู้ใช้ API เดิม

ค่าเริ่มต้น `MAX_DURATION_SECONDS=0` หมายถึงไม่จำกัดความยาววิดีโอ
ขนาดไฟล์รวม 500 MB จำนวนสื่อ งานพร้อมกัน พื้นที่ดิสก์ และ TTL ยังคงตามค่าที่ตั้งไว้
`JOB_TIMEOUT_SECONDS` เป็นเวลาทำงานจริงของงานดาวน์โหลด ไม่ใช่ความยาวคลิป
หากโหลดไฟล์ใหญ่หรือเครือข่ายช้า ให้ปรับขนาดไฟล์ พื้นที่และ timeout ให้เหมาะกับเครื่อง


แมวจะเคี้ยวระหว่างตรวจสอบลิงก์ และพ่นสื่อเมื่อพบรายการสำเร็จก่อนเปิดกล่องเลือก
หากเปลี่ยนลิงก์ ยกเลิก หรือเกิดข้อผิดพลาดจะกลับท่าปกติ ปุ่ม **แอนิเมชัน: เปิด / ปิด** ข้างปุ่มภาษาควบคุมแอนิเมชันของแมว
เมื่อเลือกภาพนิ่งจะเปิดผลลัพธ์ทันที ไม่ต้องรอเอฟเฟกต์พ่น
ทดสอบด้วย `MEDIA_UI_URL` และ `pytest tests/test_cat_animation.py -q`

หากเปิด Chrome ใหม่ ระบบจะเตรียมเฟรมแมวตั้งแต่เริ่มหน้า และใช้ภาพที่โหลดสำเร็จ
ได้แม้ตัวถอด SVG ของ Chrome คืนข้อผิดพลาดหรือไม่ตอบกลับ โดยไม่ค้างรอแอนิเมชัน

แอนิเมชันแมวใช้ PNG sprite โดยตรงและเปิดเป็นค่าเริ่มต้นตามที่ผู้ใช้ขอ
ระบบจำค่าเปิด/ปิดของแมวใน localStorage แยกตามที่อยู่เว็บ เช่น localhost และ 127.0.0.1
ค่าของแมวใช้เฉพาะในแอปนี้ ไม่เปลี่ยนการตั้งค่า Windows หรือ Chrome ทั้งระบบ


เคอร์เซอร์ในหน้าเว็บเป็นอุ้งเท้าแมว pixel art: สีฟ้าปกติ สีทองสำหรับปุ่ม/ข้อความ
สีแดงสำหรับปุ่มที่กดไม่ได้ และหมุนระหว่างอ่านข้อมูล/ดาวน์โหลด/เปิดตัวอย่างสื่อ
ปุ่มแอนิเมชันควบคุมทั้งแมวและการหมุนของเคอร์เซอร์ หน้าจอสัมผัสไม่แสดงเคอร์เซอร์ซ้อน
เบราว์เซอร์ที่ไม่รองรับ top-layer popover ใช้เคอร์เซอร์อุ้งเท้าแบบนิ่งสำรอง
ทดสอบด้วย `MEDIA_UI_URL` และ `pytest tests/test_paw_cursor.py -q`
