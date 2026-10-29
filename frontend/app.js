"use strict";
const $ = (id) => document.getElementById(id);
const form = $("link-form"), urlInput = $("url"), inspectButton = $("inspect"), downloadButton = $("download");
let media = null, inspectedUrl = "", inspection = null, revision = 0, activeJob = null, polling = false, submitting = false;
const selected = new Map();
let profileLoading = null, readAllPosts = false, profileReturn = null;
const numbers = new Intl.NumberFormat("th-TH", { maximumFractionDigits: 0 });
const picker = $("media-picker");
let pickerTrigger = null, viewerTrigger = null, viewerRevision = 0;

function prepareCatFrame(image) {
  return new Promise(resolve => {
    const loaded = async () => {
      image.removeEventListener("load", loaded); image.removeEventListener("error", loaded);
      if (image.naturalWidth > 0) {
        let timer;
        try {
          await Promise.race([image.decode(), new Promise(done => { timer = setTimeout(done, 200); })]);
        } catch { /* Loaded SVG views can render even when Chrome rejects decode(). */ }
        finally { clearTimeout(timer); }
      }
      resolve(image.complete && image.naturalWidth > 0);
    };
    if (image.complete) loaded();
    else { image.addEventListener("load", loaded, { once: true }); image.addEventListener("error", loaded, { once: true }); }
  });
}
// A native PNG sheet avoids Chrome's SVG-view decoding and fragment cache.
const catSprite = new Image();
const spriteURL = getComputedStyle($("cat-scene")).getPropertyValue("--cat-chew-image").trim();
catSprite.src = spriteURL.slice(4, -1).trim().replace(/^["']|["']$/g, "");
const catFramesReady = prepareCatFrame(catSprite);
let catMotion = true;
try { catMotion = localStorage.getItem("cat-motion") !== "off"; } catch { /* Optional preference storage. */ }
function updateCatMotion() {
  document.documentElement.dataset.catMotion = catMotion ? "on" : "off";
  const toggle = $("cat-motion-toggle");
  toggle.setAttribute("aria-pressed", String(catMotion));
  MediaI18n.text(toggle, catMotion ? "แอนิเมชัน: เปิด" : "แอนิเมชัน: ปิด");
}
updateCatMotion();
$("cat-motion-toggle").addEventListener("click", () => {
  catMotion = !catMotion;
  try { localStorage.setItem("cat-motion", catMotion ? "on" : "off"); } catch { /* Optional preference storage. */ }
  updateCatMotion();
});
$("cat-motion-toggle").disabled = false;

let catStartedAt = 0;
function setCatState(state) {
  const scene = $("cat-scene");
  scene.dataset.state = state;
  delete scene.dataset.ready;
  if (state === "chewing") {
    catStartedAt = performance.now();
    catFramesReady
      .then(ready => {
        if (ready && scene.dataset.state === "chewing") {
          scene.dataset.ready = "true";
          catStartedAt = performance.now();
        }
      })
      .catch(() => { /* Keep the original cat visible if an animation asset fails. */ });
  }
}
function waitForCat(milliseconds, signal) {
  return new Promise((resolve, reject) => {
    if (signal.aborted) { reject(new DOMException("Aborted", "AbortError")); return; }
    const abort = () => { clearTimeout(timer); signal.removeEventListener("abort", abort); reject(new DOMException("Aborted", "AbortError")); };
    const timer = setTimeout(() => { signal.removeEventListener("abort", abort); resolve(); }, milliseconds);
    signal.addEventListener("abort", abort, { once: true });
  });
}
async function finishCat(signal) {
  if (!catMotion) { setCatState("idle"); return; }
  await Promise.race([catFramesReady, waitForCat(800, signal)]);
  if (signal.aborted) throw new DOMException("Aborted", "AbortError");
  await waitForCat(Math.max(0, 280 - (performance.now() - catStartedAt)), signal);
  setCatState("spitting");
  MediaI18n.text($("empty-title"), "พบสื่อแล้ว กำลังจัดให้คุณ…");
  await waitForCat(620, signal);
  setCatState("idle");
}

function error(message = "", field = false) {
  MediaI18n.text($("error-message"), message);
  urlInput.setAttribute("aria-invalid", String(field));
  if (field) urlInput.focus();
}
function step(index) {
  document.querySelectorAll(".steps li").forEach((node, i) => {
    if (i === index) node.setAttribute("aria-current", "step");
    else node.removeAttribute("aria-current");
  });
}
function busy(button, value) { button.disabled = value; button.setAttribute("aria-busy", String(value)); }
function selectionState() {
  document.documentElement.dataset.appBusy = String(!!inspection || submitting || !!activeJob || !!profileLoading);
  const count = [...selected.values()].filter(Boolean).length;
  MediaI18n.text($("selection-count"), media ? `เลือก ${numbers.format(count)} / ${numbers.format(media.items.length)} ${media.type === "profile" ? "โพสต์" : "รายการ"}` : "");
  const mediaCount = media?.type === "profile" ? media.items.filter((item) => selected.get(item.id)).reduce((total, item) => total + (item.media_count || 1), 0) : count;
  if (media?.type === "profile") MediaI18n.append($("selection-count"), ` · รวม ${numbers.format(mediaCount)} สื่อ`);
  if (mediaCount > (media?.limits?.max_items || 100)) MediaI18n.append($("selection-count"), " · เกินขีดจำกัด กรุณาแบ่งเป็นชุด");
  MediaI18n.text($("picker-count"), MediaI18n.original($("selection-count")));
  $("select-all").checked = !!media && count === media.items.length;
  $("select-all").indeterminate = !!media && count > 0 && count < media.items.length;
  $("output-options").hidden = !media || (media.type !== "profile" && !media.items.some((item) => item.type === "video"));
  $("video-format").disabled = !!activeJob || submitting || !!inspection || !!profileLoading || !media;
  downloadButton.disabled = !count || !!activeJob || submitting || !!inspection || !!profileLoading || mediaCount > (media?.limits?.max_items || 100);
  $("open-picker").disabled = !media || !!activeJob || submitting || !!inspection;
  $("return-profile").hidden = !profileReturn;
  $("return-profile-picker").hidden = !profileReturn;
  $("return-profile-picker").disabled = !!activeJob || submitting || !!inspection;
  $("return-profile").disabled = !!activeJob || submitting || !!inspection;
  $("load-more").disabled = !!profileLoading || !!activeJob || !media?.next_cursor;
  $("load-all-posts").disabled = $("load-more").disabled;
  $("stop-profile").hidden = !profileLoading;
  $("stop-profile").disabled = !profileLoading;
  document.querySelectorAll(".media-tile").forEach((tile) => tile.classList.toggle("is-selected", !!selected.get(tile.dataset.id)));
}

function closeViewer(restore = true) {
  viewerRevision++;
  const video = $("viewer-video");
  video.pause(); video.removeAttribute("src"); video.load(); video.hidden = true;
  $("viewer-image").removeAttribute("src"); $("viewer-image").hidden = true;
  $("media-viewer").hidden = true;
  if (restore && viewerTrigger?.isConnected) viewerTrigger.focus();
}
function openViewer(item, index, trigger) {
  closeViewer(false); viewerTrigger = trigger;
  const currentViewer = viewerRevision;
  const isVideo = item.type === "video";
  MediaI18n.text($("viewer-title"), `${isVideo ? "วิดีโอ" : "รูปภาพ"} ${index + 1}`);
  MediaI18n.text($("viewer-status"), ""); MediaI18n.text($("viewer-error"), "");
  $("media-viewer").hidden = false;
  if (isVideo) {
    if (!item.preview_url?.startsWith("/streams/")) {
      MediaI18n.text($("viewer-error"), "คลิปนี้ไม่มีรูปแบบตัวอย่างที่เบราว์เซอร์เล่นได้ คุณยังเลือกดาวน์โหลดไฟล์ได้");
    } else {
      const video = $("viewer-video"); video.hidden = false;
      video.poster = item.thumbnail || ""; video.src = item.preview_url;
      MediaI18n.text($("viewer-status"), "กำลังเปิดตัวอย่างคลิป…");
      video.onplaying = () => { if (currentViewer === viewerRevision) MediaI18n.text($("viewer-status"), item.preview_muted ? "ตัวอย่างนี้ไม่มีเสียง ไฟล์ดาวน์โหลดจะรวมเสียงตามต้นทาง" : "กำลังเล่นตัวอย่าง · ยังไม่ได้สร้างงานดาวน์โหลด"); };
      video.onerror = () => { if (currentViewer === viewerRevision) { MediaI18n.text($("viewer-status"), ""); MediaI18n.text($("viewer-error"), "เล่นตัวอย่างไม่ได้ ลิงก์อาจหมดอายุหรือรูปแบบไม่รองรับ ลองตรวจสอบโพสต์ใหม่ หรือเลือกดาวน์โหลดไฟล์"); } };
      video.play().catch(() => { if (currentViewer === viewerRevision && !video.error) MediaI18n.text($("viewer-status"), "กดปุ่มเล่นบนคลิปเพื่อเริ่มดูตัวอย่าง"); });
    }
  } else {
    const image = $("viewer-image"); MediaI18n.attr(image, "alt", `ตัวอย่างรูปภาพ ${index + 1}`);
    if (item.thumbnail?.startsWith("/thumbnails/")) { image.src = item.thumbnail; image.hidden = false; }
    else MediaI18n.text($("viewer-error"), "ไม่มีรูปตัวอย่างสำหรับรายการนี้");
    image.onerror = () => { MediaI18n.text($("viewer-error"), "โหลดรูปตัวอย่างไม่ได้ กรุณาตรวจสอบลิงก์อีกครั้ง"); };
  }
  $("media-viewer").scrollIntoView({ block: "nearest" });
  $("viewer-title").focus({ preventScroll: true });
}
function openPicker() {
  if (!media || picker.open) return;
  pickerTrigger = document.activeElement;
  picker.showModal(); document.documentElement.classList.add("picker-open");
  window.PawCursor?.raise();
}
$("open-picker").addEventListener("click", openPicker);
$("close-picker").disabled = false; $("close-viewer").disabled = false;
$("close-picker").addEventListener("click", () => picker.close());
$("close-viewer").addEventListener("click", () => closeViewer());
picker.addEventListener("close", () => {
  readAllPosts = false; profileLoading?.abort();
  closeViewer(false); document.documentElement.classList.remove("picker-open");
  if (pickerTrigger?.isConnected) pickerTrigger.focus();
});
picker.addEventListener("keydown", (event) => {
  if (event.key !== "Tab") return;
  const controls = [...picker.querySelectorAll("button:not(:disabled), input:not(:disabled), select:not(:disabled), video[controls]")].filter((node) => node.getClientRects().length > 0);
  const first = controls[0], last = controls[controls.length - 1];
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
});
picker.addEventListener("click", (event) => {
  if (event.target !== picker) return;
  const bounds = picker.getBoundingClientRect();
  if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) picker.close();
});
async function api(path, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), path === "/info" ? 135000 : 20000);
  const outer = options.signal;
  if (outer) outer.addEventListener("abort", () => controller.abort(), { once: true });
  const waitUntil = Date.now() + 20000;
  try {
    while (true) {
      const response = await fetch(path, { ...options, signal: controller.signal, headers: { "Content-Type": "application/json", ...options.headers } });
      const body = await response.json();
      // Profile thumbnails share the bounded worker pool with inspection.
      // Wait briefly for a slot only for read-only info; never retry a download.
      if (path === "/info" && response.status === 429 && body.error?.code === "busy" && Date.now() < waitUntil) {
        await new Promise((resolve) => setTimeout(resolve, 1000));
        if (controller.signal.aborted) throw new DOMException("Aborted", "AbortError");
        continue;
      }
      if (!response.ok) {
        const failure = new Error(body.error?.message || "ทำรายการไม่สำเร็จ กรุณาลองใหม่");
        failure.status = response.status;
        throw failure;
      }
      return body;
    }
  } catch (issue) {
    if (issue.name === "AbortError") throw new Error("การเชื่อมต่อใช้เวลานานเกินไป กรุณาลองใหม่");
    if (issue instanceof TypeError) throw new Error("เชื่อมต่อแอปไม่ได้ ตรวจสอบว่าเซิร์ฟเวอร์ยังทำงานอยู่ แล้วลองอีกครั้ง");
    throw issue;
  } finally { clearTimeout(timeout); }
}

function renderMedia(result, preserve = false) {
  const previous = preserve ? new Map(selected) : new Map();
  media = result;
  selected.clear();
  const isProfile = result.type === "profile";
  $("profile-controls").hidden = !isProfile;
  if (!preserve) MediaI18n.text($("profile-error"), "");
  MediaI18n.text($("picker-title"), isProfile ? "เลือกโพสต์ที่จะบันทึก" : "เลือกสื่อที่จะบันทึก");
  MediaI18n.text($("picker-help"), isProfile ? "กดภาพปกเพื่อดูสื่อในโพสต์ เลือกหลายโพสต์เพื่อรวมเป็น ZIP" : "กดที่รูปเพื่อขยาย หรือกดที่คลิปเพื่อเล่นตัวอย่าง");
  MediaI18n.text($("download-note"), isProfile ? "ดาวน์โหลดทุกสื่อในโพสต์ที่เลือกเป็น ZIP · วิดีโอคุณภาพสูงสุดจากต้นทาง" : "เลือกได้ทั้งวิดีโอและรูปภาพ หลายรายการจะรวมเป็นไฟล์ ZIP");
  if (isProfile) MediaI18n.text($("profile-status"), `อ่านแล้ว ${numbers.format(result.items.length)} โพสต์${result.next_cursor ? " · ยังมีโพสต์เพิ่มเติม" : " · อ่านครบตามที่แพลตฟอร์มส่งมาแล้ว"}`);
  $("empty-state").hidden = true;
  $("media-content").hidden = false;
  $("media-title").textContent = result.title;
  if (isProfile && !result.items.length && !result.next_cursor) MediaI18n.text($("profile-status"), "ยังไม่พบโพสต์ อาจไม่มีโพสต์หรือบัญชีที่เชื่อมต่อยังไม่มีสิทธิ์ดู");
  const kinds = { video: "วิดีโอ", image: "รูปภาพ", carousel: "โพสต์หลายรายการ", profile: `โปรไฟล์ ${result.platform || "Instagram"}` };
  const duration = result.duration ? ` · ${numbers.format(Math.floor(result.duration / 60))}:${String(Math.floor(result.duration % 60)).padStart(2, "0")} นาที` : "";
  MediaI18n.text($("media-meta"), `${kinds[result.type] || "สื่อ"} · ${numbers.format(result.items.length)} รายการ${duration}`);
  const thumbnail = $("thumbnail");
  thumbnail.hidden = true;
  $("thumbnail-fallback").hidden = false;
  thumbnail.onload = () => { thumbnail.hidden = false; $("thumbnail-fallback").hidden = true; };
  thumbnail.onerror = () => { thumbnail.hidden = true; $("thumbnail-fallback").hidden = false; };
  if (result.thumbnail?.startsWith("/thumbnails/")) thumbnail.src = result.thumbnail;
  else thumbnail.removeAttribute("src");
  $("media-list").replaceChildren();
  result.items.forEach((item, index) => {
    const row = document.createElement("article"); row.className = "media-tile"; row.dataset.id = item.id;
    const preview = document.createElement("button"); preview.type = "button"; preview.className = "tile-preview";
    MediaI18n.attr(preview, "aria-label", `${item.type === "post" ? "ดูสื่อในโพสต์" : item.type === "video" ? "เล่นวิดีโอ" : "ดูรูปภาพ"} ${index + 1}`);
    const placeholder = document.createElement("span"); placeholder.className = "tile-placeholder"; MediaI18n.text(placeholder, "กำลังโหลดตัวอย่าง…");
    const image = document.createElement("img"); image.alt = ""; image.loading = "lazy"; image.decoding = "async";
    image.onload = () => { placeholder.hidden = true; image.classList.add("is-loaded"); };
    image.onerror = () => { MediaI18n.text(placeholder, "ไม่มีรูปตัวอย่าง"); };
    if (item.thumbnail?.startsWith("/thumbnails/")) image.src = item.thumbnail;
    else MediaI18n.text(placeholder, "ไม่มีรูปตัวอย่าง");
    preview.append(placeholder, image);
    if (item.type === "video") { const play = document.createElement("span"); play.className = "tile-play"; MediaI18n.text(play, "▶"); play.setAttribute("aria-hidden", "true"); preview.append(play); }
    preview.addEventListener("click", () => item.type === "post" ? openProfilePost(item, preview) : openViewer(item, index, preview));
    row.append(preview);
    const label = document.createElement("label");
    label.className = "tile-selection";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox"; checkbox.checked = previous.has(item.id) ? previous.get(item.id) : true; checkbox.dataset.item = item.id;
    selected.set(item.id, checkbox.checked);
    checkbox.addEventListener("change", () => { selected.set(item.id, checkbox.checked); selectionState(); });
    label.append(checkbox, MediaI18n.label(`${item.type === "post" ? "โพสต์" : item.type === "video" ? "วิดีโอ" : "รูปภาพ"} ${index + 1}`));
    row.append(label);
    if (item.type === "post") {
      const caption = document.createElement("p"); caption.className = "post-caption"; caption.textContent = item.title; row.append(caption);
      const detail = document.createElement("p"); detail.className = "post-detail"; MediaI18n.text(detail, `${numbers.format(item.media_count)} สื่อ${item.has_video ? " · มีวิดีโอ" : " · รูปภาพ"}`); row.append(detail);
    }
    if (item.type === "video") {
      const note = document.createElement("p"); note.className = "quality-note";
      MediaI18n.text(note, "คุณภาพสูงสุดจากต้นทาง"); row.append(note);
      if (item.qualities.some((quality) => quality.id === "mp3")) {
        const audioLabel = document.createElement("label"); audioLabel.className = "audio-choice";
        const audio = document.createElement("input"); audio.type = "checkbox"; audio.dataset.audio = item.id;
        audio.addEventListener("change", () => MediaI18n.text(note, audio.checked ? "เสียง MP3 · 192 kbps" : "คุณภาพสูงสุดจากต้นทาง"));
        audioLabel.append(audio, MediaI18n.label("เสียงอย่างเดียว MP3")); row.append(audioLabel);
      }
    }
    $("media-list").append(row);
  });
  if (result.limits) {
    const limits = result.limits;
    const duration = limits.max_duration_seconds ? `วิดีโอไม่เกิน ${numbers.format(limits.max_duration_seconds / 60)} นาที` : "ความยาววิดีโอไม่จำกัด";
    MediaI18n.text($("limits"), `สูงสุด ${numbers.format(limits.max_file_mb)} MB ต่องาน · ${duration} · ไม่เกิน ${numbers.format(limits.max_items)} รายการ · ไฟล์เก็บไว้ ${numbers.format(limits.ttl_seconds / 60)} นาที`);
  }
  MediaI18n.prune();
  step(1); selectionState();
  openPicker();
}

$("select-all").addEventListener("change", (event) => {
  selected.forEach((_, id) => selected.set(id, event.target.checked));
  document.querySelectorAll("[data-item]").forEach((node) => { node.checked = event.target.checked; });
  selectionState();
});
async function loadProfilePages(all = false) {
  if (media?.type !== "profile" || profileLoading || activeJob || !media.next_cursor) return;
  const current = revision, profileUrl = inspectedUrl;
  const controller = new AbortController(); profileLoading = controller; readAllPosts = all;
  const cursors = new Set();
  MediaI18n.text($("profile-error"), "");
  selectionState();
  try {
    do {
      const cursor = media.next_cursor;
      if (!cursor || cursors.has(cursor)) throw new Error("แพลตฟอร์มส่งหน้าซ้ำ กรุณาลองใหม่ภายหลัง");
      cursors.add(cursor);
      if (cursors.size > 100) throw new Error("อ่านครบขีดจำกัด 100 หน้าแล้ว กรุณาเลือกดาวน์โหลดเป็นชุด");
      MediaI18n.text($("profile-status"), `กำลังอ่านโพสต์เพิ่ม… อ่านแล้ว ${numbers.format(media.items.length)} โพสต์`);
      const page = await api("/info", { method: "POST", body: JSON.stringify({ url: profileUrl, cursor }), signal: controller.signal });
      if (revision !== current || controller.signal.aborted) return;
      const merged = new Map(media.items.map((item) => [item.id, item]));
      page.items.forEach((item) => merged.set(item.id, item));
      if (merged.size > 1000) throw new Error("อ่านครบขีดจำกัด 1,000 โพสต์แล้ว กรุณาเลือกดาวน์โหลดเป็นชุด");
      renderMedia({ ...media, items: [...merged.values()], next_cursor: page.next_cursor }, true);
    } while (readAllPosts && media.next_cursor);
  } catch (issue) {
    if (revision === current && !controller.signal.aborted) { MediaI18n.text($("profile-error"), issue.message); MediaI18n.text($("profile-status"), `เก็บไว้ ${numbers.format(media.items.length)} โพสต์ · อ่านต่อไม่สำเร็จ`); }
  } finally {
    if (profileLoading === controller) {
      profileLoading = null; readAllPosts = false;
      if (controller.signal.aborted && media?.type === "profile") MediaI18n.text($("profile-status"), `หยุดอ่านแล้ว · เก็บไว้ ${numbers.format(media.items.length)} โพสต์`);
      selectionState();
    }
  }
}
$("load-more").addEventListener("click", () => loadProfilePages(false));
$("load-all-posts").addEventListener("click", () => loadProfilePages(true));
$("stop-profile").addEventListener("click", () => { readAllPosts = false; profileLoading?.abort(); });
async function openProfilePost(item, trigger) {
  if (inspection || activeJob || submitting || profileLoading) return;
  const snapshot = { media, selected: new Map(selected), url: inspectedUrl, id: item.id };
  const current = revision, controller = new AbortController(); inspection = controller;
  error(); trigger.setAttribute("aria-busy", "true"); selectionState();
  try {
    const result = await api("/info", { method: "POST", body: JSON.stringify({ url: item.url }), signal: controller.signal });
    if (revision !== current) return;
    closeViewer(false); profileReturn = snapshot; inspectedUrl = result.url || item.url;
    renderMedia(result); $("return-profile-picker").hidden = false;
    $("picker-title").setAttribute("tabindex", "-1"); $("picker-title").focus();
  } catch (issue) {
    if (revision === current) MediaI18n.text($("profile-error"), issue.message);
  } finally {
    if (inspection === controller) { inspection = null; selectionState(); }
    trigger.removeAttribute("aria-busy");
  }
}
function returnToProfile() {
  if (!profileReturn || inspection || activeJob || submitting) return;
  const snapshot = profileReturn; profileReturn = null; closeViewer(false);
  selected.clear(); snapshot.selected.forEach((value, key) => selected.set(key, value));
  inspectedUrl = snapshot.url; renderMedia(snapshot.media, true);
  $("return-profile-picker").hidden = true;
  [...document.querySelectorAll(".media-tile")].find((tile) => tile.dataset.id === snapshot.id)?.querySelector("button")?.focus();
}
$("return-profile").addEventListener("click", returnToProfile);
$("return-profile-picker").addEventListener("click", returnToProfile);
urlInput.addEventListener("input", () => {
  if (picker.open) picker.close();
  revision++;
  setCatState("idle");
  readAllPosts = false; profileLoading?.abort(); profileLoading = null; profileReturn = null;
  inspection?.abort(); inspection = null;
  media = null; inspectedUrl = ""; selected.clear();
  $("media-content").hidden = true; $("empty-state").hidden = false;
  MediaI18n.text($("empty-title"), "เริ่มจากวางลิงก์ที่คุณต้องการบันทึก");
  MediaI18n.text($("empty-detail"), "ตรวจสอบลิงก์เพื่อดูตัวอย่างและเลือกวิดีโอหรือรูปภาพ");
  busy(inspectButton, false); $("media-section").setAttribute("aria-busy", "false");
  step(0); selectionState(); error();
});
form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (event.isComposing || inspection || activeJob) return;
  const url = urlInput.value.trim();
  try {
    const parsed = new URL(url);
    if (!["http:", "https:"].includes(parsed.protocol)) throw new Error();
  } catch { error("กรุณาวางลิงก์ http หรือ https ที่ถูกต้อง", true); return; }
  const current = ++revision;
  profileReturn = null; readAllPosts = false; profileLoading?.abort(); profileLoading = null;
  inspection = new AbortController();
  error(); busy(inspectButton, true);
  $("empty-state").hidden = false; $("media-content").hidden = true;
  setCatState("chewing");
  selectionState();
  $("media-section").setAttribute("aria-busy", "true");
  MediaI18n.text($("empty-title"), "กำลังตรวจสอบลิงก์…");
  MediaI18n.text($("empty-detail"), "บางแพลตฟอร์มอาจใช้เวลาสักครู่");
  try {
    const result = await api("/info", { method: "POST", body: JSON.stringify({ url }), signal: inspection.signal });
    if (revision !== current) return;
    if (result.items?.length) await finishCat(inspection.signal);
    else setCatState("idle");
    if (revision !== current) return;
    inspectedUrl = result.url || url;
    renderMedia(result);
  } catch (issue) {
    if (revision !== current) return;
    setCatState("idle");
    media = null; selected.clear();
    $("media-content").hidden = true; $("empty-state").hidden = false;
    error(issue.message, true);
    MediaI18n.text($("empty-title"), "ยังตรวจสอบลิงก์นี้ไม่ได้");
    MediaI18n.text($("empty-detail"), "ตรวจสอบลิงก์และสิทธิ์ของบัญชีที่ล็อกอิน แล้วกดตรวจสอบอีกครั้ง");
  } finally {
    if (revision === current) {
      inspection = null; busy(inspectButton, false);
      $("media-section").setAttribute("aria-busy", "false"); selectionState();
    }
  }
});
// Enter while committing Thai/other IME text must not submit the form.
urlInput.addEventListener("keydown", (event) => { if (event.key === "Enter" && event.isComposing) event.preventDefault(); });

function lockSelections(locked) {
  urlInput.disabled = locked; inspectButton.disabled = locked;
  document.querySelectorAll("#media-picker input, #media-picker select").forEach((node) => { node.disabled = locked; });
  selectionState();
}
function rememberJob(identifier) {
  try { if (identifier) sessionStorage.setItem("media-job", identifier); else sessionStorage.removeItem("media-job"); } catch { /* Storage may be disabled. */ }
}
async function pollJob() {
  if (polling || !activeJob) return;
  polling = true;
  $("retry-status").hidden = true;
  try {
    while (activeJob) {
      const job = await api(`/jobs/${encodeURIComponent(activeJob)}`);
      const phases = { queued: "กำลังรอคิว", inspecting: "กำลังตรวจสอบสื่ออีกครั้ง", downloading: "กำลังดาวน์โหลด", converting: "กำลังแปลงไฟล์" };
      if (job.status === "completed") {
        $("progress").value = 100;
        MediaI18n.text($("job-status"), "ดาวน์โหลดเสร็จแล้ว — พร้อมบันทึกไฟล์");
        $("file-link").href = job.file_url; $("file-link").download = job.filename;
        $("file-link").hidden = false;
        activeJob = null; rememberJob(null); lockSelections(false); break;
      }
      if (job.status === "failed") {
        error(job.error?.message || "ดาวน์โหลดไม่สำเร็จ กรุณาลองใหม่");
        MediaI18n.text($("job-status"), "ดาวน์โหลดไม่สำเร็จ — เลือกรายการแล้วลองใหม่ได้");
        $("progress").value = 0;
        activeJob = null; rememberJob(null); lockSelections(false); break;
      }
      const percent = job.progress || 0;
      MediaI18n.text($("job-status"), `${phases[job.phase] || "กำลังทำงาน"}${percent > 0 ? ` ${numbers.format(percent)}%` : "…"}`);
      if (percent > 0) $("progress").value = percent; else $("progress").removeAttribute("value");
      await new Promise((resolve) => setTimeout(resolve, 1200));
    }
  } catch (issue) {
    error(issue.message);
    if (issue.status === 404) {
      activeJob = null; rememberJob(null); lockSelections(false);
      MediaI18n.text($("job-status"), "งานหมดอายุหรือระบบถูกเริ่มใหม่ กรุณาตรวจสอบลิงก์อีกครั้ง");
      $("progress").value = 0;
    } else {
      MediaI18n.text($("job-status"), "ยังตรวจสอบสถานะไม่ได้ งานอาจยังทำงานอยู่");
      $("retry-status").disabled = false;
      $("retry-status").hidden = false;
    }
  } finally { polling = false; }
}
$("retry-status").addEventListener("click", () => { error(); pollJob(); });
downloadButton.addEventListener("click", async () => {
  if (!media || activeJob || submitting || profileLoading) return;
  const selections = media.items.filter((item) => selected.get(item.id)).map((item) => {
    const value = { id: item.id };
    if (item.type === "video") value.quality = [...document.querySelectorAll("[data-audio]")].find((node) => node.dataset.audio === item.id)?.checked ? "mp3" : "best";
    return value;
  });
  if (!selections.length) { error("กรุณาเลือกอย่างน้อยหนึ่งรายการ"); return; }
  if (selections.length > (media.limits?.max_items || 100)) { error("เลือกเกินจำนวนที่กำหนด กรุณาแบ่งดาวน์โหลดเป็นชุด"); return; }
  submitting = true; error(); busy(downloadButton, true); lockSelections(true);
  $("file-link").hidden = true; $("retry-status").hidden = true;
  MediaI18n.text($("job-status"), "กำลังสร้างงาน…"); $("progress").removeAttribute("value");
  try {
    const result = await api("/download", { method: "POST", body: JSON.stringify({ url: inspectedUrl, selections, video_format: $("video-format").value }) });
    activeJob = result.job_id; rememberJob(activeJob); step(2); pollJob();
  } catch (issue) {
    error(issue.message + " หากการเชื่อมต่อขาด งานอาจถูกสร้างแล้ว กรุณาตรวจสอบก่อนลองใหม่");
    MediaI18n.text($("job-status"), "ยังยืนยันการสร้างงานไม่ได้"); $("progress").value = 0;
  } finally { submitting = false; busy(downloadButton, false); lockSelections(!!activeJob); }
});
try { activeJob = sessionStorage.getItem("media-job"); } catch { /* Storage is optional. */ }
if (activeJob && /^[a-f0-9]{32}$/.test(activeJob)) { step(2); lockSelections(true); pollJob(); }
else { activeJob = null; rememberJob(null); }

function toggleLanguage() { MediaI18n.setLanguage(MediaI18n.language === "th" ? "en" : "th"); }
$("language-toggle").addEventListener("click", toggleLanguage);
$("picker-language-toggle").addEventListener("click", toggleLanguage);
$("language-toggle").disabled = false;
$("picker-language-toggle").disabled = false;


// Pointer visuals are decorative: never intercept focus, clicks, selection or drag.
(() => {
  const cursor = $("paw-cursor"), root = document.documentElement;
  const fine = matchMedia("(any-pointer: fine) and (any-hover: hover)");
  const contrast = matchMedia("(forced-colors: active)");
  if (!cursor.showPopover) return; // Keep native SVG paw cursors as a safe fallback.
  let point = null, visible = false;
  const waitingMedia = new Set();
  function allowed() { return fine.matches && !contrast.matches; }
  function hide() {
    visible = false; delete root.dataset.pawCursor;
    cursor.dataset.visible = "false"; cursor.dataset.pressed = "false";
  }
  function raise() {
    if (!visible || !allowed()) return;
    try {
      if (cursor.matches(":popover-open")) cursor.hidePopover();
      cursor.showPopover();
    } catch { hide(); }
  }
  function update() {
    if (!visible || !point || !allowed()) return;
    const target = document.elementFromPoint(point.x, point.y);
    let kind = "default";
    const preview = target?.closest(".tile-preview");
    const previewImage = preview?.querySelector("img");
    if (root.dataset.appBusy === "true" || waitingMedia.size || target?.closest('[aria-busy="true"]') || (previewImage?.getAttribute("src") && !previewImage.complete)) kind = "busy";
    else if (target?.closest(":disabled, [aria-disabled='true']")) kind = "disabled";
    else if (target?.closest('input:not([type="checkbox"]):not([type="button"]), textarea, [contenteditable="true"]')) kind = "text";
    else if (target?.closest('button, a[href], label, select, input[type="checkbox"], video, [role="button"]')) kind = "pointer";
    cursor.dataset.kind = kind;
  }
  cursor.addEventListener("toggle", () => { if (visible && !cursor.matches(":popover-open")) hide(); });
  document.addEventListener("pointermove", event => {
    if (event.pointerType === "touch" || !allowed()) { hide(); return; }
    point = { x: event.clientX, y: event.clientY };
    if (!document.hasFocus()) { hide(); return; }
    if (!visible) {
      visible = true; raise();
      if (!visible) return;
      root.dataset.pawCursor = "on"; cursor.dataset.visible = "true";
    }
    if (!cursor.matches(":popover-open")) { raise(); if (!visible) return; }
    cursor.style.setProperty("--paw-x", point.x + "px"); cursor.style.setProperty("--paw-y", point.y + "px");
    update();
  }, { passive: true });
  document.addEventListener("pointerdown", event => {
    if (event.pointerType === "touch") hide();
    else cursor.dataset.pressed = "true";
  }, { passive: true });
  document.addEventListener("pointerup", () => { cursor.dataset.pressed = "false"; }, { passive: true });
  document.addEventListener("pointercancel", hide, { passive: true });
  document.addEventListener("pointerout", event => { if (!event.relatedTarget) hide(); }, { passive: true });
  document.addEventListener("contextmenu", hide);
  window.addEventListener("blur", hide);
  document.addEventListener("visibilitychange", () => { if (document.hidden) hide(); });
  fine.addEventListener("change", () => { if (!allowed()) hide(); });
  contrast.addEventListener("change", () => { if (!allowed()) hide(); });
  document.addEventListener("fullscreenchange", raise);
  document.addEventListener("load", update, true); document.addEventListener("error", update, true);
  document.addEventListener("waiting", event => { if (event.target instanceof HTMLMediaElement) { waitingMedia.add(event.target); update(); } }, true);
  for (const name of ["playing", "pause", "ended", "error", "emptied"]) {
    document.addEventListener(name, event => { waitingMedia.delete(event.target); update(); }, true);
  }
  new MutationObserver(update).observe(root, { attributes: true, subtree: true, attributeFilter: ["data-app-busy", "aria-busy", "disabled"] });
  window.PawCursor = { raise };
})();
