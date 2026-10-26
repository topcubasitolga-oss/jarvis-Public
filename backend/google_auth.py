#!/usr/bin/env python3
"""
Bir kez, kendi bilgisayarınızda çalıştırılır: Google hesabınız için izin alır ve token.json üretir.

Ön hazırlık (yaklaşık 10 dakika, README'de ayrıntılı):
  1. console.cloud.google.com → yeni proje → "Gmail API", "Google Calendar API", "Google Sheets API" etkinleştir.
  2. APIs & Services → OAuth consent screen → External → test kullanıcısı olarak kendi Gmail adresinizi ekleyin.
  3. Credentials → Create credentials → OAuth client ID → Desktop app → JSON'u indirip bu klasöre
     credentials.json adıyla koyun.
  4. python google_auth.py  → tarayıcı açılır, izin verin → token.json oluşur.

Bulutta (Railway/Render) çalıştırmak için token.json içeriğini GOOGLE_TOKEN_JSON ortam değişkenine koyun;
bu script sonunda base64 hâlini de yazdırır.
"""
import base64
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/spreadsheets.readonly",
]
HERE = Path(__file__).resolve().parent

if not (HERE / "credentials.json").exists():
    raise SystemExit("credentials.json bulunamadı. Google Cloud'dan OAuth 'Desktop app' istemcisi indirin.")

flow = InstalledAppFlow.from_client_secrets_file(str(HERE / "credentials.json"), SCOPES)
creds = flow.run_local_server(port=0, prompt="consent")
(HERE / "token.json").write_text(creds.to_json(), encoding="utf-8")
print("token.json yazıldı.\n")
print("Bulut için GOOGLE_TOKEN_JSON değeri (base64):")
print(base64.b64encode(creds.to_json().encode()).decode())
