#!/usr/bin/env python3
"""
Aşama 2: tools.json'daki araçları ElevenLabs'te oluşturur ve Jarvis ajanına bağlar.

Kullanım:
  export ELEVENLABS_API_KEY="xi-..."
  python add_tools.py --agent-id AGENT_ID --backend-url https://jarvis-backend.example.app --secret-id SECRET_ID
      (SECRET_ID: ElevenLabs panelinde Agents > Settings > Secrets'ta JARVIS_KEY değerini kaydedince verilen kimlik)
  python add_tools.py --agent-id AGENT_ID --backend-url https://... --key DUZ_METIN_ANAHTAR
      (secret yerine anahtarı düz metin yazar; kişisel kullanım için kabul edilebilir, secret daha güvenli)

Ek bağımlılık yok.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.elevenlabs.io/v1/convai"
HERE = Path(__file__).resolve().parent


def api(method, path, key, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(API + path, data=data, method=method,
                                 headers={"xi-api-key": key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        sys.exit(f"ElevenLabs API hatası {e.code} ({method} {path}): {e.read().decode(errors='replace')}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--agent-id", required=True)
    p.add_argument("--backend-url", required=True, help="Backend'in kök adresi, sonunda / olmadan")
    p.add_argument("--secret-id", help="ElevenLabs workspace secret kimliği (önerilen)")
    p.add_argument("--key", help="Düz metin anahtar (secret yoksa)")
    p.add_argument("--api-key")
    args = p.parse_args()

    key = args.api_key or os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        sys.exit("ELEVENLABS_API_KEY tanımlı değil.")
    if not (args.secret_id or args.key):
        sys.exit("--secret-id ya da --key verin.")

    header_value = {"secret_id": args.secret_id} if args.secret_id else args.key
    base = args.backend_url.rstrip("/")

    tools = json.loads((HERE / "tools.json").read_text(encoding="utf-8"))
    tool_ids = []
    for t in tools:
        t["api_schema"]["url"] = t["api_schema"]["url"].replace("{{BACKEND_URL}}", base)
        t["api_schema"]["request_headers"] = {"X-Jarvis-Key": header_value}
        res = api("POST", "/tools", key, {"tool_config": t})
        tid = res.get("id") or res.get("tool_id")
        if not tid:
            sys.exit(f"Araç oluşturulamadı ({t['name']}): {res}")
        tool_ids.append(tid)
        print(f"  + {t['name']:<18} {tid}")

    api("PATCH", f"/agents/{args.agent_id}", key,
        {"conversation_config": {"agent": {"prompt": {"tool_ids": tool_ids}}}})
    print(f"\n{len(tool_ids)} araç Jarvis'e bağlandı. Panelde Agent > Tools altından görebilirsiniz.")
    print("Hatırlatma: artık ajanı 'private' yapıp uygulamada Özel mod + backend adresini kullanın.")


if __name__ == "__main__":
    main()
