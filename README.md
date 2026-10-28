# Media Downloader

เว็บส่วนตัวสำหรับบันทึกวิดีโอและรูปภาพจาก YouTube, Facebook, Instagram และ X
รันบน localhost ด้วย Python/FastAPI ใช้ yt-dlp สำหรับวิดีโอ, gallery-dl สำหรับรูป
และ ffmpeg สำหรับรวมภาพ/เสียงหรือแปลง MP3 เลือกสื่อทั้งสองชนิดจากโพสต์เดียวกันได้
หลายรายการรวมเป็น ZIP ส่วนวิดีโอใช้ MKV เพื่อรองรับ codec ต้นฉบับโดยไม่แปลงภาพใหม่

ใช้เฉพาะเนื้อหาของตัวเองหรือที่ได้รับอนุญาต และเฉพาะเนื้อหาสาธารณะ
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
| `MAX_DURATION_SECONDS` | 1800 | ความยาววิดีโอสูงสุด ตรวจ metadata และตรวจไฟล์ด้วย ffprobe |
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

ค่าเริ่มต้นปิด cookies ไม่มีช่องหรือ API สำหรับอัปโหลด cookies
ระบบจะลองดึงโพสต์สาธารณะแบบไม่ใช้ cookies ก่อนเสมอ แม้ตั้ง `COOKIES_BROWSER` ไว้
จึงไม่ต้องปิด Chrome สำหรับโพสต์ที่ดึงแบบสาธารณะได้ หากแพลตฟอร์มขอให้ล็อกอิน
หรือบล็อกการดึงแบบสาธารณะ จึงลองใช้ cookies ของ browser ที่ตั้งค่าไว้
ลิงก์ X ที่ลงท้าย `/photo/1` หรือ `/video/1` จะตรวจทั้งโพสต์เพื่อให้เลือกสื่อทั้งหมดได้
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
อย่านำ cookies ไปใส่ใน repository และอย่าเปิดใช้เพื่อเข้าถึงโพสต์ส่วนตัว
เมื่อเปิด cookies ระบบต้องพบ metadata ที่ระบุว่าเป็นสาธารณะด้วย หากยืนยันไม่ได้
จะปฏิเสธงานด้วยข้อความภาษาไทย แม้บัญชีของคุณจะเข้าถึงโพสต์นั้นได้
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

`POST /download` รับ:

```json
{
  "url": "https://x.com/OWNER/status/POST_ID",
  "selections": [
    {"id": "video-0", "quality": "720p"},
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
```

tests ใช้ fixture/mocks เพื่อทดสอบ URL, SSRF guard, adapter, คิว, TTL และ API
โดยไม่ดาวน์โหลดเนื้อหาจริงจากโซเชียล ชุดทดสอบแปลงสื่อจะทำงานเมื่อพบ ffmpeg/ffprobe
การทดสอบ UI แยกตรวจ desktop 1440×1000 และ mobile 390×844 รวม keyboard,
เลือกหลายสื่อ, MP3, progress, error, offline และกู้สถานะงานหมดอายุ

## ข้อจำกัด

- โพสต์ที่ล็อก ส่วนตัว ถูกลบ ต้องสมัครสมาชิก หรือมี DRM จะไม่รองรับ
- ไม่รองรับ livestream และไม่ไล่เก็บทั้ง profile/playlist ผ่าน gallery queue
- Facebook/Instagram/X อาจบังคับล็อกอินหรือบล็อก extractor ได้แม้โพสต์เป็นสาธารณะ
- รองรับเฉพาะรูปแบบที่โหลดผ่าน HTTP/HTTPS และ native HLS/DASH ได้อย่างปลอดภัย
  รูปแบบที่ต้องใช้ impersonation หรือ ffmpeg เชื่อมเครือข่ายจะถูกปฏิเสธ
- ไม่มี retry งานดาวน์โหลดอัตโนมัติจากหน้าเว็บ เพื่อป้องกันสร้างงานซ้ำเมื่อเครือข่ายขาด
- คิวและประวัติไม่คงอยู่หลัง restart ไม่รองรับหลาย ASGI workers หรือหลายเครื่อง

แหล่งอ้างอิง: [yt-dlp embedding](https://github.com/yt-dlp/yt-dlp#embedding-yt-dlp),
[YouTube JavaScript runtime](https://github.com/yt-dlp/yt-dlp/wiki/EJS),
[gallery-dl](https://github.com/mikf/gallery-dl),
[OWASP SSRF prevention](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html)
