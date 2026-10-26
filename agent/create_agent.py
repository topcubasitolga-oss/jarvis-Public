#!/usr/bin/env python3
"""
Jarvis ajanını ElevenLabs'te tek komutla oluşturur (ya da günceller).

Kullanım:
  export ELEVENLABS_API_KEY="xi-..."
  python create_agent.py --voice VOICE_ID                 # yeni ajan oluşturur
  python create_agent.py --update AGENT_ID                # system_prompt.md değiştiyse ajanı günceller
  python create_agent.py --voice VOICE_ID --llm claude-haiku-5-5   # daha hızlı/ucuz model

Ek bağımlılık yok; yalnızca Python standart kütüphanesi.
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


def api(method: str, path: str, key: str, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        API + path,
        data=data,
        method=method,
        headers={"xi-api-key": key, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        sys.exit(f"ElevenLabs API hatası {e.code}: {body}")


def build_config(args):
    prompt = (HERE / "system_prompt.md").read_text(encoding="utf-8").strip()
    cfg = json.loads((HERE / "jarvis_agent.json").read_text(encoding="utf-8"))
    cfg["conversation_config"]["agent"]["prompt"]["prompt"] = prompt
    if args.llm:
        cfg["conversation_config"]["agent"]["prompt"]["llm"] = args.llm
    if args.voice:
        cfg["conversation_config"]["tts"]["voice_id"] = args.voice
    if args.name:
        cfg["name"] = args.name
    return cfg


def main():
    p = argparse.ArgumentParser(description="Jarvis ajanını oluştur/güncelle")
    p.add_argument("--voice", help="ElevenLabs ses kimliği (Voice ID)")
    p.add_argument("--llm", help="LLM adı, ör. claude-sonnet-5-5 / claude-haiku-5-5")
    p.add_argument("--name", help="Ajan adı (varsayılan: Jarvis)")
    p.add_argument("--update", metavar="AGENT_ID", help="Var olan ajanı güncelle")
    p.add_argument("--api-key", help="ELEVENLABS_API_KEY yerine doğrudan anahtar")
    args = p.parse_args()

    key = args.api_key or os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        sys.exit("ELEVENLABS_API_KEY tanımlı değil. Profil > API Keys'ten anahtar alıp dışa aktarın.")

    cfg = build_config(args)

    if args.update:
        # Güncellemede yalnızca prompt metni (+ isteğe bağlı llm/ses) gönderilir;
        # araç bağlantıları ve diğer ayarlar korunur.
        prompt_patch = {"prompt": cfg["conversation_config"]["agent"]["prompt"]["prompt"]}
        if args.llm:
            prompt_patch["llm"] = args.llm
        patch = {"conversation_config": {"agent": {"prompt": prompt_patch}}}
        if args.voice:
            patch["conversation_config"]["tts"] = {"voice_id": args.voice}
        res = api("PATCH", f"/agents/{args.update}", key, patch)
        print(f"Ajan güncellendi: {res.get('agent_id', args.update)}")
        return

    if "{{VOICE_ID}}" in cfg["conversation_config"]["tts"]["voice_id"]:
        sys.exit("Ses seçilmedi. --voice VOICE_ID verin (README: 'Ses seçimi').")

    res = api("POST", "/agents/create", key, cfg)
    agent_id = res.get("agent_id")
    if not agent_id:
        sys.exit(f"Beklenmeyen cevap: {res}")
    (HERE / "agent_id.txt").write_text(agent_id + "\n", encoding="utf-8")
    print("Jarvis oluşturuldu.")
    print(f"  Agent ID : {agent_id}   (agent/agent_id.txt dosyasına da yazıldı)")
    print(f"  Panel    : https://elevenlabs.io/app/agents/agents/{agent_id}")
    print("Şimdi uygulamayı açıp Ayarlar'a bu Agent ID'yi yapıştırın.")


if __name__ == "__main__":
    main()
