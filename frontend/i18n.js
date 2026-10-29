"use strict";
// UI copy uses canonical Thai sources. Only language preference is stored.
window.MediaI18n = (() => {
  const dictionary = {
  "เบราว์เซอร์เล่น codec ของคลิปนี้ไม่ได้ ลองดาวน์โหลดไฟล์เพื่อเปิดด้วยโปรแกรมที่รองรับ": "Your browser cannot play this video codec. Download the file and open it with a compatible player.",
  "ข้อมูลช่วงวิดีโอจากต้นทางไม่ถูกต้อง": "The source returned invalid video range data.",
  "ไฟล์ต้นทางใหญ่เกินขีดจำกัดพรีวิว": "The source file exceeds the preview size limit.",
  "เตรียมพรีวิวนานเกินกำหนด กรุณาลองใหม่": "Preview preparation timed out. Please try again.",
  "กำลังเตรียมพรีวิวคุณภาพสูงสุดและรวมเสียง อาจใช้เวลาสักครู่…": "Preparing the highest-quality preview and combining audio. This may take a moment…",
  "พรีวิวคุณภาพสูงสุดจากต้นทาง": "Highest available source quality preview",
  "เตรียมพรีวิวไม่สำเร็จ กรุณาตรวจสอบลิงก์ใหม่": "Could not prepare the preview. Check the link again.",
  "รูปแบบไฟล์วิดีโอ": "Video file format",
  "MKV · เก็บ codec เดิม": "MKV · Original codecs",
  "คงความละเอียดและเฟรมเรตเดิม · MP4/MOV อาจต้องแปลง codec และใช้เวลานานขึ้น": "Keep source resolution and frame rate · MP4/MOV may need codec conversion and take longer",
  "รูปแบบวิดีโอไม่รองรับ กรุณาเลือก MKV, MP4 หรือ MOV": "Unsupported video format. Choose MKV, MP4 or MOV.",
  "codec ของคลิปนี้ต้องแปลงภาพ กรุณาติดตั้ง ffmpeg ที่มี libx264 หรือเลือก MKV": "This codec needs conversion. Install ffmpeg with libx264 or choose MKV.",
  "สร้างไฟล์รูปแบบที่เลือกไม่สำเร็จ ลองเลือก MKV เพื่อเก็บ codec เดิม": "Could not create the selected format. Try MKV to keep the original codecs.",
  "แอนิเมชัน: เปิด": "Animation: on",
  "แอนิเมชัน: ปิด": "Animation: off",
  "แมว: เคลื่อนไหว": "Cat: animated",
  "แมว: ภาพนิ่ง": "Cat: still",
  "พบสื่อแล้ว กำลังจัดให้คุณ…": "Media found. Getting it ready…",
  "เสียง MP3 · 192 kbps": "MP3 audio · 192 kbps",
  "คุณภาพสูงสุดจากต้นทาง": "Highest available quality",
  "เสียงอย่างเดียว MP3": "Audio only (MP3)",
  "ดาวน์โหลดทุกสื่อในโพสต์ที่เลือกเป็น ZIP · วิดีโอคุณภาพสูงสุดจากต้นทาง": "Save all media in selected posts as a ZIP · Highest available video quality",
  "บันทึกวิดีโอและรูปภาพจากลิงก์": "Save videos and images from a link",
  "วางลิงก์": "Paste link",
  "เลือกสื่อ": "Select media",
  "ดาวน์โหลด": "Download",
  "ลิงก์วิดีโอ โพสต์ หรือโปรไฟล์": "Video, post or profile link",
  "วางลิงก์ที่นี่ เช่น https://youtu.be/…": "Paste a link, e.g. https://youtu.be/…",
  "ตรวจสอบ": "Check link",
  "YouTube · Facebook · Instagram · X · TikTok — เนื้อหาของคุณหรือที่ได้รับอนุญาต": "YouTube · Facebook · Instagram · X · TikTok — Yours or used with permission",
  "เลือกสื่อที่ต้องการ": "Choose what to save",
  "เริ่มจากวางลิงก์ที่คุณต้องการบันทึก": "Start with a link you want to save",
  "ตรวจสอบลิงก์เพื่อดูตัวอย่างและเลือกวิดีโอหรือรูปภาพ": "Check a link to preview and choose videos or images",
  "ไม่มีรูปตัวอย่าง": "No preview image",
  "ตัวอย่างสื่อจากโพสต์": "Media preview from the post",
  "เลือกได้ทั้งวิดีโอและรูปภาพ หลายรายการจะรวมเป็นไฟล์ ZIP": "Choose videos and images. Multiple files are saved as a ZIP.",
  "ดูตัวอย่างและเลือกสื่อ": "Preview and select media",
  "กลับไปเลือกโพสต์ในโปรไฟล์": "Back to profile posts",
  "← กลับไปเลือกโพสต์ในโปรไฟล์": "← Back to profile posts",
  "ดาวน์โหลดที่เลือก": "Download selected",
  "ยังไม่มีงานดาวน์โหลด": "No downloads yet",
  "บันทึกไฟล์ลงเครื่อง": "Save file to your device",
  "ตรวจสอบสถานะอีกครั้ง": "Check status again",
  "ใช้กับเนื้อหาของตัวเองหรือที่ได้รับอนุญาตเท่านั้น": "Save only your own content or content you have permission to use.",
  "บางแพลตฟอร์มอาจต้องล็อกอินหรือบล็อกการดึงข้อมูล": "Some platforms require sign-in or may block extraction.",
  "เลือกสื่อที่จะบันทึก": "Select what to save",
  "เลือกโพสต์ที่จะบันทึก": "Select posts to save",
  "กดที่รูปเพื่อขยาย หรือกดที่คลิปเพื่อเล่นตัวอย่าง": "Open an image to enlarge it, or a video to play a preview.",
  "กดภาพปกเพื่อดูสื่อในโพสต์ เลือกหลายโพสต์เพื่อรวมเป็น ZIP": "Open a cover to preview its post. Select multiple posts to save a ZIP.",
  "เลือกทั้งหมด": "Select all",
  "โหลดเพิ่ม": "Load more",
  "อ่านโพสต์ทั้งหมด": "Read all posts",
  "หยุดอ่าน": "Stop reading",
  "กลับไปดูทั้งหมด": "Back to all media",
  "เสร็จแล้ว": "Done",
  "ขั้นตอนการดาวน์โหลด": "Download steps",
  "ความคืบหน้าการดาวน์โหลด": "Download progress",
  "ปิดกล่องเลือกสื่อ": "Close media picker",
  "กำลังโหลดตัวอย่าง…": "Loading preview…",
  "คลิปนี้ไม่มีรูปแบบตัวอย่างที่เบราว์เซอร์เล่นได้ คุณยังเลือกดาวน์โหลดไฟล์ได้": "No browser-compatible preview is available. You can still download this video.",
  "กำลังเปิดตัวอย่างคลิป…": "Opening video preview…",
  "ตัวอย่างนี้ไม่มีเสียง ไฟล์ดาวน์โหลดจะรวมเสียงตามต้นทาง": "This preview is muted. The downloaded file includes source audio when available.",
  "กำลังเล่นตัวอย่าง · ยังไม่ได้สร้างงานดาวน์โหลด": "Playing preview · No download job created",
  "เล่นตัวอย่างไม่ได้ ลิงก์อาจหมดอายุหรือรูปแบบไม่รองรับ ลองตรวจสอบโพสต์ใหม่ หรือเลือกดาวน์โหลดไฟล์": "Preview unavailable. The link may have expired or its format is unsupported. Check the post again or download it.",
  "กดปุ่มเล่นบนคลิปเพื่อเริ่มดูตัวอย่าง": "Press play to preview the video.",
  "ไม่มีรูปตัวอย่างสำหรับรายการนี้": "No preview image is available for this item.",
  "โหลดรูปตัวอย่างไม่ได้ กรุณาตรวจสอบลิงก์อีกครั้ง": "Could not load the image. Please check the link again.",
  "การเชื่อมต่อใช้เวลานานเกินไป กรุณาลองใหม่": "The connection timed out. Please try again.",
  "เชื่อมต่อแอปไม่ได้ ตรวจสอบว่าเซิร์ฟเวอร์ยังทำงานอยู่ แล้วลองอีกครั้ง": "Cannot connect to the app. Check that the server is running and try again.",
  "ทำรายการไม่สำเร็จ กรุณาลองใหม่": "The request failed. Please try again.",
  "ยังไม่พบโพสต์ อาจไม่มีโพสต์หรือบัญชีที่เชื่อมต่อยังไม่มีสิทธิ์ดู": "No posts found. This account may have no posts, or your session may lack access.",
  "แพลตฟอร์มส่งหน้าซ้ำ กรุณาลองใหม่ภายหลัง": "The platform returned a repeated page. Please try again later.",
  "อ่านครบขีดจำกัด 100 หน้าแล้ว กรุณาเลือกดาวน์โหลดเป็นชุด": "Reached the 100-page limit. Please download in smaller batches.",
  "อ่านครบขีดจำกัด 1,000 โพสต์แล้ว กรุณาเลือกดาวน์โหลดเป็นชุด": "Reached the 1,000-post limit. Please download in smaller batches.",
  "กรุณาวางลิงก์ http หรือ https ที่ถูกต้อง": "Enter a valid HTTP or HTTPS link.",
  "กำลังตรวจสอบลิงก์…": "Checking link…",
  "บางแพลตฟอร์มอาจใช้เวลาสักครู่": "Some platforms may take a moment.",
  "ยังตรวจสอบลิงก์นี้ไม่ได้": "Could not check this link",
  "ตรวจสอบลิงก์และสิทธิ์ของบัญชีที่ล็อกอิน แล้วกดตรวจสอบอีกครั้ง": "Check the link and your signed-in account's access, then try again.",
  "กำลังรอคิว": "Queued",
  "กำลังตรวจสอบสื่ออีกครั้ง": "Checking media again",
  "กำลังดาวน์โหลด": "Downloading",
  "กำลังแปลงไฟล์": "Converting",
  "กำลังทำงาน": "Working",
  "ดาวน์โหลดเสร็จแล้ว — พร้อมบันทึกไฟล์": "Download complete — ready to save",
  "ดาวน์โหลดไม่สำเร็จ กรุณาลองใหม่": "Download failed. Please try again.",
  "ดาวน์โหลดไม่สำเร็จ — เลือกรายการแล้วลองใหม่ได้": "Download failed — you can select media and try again.",
  "งานหมดอายุหรือระบบถูกเริ่มใหม่ กรุณาตรวจสอบลิงก์อีกครั้ง": "The job expired or the server restarted. Please check the link again.",
  "ยังตรวจสอบสถานะไม่ได้ งานอาจยังทำงานอยู่": "Cannot check the status yet. Your job may still be running.",
  "กรุณาเลือกอย่างน้อยหนึ่งรายการ": "Select at least one item.",
  "เลือกเกินจำนวนที่กำหนด กรุณาแบ่งดาวน์โหลดเป็นชุด": "Too many items selected. Please download in smaller batches.",
  "กำลังสร้างงาน…": "Creating download…",
  "ยังยืนยันการสร้างงานไม่ได้": "Could not confirm the download job",
  "วิดีโอ": "Video",
  "รูปภาพ": "Image",
  "โพสต์": "Post",
  "โพสต์หลายรายการ": "Multiple media",
  "สื่อ": "Media",
  "ระบบกำลังทำงานเต็มจำนวน กรุณารอสักครู่": "All worker slots are busy. Please wait a moment.",
  "ต้องล็อกอิน เว็บไซต์อาจไม่อนุญาตให้ดึงโพสต์นี้": "Sign-in is required, or the platform is restricting this post.",
  "แพลตฟอร์มบล็อกการดึงข้อมูล กรุณาลองใหม่ภายหลัง": "The platform blocked extraction. Please try again later.",
  "ไม่พบวิดีโอหรือรูปในลิงก์นี้ หรือเนื้อหาถูกลบแล้ว": "No videos or images were found, or the content was removed.",
  "บัญชีที่ล็อกอินยังไม่มีสิทธิ์เข้าถึงโพสต์นี้ หรือ session หมดอายุ": "Your signed-in account cannot access this post, or its session has expired.",
  "รองรับเฉพาะลิงก์ YouTube, Facebook, Instagram, X และ TikTok เท่านั้น": "Only YouTube, Facebook, Instagram, X and TikTok links are supported.",
  "อ่าน cookies ของเบราว์เซอร์ไม่ได้ เพราะไฟล์ถูกล็อก กรุณาปิดเบราว์เซอร์ทุกหน้าต่างแล้วลองใหม่": "The browser cookie database is locked. Close all browser windows and try again.",
  "ดึงข้อมูลไม่สำเร็จ ลองอัปเดต yt-dlp และ gallery-dl แล้วตรวจสอบลิงก์อีกครั้ง": "Could not extract media. Update yt-dlp and gallery-dl, then check the link again."
};
  const bindings = new Map();
  let language = "th";
  try { if (localStorage.getItem("media-language") === "en") language = "en"; } catch { /* Optional storage. */ }
  const patterns = [
    [/^สูงสุด ([\d,.]+) MB ต่องาน · ความยาววิดีโอไม่จำกัด · ไม่เกิน ([\d,.]+) รายการ · ไฟล์เก็บไว้ ([\d,.]+) นาที$/, (_, size, items, ttl) => `Up to ${size} MB/job · No video duration limit · ${items} items · Files kept for ${ttl} min`],
    [/^เลือก ([\d,]+) \/ ([\d,]+) (โพสต์|รายการ)(.*)$/, (_, a, b, kind, tail) => `Selected ${a} / ${b} ${kind === "โพสต์" ? "posts" : "items"}${translate(tail)}`],
    [/^ · รวม ([\d,]+) สื่อ(.*)$/, (_, n, tail) => ` · ${n} media${translate(tail)}`],
    [/^ · เกินขีดจำกัด กรุณาแบ่งเป็นชุด$/, () => " · Over the limit. Select a smaller batch."],
    [/^อ่านแล้ว ([\d,]+) โพสต์(.*)$/, (_, n, tail) => `${n} posts loaded${translate(tail)}`],
    [/^ · ยังมีโพสต์เพิ่มเติม$/, () => " · More posts available"],
    [/^ · อ่านครบตามที่แพลตฟอร์มส่งมาแล้ว$/, () => " · All posts returned by the platform loaded"],
    [/^กำลังอ่านโพสต์เพิ่ม… อ่านแล้ว ([\d,]+) โพสต์$/, (_, n) => `Loading more… ${n} posts loaded`],
    [/^เก็บไว้ ([\d,]+) โพสต์ · อ่านต่อไม่สำเร็จ$/, (_, n) => `${n} posts kept · Could not load the next page`],
    [/^หยุดอ่านแล้ว · เก็บไว้ ([\d,]+) โพสต์$/, (_, n) => `Stopped · ${n} posts kept`],
    [/^(วิดีโอ|รูปภาพ|โพสต์|ดูสื่อในโพสต์|เล่นวิดีโอ|ดูรูปภาพ|คุณภาพวิดีโอ|ตัวอย่างรูปภาพ) ([\d,]+)$/, (_, kind, n) => `${({"วิดีโอ":"Video","รูปภาพ":"Image","โพสต์":"Post","ดูสื่อในโพสต์":"Preview post","เล่นวิดีโอ":"Play video","ดูรูปภาพ":"View image","คุณภาพวิดีโอ":"Video quality","ตัวอย่างรูปภาพ":"Image preview"})[kind]} ${n}`],
    [/^([\d,]+) สื่อ · (มีวิดีโอ|รูปภาพ)$/, (_, n, kind) => `${n} media · ${kind === "มีวิดีโอ" ? "Includes video" : "Images"}`],
    [/^สูงสุด ([\d,.]+) MB ต่องาน · วิดีโอไม่เกิน ([\d,.]+) นาที · ไม่เกิน ([\d,.]+) รายการ · ไฟล์เก็บไว้ ([\d,.]+) นาที$/, (_, size, minutes, items, ttl) => `Up to ${size} MB/job · ${minutes} min/video · ${items} items · Files kept for ${ttl} min`],
    [/^(.*) · ([\d,]+) รายการ(.*)$/, (_, kind, n, tail) => `${translate(kind)} · ${n} items${translate(tail)}`],
    [/^โปรไฟล์ (.+)$/, (_, name) => `${name} profile`],
    [/^ · ([\d,]+:[\d]+) นาที$/, (_, time) => ` · ${time} min`],
    [/^(กำลังรอคิว|กำลังตรวจสอบสื่ออีกครั้ง|กำลังดาวน์โหลด|กำลังแปลงไฟล์|กำลังทำงาน)(.*)$/, (_, phase, tail) => translate(phase) + tail],
  ];
  function translate(source) {
    source = String(source ?? "");
    if (language === "th" || !source) return source;
    if (dictionary[source]) return dictionary[source];
    for (const [pattern, render] of patterns) { const match = source.match(pattern); if (match) return render(...match); }
    const suffix = " หากการเชื่อมต่อขาด งานอาจถูกสร้างแล้ว กรุณาตรวจสอบก่อนลองใหม่";
    if (source.endsWith(suffix)) return translate(source.slice(0, -suffix.length)) + " If the connection was lost, a job may already exist. Check before trying again.";
    return /[\u0e00-\u0e7f]/.test(source) ? "The request could not be completed. Check your account access and try again." : source;
  }
  function bind(element, attribute, source) {
    if (!element) return;
    let fields = bindings.get(element);
    if (!fields) { fields = new Map(); bindings.set(element, fields); }
    fields.set(attribute, String(source ?? ""));
    if (attribute === "textContent") element.textContent = translate(source);
    else element.setAttribute(attribute, translate(source));
  }
  function text(element, source) { bind(element, "textContent", source); }
  function original(element) { return bindings.get(element)?.get("textContent") ?? element.textContent; }
  function append(element, source) { text(element, original(element) + source); }
  function label(source) { const element = document.createElement("span"); text(element, source); return element; }
  function prune() { for (const element of bindings.keys()) if (!element.isConnected) bindings.delete(element); }
  function setLanguage(next) {
    language = next === "en" ? "en" : "th";
    try { localStorage.setItem("media-language", language); } catch { /* Optional storage. */ }
    document.documentElement.lang = language;
    for (const [element, fields] of bindings) {
      if (!element.isConnected) { bindings.delete(element); continue; }
      for (const [attribute, source] of fields) {
        if (attribute === "textContent") element.textContent = translate(source);
        else element.setAttribute(attribute, translate(source));
      }
    }
    document.querySelectorAll("[data-language-toggle]").forEach(button => {
      button.textContent = language === "th" ? "EN" : "ไทย";
      button.setAttribute("aria-label", language === "th" ? "Switch to English" : "เปลี่ยนเป็นภาษาไทย");
    });
    document.title = language === "th" ? "Media Downloader — ดาวน์โหลดวิดีโอและรูปภาพ" : "Media Downloader — Save videos and images";
  }
  document.querySelectorAll("[data-i18n]").forEach(element => text(element, element.textContent));
  document.querySelectorAll("[placeholder], [aria-label], [alt]").forEach(element => {
    for (const attribute of ["placeholder", "aria-label", "alt"]) {
      const source = element.getAttribute(attribute);
      if (source && /[\u0e00-\u0e7f]/.test(source)) bind(element, attribute, source);
    }
  });
  setLanguage(language);
  return { text, append, original, label, prune, attr: bind, translate, setLanguage, get language() { return language; } };
})();
