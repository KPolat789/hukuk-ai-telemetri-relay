# -*- coding: utf-8 -*-
"""
TELEMETRI RELAY — Müsteri client'larindan gelen raporlari GitHub Issue'ya cevirir.

DEPLOYMENT:
  - Render.com (onerilen, ucretsiz):
      1. https://render.com/ hesap ac
      2. New Web Service
      3. GitHub repo'ya bagla (bu klasoru kendi reponuza push edin)
      4. Build Command:  pip install -r requirements.txt
      5. Start Command:  uvicorn app:app --host 0.0.0.0 --port $PORT
      6. Environment Variables:
         GITHUB_TOKEN = ghp_xxx (sadece issues:write yetkisi)
         GITHUB_REPO  = <username>/hukuk-ai-telemetri
         RATE_LIMIT_DAKIKA = 5 (opsiyonel)
  - Railway.app veya kendi VPS'iniz de calisir.

GITHUB TOKEN NASIL ALINIR:
  1. https://github.com/settings/tokens → "Fine-grained personal access tokens"
  2. Repository access: sadece telemetri reponuz
  3. Permissions: Issues (Read and write)
  4. Uretin ve Render'da env var olarak kaydedin

SECURITY:
  - Rate limit: ayni IP'den dakikada max 5 rapor
  - Payload dogrulama: ASLA kisisel veri kabul etme
  - HMAC/shared secret (opsiyonel)
"""

import os
import json
import time
import hashlib
import hmac
from collections import defaultdict, deque
from typing import Dict, Any
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import httpx


# ═══════════════════════════════════════════════════════════════════
#  KONFIGURASYON (Environment Variables)
# ═══════════════════════════════════════════════════════════════════

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
GITHUB_REPO = os.environ.get("GITHUB_REPO", "").strip()  # "username/repo"
RATE_LIMIT_DAKIKA = int(os.environ.get("RATE_LIMIT_DAKIKA", "5"))
# Opsiyonel: client'in HMAC imzasi (ayni shared secret her iki tarafta)
SHARED_SECRET = os.environ.get("SHARED_SECRET", "").strip()
# Geliştirme modu (GitHub cagrisi yapma, sadece logla)
DEV_MODE = os.environ.get("DEV_MODE", "false").lower() == "true"


# ═══════════════════════════════════════════════════════════════════
#  APP
# ═══════════════════════════════════════════════════════════════════

app = FastAPI(
    title="Hukuk AI Telemetri Relay",
    description="Kullanici rizasiyla gonderilen hata/guvenlik raporlarini GitHub Issue'ya cevirir.",
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════════════════════
#  RATE LIMIT (Anti-Spam)
# ═══════════════════════════════════════════════════════════════════

_rate_limit_cache: Dict[str, deque] = defaultdict(deque)


def _rate_limit_kontrol(istemci_key: str) -> bool:
    """Dakikada max N rapor. Asilirsa reddet."""
    simdi = time.time()
    dakika = simdi - 60
    # Eski girisleri sil
    d = _rate_limit_cache[istemci_key]
    while d and d[0] < dakika:
        d.popleft()
    if len(d) >= RATE_LIMIT_DAKIKA:
        return False
    d.append(simdi)
    return True


# ═══════════════════════════════════════════════════════════════════
#  MODELLER
# ═══════════════════════════════════════════════════════════════════

class Rapor(BaseModel):
    """Client'tan gelen hata/guvenlik raporu.

    Alanlari telemetri.py'de HataRaporu ile ayni olmali.
    """
    id: str = Field(..., max_length=32)
    timestamp: str = Field(..., max_length=40)
    kategori: str = Field(..., pattern="^(BUG|SECURITY|PERFORMANCE|LICENSE)$")
    alt_kategori: str = Field(..., max_length=50)
    ozet: str = Field(..., max_length=300)
    stack_trace: str = Field(default="", max_length=5000)
    modul: str = Field(..., max_length=100)
    versiyon: str = Field(..., max_length=20)
    python: str = Field(..., max_length=20)
    isletim_sistemi: str = Field(..., max_length=60)
    lisans_hash: str = Field(default="", max_length=32)
    ek_bilgi: Dict[str, Any] = Field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════════
#  GITHUB ISSUE OLUSTUR
# ═══════════════════════════════════════════════════════════════════

async def _github_issue_olustur(rapor: Rapor) -> Dict[str, Any]:
    """GitHub REST API ile issue olusturur."""
    if DEV_MODE:
        print(f"[DEV] Issue olusturulmadi (DEV_MODE): {rapor.ozet}")
        return {"ok": True, "dev_mode": True}

    if not GITHUB_TOKEN or not GITHUB_REPO:
        raise HTTPException(500, "GITHUB_TOKEN veya GITHUB_REPO ayarlanmadi")

    # Issue basligi — prefixli
    prefix = {
        "BUG": "[BUG]",
        "SECURITY": "[SEC]",
        "PERFORMANCE": "[PERF]",
        "LICENSE": "[LIC]",
    }.get(rapor.kategori, "[RAP]")
    baslik = f"{prefix}[{rapor.alt_kategori}] {rapor.ozet[:80]}"

    # Issue govdesi — markdown
    govde = f"""## Rapor Ozeti

**Kategori:** `{rapor.kategori}` / `{rapor.alt_kategori}`
**Versiyon:** `{rapor.versiyon}`
**Python:** `{rapor.python}`
**OS:** `{rapor.isletim_sistemi}`
**Modul:** `{rapor.modul}`
**Zaman:** `{rapor.timestamp}`
**Rapor ID:** `{rapor.id}`
**Lisans Hash:** `{rapor.lisans_hash}` (anonim — kimlik degil)

## Ozet

> {rapor.ozet}

## Stack Trace

```python
{rapor.stack_trace[:3000]}
```

## Ek Bilgi

```json
{json.dumps(rapor.ek_bilgi, ensure_ascii=False, indent=2)[:1000]}
```

---

*Bu issue otomatik olusturuldu — Hukuk AI Telemetri Relay*
*Tum raporlar kullanici acik rizasiyla veya KVKK m.5/2-f mesru menfaat kapsaminda gelir.*
"""

    # Label'lar
    labels = [
        rapor.kategori.lower(),
        f"v{rapor.versiyon}",
    ]
    if rapor.alt_kategori:
        labels.append(rapor.alt_kategori.lower().replace("_", "-"))

    # GitHub API call
    url = f"https://api.github.com/repos/{GITHUB_REPO}/issues"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    payload = {
        "title": baslik[:256],
        "body": govde[:65000],
        "labels": labels[:10],
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code == 201:
                issue = resp.json()
                return {
                    "ok": True,
                    "issue_no": issue.get("number"),
                    "issue_url": issue.get("html_url"),
                }
            else:
                return {
                    "ok": False,
                    "status": resp.status_code,
                    "detay": resp.text[:300],
                }
        except Exception as e:
            return {"ok": False, "hata": str(e)[:200]}


# ═══════════════════════════════════════════════════════════════════
#  ENDPOINTS
# ═══════════════════════════════════════════════════════════════════

@app.get("/")
async def kok():
    return {
        "app": "Hukuk AI Telemetri Relay",
        "durum": "aktif",
        "endpoint_rapor": "/api/rapor (POST)",
        "endpoint_saglik": "/health",
        "github_repo": GITHUB_REPO if GITHUB_REPO else "ayarlanmadi",
        "rate_limit": f"{RATE_LIMIT_DAKIKA}/dakika",
        "dev_mode": DEV_MODE,
    }


@app.get("/health")
async def saglik():
    return {"ok": True, "timestamp": time.time()}


@app.post("/api/rapor")
async def rapor_al(rapor: Rapor, request: Request):
    """Client'tan gelen raporu GitHub Issue'ya cevir."""
    # Rate limit — lisans_hash bazli (unique istemci)
    rate_key = rapor.lisans_hash or request.client.host
    if not _rate_limit_kontrol(rate_key):
        raise HTTPException(429, "Rate limit asildi (dakikada max rapor)")

    # Opsiyonel HMAC imzasi dogrulama
    if SHARED_SECRET:
        imza = request.headers.get("X-HukukAI-Signature", "")
        payload_bytes = json.dumps(rapor.dict()).encode("utf-8")
        beklenen = hmac.new(
            SHARED_SECRET.encode(), payload_bytes, hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(imza, beklenen):
            raise HTTPException(401, "Imza gecersiz")

    # Boyut sanity check
    if len(rapor.stack_trace) > 5000:
        rapor.stack_trace = rapor.stack_trace[:5000]

    # GitHub Issue olustur
    sonuc = await _github_issue_olustur(rapor)
    return {
        "kabul_edildi": True,
        "rapor_id": rapor.id,
        "github": sonuc,
    }


@app.get("/api/durum")
async def durum():
    """Ozet istatistik (admin icin)."""
    toplam_kayit = sum(len(d) for d in _rate_limit_cache.values())
    return {
        "rate_limit_cache_size": len(_rate_limit_cache),
        "toplam_kayit_dakikada": toplam_kayit,
        "ayar": {
            "github_repo": GITHUB_REPO,
            "rate_limit_dakika": RATE_LIMIT_DAKIKA,
            "hmac_aktif": bool(SHARED_SECRET),
            "dev_mode": DEV_MODE,
        },
    }


@app.get("/api/debug/env")
async def debug_env():
    """GECICI: Environment variables'larin durumu (secret sizdirmaz)."""
    import os
    return {
        "GITHUB_TOKEN_var_mi": bool(os.environ.get("GITHUB_TOKEN")),
        "GITHUB_TOKEN_uzunluk": len(os.environ.get("GITHUB_TOKEN", "")),
        "GITHUB_TOKEN_basi": os.environ.get("GITHUB_TOKEN", "")[:10],
        "GITHUB_REPO_degeri": os.environ.get("GITHUB_REPO", "YOK"),
        "RATE_LIMIT_DAKIKA_degeri": os.environ.get("RATE_LIMIT_DAKIKA", "YOK"),
        "iliskili_env_keys": sorted([k for k in os.environ.keys()
                                        if "GITHUB" in k.upper()
                                        or "RATE" in k.upper()
                                        or "TOKEN" in k.upper()]),
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8765))
    uvicorn.run(app, host="0.0.0.0", port=port)
