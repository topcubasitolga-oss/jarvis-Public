/**
 * JARVIS KÖPRÜSÜ — Google Apps Script web uygulaması
 * Jarvis'in (ElevenLabs ajanı) Gmail, Takvim, Drive, Sheets ve Notion'a ulaşmasını sağlar.
 *
 * Kurulum: script.google.com → yeni proje → bu kodu yapıştır → Dağıt → Yeni dağıtım → Web uygulaması
 *   Çalıştıran: Ben · Erişim: Herkes → Dağıt → izinleri ver → /exec adresini kopyala.
 * Notion için: Proje ayarları → Script Properties → NOTION_TOKEN = ntn_... (notion.so/my-integrations)
 *
 * İstek biçimi (POST JSON ya da GET sorgu): { key, action, ...parametreler }
 * Her cevap JSON'dur. Hiçbir eylem e-posta GÖNDERMEZ; yalnızca taslak oluşturur.
 */
var JARVIS_KEY = "BURAYA_UZUN_RASTGELE_BIR_ANAHTAR"; // python -c "import secrets; print(secrets.token_urlsafe(24))"
var TZ = "Europe/Istanbul";
var SHEETS = { durum_defteri: "Jarvis Durum Defteri", tt_robotics: "Jarvis TT Robotics" };

function doPost(e) { return handle(parseParams(e)); }
function doGet(e) { return handle(parseParams(e)); }

function parseParams(e) {
  var p = {};
  if (e && e.parameter) for (var k in e.parameter) p[k] = e.parameter[k];
  if (e && e.postData && e.postData.contents) {
    try { var body = JSON.parse(e.postData.contents); for (var j in body) p[j] = body[j]; } catch (err) {}
  }
  return p;
}

function json(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

function handle(p) {
  if (!p.key || p.key !== JARVIS_KEY) return json({ error: "Geçersiz anahtar" });
  var action = String(p.action || "").toLowerCase();
  try {
    switch (action) {
      case "ping": return json({ ok: true, time: fmt(new Date()) });
      case "mail_inbox": return json(mailInbox(p));
      case "mail_search": return json(mailSearch(p));
      case "mail_read": return json(mailRead(p));
      case "mail_draft_reply": return json(mailDraftReply(p));
      case "calendar_upcoming": return json(calendarUpcoming(p));
      case "drive_search": return json(driveSearch(p));
      case "drive_read": return json(driveRead(p));
      case "sheet_query": return json(sheetQuery(p));
      case "notion_search": return json(notionSearch(p));
      case "notion_read": return json(notionRead(p));
      case "memory_recall": return json(memoryRecall(p));
      case "memory_save": return json(memorySave(p));
      case "post_call": return json(postCall(p));
      default: return json({ error: "Bilinmeyen eylem: " + action, actions: ["mail_inbox", "mail_search", "mail_read", "mail_draft_reply", "calendar_upcoming", "drive_search", "drive_read", "sheet_query", "notion_search", "notion_read", "memory_recall", "memory_save", "post_call"] });
    }
  } catch (err) {
    return json({ error: String(err && err.message || err) });
  }
}

// ---------------------------------------------------------------- yardımcılar
function fmt(d) { return Utilities.formatDate(d, TZ, "dd.MM.yyyy HH:mm"); }
function clampInt(v, def, min, max) { var n = parseInt(v, 10); if (isNaN(n)) n = def; return Math.max(min, Math.min(max, n)); }
function truthy(v, def) { if (v === undefined || v === null || v === "") return def; return String(v).toLowerCase() !== "false" && v !== false && v !== 0 && String(v) !== "0"; }
function clip(s, n) { s = String(s || ""); return s.length > n ? s.slice(0, n) + " […]" : s; }

// Gmail'e bağlı posta kutuları: Jarvis "hesap" adıyla filtreler, cevap taslağı doğru adresten çıkar.
var ACCOUNTS = {
  gmail: "topcubasitolga@gmail.com",
  hotmail: "tolga.121@hotmail.com",
  "29mayis": "ttopcubasi@29mayis.edu.tr"
};
function accountOf(m) {
  var hay = ((m.getTo() || "") + " " + (m.getCc() || "") + " " + (m.getHeader("Delivered-To") || "") + " " + (m.getHeader("X-Forwarded-To") || "")).toLowerCase();
  for (var k in ACCOUNTS) if (k !== "gmail" && hay.indexOf(ACCOUNTS[k].toLowerCase()) >= 0) return k;
  return "gmail";
}
function accountQuery(account) {
  var k = String(account || "").toLowerCase().replace(/\s/g, "");
  if (k === "universite" || k === "üniversite" || k === "okul" || k === "kurum") k = "29mayis";
  if (k === "outlook") k = "hotmail";
  if (!k || k === "hepsi" || k === "all") return "";
  if (k === "gmail") return " -to:" + ACCOUNTS.hotmail + " -to:" + ACCOUNTS["29mayis"];
  if (ACCOUNTS[k]) return " to:" + ACCOUNTS[k];
  return "";
}

function msgSummary(m) {
  return {
    id: m.getId(),
    account: accountOf(m),
    from: m.getFrom(),
    subject: m.getSubject() || "(konu yok)",
    date: fmt(m.getDate()),
    unread: m.isUnread(),
    snippet: clip(m.getPlainBody().replace(/\s+/g, " ").trim(), 180)
  };
}

function searchMessages(query, limit) {
  var threads = GmailApp.search(query, 0, limit);
  var out = [];
  for (var i = 0; i < threads.length; i++) {
    var msgs = threads[i].getMessages();
    out.push(msgSummary(msgs[msgs.length - 1]));
  }
  return out;
}

// ---------------------------------------------------------------- Gmail
function mailInbox(p) {
  var days = clampInt(p.days, 1, 1, 30), limit = clampInt(p.limit, 10, 1, 25);
  var unread = truthy(p.unread_only, true);
  var q = "in:inbox newer_than:" + days + "d -category:promotions -category:social" + (unread ? " is:unread" : "") + accountQuery(p.account);
  var list = searchMessages(q, limit);
  return { count: list.length, window_days: days, unread_only: unread, account: p.account || "hepsi", messages: list };
}

function mailSearch(p) {
  if (!p.query) return { error: "query gerekli" };
  var list = searchMessages(String(p.query) + accountQuery(p.account), clampInt(p.limit, 10, 1, 25));
  return { count: list.length, query: p.query, account: p.account || "hepsi", messages: list };
}

function mailRead(p) {
  if (!p.message_id) return { error: "message_id gerekli" };
  var m = GmailApp.getMessageById(String(p.message_id));
  var s = msgSummary(m);
  s.to = m.getTo();
  s.body = clip(m.getPlainBody().replace(/\r/g, "").replace(/\n{3,}/g, "\n\n").trim(), 6000);
  s.attachments = m.getAttachments().map(function (a) { return a.getName(); });
  return s;
}

function mailDraftReply(p) {
  if (!p.message_id || !p.body) return { error: "message_id ve body gerekli" };
  var m = GmailApp.getMessageById(String(p.message_id));
  // İleti hotmail/29 Mayıs adresine gelmişse ve o adres Gmail'de "farklı gönder" olarak tanımlıysa taslak o adresten çıkar.
  var acc = accountOf(m), opts = {};
  if (acc !== "gmail") {
    var aliases = GmailApp.getAliases().map(function (a) { return a.toLowerCase(); });
    if (aliases.indexOf(ACCOUNTS[acc].toLowerCase()) >= 0) opts.from = ACCOUNTS[acc];
  }
  var d = m.createDraftReply(String(p.body), opts);
  return { status: "taslak_hazir", draft_id: d.getId(), to: m.getReplyTo() || m.getFrom(), subject: "Re: " + m.getSubject(),
           from: opts.from || ACCOUNTS.gmail, account: acc,
           note: "Gönderilmedi. Gmail > Taslaklar klasöründe; göndermeyi Tolga Bey yapar." };
}

// ---------------------------------------------------------------- Takvim
function calendarUpcoming(p) {
  var days = clampInt(p.days, 1, 1, 31);
  var now = new Date();
  var start = new Date(Utilities.formatDate(now, TZ, "yyyy-MM-dd") + "T00:00:00+03:00");
  var end = new Date(start.getTime() + days * 86400000);
  var events = CalendarApp.getDefaultCalendar().getEvents(start, end);
  var out = events.slice(0, 40).map(function (ev) {
    var allDay = ev.isAllDayEvent();
    return {
      title: ev.getTitle() || "(başlıksız)",
      when: allDay ? Utilities.formatDate(ev.getAllDayStartDate(), TZ, "dd.MM.yyyy") + " (tüm gün)"
                   : fmt(ev.getStartTime()) + "–" + Utilities.formatDate(ev.getEndTime(), TZ, "HH:mm"),
      location: ev.getLocation() || "",
      guests: ev.getGuestList().slice(0, 6).map(function (g) { return g.getEmail(); })
    };
  });
  return { count: out.length, from: Utilities.formatDate(start, TZ, "dd.MM.yyyy"), days: days, events: out };
}

// ---------------------------------------------------------------- Drive
function driveSearch(p) {
  if (!p.query) return { error: "query gerekli" };
  var q = String(p.query).replace(/'/g, "\\'");
  var limit = clampInt(p.limit, 10, 1, 25);
  var it = DriveApp.searchFiles("(title contains '" + q + "' or fullText contains '" + q + "') and trashed = false");
  var out = [];
  while (it.hasNext() && out.length < limit) {
    var f = it.next();
    out.push({ id: f.getId(), name: f.getName(), type: f.getMimeType().replace("application/vnd.google-apps.", "google-"), modified: fmt(f.getLastUpdated()), url: f.getUrl() });
  }
  out.sort(function (a, b) { return a.modified < b.modified ? 1 : -1; });
  return { count: out.length, query: p.query, files: out };
}

function driveRead(p) {
  if (!p.file_id) return { error: "file_id gerekli" };
  var f = DriveApp.getFileById(String(p.file_id));
  var mime = f.getMimeType(), text = "";
  if (mime === "application/vnd.google-apps.document") text = DocumentApp.openById(f.getId()).getBody().getText();
  else if (mime === "application/vnd.google-apps.spreadsheet") {
    var sh = SpreadsheetApp.openById(f.getId()).getSheets()[0];
    text = sh.getDataRange().getValues().slice(0, 100).map(function (r) { return r.join(" | "); }).join("\n");
  } else if (/^text\//.test(mime) || mime === "application/json") text = f.getBlob().getDataAsString();
  else return { name: f.getName(), type: mime, note: "Bu dosya türünün metni okunamıyor; bağlantısı: " + f.getUrl() };
  return { name: f.getName(), type: mime, url: f.getUrl(), text: clip(text.trim(), 8000) };
}

// ---------------------------------------------------------------- Sheets (Durum Defteri, TT Robotics)
function sheetQuery(p) {
  var key = String(p.sheet || "").toLowerCase();
  var name = SHEETS[key];
  if (!name) return { error: "Tanımsız sheet: " + key, valid: Object.keys(SHEETS) };
  var files = DriveApp.getFilesByName(name);
  if (!files.hasNext()) return { error: "'" + name + "' adlı tablo Drive'da yok. Önce oluşturun." };
  var ss = SpreadsheetApp.open(files.next());
  var sh = p.tab ? ss.getSheetByName(String(p.tab)) : ss.getSheets()[0];
  if (!sh) return { error: "Sekme bulunamadı: " + p.tab, tabs: ss.getSheets().map(function (s) { return s.getName(); }) };
  var values = sh.getDataRange().getValues();
  if (values.length < 2) return { sheet: key, tab: sh.getName(), count: 0, rows: [] };
  var header = values[0].map(function (h) { return String(h).trim(); });
  var needle = String(p.search || "").toLowerCase().trim();
  var rows = [];
  for (var i = 1; i < values.length; i++) {
    var r = values[i];
    if (!r.some(function (c) { return String(c).trim(); })) continue;
    var obj = {};
    for (var j = 0; j < header.length; j++) {
      var c = r[j];
      obj[header[j] || ("col" + (j + 1))] = (c instanceof Date) ? Utilities.formatDate(c, TZ, "dd.MM.yyyy") : String(c);
    }
    if (needle && Object.keys(obj).map(function (k) { return obj[k]; }).join(" ").toLowerCase().indexOf(needle) < 0) continue;
    rows.push(obj);
  }
  return { sheet: key, tab: sh.getName(), count: rows.length, rows: rows.slice(0, 120), truncated: rows.length > 120 };
}

// ---------------------------------------------------------------- Hafıza (Drive'da "Jarvis Hafıza" tablosu)
var MEMORY_SHEET = "Jarvis Hafıza";
function memoryBook() {
  var files = DriveApp.getFilesByName(MEMORY_SHEET);
  var ss = files.hasNext() ? SpreadsheetApp.open(files.next()) : SpreadsheetApp.create(MEMORY_SHEET);
  var notes = ss.getSheetByName("Notlar") || ss.insertSheet("Notlar");
  if (notes.getLastRow() === 0) notes.appendRow(["Tarih", "Konu", "Not"]);
  var calls = ss.getSheetByName("Konuşmalar") || ss.insertSheet("Konuşmalar");
  if (calls.getLastRow() === 0) calls.appendRow(["Tarih", "Süre (sn)", "Özet", "Döküm", "Konuşma ID"]);
  var first = ss.getSheets()[0];
  if (first.getName() !== "Notlar" && first.getName() !== "Konuşmalar" && first.getLastRow() === 0) ss.deleteSheet(first);
  return { ss: ss, notes: notes, calls: calls };
}
function memorySave(p) {
  if (!p.note) return { error: "note gerekli" };
  var b = memoryBook();
  b.notes.appendRow([fmt(new Date()), String(p.topic || "genel"), String(p.note)]);
  return { status: "kaydedildi", topic: p.topic || "genel", note: p.note };
}
function memoryRecall(p) {
  var b = memoryBook();
  var limit = clampInt(p.limit, 12, 1, 40);
  var needle = String(p.query || "").toLowerCase().trim();
  function pick(sheet, cols) {
    var v = sheet.getDataRange().getValues().slice(1);
    var out = [];
    for (var i = v.length - 1; i >= 0 && out.length < limit; i--) {
      var row = cols.map(function (c) { return String(v[i][c] instanceof Date ? fmt(v[i][c]) : v[i][c]); });
      if (needle && row.join(" ").toLowerCase().indexOf(needle) < 0) continue;
      out.push(row);
    }
    return out;
  }
  return {
    notes: pick(b.notes, [0, 1, 2]).map(function (r) { return { date: r[0], topic: r[1], note: r[2] }; }),
    past_conversations: pick(b.calls, [0, 2]).map(function (r) { return { date: r[0], summary: clip(r[1], 600) }; }),
    hint: "En yeni kayıt en üstte."
  };
}
// ElevenLabs post-call webhook hedefi: .../exec?key=...&action=post_call  (gövde ElevenLabs'in yolladığı JSON)
function postCall(p) {
  var d = p.data || p;
  var transcript = (d.transcript || []).map(function (t) { return (t.role === "agent" ? "JARVİS: " : "TOLGA: ") + (t.message || ""); }).join("\n");
  var summary = (d.analysis && (d.analysis.transcript_summary || d.analysis.call_summary_title)) || clip(transcript, 400);
  if (!transcript.trim()) return { status: "bos_konusma" };
  var b = memoryBook();
  b.calls.appendRow([fmt(new Date()), d.metadata && d.metadata.call_duration_secs || "", summary, clip(transcript, 20000), d.conversation_id || ""]);
  return { status: "kaydedildi" };
}

// ---------------------------------------------------------------- Notion
function notionToken() {
  var t = PropertiesService.getScriptProperties().getProperty("NOTION_TOKEN");
  if (!t) throw new Error("Notion bağlı değil: Script Properties'e NOTION_TOKEN ekleyin.");
  return t;
}
function notionFetch(path, method, payload) {
  var res = UrlFetchApp.fetch("https://api.notion.com/v1" + path, {
    method: method || "get", muteHttpExceptions: true, contentType: "application/json",
    headers: { Authorization: "Bearer " + notionToken(), "Notion-Version": "2022-06-28" },
    payload: payload ? JSON.stringify(payload) : undefined
  });
  var data = JSON.parse(res.getContentText() || "{}");
  if (res.getResponseCode() >= 300) throw new Error("Notion: " + (data.message || res.getResponseCode()));
  return data;
}
function richText(arr) { return (arr || []).map(function (t) { return t.plain_text; }).join(""); }
function notionTitle(obj) {
  if (obj.object === "database") return richText(obj.title);
  var props = obj.properties || {};
  for (var k in props) if (props[k].type === "title") return richText(props[k].title);
  return "(başlıksız)";
}
function notionSearch(p) {
  var payload = { page_size: clampInt(p.limit, 10, 1, 25), sort: { direction: "descending", timestamp: "last_edited_time" } };
  if (p.query) payload.query = String(p.query);
  var data = notionFetch("/search", "post", payload);
  return { count: data.results.length, results: data.results.map(function (r) { return { id: r.id, type: r.object, title: notionTitle(r), edited: fmt(new Date(r.last_edited_time)), url: r.url }; }) };
}
function notionRead(p) {
  if (!p.page_id) return { error: "page_id gerekli" };
  var id = String(p.page_id);
  var data = notionFetch("/blocks/" + id + "/children?page_size=100");
  var lines = [];
  (data.results || []).forEach(function (b) {
    var t = b.type, v = b[t] || {};
    var text = richText(v.rich_text || v.text || []);
    if (!text && t === "child_page") text = "[Alt sayfa] " + v.title;
    if (t === "to_do") text = (v.checked ? "[x] " : "[ ] ") + text;
    if (/^heading/.test(t)) text = "## " + text;
    if (/bulleted|numbered/.test(t)) text = "• " + text;
    if (text) lines.push(text);
  });
  return { page_id: id, text: clip(lines.join("\n"), 8000), has_more: !!data.has_more };
}
