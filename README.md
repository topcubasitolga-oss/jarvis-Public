# Jarvis — kişisel sesli asistan

Telefonda ya da masaüstünde tek dokunuşla açılan, "Buyurun efendim." diyen, Gmail'e, takvime ve
kayıtlara bakabilen kişisel asistan. Beyni Claude, sesi ElevenLabs, karakteri `agent/system_prompt.md`.

```
  [ Jarvis uygulaması ]  ─── ses ───▶  [ ElevenLabs Agents ]  ───▶  Claude (beyin)
    docs/  (GitHub Pages)               konuşma tanıma + ses            │
    büyük düğme, döküm                          │  webhook araçları      │
                                                ▼                       │
                                        [ backend/ (FastAPI) ] ◀────────┘
                                          Gmail · Takvim · Google Sheets
```

| Klasör     | Ne var                                                                 |
|------------|------------------------------------------------------------------------|
| `docs/`    | Uygulama: tek sayfa, telefona ikon olarak eklenebilir (PWA)             |
| `agent/`   | Jarvis'in karakteri, ElevenLabs ajan ayarı, araç tanımları, kurulum scriptleri |
| `backend/` | Araçlar: gelen kutusu, arama, cevap taslağı, takvim, sheet sorgusu (Aşama 2) |

Üç aşamada ilerler. Aşama 1 bittiğinde Jarvis konuşur; Aşama 2'de posta kutusunu ve takvimi görür;
Aşama 3'te projelerinizi ve TT Robotics kayıtlarını bilir.

---

## Aşama 1 — Jarvis konuşsun (yaklaşık 20 dakika, kod yazmadan)

### 1. ElevenLabs hesabı ve API anahtarı
elevenlabs.io'da hesap açın (Agents için ücretsiz katmanda da deneme dakikası var). Sağ üstten
profil → **API Keys** → yeni anahtar. Bu anahtarı kimseyle paylaşmayın.

### 2. Ses seçimi
Filmdeki karakteri seslendiren oyuncunun sesini kopyalamıyoruz; kütüphaneden o ruhu taşıyan bir ses
seçiyoruz: sakin, biraz derin, ölçülü, kibar.

- **Voices → Explore (Voice Library)** bölümüne girin.
- İki yol var, ikisini de "Buyurun efendim. Son yirmi dört saatte dokuz yeni ileti var." cümlesiyle dinleyin:
  - **Türkçe doğal ses:** dil filtresini Turkish yapın, "calm", "narration", "formal" etiketli erkek seslere bakın.
  - **İngiliz aksanlı kâhya tonu:** dil filtresi English (British), "calm", "deep", "butler", "narrator" gibi
    aramalar. Ajan modeli çok dilli olduğu için bu sesler Türkçe'yi hafif aksanla ama akıcı konuşur;
    "Jarvis hissi" çoğu zaman buradan çıkar.
- Beğendiğiniz sesi kütüphanenize ekleyin (**Add to My Voices**) ve **Voice ID**'sini kopyalayın
  (ses kartındaki üç nokta → Copy Voice ID).

### 3. Ajanı oluşturun

**Yol A — tek komut (önerilen):**
```bash
export ELEVENLABS_API_KEY="xi-..."
python agent/create_agent.py --voice VOICE_ID
```
Script, `agent/system_prompt.md` ve `agent/jarvis_agent.json`'u birleştirip ajanı yaratır,
**Agent ID**'yi ekrana ve `agent/agent_id.txt` dosyasına yazar.
Karakteri değiştirdiğinizde: `python agent/create_agent.py --update AGENT_ID`.
Daha hızlı/ucuz model isterseniz: `--llm claude-haiku-5-5`.

**Yol B — panelden elle:** Agents → New agent → Blank. Şu alanları doldurun:
- Agent language: **Turkish** · First message: **Buyurun efendim.**
- System prompt: `agent/system_prompt.md` içeriğini olduğu gibi yapıştırın
- LLM: **claude-sonnet-5-5** (ya da listedeki en yeni Claude Sonnet) · Temperature: 0.4
- Voice: 2. adımda seçtiğiniz ses · TTS model: varsayılan (v4 turbo)
- Advanced → Timezone: Europe/Istanbul

### 4. Hızlı deneme
Ajan sayfasındaki **Test agent** düğmesine basın, "Selam Jarvis" deyin. "Buyurun efendim." duymalısınız.
Ses, tempo ya da üslup oturmadıysa önce sesi değiştirin; üslup için `system_prompt.md`'yi düzenleyip
`--update` ile gönderin.

### 5. Uygulamayı yayınlayın
Mikrofon için HTTPS şart; en kolay iki yol:

- **GitHub Pages:** bu klasörü bir GitHub deposuna koyun → repo Settings → Pages →
  Source: *Deploy from a branch* → Branch: `main`, klasör: **/docs** → Save. Adres:
  `https://KULLANICI.github.io/DEPO/`
- **Netlify Drop:** app.netlify.com/drop sayfasına `docs` klasörünü sürükleyin; anında bir adres verir.

### 6. Telefona ekleyin ve uyandırın
- iPhone/Safari: Paylaş → **Ana Ekrana Ekle**. Android/Chrome: menü → **Ana ekrana ekle** (ya da "Yükle").
- Uygulama ilk açılışta Agent ID'yi sorar: 3. adımdaki `agent_...` değerini yapıştırıp kaydedin.
- Büyük düğmeye basın, mikrofon iznini verin. Jarvis "Buyurun efendim." der; artık konuşabilirsiniz.
  Düğmeye tekrar basmak oturumu bitirir. Masaüstünde boşluk tuşu da aynı işi görür. Alttaki satırdan
  yazarak da sorabilirsiniz.

> Bu aşamada ajan "public" olduğu için Agent ID'yi bilen biri Jarvis'le konuşabilir; kişisel veri
> henüz bağlı olmadığından sorun değil. Aşama 2'de ajanı özel yapacağız.

---

## Aşama 2 — Gözleri ve elleri: Gmail, Takvim, Sheets

### 1. Google izni (bir kez, kendi bilgisayarınızda, ~10 dk)
1. console.cloud.google.com → yeni proje (adı "Jarvis" olabilir).
2. **APIs & Services → Library**: *Gmail API*, *Google Calendar API*, *Google Sheets API* → Enable.
3. **OAuth consent screen**: External → uygulama adı Jarvis → *Test users* bölümüne kendi Gmail adresinizi ekleyin.
4. **Credentials → Create credentials → OAuth client ID → Desktop app** → JSON'u indirin →
   `backend/credentials.json` adıyla kaydedin.
5. Terminalde:
   ```bash
   cd backend
   pip install -r requirements.txt
   python google_auth.py
   ```
   Tarayıcı açılır, izin verirsiniz, `token.json` oluşur. Script sonunda bulut için base64 değer yazdırır; saklayın.

### 2. Backend'i yayınlayın
Yerelde denemek için: `cp .env.example .env` → doldurun → `uvicorn main:app --reload`.
Bulutta en kolayı **Railway** ya da **Render**: GitHub deposunu bağlayın, kök dizin `backend`,
ortam değişkenlerini `.env.example`'daki adlarla girin (`GOOGLE_TOKEN_JSON` = base64 değer).
Yayınlanınca `https://ADRES/health` çalışıyor olmalı.

`JARVIS_KEY` için uzun rastgele bir parola üretin: `python -c "import secrets; print(secrets.token_urlsafe(32))"`

### 3. Araçları Jarvis'e bağlayın
ElevenLabs panelinde Agents → Settings → **Secrets** → `JARVIS_KEY` değerini kaydedin, verilen
secret kimliğini alın. Sonra:
```bash
python agent/add_tools.py --agent-id AGENT_ID --backend-url https://ADRES --secret-id SECRET_ID
```
Altı araç oluşur ve ajana bağlanır: `mail_inbox`, `mail_search`, `mail_read`, `mail_draft_reply`,
`calendar_upcoming`, `sheet_query`. Panelde Agent → Tools altında görünür.

### 4. Ajanı özel yapın, uygulamayı özel moda alın
Ajan ayarlarında **Security → Enable authentication** (ajan artık yalnızca imzalı bağlantıyla açılır).
Backend `.env`'ine `ELEVENLABS_API_KEY` ve `ELEVENLABS_AGENT_ID` girin. Uygulamada ⚙ →
Bağlantı: **Özel ajan** → backend adresi ve `JARVIS_KEY` → Kaydet.

### 5. Deneyin
"Bugün mail var mı?", "Dergiden mail gelmiş mi?", "Şu maili oku", "Buna kibar bir cevap taslağı hazırla",
"Yarın programım ne?". Jarvis mail **göndermez**: taslağı Gmail'in Taslaklar klasörüne bırakır,
göndermek size kalır.

---

## Aşama 3 — Durum Defteri ve TT Robotics

Jarvis'in "makalenin son durumu ne" ya da "hangi okulda hangi set var" sorularına cevap verebilmesi
için bilginin bir tabloda olması gerekir. İki Google Sheet:

**Durum Defteri** (her satır bir proje):

| Proje | Tür | Aşama | Son olay | Tarih | Bekleyen iş | Not |
|-------|-----|-------|----------|-------|-------------|-----|
| ... makale | Makale | Hakem değerlendirmesi | Editörden bilgilendirme | 18.10.2026 | — | ... |

**TT Robotics** (sekmeler):
- `Okullar`: Okul · İlçe · İrtibat kişisi · Telefon · Son görüşme · Durum
- `Setler`: Set adı · Seri no · Okul/Konum · Durum · Tarih
- `Satışlar`: Tarih · Okul · Ürün · Adet · Tutar · Ödeme durumu
- `Görüşmeler`: Tarih · Okul · Kişi · Konu · Sonraki adım

Sheet URL'sindeki kimlikleri (`/d/` ile `/edit` arası) backend `.env`'ine `SHEET_DURUM_DEFTERI_ID` ve
`SHEET_TT_ROBOTICS_ID` olarak girin. Durum Defteri'ni Claude ile sohbetlerde güncelletebilirsiniz;
sonraki adım bunu günlük zamanlanmış göreve bağlamak.

---

## Güvenlik notları
- Anahtarlar yalnızca `backend/.env`'de ve ElevenLabs Secrets'ta durur; `.gitignore` bunları dışarıda tutar.
- Araçlar bağlandıktan sonra ajan mutlaka özel (authentication açık) olmalı.
- Backend yalnızca okur; tek yazma işi cevap **taslağı** oluşturmaktır. Gönderme, silme, takvim değişikliği yok.
- `APP_ORIGIN`'i uygulamanın gerçek adresiyle sınırlayın.

## Sonraki adımlar
- "Selam Jarvis" ile eller serbest uyandırma (Picovoice Porcupine web SDK ile özel uyandırma sözcüğü).
- Hotmail/Outlook ve kurum e-postası (Microsoft Graph API; `mail_*` araçlarının Outlook eşleri).
- Durum Defteri'nin Claude tarafından otomatik güncellenmesi (günlük zamanlanmış görev).
- Konuşma geçmişi ve sabah özeti ("Günaydın efendim, bugün...") için açılışta otomatik brifing.

## Sorun giderme
| Belirti | Sebep / çözüm |
|---------|----------------|
| "Ses kütüphanesi yüklenemedi" | İnternet yok ya da CDN engelli; sayfayı yenileyin |
| Mikrofon izni çıkmıyor | Adres HTTPS olmalı; Safari'de Ayarlar → Safari → Mikrofon |
| "Backend anahtarı reddedildi" | Uygulamadaki anahtar ile `JARVIS_KEY` farklı |
| Jarvis "bu bilgi elimde yok" diyor | Araçlar henüz bağlı değil ya da backend çalışmıyor (`/health`) |
| Türkçe'si çok aksanlı | Türkçe doğal bir ses seçin; olmazsa TTS modelini `eleven_flash_v2_5` yapın |
| Konuşma kesik / gecikmeli | Kulaklık kullanın; `--llm claude-haiku-5-5` ile deneyin |
