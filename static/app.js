"use strict";

/* =====================================================================
   ฟังก์ชันที่ใช้ร่วมกันทุกหน้า
   ===================================================================== */

const SVG_NS = "http://www.w3.org/2000/svg";
const $ = (selector, root = document) => root.querySelector(selector);

/** สร้าง element แบบปลอดภัย (ใช้ textContent ไม่ใช้ innerHTML) */
function h(tag, props = {}, ...children) {
    const element = document.createElement(tag);
    for (const [key, value] of Object.entries(props || {})) {
        if (value === null || value === undefined || value === false) continue;
        if (key === "class") element.className = value;
        else if (key === "text") element.textContent = value;
        else if (key.startsWith("on")) element.addEventListener(key.slice(2), value);
        else element.setAttribute(key, value === true ? "" : value);
    }
    for (const child of children.flat()) {
        if (child === null || child === undefined || child === false) continue;
        element.append(child instanceof Node ? child : document.createTextNode(String(child)));
    }
    return element;
}

function icon(name, className = "icon") {
    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("class", className);
    const use = document.createElementNS(SVG_NS, "use");
    use.setAttribute("href", `#${name}`);
    svg.append(use);
    return svg;
}

/** เรียก API แล้วคืน JSON (ถ้าผิดพลาดจะ throw Error ข้อความภาษาไทย) */
async function api(url, options = {}) {
    const request = { cache: "no-store", ...options };
    if (request.body !== undefined && typeof request.body !== "string") {
        request.body = JSON.stringify(request.body);
        request.headers = { "Content-Type": "application/json" };
    }
    let response;
    try {
        response = await fetch(url, request);
    } catch {
        throw new Error("เชื่อมต่อระบบไม่ได้ — ตรวจสอบว่า Raspberry Pi ยังทำงานอยู่");
    }
    let data = null;
    try { data = await response.json(); } catch { /* ไม่ใช่ JSON */ }
    if (!response.ok) {
        const error = new Error((data && data.message) || `เกิดข้อผิดพลาด (${response.status})`);
        error.data = data;
        error.status = response.status;
        throw error;
    }
    return data;
}

let toastTimer = null;
function toast(message, kind = "") {
    const element = $("#toast");
    if (!element) return;
    element.className = `toast ${kind}`;
    element.replaceChildren(
        icon(kind === "error" ? "i-alert" : "i-check"),
        h("span", { text: message }),
    );
    element.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { element.hidden = true; }, kind === "error" ? 6000 : 3500);
}

/* ---------- เวลา (ใช้เวลาจากเครื่อง Pi เป็นหลัก แสดงเป็นเวลาไทย) ---------- */

const Clock = { offsetMs: 0, utcOffsetHours: 7 };

function syncClock(overview) {
    Clock.offsetMs = overview.server_epoch * 1000 - Date.now();
    Clock.utcOffsetHours = overview.utc_offset_hours;
}

function serverNowEpoch() {
    return (Date.now() + Clock.offsetMs) / 1000;
}

function clockText() {
    const local = new Date(Date.now() + Clock.offsetMs + Clock.utcOffsetHours * 3600 * 1000);
    const pad = (value) => String(value).padStart(2, "0");
    return `${pad(local.getUTCHours())}:${pad(local.getUTCMinutes())}:${pad(local.getUTCSeconds())} น.`;
}

function relativeTime(epoch) {
    if (!epoch) return "";
    const seconds = Math.max(0, serverNowEpoch() - epoch);
    if (seconds < 45) return "เมื่อสักครู่";
    if (seconds < 3600) return `${Math.round(seconds / 60)} นาทีที่แล้ว`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)} ชม. ที่แล้ว`;
    return `${Math.floor(seconds / 86400)} วันที่แล้ว`;
}

const percent = (value) => `${Math.round((value || 0) * 100)}%`;
const formatNumber = (value) => new Intl.NumberFormat("th-TH").format(value || 0);

/* ---------- สถานะอุปกรณ์ -> ข้อความภาษาไทย ---------- */

function chip(kind, text) {
    return h("span", { class: `chip chip-${kind}` }, h("span", { class: "dot" }), text);
}

function cameraState(status) {
    switch (status) {
        case "Connected": return { kind: "ok", text: "เชื่อมต่อแล้ว" };
        case "Connecting": return { kind: "warn", text: "กำลังเชื่อมต่อ…" };
        case "Disconnected": return { kind: "danger", text: "ไม่ได้เชื่อมต่อ" };
        default: return { kind: "muted", text: "ปิดใช้งาน" };
    }
}

function pumpState(pump) {
    if (!pump) return { kind: "muted", box: "", text: "ปิดใช้งาน", detail: "จุดนี้ปิดใช้งานอยู่" };
    const duration = pump.duration_s ? `พ่นครั้งละ ${pump.duration_s} วินาที` : "";
    if (pump.pump_on) {
        return { kind: "run", box: "run", text: "กำลังพ่นยา", detail: `อีกประมาณ ${pump.remaining_s} วินาที` };
    }
    if (pump.online === false) {
        return { kind: "danger", box: "danger", text: "ไม่ตอบสนอง", detail: "ตรวจสอบไฟเลี้ยงและ WiFi ของ ESP32" };
    }
    if (pump.online === null) {
        return { kind: "muted", box: "", text: "กำลังตรวจสอบ…", detail: "รอการตอบกลับจาก ESP32" };
    }
    return { kind: "ok", box: "ok", text: "พร้อมทำงาน", detail: duration || "รอคำสั่งพ่น" };
}

const SOURCE_TEXT = { auto: "พ่นอัตโนมัติ", manual: "สั่งพ่นจากหน้าเว็บ", stop: "สั่งหยุดปั๊ม" };
const OUTCOME_TEXT = {
    pump_on: "ปั๊มทำงาน",
    busy: "ปั๊มทำงานอยู่แล้ว",
    stopped: "หยุดแล้ว",
    no_reply: "ESP32 ไม่ตอบสนอง",
    unknown: "ไม่ทราบผล",
};

function sprayOutcomeChip(event) {
    if (event.outcome === "pump_on") return chip("run", `พ่น${event.duration_ms ? ` ${event.duration_ms / 1000} วิ` : "แล้ว"}`);
    if (event.outcome === "no_reply") return chip("danger", "ไม่ตอบสนอง");
    if (event.outcome === "stopped") return chip("warn", OUTCOME_TEXT.stopped);
    return chip("muted", OUTCOME_TEXT[event.outcome] || event.outcome);
}

/** แปลงเหตุการณ์ (ตรวจพบ/พ่น) เป็นแถวในรายการ */
function eventRow(event) {
    let iconName, iconClass, title, detail;
    if (event.kind === "detection") {
        iconName = "i-leaf"; iconClass = "detect";
        title = `พบผักตบชวา #${event.track_id}`;
        detail = `ความมั่นใจ ${percent(event.confidence)}`;
    } else if (event.source === "stop") {
        iconName = "i-stop"; iconClass = "stop";
        title = "สั่งหยุดปั๊ม";
        detail = OUTCOME_TEXT[event.outcome] || event.outcome;
    } else if (event.outcome === "no_reply") {
        iconName = "i-alert"; iconClass = "fail";
        title = "สั่งพ่นไม่สำเร็จ";
        detail = "ESP32 ไม่ตอบสนอง";
    } else {
        iconName = "i-drop"; iconClass = "spray";
        title = SOURCE_TEXT[event.source] || "พ่นยา";
        detail = event.outcome === "pump_on" && event.duration_ms
            ? `ปั๊มทำงาน ${event.duration_ms / 1000} วินาที`
            : (OUTCOME_TEXT[event.outcome] || event.outcome);
    }
    return h("div", { class: "event" },
        h("span", { class: `event-icon ${iconClass}` }, icon(iconName)),
        h("div", { class: "event-text" }, h("strong", { text: title }), h("small", { text: detail })),
        h("div", { class: "event-time" }, event.time, h("br"), relativeTime(event.epoch)),
    );
}

function mergeEvents(stats, cameraId = null, limit = 8) {
    const detections = stats.recent_detections.map((e) => ({ ...e, kind: "detection" }));
    const sprays = stats.recent_sprays.map((e) => ({ ...e, kind: "spray" }));
    return [...detections, ...sprays]
        .filter((e) => cameraId === null || e.camera_id === cameraId)
        .sort((a, b) => b.epoch - a.epoch)
        .slice(0, limit);
}

function renderAlerts(container, alerts) {
    const iconFor = { danger: "i-alert", warning: "i-alert", info: "i-info" };
    container.replaceChildren(...alerts.map((alert) =>
        h("div", { class: `alert alert-${alert.level}` }, icon(iconFor[alert.level] || "i-info"), h("span", { text: alert.text })),
    ));
}

/* ---------- เปิด/ปิดพ่นอัตโนมัติ + หยุดฉุกเฉิน (ใช้ได้ทุกหน้า) ---------- */

async function setAutoSpray(enabled) {
    if (enabled === false && !confirm("ปิดการพ่นอัตโนมัติ?\nระบบจะยังตรวจจับและแสดงภาพ แต่จะไม่สั่งพ่นเอง")) {
        return null;
    }
    try {
        const result = await api("/api/auto_spray", { method: "POST", body: { enabled } });
        toast(result.auto_spray ? "เปิดการพ่นอัตโนมัติแล้ว" : "ปิดการพ่นอัตโนมัติแล้ว", "success");
        return result.auto_spray;
    } catch (error) {
        toast(error.message, "error");
        return null;
    }
}

async function emergencyStop() {
    if (!confirm("หยุดฉุกเฉิน?\n• หยุดปั๊มทุกจุดทันที\n• ปิดการพ่นอัตโนมัติ (ต้องเปิดใหม่เองเมื่อปลอดภัย)")) return;
    try {
        const result = await api("/api/emergency_stop", { method: "POST" });
        toast(result.message, "success");
    } catch (error) {
        toast(error.message, "error");
    }
}

/** ผูกสวิตช์พ่นอัตโนมัติ: toggle = <input type=checkbox>, label = element แสดงข้อความ */
function bindAutoSprayToggle(toggle, label) {
    toggle.addEventListener("change", async () => {
        const wanted = toggle.checked;
        toggle.disabled = true;
        const result = await setAutoSpray(wanted);
        toggle.disabled = false;
        if (result === null) toggle.checked = !wanted;
        else showAutoSpray(toggle, label, result);
    });
}

function showAutoSpray(toggle, label, enabled) {
    if (!toggle.disabled) toggle.checked = enabled;
    if (label) label.textContent = enabled ? "เปิดอยู่ — พ่นเมื่อพบผักตบ" : "ปิดอยู่ — ตรวจจับอย่างเดียว";
}

/* ---------- Sidebar ---------- */

function updateSidebar(overview) {
    const status = $("#sideAutoSpray");
    if (!status) return;
    status.className = `side-status ${overview.auto_spray ? "on" : "off"}`;
    status.replaceChildren(
        h("span", { class: "dot" }),
        h("span", { text: overview.auto_spray ? "พ่นอัตโนมัติ: เปิด" : "พ่นอัตโนมัติ: ปิด" }),
    );
}

/** ดึงสถานะระบบซ้ำ ๆ แล้วเรียก callback(data) */
function pollOverview(callback, intervalMs = 2000) {
    async function tick() {
        try {
            const data = await api("/api/overview");
            syncClock(data);
            updateSidebar(data);
            callback(data, null);
        } catch (error) {
            callback(null, error);
        } finally {
            setTimeout(tick, intervalMs);
        }
    }
    tick();
}

function pollStats(callback, intervalMs = 5000) {
    async function tick() {
        try {
            callback(await api("/api/stats"), null);
        } catch (error) {
            callback(null, error);
        } finally {
            setTimeout(tick, intervalMs);
        }
    }
    tick();
}

setInterval(() => {
    const clock = $("#sideClock");
    if (clock) clock.textContent = clockText();
}, 1000);
