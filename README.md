# Hukuk AI — Telemetri Relay

Müşteri bilgisayarlarından gelen **kullanıcı onaylı** hata/güvenlik raporlarını
GitHub Issue olarak size ulaştıran köprü sunucu.

## 🔐 Felsefe

- **ASLA** sohbet içeriği, belge içeriği, müvekkil bilgileri gönderilmez
- **SADECE** teknik metadata: exception stack, versiyon, OS kategorisi
- **HWID hash** kullanılır (kimlik değil, gruplayıcı — geri dönüştürülemez)

## 🚀 Deploy Adımları

### 1) GitHub Repo Oluşturun

Private repo açın, örnek ad: `hukuk-ai-telemetri`

Buraya hiçbir şey yüklemeyeceksiniz — sadece issue alıyor.

### 2) GitHub Token Alın

1. https://github.com/settings/tokens → **Fine-grained personal access tokens**
2. **New token** → İsim: "Hukuk AI Telemetri Relay"
3. **Resource owner:** kendi kullanıcınız
4. **Repository access:** Only selected → `hukuk-ai-telemetri`
5. **Permissions:**
   - Issues: **Read and write**
6. **Generate** → Token'ı kopyalayın (`ghp_xxxxxx`)

### 3) Render.com ile Ücretsiz Deploy (Önerilen)

1. **telemetri_relay/** klasörünü **ayrı bir GitHub reposuna** push edin
   (örn: `hukuk-ai-telemetri-relay` — public veya private)

2. https://render.com → hesap açın, GitHub ile bağlayın

3. **New → Web Service**
   - Connect: yeni push ettiğiniz relay repo
   - **Name:** `hukuk-ai-telemetri`
   - **Region:** Frankfurt (Türkiye'ye en yakın)
   - **Branch:** main
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app:app --host 0.0.0.0 --port $PORT`
   - **Plan:** Free (0$)

4. **Environment Variables** bölümünde:
   ```
   GITHUB_TOKEN  = ghp_xxxxxxxxxxxxxx
   GITHUB_REPO   = kullaniciadi/hukuk-ai-telemetri
   RATE_LIMIT_DAKIKA = 5
   ```
   Opsiyonel:
   ```
   SHARED_SECRET = (rastgele 32 karakter — client ile paylaşılacak)
   DEV_MODE      = false
   ```

5. **Create Web Service** → 2-3 dakika içinde aktif

6. Verilen URL'yi kopyalayın: `https://hukuk-ai-telemetri.onrender.com`

### 4) Client'ı Yönlendirin

`files/backend/telemetri.py` içinde şu satırı bulun:
```python
TELEMETRI_URL = os.environ.get(
    "HUKUKAI_TELEMETRI_URL",
    "https://hukuk-ai-telemetri.onrender.com/api/rapor"  # ← buraya URL'niz
)
```

`onrender.com` yerine kendi Render URL'nizi yazın.

### 5) Test Edin

```powershell
# Health check
curl https://hukuk-ai-telemetri.onrender.com/health

# Durum
curl https://hukuk-ai-telemetri.onrender.com/api/durum

# Sentetik rapor (dev modda)
curl -X POST https://hukuk-ai-telemetri.onrender.com/api/rapor `
  -H "Content-Type: application/json" `
  -d '{
    "id": "test001",
    "timestamp": "2026-04-22T12:00:00Z",
    "kategori": "BUG",
    "alt_kategori": "TEST",
    "ozet": "Deploy testi",
    "stack_trace": "traceback here",
    "modul": "test.py",
    "versiyon": "4.0.0",
    "python": "3.12.0",
    "isletim_sistemi": "Windows 10",
    "lisans_hash": "abc123",
    "ek_bilgi": {}
  }'
```

Başarılı ise GitHub repo'nuzda yeni issue görürsünüz: `[BUG][TEST] Deploy testi`

## 🛡️ Güvenlik Önlemleri

| Özellik | Detay |
|---------|-------|
| **Rate limit** | Aynı lisans_hash'ten dakikada 5 rapor |
| **Payload validation** | Pydantic ile sıkı alan kontrolü + boyut limitleri |
| **HMAC (opsiyonel)** | SHARED_SECRET ile imza doğrulama |
| **HTTPS** | Render.com otomatik TLS sağlar |
| **Sadece issues:write** | Token'ın başka yetkisi yok |

## 📊 GitHub'da Ne Görürsünüz?

Her rapor şöyle bir issue açar:

```
[BUG][IMPORT_ERROR] ImportError: No module named 'fitz'

## Rapor Ozeti
Kategori: BUG / IMPORT_ERROR
Versiyon: 4.0.0
Python: 3.12.0
OS: Windows 10 Pro
Modul: sunucu.py
Zaman: 2026-04-22T14:33:00Z
Rapor ID: a081410b7f69
Lisans Hash: abc123... (anonim)

## Stack Trace
...

Labels: bug, v4.0.0, import-error
```

## 🔧 Maintenance

### Render.com Uyuma Sorunu (Ücretsiz Tier)

Ücretsiz tier'da 15 dakika kullanılmayınca sunucu uyur. İlk istek 30 saniye sürer.

Çözüm: https://cron-job.org/ ile her 14 dakikada bir `/health` çağır.
Veya Render paid plana geç (7$/ay).

### GitHub Rate Limit

Kişisel token için 5000 istek/saat. Bu kadar rapor gelirse GitHub'ın API'si şikayet eder.
`RATE_LIMIT_DAKIKA=5` yeterli koruma.

### Token Rotation

Güvenlik için 90 günde bir token'ı yenileyin. Env var değiştirmek 1 dakika.

## 📜 Uyumluluk

- **KVKK:** Sadece anonim teknik veri. Kişisel veri işleme YOK.
- **DMCA/Avukatlık K.:** Müvekkil sırrı ASLA sunucuya gitmez.
- **GitHub ToS:** Issue otomatik açma legal — rate limit altında.
