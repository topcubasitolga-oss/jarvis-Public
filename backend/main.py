"""
Jarvis backend — ElevenLabs ajanının "elleri".

ElevenLabs webhook araçları bu sunucuya POST atar; sunucu Gmail / Takvim / Sheets'e bakıp
kısa ve LLM'in okuyacağı biçimde JSON döner. Ayrıca özel (private) ajan için imzalı bağlantı üretir.

Çalıştırma (yerel):
  pip install -r requirements.txt
  cp .env.example .env   # doldurun
  python google_auth.py  # bir kez: token.json üretir
  uvicorn main:app --reload --port 8000

Tüm uçlar 'X-Jarvis-Key' başlığı ister (JARVIS_KEY ile aynı olmalı).
"""
from __future__ import annotations

import base64
import datetime as dt
import html
import json
import os
import re
import zoneinfo
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Optional

import httpx
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from pydantic import BaseModel, Field

load_dotenv()

JARVIS_KEY = os.environ.get("JARVIS_KEY", "")
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
ELEVENLABS_AGENT_ID = os.environ.get("ELEVENLABS_AGENT_ID", "")
APP_ORIGIN = os.environ.get("APP_ORIGIN", "*")  # uygulamanın adresi, ör. https://kullanici.github.io
TZ = zoneinfo.ZoneInfo(os.environ.get("TIMEZONE", "Europe/Istanbul"))
SHEETS = {
    "durum_defteri": os.environ.get("SHEET_DURUM_DEFTERI_ID", ""),
    "tt_robotics": os.environ.get("SHEET_TT_ROBOTICS_ID", ""),
}
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/spreadsheets.readonly",
]
TOKEN_PATH = Path(os.environ.get("TOKEN_PATH", Path(__file__).with_name("token.json")))

app = FastAPI(title="Jarvis backend", version="0.2")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in APP_ORIGIN.split(",")] if APP_ORIGIN != "*" else ["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- yetki
def auth(x_jarvis_key: str = Header(default="")) -> None:
    if not JARVIS_KEY or x_jarvis_key != JARVIS_KEY:
        raise HTTPException(status_code=401, detail="Geçersiz anahtar")


def google_creds() -> Credentials:
    raw = os.environ.get("GOOGLE_TOKEN_JSON")  # bulutta: token.json içeriği (düz ya da base64)
    if raw:
        try:
            info = json.loads(raw)
        except json.JSONDecodeError:
            info = json.loads(base64.b64decode(raw).decode())
    elif TOKEN_PATH.exists():
        info = json.loads(TOKEN_PATH.read_text(encoding="utf-8"))
    else:
        raise HTTPException(status_code=503, detail="Google yetkisi yok: google_auth.py çalıştırın")
    creds = Credentials.from_authorized_user_info(info, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(GoogleRequest())
        if not raw:
            TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    return creds


def gmail():
    return build("gmail", "v1", credentials=google_creds(), cache_discovery=False)


def calendar():
    return build("calendar", "v3", credentials=google_creds(), cache_discovery=False)


def sheets():
    return build("sheets", "v4", credentials=google_creds(), cache_discovery=False)


# --------------------------------------------------------------------------- yardımcılar
def _headers(msg: dict) -> dict[str, str]:
    return {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}


def _b64(data: str) -> str:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode(errors="replace")


def _strip_html(s: str) -> str:
    s = re.sub(r"(?is)<(script|style).*?</\1>", " ", s)
    s = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>", "\n", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    return re.sub(r"[ \t]+", " ", re.sub(r"\n{3,}", "\n\n", s)).strip()


def _body_text(payload: dict) -> str:
    """text/plain tercih, yoksa text/html'den metin çıkar."""
    plain, htmlpart = [], []

    def walk(p: dict):
        mime = p.get("mimeType", "")
        data = p.get("body", {}).get("data")
        if data and mime == "text/plain":
            plain.append(_b64(data))
        elif data and mime == "text/html":
            htmlpart.append(_b64(data))
        for sub in p.get("parts", []) or []:
            walk(sub)

    walk(payload)
    text = "\n".join(plain).strip() or _strip_html("\n".join(htmlpart))
    return text


def _summary(msg: dict) -> dict:
    h = _headers(msg)
    return {
        "id": msg["id"],
        "thread_id": msg.get("threadId"),
        "from": h.get("from", ""),
        "subject": h.get("subject", "(konu yok)"),
        "date": h.get("date", ""),
        "unread": "UNREAD" in msg.get("labelIds", []),
        "snippet": html.unescape(msg.get("snippet", ""))[:200],
    }


def _list_messages(q: str, limit: int) -> list[dict]:
    svc = gmail()
    res = svc.users().messages().list(userId="me", q=q, maxResults=max(1, min(limit, 25))).execute()
    out = []
    for m in res.get("messages", []) or []:
        full = svc.users().messages().get(
            userId="me", id=m["id"], format="metadata", metadataHeaders=["From", "Subject", "Date"]
        ).execute()
        out.append(_summary(full))
    return out


# --------------------------------------------------------------------------- modeller
class InboxIn(BaseModel):
    days: int = Field(1, ge=1, le=30)
    unread_only: bool = True
    limit: int = Field(10, ge=1, le=25)


class SearchIn(BaseModel):
    query: str
    limit: int = Field(10, ge=1, le=25)


class ReadIn(BaseModel):
    message_id: str


class DraftIn(BaseModel):
    message_id: str
    body: str


class CalendarIn(BaseModel):
    days: int = Field(1, ge=1, le=31)


class SheetIn(BaseModel):
    sheet: str
    tab: Optional[str] = None
    search: Optional[str] = None


# --------------------------------------------------------------------------- uçlar
@app.get("/health")
def health():
    return {"ok": True, "time": dt.datetime.now(TZ).isoformat(timespec="minutes")}


@app.get("/signed-url", dependencies=[Depends(auth)])
async def signed_url():
    """Özel ajan için tek kullanımlık bağlantı. Uygulama bunu alıp ElevenLabs'e websocket açar."""
    if not (ELEVENLABS_API_KEY and ELEVENLABS_AGENT_ID):
        raise HTTPException(503, "ELEVENLABS_API_KEY / ELEVENLABS_AGENT_ID eksik")
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get(
            "https://api.elevenlabs.io/v1/convai/conversation/get-signed-url",
            params={"agent_id": ELEVENLABS_AGENT_ID},
            headers={"xi-api-key": ELEVENLABS_API_KEY},
        )
    if r.status_code != 200:
        raise HTTPException(502, f"ElevenLabs: {r.text[:200]}")
    return r.json()  # {"signed_url": "..."}


@app.post("/tools/mail_inbox", dependencies=[Depends(auth)])
def mail_inbox(inp: InboxIn):
    q = f"newer_than:{inp.days}d -category:promotions -category:social"
    if inp.unread_only:
        q += " is:unread"
    items = _list_messages(q, inp.limit)
    return {"count": len(items), "window_days": inp.days, "unread_only": inp.unread_only, "messages": items}


@app.post("/tools/mail_search", dependencies=[Depends(auth)])
def mail_search(inp: SearchIn):
    items = _list_messages(inp.query, inp.limit)
    return {"count": len(items), "query": inp.query, "messages": items}


@app.post("/tools/mail_read", dependencies=[Depends(auth)])
def mail_read(inp: ReadIn):
    msg = gmail().users().messages().get(userId="me", id=inp.message_id, format="full").execute()
    text = _body_text(msg.get("payload", {}))
    out = _summary(msg)
    out["body"] = text[:6000] + ("\n[... metin kısaltıldı ...]" if len(text) > 6000 else "")
    out["attachments"] = [
        p.get("filename") for p in msg.get("payload", {}).get("parts", []) or [] if p.get("filename")
    ]
    return out


@app.post("/tools/mail_draft_reply", dependencies=[Depends(auth)])
def mail_draft_reply(inp: DraftIn):
    """Cevap TASLAĞI oluşturur; göndermez. Göndermek Tolga Bey'in işi."""
    svc = gmail()
    orig = svc.users().messages().get(
        userId="me", id=inp.message_id, format="metadata",
        metadataHeaders=["From", "Reply-To", "Subject", "Message-ID", "References"],
    ).execute()
    h = _headers(orig)
    to = h.get("reply-to") or h.get("from", "")
    subject = h.get("subject", "")
    if not re.match(r"(?i)^\s*re:", subject):
        subject = "Re: " + subject
    msg = EmailMessage()
    msg["To"] = to
    msg["Subject"] = subject
    if h.get("message-id"):
        msg["In-Reply-To"] = h["message-id"]
        msg["References"] = (h.get("references", "") + " " + h["message-id"]).strip()
    msg.set_content(inp.body)
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    draft = svc.users().drafts().create(
        userId="me", body={"message": {"raw": raw, "threadId": orig.get("threadId")}}
    ).execute()
    return {
        "status": "taslak_hazir",
        "draft_id": draft["id"],
        "to": to,
        "subject": subject,
        "note": "Gönderilmedi. Gmail > Taslaklar klasöründe; göndermeyi Tolga Bey yapar.",
    }


@app.post("/tools/calendar_upcoming", dependencies=[Depends(auth)])
def calendar_upcoming(inp: CalendarIn):
    now = dt.datetime.now(TZ)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + dt.timedelta(days=inp.days)
    res = calendar().events().list(
        calendarId="primary", timeMin=start.isoformat(), timeMax=end.isoformat(),
        singleEvents=True, orderBy="startTime", maxResults=40,
    ).execute()
    events = []
    for ev in res.get("items", []) or []:
        s = ev.get("start", {}); e = ev.get("end", {})
        if "dateTime" in s:
            sdt = dt.datetime.fromisoformat(s["dateTime"]).astimezone(TZ)
            edt = dt.datetime.fromisoformat(e["dateTime"]).astimezone(TZ)
            when = sdt.strftime("%d.%m.%Y %H:%M") + "–" + edt.strftime("%H:%M")
        else:
            when = s.get("date", "") + " (tüm gün)"
        events.append({
            "title": ev.get("summary", "(başlıksız)"),
            "when": when,
            "location": ev.get("location", ""),
            "attendees": [a.get("email") for a in ev.get("attendees", []) or []][:6],
        })
    return {"count": len(events), "from": start.strftime("%d.%m.%Y"), "days": inp.days, "events": events}


@app.post("/tools/sheet_query", dependencies=[Depends(auth)])
def sheet_query(inp: SheetIn):
    sid = SHEETS.get(inp.sheet.strip().lower())
    if not sid:
        raise HTTPException(404, f"Tanımsız sheet: {inp.sheet}. Geçerli: {', '.join(k for k, v in SHEETS.items() if v)}")
    svc = sheets()
    rng = f"'{inp.tab}'!A1:Z1000" if inp.tab else "A1:Z1000"
    try:
        values = svc.spreadsheets().values().get(spreadsheetId=sid, range=rng).execute().get("values", [])
    except Exception as ex:  # yanlış sekme adı vb.
        meta = svc.spreadsheets().get(spreadsheetId=sid, fields="sheets.properties.title").execute()
        tabs = [s["properties"]["title"] for s in meta.get("sheets", [])]
        raise HTTPException(400, f"Okunamadı ({ex.__class__.__name__}). Sekmeler: {', '.join(tabs)}")
    if not values:
        return {"count": 0, "rows": []}
    header = [str(c).strip() for c in values[0]]
    rows: list[dict[str, Any]] = []
    needle = (inp.search or "").casefold().strip()
    for r in values[1:]:
        if not any(str(c).strip() for c in r):
            continue
        row = {header[i] if i < len(header) and header[i] else f"col{i+1}": str(c) for i, c in enumerate(r)}
        if needle and needle not in " ".join(row.values()).casefold():
            continue
        rows.append(row)
    total = len(rows)
    return {"sheet": inp.sheet, "tab": inp.tab or "(ilk sekme)", "count": total, "rows": rows[:150],
            "truncated": total > 150}
