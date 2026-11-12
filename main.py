# -*- coding: utf-8 -*-
"""
YouTube Shorts Hikaye Stüdyosu v7
---------------------------------
Gemini hikaye + başlık/açıklama yazar -> edge-tts seslendirir (kelime zamanlarıyla)
-> ffmpeg klip/resim/uzun video arka planı + vurgulu altyazı + müzik ile render eder
-> istenirse YouTube'a yükler (hemen ya da planlı).

Arayüz:      python main.py
Otomatik:    python main.py --oto 3 --yukle            (3 video üret ve yükle)
             python main.py --oto 4 --yukle --aralik 6 (6 saat arayla planlı yayın)
             python main.py --konu "Ormandaki kutu"     (tek video, arayüzsüz)
"""
import os
import sys
import re
import json
import time
import random
import shutil
import asyncio
import argparse
import threading
import datetime
import importlib
import importlib.util
import hashlib
import subprocess
import base64
import difflib
import io
import wave

# ---------------------------------------------------------------------------
# 0. YOLLAR (her şey bu dosyanın bulunduğu klasöre göre)
# ---------------------------------------------------------------------------
BASE = os.path.dirname(os.path.abspath(__file__))


def yol(*p):
    return os.path.join(BASE, *p)


CIKTI = yol("ciktilar")
GECICI = yol("gecici")
MUZIK = yol("muzik")
KLIP = yol("bg_klipler")
RESIM = yol("bg_resimler")
UZUN_BG = yol("arkaplan.mp4")
HAVUZ = yol("arkaplan_videolari")
AYAR_DOSYA = yol("ayarlar.json")
GECMIS_DOSYA = yol("gecmis.json")
CLIENT_SECRET = yol("client_secret.json")
TOKEN = yol("token.json")
for _d in (CIKTI, GECICI, MUZIK, KLIP, RESIM, HAVUZ):
    os.makedirs(_d, exist_ok=True)

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# ---------------------------------------------------------------------------
# KANAL PROFİLLERİ: her kanalın kendi ayarı, geçmişi, çıktıları, YouTube bağlantısı ve geçici klasörü var.
# Türkçe kanal ('tr') eskisi gibi ana klasördeki dosyaları kullanır; diğerleri profiller/<id>/ altında.
# Program her açılışta tek bir profille çalışır; kanal değiştirince kendini yeniden başlatır.
# ---------------------------------------------------------------------------
PROFIL_DOSYA = yol("profiller.json")
PROFIL_VARSAYILAN = {
    "aktif": "tr",
    "profiller": {
        "tr": {"ad": "BirAdımHikayeler", "dil": "tr"},
        "en": {"ad": "BirAdımHikayelerEnglish", "dil": "en"},
        "biradim": {"ad": "BirAdım", "dil": "tr", "tur": "notebooklm"},
    },
}
GENEL_AYARLAR = ("tema", "animasyon")      # kanaldan bağımsız, tüm profillerde ortak
AKTIF_PROFIL = "tr"
DIL = "tr"
KOK_AYAR_DOSYA = AYAR_DOSYA
KOK_GECMIS_DOSYA = GECMIS_DOSYA


def profiller_oku():
    v = _json_oku(PROFIL_DOSYA, {}) if "_json_oku" in globals() else {}
    sonuc = json.loads(json.dumps(PROFIL_VARSAYILAN))
    sonuc["aktif"] = v.get("aktif", sonuc["aktif"])
    for pid, bilgi in (v.get("profiller") or {}).items():
        sonuc["profiller"].setdefault(pid, {}).update(bilgi)
    if sonuc["aktif"] not in sonuc["profiller"]:
        sonuc["aktif"] = "tr"
    return sonuc


def profil_klasoru(pid):
    return BASE if pid == "tr" else yol("profiller", pid)


def profil_etkinlestir(pid):
    """Tüm dosya yollarını seçilen kanalın klasörüne çevirir. Program açılırken bir kez çağrılır."""
    global AKTIF_PROFIL, DIL, CIKTI, GECICI, AYAR_DOSYA, GECMIS_DOSYA, CLIENT_SECRET, TOKEN, YORUM_DOSYA
    prf = profiller_oku()
    if pid not in prf["profiller"]:
        pid = "tr"
    AKTIF_PROFIL = pid
    DIL = prf["profiller"][pid].get("dil", "tr")
    k = profil_klasoru(pid)
    CIKTI = os.path.join(k, "ciktilar")
    GECICI = os.path.join(k, "gecici")
    AYAR_DOSYA = os.path.join(k, "ayarlar.json")
    GECMIS_DOSYA = os.path.join(k, "gecmis.json")
    CLIENT_SECRET = os.path.join(k, "client_secret.json")
    TOKEN = os.path.join(k, "token.json")
    YORUM_DOSYA = os.path.join(k, "yorumlar.json")
    for d in (CIKTI, GECICI):
        os.makedirs(d, exist_ok=True)
    if pid != "tr" and not os.path.exists(AYAR_DOSYA):
        _profil_ayar_olustur(pid, prf["profiller"][pid])


def _profil_ayar_olustur(pid, bilgi):
    """Yeni kanalın ilk ayarları: Türkçe kanalın görüntü/ses ayarlarını alır, dile özel olanları değiştirir."""
    tr = dict(VARSAYILAN)
    tr.update(_json_oku(KOK_AYAR_DOSYA, {}))
    a = {k_: tr[k_] for k_ in ("g_ses", "hiz", "arkaplan", "altyazi", "muzik", "muzik_ses", "kapanis", "kapanis_sure",
                               "kapanis_gecis", "gizlilik", "ses_motoru", "ses_sadece_gemini", "onizle",
                               "hikaye_editor", "tema", "animasyon", "uzunluk", "yon", "surum") if k_ in tr}
    a.update(dil=bilgi.get("dil", "en"), hedef_kanal=bilgi.get("ad", ""), tur="Karışık", eslestir=False,
             plan=[{"saat": "02:00", "format": "kisa", "gunler": list(range(7))},
                   {"saat": "04:00", "format": "kisa", "gunler": list(range(7))}],
             plan_saatler=["02:00", "04:00"], plan_gun=3, plan_gorev_saat="14:00",
             stil=VARSAYILAN_STIL_EN, ses="en-US-GuyNeural", yorum_oto=False, yorum_mod="onay",
             yorum_stil=VARSAYILAN_YORUM_STIL_EN, fikir_basari=True,
             kapanis_dosya=os.path.join(profil_klasoru(pid), f"kapanis_{pid}.png"))
    if bilgi.get("tur") == "notebooklm":
        a.update(dil="tr", stil=VARSAYILAN_STIL, ses="tr-TR-AhmetNeural", muzik=False,
                 plan=[{"saat": "12:00", "format": "kisa", "gunler": list(range(7))},
                       {"saat": "19:00", "format": "kisa", "gunler": list(range(7))}],
                 plan_saatler=["12:00", "19:00"], plan_gun=2, plan_gorev_saat="11:00", ilk_yorum=True,
                 yorum_oto=True, yorum_mod="oto", yorum_stil=VARSAYILAN_YORUM_STIL_BIRADIM,
                 nblm_altyazi=False, nblm_kanca=True, nblm_rozet=True)
    _json_yaz(os.path.join(profil_klasoru(pid), "ayarlar.json"), a)


def profil_sec(pid):
    """Bir sonraki açılışta hangi kanalla başlanacağını kaydeder."""
    prf = profiller_oku()
    prf["aktif"] = pid
    _json_yaz(PROFIL_DOSYA, prf)


def profil_adi(pid=None):
    return profiller_oku()["profiller"].get(pid or AKTIF_PROFIL, {}).get("ad", "")


def T(tr, en):
    """Arayüz ve içerik metni: aktif kanalın diline göre."""
    return en if DIL == "en" else tr


def buyuk(s):
    """Altyazı/kapak büyük harfi: Türkçede i -> İ, İngilizcede normal."""
    return tr_buyuk(s) if DIL == "tr" else s.upper()


# ---------------------------------------------------------------------------
# 1. PAKETLER (eksik olan ilk açılışta otomatik kurulur)
# ---------------------------------------------------------------------------
def modul_yukle(modul, paket):
    try:
        return importlib.import_module(modul)
    except ImportError:
        print(f"[kurulum] {paket} yükleniyor...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "--upgrade", paket])
        importlib.invalidate_caches()
        return importlib.import_module(modul)


av = modul_yukle("av", "av")
imageio_ffmpeg = modul_yukle("imageio_ffmpeg", "imageio-ffmpeg")
edge_tts = modul_yukle("edge_tts", "edge-tts")
genai = modul_yukle("google.genai", "google-genai")
from google.genai import types as gtypes  # noqa: E402

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

# ---------------------------------------------------------------------------
# 2. SABİTLER VE AYARLAR
# ---------------------------------------------------------------------------
def _api_anahtari():
    """Gemini API anahtarı koda yazılmaz: önce GEMINI_API_KEY ortam değişkenine, sonra program klasöründeki
    gizli.json dosyasına bakılır ({"gemini_api_key": "..."}). gizli.json GitHub'a gönderilmez (.gitignore)."""
    anahtar = os.environ.get("GEMINI_API_KEY", "").strip()
    if anahtar:
        return anahtar
    try:
        with open(os.path.join(BASE, "gizli.json"), encoding="utf-8") as f_:
            return str(json.load(f_).get("gemini_api_key", "")).strip()
    except (OSError, ValueError):
        return ""


API_KEY = _api_anahtari()
if not API_KEY:
    print("[!] Gemini API anahtarı bulunamadı. gizli.ornek.json dosyasını gizli.json olarak kopyalayıp anahtarını "
          "yaz ya da GEMINI_API_KEY ortam değişkenini ayarla.")
MODELLER = ["gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-2.5-flash"]

SESLER = {"tr-TR-AhmetNeural": "Ahmet (erkek)", "tr-TR-EmelNeural": "Emel (kadın)"}
MOTORLAR = {"gemini": "Gemini (doğal, önerilen)", "edge": "Edge (hızlı, robotik)"}
GEMINI_SESLER = {
    "Charon": "Charon – erkek, tok ve anlatıcı",
    "Algenib": "Algenib – erkek, kalın ve pürüzlü",
    "Enceladus": "Enceladus – erkek, nefesli, gizemli",
    "Orus": "Orus – erkek, kararlı",
    "Fenrir": "Fenrir – erkek, heyecanlı",
    "Iapetus": "Iapetus – erkek, net",
    "Kore": "Kore – kadın, kararlı",
    "Sulafat": "Sulafat – kadın, sıcak",
    "Aoede": "Aoede – kadın, ferah",
    "Leda": "Leda – kadın, genç",
}
VARSAYILAN_STIL = "Gerilimli ve gizemli bir hikaye anlatıcısı gibi; akıcı, merak uyandıran, doğal bir tonla"
VARSAYILAN_STIL_EN = ("like a tense, mysterious storyteller in natural American English: smooth, intriguing, "
                      "calm but gripping")
ARKAPLANLAR = {
    "havuz": "Video havuzu (arkaplan_videolari, rastgele)",
    "uzun": "Subway Surfers (ana klasördeki video)",
    "klipler": "Klipler (hızlı geçişli)",
    "resimler": "Resimler (yakınlaşma efekti)",
    "karisik": "Karışık (klip + resim)",
}
ALTYAZILAR = {"grup": "Vurgulu grup (2-3 kelime)", "tek": "Tek kelime"}
GIZLILIK = {"public": "Herkese açık", "unlisted": "Liste dışı", "private": "Özel"}
TURLER = ["Karışık", "Korku", "Gizem", "Tarih", "Bilim kurgu", "Psikolojik gerilim",
          "Suç", "Efsane", "Uzay", "Deniz", "Kayıp şehirler"]

VARSAYILAN = {
    "tema": "acik", "fikir_basari": True, "animasyon": True, "hikaye_editor": True,
    "yorum_oto": False, "ilk_yorum": True, "nblm_altyazi": False, "nblm_kanca": True, "nblm_rozet": True, "nblm_hiz": "1.5", "hazir_onay": True, "yorum_mod": "oto", "yorum_stil": "",
    "format": "hikaye", "uzunluk": "kisa", "yon": "dikey", "ses": "tr-TR-AhmetNeural", "hiz": 15,
    "arkaplan": "havuz", "altyazi": "grup", "muzik": True, "muzik_ses": 20,
    "tur": "Karışık", "yukle": False, "gizlilik": "public",
    "oto_adet": 3, "oto_yukle": True, "oto_aralik": 0, "surum": 4,
    "ses_motoru": "gemini", "g_ses": "Enceladus", "stil": VARSAYILAN_STIL, "ses_sadece_gemini": True,
    "onizle": True, "kisayol_kuruldu": False, "hedef_kanal": "BirAdımHikayeler",
    "kapanis": True, "kapanis_sure": 4, "kapanis_gecis": "fade", "kapanis_dosya": "",
    "plan_saatler": ["12:00", "17:00", "21:00"], "plan_gun": 1, "plan_gorev_saat": "03:00",
}


def _json_oku(dosya, varsayilan):
    try:
        with open(dosya, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return varsayilan


def _json_yaz(dosya, veri):
    gecici = dosya + ".tmp"
    with open(gecici, "w", encoding="utf-8") as f:
        json.dump(veri, f, ensure_ascii=False, indent=2)
    os.replace(gecici, dosya)


def ayar_oku():
    a = dict(VARSAYILAN)
    kayitli = _json_oku(AYAR_DOSYA, {})
    a.update(kayitli)
    if kayitli and kayitli.get("surum", 1) < 2:   # eski ayar dosyası -> Subway Surfers varsayılan
        a["arkaplan"] = "uzun"
    if kayitli and kayitli.get("surum", 1) < 3:   # Gemini sese geçiş
        a["hiz"], a["ses_motoru"] = 15, "gemini"
    if kayitli and kayitli.get("surum", 1) < 4:   # müzik artık normalize ediliyor
        a["muzik_ses"] = 20
    a["surum"] = VARSAYILAN["surum"]
    if not globals().get("SENARYO_ACIK", False):
        a["format"] = "hikaye"
    if not kayitli.get("yorum_ayar_surum"):   # BirAdım: yorum cevapları açık + kanala uygun tarz (bir kez)
        try:
            if nblm_mi():
                a.update(yorum_oto=True, yorum_mod="oto", yorum_stil=VARSAYILAN_YORUM_STIL_BIRADIM)
                a["yorum_ayar_surum"] = 1
                _json_yaz(AYAR_DOSYA, dict(kayitli, **{k: a[k] for k in ("yorum_oto", "yorum_mod", "yorum_stil",
                                                                          "yorum_ayar_surum")}))
        except Exception:
            pass
    if "hazir_marka" not in kayitli:          # rozet BirAdım'a ait: varsayılan olarak sadece o kanalda açık
        try:
            a["hazir_marka"] = nblm_mi()
        except Exception:
            a["hazir_marka"] = False
    if AYAR_DOSYA != KOK_AYAR_DOSYA:       # tema gibi ortak ayarlar ana kanalın dosyasından
        kok = _json_oku(KOK_AYAR_DOSYA, {})
        for k_ in GENEL_AYARLAR:
            if k_ in kok:
                a[k_] = kok[k_]
    if AKTIF_PROFIL != "tr" and not kayitli.get("hedef_kanal"):
        a["hedef_kanal"] = profil_adi()
    return a


def ayar_yaz(a):
    _json_yaz(AYAR_DOSYA, a)
    if AYAR_DOSYA != KOK_AYAR_DOSYA:
        kok = _json_oku(KOK_AYAR_DOSYA, {})
        if any(kok.get(k_) != a.get(k_) for k_ in GENEL_AYARLAR if k_ in a):
            kok.update({k_: a[k_] for k_ in GENEL_AYARLAR if k_ in a})
            _json_yaz(KOK_AYAR_DOSYA, kok)


_gecmis_kilit = threading.Lock()


def gecmis_oku():
    return _json_oku(GECMIS_DOSYA, [])


def gecmis_sil(dosya):
    with _gecmis_kilit:
        _json_yaz(GECMIS_DOSYA, [k for k in gecmis_oku() if k.get("dosya") != dosya])


def gecmis_kaydet(kayit):
    """Aynı dosyaya ait kayıt varsa günceller, yoksa ekler."""
    with _gecmis_kilit:
        g = gecmis_oku()
        for i, k in enumerate(g):
            if k.get("dosya") == kayit.get("dosya"):
                g[i] = kayit
                break
        else:
            g.append(kayit)
        _json_yaz(GECMIS_DOSYA, g[-500:])


# ---------------------------------------------------------------------------
# 3. YARDIMCILAR
# ---------------------------------------------------------------------------
class IptalHatasi(Exception):
    """Kullanıcı işlemi iptal etti."""


IPTAL = threading.Event()


class YuklemeSiniriHatasi(Exception):
    """YouTube kanalın 24 saatlik yükleme sınırına ulaşıldı."""


def iptal_kontrol():
    if IPTAL.is_set():
        raise IptalHatasi("İşlem iptal edildi.")


def bekle_iptal(saniye):
    """time.sleep yerine: iptal edilirse beklemeyi hemen keser."""
    if IPTAL.wait(saniye):
        raise IptalHatasi("İşlem iptal edildi.")


def iptal_edilebilir(fn, *a, _zaman_asimi=None, **k):
    """Uzun süren bir çağrıyı ayrı iş parçacığında çalıştırır; iptal edilince ya da zaman aşımında
    sonucu beklemeden bırakır."""
    iptal_kontrol()
    bas = time.time()
    sonuc = {}

    def calis():
        try:
            sonuc["d"] = fn(*a, **k)
        except BaseException as e:  # noqa: B902
            sonuc["e"] = e
    t = threading.Thread(target=calis, daemon=True)
    t.start()
    while t.is_alive():
        t.join(0.2)
        iptal_kontrol()
        if _zaman_asimi and time.time() - bas > _zaman_asimi:
            raise TimeoutError(f"{int(_zaman_asimi)} sn içinde yanıt gelmedi (zaman aşımı)")
    if "e" in sonuc:
        raise sonuc["e"]
    return sonuc.get("d")


BASLIK_SINIR = 100   # YouTube'un başlık sınırı


def baslik_sinirla(metin, sinir=BASLIK_SINIR):
    """Başlığı en fazla 100 karaktere indirir: kelimenin ortasından kesmez, sondaki #shorts'u korur,
    YouTube'un kabul etmediği < > işaretlerini atar."""
    metin = re.sub(r"\s+", " ", str(metin or "").replace("<", "").replace(">", "")).strip()
    if len(metin) <= sinir:
        return metin
    ek = ""
    if metin.lower().endswith("#shorts"):
        ek, metin = " #shorts", metin[:-7].rstrip()
    yer = sinir - len(ek)
    kes = metin[:yer]
    if len(metin) > yer and " " in kes[int(yer * 0.6):]:
        kes = kes[:kes.rfind(" ")]
    return (kes.rstrip(" ,.;:-–—") + ek)[:sinir]


def tr_buyuk(s):
    """Türkçe büyük harf: i -> İ, ı -> I (Python'un upper()'ı bunu yanlış yapar)."""
    return s.replace("i", "İ").replace("ı", "I").upper()


def medya_suresi(p):
    with av.open(p) as c:
        if c.duration:
            return float(c.duration) / av.time_base
        for s in c.streams:
            if s.duration:
                return float(s.duration * s.time_base)
    return 0.0


def _dosyalar(klasor, uzantilar):
    if not os.path.isdir(klasor):
        return []
    return sorted(os.path.join(klasor, f) for f in os.listdir(klasor)
                  if f.lower().endswith(uzantilar))


VIDEO_UZ = (".mp4", ".mov", ".mkv", ".webm", ".m4v")
RESIM_UZ = (".jpg", ".jpeg", ".png", ".webp", ".bmp")
MUZIK_UZ = (".mp3", ".m4a", ".wav", ".ogg", ".aac")


def klasor_ac(p):
    try:
        if os.name == "nt":
            os.startfile(p)  # noqa
        else:
            subprocess.Popen(["xdg-open", p])
    except Exception:
        pass


def klasorde_goster(p):
    """Dosyayı Windows Gezgini'nde seçili olarak açar."""
    if os.name == "nt" and os.path.exists(p):
        subprocess.Popen(["explorer", "/select,", os.path.normpath(p)])
    else:
        klasor_ac(os.path.dirname(p))


def kucuk_resim(video, kutu=240):
    """Videodan küçük resim (PNG) çıkarır; önbellekten döner."""
    if not video or not os.path.exists(video):
        return None
    klasor = os.path.join(GECICI, "kucuk")
    os.makedirs(klasor, exist_ok=True)
    hedef = os.path.join(klasor, hashlib.md5(video.encode("utf-8")).hexdigest()[:14] + f"_{kutu}.png")
    if not os.path.exists(hedef):
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-ss", "3", "-i", video, "-frames:v", "1",
                        "-vf", f"scale={kutu}:{kutu}:force_original_aspect_ratio=decrease", hedef],
                       capture_output=True, creationflags=NO_WINDOW)
    return hedef if os.path.exists(hedef) else None


def kucuk_resim_kare(video, kutu=56):
    """Listede hizalı durması için küçük resmi kare beyaz zeminin ortasına koyar."""
    if not video or not os.path.exists(video):
        return None
    klasor = os.path.join(GECICI, "kucuk")
    os.makedirs(klasor, exist_ok=True)
    hedef = os.path.join(klasor, hashlib.md5(video.encode("utf-8")).hexdigest()[:14] + f"_k{kutu}.png")
    if not os.path.exists(hedef):
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-ss", "3", "-i", video, "-frames:v", "1", "-vf",
                        f"scale={kutu}:{kutu}:force_original_aspect_ratio=decrease,"
                        f"pad={kutu}:{kutu}:(ow-iw)/2:(oh-ih)/2:color=white", hedef],
                       capture_output=True, creationflags=NO_WINDOW)
    return hedef if os.path.exists(hedef) else None


def kisayol_olustur():
    """Masaüstüne 'Shorts Studyo' kısayolu ekler (konsol penceresi açılmadan çalışır)."""
    if os.name != "nt":
        raise RuntimeError("Kısayol sadece Windows'ta oluşturulabilir.")
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(pyw):
        pyw = sys.executable
    q = lambda x: str(x).replace("'", "''")  # noqa: E731
    ps = (
        "$d=[Environment]::GetFolderPath('Desktop');"
        "$y=Join-Path $d 'Shorts Studyo.lnk';"
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($y);"
        f"$s.TargetPath='{q(pyw)}';"
        f"$s.Arguments='\"{q(os.path.abspath(__file__))}\"';"
        f"$s.WorkingDirectory='{q(BASE)}';"
        f"$s.IconLocation='{q(yol('simge.ico'))},0';"
        "$s.Description='YouTube Shorts Hikaye Otomasyonu';"
        "$s.Save();Write-Output $y"
    )
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       creationflags=NO_WINDOW)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[-300:] or "PowerShell hatası")
    return r.stdout.strip()


# ---------------------------------------------------------------------------
# 4. GEMINI: FİKİR + HİKAYE + BAŞLIK/AÇIKLAMA
# ---------------------------------------------------------------------------
_client = None


def _istemci():
    global _client
    if _client is None:
        try:
            _client = genai.Client(api_key=API_KEY, http_options=gtypes.HttpOptions(timeout=170_000))
        except Exception:
            _client = genai.Client(api_key=API_KEY)
    return _client


_model_kapali = {}          # model -> bu zamana kadar atla (günlük kotası dolanlar)
_gemini_ses_kapali = {"kadar": 0.0, "neden": ""}


def _gemini_uret(prompt, log=print, json_mod=False):
    son_hata = None
    simdi = time.time()
    modeller = [m for m in MODELLER if _model_kapali.get(m, 0) < simdi] or MODELLER
    for model in modeller:
        for deneme in range(3):
            try:
                cfg = gtypes.GenerateContentConfig(
                    temperature=1.0,
                    response_mime_type="application/json" if json_mod else None,
                )
                r = iptal_edilebilir(_istemci().models.generate_content, model=model, contents=prompt, config=cfg,
                                     _zaman_asimi=180)
                metin = (getattr(r, "text", None) or "").strip()
                if not metin:
                    raise RuntimeError("Gemini boş yanıt döndürdü")
                return metin
            except IptalHatasi:
                raise
            except Exception as e:
                son_hata = e
                mesaj = str(e)
                kota = "429" in mesaj or "RESOURCE_EXHAUSTED" in mesaj or "quota" in mesaj.lower()
                if kota and ("PerDay" in mesaj or "exceeded your current quota" in mesaj):
                    _model_kapali[model] = time.time() + 3600   # günlük kota: 1 saat bu modeli deneme
                gecici = any(x in mesaj for x in ("500", "503", "UNAVAILABLE", "overloaded", "boş yanıt"))
                if kota and _model_kapali.get(model, 0) < time.time() and deneme < 2:
                    m = re.search(r"retry in ([\d.]+)s|retryDelay['\"]?:\s*['\"]?(\d+)", mesaj)
                    bekle = min(int(float(m.group(1) or m.group(2))) + 2, 65) if m else 30
                    log(f"[~] {model} kota sınırı, {bekle} sn bekleniyor...")
                    bekle_iptal(bekle)
                    continue
                if gecici and deneme < 2:
                    bekle_iptal(5)
                    continue
                log(f"[!] {model} kullanılamadı, sıradaki modele geçiliyor. ({mesaj[:120]})")
                break
    raise RuntimeError(f"Hiçbir Gemini modeli yanıt vermedi.\n{son_hata}")


def _json_coz(metin):
    metin = re.sub(r"^```(?:json)?\s*|\s*```$", "", metin.strip())
    try:
        veri = json.loads(metin)
    except Exception:
        m = re.search(r"\{.*\}", metin, re.S)
        if not m:
            raise RuntimeError("Gemini yanıtı okunamadı (JSON değil).")
        veri = json.loads(m.group(0))
    if isinstance(veri, list):
        veri = veri[0]
    return veri


# Kanca türleri: her fikirde rastgele 3'ü önerilir; kanal tek bir kalıba (kendi yansıması, kendi cesedi...) sıkışmasın.
KANCA_TURLERI = [
    "bir yerin uyulması gereken tuhaf kuralları ve kurallardan biri çiğnenince olanlar",
    "yanlış kişiye gelen bir mesaj, mektup ya da paket",
    "bir çocuğun ya da yaşlının bilmemesi gereken bir şeyi bilmesi",
    "gece vardiyasında ya da tuhaf bir iş ilanında fark edilen tek bir detay",
    "bir kayıp vakasında herkesin gözden kaçırdığı tek ipucu",
    "tarihi bir olayın gizlenmiş, bilinmeyen yüzü",
    "iki kötü seçenek arasında kalınan bir ahlaki ikilem",
    "bir komşunun, ev arkadaşının ya da aile üyesinin sakladığı sır",
    "kurbanın son anda fark ettiği bir tuzak ya da dolandırıcılık",
    "doğada, mağarada ya da denizde açıklanamayan bir buluntu",
    "belli bir saate kadar çözülmesi gereken bir geri sayım",
    "eski bir köy efsanesinin bugün gerçek çıkması",
    "bir hayvanın ya da evcil hayvanın tuhaf davranışının gerçek sebebi",
    "kapalı bir yerde (asansör, kabin, otel odası) kısılıp kalan yabancılar",
]

# Son konularda sık tekrarlanan motifler (anahtar kelime grupları)
MOTIFLER = {
    "kendi yansıması / kopyası / ikizi": ["yansıma", "ayna", "ikiz", "kopya", "kendi ses", "kendimi", "kendi yüz"],
    "kendi ölümü / cesedi / mezarı": ["kendi ölüm", "cesedim", "kendi ceset", "mezar", "cenaze", "ölüm ilan",
                                       "ölüm anı", "kendi cinayet", "tabut"],
    "gelecekteki ben / zaman döngüsü": ["gelecek", "zaman döngü", "döngü", "geçmişe", "henüz doğmamış"],
    "akıllı cihaz / telefon / uygulama": ["akıllı", "telefon", "uygulama", "qr", "parmak izi", "asistan",
                                          "kamera kayd", "kapı zili", "mesaj"],
    "uzay gemisi": ["uzay gemi", "yıldız gemi", "yıldızlararası", "ötegezegen"],
}


def asiri_motifler(konular, esik=3):
    """Son konularda 'esik' kez ya da daha sık geçen motiflerin adları."""
    say = {}
    for k in konular:
        kk = tr_kucuk(k or "")
        for ad, kelimeler in MOTIFLER.items():
            if any(w in kk for w in kelimeler):
                say[ad] = say.get(ad, 0) + 1
    return [ad for ad, n in say.items() if n >= esik]


def _motif_var(konu, motifler):
    kk = tr_kucuk(konu or "")
    return any(any(w in kk for w in MOTIFLER[m]) for m in motifler)


# ---------------------------------------------------------------------------
# KONU BANKASI: elle yazılmış, sonu ve mantığı baştan belli hikâye tohumları.
# Her biri: kanca (konu), adil ipucu, çözüm (insan eliyle, mantıklı ve anlamlı) ve tür.
# Yapay zeka / teknoloji / zaman döngüsü / "kendi kopyam" kalıbı YOK. Banka bitince Gemini bunları
# örnek alarak yenilerini üretir.
# ---------------------------------------------------------------------------
KONU_BANKASI = [
    {"id": 1, "tur": "Gizem",
     "konu": "Mahallenin en cimri bakkalı ölünce defterindeki kırk yıllık veresiyelerin hepsinin üstü çizilmişti.",
     "ipucu": "Çizgilerin mürekkepleri farklı renklerdeydi, yani yıllara yayılmıştı; bakkal kimseden borç istemezdi.",
     "cozum": "Bakkal borçları hiç tahsil etmemiş, her ay kendi cebinden kapatmıştı. Cimri görünmesinin sebebi, "
              "yardım ettiği yoksul ailelerin mahallede utanmamasıydı."},
    {"id": 2, "tur": "Gizem",
     "konu": "Annem öldükten sonra her ay hesabıma, gönderen adı boş, tam üç yüz on iki lira yatıyordu.",
     "ipucu": "Annemin son haftalarını geçirdiği hastane odasının numarası üç yüz on ikiydi ve odayı yaşlı bir "
              "kadınla paylaşıyordu.",
     "cozum": "Parayı annemin oda arkadaşı gönderiyordu: annem ölmeden önce kadının ilaç parasını gizlice ödemişti; "
              "kadın da bu borcu emekli maaşından bölerek annemin çocuğuna ödüyordu."},
    {"id": 3, "tur": "Efsane",
     "konu": "Köyün imamı kırk yıl boyunca her sabah ezandan önce boş bir mezarın başına ekmek bırakıyordu.",
     "ipucu": "Mezar taşında isim yoktu, sadece selin olduğu yıl yazıyordu; ekmeği her sabah biri alıyordu ve "
              "imam bunu izleyip hiç peşine düşmüyordu.",
     "cozum": "Mezar, selde kaybolan ve cesedi bulunamayan oğlu için yapılmıştı. Ekmeği alan, selden hafızasını "
              "kaybederek kurtulan ve köyün dışında çobanlık yapan oğlunun ta kendisiydi; imam onun kendisini "
              "tanımadığını bildiği için sadece ekmek bırakabiliyordu."},
    {"id": 4, "tur": "Korku",
     "konu": "Köyde kurumuş kuyuya taş atan her çocuk, ertesi sabah kapısının önünde ıslak bir taş buluyordu.",
     "ipucu": "Kuyunun hemen yanındaki evde yaşayan yaşlı kadının elleri her zaman ıslak ve çatlaktı; kızı yıllar "
              "önce o kuyuda boğulmuştu.",
     "cozum": "Taşları geri getiren yaşlı kadındı. Köy kuyuyu hiç kapatmadığı için çocukları korkutarak kuyudan "
              "uzak tutuyordu; kızının başına gelenin başka bir çocuğun başına gelmesinden korkuyordu."},
    {"id": 5, "tur": "Gerilim",
     "konu": "Dağ otelindeki odamın kapısının altından her saat titrek bir yazıyla aynı not atılıyordu: Sakın uyuma.",
     "ipucu": "Oda hafif soba kokuyordu, başım zonkluyordu; resepsiyondaki yaşlı gece bekçisi yıllar önce eşini "
              "bu otelde kaybetmişti.",
     "cozum": "Odaya karbonmonoksit sızıyordu. Notları, eşini aynı odada aynı sebeple kaybeden ve kapıyı açacak "
              "anahtarı olmayan yaşlı bekçi yazıyordu; o gece hayatımı kurtaran, yıllardır deli sanılan adamdı."},
    {"id": 6, "tur": "Suç",
     "konu": "Kayıp kızın odasındaki bütün saatler aynı dakikada, on dört yirmide durdurulmuştu.",
     "ipucu": "Servis şoförü ifadesinde kızı on dört otuzda bıraktığını söylemişti; kızın en sevdiği şey "
              "saat tamir etmekti.",
     "cozum": "Kız saatleri kaçmadan önce kendisi durdurmuştu: şoförün yalan söylediğini, onu servisten on dakika "
              "önce bir yabancının arabasına bindirdiğini göstermek için. Polis saatler sayesinde gerçek kaçırma "
              "anını ve arabayı buldu; kız sağ kurtarıldı."},
    {"id": 7, "tur": "Psikolojik gerilim",
     "konu": "Kapıcı yıllardır her gece kilitlemeden önce boş bodruma 'İyi geceler' diyordu.",
     "ipucu": "Kazan dairesinde her sabah temizlenmiş bir yemek tabağı bulunuyordu; kapıcı ekmeği hep iki "
              "kişilik alıyordu.",
     "cozum": "Bodrumda, evini kaybetmiş ve kimseye görünmekten utanan yaşlı bir adam yaşıyordu. Kapıcı onu "
              "yöneticiden gizleyip yıllarca beslemişti; korku hikâyesi sandığım şey bir iyilikti."},
    {"id": 8, "tur": "Deniz",
     "konu": "Fenerci babamın defterinde her fırtınalı geceye aynı cümle yazılmıştı: Işığı bir kez söndürdüm.",
     "ipucu": "Defterdeki tarihlerden biri, annemin beni hamile olarak köyden kaçtığı geceyle aynıydı.",
     "cozum": "O gece annemi kovalayan adamların teknesi limana yaklaşıyordu. Babam ışığı söndürerek tekneyi "
              "geri dönmeye zorlamış, annemle beni kurtarmıştı; diğer fırtınalı gecelerde de o geceyi "
              "unutmamak için ışığı bir anlığına söndürüp defterine yazıyordu."},
    {"id": 9, "tur": "Gizem",
     "konu": "Otogarda bekleyen yaşlı adam yirmi yıldır her akşam aynı otobüsü karşılıyor ama kimseyi almıyordu.",
     "ipucu": "Cebinde, kenarları yıpranmış ve tarihi yirmi yıl öncesine ait iki kişilik bir bilet vardı.",
     "cozum": "Yirmi yıl önce oğluyla kavga etmiş, oğlu o otobüsle gitmiş ve hiç dönmemişti. Adam her akşam "
              "otobüsü karşılıyordu çünkü oğluna son sözü 'Bir daha bu otobüsten inme' olmuştu; o gün otobüsten "
              "inen bir genç, adamın torunu olduğunu söyledi."},
    {"id": 10, "tur": "Korku",
     "konu": "Gece vardiyasındaki bekçi, kapalı fabrikada her gece aynı makinenin kendi kendine çalıştığını duyuyordu.",
     "ipucu": "Makinenin yanında her sabah yeni bir talaş yığını ve küçük, el yapımı bir oyuncak vardı.",
     "cozum": "Fabrikadan haksız yere atılan yaşlı usta, geceleri gizlice girip torunlarına oyuncak yapıyordu. "
              "Bekçi onu yakaladığında ihbar etmek yerine anahtarı bıraktı."},
    {"id": 11, "tur": "Suç",
     "konu": "Kuyumcu soygununda hırsız vitrindeki altınlara dokunmamış, sadece bir alyansı almıştı.",
     "ipucu": "Alyansın içinde kazınmış tarih, kuyumcunun kendi evlilik tarihinden bir gün sonrasıydı.",
     "cozum": "Alyansı alan, kuyumcunun yıllar önce terk ettiği ilk eşinin oğluydu; yüzük annesine verilmesi "
              "gereken ama kuyumcunun vitrinde sakladığı yüzüktü. Polis çocuğu buldu ama kuyumcu şikâyetini "
              "geri çekti."},
    {"id": 12, "tur": "Psikolojik gerilim",
     "konu": "Yeni taşındığım evin duvarında, her odada aynı yüksekliğe çizilmiş küçük çentikler vardı.",
     "ipucu": "Çentiklerin yanında tarih yoktu, sadece isimler; en alttaki çentik tam yerden on santim yukarıdaydı.",
     "cozum": "Çentikler, ev sahibinin büyüttüğü koruyucu aile çocuklarının boylarıydı. Her çocuk gittiğinde "
              "yeni bir oda açılmış; en alttaki çentik, ev sahibinin kaybettiği kendi bebeğine aitti."},
    {"id": 13, "tur": "Efsane",
     "konu": "Karadeniz köyünde her yıl aynı gece bütün evlerin pencerelerine birer mum konuyordu.",
     "ipucu": "Köyün yaşlıları o gece denize bakan tek evin mumunu hiç yakmıyordu; o evde yıllardır kimse "
              "oturmuyordu.",
     "cozum": "Mumlar, yıllar önce fırtınada dönmeyen balıkçılar içindi. Boş ev, o gece tekneyi denize çıkmaya "
              "zorlayan ve köyden kovulan reisin eviydi; köy onu affetmediği için evini karanlıkta bırakıyordu."},
    {"id": 14, "tur": "Gerilim",
     "konu": "Asansör iki kat arasında durduğunda içerideki yabancı panikle değil, sakince saatine baktı.",
     "ipucu": "Adamın elinde binanın elektrik dağıtım odasının anahtarı vardı ve asansör duvarına sırtını "
              "dayamıştı.",
     "cozum": "Adam binanın yeni bekçisiydi; asansörü kendisi durdurmuştu çünkü yukarıdaki dairede yangın "
              "çıktığını fark etmiş ve asansörün o kata açılmasını engellemişti. Paniklemememin tek sebebi "
              "onun sakinliğiydi."},
    {"id": 15, "tur": "Gizem",
     "konu": "Kütüphaneye kırk yıl önce ödünç verilen kitap, iade kutusunda bir mektupla geri geldi.",
     "ipucu": "Kitap, mahalledeki yetimhanenin kapandığı yıl alınmıştı; mektupta sadece 'Gecikme cezamı ödemeye "
              "geldim' yazıyordu.",
     "cozum": "Kitabı alan yetim çocuk, kitabı geri vermeye utandığı için saklamıştı. Yıllar sonra öğretmen "
              "olmuş ve gecikme cezası olarak kütüphaneye bir okuma odası bağışlamıştı."},
    {"id": 16, "tur": "Korku",
     "konu": "Kardaki ayak izleri evimin kapısına kadar geliyor ama hiçbiri geri dönmüyordu.",
     "ipucu": "İzler küçüktü, adımları kısaydı; çatı katındaki eski sandık kapağı aralıktı.",
     "cozum": "İzler, gece donmamak için evimin çatı katına sığınan komşunun küçük kızınındı. Babası onu "
              "döverken kaçmış ve günlerdir sandıkta saklanıyordu; kızı bulduğumda ilk sözü 'Lütfen beni geri "
              "verme' oldu."},
    {"id": 17, "tur": "Suç",
     "konu": "Hırsız evimden hiçbir şey almamış, sadece buzdolabını doldurup gitmişti.",
     "ipucu": "Mutfak masasında, iki ay önce işten çıkarıldığımda kimseye söylemediğim maaş bordrom açık "
              "duruyordu.",
     "cozum": "'Hırsız', işsiz kaldığımı fark eden ve gururumu kırmamak için evime yedek anahtarla giren "
              "babamdı; yıllardır konuşmadığımız babam."},
    {"id": 18, "tur": "Tarih",
     "konu": "Kurtuluş Savaşı'ndan kalma bir mektupta, cepheye giden askerin annesine tek bir sorusu vardı.",
     "ipucu": "Mektup hiç gönderilmemişti; zarfın içinde bir ceviz kabuğu ve üç saç teli vardı.",
     "cozum": "Asker okuma yazma bilmiyordu; mektubu ona arkadaşı yazmıştı. Ceviz kabuğu, annesinin evinin "
              "önündeki ağaçtandı; soru 'Ceviz bu yıl da tuttu mu?' idi. Asker dönemedi, arkadaşı mektubu "
              "yıllarca cebinde taşıyıp sonunda ağacın dibine gömdü."},
    {"id": 19, "tur": "Psikolojik gerilim",
     "konu": "Komşum her gece tam aynı saatte balkona çıkıp karşı apartmandaki boş daireye el sallıyordu.",
     "ipucu": "Boş dairenin penceresinde solmuş bir çocuk çizimi asılıydı; komşum el sallarken hep gülümsüyordu.",
     "cozum": "Karşı dairede bir zamanlar lösemi tedavisi gören ve dışarı çıkamayan bir çocuk yaşamıştı. Komşum "
              "çocukla her gece el sallaşarak arkadaş olmuştu; çocuk iyileşip taşındıktan sonra da sözünü "
              "tutuyordu çünkü çocuk 'Ben gelene kadar el sallamayı bırakma' demişti."},
    {"id": 20, "tur": "Gerilim",
     "konu": "Tren tünelde durduğunda kondüktör bütün vagonlarda tek bir kişiyi aradı: beni.",
     "ipucu": "Kondüktörün elinde benim adımın yazılı olduğu bir zarf ve hastane mührü vardı.",
     "cozum": "Kardeşim kaza geçirmişti ve kan grubu çok nadirdi. Hastane, uygun tek akrabaya ulaşmak için "
              "tren şirketini aramış; tren bir sonraki istasyonda beni ambulansa vermek için durdurulmuştu."},
    {"id": 21, "tur": "Kayıp şehirler",
     "konu": "Barajın suları çekildiğinde, otuz yıl önce sular altında kalan köyün camisinin ışığı yanıyordu.",
     "ipucu": "Minarenin içinde yeni bir akü, kıyıda ise her hafta aynı yaşlı adamın kayığı vardı.",
     "cozum": "Işığı yakan, köyden göç etmeyi reddeden son müezzindi. Her hafta kayıkla gelip lambayı yeniliyordu "
              "ki köyün eski sakinleri kıyıdan baktığında evlerini görebilsin."},
    {"id": 22, "tur": "Korku",
     "konu": "Babaannemin evindeki eski telefon, hat iptal edildiği hâlde her bayram sabahı çalıyordu.",
     "ipucu": "Telefon kablosu duvarın içinden komşu eve geçiyordu; komşunun oğlu yıllar önce babaannemin "
              "elinde büyümüştü.",
     "cozum": "Hattı iptal ettirmeyen ve faturayı gizlice ödeyen komşunun oğluydu; yurt dışından her bayram "
              "arayıp babaannemin sesini duymak için. Babaannem öldükten sonra da aramaya devam etmişti, çünkü "
              "kimse ona haber vermemişti."},
    {"id": 23, "tur": "Suç",
     "konu": "Eczacı, her ay aynı reçeteyi getiren çocuğun ilacı hiç kullanmadığını fark etti.",
     "ipucu": "Kutular hiç açılmadan geri getiriliyordu; reçetedeki doktorun imzası her seferinde biraz "
              "farklıydı.",
     "cozum": "Çocuğun annesi, yatalak yaşlı komşularının ilaçlarını almak için çocuğu kullanıyordu ama ilaçları "
              "satıyordu. Çocuk kutuları açmadan eczacıya geri getirerek yardım istiyordu; eczacı polisi aradı ve "
              "yaşlı kadın kurtarıldı."},
    {"id": 24, "tur": "Gizem",
     "konu": "Dedemin taziyesine kimsenin tanımadığı yetmiş kişi geldi ve hepsi aynı gömleği giyiyordu.",
     "ipucu": "Gömleklerin hepsinin sol cebinde aynı terzi etiketi vardı; dedem emekli bir terziydi.",
     "cozum": "Dedem yıllarca, işe girişe gidecek ama gömlek alacak parası olmayan gençlere ücretsiz gömlek "
              "dikmişti. Gelenler, o gömlekle ilk işine giren insanlardı."},
    {"id": 25, "tur": "Psikolojik gerilim",
     "konu": "Kör komşum, evine girdiğimde benim kim olduğumu adımlarımdan değil, başka bir şeyden anladı.",
     "ipucu": "Her gelişimde elimde aynı dükkândan aldığım simit poşeti vardı; komşum 'Bugün geç kaldın' dedi.",
     "cozum": "Komşum beni simit kokusundan tanıyordu. Ama 'geç kaldın' demesinin sebebi, her sabah benden önce "
              "gelen ve kendini ben diye tanıtan bir dolandırıcıydı; o adam aylardır yaşlı kadının parasını "
              "çalıyordu ve komşum bunu fark edince sadece bana söylemişti."},
    {"id": 26, "tur": "Deniz",
     "konu": "Balıkçı ağına takılan şişede, yazısı otuz yıl önceki bir çocuğa ait bir dilek vardı.",
     "ipucu": "Dilekte 'Babam denizden dönsün' yazıyordu ve altında benim mahallemin adı vardı.",
     "cozum": "Dileği yazan çocuk bendim. Otuz yıl önce babamın teknesi batmıştı; ağı çeken balıkçı, babamı o "
              "gece kurtarıp hafızasını kaybettiği için yıllarca yanında çalıştıran reisti. Şişeyi okuyunca "
              "babamın kim olduğunu anladı."},
    {"id": 27, "tur": "Gerilim",
     "konu": "Gece yarısı kapıma gelen polis, beni üç yıl önce ölen kardeşimin adıyla çağırdı.",
     "ipucu": "Polisin elindeki kimlikte kardeşimin adı vardı ama fotoğraf bir başkasına aitti.",
     "cozum": "Kardeşimin kimliği o öldükten sonra çalınmış ve bir kaçakçı tarafından kullanılıyordu. Polis "
              "adresi kimlikten bulmuştu; kardeşimin adını temize çıkarmak için polisle birlikte o adamı "
              "bulmamız gerekti."},
    {"id": 28, "tur": "Efsane",
     "konu": "Köyün çocukları, ormandaki tek ağacın altına her yıl bir ayakkabı bırakmak zorundaydı.",
     "ipucu": "Ayakkabılar her yıl kayboluyordu; ormanın öbür tarafındaki köyde çocuklar hep yalınayaktı.",
     "cozum": "Gelenek, yıllar önce iki köy arasındaki kan davasını bitirmek için başlamıştı: ayakkabıları öbür "
              "köyün yaşlıları alıyordu. Kimse bunu konuşmuyordu ama iki köy otuz yıldır tek bir kavga etmemişti."},
    {"id": 29, "tur": "Gizem",
     "konu": "Taksi şoförü beni evime bıraktığında parayı almadı ve sadece 'Borcumu ödedim' dedi.",
     "ipucu": "Dikiz aynasında solmuş bir ilkokul sınıf fotoğrafı asılıydı; öğretmen masasındaki kadın annemdi.",
     "cozum": "Şoför, annemin yıllarca beslenmesini gizlice paylaştığı yoksul öğrencisiydi. Annem öldüğünde "
              "haberi geç almış, taziyeye gelememişti; borcunu annemin çocuğunu eve götürerek ödüyordu."},
    {"id": 30, "tur": "Korku",
     "konu": "Hastanenin kapalı servisinden her gece aynı ninni sesi geliyordu.",
     "ipucu": "Ninni hep yarıda kesiliyordu; servisin temizlikçisi her sabah ağlamaklı gözlerle çıkıyordu.",
     "cozum": "Ninniyi söyleyen temizlikçiydi. Yıllar önce o serviste kaybettiği bebeği için her gece ninninin "
              "ilk yarısını söylüyor, ikinci yarısını söyleyemiyordu; o gece yanına oturup ninninin sonunu ben "
              "söyledim."},
    # --- ürpertici sonlar: tehlike gerçekti, açıklaması insan eliyle ---
    {"id": 31, "tur": "Psikolojik gerilim",
     "konu": "Kiraladığım evin her odasında, duvar kâğıdının altına farklı bir tarih yazılmıştı.",
     "ipucu": "Ev sahibi kirayı hep elden ve peşin istiyordu; komşular kiracıların hiçbirinin üç aydan fazla "
              "kalmadığını söyledi.",
     "cozum": "Tarihler, ev sahibinin gizli kameralarla izlediği önceki kiracıların evden kaçtığı günlerdi. Yatak "
              "odamın duvar kâğıdının altında da bir tarih vardı: yarın."},
    {"id": 32, "tur": "Psikolojik gerilim",
     "konu": "Bebek telsizinden, uyuyan kızımın odasında birinin kimsenin bilmediği bir ninni söylediğini duydum.",
     "ipucu": "Ninni, annemin çocukken bana söylediği ve kendi uydurduğu bir ninniydi; annem birkaç aydır "
              "unutkanlaşmıştı ve bizimle yaşıyordu.",
     "cozum": "Ninniyi söyleyen annemdi. Gece kalkıp torununun odasına gidiyor, kendini genç bir anne, kızımı da "
              "bebekken ki ben sanıyordu; beni artık tanımıyordu ama o ninniyi hiç unutmamıştı."},
    {"id": 33, "tur": "Suç",
     "konu": "Mahalledeki bütün kediler her gece aynı evin kapısının önünde toplanıyordu.",
     "ipucu": "Evin yaşlı sahibini aylardır kimse görmemişti; kapının önüne her sabah taze mama konuyordu ve "
              "kadının kızı her ay başı bankaya gidiyordu.",
     "cozum": "Yaşlı kadın aylar önce ölmüştü. Kızı, annesinin maaşını çekmeye devam etmek için ölümünü saklıyor, "
              "kimse şüphelenmesin diye kapıya annesinin her gün yaptığı gibi mama koyuyordu."},
    {"id": 34, "tur": "Suç",
     "konu": "Ölen hastanın yastığının altında, nöbetçi hemşirenin adının yazılı olduğu bir zarf vardı.",
     "ipucu": "Hasta son günlerinde ilaçlarını içmiyor, bir kutuda saklıyordu; oğlu her ziyaretinde hemşireye "
              "fazla nazik davranıyordu.",
     "cozum": "Oğlu, miras için babasının ilaçlarını değiştiriyordu. Hasta bunu fark etmiş, ilaçları saklamış ve "
              "kanıtı güvendiği tek kişiye, hemşireye bırakmıştı; zarfın içinde ilaçlar ve 'Oğluma inanma' "
              "notu vardı."},
    {"id": 35, "tur": "Gerilim",
     "konu": "Kaybolan dağcının çadırında, kaybolduğu günden sonraki üç güne ait notlar bulundu.",
     "ipucu": "Notlardaki yazı gün geçtikçe titrek değil, düzgünleşiyordu; çadırda ekip arkadaşının eldiveni "
              "vardı.",
     "cozum": "Notları dağcı değil, onu fırtınada yalnız bırakıp dönen ekip arkadaşı yazmıştı; dağcı ilk gün "
              "ölmüştü ve arkadaşı kendini aklamak için onun hâlâ yaşadığını gösteren notlar uydurmuştu."},
    {"id": 36, "tur": "Gerilim",
     "konu": "Her sabah kapıma bırakılan gazetede tek bir kelime kırmızı kalemle daire içine alınmıştı.",
     "ipucu": "Gazeteyi bırakan çocuk hep aynı saatte geliyor, gözünü karşıdaki perdeleri kapalı eve dikiyordu.",
     "cozum": "Bir haftanın kelimelerini yan yana koyunca cümle çıktı: 'Karşı evde kardeşimi tutuyorlar.' "
              "Çocuk konuşmaktan korktuğu için yardımı gazeteyle istiyordu; polis o akşam evi bastı."},
    {"id": 37, "tur": "Psikolojik gerilim",
     "konu": "Annemin eski fotoğraflarının hepsinde, arka planda aynı yabancı adam duruyordu.",
     "ipucu": "Adam her fotoğrafta biraz daha yaşlıydı; annem bir fotoğrafa uzun uzun bakıp albümü kaldırmıştı.",
     "cozum": "Adam, annemin evlenmeden önce kaçtığı ve yıllarca onu uzaktan takip eden eski nişanlısıydı. En "
              "son fotoğraf dün çekilmişti, bizim evin bahçe kapısında."},
    {"id": 38, "tur": "Suç",
     "konu": "Köprünün altında yaşayan adam on yıldır her gece aynı arabanın plakasını duvara yazıyordu.",
     "ipucu": "Plakalar hep aynıydı ve hep aynı saatte yazılıyordu; adamın cebinde bir çocuğun okul kartı vardı.",
     "cozum": "On yıl önce oğlunu ezip kaçan arabanın plakasıydı. Adam evini, işini bırakıp köprünün altında "
              "beklemiş, sonunda arabayı yakalamıştı; direksiyondaki adam şehrin tanınmış bir hâkimiydi."},
    {"id": 39, "tur": "Gerilim",
     "konu": "Otostopçu kız arabama biner binmez ilk iş arka koltuğa baktı ve rahatladı.",
     "ipucu": "Kızın çantasından bir bıçak sapı görünüyordu ve elinde, bölgede kaybolan bir kadının ilanı vardı.",
     "cozum": "Kız, ablasını öldüren ve otostopçuları arka koltukta saklanan ortağıyla kaçıran adamı arıyordu. "
              "Arka koltuğun boş olduğunu görünce o arabanın ben olmadığımı anlamıştı; bir sonraki arabaya "
              "binmek için indi."},
    {"id": 40, "tur": "Efsane",
     "konu": "Muhtar nüfus kayıtlarını açtığında, köyde kırk yıldır tek bir kişinin bile ölmediğini gördü.",
     "ipucu": "Köy mezarlığında yeni taşlar vardı ama hepsinde isim kazınmamıştı; köyün yaşlıları her ay ilçeye "
              "toplu gidiyordu.",
     "cozum": "Köy, ölenlerin ölümünü kırk yıl boyunca bildirmemiş, maaşlarını çekerek yaşamıştı. Muhtar dosyayı "
              "kapattı; listede kendi babasının adı da vardı."},
]

YASAK_KALIP = re.compile(
    r"yapay zek|yapay zeka|robot|algoritma|simülasyon|sanal gerçek|akıllı (saat|ev|asistan|telefon|kapı)|"
    r"\b(akıllı|mobil|telefon) uygulama|qr kod|hologram|zaman döngü|zaman yolculu|zamanda yolculuk|gelecekteki (ben|kendim|halim|ben)|"
    r"gelecekten gel|paralel evren|klon|rüyaymış|rüya olduğunu|rüyadan uyan|uzaylı|siborg|nöral|çip tak|"
    r"bilgisayar oyunu|matrix|veri akışı|sinyal gönder|frekans", re.I)


YASAK_KALIP_EN = re.compile(
    r"artificial intelligence|\bai\b|\ba\.i\.|robot|algorithm|simulation|virtual reality|smart (watch|home|speaker|"
    r"assistant|phone|door)|\bapp\b|qr code|hologram|time loop|time travel|future (self|me|version of me)|"
    r"from the future|parallel (universe|world)|\bclone|it was (all )?a dream|woke up from the dream|alien|cyborg|"
    r"neural|microchip|video game|matrix|data stream|signal|frequency", re.I)


def yasak_kalip_var(metin):
    m = metin or ""
    return bool(YASAK_KALIP.search(tr_kucuk(m)) or YASAK_KALIP_EN.search(m.lower()))


def yasak_kalip_bul(metin):
    m = metin or ""
    x = YASAK_KALIP.search(tr_kucuk(m)) or YASAK_KALIP_EN.search(m.lower())
    return x.group(0) if x else ""


# Sonun duygusu: art arda aynı tür son gelirse izleyici kalıbı çözer
SON_TIPI = {"iyilik": [1, 2, 4, 5, 7, 10, 14, 15, 17, 19, 24, 29],
            "aile": [3, 8, 9, 12, 18, 20, 21, 22, 26, 30, 32],
            "adalet": [6, 11, 23, 25, 27, 34, 36, 38],
            "urperti": [13, 16, 28, 31, 33, 35, 37, 39, 40]}
SON_TIPI_AD = {"iyilik": "korkutucu görünen şeyin ardından bir iyilik çıkar",
               "aile": "bir aile sırrı ya da kayıp ortaya çıkar, hüzün bırakır",
               "adalet": "gizli bir suç ortaya çıkar ve suçlu bulunur",
               "urperti": "tehlike gerçektir; son, izleyicinin içini ürperten insan eliyle bir gerçekle biter"}


def son_tipi(banka_id):
    return next((t for t, ids in SON_TIPI.items() if banka_id in ids), None)


def son_tip_sirasi(gecmis_=None):
    """Son tiplerini, son 6 videoda en az kullanılandan en çok kullanılana sıralar."""
    gecmis_ = gecmis_ if gecmis_ is not None else gecmis_oku()
    son = [k.get("son_tipi") for k in gecmis_[-6:] if k.get("son_tipi")]
    return sorted(SON_TIPI, key=lambda t: (son.count(t), t in son[-1:], random.random()))


def tum_gecmisler():
    """Bütün kanalların geçmişi: konu bankası ve benzerlik kontrolü kanallar arasında ortak çalışsın,
    aynı hikâye iki kanalda (iki dilde) yayınlanmasın."""
    hepsi = list(_json_oku(KOK_GECMIS_DOSYA, []))
    kok = yol("profiller")
    if os.path.isdir(kok):
        for pid in os.listdir(kok):
            d = os.path.join(kok, pid, "gecmis.json")
            if os.path.exists(d):
                hepsi += _json_oku(d, [])
    return hepsi


def banka_konusu(tur="Karışık"):
    """Kullanılmamış bir banka konusu seçer: son videolardaki son tipini ve türü tekrar etmemeye çalışır."""
    gecmis_ = gecmis_oku()
    hepsi = tum_gecmisler()                      # diğer kanalda kullanılan tohum burada da kullanılmaz
    kullanilan = {k.get("banka_id") for k in hepsi if k.get("banka_id")}
    kullanilan |= {b["id"] for b in KONU_BANKASI if any(b["konu"] == k.get("konu") for k in hepsi)}
    adaylar = [b for b in KONU_BANKASI if b["id"] not in kullanilan]
    if tur != "Karışık":
        adaylar = [b for b in adaylar if b["tur"] == tur] or []
    if not adaylar:
        return None
    son_turler = [k.get("banka_tur") for k in gecmis_[-2:]]
    for tip in son_tip_sirasi(gecmis_):          # en az kullanılan son tipinden başla
        tipli = [b for b in adaylar if son_tipi(b["id"]) == tip]
        if tipli:
            farkli = [b for b in tipli if b["tur"] not in son_turler]
            return random.choice(farkli or tipli)
    return random.choice(adaylar)


def banka_bul(konu):
    return next((b for b in KONU_BANKASI if b["konu"].strip() == (konu or "").strip()), None)


TOHUM_DOSYA = yol("gecici/tohumlar.json")


def _kelimeler(metin):
    return {w for w in re.findall(r"[a-zçğıöşü]+", tr_kucuk(metin or "")) if len(w) > 3}


def benzerlik(a, b):
    """İki fikrin kelime örtüşmesi (0..1); 0,3 üstü 'aynı hikâyenin çeşitlemesi' sayılır."""
    x, y = _kelimeler(a), _kelimeler(b)
    return len(x & y) / max(1, min(len(x), len(y)))


def eski_fikirler():
    """Kanalda kullanılmış konular + çözümleri (banka ve Gemini tohumları dahil)."""
    metinler = []
    for k in tum_gecmisler():
        t = tohum_bul(k.get("konu", "")) or {}
        metinler.append(f"{k.get('konu', '')} {t.get('cozum', '')}")
    return metinler


def tohum_kaydet(t):
    try:
        with open(TOHUM_DOSYA, encoding="utf-8") as f:
            v = json.load(f)
    except (OSError, ValueError):
        v = []
    v = [x for x in v if x.get("konu") != t["konu"]][-60:] + [t]
    _json_yaz(TOHUM_DOSYA, v)


def tohum_bul(konu):
    """Konunun iskeleti (ipucu + çözüm): önce banka, sonra Gemini'nin ürettikleri."""
    b = banka_bul(konu)
    if b:
        return b
    try:
        with open(TOHUM_DOSYA, encoding="utf-8") as f:
            return next((x for x in json.load(f) if x.get("konu", "").strip() == (konu or "").strip()), None)
    except (OSError, ValueError):
        return None


def eslestirilecek_konu():
    """İngilizce kanal: Türkçe kanalda yeni sistemle (banka / iskeletli fikir) üretilmiş ama bu kanalda henüz
    kullanılmamış en eski hikâyenin konusu. Eski kurallarla yazılmış Türkçe hikâyeler eşleştirilmez."""
    if AKTIF_PROFIL == "tr":
        return None
    burada = {k.get("konu") for k in gecmis_oku()}
    sinir = (datetime.datetime.now() - datetime.timedelta(days=14)).isoformat()
    for k in _json_oku(KOK_GECMIS_DOSYA, []):
        konu = k.get("konu")
        if (konu and konu not in burada and k.get("tarih", "") >= sinir and k.get("hikaye")
                and (k.get("banka_id") or tohum_bul(konu)) and not k.get("geri_cekildi")):
            return konu
    return None


def fikir_uret(tur="Karışık", log=print):
    """Önce elle yazılmış konu bankasından seçer. Banka bitince Gemini, banka örneklerini model alarak
    iskeletiyle (ipucu + çözüm) birlikte 5 aday üretir; merak, mantık, anlam ve özgünlüğe göre en iyisi seçilir."""
    if format_senaryo():
        return senaryo_fikri(log)
    if nblm_mi():
        return nblm_konu_uret(tur if tur in BIRADIM_ALANLARI else "Karışık", log=log)["konu"]
    if DIL != "tr" and ayar_oku().get("eslestir", False):
        k = eslestirilecek_konu()
        if k:
            log(f"[+] Türkçe kanaldaki hikâye İngilizce yazılacak: {k}")
            return k
    b = banka_konusu(tur)
    if b:
        log(f"[+] Konu bankasından seçildi (#{b['id']}, {b['tur']}): {b['konu']}")
        return b["konu"]
    gecmis_ = gecmis_oku()
    sonlar = [g.get("konu", "") for g in gecmis_[-25:]]
    yasak = asiri_motifler([g.get("konu", "") for g in gecmis_[-15:]])
    t = random.choice([x for x in TURLER[1:] if x not in ("Bilim kurgu", "Uzay")]) if tur == "Karışık" else tur
    hedef_tip = son_tip_sirasi(gecmis_)[0]
    eskiler = eski_fikirler()
    kancalar = random.sample(KANCA_TURLERI, 3)
    ornekler = "\n".join(f"- Konu: {b_['konu']}\n  İpucu: {b_['ipucu']}\n  Çözüm: {b_['cozum']}"
                         for b_ in random.sample(KONU_BANKASI, 3))
    iyi = [x for x in (basarili_konular() if ayar_oku().get("fikir_basari", True) else []) if not yasak_kalip_var(x)]
    ipucu = ""
    if iyi and random.random() < 0.7:      # %30 tamamen yeni yön: kanal tek tipe sıkışmasın
        ipucu = ("Kanalda en çok izlenen hikayeler şunlar; izleyicinin sevdiği his ve kanca türünü yakala ama "
                 f"aynı konuyu tekrar etme: {'; '.join(iyi)}\n")
        log("[+] Fikir, en çok izlenen videolarına göre de besleniyor.")
    yasak_metni = ""
    if yasak:
        yasak_metni = ("Bu motifler kanalda son zamanlarda çok kullanıldı, izleyici sıkılıyor; HİÇBİRİNİ kullanma: "
                       + "; ".join(yasak) + "\n")
        log(f"[~] Tekrar eden motifler bu sefer dışarıda: {', '.join(yasak)}")
    prompt = f"""YouTube Shorts için {t.lower()} temalı, Türkçe KISA HİKAYE fikirleri bul. Her fikir; merak uyandıran
bir KONU (kanca), hikayenin ilk yarısına gizlenecek adil bir İPUCU ve sondaki ÇÖZÜM'den oluşur.

Kanalın çıtası şu örneklerdir; bu kalitede ama bunlardan FARKLI fikirler üret:
{ornekler}

İyi bir fikir:
- Konu tek cümle, en fazla 18 kelime; somut bir nesne/yer/sayı içerir; izleyici "neden?" ya da "kim?" diye sorar.
{"- Gerçek hayatta geçer: Türkiye'de bir köy, mahalle, apartman, hastane, otogar, balıkçı limanı, okul, fabrika..." if DIL == "tr" else "- Gerçek hayatta geçer: dünyanın herhangi bir yerinde (her aday farklı bir ülkede). Konu, ipucu ve çözümü İNGİLİZCE yaz."}
- Çözüm İNSAN eliyle ve mantıklıdır: bir sır, bir fedakârlık, bir suçluluk, bir intikam, bir yanlış anlaşılma.
  Çözüm, başta korkutucu görünen olayın anlamını değiştirir ve izleyicide bir duygu bırakır (hüzün, adalet,
  minnet, ürperti). Tek cümlede anlatılabilir ve konudaki her tuhaflığı açıklar.
- İpucu, çözümü haklı çıkarır ama tek başına ele vermez.

KESİNLİKLE YASAK: yapay zeka, robot, algoritma, akıllı cihaz/ev/saat/asistan, telefon uygulaması, simülasyon,
zaman yolculuğu / zaman döngüsü, gelecekteki ben, kendi kopyam / ikizim / yansımam, paralel evren, uzaylı,
"hepsi rüyaymış", açıklanmayan doğaüstü olay. Teknoloji hikayenin çözümü OLAMAZ.
Adayların her biri farklı bir kanca türünden gelsin: {'; '.join(kancalar)}.
Bu seferki adayların HEPSİNDE sonun türü şu olsun: {SON_TIPI_AD[hedef_tip]}.
{yasak_metni}{ipucu}Şu konulara benzemesin: {'; '.join(s_ for s_ in sonlar if s_) or '-'}

5 aday yaz ve her birine 1-10 arası dürüst puan ver: merak (sonunu ne kadar merak ettiriyor), mantik (çözüm her
tuhaflığı tutarlı açıklıyor mu), anlam (sonda bir duygu/anlam bırakıyor mu), ozgunluk (klişelerden ne kadar uzak).
Yanıtı YALNIZCA şu JSON biçiminde ver:
{{"adaylar": [{{"konu": "...", "ipucu": "...", "cozum": "...", "merak": 8, "mantik": 9, "anlam": 8, "ozgunluk": 7}}]}}"""
    try:
        v = _json_coz(_gemini_uret(prompt, log, json_mod=True))
        adaylar = [a for a in (v.get("adaylar") or []) if str(a.get("konu", "")).strip()
                   and not yasak_kalip_var(f"{a.get('konu', '')} {a.get('cozum', '')}")]
        once = len(adaylar)
        adaylar = [a for a in adaylar if max([benzerlik(f"{a['konu']} {a.get('cozum', '')}", e) for e in eskiler]
                                             + [0]) < 0.3]
        if once > len(adaylar):
            log(f"[~] {once - len(adaylar)} aday daha önceki bir hikâyeye fazla benzediği için elendi.")
    except Exception as e:
        if isinstance(e, IptalHatasi):
            raise
        adaylar = []
    if adaylar:
        def puan(a):
            try:
                p = (float(a.get("merak", 0)) * 1.5 + float(a.get("mantik", 0)) + float(a.get("anlam", 0))
                     + float(a.get("ozgunluk", 0)))
            except (TypeError, ValueError):
                p = 0
            return p - (10 if yasak and _motif_var(a["konu"], yasak) else 0)
        adaylar.sort(key=puan, reverse=True)
        en = adaylar[0]
        konu = str(en["konu"]).strip().strip(" \"'“”*#-").splitlines()[0]
        tohum_kaydet({"konu": konu, "ipucu": str(en.get("ipucu", "")), "cozum": str(en.get("cozum", "")),
                      "tur": t, "son_tipi": hedef_tip})
        log(f"[+] {len(adaylar)} aday fikirden en iyisi seçildi (merak {en.get('merak')}, mantık {en.get('mantik')}, "
            f"anlam {en.get('anlam')}).")
        return konu
    # yedek: eski tek seferlik istek
    konu = _gemini_uret(f"YouTube Shorts için {t.lower()} temalı, merak uyandıran, özgün bir KISA HİKAYE KONUSU "
                        "bul. Tek cümle, en fazla 15 kelime. Sadece konuyu yaz.\n" + yasak_metni, log)
    return konu.strip().splitlines()[0].strip(" \"'“”*#-")


def hikaye_sorunlari(hikaye, yasak_motifler=()):
    """Yazım talimatının hikayeye sızması ya da sonun yasaklı (çok tekrar eden) kalıba dayanması."""
    sorunlar = []
    kk = tr_kucuk(hikaye or "")
    if re.search(r"ipucu gibi|ters köşe|açık soru|doruk noktası|kanca cümle", kk):
        sorunlar.append("talimattaki teknik kelimeler (ipucu, ters köşe, açık soru) hikayenin içinde geçiyor")
    if re.search(r"\bthe clue\b|plot twist|open question|the twist", (hikaye or "").lower()):
        sorunlar.append("instruction words (clue, twist, open question) leaked into the story")
    if yasak_kalip_var(hikaye):
        bul = yasak_kalip_bul(hikaye)
        sorunlar.append(f"yasak teknoloji/zaman kalıbı kullanılmış ('{bul}'); hikaye insan eliyle, gerçekçi bir "
                        "açıklamayla çözülmeli")
    cumleler = [c for c in re.split(r"(?<=[.!?…])\s+", (hikaye or "").strip()) if c]
    son = " ".join(cumleler[-2:])
    if yasak_motifler and _motif_var(son, yasak_motifler):
        sorunlar.append("son, kanalda çok kullanılan kalıba dayanıyor (" + ", ".join(
            m for m in yasak_motifler if _motif_var(son, [m])) + "); başka bir açıklama bul")
    return sorunlar


def metin_duzelt(metin):
    """Gemini'nin ara sıra bıraktığı hataları temizler: üst simge rakamlar, tamamı küçük harf cümleler."""
    metin = re.sub(r"[⁰¹²³⁴⁵⁶⁷⁸⁹]", "", metin)
    metin = re.sub(r"[ \t]+", " ", metin).strip()

    def buyut(m):
        return m.group(1) + buyuk(m.group(2))
    metin = re.sub(r"(^|[.!?…]\s+)([a-zçğıöşü])", buyut, metin)
    return metin


SHORTS_MIN, SHORTS_MAX = 40.0, 90.0   # saniye


def icerik_uret(konu, uzunluk, yon, log=print):
    kisa = uzunluk == "kisa"
    # Gemini sesi +%15 hızla ~2.6 kelime/sn okur -> 150-190 kelime ≈ 60-75 sn, 1400-1600 ≈ 10 dk
    alt, ust = (150, 190) if kisa else (1400, 1600)
    kabul_alt, kabul_ust = (125, 215) if kisa else (1250, 1800)
    ek = "" if kisa else """
Bu UZUN bir hikaye (yaklaşık 10 dakikalık anlatım):
- En az 7-8 sahne olsun; karakterlere isim ver, mekanları ve atmosferi canlı anlat, kısa diyaloglar kullan.
- Gelişme bölümünde gerilimi birkaç kez yükselt, yanlış ipuçları ve küçük sürprizler ekle.
- Tempo düşmesin; her sahne bir sonrakine merak bıraksın.
"""
    log(f"[+] Hikaye yazılıyor ({'Shorts' if kisa else 'Uzun'} format)...")
    # Son videoların konu ve SONLARINA bak: aynı tür çözüm (gelecekteki ben, yansıma...) tekrar etmesin
    son_ = gecmis_oku()[-15:]
    yasak = asiri_motifler([f"{g.get('konu', '')} {(g.get('hikaye') or '')[-220:]}" for g in son_])
    yasak_satir = ("\n- Sonun açıklaması şu kalıplara DAYANMASIN, kanalda çok kullanıldı ve izleyici tahmin ediyor: "
                   + "; ".join(yasak) + ".") if yasak else ""
    tohum = tohum_bul(konu)
    iskelet = ""
    if tohum and tohum.get("cozum"):
        iskelet = f"""
HİKAYENİN İSKELETİ (buna sadık kal; çözümü DEĞİŞTİRME, başka bir son uydurma):
- İlk yarıya fark ettirmeden yerleştirilecek detay: {tohum.get('ipucu', '')}
- Sondaki gerçek: {tohum.get('cozum', '')}
"""
    temel = f"""Konu: "{konu}"
Bu konuda YouTube {'Shorts' if kisa else 'videosu'} için {alt} ile {ust} kelime arasında, sürükleyici ve TAMAMLANMIŞ bir Türkçe {'mini ' if kisa else ''}hikaye yaz ve yayın bilgilerini hazırla.
{ek}{iskelet}
ANLAM VE MANTIK (en önemli kısım):
- Hikaye gerçek hayatta geçer; karakterlerin Türkçe isimleri, somut mekanları ve anlaşılır niyetleri vardır.
- Sondaki açıklama insan eliyle ve mantıklıdır; konudaki ve hikayedeki her tuhaflığı tutarlı biçimde açıklar.
  Hikayede söylenen hiçbir ayrıntı (yıl, yer, olay) sonra çelişkili biçimde değişmez.
- Son, başta korkutucu ya da tuhaf görünen olayın anlamını değiştirir ve izleyicide bir duygu bırakır: hüzün,
  adalet, minnet ya da ürperti. Son cümle bu duyguyu tek bir somut görüntüyle verir.
- KESİNLİKLE YASAK: yapay zeka, robot, algoritma, akıllı cihaz, telefon uygulaması, sinyal/frekans/veri,
  simülasyon, zaman yolculuğu ya da döngüsü, gelecekteki ben, kendi kopyam/yansımam, paralel evren, uzaylı,
  "rüyaymış" sonu. Teknoloji hikayenin çözümü OLAMAZ.

Hikayenin yapısı (izleyiciyi SONUNA KADAR tutmak için, hepsi zorunlu):
1. KANCA (ilk cümle, en fazla 12 kelime): Hikayenin en tuhaf ya da en tehlikeli anını somut bir detayla ver.
   Sahne tasviri, isim tanıtımı, "gece yarısıydı", "merhaba", "bugün size" gibi girişler YOK.
   Konu cümlesini aynen tekrar etme; aynı anı daha çarpıcı ve kısa söyle.
2. AÇIK SORU: İlk iki cümle izleyicinin kafasına tek, net bir soru koysun (kim, neden, nasıl ya da ne olacak).
   Bu sorunun cevabı EN SONA kadar kesinlikle verilmesin; izleyici cevabı öğrenmek için sonuna kadar izlesin.
3. TIRMANMA: Her 2-3 cümlede yeni bir bilgi, tehlike ya da ipucu gelsin; tempo hiç düşmesin. Ortalarda gerilimi
   artıran küçük bir keşif olsun ama asıl cevabı ele vermesin.
4. ADİL İPUCU: Sondaki çözümü haklı çıkaran bir ipucu hikayenin ilk yarısına fark ettirmeden yerleştirilsin;
   izleyici sonda "demek o yüzden!" desin. İpucu olmadan gelen sürpriz son YASAK.
5. ÇÖZÜM (son 2 cümle): Açık sorunun cevabı burada, tek cümlede anlaşılır biçimde verilsin. TEK bir ters köşe olsun.
   Zincirleme ters köşe, "rüyaymış / hayalmiş" sonu, birden ortaya çıkan alakasız kötü karakter, zaman paradoksuyla
   her şeyi açıklama ve uzun açıklama YASAK. Son cümle kısa ve vurucu olsun; açık uçlu, "devamı gelecek" ya da soru
   işaretiyle biten son YASAK.

Biçim kuralları:
- Kısa, akıcı cümleler; doğal duraklama için virgül ve noktayı normal kullan.
- Sadece seslendirilecek düz metin: başlık, emoji, yıldız, diyez, [sahne notu] YOK.
- Sayıları rakamla değil yazıyla yaz (örn: "sekiz bin").
- Uzunluk ÇOK ÖNEMLİ: {alt}-{ust} kelime. Daha kısa yazma.
- Bu talimattaki teknik kelimeleri (ipucu, kanca, açık soru, ters köşe, çözüm, doruk) hikayenin içinde ASLA
  kullanma; ipucunu sezdir, adını koyma. Hikaye anlatıcının ağzından doğal bir anlatım olsun.{yasak_satir}

Önce planı yap, sonra hikayeyi plana sadık kalarak yaz.
Yanıtı YALNIZCA şu JSON biçiminde ver:
{{"plan": {{"acik_soru": "izleyicinin kafasına koyduğun soru", "ipucu": "ilk yarıya gizlediğin ipucu",
           "cozum": "sorunun cevabı, tek cümle"}},
  "hikaye": "...",
  "baslik": "en fazla 60 karakter; açık soruyu ima ederek merak uyandırsın ama sonucu ASLA ele vermesin (örneğin 'hayatımı kurtardı', 'katil oymuş' gibi sonu söyleyen başlık YASAK)",
  "aciklama": "2-3 cümlelik merak uyandıran açıklama, sonunda 3-5 Türkçe hashtag",
  "etiketler": ["8-12 adet Türkçe etiket"]}}"""
    if DIL == "en":
        temel = _en_hikaye_istemi(konu, tohum, kisa, alt, ust, yasak)
    prompt, en_iyi = temel, None
    for deneme in range(3):
        try:
            v = _json_coz(_gemini_uret(prompt, log, json_mod=True))
        except RuntimeError as e:
            if "okunamadı" not in str(e) or deneme == 2:
                raise
            continue
        if not isinstance(v, dict):
            continue
        h = str(v.get("hikaye", "")).strip()
        n = len(h.split())
        fark = 0 if kabul_alt <= n <= kabul_ust else min(abs(n - kabul_alt), abs(n - kabul_ust))
        sorunlar = hikaye_sorunlari(h, yasak)
        if en_iyi is None or (len(sorunlar), fark) < en_iyi[0]:
            en_iyi = ((len(sorunlar), fark), v)
        if fark == 0 and not sorunlar:
            log(f"[+] Hikaye {n} kelime.")
            break
        if sorunlar and deneme < 2:
            log(f"[~] Hikayede sorun var ({'; '.join(sorunlar)}), düzelttiriliyor...")
            prompt = (temel + "\n\nÖNEMLİ: Önceki denemende şu sorunlar vardı, bu sefer olmasın: "
                      + "; ".join(sorunlar) + f". Uzunluk {alt}-{ust} kelime.")
            continue
        if fark == 0:
            break
        yon_ = "çok kısa" if n < kabul_alt else "çok uzun"
        log(f"[~] Hikaye {n} kelime geldi ({yon_}), yeniden yazdırılıyor...")
        if not kisa and n < kabul_alt:   # uzun hikayeyi baştan yazdırmak yerine genişlet
            prompt = (temel + f"\n\nÖNEMLİ: Aşağıdaki taslak sadece {n} kelime. Onu {alt}-{ust} kelimeye "
                      "GENİŞLET: sahneleri detaylandır, yeni olaylar ve diyaloglar ekle; ana olayı, çözümü ve "
                      f"ters köşeyi koru. Aynı JSON biçiminde döndür.\n\nTASLAK:\n{h}")
        else:
            prompt = (temel + f"\n\nÖNEMLİ: Önceki denemen {n} kelimeydi, bu {yon_}. "
                      f"Bu sefer kesinlikle {alt}-{ust} kelime yaz ve hikayeyi net bir sonla bitir.")
    if en_iyi is None:
        raise RuntimeError("Gemini'nin hikaye yanıtı okunamadı, tekrar deneyin.")
    veri = en_iyi[1]
    hikaye = metin_duzelt(str(veri.get("hikaye", "")).strip())
    plan_ = veri.get("plan") or {}
    if isinstance(plan_, dict) and plan_.get("acik_soru"):
        log(f"[+] Açık soru: {plan_.get('acik_soru')}  →  cevap sonda: {plan_.get('cozum', '')}")
    if kisa and ayar_oku().get("hikaye_editor", True):
        hikaye = hikaye_editor(konu, hikaye, tohum, plan_ if isinstance(plan_, dict) else {}, (kabul_alt, kabul_ust),
                               (alt, ust), yasak, log)
    if len(hikaye.split()) < 40:
        raise RuntimeError("Gemini hikayeyi eksik döndürdü, tekrar deneyin.")
    baslik = baslik_sinirla(str(veri.get("baslik") or konu).strip().strip('"'), BASLIK_SINIR - 8)
    aciklama = str(veri.get("aciklama", "")).strip()
    etiketler = [str(e).strip().lstrip("#") for e in (veri.get("etiketler") or []) if str(e).strip()]
    if kisa and yon == "dikey":
        if "#shorts" not in baslik.lower() and len(baslik) <= 92:
            baslik += " #shorts"
        if "#shorts" not in aciklama.lower():
            aciklama += "\n\n#shorts"
    sonuc = {"hikaye": hikaye, "baslik": baslik_sinirla(baslik), "aciklama": aciklama[:4900],
             "etiketler": etiketler[:15]}
    if tohum and tohum.get("id"):
        sonuc.update(banka_id=tohum["id"], banka_tur=tohum.get("tur"), son_tipi=son_tipi(tohum["id"]))
    elif tohum and tohum.get("son_tipi"):
        sonuc["son_tipi"] = tohum["son_tipi"]
    return sonuc


YERLER = ["a fishing village in Norway", "a small town in Louisiana", "a mountain village in Japan", "Mexico City",
          "a farm in rural Ireland", "a hospital in Seoul", "a bus station in Buenos Aires", "a ski lodge in the Alps",
          "an apartment block in Istanbul", "a coastal town in Maine", "a Scottish island", "a desert town in Arizona",
          "a village on the Black Sea coast of Turkey", "an old quarter of Lisbon", "a mining town in Wales",
          "a small town in Ontario", "a train line in rural India", "a lighthouse in Brittany, France",
          "a neighborhood in Cairo", "a village in the Carpathian mountains of Romania", "a ranch in Montana",
          "a seaside town in Cornwall", "a suburb of Melbourne", "a monastery town in Greece", "a river town in Brazil",
          "a factory town in Ohio", "a fishing harbor in Chile", "a quiet street in Kyoto", "a village in Tuscany",
          "a border town in Texas"]


def _en_hikaye_istemi(konu, tohum, kisa, alt, ust, yasak=()):
    """İngilizce kanal: hikâye aynı iskeletten DOĞRUDAN İngilizce yazılır (çeviri değil), mekân dünyadan rastgele."""
    yer = random.choice(YERLER)
    kaynak = next((k for k in reversed(_json_oku(KOK_GECMIS_DOSYA, [])) if k.get("konu") == konu and k.get("hikaye")),
                  None) if not (tohum and tohum.get("cozum")) else None
    iskelet = ""
    if tohum and tohum.get("cozum"):
        iskelet = f"""
STORY SKELETON (stay faithful to it; do NOT change the ending or invent another one). It may be written in Turkish;
adapt names, jobs and customs naturally to the new setting (e.g. a village imam can become a local priest or caretaker):
- Detail to hide quietly in the first half: {tohum.get('ipucu', '')}
- The truth revealed at the end: {tohum.get('cozum', '')}
"""
    elif kaynak:
        iskelet = f"""
SOURCE STORY (Turkish). Re-tell the same premise and the same ending in natural English; do NOT translate line by line,
move it to the new setting and make every sentence sound like a native English storyteller:
{kaynak.get('hikaye', '')}
"""
    uzun_ek = "" if kisa else """
This is a LONG story (about 10 minutes of narration): at least 7-8 scenes, named characters, vivid places and
atmosphere, short dialogue lines; raise the tension several times with false leads and small surprises.
"""
    return f"""Premise (may be in Turkish): "{konu}"
Write a gripping, COMPLETE {'short ' if kisa else ''}story in natural, native ENGLISH for a YouTube {'Short' if kisa else 'video'},
between {alt} and {ust} words, and prepare the upload info. Set the story in {yer}; use local names and concrete places.
{uzun_ek}{iskelet}
MEANING AND LOGIC (most important):
- Real-world setting, characters with clear motives; nothing said early changes or contradicts later (years, places, events).
- The ending is explained by people, logically, and explains every strange thing in the story.
- The ending changes the meaning of what seemed scary or strange and leaves a feeling: sadness, justice, gratitude or
  a chill. The last sentence delivers that feeling with one concrete image.
- STRICTLY FORBIDDEN: artificial intelligence, robots, algorithms, smart devices, phone apps, signals/frequencies/data,
  simulations, time travel or time loops, a future self, doubles/clones/reflections of yourself, parallel worlds,
  aliens, "it was all a dream". Technology can NEVER be the explanation.

STRUCTURE (keep viewers until the very end):
1. HOOK: first sentence, max 12 words, the strangest or most dangerous moment with a concrete detail. No scene-setting,
   no "It was a dark night", no greetings. Do not repeat the premise sentence word for word.
2. OPEN QUESTION: the first two sentences plant one clear question (who, why, how, what will happen) that is answered
   ONLY in the last sentences.
3. ESCALATION: every 2-3 sentences a new fact, danger or detail; the pace never drops.
4. FAIR CLUE: a detail in the first half that justifies the ending without giving it away.
5. ENDING (last 2 sentences): the answer, clear in one sentence, ONE twist only; no chained twists, no sudden unrelated
   villain, no open ending, no question mark at the end. Final sentence short and powerful.

STYLE: short, flowing sentences, written to be read aloud; plain narration only (no titles, emojis, asterisks, hashtags,
[stage notes]); write numbers as words. Length is VERY important: {alt}-{ust} words. Never write the words "clue",
"twist" or "open question" inside the story.{(' Avoid these overused endings: ' + '; '.join(yasak) + '.') if yasak else ''}

Plan first, then write the story faithfully to the plan.
Reply ONLY with this JSON:
{{"plan": {{"acik_soru": "the question you plant", "ipucu": "the clue you hide", "cozum": "the answer, one sentence"}},
  "hikaye": "...",
  "baslik": "max 60 characters, English, hints at the open question and makes people curious but NEVER reveals the ending",
  "aciklama": "2-3 sentence intriguing English description ending with 3-5 English hashtags",
  "etiketler": ["8-12 English tags"]}}"""


def hikaye_editor(konu, hikaye, tohum, plan_, kabul, hedef, yasak=(), log=print):
    """İkinci göz: hikayeyi kanca, merak, mantık, ipucu, son ve dil açısından puanlar. Zayıfsa ya da mantık
    hatası varsa iskelete sadık kalarak yeniden yazdırır. Gemini kotası yoksa hikaye olduğu gibi kalır."""
    cozum = (tohum or {}).get("cozum") or plan_.get("cozum", "")
    ipucu = (tohum or {}).get("ipucu") or plan_.get("ipucu", "")
    dil_notu = ("" if DIL == "tr" else
                "\nHikaye İNGİLİZCE. Dil ölçütünü doğal, anadil düzeyinde İngilizceye göre değerlendir; yeniden yazarsan "
                "İNGİLİZCE yaz.\n")
    prompt = f"""Sen titiz bir hikaye editörüsün. Aşağıdaki YouTube Shorts korku/gizem hikayesini değerlendir.{dil_notu}

Konu: {konu}
Olması gereken ipucu: {ipucu or '-'}
Olması gereken son: {cozum or '-'}

HİKAYE:
{hikaye}

Her ölçüte 1-10 puan ver:
- kanca: İlk cümle 12 kelimeyi geçmiyor ve hemen merak uyandırıyor mu?
- merak: İzleyicinin kafasındaki soru son cümleye kadar açık kalıyor mu?
- mantik: Çelişki, boşluk, açıklanmayan tuhaflık ya da sonradan değişen ayrıntı (yıl, yer, olay) var mı? Yoksa yüksek puan.
- ipucu: Son, ilk yarıda fark ettirmeden verilmiş bir ayrıntıyla haklı çıkıyor mu?
- son: Son tatmin edici, net ve tek cümlede anlaşılır mı; bir duygu (hüzün, adalet, minnet, ürperti) bırakıyor mu?
- dil: Doğal, akıcı, seslendirmeye uygun {'Türkçe' if DIL == 'tr' else 'İngilizce'} mi; tekrar, devrik ya da yapay cümle var mı?

Ortalama 8'in altındaysa YA DA mantık 8'in altındaysa hikayeyi YENİDEN YAZ: aynı konu ve aynı sonla, {hedef[0]}-{hedef[1]}
kelime, ilk cümle en fazla 12 kelime, son cümle kısa ve vurucu. Yapay zeka, teknoloji, zaman döngüsü, gelecekteki ben,
kendi kopyam, rüyaymış sonu KULLANMA. Talimat kelimelerini (ipucu, ters köşe, çözüm) hikayeye yazma.
İyi ise "yeni_hikaye" boş kalsın.

Yanıtı YALNIZCA şu JSON biçiminde ver:
{{"puanlar": {{"kanca": 8, "merak": 8, "mantik": 8, "ipucu": 8, "son": 8, "dil": 8}}, "sorunlar": ["..."],
  "yeni_hikaye": ""}}"""
    try:
        v = _json_coz(_gemini_uret(prompt, log, json_mod=True))
    except IptalHatasi:
        raise
    except Exception as e:
        log(f"[~] Editör kontrolü yapılamadı ({str(e)[:80]}); hikaye olduğu gibi kullanılıyor.")
        return hikaye
    if not isinstance(v, dict):
        return hikaye
    puanlar = v.get("puanlar") or {}
    try:
        ort = sum(float(x) for x in puanlar.values()) / max(1, len(puanlar))
    except (TypeError, ValueError):
        ort = 0
    sorunlar = [str(x) for x in (v.get("sorunlar") or []) if str(x).strip()]
    log(f"[+] Editör puanı: {ort:.1f}/10" + (f" · {'; '.join(sorunlar[:2])}" if sorunlar else ""))
    yeni = metin_duzelt(str(v.get("yeni_hikaye") or "").strip())
    if not yeni:
        return hikaye
    n = len(yeni.split())
    if not (kabul[0] <= n <= kabul[1]) or hikaye_sorunlari(yeni, yasak):
        log("[~] Editörün yeniden yazdığı hikaye kurallara uymadı; ilk hali kullanılıyor.")
        return hikaye
    log(f"[✓] Hikaye editör tarafından iyileştirildi ({n} kelime).")
    return yeni


# ---------------------------------------------------------------------------
# 5. SESLENDİRME (Gemini doğal ses + Whisper hizalama, yedek: edge-tts)
# ---------------------------------------------------------------------------
def tr_kucuk(s):
    return s.replace("I", "ı").replace("İ", "i").lower()


def _norm(w):
    return re.sub(r"[^\w]", "", tr_kucuk(w))


def tts_metni(metin):
    t = re.sub(r"[*#_`\"“”‘’\[\]()<>]", " ", metin)
    t = re.sub(r"\s[-–—]+\s|[–—]", ", ", t)       # konuşma tireleri -> kısa duraklama
    t = re.sub(r"…|\.{2,}", "...", t)
    return " ".join(t.split())


def _tahmini_zaman(metin, sure):
    """Kelime zamanı bulunamazsa süreyi kelime uzunluğuna göre paylaştırır."""
    k = metin.split()
    agirlik = [len(x) + 2 for x in k]
    toplam = sum(agirlik) or 1
    t, sonuc = 0.0, []
    for kelime, a in zip(k, agirlik):
        d = sure * a / toplam
        sonuc.append([t, t + d * 0.92, kelime, kelime])
        t += d
    return sonuc


def ses_son_islem(giris, cikis, tempo=1.0):
    """Hızlandırma (ses tonu bozulmadan) + YouTube seviyesinde ses yüksekliği."""
    filtre = []
    if abs(tempo - 1.0) > 0.01:
        filtre.append(f"atempo={max(0.5, min(2.0, tempo)):.3f}")
    filtre.append("loudnorm=I=-14:TP=-1.5:LRA=11")
    komut = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", giris,
             "-af", ",".join(filtre), "-ar", "44100", "-ac", "1",
             "-c:a", "libmp3lame", "-b:a", "192k", cikis]
    r = subprocess.run(komut, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       creationflags=NO_WINDOW)
    if r.returncode != 0:
        raise RuntimeError(f"Ses işleme hatası: {r.stderr.strip()[-300:]}")


# ---- 5a. Gemini TTS (doğal ses) ----
TTS_MODELLER_YENI = ["gemini-3.8-flash-tts", "gemini-3.8-flash-lite-tts"]      # interactions API
TTS_MODELLER_ESKI = ["gemini-3.1-flash-tts-preview", "gemini-2.5-flash-preview-tts"]  # generate_content


def _pcm_coz(veri):
    """Gemini'den gelen sesi (WAV ya da ham PCM) -> (pcm, örnekleme hızı)."""
    if isinstance(veri, str):
        veri = base64.b64decode(veri)
    if veri[:4] == b"RIFF":
        with wave.open(io.BytesIO(veri)) as w:
            if w.getnchannels() != 1 or w.getsampwidth() != 2:
                raise RuntimeError("Beklenmeyen ses biçimi")
            return w.readframes(w.getnframes()), w.getframerate()
    return veri, 24000


_tts_son_basarili = {"model": None}


def _tts_adaylari():
    c = _istemci()
    adaylar = []
    if hasattr(c, "interactions"):
        adaylar += [("yeni", m) for m in TTS_MODELLER_YENI]
    adaylar += [("eski", m) for m in TTS_MODELLER_ESKI]
    return adaylar


def _tts_cagir(tur, m, metin, ses, stil):
    c = _istemci()
    if tur == "yeni":
        icerik = {"type": "text", "text": metin}
        if stil:
            icerik["annotations"] = [{"type": "speech_metadata", "style": stil}]
        it = c.interactions.create(model=m, input=[{"type": "user_input", "content": [icerik]}],
                                   response_format={"type": "audio"},
                                   generation_config={"speech_config": [{"voice": ses}]})
        return _pcm_coz(it.output_audio.data)
    cfg = gtypes.GenerateContentConfig(
        response_modalities=["AUDIO"],
        speech_config=gtypes.SpeechConfig(voice_config=gtypes.VoiceConfig(
            prebuilt_voice_config=gtypes.PrebuiltVoiceConfig(voice_name=ses))))
    if DIL == "en":
        istem = f"Read the following text {stil}:\n{metin}" if stil else metin
    else:
        istem = f"Aşağıdaki metni {stil} seslendir:\n{metin}" if stil else metin
    r = c.models.generate_content(model=m, contents=istem, config=cfg)
    return _pcm_coz(r.candidates[0].content.parts[0].inline_data.data)


def _hata_ozet(e):
    m = str(e)
    if "zaman aşımı" in m:
        return "yanıt vermedi"
    if "PerDay" in m or "exceeded your current quota" in m:
        return "günlük kota doldu"
    if "429" in m or "RESOURCE_EXHAUSTED" in m:
        return "kota sınırı (dakikalık)"
    if "404" in m or "not found" in m.lower():
        return "model bulunamadı"
    if "403" in m or "permission" in m.lower():
        return "izin yok"
    return m[:90]


def _gemini_tts_parca(metin, ses, stil, model_sure=75):
    """Bir metin parçasını seslendirir. Her model kendi süresi içinde yanıt vermezse sıradakine geçilir
    (ses adı tüm Gemini ses modellerinde aynıdır, yani ses değişmez). Son çalışan model önce denenir."""
    adaylar = _tts_adaylari()
    adaylar.sort(key=lambda x: x[1] != _tts_son_basarili["model"])
    hatalar = []
    for tur, m in adaylar:
        try:
            sonuc = iptal_edilebilir(_tts_cagir, tur, m, metin, ses, stil, _zaman_asimi=model_sure)
            _tts_son_basarili["model"] = m
            return sonuc
        except IptalHatasi:
            raise
        except Exception as e:
            hatalar.append(f"{m}: {str(e)[:120]}")
    hepsi_kota = all(("429" in h or "RESOURCE_EXHAUSTED" in h or "quota" in h.lower()) for h in hatalar)
    raise RuntimeError(("429 RESOURCE_EXHAUSTED · " if hepsi_kota else "") + " | ".join(hatalar))


def gemini_ses_teshis(ses, stil, metin, sure=45):
    """Tüm Gemini ses modellerini aynı anda dener. {model: (durum, saniye, (pcm, hız) | None)} döndürür."""
    sonuclar, kilit = {}, threading.Lock()

    def dene(tur, m):
        t0 = time.time()
        try:
            veri = _tts_cagir(tur, m, metin, ses, stil)
            if len(veri[0]) < 2000:
                raise RuntimeError("boş ses")
            durum = ("✓ çalışıyor", time.time() - t0, veri)
        except Exception as e:
            durum = ("✗ " + _hata_ozet(e), time.time() - t0, None)
        with kilit:
            sonuclar[m] = durum
    adaylar = _tts_adaylari()
    isler = [threading.Thread(target=dene, args=a, daemon=True) for a in adaylar]
    for t in isler:
        t.start()
    bas = time.time()
    while any(t.is_alive() for t in isler) and time.time() - bas < sure:
        iptal_kontrol()
        time.sleep(0.2)
    with kilit:
        for _tur, m in adaylar:
            sonuclar.setdefault(m, ("✗ yanıt vermedi", sure, None))
        calisan = [m for _t, m in adaylar if sonuclar[m][2]]
    if calisan:
        _tts_son_basarili["model"] = calisan[0]
        _gemini_ses_kapali["kadar"] = 0.0
    return [(m, *sonuclar[m]) for _t, m in adaylar]


def _parcala(metin, sinir=2000):
    cumleler = re.split(r"(?<=[.!?…])\s+", metin)
    parcalar, simdiki = [], ""
    for c in cumleler:
        if simdiki and len(simdiki) + len(c) + 1 > sinir:
            parcalar.append(simdiki)
            simdiki = c
        else:
            simdiki = (simdiki + " " + c).strip()
    if simdiki:
        parcalar.append(simdiki)
    return parcalar


def gemini_tts(metin, ses, stil, wav_dosya, log=print, asama=None, sabirli=False):
    """Gemini ile seslendirir. Süre bütçesi aşılırsa hata verir.
    sabirli=True (sadece Gemini modu): kota/takılmada daha uzun bekler ve daha çok dener."""
    pcm_hepsi, hiz = b"", 24000
    parcalar = _parcala(metin)
    bas = time.time()
    if sabirli:
        butce, deneme_sayisi, kota_bekle = max(900, 300 * len(parcalar)), 4, 60
    else:
        butce, deneme_sayisi, kota_bekle = max(240, 120 * len(parcalar)), 3, 30
    for i, parca in enumerate(parcalar):
        iptal_kontrol()
        if len(parcalar) > 1:
            log(f"[+] Ses parçası {i + 1}/{len(parcalar)}...")
        if asama:
            asama(f"Seslendiriliyor (Gemini, parça {i + 1}/{len(parcalar)})", 20 + 7 * i / len(parcalar))
        for deneme in range(deneme_sayisi):
            if time.time() - bas > butce:
                raise RuntimeError(f"Gemini ses {int(butce // 60)} dakikada bitmedi")
            try:
                pcm, hiz = _gemini_tts_parca(parca, ses, stil)
                break
            except IptalHatasi:
                raise
            except Exception as e:
                kota = "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e)
                gunluk = "PerDay" in str(e) or "exceeded your current quota" in str(e)
                if gunluk or deneme == deneme_sayisi - 1 or (not kota and deneme >= 1 and not sabirli):
                    neden = ("günlük kotası doldu" if gunluk else "kota sınırına takıldı" if kota else
                             "yanıt vermedi" if "zaman aşımı" in str(e) else "hata verdi")
                    _gemini_ses_kapali.update(kadar=time.time() + 1800, neden=neden)
                    raise
                bekle = kota_bekle if kota else 10
                log(f"[~] Gemini ses {'kota sınırı' if kota else 'hatası'} ({str(e)[:80]}), {bekle} sn sonra tekrar...")
                bekle_iptal(bekle)
        if len(pcm) < 2000:
            raise RuntimeError("Gemini boş ses döndürdü")
        pcm_hepsi += pcm + (b"\x00\x00" * int(hiz * 0.15) if i < len(parcalar) - 1 else b"")
    with wave.open(wav_dosya, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(hiz)
        w.writeframes(pcm_hepsi)


# ---- 5b. Kelime zamanları (Whisper ile hizalama) ----
_whisper = None
_whisper_yok = False


def _whisper_al(log=print, cpu=False):
    global _whisper, _whisper_yok
    if _whisper_yok:
        raise RuntimeError("faster-whisper kurulamadı")
    if _whisper is None or cpu:
        try:
            modul_yukle("faster_whisper", "faster-whisper")
        except Exception:
            _whisper_yok = True
            raise
        fw = modul_yukle("faster_whisper", "faster-whisper")
        if os.name == "nt":
            for paket in ("nvidia.cublas", "nvidia.cudnn"):
                try:
                    spec = importlib.util.find_spec(paket)
                    if spec and spec.submodule_search_locations:
                        b = os.path.join(list(spec.submodule_search_locations)[0], "bin")
                        if os.path.isdir(b):
                            os.add_dll_directory(b)
                            os.environ["PATH"] = b + os.pathsep + os.environ.get("PATH", "")
                except Exception:
                    pass
        if not cpu:
            try:
                _whisper = fw.WhisperModel("small", device="cuda", compute_type="float16")
                return _whisper
            except Exception:
                pass
        log("[~] Whisper işlemcide çalışıyor (biraz yavaş).")
        _whisper = fw.WhisperModel("small", device="cpu", compute_type="int8")
    return _whisper


def _hizala(kelimeler, ws):
    """Metindeki kelimelere Whisper'ın zamanlarını eşler (yazım metinden gelir)."""
    a = [_norm(k) for k in kelimeler]
    b = [_norm(w[2]) for w in ws]
    zaman = [None] * len(kelimeler)
    for blk in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks():
        for i in range(blk.size):
            zaman[blk.a + i] = (ws[blk.b + i][0], ws[blk.b + i][1])
    n, son_t = len(kelimeler), ws[-1][1]
    i = 0
    while i < n:
        if zaman[i] is not None:
            i += 1
            continue
        j = i
        while j < n and zaman[j] is None:
            j += 1
        bas = zaman[i - 1][1] if i > 0 else 0.0
        bit = zaman[j][0] if j < n else max(son_t, bas + 0.3 * (j - i))
        agir = [len(kelimeler[k]) + 2 for k in range(i, j)]
        t, toplam = bas, sum(agir)
        for k, ag in zip(range(i, j), agir):
            d = (bit - bas) * ag / toplam
            zaman[k] = (t, t + d)
            t += d
        i = j
    zaman = _zaman_duzelt(zaman, kelimeler)
    return [[s, e, w, w] for (s, e), w in zip(zaman, kelimeler)]


def _zaman_duzelt(zaman, kelimeler):
    """Whisper bazen bir kelimeyi saniyelerce uzatıp sonrakileri geç başlatır; altyazı o kelimede takılı kalır,
    anlatıcı ise konuşmaya devam eder. Cümle parçası (virgül/nokta arası) içinde böyle bir sapma varsa, parçanın
    kelimeleri parçanın başı ile sonu arasına uzunluklarına göre eşit hızla yeniden dağıtılır."""
    n = len(zaman)
    if n < 4:
        return zaman
    agir = [len(_norm(w)) + 2 for w in kelimeler]
    oranlar = sorted((e - s_) / a_ for (s_, e), a_ in zip(zaman, agir) if e > s_)
    if not oranlar:
        return zaman
    k = oranlar[len(oranlar) // 2]          # karakter başına tipik süre (medyan)
    zaman = [list(z) for z in zaman]
    parcalar, bas = [], 0
    for i, w in enumerate(kelimeler):
        if w.rstrip("\"'”’)»").endswith((",", ".", "!", "?", ";", ":", "…")) or i == n - 1:
            parcalar.append((bas, i))
            bas = i + 1
    for a, b in parcalar:
        sapma = False
        for i in range(a, b + 1):
            sure_ = zaman[i][1] - zaman[i][0]
            if sure_ > max(0.9, 3.0 * k * agir[i]):
                sapma = True
        if not sapma:
            continue
        t0 = zaman[a][0]
        beklenen = k * sum(agir[a:b + 1])
        t1 = min(zaman[b][1], t0 + beklenen * 1.6)         # parça sonu da uzamışsa kırp
        if b + 1 < n:
            t1 = min(t1, zaman[b + 1][0])
        t1 = max(t1, t0 + 0.12 * (b - a + 1))
        toplam, t = sum(agir[a:b + 1]), t0
        for i in range(a, b + 1):
            d = (t1 - t0) * agir[i] / toplam
            zaman[i] = [t, t + d]
            t += d
    return [tuple(z) for z in zaman]


def kelime_zamanlari(ses_dosyasi, metin, log=print):
    kelimeler = metin.split()
    try:
        log("[+] Altyazı zamanlaması çıkarılıyor (Whisper)...")
        def coz(model):
            segs, _ = model.transcribe(ses_dosyasi, language=DIL, word_timestamps=True,
                                       initial_prompt=metin[:600], beam_size=5)
            sonuc = []
            for s in segs:             # her segment (~30 sn ses) arasında iptal kontrolü
                iptal_kontrol()
                sonuc += [(w.start, w.end, w.word) for w in (s.words or [])]
            return sonuc
        try:
            ws = coz(iptal_edilebilir(_whisper_al, log))
        except IptalHatasi:
            raise
        except Exception:
            ws = coz(iptal_edilebilir(_whisper_al, log, cpu=True))
        if len(ws) < max(3, len(kelimeler) // 4):
            raise RuntimeError("yetersiz kelime tanındı")
        return _hizala(kelimeler, ws)
    except IptalHatasi:
        raise
    except Exception as e:
        log(f"[~] Whisper kullanılamadı ({str(e)[:120]}), tahmini zamanlama kullanılıyor.")
        return _tahmini_zaman(metin, medya_suresi(ses_dosyasi))


# ---- 5c. Edge TTS (yedek) ----
async def _tts(metin, ses, hiz, dosya):
    try:
        com = edge_tts.Communicate(metin, ses, rate=hiz, boundary="WordBoundary")
    except TypeError:  # eski edge-tts sürümleri boundary parametresi almaz
        com = edge_tts.Communicate(metin, ses, rate=hiz)
    kelimeler = []
    with open(dosya, "wb") as f:
        async for c in com.stream():
            if c["type"] == "audio":
                f.write(c["data"])
            elif c["type"] == "WordBoundary":
                bas = c["offset"] / 1e7
                kelimeler.append([bas, bas + c["duration"] / 1e7, c["text"]])
    return kelimeler


def _metinle_eslestir(kelimeler, metin):
    """edge-tts kelimelerine metindeki noktalamayı geri ekler (grup bölmek için)."""
    parcalar = metin.split()
    j = 0
    for w in kelimeler:
        hedef = _norm(w[2])
        for k in range(j, min(j + 4, len(parcalar))):
            if _norm(parcalar[k]) == hedef:
                w.append(parcalar[k])
                j = k + 1
                break
        else:
            w.append(w[2])
    return kelimeler


def _edge_ses(temiz, dosya, ses, hiz, log=print):
    log(f"[+] Edge ile seslendiriliyor ({SESLER.get(ses, ses)}, {hiz:+d}% hız)...")
    son = None
    for s in [ses] + [x for x in SESLER if x != ses]:
        for deneme in range(2):
            try:
                kel = iptal_edilebilir(lambda: asyncio.run(_tts(temiz, s, f"{int(hiz):+d}%", dosya)))
                if os.path.exists(dosya) and os.path.getsize(dosya) > 1000:
                    if not kel:
                        log("[~] Kelime zamanları gelmedi, tahmini zamanlama kullanılıyor.")
                        return _tahmini_zaman(temiz, medya_suresi(dosya))
                    return _metinle_eslestir(kel, temiz)
            except IptalHatasi:
                raise
            except Exception as e:
                son = e
            bekle_iptal(2 + 2 * deneme)
    raise RuntimeError(f"Ses oluşturulamadı (edge-tts): {son}")


def _tempo_ayarla(ham_sure, tempo, ayar, log=print):
    """Shorts için sesi 40-90 sn aralığına çeker (ton bozulmadan hız ayarı)."""
    if ayar.get("uzunluk") != "kisa" or ham_sure <= 0:
        return tempo
    hedef = ham_sure / tempo
    if hedef > SHORTS_MAX - 1:
        yeni = min(ham_sure / (SHORTS_MAX - 1.5), 1.45)
        log(f"[~] Ses {hedef:.0f} sn olacaktı, 90 sn sınırı için biraz hızlandırıldı.")
        return yeni
    if hedef < SHORTS_MIN:
        yeni = max(ham_sure / (SHORTS_MIN + 0.5), 0.92)
        log(f"[~] Ses {hedef:.0f} sn olacaktı, 40 sn alt sınırı için hız düşürüldü.")
        return yeni
    return tempo


def ses_olustur(metin, dosya, ayar, log=print, zamanla=True, asama=None):
    """Metni seslendirir, [başlangıç, bitiş, kelime, kelime] listesi döndürür."""
    temiz = tts_metni(metin)
    if not temiz:
        raise RuntimeError("Seslendirilecek metin boş.")
    hiz = int(ayar.get("hiz", 15))
    sadece = ayar.get("ses_motoru", "gemini") == "gemini" and ayar.get("ses_sadece_gemini", True)
    ses_adi = GEMINI_SESLER.get(ayar.get("g_ses", "Charon"), ayar.get("g_ses", "Charon")).split(" –")[0]
    gemini_bekle = _gemini_ses_kapali["kadar"] - time.time()
    if sadece and gemini_bekle > 600:
        _gemini_ses_kapali["kadar"] = time.time() + 600       # sadece Gemini modunda en fazla 10 dk ara
        gemini_bekle = 600
    if ayar.get("ses_motoru", "gemini") == "gemini" and gemini_bekle > 0:
        if sadece:
            raise RuntimeError(f"Gemini sesi ({ses_adi}) az önce {_gemini_ses_kapali['neden']}; "
                               f"{max(1, round(gemini_bekle / 60))} dk sonra tekrar dene. Farklı sesle video üretilmedi.")
        log(f"[~] Gemini sesi az önce {_gemini_ses_kapali['neden']}; {int(gemini_bekle // 60) + 1} dk boyunca "
            "Edge sesi kullanılıyor.")
    elif ayar.get("ses_motoru", "gemini") == "gemini":
        try:
            ses = ayar.get("g_ses", "Charon")
            log(f"[+] Gemini ile seslendiriliyor ({GEMINI_SESLER.get(ses, ses)})...")
            ham = os.path.join(GECICI, "ham_ses.wav")
            gemini_tts(temiz, ses, ayar.get("stil", "").strip(), ham, log, asama, sabirli=sadece)
            iptal_kontrol()
            ses_son_islem(ham, dosya, _tempo_ayarla(medya_suresi(ham), 1 + hiz / 100, ayar, log))
            log(f"[+] Ses hazır ({medya_suresi(dosya):.0f} sn).")
            if asama and zamanla:
                asama("Altyazı zamanlaması (Whisper)", 28)
            return kelime_zamanlari(dosya, temiz, log) if zamanla else []
        except IptalHatasi:
            raise
        except Exception as e:
            if sadece:
                raise RuntimeError(f"Gemini sesi ({ses_adi}) alınamadı, farklı sesle video üretilmedi. "
                                   f"Kota dolmuş olabilir; biraz sonra tekrar dene. ({str(e)[:160]})")
            log(f"[!] Gemini ses başarısız, Edge'e geçiliyor. ({str(e)[:200]})")
    iptal_kontrol()
    if asama:
        asama("Seslendiriliyor (Edge)", 24)
    ham = os.path.join(GECICI, "ham_ses.mp3")
    kel = _edge_ses(temiz, ham, ayar.get("ses", "tr-TR-AhmetNeural"), hiz, log)
    tempo = _tempo_ayarla(medya_suresi(ham), 1.0, ayar, log)
    ses_son_islem(ham, dosya, tempo)
    return [[w[0] / tempo, w[1] / tempo, *w[2:]] for w in kel]



# ---------------------------------------------------------------------------
# 6. ALTYAZI (ASS)
# ---------------------------------------------------------------------------
VURGU = r"{\1c&H00E1FF&}"      # sarı (ASS renkleri BGR)
BEYAZ = r"{\1c&HFFFFFF&}"
POP = r"{\fscx116\fscy116\t(0,110,\fscx100\fscy100)}"


def _ass_zaman(t):
    cs = int(round(max(t, 0) * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def _goster(k):
    k = re.sub(r"[{}\\]", "", k.strip().strip(".,;:!?\"'“”‘’…()-–—"))
    return buyuk(k)


def altyazi_yaz(kelimeler, W, H, stil, dosya, sayaclar=None):
    """sayaclar: [(bas, bit, "40. GÜN"), ...] verilirse sol üstte gün sayacı da yazılır (çizimli senaryo)."""
    dikey = H > W
    taban = W if dikey else H
    fs = int(taban * (0.092 if stil == "tek" else 0.074))
    mv = int(H * (0.40 if dikey else 0.12))   # dikeyde ekranın ortası: oyun karakterinin üstünde
    if sayaclar:
        mv = int(H * (0.24 if dikey else 0.08))   # çizimin üstünü kapatmasın: alt kısım
    sfs = int(taban * 0.068)
    satirlar = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}",
        "WrapStyle: 0", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,Arial,{fs},&H00FFFFFF,&H000000FF,&H00000000,&H96000000,"
        f"-1,0,0,0,100,100,1,0,1,7,4,2,70,70,{mv},1",
        f"Style: Sayac,Arial,{sfs},&H00FFFFFF,&H000000FF,&H40141016,&H00000000,"
        f"-1,0,0,0,100,100,2,0,3,{max(10, sfs // 4)},0,7,{int(W * 0.06)},70,{int(H * 0.075)},1",
        "", "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    k = []
    for w in kelimeler:
        g = _goster(w[2])
        if g:
            k.append((w[0], w[1], g, w[3] if len(w) > 3 else w[2]))
    olaylar = []

    if stil == "tek":
        for i, (s, e, t, _) in enumerate(k):
            sonraki = k[i + 1][0] if i + 1 < len(k) else None
            bit = sonraki if sonraki is not None and sonraki - e < 0.35 else e + 0.15
            if sonraki is not None:
                bit = min(bit, sonraki)
            olaylar.append((s, bit, POP + t))
    else:
        gruplar, g = [], []
        for i, w in enumerate(k):
            g.append(w)
            karakter = sum(len(x[2]) for x in g) + len(g) - 1
            sonraki = k[i + 1] if i + 1 < len(k) else None
            kes = (len(g) >= 3 or karakter >= 15 or w[3].rstrip()[-1:] in ".!?…,;:"
                   or sonraki is None or sonraki[0] - w[1] > 0.45
                   or (sonraki and karakter + len(sonraki[2]) + 1 > 18))
            if kes:
                gruplar.append(g)
                g = []
        for gi, grup in enumerate(gruplar):
            sonraki_bas = gruplar[gi + 1][0][0] if gi + 1 < len(gruplar) else None
            for j, w in enumerate(grup):
                bas = w[0]
                if j + 1 < len(grup):
                    bit = grup[j + 1][0]
                else:
                    bit = w[1] + 0.30
                    if sonraki_bas is not None:
                        bit = min(bit, sonraki_bas)
                metin = " ".join((VURGU + x[2] + BEYAZ) if x is w else x[2] for x in grup)
                olaylar.append((bas, bit, (POP if j == 0 else "") + metin))

    for s, e, t in olaylar:
        if e - s < 0.04:
            e = s + 0.04
        satirlar.append(f"Dialogue: 0,{_ass_zaman(s)},{_ass_zaman(e)},Default,,0,0,0,,{t}")
    for s, e, t in sayaclar or []:
        t = re.sub(r"[{}\\]", "", str(t)).strip()
        if t:
            satirlar.append(f"Dialogue: 1,{_ass_zaman(s)},{_ass_zaman(e)},Sayac,,0,0,0,,"
                            r"{\fad(120,0)\fscx125\fscy125\t(0,200,\fscx100\fscy100)}" + t)
    with open(dosya, "w", encoding="utf-8") as f:
        f.write("\n".join(satirlar) + "\n")


# ---------------------------------------------------------------------------
# 7. ARKA PLAN + RENDER
# ---------------------------------------------------------------------------
_sure_onbellek = {}


def _sure(p):
    if p not in _sure_onbellek:
        try:
            _sure_onbellek[p] = medya_suresi(p)
        except Exception:
            _sure_onbellek[p] = 0.0
    return _sure_onbellek[p]


def _cift(x):
    return int(x) // 2 * 2


def uzun_bg_bul():
    """Ana klasördeki arka plan videosu: önce arkaplan.mp4, yoksa klasördeki en uzun video."""
    if os.path.exists(UZUN_BG) and _sure(UZUN_BG) > 60:
        return UZUN_BG
    adaylar = [p for p in _dosyalar(BASE, VIDEO_UZ) if _sure(p) > 60]
    return max(adaylar, key=_sure) if adaylar else None


def _video_boyut(p):
    try:
        with av.open(p) as c:
            v = c.streams.video[0]
            if v.width and v.height:
                return v.width, v.height
    except Exception:
        pass
    try:  # yedek: ffmpeg'in dosya bilgisinden oku
        r = subprocess.run([FFMPEG, "-hide_banner", "-i", p], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
        m = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", r.stderr)
        if m:
            return int(m.group(1)), int(m.group(2))
    except Exception:
        pass
    return None


def _sigdir(W, H, kb):
    """Kaynak videoyu hedef boyuta getirir. Dikey video yatay çıktıya girerse kırpmak yerine
    ortada tam boy gösterir, yanları aynı videonun bulanık haliyle doldurur."""
    son = "setsar=1,format=yuv420p"
    if kb and kb[0] / kb[1] < 0.75 * (W / H):
        w4, h4 = _cift(W / 4), _cift(H / 4)
        return (f"fps=30,split=2[bA][bB];"
                f"[bA]scale={w4}:{h4}:force_original_aspect_ratio=increase,crop={w4}:{h4},"
                f"boxblur=8:2,scale={W}:{H},eq=brightness=-0.15[bZ];"
                f"[bB]scale=-2:{H}[bF];[bZ][bF]overlay=(W-w)/2:0,{son}")
    return f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps=30,{son}"


_son_havuz_videosu = {"yol": None}


_acilmayan = set()          # bu bilgisayardaki ffmpeg'in çözemediği videolar (oturum boyunca atlanır)
_video_bilgi_onbellek = {}
KOLAY_KODEKLER = ("h264", "hevc", "mpeg4", "vp8", "vp9")


def video_bilgi(p):
    """Kodek, boyut ve kare hızı (PyAV ile, dosyayı çözmeden)."""
    if p not in _video_bilgi_onbellek:
        try:
            with av.open(p) as c:
                v = c.streams.video[0]
                fps = float(v.average_rate or v.guessed_rate or 30)
                _video_bilgi_onbellek[p] = {"kodek": v.codec_context.name, "w": v.codec_context.width,
                                            "h": v.codec_context.height, "fps": fps}
        except Exception:
            _video_bilgi_onbellek[p] = {}
    return _video_bilgi_onbellek[p]


def agir_video_mu(p):
    """4K, 60 fps ya da AV1 gibi ağır/zor kodekli video: render'dan önce kesitini hafif biçime çevirmek gerekir."""
    b = video_bilgi(p)
    return bool(b) and (b.get("kodek") not in KOLAY_KODEKLER or max(b.get("w", 0), b.get("h", 0)) > 2000
                        or b.get("fps", 30) > 31)


def arkaplan_kesit_hazirla(kaynak, bas, sure, W, H, log=print):
    """Ağır videonun sadece kullanılacak kesitini (ör. 60 sn) hedef boyutta, 30 fps H.264'e çevirir.
    Böylece 1 saatlik 4K/AV1 video yerine birkaç MB'lık bir kesit render'a girer."""
    hedef = os.path.join(GECICI, "bg_kesit.mp4")
    vf = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps=30,format=yuv420p"
    komut = [FFMPEG, "-y", "-loglevel", "error", "-ss", f"{bas:.3f}", "-t", f"{sure + 0.5:.3f}", "-i", kaynak,
             "-an", "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", hedef]
    bas_t = time.time()
    r = iptal_edilebilir(subprocess.run, komut, capture_output=True, text=True, creationflags=NO_WINDOW,
                         _zaman_asimi=900)
    if r.returncode != 0 or not os.path.exists(hedef) or os.path.getsize(hedef) < 10000:
        raise RuntimeError((r.stderr or "")[-300:] or "kesit oluşturulamadı")
    log(f"[+] Ağır arka plan videosunun kesiti hazırlandı ({time.time() - bas_t:.0f} sn).")
    return hedef


def havuz_videolari():
    return [p for p in _dosyalar(HAVUZ, VIDEO_UZ) if _sure(p) > 1 and p not in _acilmayan]


def arkaplan_kur(kaynak, sure, W, H, log=print):
    kirp = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
            f"setsar=1,fps=30,format=yuv420p")
    girisler, filtre = [], []
    if kaynak == "havuz":
        videolar = havuz_videolari()
        while videolar:
            secenek = [v for v in videolar if v != _son_havuz_videosu["yol"]] or videolar
            secilen = random.choice(secenek)
            _son_havuz_videosu["yol"] = secilen
            vs = _sure(secilen)
            if agir_video_mu(secilen):
                b_ = video_bilgi(secilen)
                bas = random.uniform(0, vs - sure - 1) if vs > sure + 2 else 0.0
                log(f"[+] Arka plan: {os.path.basename(secilen)} ({b_.get('kodek', '?').upper()} "
                    f"{b_.get('w')}x{b_.get('h')} {b_.get('fps', 0):.0f} fps), {int(bas // 60)}:{int(bas % 60):02d} "
                    "noktasından; önce sadece gereken kesit hafif biçime çevriliyor...")
                try:
                    kesit = arkaplan_kesit_hazirla(secilen, bas, sure, W, H, log)
                except IptalHatasi:
                    raise
                except Exception as e:
                    _acilmayan.add(secilen)
                    videolar = [v for v in videolar if v != secilen]
                    log(f"[!] {os.path.basename(secilen)} bu bilgisayarda açılamadı ({str(e)[:120]}); "
                        "havuzdan başka video seçiliyor. Bu videoyu MP4 (H.264) olarak indirmen önerilir.")
                    continue
                girisler += ["-i", kesit]
                filtre.append("[0:v]setsar=1,fps=30,format=yuv420p[bg]")
                return girisler, filtre
            if vs > sure + 2:
                bas = random.uniform(0, vs - sure - 1)
                girisler += ["-ss", f"{bas:.3f}", "-t", f"{sure + 0.5:.3f}", "-i", secilen]
                log(f"[+] Arka plan: {os.path.basename(secilen)} ({len(videolar)} videoluk havuzdan), "
                    f"{int(bas // 60)}:{int(bas % 60):02d} noktasından.")
            else:   # video kısa: baştan döngüye al
                girisler += ["-stream_loop", "-1", "-t", f"{sure + 0.5:.3f}", "-i", secilen]
                log(f"[+] Arka plan: {os.path.basename(secilen)} ({len(videolar)} videoluk havuzdan, "
                    f"{vs:.0f} sn olduğu için döngüde).")
            filtre.append(f"[0:v]{_sigdir(W, H, _video_boyut(secilen))}[bg]")
            return girisler, filtre
        log("[!] arkaplan_videolari klasöründe kullanılabilir video yok, Subway Surfers (arkaplan.mp4) kullanılıyor.")
        kaynak = "uzun"
    havuz = []
    uzun = uzun_bg_bul()
    uzun_var = uzun is not None
    if kaynak == "uzun" and not uzun_var:
        log("[!] Ana klasörde arka plan videosu bulunamadı, bg_klipler kullanılıyor.")
        kaynak = "klipler"
    if kaynak in ("klipler", "karisik"):
        havuz += [("v", p) for p in _dosyalar(KLIP, VIDEO_UZ) if _sure(p) > 1.5]
    if kaynak in ("resimler", "karisik"):
        havuz += [("r", p) for p in _dosyalar(RESIM, RESIM_UZ)]

    if kaynak == "uzun" or not havuz:
        if kaynak != "uzun":
            log("[!] Seçilen arka plan klasörü boş, arkaplan.mp4 deneniyor.")
        if uzun_var:
            bs = _sure(uzun)
            bas = random.uniform(0, bs - sure - 1) if bs > sure + 2 else 0.0
            log(f"[+] Arka plan: {os.path.basename(uzun)}, {int(bas // 60)}:{int(bas % 60):02d} "
                f"noktasından başlayıp {sure:.0f} sn kesintisiz.")
            girisler += ["-ss", f"{bas:.3f}", "-t", f"{sure + 0.5:.3f}", "-i", uzun]
            filtre.append(f"[0:v]{_sigdir(W, H, _video_boyut(uzun))}[bg]")
        else:
            log("[!] Arka plan bulunamadı, düz renk kullanılıyor.")
            girisler += ["-f", "lavfi", "-i", f"color=c=0x12141c:s={W}x{H}:r=30:d={sure + 0.5:.3f}"]
            filtre.append("[0:v]format=yuv420p[bg]")
        return girisler, filtre

    kisa = sure <= 75
    hedef = sure + 0.5
    toplam, i, onceki, etiketler = 0.0, 0, None, []
    while toplam < hedef and i < 60:
        secenek = [h for h in havuz if h != onceki] or havuz
        tur, p = random.choice(secenek)
        onceki = (tur, p)
        L = random.uniform(2.8, 4.8) if kisa else random.uniform(5.0, 8.0)
        L = min(L, hedef - toplam) if hedef - toplam > 1.0 else hedef - toplam + 0.3
        if tur == "v":
            ds = _sure(p)
            L = min(L, ds - 0.2)
            bas = random.uniform(0, max(0.0, ds - L - 0.2))
            girisler += ["-ss", f"{bas:.3f}", "-t", f"{L + 0.2:.3f}", "-i", p]
            filtre.append(f"[{i}:v]{kirp},trim=duration={L:.3f},setpts=PTS-STARTPTS[p{i}]")
        else:
            W2, H2 = _cift(W * 1.2), _cift(H * 1.2)
            if random.random() < 0.5:
                z = "min(zoom+0.0009,1.18)"
            else:
                z = "if(lte(zoom,1.0),1.18,max(1.001,zoom-0.0009))"
            girisler += ["-loop", "1", "-framerate", "30", "-t", f"{L + 0.2:.3f}", "-i", p]
            filtre.append(
                f"[{i}:v]scale={W2}:{H2}:force_original_aspect_ratio=increase,crop={W2}:{H2},"
                f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps=30,"
                f"setsar=1,format=yuv420p,trim=duration={L:.3f},setpts=PTS-STARTPTS[p{i}]")
        etiketler.append(f"[p{i}]")
        toplam += L
        i += 1
    filtre.append(f"{''.join(etiketler)}concat=n={len(etiketler)}:v=1:a=0[bg]")
    log(f"[+] Arka plan: {len(etiketler)} parça ({ARKAPLANLAR.get(kaynak, kaynak)}).")
    return girisler, filtre


def _font_hazirla():
    hedef = os.path.join(GECICI, "fonts")
    os.makedirs(hedef, exist_ok=True)
    if not os.path.exists(os.path.join(hedef, "arialbd.ttf")):
        for kaynak in ("C:/Windows/Fonts/arialbd.ttf", yol("fonts_tmp", "arialbd.ttf")):
            if os.path.exists(kaynak):
                shutil.copy(kaynak, hedef)
                break


GECISLER = {
    "fade": "Yumuşak geçiş (önerilen)",
    "fadewhite": "Beyaza açılarak",
    "fadeblack": "Siyahtan geçerek",
    "dissolve": "Çözülerek",
    "circleopen": "Daire şeklinde açılarak",
    "smoothup": "Yukarı kayarak",
    "radial": "Saat gibi dönerek",
}


def kapanis_bul(ayar):
    """Kapanış kartı: ayarda seçilen dosya, yoksa ana klasördeki ilk resim."""
    secili = ayar.get("kapanis_dosya") or ""
    if secili and os.path.exists(secili):
        return secili
    adaylar = _dosyalar(BASE, RESIM_UZ)
    return adaylar[0] if adaylar else None


def _kapanis_hazirla(kart, W, H):
    """Kartı hedef boyuta bir kez hazırlar (önbellekli). Dikey kart yatay videoya girerse
    ortada durur, yanları kartın bulanık haliyle dolar."""
    anahtar = hashlib.md5(f"{kart}|{os.path.getmtime(kart)}|{W}x{H}".encode("utf-8")).hexdigest()[:14]
    hedef = os.path.join(GECICI, f"kapanis_{anahtar}.png")
    if os.path.exists(hedef):
        return hedef
    kb = _video_boyut(kart)
    if kb and kb[0] / kb[1] < 0.75 * (W / H):
        w4, h4 = _cift(W / 4), _cift(H / 4)
        f = (f"[0:v]split=2[a][b];[a]scale={w4}:{h4}:force_original_aspect_ratio=increase,crop={w4}:{h4},"
             f"boxblur=10:2,scale={W}:{H},eq=brightness=-0.06[z];[b]scale=-2:{H}[k];"
             f"[z][k]overlay=(W-w)/2:0,format=rgb24[o]")
    else:
        f = f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},format=rgb24[o]"
    r = subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", kart, "-filter_complex", f, "-map", "[o]",
                        "-frames:v", "1", hedef], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", creationflags=NO_WINDOW)
    if r.returncode != 0 or not os.path.exists(hedef):
        raise RuntimeError(f"Kapanış kartı hazırlanamadı: {r.stderr.strip()[-200:]}")
    return hedef


def _kapanis_ekle(girisler, filtre, ana_etiket, ana_sure, W, H, ayar, log=print):
    """ana_etiket videosunun sonuna kapanış kartını ekler. (yeni etiket, toplam süre) döndürür.
    Kapanış açıksa kart her videoda mutlaka eklenir; eklenemiyorsa hata verir (kapanışsız video çıkmaz)."""
    if not ayar.get("kapanis", True):
        return ana_etiket, ana_sure
    kart = kapanis_bul(ayar)
    if not kart:
        raise RuntimeError("Kapanış kartı bulunamadı. Ana klasöre kartı koy ya da Ayarlar'dan seç "
                           "(kapanışsız video üretilmedi).")
    hazir = _kapanis_hazirla(kart, W, H)
    D = float(ayar.get("kapanis_sure", 4))
    gecis = ayar.get("kapanis_gecis", "fade")
    oi = girisler.count("-i")
    girisler += ["-loop", "1", "-framerate", "30", "-t", f"{D + 0.3:.3f}", "-i", hazir]
    kart_zinciri = (f"[{oi}:v]zoompan=z='min(zoom+0.0005,1.06)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:"
                    f"s={W}x{H}:fps=30,setsar=1,format=yuv420p,trim=duration={D:.3f},setpts=PTS-STARTPTS,"
                    f"fade=t=out:st={D - 0.6:.3f}:d=0.6")
    if ayar.get("_kapanis_yedek"):
        # Yedek yöntem: video siyaha kararır, kart siyahtan belirir (concat; kare hızı eşleşmesi gerektirmez)
        filtre.append(
            f"[{ana_etiket}]trim=duration={ana_sure:.3f},setpts=PTS-STARTPTS,format=yuv420p,setsar=1,"
            f"fade=t=out:st={max(0.0, ana_sure - 0.5):.3f}:d=0.5[km];"
            f"{kart_zinciri},fade=t=in:st=0:d=0.5[ko];"
            f"[km][ko]concat=n=2:v=1:a=0,fps=30[kv]")
        log(f"[+] Kapanış (yedek geçiş: siyahtan, {D:.0f} sn): {os.path.basename(kart)}")
        return "kv", ana_sure + D
    fd = min(1.0, D / 2)
    filtre.append(
        f"[{ana_etiket}]trim=duration={ana_sure:.3f},setpts=PTS-STARTPTS,settb=AVTB,format=yuv420p,fps=30[km];"
        f"{kart_zinciri},settb=AVTB,fps=30[ko];"
        f"[km][ko]xfade=transition={gecis}:duration={fd:.2f}:offset={ana_sure - fd:.3f}[kv]")
    log(f"[+] Kapanış: {os.path.basename(kart)} ({GECISLER.get(gecis, gecis).lower()}, {D:.0f} sn)")
    return "kv", ana_sure - fd + D


def _render(girisler, filtre, haritalar, toplam, cikti, log=print, ilerleme=None, ses=True):
    hata_dosya = os.path.join(GECICI, "ffmpeg_hata.txt")

    def calistir(kodlayici):
        komut = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-nostats", "-progress", "pipe:1",
                 *girisler, "-filter_complex", ";".join(filtre)]
        for m in haritalar:
            komut += ["-map", m]
        komut += ["-t", f"{toplam:.3f}", *kodlayici, "-pix_fmt", "yuv420p", "-r", "30"]
        komut += ["-c:a", "aac", "-b:a", "192k"] if ses else ["-an"]
        komut += ["-movflags", "+faststart", cikti]
        with open(hata_dosya, "w", encoding="utf-8", errors="replace") as he:
            p = subprocess.Popen(komut, cwd=GECICI, stdout=subprocess.PIPE, stderr=he, text=True,
                                 encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
            for satir in p.stdout:
                if IPTAL.is_set():
                    p.kill()
                    break
                if satir.startswith("out_time_ms=") and ilerleme:
                    try:
                        ilerleme(min(int(satir.split("=")[1]) / 1e6 / toplam, 1.0))
                    except ValueError:
                        pass
            p.wait()
        with open(hata_dosya, encoding="utf-8", errors="replace") as f:
            return p.returncode, f.read()

    def iptal_temizle():
        if IPTAL.is_set():
            try:
                os.remove(cikti)
            except OSError:
                pass
            iptal_kontrol()

    iptal_kontrol()
    kod, hata = calistir(["-c:v", "h264_nvenc", "-preset", "p6", "-cq", "20", "-b:v", "0", "-profile:v", "high"])
    iptal_temizle()
    if kod != 0:
        log("[~] NVENC kullanılamadı, işlemci ile render ediliyor (daha yavaş)...")
        kod, hata = calistir(["-c:v", "libx264", "-preset", "medium", "-crf", "20", "-profile:v", "high"])
        iptal_temizle()
        if kod != 0:
            raise RuntimeError(f"Render başarısız:\n{hata.strip()[-600:]}")


def muzik_hazirla(m, log=print):
    """Müziği standart seviyeye (-16 LUFS) getirir, baştaki/sondaki sessizliği kırpar. Önbellekli."""
    anahtar = hashlib.md5(f"{m}|{os.path.getmtime(m)}".encode("utf-8")).hexdigest()[:14]
    hedef = os.path.join(GECICI, f"muzik_{anahtar}.m4a")
    if os.path.exists(hedef):
        return hedef
    log(f"[+] Müzik hazırlanıyor (ses seviyesi eşitleniyor): {os.path.basename(m)}")
    sessiz = "silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.05"
    af = f"{sessiz},areverse,{sessiz},areverse,loudnorm=I=-16:TP=-2:LRA=11"
    r = subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", m, "-af", af, "-ar", "44100", "-ac", "2",
                        "-c:a", "aac", "-b:a", "192k", hedef], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
    if r.returncode != 0 or not os.path.exists(hedef):
        log(f"[!] Müzik hazırlanamadı, olduğu gibi kullanılıyor. ({r.stderr.strip()[-150:]})")
        return m
    return hedef


def muzik_lisansi(m):
    """Müziğin yanındaki aynı adlı .txt Pixabay lisans sertifikasını okur."""
    if not m:
        return None
    txt = os.path.splitext(m)[0] + ".txt"
    if not os.path.exists(txt):
        return None
    with open(txt, encoding="utf-8", errors="replace") as f:
        metin = f.read()

    def alan(ad):
        mm = re.search(ad + r"\s*:\s*\n\s*(.+)", metin)
        return mm.group(1).strip() if mm else ""
    lisansor = alan("Licensor's Username")
    sanatci = re.sub(r"-\d+/?$", "", lisansor.rstrip("/").rsplit("/", 1)[-1]) if lisansor else ""
    return {"dosya": os.path.basename(m), "baslik": alan("Audio File Title") or os.path.basename(m),
            "sanatci": sanatci, "url": alan("Audio File URL"), "lisans": txt}


def itiraz_metni(kayit):
    """YouTube Content ID itirazına yapıştırılacak metin."""
    mz = kayit.get("muzik") or {}
    lisans = mz.get("lisans")
    if not lisans or not os.path.exists(lisans):
        return None
    with open(lisans, encoding="utf-8", errors="replace") as f:
        sertifika = f.read().strip()
    return (f"I have a valid license to use this music. The track \"{mz.get('baslik')}\" by "
            f"{mz.get('sanatci')} was downloaded from Pixabay and is used under the Pixabay Content License "
            f"(https://pixabay.com/service/license-summary/). Track URL: {mz.get('url')}\n\n"
            f"License certificate:\n{sertifika}")


def video_olustur(ses_dosyasi, kelimeler, boyut, ayar, cikti, log=print, ilerleme=None, bilgi=None, sahneler=None):
    """sahneler verilirse arka plan, sahne çizimlerinden (yakınlaşma/kaydırma) + gün sayacıyla kurulur."""
    W, H = boyut
    ses_dosyasi, cikti = os.path.abspath(ses_dosyasi), os.path.abspath(cikti)
    sure = medya_suresi(ses_dosyasi)
    log(f"[+] Ses süresi: {sure:.1f} sn. Altyazı hazırlanıyor...")
    zamanlar = sahne_zamanlari(sahneler, kelimeler, sure) if sahneler else None
    sayaclar = [(b, e, s_.get("sayac", "")) for s_, (b, e) in zip(sahneler, zamanlar)] if sahneler else None
    altyazi_yaz(kelimeler, W, H, ayar.get("altyazi", "grup"), os.path.join(GECICI, "altyazi.ass"), sayaclar)
    _font_hazirla()

    kapanis_var = bool(ayar.get("kapanis", True))
    ana_sure = sure + (0.6 if kapanis_var else 0.0)       # anlatımdan sonra kısa nefes payı
    if sahneler and all(s_.get("resim") for s_ in sahneler):
        girisler, filtre = sahne_arkaplan(sahneler, zamanlar, ana_sure + 0.3, W, H)
        log(f"[+] Arka plan: {len(sahneler)} sahne çizimi.")
    else:
        girisler, filtre = arkaplan_kur(ayar.get("arkaplan", "klipler"), ana_sure + 0.3, W, H, log)
    ses_idx = girisler.count("-i")
    girisler += ["-i", ses_dosyasi]
    filtre.append("[bg]subtitles=altyazi.ass:fontsdir=fonts[v0]")
    v_etiket, toplam = _kapanis_ekle(girisler, filtre, "v0", ana_sure, W, H, ayar, log)

    filtre.append(f"[{ses_idx}:a]apad=whole_dur={toplam:.3f}[na]")
    ses_map = "[na]"
    muzikler = _dosyalar(MUZIK, MUZIK_UZ)
    if ayar.get("muzik") and muzikler:
        m = ayar.get("_muzik_sabit") or random.choice(muzikler)
        if bilgi is not None:
            bilgi["muzik"] = m
        mh = muzik_hazirla(m, log)
        ms = _sure(mh)
        bas = random.uniform(0, max(0.0, ms - 8)) if ms > 20 else 0.0
        log(f"[+] Müzik: {os.path.basename(m)} ({int(bas)}. saniyeden)")
        mi = girisler.count("-i")
        girisler += ["-stream_loop", "-1", "-ss", f"{bas:.2f}", "-i", mh]
        v1 = float(ayar.get("muzik_ses", 12)) / 100
        v2 = min(max(v1 * 3, 0.35), 0.6)       # kapanışta müzik yükselir
        hacim = (f"volume='{v1:.3f}+({v2:.3f}-{v1:.3f})*min(1,max(0,(t-{sure:.2f})/1.0))':eval=frame"
                 if toplam > sure + 1 else f"volume={v1:.3f}")
        filtre.append(
            f"[{mi}:a]{hacim},afade=t=in:d=0.8,afade=t=out:st={max(0.0, toplam - 2):.2f}:d=2[mz];"
            f"[na][mz]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]")
        ses_map = "[a]"

    log("[+] Render başlıyor (NVIDIA NVENC)...")
    try:
        _render(girisler, filtre, [f"[{v_etiket}]", ses_map], toplam, cikti, log, ilerleme)
    except RuntimeError as e:
        if not kapanis_var or ayar.get("_kapanis_yedek"):
            raise
        log(f"[!] Seçilen geçiş efekti çalışmadı; aynı kapanış kartı 'siyahtan geçiş' ile ekleniyor.\n"
            f"    ({str(e)[-160:]})")
        return video_olustur(ses_dosyasi, kelimeler, boyut, dict(ayar, _kapanis_yedek=True),
                             cikti, log, ilerleme, bilgi, sahneler)
    return toplam


def kapanis_onizle(ayar, log=print):
    """Arka plandan 3 sn + kapanış geçişi; kısa deneme videosu üretir."""
    if not kapanis_bul(ayar):
        raise RuntimeError("Kapanış kartı bulunamadı. Ana klasöre bir resim koy ya da Ayarlar'dan seç.")
    a = dict(ayar, kapanis=True)
    W, H = (1080, 1920) if a.get("yon", "dikey") == "dikey" else (1920, 1080)
    girisler, filtre = arkaplan_kur(a.get("arkaplan", "uzun"), 3.3, W, H, log)
    filtre[-1] = filtre[-1][:filtre[-1].rindex("[bg]")] + "[v0]"
    v, toplam = _kapanis_ekle(girisler, filtre, "v0", 3.0, W, H, a, log)
    cikti = os.path.join(GECICI, f"kapanis_deneme_{int(time.time())}.mp4")
    _render(girisler, filtre, [f"[{v}]"], toplam, cikti, log, ses=False)
    return cikti


def _ass_metin(x):
    return re.sub(r"[{}\\]", "", x)


def kapak_olustur(kayit, log=print):
    """Videodan bulanık arka plan + büyük başlık yazılı kapak resmi (JPG) üretir."""
    video = kayit.get("dosya", "")
    if not os.path.exists(video):
        raise RuntimeError("Video dosyası bulunamadı.")
    dikey = kayit.get("yon") == "dikey"
    W, H = (1080, 1920) if dikey else (1280, 720)
    hedef = video[:-4] + "_kapak.jpg"
    baslik = re.sub(r"\s*#\w+", "", kayit.get("baslik", "")).strip() or kayit.get("konu", "")
    kelimeler = buyuk(_ass_metin(baslik)).split()
    vurgu = max(1, min(2, len(kelimeler) // 3))          # son 1-2 kelime sarı
    metin = " ".join(kelimeler[:-vurgu]) + r" {\1c&H00E1FF&}" + " ".join(kelimeler[-vurgu:])
    fs = int(W * 0.105) if dikey else int(H * 0.13)
    ass = os.path.join(GECICI, "kapak.ass")
    with open(ass, "w", encoding="utf-8") as f:
        f.write("\n".join([
            "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 0",
            "ScaledBorderAndShadow: yes", "", "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
            "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
            "MarginL, MarginR, MarginV, Encoding",
            f"Style: K,Arial,{fs},&H00FFFFFF,&H000000FF,&H00000000,&HA0000000,-1,0,0,0,100,100,1,0,1,"
            f"{max(6, fs // 11)},{max(3, fs // 20)},5,{int(W * 0.08)},{int(W * 0.08)},0,1",
            "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
            f"Dialogue: 0,0:00:00.00,0:00:05.00,K,,0,0,0,,{metin}", ""]))
    _font_hazirla()
    an = min(max(2.0, float(kayit.get("sure", 10)) * 0.3), 20.0)
    vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=14:2,"
          f"eq=brightness=-0.22:saturation=1.25,vignette=PI/4,subtitles=kapak.ass:fontsdir=fonts")
    r = subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-ss", f"{an:.2f}", "-i", video, "-frames:v", "1",
                        "-vf", vf, "-q:v", "3", hedef], cwd=GECICI, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
    if r.returncode != 0 or not os.path.exists(hedef):
        raise RuntimeError(f"Kapak oluşturulamadı: {r.stderr.strip()[-200:]}")
    kayit["kapak"] = hedef
    return hedef


def kapak_yukle(kayit, log=print):
    """Kapak resmini YouTube'a gönderir. Başarısızsa nedenini açıklar (hata fırlatmaz)."""
    from googleapiclient.http import MediaFileUpload
    try:
        kapak = kayit.get("kapak")
        if not kapak or not os.path.exists(kapak):
            kapak = kapak_olustur(kayit, log)
        yt = yt_servis(True, log)
        yt.thumbnails().set(videoId=kayit["video_id"],
                            media_body=MediaFileUpload(kapak, mimetype="image/jpeg")).execute()
        kayit["kapak_yuklendi"] = True
        gecmis_kaydet(kayit)
        log("[✓] Kapak resmi YouTube'a yüklendi.")
        return True
    except Exception as e:
        m = str(e)
        if "permission" in m.lower() or "forbidden" in m.lower() or "403" in m:
            neden = ("YouTube özel kapağa izin vermedi. Shorts'ta özel kapak şimdilik sadece İş Ortağı Programı'ndaki "
                     "kanallara açık; uzun videolarda ise kanalın telefonla doğrulanması gerekir "
                     "(youtube.com/verify). Kapak dosyası videonun yanında duruyor, Studio'dan elle yükleyebilirsin.")
        else:
            neden = f"Kapak yüklenemedi: {m[:200]}"
        log(f"[!] {neden}")
        return False


# ---------------------------------------------------------------------------
# 8. ÜRETİM HATTI
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# 8b. SENARYO (ÇİZİMLİ): "...olsaydın?" hikâyeleri, sahne sahne Gemini çizimleri + gün sayacı
# ---------------------------------------------------------------------------
SENARYO_ACIK = False        # çizimli senaryo şimdilik kapalı (Gemini görsel kotası yok); açmak için True
FORMATLAR = {"hikaye": "Hikâye (arka plan videosu)", "senaryo": "Senaryo (çizimli, gün sayaçlı)"}
CIZIM_MODELLER = ["gemini-2.5-flash-image", "gemini-3-pro-image-preview", "gemini-2.5-flash-image-preview",
                  "gemini-2.0-flash-preview-image-generation"]
CIZIM_STIL = ("Flat 2D cartoon illustration in a consistent storybook animation style: simple rounded shapes, thick "
              "clean dark outlines, flat colors with soft shading, muted desaturated palette, moody cinematic "
              "lighting, slightly eerie atmosphere. Vertical 9:16 portrait composition, the important action in the "
              "middle of the frame. Absolutely NO text, letters, numbers, signs with writing, captions, speech "
              "bubbles, logos or watermarks anywhere in the image.")
KARAKTER_TARIF = ("a young man in his mid twenties, slim, short messy dark brown hair, simple round face with big "
                  "expressive dark eyes and thick eyebrows, light stubble, mustard yellow hooded raincoat over a grey "
                  "t-shirt, dark blue jeans, worn red sneakers, a small brown backpack")
SENARYO_YERLER_TR = [
    "Karadeniz'de ıssız bir deniz feneri", "kar altında kalmış bir dağ evi", "terk edilmiş bir metro istasyonu",
    "fırtınada sürüklenen bir balıkçı teknesi", "kapanmış bir lunapark", "orman yangını gözetleme kulesi",
    "çölde bozulan bir otobüs", "kapıları kilitlenmiş bir alışveriş merkezi", "bir maden ocağının derinliği",
    "issiz bir adadaki eski karakol", "sular altında kalan bir köy", "gece vardiyasındaki bir hastane katı",
    "dağda mahsur kalan bir teleferik", "boşaltılmış bir kasaba", "bir kütüphanenin kilitli bodrumu",
    "kar fırtınasında bir tren", "ıssız bir otoyol kenarındaki motel", "terk edilmiş bir yatılı okul",
    "kuraklıkta kurumuş bir göl kıyısı", "bir şatonun kule odası", "nöbetçi olarak kalınan bir müze",
    "elektriği kesilen bir gökdelen", "kayalık bir koydaki batık gemi", "bir yayla evinde kış",
]
SENARYO_YERLER_EN = [
    "an abandoned lighthouse on a Scottish island", "a snowed-in mountain cabin in Alaska",
    "a closed subway station in New York", "a fishing boat adrift in a storm", "a shut-down amusement park",
    "a fire lookout tower in Oregon", "a broken-down bus in the Sahara", "a locked shopping mall at night",
    "the bottom of a mine in Wales", "an old outpost on a remote island", "a flooded village in Vietnam",
    "a night-shift hospital floor in Seoul", "a cable car stuck above the Alps", "an evacuated small town in Ohio",
    "the locked basement of an old library", "a train stuck in a blizzard in Canada", "a roadside motel in Nevada",
    "an abandoned boarding school in England", "a dried-up lake shore in Australia", "a castle tower in Romania",
    "a museum where you are the night guard", "a skyscraper during a city-wide blackout",
    "a shipwreck in a rocky cove in Chile", "a remote research hut in Iceland",
]
SENARYO_SURELER_TR = ["7 gece", "10 gün", "30 gün", "40 gün", "100 gün", "6 ay", "1 yıl", "3 gece", "72 saat"]
SENARYO_SURELER_EN = ["7 nights", "10 days", "30 days", "40 days", "100 days", "6 months", "1 year", "3 nights",
                      "72 hours"]


def format_senaryo(ayar=None):
    return (ayar or ayar_oku()).get("format", "hikaye") == "senaryo"


def _profil_dosya(ad):
    """Aktif kanalın klasöründeki dosya (TR: ana klasör, EN: profiller/en)."""
    return os.path.join(os.path.dirname(os.path.abspath(AYAR_DOSYA)), ad)


def senaryo_fikri(log=print):
    """'... olsaydın/kalsaydın?' tipi senaryo konusu üretir; kanalda daha önce yapılanlara benzemez."""
    tr = DIL == "tr"
    eskiler = [g.get("konu", "") for g in tum_gecmisler() if g.get("format") == "senaryo"]
    yerler = random.sample(SENARYO_YERLER_TR if tr else SENARYO_YERLER_EN, 4)
    sureler = random.sample(SENARYO_SURELER_TR if tr else SENARYO_SURELER_EN, 3)
    if tr:
        prompt = f"""YouTube Shorts için "ikinci tekil şahıs" hayatta kalma / gizem SENARYOSU fikirleri bul.
İzleyici kendini karakterin yerine koyar: "...{sureler[0]} mahsur kalsaydın?" gibi.

Kurallar:
- Başlık tek soru cümlesi, en fazla 12 kelime, bir YER ve bir SÜRE içersin. Örnek yer ve süreler (bunlardan seç
  ya da benzerlerini bul): yerler: {', '.join(yerler)}; süreler: {', '.join(sureler)}.
- Gerçek hayatta geçebilecek bir durum. Zombi, uzaylı, yapay zeka, robot, zaman yolculuğu, paralel evren,
  simülasyon, "rüyaymış" YASAK. Doğaüstü bir şey olacaksa bile sonda insan eliyle mantıklı bir açıklaması olsun.
- Merak: izleyici "ben olsam ne yapardım, sonunda ne olacak?" diye sonuna kadar izlemeli. Bir sır/tuhaflık olsun
  (her gece biri kapıyı çalıyor, erzak kendi kendine azalıyor, telsizden bilinmeyen bir ses...).
- Şu senaryolara benzemesin: {'; '.join(eskiler[-30:]) or '-'}

5 aday yaz, her birine 1-10 merak ve ozgunluk puanı ver. Ayrıca her adayın kısa "sir" alanına sondaki mantıklı
açıklamayı yaz (izleyiciye başta söylenmeyecek).
Yanıtı YALNIZCA şu JSON biçiminde ver:
{{"adaylar": [{{"konu": "...", "sir": "...", "merak": 8, "ozgunluk": 7}}]}}"""
    else:
        prompt = f"""Find second-person survival / mystery SCENARIO ideas for YouTube Shorts in ENGLISH.
The viewer puts themselves in the character's shoes: "What if you were stuck ... for {sureler[0]}?"

Rules:
- The title is one question, at most 12 words, containing a PLACE and a DURATION. Example places and durations
  (pick from these or similar ones anywhere in the world): places: {', '.join(yerler)}; durations: {', '.join(sureler)}.
- Realistic situation. NO zombies, aliens, AI, robots, time travel, parallel worlds, simulations, "it was a dream".
  If something seems supernatural, it must have a logical human explanation at the end.
- Curiosity: the viewer should wonder "what would I do, and how does it end?". Include a mystery (someone knocks
  every night, supplies disappear, an unknown voice on the radio...).
- Must not resemble: {'; '.join(eskiler[-30:]) or '-'}

Write 5 candidates, score each 1-10 for merak (curiosity) and ozgunluk (originality). Put the logical explanation
of the ending in "sir" (not revealed to the viewer at the start).
Reply ONLY in this JSON format:
{{"adaylar": [{{"konu": "...", "sir": "...", "merak": 8, "ozgunluk": 7}}]}}"""
    adaylar = []
    try:
        v = _json_coz(_gemini_uret(prompt, log, json_mod=True))
        adaylar = [a for a in (v.get("adaylar") or []) if str(a.get("konu", "")).strip()
                   and not yasak_kalip_var(f"{a.get('konu', '')} {a.get('sir', '')}")
                   and max([benzerlik(str(a["konu"]), e) for e in eskiler] + [0]) < 0.45]
    except IptalHatasi:
        raise
    except Exception as e:
        log(f"[!] Senaryo fikri alınamadı: {str(e)[:160]}")
    if not adaylar:
        yer, sure_ = yerler[0], sureler[0]
        return (f"{yer[0].upper() + yer[1:]} yerinde {sure_} mahsur kalsaydın?" if tr
                else f"What if you were stuck in {yer} for {sure_}?")

    def puan(a):
        try:
            return float(a.get("merak", 0)) * 1.5 + float(a.get("ozgunluk", 0))
        except (TypeError, ValueError):
            return 0
    adaylar.sort(key=puan, reverse=True)
    en = adaylar[0]
    konu = str(en["konu"]).strip().strip(" \"'“”*#-").splitlines()[0]
    tohum_kaydet({"konu": konu, "ipucu": "", "cozum": str(en.get("sir", "")), "tur": "Senaryo"})
    log(f"[+] Senaryo seçildi (merak {en.get('merak')}, özgünlük {en.get('ozgunluk')}): {konu}")
    return konu


def senaryo_uret(konu, yon="dikey", log=print):
    """Senaryoyu 6-8 sahneye bölünmüş olarak yazar. Döndürür: icerik_uret ile aynı alanlar + 'sahneler'."""
    tr = DIL == "tr"
    tohum = tohum_bul(konu) or {}
    sir = tohum.get("cozum", "")
    alt, ust = 135, 175
    if tr:
        prompt = f"""Senaryo: "{konu}"
{f'Sondaki mantıklı açıklama (buna sadık kal): {sir}' if sir else ''}
Bu senaryoyu YouTube Shorts için İKİNCİ TEKİL ŞAHISLA ("sen") anlatılan, {alt}-{ust} kelimelik Türkçe bir hikâyeye
dönüştür ve 6-8 SAHNEYE böl. Her sahne zamanda ileri atlar ve ekranda bir sayaçla gösterilir (örn. "1. GÜN",
"3. GECE", "40. GÜN", "1. AY"). Sayaç her sahnede ileri gider, asla geri gitmez.

Hikâye kuralları:
- İlk cümle (en fazla 12 kelime) izleyiciyi doğrudan duruma atar: "Kapı arkandan kilitlendi ve anahtar dışarıda kaldı."
- Her sahnede yeni bir sorun, karar ya da tuhaflık olsun; izleyici "ben olsam ne yapardım" diye düşünsün.
- Bir sır/tuhaflık baştan kurulur, ilk yarıya adil bir ipucu gizlenir, son sahnede insan eliyle MANTIKLI biçimde
  açıklanır ve bir duygu bırakır (hüzün, minnet, adalet ya da ürperti). Tek ters köşe.
- YASAK: yapay zeka, robot, zombi, uzaylı, zaman yolculuğu, simülasyon, "rüyaymış", açık uçlu son.
- Sadece seslendirilecek düz metin; sayıları yazıyla yaz ("kırk gün"). Talimat kelimelerini (ipucu, sır, sahne,
  sayaç) metinde kullanma.

Her sahne için "cizim" alanına o sahnenin İNGİLİZCE çizim tarifini yaz (1-2 cümle): mekân, günün saati, ışık,
ana karakterin (the main character) ne yaptığı ve yüz ifadesi, kamera açısı. Çizimde yazı/tabela olmayacak.
Ana karakter sahnede yoksa tarifinde de geçmesin. Tarifler birbirinden görsel olarak farklı olsun.

Yanıtı YALNIZCA şu JSON biçiminde ver:
{{"sahneler": [{{"sayac": "1. GÜN", "metin": "seslendirilecek 2-4 cümle", "cizim": "English scene description"}}],
  "baslik": "en fazla 60 karakter, soru biçiminde, sonu ele vermesin",
  "aciklama": "2-3 cümlelik merak uyandıran açıklama, sonunda 3-5 Türkçe hashtag",
  "etiketler": ["8-12 adet Türkçe etiket"]}}"""
    else:
        prompt = f"""Scenario: "{konu}"
{f'The logical explanation at the end (stay faithful to it): {sir}' if sir else ''}
Turn this scenario into a {alt}-{ust} word story for YouTube Shorts told in the SECOND PERSON ("you"), in natural
American English, split into 6-8 SCENES. Each scene jumps forward in time and is shown with an on-screen counter
(e.g. "DAY 1", "NIGHT 3", "DAY 40", "MONTH 2"). The counter always moves forward.

Story rules:
- The first sentence (max 12 words) drops the viewer straight into the situation.
- Every scene brings a new problem, decision or oddity; the viewer should think "what would I do?".
- A mystery is set up early, a fair clue is hidden in the first half, and the last scene explains it LOGICALLY
  through human actions, leaving an emotion (sadness, gratitude, justice or a chill). One twist only.
- FORBIDDEN: AI, robots, zombies, aliens, time travel, simulations, "it was a dream", open endings.
- Plain narration text only; write numbers as words. Never use instruction words (clue, twist, scene, counter).

For each scene write "cizim": a 1-2 sentence description of the illustration: place, time of day, lighting, what
the main character (the main character) does and their facial expression, camera angle. No text or signs in the
picture. If the main character is not in the scene, don't mention them. Make the scenes visually different.

Reply ONLY in this JSON format:
{{"sahneler": [{{"sayac": "DAY 1", "metin": "2-4 sentences of narration", "cizim": "scene description"}}],
  "baslik": "max 60 characters, a question, must not reveal the ending",
  "aciklama": "2-3 intriguing sentences, ending with 3-5 English hashtags",
  "etiketler": ["8-12 English tags"]}}"""
    en_iyi = None
    for deneme in range(3):
        try:
            v = _json_coz(_gemini_uret(prompt, log, json_mod=True))
        except RuntimeError as e:
            if "okunamadı" not in str(e) or deneme == 2:
                raise
            continue
        sahneler = []
        for s in (v.get("sahneler") or []) if isinstance(v, dict) else []:
            metin = metin_duzelt(str(s.get("metin", "")).strip())
            if metin:
                sahneler.append({"sayac": buyuk(str(s.get("sayac", "")).strip())[:16], "metin": metin,
                                 "cizim": str(s.get("cizim", "")).strip()})
        if not sahneler:
            continue
        hikaye = " ".join(s["metin"] for s in sahneler)
        n = len(hikaye.split())
        sorunlar = hikaye_sorunlari(hikaye)
        if not 5 <= len(sahneler) <= 9:
            sorunlar.append(f"{len(sahneler)} sahne var, 6-8 olmalı")
        fark = 0 if alt - 20 <= n <= ust + 30 else min(abs(n - alt), abs(n - ust))
        if en_iyi is None or (len(sorunlar), fark) < en_iyi[0]:
            en_iyi = ((len(sorunlar), fark), v, sahneler)
        if not sorunlar and fark == 0:
            log(f"[+] Senaryo {len(sahneler)} sahne, {n} kelime.")
            break
        log(f"[~] Senaryo düzelttiriliyor ({'; '.join(sorunlar) or f'{n} kelime'})...")
        prompt += (f"\n\nÖNEMLİ: Önceki denemende şu sorunlar vardı: {'; '.join(sorunlar) or ''} "
                   f"Uzunluk {alt}-{ust} kelime, 6-8 sahne olsun.")
    if en_iyi is None:
        raise RuntimeError("Gemini'nin senaryo yanıtı okunamadı, tekrar deneyin.")
    _, v, sahneler = en_iyi
    baslik = baslik_sinirla(str(v.get("baslik") or konu).strip().strip('"'), BASLIK_SINIR - 8)
    aciklama = str(v.get("aciklama", "")).strip()
    etiketler = [str(e).strip().lstrip("#") for e in (v.get("etiketler") or []) if str(e).strip()]
    if yon == "dikey":
        if "#shorts" not in baslik.lower():
            baslik += " #shorts"
        if "#shorts" not in aciklama.lower():
            aciklama += "\n\n#shorts"
    return {"hikaye": " ".join(s["metin"] for s in sahneler), "baslik": baslik_sinirla(baslik),
            "aciklama": aciklama[:4900], "etiketler": etiketler[:15], "sahneler": sahneler, "format": "senaryo"}


def senaryo_sahne_esitle(icerik):
    """Hikâye onay penceresinde metin düzenlendiyse sahnelerin metnini ona göre yeniden dağıtır."""
    sahneler = icerik.get("sahneler") or []
    if not sahneler:
        return
    eski = " ".join(s["metin"] for s in sahneler)
    if " ".join(icerik["hikaye"].split()) == " ".join(eski.split()):
        return
    yeni = icerik["hikaye"].split()
    oranlar = [len(s["metin"].split()) for s in sahneler]
    toplam = sum(oranlar) or 1
    bas = 0
    for i, s in enumerate(sahneler):
        bit = len(yeni) if i == len(sahneler) - 1 else round(sum(oranlar[:i + 1]) / toplam * len(yeni))
        s["metin"] = " ".join(yeni[bas:bit])
        bas = bit


# --- görsel üretimi -------------------------------------------------------
_cizim_model = {"ad": None}


def _cizim_modelleri():
    """Bilinen çizim modelleri + bu API anahtarında görünen diğer görsel modelleri."""
    liste = list(CIZIM_MODELLER)
    if _cizim_model["ad"]:
        liste.insert(0, _cizim_model["ad"])
    try:
        for m in _istemci().models.list():
            ad = (getattr(m, "name", "") or "").split("/")[-1]
            eylem = getattr(m, "supported_actions", None) or []
            if "image" in ad and "imagen" not in ad and ad not in liste and (not eylem or "generateContent" in eylem):
                liste.append(ad)
    except Exception:
        pass
    return list(dict.fromkeys(liste))


def _gorsel_baytlari(r):
    for aday in getattr(r, "candidates", None) or []:
        icerik = getattr(aday, "content", None)
        for parca in (getattr(icerik, "parts", None) or []):
            veri = getattr(parca, "inline_data", None)
            if veri is not None and getattr(veri, "data", None):
                d = veri.data
                if isinstance(d, str):
                    d = base64.b64decode(d)
                return d, (getattr(veri, "mime_type", "") or "image/png")
    return None, None


def gorsel_uret(tarif, hedef, referans=None, log=print):
    """Gemini görsel modeliyle tek bir çizim üretip 'hedef' (uzantısız) yoluna kaydeder; dosya yolunu döndürür."""
    istem = f"{CIZIM_STIL}\n\n{tarif}"
    icerik = [istem]
    if referans and os.path.exists(referans):
        with open(referans, "rb") as f:
            ref = f.read()
        icerik = [gtypes.Part.from_bytes(data=ref, mime_type="image/jpeg" if referans.lower().endswith(".jpg")
                                         else "image/png"),
                  "The image above is the MAIN CHARACTER reference. Whenever the main character appears, draw "
                  "exactly this person: same face, hair, clothes, colors and art style.\n\n" + istem]
    try:
        cfg = gtypes.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"],
                                           image_config=gtypes.ImageConfig(aspect_ratio="9:16"))
    except Exception:          # eski google-genai: oran ayarı yok, istemde söylüyoruz
        cfg = gtypes.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"])
    son_hata = None
    for model in _cizim_modelleri():
        for deneme in range(2):
            try:
                r = iptal_edilebilir(_istemci().models.generate_content, model=model, contents=icerik, config=cfg,
                                     _zaman_asimi=150)
                veri, tur = _gorsel_baytlari(r)
                if not veri:
                    raise RuntimeError("model görsel döndürmedi")
                yol_ = hedef + (".jpg" if "jpeg" in tur or "jpg" in tur else ".png")
                with open(yol_, "wb") as f:
                    f.write(veri)
                _cizim_model["ad"] = model
                return yol_
            except IptalHatasi:
                raise
            except Exception as e:
                son_hata = e
                m = str(e)
                if "429" in m or "RESOURCE_EXHAUSTED" in m:
                    if deneme == 0 and "PerDay" not in m:
                        bekle_iptal(20)
                        continue
                    break
                if any(x in m for x in ("404", "NOT_FOUND", "not supported", "INVALID_ARGUMENT", "PERMISSION")):
                    break            # bu model bu anahtarda yok: sıradakine geç
                if deneme == 0:
                    bekle_iptal(4)
    # son çare: Imagen (referans resmi desteklemez, ama video yine çıkar)
    try:
        r = iptal_edilebilir(_istemci().models.generate_images, model="imagen-4.0-generate-001", prompt=istem,
                             config=gtypes.GenerateImagesConfig(number_of_images=1, aspect_ratio="9:16"),
                             _zaman_asimi=150)
        veri = r.generated_images[0].image.image_bytes
        yol_ = hedef + ".png"
        with open(yol_, "wb") as f:
            f.write(veri)
        return yol_
    except IptalHatasi:
        raise
    except Exception:
        pass
    m = str(son_hata)
    if "429" in m or "RESOURCE_EXHAUSTED" in m or "quota" in m.lower():
        raise RuntimeError("Gemini görsel kotası dolu ya da bu API anahtarında görsel üretimi açık değil "
                           "(ücretsiz katmanda görsel modelleri kapalı olabilir; Google AI Studio'da faturalandırmayı "
                           f"açman gerekebilir). Ayrıntı: {m[:200]}")
    raise RuntimeError(f"Çizim üretilemedi: {m[:300]}")


def karakter_yolu():
    for uz in (".png", ".jpg"):
        p_ = _profil_dosya("karakter" + uz)
        if os.path.exists(p_):
            return p_
    return None


def karakter_hazirla(log=print, yeniden=False):
    """Kanalın sabit ana karakterini bir kez çizer (karakter.png); sonraki her sahnede referans olur."""
    p_ = karakter_yolu()
    if p_ and not yeniden:
        return p_
    log("[+] Kanalın ana karakteri çiziliyor (bir kez yapılır, sonra her videoda aynı karakter kullanılır)...")
    eski = p_
    yeni = gorsel_uret("Character reference sheet of the main character: one full-body figure, front view, standing "
                       f"in a relaxed neutral pose, plain soft grey background, nothing else in the image. "
                       f"The character is {KARAKTER_TARIF}.", _profil_dosya("karakter_yeni"), log=log)
    if eski and os.path.exists(eski):
        try:
            os.replace(eski, _profil_dosya("karakter_eski" + os.path.splitext(eski)[1]))
        except OSError:
            pass
    son = _profil_dosya("karakter" + os.path.splitext(yeni)[1])
    os.replace(yeni, son)
    log("[✓] Ana karakter hazır.")
    return son


def sahne_ciz(sahne, hedef, log=print):
    tarif = (f"Scene: {sahne.get('cizim') or sahne.get('metin', '')}\n"
             "Keep the same art style as the reference. Show the moment clearly and dramatically.")
    return gorsel_uret(tarif, hedef, karakter_yolu(), log)


def sahneleri_ciz(sahneler, klasor, log=print, asama=None, bas_yuzde=34, son_yuzde=55):
    os.makedirs(klasor, exist_ok=True)
    karakter_hazirla(log)
    onceki = None
    for i, s in enumerate(sahneler):
        iptal_kontrol()
        if asama:
            asama(f"Sahneler çiziliyor ({i + 1}/{len(sahneler)})",
                  bas_yuzde + (son_yuzde - bas_yuzde) * i / max(1, len(sahneler)))
        log(f"[+] Sahne {i + 1}/{len(sahneler)} çiziliyor: {s.get('sayac', '')} – {s.get('cizim', '')[:80]}")
        try:
            s["resim"] = sahne_ciz(s, os.path.join(klasor, f"sahne_{i + 1:02d}"), log)
        except IptalHatasi:
            raise
        except Exception as e:
            if onceki is None and i == len(sahneler) - 1:
                raise
            if "kota" in str(e) and onceki is None:
                raise
            log(f"[!] Sahne {i + 1} çizilemedi ({str(e)[:140]}); önceki çizim kullanılıyor.")
            s["resim"] = onceki
        onceki = s.get("resim") or onceki
    ilk = next((s["resim"] for s in sahneler if s.get("resim")), None)
    if not ilk:
        raise RuntimeError("Hiçbir sahne çizilemedi.")
    for s in sahneler:
        s["resim"] = s.get("resim") or ilk
    return sahneler


def sahne_zamanlari(sahneler, kelimeler, toplam):
    """Her sahnenin seslendirmede başladığı ve bittiği saniye (kelime sayısı oranına göre)."""
    adet = [max(1, len(tts_metni(s["metin"]).split())) for s in sahneler]
    tum = sum(adet)
    n = len(kelimeler)
    zamanlar, sayac = [], 0
    for i, a in enumerate(adet):
        if i == 0 or not n:
            bas = 0.0 if i == 0 else toplam * sayac / tum
        else:
            idx = min(n - 1, round(sayac / tum * n))
            bas = max(0.0, float(kelimeler[idx][0]) - 0.15)
        zamanlar.append(bas)
        sayac += a
    sonuc = []
    for i, bas in enumerate(zamanlar):
        bit = zamanlar[i + 1] if i + 1 < len(zamanlar) else toplam
        sonuc.append((bas, max(bas + 0.8, bit)))
    return sonuc


def sahne_arkaplan(sahneler, zamanlar, sure, W, H):
    """Çizimlerden hafif yakınlaşma/kaydırma efektli arka plan (ffmpeg girişleri + filtre)."""
    girisler, filtre, etiketler = [], [], []
    W2, H2 = _cift(W * 1.18), _cift(H * 1.18)
    for i, (s, (bas, bit)) in enumerate(zip(sahneler, zamanlar)):
        L = (sure - bas) if i == len(sahneler) - 1 else (bit - bas)
        L = max(0.5, L)
        kare = int(round(L * 30)) + 2
        hiz = 0.16 / kare
        tip = i % 4
        if tip == 0:      # yavaşça yakınlaş
            z, x, y = f"min(1+{hiz:.6f}*on,1.16)", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
        elif tip == 1:    # yakından uzaklaş
            z, x, y = f"max(1.16-{hiz:.6f}*on,1.0)", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
        elif tip == 2:    # sağa kay
            z, x, y = "1.12", f"(iw-iw/zoom)*on/{kare}", "ih/2-(ih/zoom/2)"
        else:             # yukarı kay
            z, x, y = "1.12", "iw/2-(iw/zoom/2)", f"(ih-ih/zoom)*(1-on/{kare})"
        girisler += ["-loop", "1", "-framerate", "30", "-t", f"{L + 0.2:.3f}", "-i", s["resim"]]
        filtre.append(
            f"[{i}:v]scale={W2}:{H2}:force_original_aspect_ratio=increase,crop={W2}:{H2},"
            f"zoompan=z='{z}':x='{x}':y='{y}':d=1:s={W}x{H}:fps=30,"
            f"setsar=1,format=yuv420p,trim=duration={L:.3f},setpts=PTS-STARTPTS[s{i}]")
        etiketler.append(f"[s{i}]")
    filtre.append(f"{''.join(etiketler)}concat=n={len(etiketler)}:v=1:a=0[bg]")
    return girisler, filtre


def cizim_kucuk(resim, yukseklik=220):
    """Tk'nin açabileceği küçük PNG önizleme (Tk JPG açamaz)."""
    try:
        anahtar = hashlib.md5(f"{resim}{os.path.getmtime(resim)}{yukseklik}".encode()).hexdigest()[:12]
    except OSError:
        return None
    hedef = os.path.join(GECICI, f"ciz_{anahtar}.png")
    if not os.path.exists(hedef):
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", resim, "-vf", f"scale=-2:{yukseklik}", hedef],
                       capture_output=True, creationflags=NO_WINDOW)
    return hedef if os.path.exists(hedef) else None


def senaryo_sahne_yenile(kayit, sahne_no, log=print):
    """Tek sahneyi yeniden çizer ve videoyu (aynı ses, aynı müzik) yeniden render eder."""
    sahneler = kayit.get("sahneler") or []
    if not 0 <= sahne_no < len(sahneler):
        raise RuntimeError("Sahne bulunamadı.")
    klasor = kayit["dosya"][:-4] + "_sahneler"
    ses = os.path.join(klasor, "ses.mp3")
    kelimeler = _json_oku(os.path.join(klasor, "kelimeler.json"), None)
    if not os.path.exists(ses) or not kelimeler:
        raise RuntimeError("Bu videonun ses dosyası bulunamadı; yeniden render edilemiyor.")
    s = sahneler[sahne_no]
    log(f"[+] Sahne {sahne_no + 1} yeniden çiziliyor...")
    s["resim"] = sahne_ciz(s, os.path.join(klasor, f"sahne_{sahne_no + 1:02d}_{int(time.time()) % 100000}"), log)
    ayar = dict(ayar_oku())
    if kayit.get("muzik_yol") and os.path.exists(kayit["muzik_yol"]):
        ayar["_muzik_sabit"] = kayit["muzik_yol"]
    elif kayit.get("muzik_yol") is None and not kayit.get("muzik"):
        ayar["muzik"] = False
    boyut = (1080, 1920) if kayit.get("yon", "dikey") == "dikey" else (1920, 1080)
    gecici_cikti = kayit["dosya"][:-4] + "_yeni.mp4"
    log("[+] Video yeniden render ediliyor...")
    sure = video_olustur(ses, kelimeler, boyut, ayar, gecici_cikti, log, sahneler=sahneler)
    os.replace(gecici_cikti, kayit["dosya"])
    kayit["sure"] = round(sure, 1)
    try:
        kapak_olustur(kayit, log)
    except Exception:
        pass
    gecmis_kaydet(kayit)
    log("[✓] Video güncellendi.")
    return kayit


def _bos(*a, **k):
    pass


def video_uret(konu, ayar, log=print, asama=_bos, onay=None):
    """Konu -> hazır video. Geçmişe kaydedilen kayıt sözlüğünü döndürür.
    onay(icerik) verilirse: düzenlenmiş içerik, "tekrar" ya da None (iptal) döndürmeli."""
    while True:
        iptal_kontrol()
        senaryo = format_senaryo(ayar)
        asama("Senaryo yazılıyor" if senaryo else "Hikaye yazılıyor", 5)
        icerik = (senaryo_uret(konu, ayar["yon"], log) if senaryo
                  else icerik_uret(konu, ayar["uzunluk"], ayar["yon"], log))
        iptal_kontrol()
        if not onay:
            break
        asama("Hikaye onayını bekliyor", 12)
        sonuc = onay(icerik)
        if sonuc == "tekrar":
            log("[~] Hikaye yeniden yazdırılıyor...")
            continue
        if not sonuc:
            raise IptalHatasi("İşlem iptal edildi.")
        icerik = sonuc
        senaryo_sahne_esitle(icerik)
        break
    log(f"[+] Başlık: {icerik['baslik']}")

    iptal_kontrol()
    asama("Seslendiriliyor", 20)
    ses = os.path.join(GECICI, "ses.mp3")
    kelimeler = ses_olustur(icerik["hikaye"], ses, ayar, log, asama=asama)
    iptal_kontrol()

    boyut = (1080, 1920) if ayar["yon"] == "dikey" else (1920, 1080)
    isim = re.sub(r"[^\wçğıöşüÇĞİÖŞÜ]+", "_", konu)[:40].strip("_") or "video"
    zaman = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    cikti = os.path.join(CIKTI, f"{zaman}_{isim}.mp4")
    sahneler = icerik.get("sahneler")
    r_bas = 32
    if sahneler:
        klasor = cikti[:-4] + "_sahneler"
        try:
            sahneleri_ciz(sahneler, klasor, log, asama, 32, 60)
        except IptalHatasi:
            raise
        except Exception as e:      # görsel kotası yoksa video yine çıksın: arka plan videosu + gün sayacı
            log(f"[!] Sahneler çizilemedi, bu video arka plan videosuyla (gün sayacı korunarak) yapılıyor.\n"
                f"    {str(e)[:260]}")
            for s_ in sahneler:
                s_.pop("resim", None)
        shutil.copy2(ses, os.path.join(klasor, "ses.mp3"))         # sahne yeniden çizilirse tekrar render için
        _json_yaz(os.path.join(klasor, "kelimeler.json"), kelimeler)
        r_bas = 60
    asama("Render ediliyor", r_bas)
    bilgi = {}
    sure = video_olustur(ses, kelimeler, boyut, ayar, cikti, log,
                         ilerleme=lambda o: asama(None, r_bas + o * (90 - r_bas)), bilgi=bilgi, sahneler=sahneler)
    muzik = muzik_lisansi(bilgi.get("muzik"))
    if muzik:   # sanatçıya kredi + itirazda kanıt
        kredi = f"🎵 {T('Müzik', 'Music')}: {muzik['baslik']}" + (f" – {muzik['sanatci']}" if muzik["sanatci"] else "") + " (Pixabay)"
        icerik["aciklama"] = f"{icerik['aciklama']}\n\n{kredi}" + (f"\n{muzik['url']}" if muzik["url"] else "")
    elif bilgi.get("muzik"):
        muzik = {"dosya": os.path.basename(bilgi["muzik"])}

    kayit = {
        "tarih": datetime.datetime.now().isoformat(timespec="seconds"),
        "konu": konu, "dosya": cikti, "sure": round(sure, 1),
        "yon": ayar["yon"], "uzunluk": ayar["uzunluk"],
        **icerik, "video_id": None, "durum": "uretildi", "muzik": muzik,
    }
    if sahneler:
        kayit["muzik_yol"] = bilgi.get("muzik")
    try:
        kapak_olustur(kayit, log)
        log("[+] Kapak resmi hazırlandı.")
    except Exception as e:
        log(f"[!] {e}")
    with open(cikti[:-4] + ".txt", "w", encoding="utf-8") as f:
        f.write(f"BAŞLIK:\n{icerik['baslik']}\n\nAÇIKLAMA:\n{icerik['aciklama']}\n\n"
                f"ETİKETLER:\n{', '.join(icerik['etiketler'])}\n\nHİKAYE:\n{icerik['hikaye']}\n")
    gecmis_kaydet(kayit)
    asama("Video hazır", 90)
    log(f"[✓] VİDEO HAZIR: {os.path.basename(cikti)} ({sure:.0f} sn)")
    return kayit


# ---------------------------------------------------------------------------
# 9. YOUTUBE
# ---------------------------------------------------------------------------
YT_KAPSAM = ["https://www.googleapis.com/auth/youtube",
             "https://www.googleapis.com/auth/youtube.force-ssl",      # yorumlara cevap için gerekli
             "https://www.googleapis.com/auth/yt-analytics.readonly"]
YORUM_KAPSAM = "https://www.googleapis.com/auth/youtube.force-ssl"


def yorum_izni_var():
    """Kayıtlı oturum yorumlara cevap yazma iznini (youtube.force-ssl) içeriyor mu?"""
    try:
        with open(TOKEN, encoding="utf-8") as f:
            return YORUM_KAPSAM in (json.load(f).get("scopes") or [])
    except (OSError, ValueError):
        return False
_yt = None
_yt_creds = None
_yt_kilit = threading.Lock()


def _yt_paketler():
    modul_yukle("googleapiclient", "google-api-python-client")
    modul_yukle("google_auth_oauthlib", "google-auth-oauthlib")
    modul_yukle("google_auth_httplib2", "google-auth-httplib2")


def yt_servis(etkilesimli=True, log=print):
    """Yetkili YouTube servisini döndürür. Gerekirse tarayıcıda giriş açar."""
    global _yt
    with _yt_kilit:
        if _yt is not None:
            return _yt
        _yt_paketler()
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        creds = None
        if os.path.exists(TOKEN):
            try:
                creds = Credentials.from_authorized_user_file(TOKEN)   # dosyadaki izinlerle (eski oturumlar da çalışsın)
            except Exception:
                creds = None
        if creds and not creds.valid and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                log("[!] YouTube oturumu yenilenemedi, yeniden giriş gerekiyor.")
                creds = None
        if not creds or not creds.valid:
            if not etkilesimli:
                return None
            if not os.path.exists(CLIENT_SECRET):
                raise RuntimeError(
                    "client_secret.json bulunamadı.\nGoogle Cloud Console'dan 'Masaüstü uygulaması' "
                    "OAuth istemcisi indirip bu klasöre client_secret.json adıyla koyun.")
            log("[+] Tarayıcıda Google girişi açılıyor...")
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET, YT_KAPSAM)
            creds = flow.run_local_server(port=0, prompt="consent select_account",
                                          success_message="Bağlantı tamam, bu sekmeyi kapatabilirsiniz.")
        with open(TOKEN, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
        global _yt_creds
        _yt_creds = creds
        _yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
        return _yt


def yt_baglantiyi_kes():
    global _yt, _yt_creds
    _yt = None
    _yt_creds = None
    if os.path.exists(TOKEN):
        os.remove(TOKEN)


def _yeni_servis(ad, surum):
    """İstatistik için ayrı servis (yükleme ile aynı anda çalışabilsin diye)."""
    if yt_servis(False) is None or _yt_creds is None:
        return None
    from googleapiclient.discovery import build
    return build(ad, surum, credentials=_yt_creds, cache_discovery=False)


def canli_istatistik(video_idler):
    """İzlenme/beğeni/yorum ve yayın durumu (YouTube Data API, neredeyse anlık)."""
    yt = _yeni_servis("youtube", "v3")
    if yt is None:
        raise RuntimeError("YouTube bağlı değil.")
    simdi = datetime.datetime.now().isoformat(timespec="seconds")
    sonuc = {}
    for i in range(0, len(video_idler), 50):
        parca = video_idler[i:i + 50]
        r = yt.videos().list(part="statistics,status,snippet", id=",".join(parca)).execute()
        for it in r.get("items", []):
            st, du = it.get("statistics", {}), it.get("status", {})
            sonuc[it["id"]] = {"izlenme": int(st.get("viewCount", 0)), "begeni": int(st.get("likeCount", 0)),
                               "yorum": int(st.get("commentCount", 0)), "gizlilik": du.get("privacyStatus"),
                               "publishAt": du.get("publishAt"), "yukleme": du.get("uploadStatus"), "zaman": simdi,
                               "yayinlandi": (it.get("snippet") or {}).get("publishedAt")}
        for vid in parca:
            sonuc.setdefault(vid, {"silindi": True, "zaman": simdi})
    return sonuc


def istatistik_kaydet(sonuc):
    with _gecmis_kilit:
        g = gecmis_oku()
        for k in g:
            if k.get("video_id") in sonuc:
                k["istatistik"] = sonuc[k["video_id"]]
        _json_yaz(GECMIS_DOSYA, g)


def video_analitik(kayit):
    """Detaylı analitik (YouTube Analytics API). YouTube bu verileri 1-2 gün gecikmeli işler."""
    ya = _yeni_servis("youtubeAnalytics", "v2")
    if ya is None:
        raise RuntimeError("YouTube bağlı değil.")
    bas = (kayit.get("tarih") or "")[:10] or datetime.date.today().isoformat()
    son = datetime.date.today().isoformat()
    if bas > son:
        bas = son
    metrikler = ("views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,"
                 "likes,comments,shares,subscribersGained")
    try:
        r = ya.reports().query(ids="channel==MINE", startDate=bas, endDate=son, metrics=metrikler,
                               filters=f"video=={kayit['video_id']}").execute()
    except Exception as e:
        m = str(e)
        if "insufficient" in m.lower() or "scope" in m.lower():
            raise RuntimeError("Analitik izni yok: Ayarlar → Bağlantıyı kaldır → Bağlan, izin ekranında tüm "
                               "kutuları işaretle.")
        if "accessNotConfigured" in m or "has not been used" in m:
            raise RuntimeError("YouTube Analytics API projede henüz etkin değil (açıldıysa birkaç dakika bekle).")
        raise
    basliklar = [h["name"] for h in r.get("columnHeaders", [])]
    satirlar = r.get("rows") or []
    return dict(zip(basliklar, satirlar[0])) if satirlar else {}


def _analitik_sorgu(**k):
    """YouTube Analytics sorgusu -> [{sütun: değer}, ...]. Hataları anlaşılır mesaja çevirir."""
    ya = _yeni_servis("youtubeAnalytics", "v2")
    if ya is None:
        raise RuntimeError("YouTube bağlı değil.")
    try:
        r = ya.reports().query(ids="channel==MINE", **k).execute()
    except Exception as e:
        m = str(e)
        if "insufficient" in m.lower() or "scope" in m.lower():
            raise RuntimeError("Analitik izni yok: Ayarlar → Bağlantıyı kaldır → Bağlan, izin ekranında tüm "
                               "kutuları işaretle.")
        if "accessNotConfigured" in m or "has not been used" in m:
            raise RuntimeError("YouTube Analytics API projede henüz etkin değil (açıldıysa birkaç dakika bekle).")
        raise
    basliklar = [h["name"] for h in r.get("columnHeaders", [])]
    return [dict(zip(basliklar, satir)) for satir in r.get("rows") or []]


def kanal_gunluk(gun=28):
    """Son 'gun' günün günlük görüntüleme / izlenme süresi / abone verisi (eksik günler 0)."""
    son = datetime.date.today()
    bas = son - datetime.timedelta(days=gun - 1)
    satirlar = _analitik_sorgu(startDate=bas.isoformat(), endDate=son.isoformat(), dimensions="day", sort="day",
                               metrics="views,estimatedMinutesWatched,subscribersGained,subscribersLost")
    harita = {s_["day"]: s_ for s_ in satirlar}
    sonuc = []
    for i in range(gun):
        d = (bas + datetime.timedelta(days=i)).isoformat()
        s_ = harita.get(d, {})
        sonuc.append({"gun": d, "izlenme": int(s_.get("views", 0) or 0),
                      "dakika": float(s_.get("estimatedMinutesWatched", 0) or 0),
                      "abone": int(s_.get("subscribersGained", 0) or 0) - int(s_.get("subscribersLost", 0) or 0)})
    return sonuc


def videolar_analitik(idler):
    """Her videonun tüm zamanlar izlenme oranı ve ortalama izleme süresi: {video_id: {...}}."""
    sonuc = {}
    bugun = datetime.date.today().isoformat()
    for i in range(0, len(idler), 50):
        parca = idler[i:i + 50]
        satirlar = _analitik_sorgu(startDate="2020-01-01", endDate=bugun, dimensions="video", sort="-views",
                                   maxResults=50, filters="video==" + ",".join(parca),
                                   metrics="views,averageViewPercentage,averageViewDuration")
        for s_ in satirlar:
            sonuc[s_["video"]] = {"izlenme": int(s_.get("views", 0) or 0),
                                  "oran": float(s_.get("averageViewPercentage", 0) or 0),
                                  "sure": float(s_.get("averageViewDuration", 0) or 0)}
    return sonuc


def video_tutma(kayit):
    """İzleyici tutma eğrisi: videonun her %1'lik noktasında izleyicilerin ne kadarının hâlâ izlediği."""
    bas = (kayit.get("tarih") or "")[:10] or "2020-01-01"
    bugun = datetime.date.today().isoformat()
    satirlar = _analitik_sorgu(startDate=min(bas, bugun), endDate=bugun, dimensions="elapsedVideoTimeRatio",
                               sort="elapsedVideoTimeRatio", filters=f"video=={kayit['video_id']}",
                               metrics="audienceWatchRatio")
    return [(float(s_["elapsedVideoTimeRatio"]), float(s_["audienceWatchRatio"])) for s_ in satirlar]


def yayin_saati(kayit):
    """Videonun yayınlandığı yerel saat (bilinmiyorsa None)."""
    ist = kayit.get("istatistik") or {}
    for z in (ist.get("publishAt"), kayit.get("yayin_zamani"), ist.get("yayinlandi"), kayit.get("yuklenme_zamani")):
        if z:
            try:
                return datetime.datetime.fromisoformat(z.replace("Z", "+00:00")).astimezone()
            except ValueError:
                continue
    return None


def saat_analizi(gecmis=None):
    """Yayın saatine göre ortalama görüntüleme. Döndürür: (saat_grubu_listesi, öneri_metni_ya_da_None).
    Gruplar 3 saatlik dilimler; öneri için en az 6 yayınlanmış video ve 2 farklı dilim gerekir."""
    gecmis = gecmis if gecmis is not None else gecmis_oku()
    simdi = datetime.datetime.now().astimezone()
    dilimler = {}
    for k in gecmis:
        ist = k.get("istatistik") or {}
        if not k.get("video_id") or ist.get("silindi") or ist.get("izlenme") is None:
            continue
        t = yayin_saati(k)
        if not t or t > simdi - datetime.timedelta(hours=24):     # ilk 24 saati dolmamış video adil kıyas olmaz
            continue
        dilim = t.hour // 3
        dilimler.setdefault(dilim, []).append(int(ist.get("izlenme") or 0))
    gruplar = [{"dilim": d, "etiket": f"{d * 3:02d}–{d * 3 + 3:02d}", "ort": sum(v) / len(v), "adet": len(v)}
               for d, v in sorted(dilimler.items())]
    toplam = sum(g["adet"] for g in gruplar)
    if toplam < 6 or len(gruplar) < 2:
        return gruplar, None
    guvenilir = [g for g in gruplar if g["adet"] >= 2]     # tek videoluk dilim tesadüf olabilir
    if not guvenilir:
        return gruplar, None
    en = max(guvenilir, key=lambda g: g["ort"])
    return gruplar, (f"En çok izlenen yayınların {en['etiket']} arasında yayınlananlar "
                     f"(ortalama {en['ort']:.0f} görüntüleme, {en['adet']} video). Plan saatlerinden birini "
                     f"bu aralığa almayı dene.")


def basarili_konular(adet=5):
    """En iyi performans gösteren videoların konu ve başlıkları (görüntüleme + izlenme oranı)."""
    adaylar = []
    for k in gecmis_oku():
        ist = k.get("istatistik") or {}
        if k.get("video_id") and not ist.get("silindi") and int(ist.get("izlenme") or 0) > 0:
            puan = int(ist.get("izlenme") or 0) * (1 + float(k.get("izlenme_orani") or 0) / 100)
            adaylar.append((puan, k.get("baslik") or k.get("konu", "")))
    adaylar.sort(reverse=True)
    return [b for _, b in adaylar[:adet]] if len(adaylar) >= 3 else []


def kanal_bilgisi(yt):
    r = yt.channels().list(part="snippet,statistics", mine=True).execute()
    if not r.get("items"):
        return None
    c = r["items"][0]
    return {"ad": c["snippet"]["title"], "id": c["id"],
            "abone": c["statistics"].get("subscriberCount", "?"),
            "video": c["statistics"].get("videoCount", "?"),
            "izlenme": c["statistics"].get("viewCount", "?")}


def _kanal_norm(x):
    return re.sub(r"[^a-z0-9çğıöşü]", "", tr_kucuk(x or ""))


def kanal_dogrula(yt, log=print):
    """Bağlı kanal, ayarlardaki hedef kanal değilse hata verir (yanlış kanala yüklemeyi önler)."""
    hedef = ayar_oku().get("hedef_kanal", "").strip()
    b = kanal_bilgisi(yt)
    if not b:
        raise RuntimeError("Bağlı hesapta YouTube kanalı bulunamadı.")
    if hedef and _kanal_norm(b["ad"]) != _kanal_norm(hedef):
        raise RuntimeError(f"Bağlı kanal '{b['ad']}', ama yükleme '{hedef}' kanalına yapılmalı.\n"
                           "Ayarlar → Bağlantıyı kaldır, sonra Bağlan'a basıp kanal seçiminde "
                           f"'{hedef}' kanalını seç.")
    return b


def youtube_yukle(kayit, gizlilik="public", yayin_zamani=None, log=print, ilerleme=None):
    from googleapiclient.http import MediaFileUpload
    yt = yt_servis(True, log)
    kanal_dogrula(yt, log)
    durum = {"privacyStatus": gizlilik, "selfDeclaredMadeForKids": False,
             "embeddable": True}
    if yayin_zamani:
        durum["privacyStatus"] = "private"
        durum["publishAt"] = yayin_zamani.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    govde = {
        "snippet": {
            "title": baslik_sinirla(kayit["baslik"]),
            "description": kayit.get("aciklama", "")[:4900],
            "tags": kayit.get("etiketler", [])[:15],
            "categoryId": "24",
            "defaultLanguage": DIL, "defaultAudioLanguage": DIL,
        },
        "status": durum,
    }
    log(f"[+] YouTube'a yükleniyor: {kayit['baslik']}")
    medya = MediaFileUpload(kayit["dosya"], mimetype="video/mp4", chunksize=4 * 1024 * 1024,
                            resumable=True)        # küçük parçalar: bağlantı koparsa az veri kaybolur
    istek = yt.videos().insert(part="snippet,status", body=govde, media_body=medya)
    yanit, hata_sayisi = None, 0
    while yanit is None:
        iptal_kontrol()
        try:
            st, yanit = iptal_edilebilir(istek.next_chunk)
            if st and ilerleme:
                ilerleme(st.progress())
        except IptalHatasi:
            raise
        except Exception as e:
            hata_sayisi += 1
            if "uploadLimitExceeded" in str(e) or "exceeded the number of videos" in str(e):
                raise YuklemeSiniriHatasi(
                    "YouTube günlük yükleme sınırına ulaşıldı. Kanal 24 saat içinde yükleyebileceği video sayısını "
                    "doldurdu; sınır genellikle 24 saat içinde kalkar. Video kaydedildi, sonra Videolarım'dan "
                    "yükleyebilirsin. (Telefonla doğrulanmış kanallarda sınır genellikle daha yüksektir.)")
            m_ = str(e)
            baglanti = any(x in m_ for x in ("EOF occurred", "SSL", "Connection", "connection", "timed out",
                                             "reset by peer", "Broken pipe", "RemoteDisconnected", "10054", "10060"))
            if (hata_sayisi > (10 if baglanti else 5)) or "quota" in m_.lower():
                if baglanti:
                    raise RuntimeError("YouTube'a bağlantı yükleme sırasında defalarca koptu (internet/ağ kesintisi). "
                                       "Video kaydedildi; bağlantın düzelince Düzenle ve yükle ile tekrar dene. "
                                       f"Ayrıntı: {m_[:150]}") from e
                raise
            if baglanti:
                # kopan bağlantı aynı nesneyle tekrar denenince hep aynı hatayı verir: yeni bağlantı kur, yüklemenin
                # kaldığı yerden devam et (resumable upload adresi korunur)
                log(f"[~] Bağlantı koptu, yeniden bağlanılıyor ({hata_sayisi}. deneme)...")
                try:
                    yeni = _yeni_servis("youtube", "v3")
                    if yeni is not None and getattr(yeni, "_http", None) is not None:
                        istek.http = yeni._http
                except Exception:
                    pass
            bekle_iptal(min(60, 2 ** min(hata_sayisi, 6)))
    vid = yanit["id"]
    kayit.update(video_id=vid, durum="yuklendi", url=f"https://youtube.com/shorts/{vid}"
                 if kayit.get("yon") == "dikey" else f"https://youtu.be/{vid}",
                 gizlilik=durum["privacyStatus"], yayin_zamani=durum.get("publishAt"),
                 yuklenme_zamani=datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    gecmis_kaydet(kayit)
    kapak_yukle(kayit, log)
    if yayin_zamani:
        log(f"[✓] Yüklendi, {yayin_zamani.strftime('%d.%m %H:%M')} için planlandı: {kayit['url']}")
    else:
        log(f"[✓] Yüklendi ({GIZLILIK.get(gizlilik, gizlilik)}): {kayit['url']}")
    try:
        ilk_yorum_hazirla(kayit, yt, log)
    except IptalHatasi:
        raise
    except Exception as e:
        log(f"[!] İlk yorum: {str(e)[:150]}")
    return kayit


# ---------------------------------------------------------------------------
# KENDİ VİDEOLARIMIZA OTOMATİK İLK YORUM (izleyiciyi yorum yazmaya davet eder)
# Sadece kendi kanalımızın videolarına, video başına tek yorum. Başka kanallara yorum atılmaz.
# ---------------------------------------------------------------------------
def ilk_yorum_metni(kayit, log=print):
    hikaye = " ".join((kayit.get("hikaye") or "").split()[:220])
    baslik = (kayit.get("baslik") or "").replace(" #shorts", "")
    onceki = [g["ilk_yorum"]["metin"] for g in gecmis_oku()[-12:]
              if isinstance(g.get("ilk_yorum"), dict) and g["ilk_yorum"].get("metin")]
    if nblm_mi():
        prompt = f"""Kişisel gelişim / öğrenme kanalı "BirAdım"ın kısa, öğretici bir videosunun altına kanal sahibi olarak
İLK YORUMU yazacaksın. Amaç izleyicinin kendi deneyimini yazmak istemesi.
Video başlığı: {baslik}
Videoda anlatılanlar: {hikaye}

Kurallar:
- Tek ya da iki kısa cümle, sonu SORU. En fazla 120 karakter. En fazla 1 emoji.
- Videodaki tekniğe/fikre özel olsun: "Sen hangisini yapıyorsun?", "Bunu denedin mi, ne oldu?", "En zorlandığın an
  hangisi?" gibi kişinin kendini anlatacağı bir soru. Korku, gerilim, doğaüstü ima YOK.
- Link, hashtag, @etiket, "abone ol / beğen" YOK.
- Şunları tekrar etme: {' | '.join(onceki) or '-'}
Sadece yorum metnini yaz."""
    elif DIL == "tr":
        prompt = f"""Kısa bir gizem/korku hikâyesi videosunun altına, kanal sahibi olarak İLK YORUMU yazacaksın.
Amaç izleyicinin cevap yazmak istemesi.
Video başlığı: {baslik}
Hikâye: {hikaye}

Kurallar:
- Tek cümlelik ya da iki kısa cümlelik bir SORU. En fazla 120 karakter. En fazla 1 emoji.
- Hikâyeye özel olsun: izleyiciye "sen olsan ne yapardın", "hangi detayı fark ettin", "kimin yerinde olmak
  isterdin" gibi düşündürücü bir soru sor. Sonu doğrudan söyleme, ama hikâyeyi izleyen anlasın.
- Link, hashtag, @etiket, "abone ol / beğen" çağrısı YOK.
- Şunları tekrar etme: {' | '.join(onceki) or '-'}
Sadece yorum metnini yaz."""
    else:
        prompt = f"""You are the channel owner writing the FIRST COMMENT under a short mystery/horror story video, in
natural English. The goal is to make viewers want to reply.
Video title: {baslik}
Story: {hikaye}

Rules:
- One or two short sentences ending in a QUESTION. Max 120 characters. At most 1 emoji.
- Specific to this story: ask "what would you have done", "did you catch the clue", "whose side are you on" etc.
  Don't spell out the ending, but viewers who watched should get it.
- No links, hashtags, @mentions, "like/subscribe" requests.
- Don't repeat these: {' | '.join(onceki) or '-'}
Write only the comment text."""
    metin = _gemini_uret(prompt, log).strip().strip('"“”').splitlines()[0].strip()
    metin = re.sub(r"https?://\S+|#\w+|@\w+", "", metin).strip()
    if len(metin) < 8:
        raise RuntimeError("ilk yorum metni boş geldi")
    return metin[:300]


def _ilk_yorum_gonder(yt, video_id, metin):
    yt.commentThreads().insert(part="snippet", body={"snippet": {"videoId": video_id, "topLevelComment": {
        "snippet": {"textOriginal": metin}}}}).execute()


def ilk_yorum_hazirla(kayit, yt=None, log=print):
    """Yüklemeden hemen sonra çağrılır: yorumu yazar; video şu an herkese açıksa atar, planlıysa yayın saatini bekler."""
    if not ayar_oku().get("ilk_yorum", True) or not kayit.get("video_id"):
        return
    if isinstance(kayit.get("ilk_yorum"), dict) and kayit["ilk_yorum"].get("durum") == "atildi":
        return
    if not yorum_izni_var():
        log("[~] İlk yorum atlanıyor: yorum yazma izni yok (Yorumlar sayfasında 'Yorum izni ver').")
        return
    try:
        metin = ilk_yorum_metni(kayit, log)
    except IptalHatasi:
        raise
    except Exception as e:
        log(f"[!] İlk yorum yazılamadı: {str(e)[:150]}")
        return
    kayit["ilk_yorum"] = {"metin": metin, "durum": "bekliyor"}
    if kayit.get("gizlilik") == "public" and not kayit.get("yayin_zamani"):
        _ilk_yorum_at(kayit, yt, log)
    else:
        log(f"[+] İlk yorum hazır, video yayınlanınca atılacak: \"{metin}\"")
    gecmis_kaydet(kayit)


def _ilk_yorum_at(kayit, yt, log):
    try:
        yt = yt or _yeni_servis("youtube", "v3")
        if yt is None:
            return
        _ilk_yorum_gonder(yt, kayit["video_id"], kayit["ilk_yorum"]["metin"])
        kayit["ilk_yorum"].update(durum="atildi", zaman=datetime.datetime.now().isoformat(timespec="seconds"))
        log(f"[✓] İlk yorum atıldı: \"{kayit['ilk_yorum']['metin']}\" (Studio'dan sabitleyebilirsin)")
    except IptalHatasi:
        raise
    except Exception as e:
        m = str(e)
        deneme = kayit["ilk_yorum"].get("deneme", 0) + 1
        kayit["ilk_yorum"]["deneme"] = deneme
        if deneme >= 3 or "commentsDisabled" in m or "videoNotFound" in m:
            kayit["ilk_yorum"].update(durum="hata", neden=m[:200])
        log(f"[!] İlk yorum atılamadı ({m[:150]})")


def bekleyen_ilk_yorumlar(log=print):
    """Yayın saati gelmiş planlı videoların bekleyen ilk yorumlarını atar. Döndürür: atılan sayısı."""
    if not ayar_oku().get("ilk_yorum", True):
        return 0
    simdi = datetime.datetime.now(datetime.timezone.utc)
    adaylar = []
    for k in gecmis_oku():
        iy = k.get("ilk_yorum")
        if not (isinstance(iy, dict) and iy.get("durum") == "bekliyor" and k.get("video_id")):
            continue
        try:
            zaman = datetime.datetime.strptime(k.get("yayin_zamani") or "", "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=datetime.timezone.utc)
        except ValueError:
            zaman = simdi
        if zaman <= simdi:
            adaylar.append(k)
    if not adaylar:
        return 0
    kilit = os.path.join(GECICI, "ilk_yorum.kilit")
    if os.path.exists(kilit) and time.time() - os.path.getmtime(kilit) < 180:
        return 0        # başka bir işlem (gece görevi / yorum görevi) şu an atıyor: çift yorum olmasın
    with _ilk_yorum_kilit:
        with open(kilit, "w") as f:
            f.write(str(os.getpid()))
        try:
            return _bekleyenleri_at(adaylar, simdi, log)
        finally:
            try:
                os.remove(kilit)
            except OSError:
                pass


_ilk_yorum_kilit = threading.Lock()


def _bekleyenleri_at(adaylar, simdi, log):
    taze = {k.get("video_id"): k for k in gecmis_oku()}      # kilit beklerken başkası atmış olabilir
    adaylar = [taze[k["video_id"]] for k in adaylar if isinstance((taze.get(k["video_id"]) or {}).get("ilk_yorum"),
                                                                  dict)
               and taze[k["video_id"]]["ilk_yorum"].get("durum") == "bekliyor"]
    if not adaylar:
        return 0
    yt = _yeni_servis("youtube", "v3")
    if yt is None:
        return 0
    atilan = 0
    for i in range(0, len(adaylar), 50):
        grup = adaylar[i:i + 50]
        r = yt.videos().list(part="status", id=",".join(k["video_id"] for k in grup)).execute()
        durumlar = {v["id"]: v["status"].get("privacyStatus") for v in r.get("items", [])}
        for k in grup:
            d = durumlar.get(k["video_id"])
            if d is None:
                k["ilk_yorum"].update(durum="hata", neden="video bulunamadı")
            elif d != "public":
                if k.get("yayin_zamani") is None or simdi - datetime.datetime.strptime(
                        k["yayin_zamani"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc) \
                        > datetime.timedelta(days=2):
                    k["ilk_yorum"].update(durum="hata", neden=f"video {d}")
                continue
            else:
                _ilk_yorum_at(k, yt, log)
                atilan += k["ilk_yorum"].get("durum") == "atildi"
            gecmis_kaydet(k)
    return atilan


# ---------------------------------------------------------------------------
# 9b. NOTEBOOKLM KANALI (BirAdım): konu + kaynak metni Gemini hazırlar, video NotebookLM'de üretilir,
# indirilen video burada işlenir (NotebookLM logosu/kapanışı kesilir, köşe yazısı rozetle kapanır,
# alt yazı + açılış kancası + kapanış kartı eklenir) ve yayın planına göre yüklenir.
# ---------------------------------------------------------------------------
BIRADIM_ALANLARI = ["Karışık", "Öğrenme teknikleri", "Psikoloji", "Alışkanlıklar", "Verimlilik", "İletişim",
                    "Kariyer", "Beyin ve bilim efsaneleri", "Duygular", "Para ve kararlar"]
# Kanal verisinden (5 Eki – 1 Kas 2026) çıkan dersler: konu ve başlık isteminde kullanılır
BIRADIM_DERSLER = """Kanalın son 28 gününde en çok izlenen videolar ve dersleri:
- "Hedeflerini Kimseye Anlatma! (İşte Gizli Nedeni)" 1.543 izlenme: sezgiye ters bir YASAK + parantezde merak.
- "Sadece Okumayı Bırak, Bunu Yap! (Aktif Hatırlama)" 1.258 izlenme, izlenme oranı %63,6 (en yüksek), kanala en
  çok yeni izleyici getiren video: "X'i bırak, Y'yi yap" + parantezde bilimsel tekniğin ADI. Somut, hemen
  uygulanabilir öğrenme tekniği izleyiciyi sonuna kadar tutuyor.
- "Kendini İfade Etme Korkusu Nasıl Yenilir?" 1.133 izlenme, %50: herkesin yaşadığı bir korku + çözüm sözü.
- "Aynada Kendine Yalan Söylemeyi Bırak!" 1.127 ama izlenme oranı %28: başlık çekti, video tutamadı.
- "Beynimizin Sadece %10'unu mu Kullanıyoruz? (Büyük Efsane)" 632, %44,5: efsane çürütme iyi çalışıyor.
- Zayıf olanlar: soyut ve genel başlıklar ("Kusursuz Plan Diye Bir Şey...", 17 izlenme), ilk saniyesi yavaş
  başlayan videolar. İzleyicilerin %65'i ilk saniyelerde kaydırıyor; %98'i kanalı ilk kez görüyor."""


ROZET_XY, ROZET_GEN = (0.665, 0.930), 0.325      # rozetin yeri ve genişliği (video genişliğine oranla)


def _rozet_filtre(girisler, filtre, son, W, H, ayar, rozet):
    """Köşedeki NotebookLM / Gemini Notebook yazısını rozetle kapatır. Dikeyde kanalın ölçtüğümüz yeri, yatayda
    sağ alt köşeyi kullanır. Yeni etiketi döndürür."""
    ri = girisler.count("-i")
    girisler += ["-i", rozet]
    if H >= W:
        x, y = ayar.get("nblm_rozet_xy") or ROZET_XY
        bw = int(W * float(ayar.get("nblm_rozet_gen", ROZET_GEN)))
        konum = f"x={int(W * x)}:y={int(H * y)}"
    else:
        bw = int(W * float(ayar.get("nblm_rozet_gen_yatay", 0.21)))
        konum = "x=W-w*0.94:y=H-h*0.94"   # rozet köşeden biraz taşar; en alttaki "Gemini Notebook" yazısını tam kapatır
    filtre.append(f"[{ri}:v]scale={bw}:-1[rz];[{son}][rz]overlay={konum}[v1]")
    return "v1"


def kapanis_sesi_bul():
    """Kapanış kartında çalan kısa ses (kanal klasöründe kapanis_sesi.mp3/wav/m4a)."""
    for uz in (".mp3", ".wav", ".m4a"):
        p_ = os.path.join(profil_klasoru(AKTIF_PROFIL), "kapanis_sesi" + uz)
        if os.path.exists(p_):
            return p_
    return None


def _ses_kanal_sayisi(dosya):
    try:
        with av.open(dosya) as c_:
            return c_.streams.audio[0].channels if c_.streams.audio else 0
    except Exception:
        return 2


def _kapanis_sesi_ekle(girisler, filtre, ses_etiket, toplam, ayar, kaynak=None):
    """Kapanış kartı gelince kısa kapanış sesini videonun sesine karıştırır. Yeni ses etiketini döndürür."""
    ks = kapanis_sesi_bul() if ayar.get("kapanis", True) else None
    if not ks:
        return ses_etiket
    D = float(ayar.get("kapanis_sure", 4))
    ms = int(max(0.0, toplam - D - 0.4) * 1000)
    ki = girisler.count("-i")
    girisler += ["-i", ks]
    filtre.append(f"[{ki}:a]aresample=44100,aformat=channel_layouts=stereo,volume=0.85,adelay={ms}|{ms},apad,"
                  f"atrim=duration={toplam:.3f}[kss];[{ses_etiket}]aresample=44100,"
                  + ("pan=stereo|c0=c0|c1=c0" if kaynak and _ses_kanal_sayisi(kaynak) == 1      # mono ses kısılmasın
                     else "aformat=channel_layouts=stereo") + "[ana_s];"
                  f"[ana_s][kss]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[nks]")
    return "nks"


def nblm_mi():
    return profiller_oku()["profiller"].get(AKTIF_PROFIL, {}).get("tur") == "notebooklm"


def _nblm_dosya(*ad):
    return os.path.join(profil_klasoru(AKTIF_PROFIL), *ad)


def nblm_kuyruk_oku():
    return _json_oku(_nblm_dosya("kuyruk.json"), [])


def nblm_kuyruk_yaz(k):
    _json_yaz(_nblm_dosya("kuyruk.json"), k[-300:])


def nblm_paket_guncelle(pid, **alanlar):
    k = nblm_kuyruk_oku()
    for p_ in k:
        if p_.get("id") == pid:
            p_.update(alanlar)
    nblm_kuyruk_yaz(k)


def kanal_performans_ozeti(log=print, gun=90):
    """Kanalın TÜM videolarının (programla yüklenmeyenler dahil) izlenme ve izlenme oranı: en iyiler ve en zayıflar.
    Günde bir kez YouTube'dan çekilir, kanal klasöründe saklanır. Döndürür: metin (konu istemine eklenir)."""
    dosya = _nblm_dosya("kanal_performans.json")
    v = _json_oku(dosya, {})
    if v.get("tarih") == datetime.date.today().isoformat() and v.get("metin"):
        return v["metin"]
    if not os.path.exists(TOKEN):
        return v.get("metin", "")
    try:
        bugun = datetime.date.today()
        satirlar = _analitik_sorgu(startDate=(bugun - datetime.timedelta(days=gun)).isoformat(),
                                   endDate=bugun.isoformat(), dimensions="video", sort="-views", maxResults=50,
                                   metrics="views,averageViewPercentage,likes")
        if not satirlar:
            return v.get("metin", "")
        yt = _yeni_servis("youtube", "v3")
        basliklar = {}
        idler = [s_["video"] for s_ in satirlar]
        for i in range(0, len(idler), 50):
            r = yt.videos().list(part="snippet", id=",".join(idler[i:i + 50])).execute()
            for it in r.get("items", []):
                basliklar[it["id"]] = (it["snippet"]["title"], it["snippet"].get("publishedAt", "")[:10])
        veri = []
        for s_ in satirlar:
            b = basliklar.get(s_["video"])
            if not b:
                continue
            iz, oran = int(s_.get("views", 0) or 0), float(s_.get("averageViewPercentage", 0) or 0)
            veri.append({"baslik": b[0], "tarih": b[1], "izlenme": iz, "oran": oran,
                         "puan": iz * (1 + oran / 100)})
        sinir = (bugun - datetime.timedelta(days=3)).isoformat()
        iyiler = sorted(veri, key=lambda x: x["puan"], reverse=True)[:8]
        zayif = sorted([x for x in veri if x["tarih"] <= sinir and x not in iyiler], key=lambda x: x["puan"])[:5]
        satir = lambda x: f'- "{x["baslik"]}": {x["izlenme"]} izlenme, izlenme oranı %{x["oran"]:.0f}'  # noqa: E731
        metin = (f"Kanalın son {gun} gündeki GÜNCEL verisi (YouTube'dan, programla yüklenmeyen videolar dahil):\n"
                 "EN İYİLER (başlık kalıplarını ve konu türlerini örnek al, aynı konuyu tekrar etme):\n"
                 + "\n".join(satir(x) for x in iyiler)
                 + ("\nEN ZAYIFLAR (bu başlık/konu tarzından kaçın):\n" + "\n".join(satir(x) for x in zayif)
                    if zayif else ""))
        _json_yaz(dosya, {"tarih": bugun.isoformat(), "metin": metin, "veri": veri})
        log(f"[+] Kanalın {len(veri)} videosunun performansı okundu; konu buna göre seçilecek.")
        return metin
    except IptalHatasi:
        raise
    except Exception as e:
        log(f"[~] Kanal verisi okunamadı, kayıtlı derslerle devam ({str(e)[:120]})")
        return v.get("metin", "")


# Kazanan içerik tarzı (somut, hemen uygulanabilir, bilimsel adı olan teknik) sabit kalır; değişen şey konu
# alanı ve başlık kalıbı. Her yeni konu, son konularda en az kullanılan alan + kalıptan seçilir.
BIRADIM_KALIPLAR = [
    ("birak", 3, '"X\'i Bırak, Bunu Yap! (Tekniğin Adı)" — en iyi tutan kalıp'),
    ("asla", 2, '"X\'i Asla Yapma! (İşte Nedeni)"'),
    ("efsane", 2, '"Y Gerçekten Doğru mu? (Büyük Efsane)" — yaygın bir yanlışı bilimle çürüt'),
    ("nasil", 2, '"X Nasıl Yenilir?" ya da "X\'i 2 Dakikada Çöz" — herkesin yaşadığı bir sorun + çözüm sözü'),
    ("sir", 1, '"Başarılı İnsanların X Sırrı (Tekniğin Adı)" — merak + öğretici teknik'),
    ("soru", 1, '"Neden Hep X Yapıyorsun? (Beyninin Oyunu)" — izleyicinin kendini tanıdığı bir soru'),
]
BIRADIM_ALAN_AGIRLIK = {"Öğrenme teknikleri": 3, "Psikoloji": 2, "Alışkanlıklar": 2, "Verimlilik": 2,
                        "İletişim": 1, "Kariyer": 1, "Beyin ve bilim efsaneleri": 2, "Duygular": 1,
                        "Para ve kararlar": 1}


def _cesit_sec(son_kullanilan, secenekler):
    """Son konularda en az kullanılan seçeneği ağırlığına göre seçer (aynı alan/kalıp üst üste gelmesin)."""
    son = son_kullanilan[-8:]
    puan = {k: (son.count(k) + (2 if son[-1:] == [k] else 0)) / max(0.5, a) for k, a in secenekler.items()}
    en_az = min(puan.values())
    adaylar = [k for k, v in puan.items() if v <= en_az + 0.01]
    return random.choices(adaylar, weights=[secenekler[k] for k in adaylar])[0]


def nblm_konu_uret(alan="Karışık", konu=None, log=print):
    """Gemini: konu + başlık + açılış kancası + NotebookLM kaynak metni + NotebookLM istemi + açıklama/etiket."""
    kuyruk = nblm_kuyruk_oku()
    eskiler = [g.get("konu", "") for g in gecmis_oku()] + [p_.get("konu", "") for p_ in kuyruk]
    canli = kanal_performans_ozeti(log)
    eskiler += re.findall(r'- "([^"]+)"', canli)       # kanaldaki eski videolar da tekrar edilmesin
    alan_ = (_cesit_sec([p_.get("alan", "") for p_ in kuyruk], BIRADIM_ALAN_AGIRLIK)
             if alan == "Karışık" else alan)
    kalip_id = _cesit_sec([p_.get("kalip", "") for p_ in kuyruk], {k: a for k, a, _ in BIRADIM_KALIPLAR})
    kalip = next(t for k, _, t in BIRADIM_KALIPLAR if k == kalip_id)
    son_basliklar = [p_.get("baslik", "") for p_ in kuyruk[-6:]]
    prompt = f"""Sen "BirAdım" adlı Türkçe YouTube Shorts kanalının içerik editörüsün. Kanalın sloganı:
"Öğren, düşün, ilerle." Videolar NotebookLM'in Video Özeti ile, verdiğin kaynak metinden üretilir (çizim tarzı
anlatım, 50-75 saniye). Hedef kitle: 18-35 yaş, kendini geliştirmek isteyen Türk gençleri.

{BIRADIM_DERSLER}
{canli}

GÖREV: {f'Şu konuda bir video paketi hazırla: "{konu}".' if konu else f'"{alan_}" alanında YENİ bir video konusu bul ve paketini hazırla.'}
Konu bilimsel/psikolojik bir gerçeğe ya da bilinen bir tekniğe dayansın (adı konulabilsin: "Zeigarnik etkisi",
"Pomodoro", "Aralıklı tekrar" gibi); uydurma istatistik YASAK. Hemen uygulanabilir somut bir şey öğretsin.
Şu konulara benzemesin: {'; '.join(e for e in eskiler[-40:] if e) or '-'}

Alanlar:
- konu: tek cümle, ne anlatıldığı.
- baslik: en fazla 55 karakter. BU SEFER şu kalıbı kullan: {kalip}. Sonda 1 uygun emoji. Hashtag YOK.
  Son başlıklar şunlardı, kalıbı ve kelimeleri tekrar etme: {' | '.join(son_basliklar) or '-'}
  Değişmeyen kural: konu yine SOMUT, hemen uygulanabilir ve bilimsel adı olan bir tekniğe/etkiye dayansın
  (kanalda en iyi tutan "Aktif Hatırlama" videosu gibi).
- kanca: videonun ilk 2,5 saniyesinde ekranda büyük yazacak 2-6 kelimelik çarpıcı cümle (ör. "HEDEFLERİNİ KİMSEYE
  SÖYLEME"). Başlıkla aynı olmasın, merak uyandırsın.
- kaynak: NotebookLM'e verilecek 280-420 kelimelik Türkçe kaynak metin. Yapısı: (1) çarpıcı açılış iddiası,
  (2) herkesin yaptığı hata, (3) bilimsel açıklama ve tekniğin adı (varsa araştırmacı/çalışma adı, uydurma değil),
  (4) 3 adımlık uygulama, (5) gündelik bir örnek, (6) tek cümlelik akılda kalan kapanış. Düz paragraflar.
- istem: NotebookLM "Video Özeti"nin özelleştirme kutusuna yapıştırılacak Türkçe talimat (3-5 cümle): Türkçe
  anlat; giriş/selamlama yapmadan ilk cümlede çarpıcı iddiayla başla; en fazla 70 saniye; 3 adımı tek tek göster;
  sonda tek cümlelik özet; hedef kitle genç yetişkinler.
- aciklama: 2-3 cümle merak uyandıran açıklama + sonda "#biradım #shorts" ve 2-3 konu hashtag'i.
- etiketler: 8-12 Türkçe etiket.

Yanıtı YALNIZCA şu JSON biçiminde ver:
{{"konu": "...", "baslik": "...", "kanca": "...", "kaynak": "...", "istem": "...", "aciklama": "...", "etiketler": ["..."]}}"""
    for deneme in range(3):
        v = _json_coz(_gemini_uret(prompt, log, json_mod=True))
        if not isinstance(v, dict) or not str(v.get("kaynak", "")).strip():
            continue
        k_ = str(v.get("konu", "")).strip()
        if not konu and max([benzerlik(k_, e) for e in eskiler if e] + [0]) >= 0.45 and deneme < 2:
            log("[~] Konu öncekilere fazla benzedi, yenisi isteniyor...")
            prompt += f"\n\nÖNEMLİ: '{k_}' daha önce işlenene çok benziyor; bambaşka bir konu seç."
            continue
        baslik = baslik_sinirla(re.sub(r"\s*#\w+", "", str(v.get("baslik") or k_)).strip(), 90)
        aciklama = str(v.get("aciklama", "")).strip()
        if "#biradım" not in aciklama.lower():
            aciklama += "\n\n#biradım #shorts"
        aciklama += ("\n\nBu video yapay zeka araçları (NotebookLM) yardımıyla hazırlanmıştır; içerik kanal tarafından "
                     "seçilip düzenlenmiştir.")
        paket = {"id": datetime.datetime.now().strftime("%Y%m%d%H%M%S") + f"{random.randint(0, 99):02d}",
                 "tarih": datetime.datetime.now().isoformat(timespec="seconds"), "alan": alan_, "kalip": kalip_id,
                 "konu": k_ or konu, "baslik": baslik, "kanca": str(v.get("kanca", "")).strip()[:60],
                 "kaynak": str(v.get("kaynak", "")).strip(), "istem": str(v.get("istem", "")).strip(),
                 "aciklama": aciklama[:4900],
                 "etiketler": [str(e).strip().lstrip("#") for e in (v.get("etiketler") or []) if str(e).strip()][:15],
                 "durum": "video_bekliyor"}
        kuyruk = nblm_kuyruk_oku()
        kuyruk.append(paket)
        nblm_kuyruk_yaz(kuyruk)
        log(f"[+] Yeni konu hazır: {paket['baslik']}")
        return paket
    raise RuntimeError("Gemini konu paketini hazırlayamadı, tekrar deneyin.")


def nblm_eslesen_paket(dosya):
    """İndirilen videonun adına yeterince benzeyen bekleyen konu; benzemiyorsa None (başlık videonun kendi
    konuşmasından yazılır — yanlış konuyla eşleşip içerikle başlık uyuşmasın)."""
    bekleyen = [p_ for p_ in nblm_kuyruk_oku() if p_.get("durum") == "video_bekliyor"]
    if not bekleyen:
        return None
    ad = re.sub(r"[_\-.]+", " ", os.path.splitext(os.path.basename(dosya))[0])
    en = max(bekleyen, key=lambda p_: max(benzerlik(ad, p_.get("konu", "")), benzerlik(ad, p_.get("baslik", ""))))
    if max(benzerlik(ad, en.get("konu", "")), benzerlik(ad, en.get("baslik", ""))) >= 0.5:
        return en
    return None      # zayıf eşleşme: konu videonun konuşmasından bulunur


def _kare_parlaklik(video, bas, sure, fps=4):
    """[(zaman, ortalama, sapma)] — küçük gri kareler üzerinden."""
    w, h = 18, 32
    r = subprocess.run([FFMPEG, "-v", "error", "-ss", f"{max(0.0, bas):.2f}", "-t", f"{sure:.2f}", "-i", video,
                        "-vf", f"fps={fps},scale={w}:{h},format=gray", "-f", "rawvideo", "-"],
                       capture_output=True, creationflags=NO_WINDOW)
    veri, n = r.stdout, w * h
    sonuc = []
    for i in range(len(veri) // n):
        px_ = veri[i * n:(i + 1) * n]
        ort = sum(px_) / n
        beyaz_oran = sum(1 for x in px_ if x > 225) / n
        sonuc.append((max(0.0, bas) + i / fps, ort, beyaz_oran))
    return sonuc


def _kucuk_kareler(video, bas, sure, fps=8, w=18, h=32):
    r = subprocess.run([FFMPEG, "-v", "error", "-ss", f"{max(0.0, bas):.2f}", "-t", f"{sure:.2f}", "-i", video,
                        "-vf", f"fps={fps},scale={w}:{h},format=gray", "-f", "rawvideo", "-"],
                       capture_output=True, creationflags=NO_WINDOW)
    n = w * h
    return [(max(0.0, bas) + i / fps, r.stdout[i * n:(i + 1) * n]) for i in range(len(r.stdout) // n)]


def _eski_kapanis_imzasi():
    """Kanalın eski kapanış kartının küçük gri imzası (18x32). Hazır videolarda sadece bu kart kesilir."""
    for p_ in (_nblm_dosya("eski_kapanis_imza.json"), yol("biradim", "eski_kapanis_imza.json")):
        v = _json_oku(p_, None)
        if isinstance(v, list) and len(v) == 18 * 32:
            return v
    return None


def eski_kart_var_mi(video, sure):
    """Videonun sonunda kanalın ESKİ kapanış kartı var mı? Varsa video kullanıcının kendi düzenlediği hazır videodur
    (zaten hızlandırılmış/alt yazılı); yoksa NotebookLM'den gelen ham videodur."""
    imza = _eski_kapanis_imzasi()
    if not imza:
        return False
    kareler = _renkli_kareler(video, max(0.0, sure - 2.5), min(2.5, sure), fps=6)
    if not kareler:
        return False
    rgb = kareler[-1][1]
    g = [(rgb[3 * i] * 299 + rgb[3 * i + 1] * 587 + rgb[3 * i + 2] * 114) // 1000 for i in range(len(rgb) // 3)]
    return sum(abs(a - b) for a, b in zip(g, imza)) / len(imza) < 6


def hazir_son_kesim(video, sure, log=print):
    """Hazır videonun sonundaki ESKİ kapanış kartını (kanalın bilinen kartıyla birebir eşleşiyorsa) ve hemen
    önündeki NotebookLM / Gemini Notebook logo karelerini bulur; içeriğin bittiği saniyeyi döndürür.
    Eşleşen kart yoksa sadece en sondaki logo karelerini keser — içerikten asla kesmez."""
    bas = max(0.0, sure - 18)
    kareler = _renkli_kareler(video, bas, sure - bas)
    if len(kareler) < 10:
        return None
    imza = _eski_kapanis_imzasi()

    def gri(rgb):
        return [(rgb[3 * i] * 299 + rgb[3 * i + 1] * 587 + rgb[3 * i + 2] * 114) // 1000 for i in range(len(rgb) // 3)]

    def kart_mi(rgb):
        if not imza:
            return False
        g = gri(rgb)
        return sum(abs(a - b) for a, b in zip(g, imza)) / len(imza) < 6
    j = len(kareler)
    while j > 0 and kart_mi(kareler[j - 1][1]):
        j -= 1
    kart_var = len(kareler) - j >= 15                  # en az 1 sn eski kart
    if not kart_var:
        j = len(kareler)
    k = j
    while k > 0 and _logo_ekrani_mi(kareler[k - 1][1]) and kareler[j - 1][0] - kareler[k - 1][0] <= 4:
        k -= 1
    if k < j:
        k = _geri_yuru(kareler, k)
    if k == len(kareler):
        return None
    kes = kareler[k][0]
    if kart_var:
        log(f"[+] Sondaki eski kapanış kartı kesiliyor ({sure - kareler[j][0]:.1f} sn).")
    if k < j:
        log(f"[+] NotebookLM / Gemini Notebook logo ekranı kesiliyor ({kareler[j - 1][0] - kareler[k][0] + 1 / 15:.1f} sn).")
    kes = max(0.0, kes - (LOGO_GECIS_PAYI if k < j else 0.12))   # logonun belirdiği geçiş kareleri de gitsin
    return kes if kes >= sure * 0.5 else None


def nblm_slayt_bul(video, sure, log=print):
    """Videonun son %45'inde NotebookLM / Gemini Notebook beyaz logo ekranının başladığı an (yoksa None).
    Hazır videolarda bu ekrandan sonra genelde eski kapanış kartı gelir; ikisi birlikte kesilir."""
    bas = sure * 0.55
    kareler = _kare_parlaklik(video, bas, sure - bas, fps=8)
    for t, o, oran in kareler:
        if oran >= 0.95 and o > 225:
            log(f"[+] NotebookLM logo ekranı {t:.1f}. saniyede bulundu; oradan sonrası kesiliyor "
                f"({sure - t:.1f} sn).")
            return max(0.0, t - 0.06)
    return None


def _renkli_kareler(video, bas, sure, fps=15, w=18, h=32):
    r = subprocess.run([FFMPEG, "-v", "error", "-ss", f"{max(0.0, bas):.2f}", "-t", f"{sure:.2f}", "-i", video,
                        "-vf", f"fps={fps},scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                       capture_output=True, creationflags=NO_WINDOW)
    n = w * h * 3
    return [(max(0.0, bas) + i / fps, r.stdout[i * n:(i + 1) * n]) for i in range(len(r.stdout) // n)]


LOGO_GECIS_PAYI = 0.35    # logo geçişinden sonra ek güvenlik payı (sn)


def _soguk_beyaz_mi(rgb):
    """Logo ekranının belirme anı: zemin çoktan soğuk beyaza dönmüş ama ortadaki renkli logo henüz büyük/hareketli
    (tam 'logo ekranı' sayılmaz). İçerik sıcak krem olduğu için ayırt edilir."""
    n = len(rgb) // 3
    if not n:
        return False
    R, G, B = sum(rgb[0::3]) / n, sum(rgb[1::3]) / n, sum(rgb[2::3]) / n
    return (B - R) >= -4 and (R + G + B) / 3 >= 200


def _koyu_mu(rgb, esik=0.85):
    """Yeni NotebookLM / Gemini Notebook kapanışı: neredeyse siyah zemin üstünde küçük beyaz logo."""
    n = len(rgb) // 3
    if not n:
        return False
    koyu = sum(1 for i in range(n) if max(rgb[3 * i], rgb[3 * i + 1], rgb[3 * i + 2]) < 45) / n
    return koyu >= esik and sum(rgb) / len(rgb) < 55


def _geri_yuru(kareler, j):
    """j'deki ilk tam logo karesinden geriye, logonun belirdiği geçiş karelerini (soğuk beyaz ya da kararma)
    de kapsar."""
    koyu = _koyu_mu(kareler[j][1]) if j < len(kareler) else False
    while j > 0 and kareler[j][0] - kareler[j - 1][0] < 0.5 and (
            _koyu_mu(kareler[j - 1][1], 0.6) if koyu else _soguk_beyaz_mi(kareler[j - 1][1])):
        j -= 1
    return j


def _logo_ekrani_mi(rgb):
    """NotebookLM / Gemini Notebook logo ekranı: soğuk (mavimsi) bembeyaz zemin. İçerik kâğıt dokusu sıcak krem
    olduğu için (mavi < kırmızı) karışmaz — açık renkli içerik sahneleri yanlışlıkla kesilmez."""
    n = len(rgb) // 3
    if not n:
        return False
    R, G, B = sum(rgb[0::3]) / n, sum(rgb[1::3]) / n, sum(rgb[2::3]) / n
    beyaz = sum(1 for i in range(n) if min(rgb[3 * i], rgb[3 * i + 1], rgb[3 * i + 2]) > 225) / n
    if beyaz >= 0.93 and (B - R) >= -1 and (R + G + B) / 3 >= 235:
        return True
    return _koyu_mu(rgb)            # yeni tarz: siyah zeminde "Gemini Notebook" logosu


def nblm_kesim_bul(video, sure, log=print):
    """NotebookLM'in baştaki/sondaki logo ekranlarını bulur: (başlangıç, bitiş). Sadece en baştaki ve en sondaki
    kesintisiz logo karelerini keser; içeriğin ortasına ya da açık renkli sahnelere dokunmaz."""
    bas, bit = 0.0, sure
    on = _renkli_kareler(video, 0, min(6.0, sure / 3))
    i = 0
    while i < len(on) and _logo_ekrani_mi(on[i][1]):
        i += 1
    if i:
        bas = (on[i][0] + 0.35) if i < len(on) else 0.0      # baştaki logodan içeriğe geçiş kareleri de gitsin
    uz = min(10.0, sure / 3)
    arka = _renkli_kareler(video, sure - uz, uz)
    j = len(arka)
    while j > 0 and _logo_ekrani_mi(arka[j - 1][1]):
        j -= 1
    if j < len(arka) and j > 0:
        # logo ekranı içeriğin üstüne beliriyor: o geçiş kareleri tam beyaz değil ama logoyu gösterir; onları da al
        j = _geri_yuru(arka, j)
        bit = max(0.0, arka[j][0] - LOGO_GECIS_PAYI)
    if bit - bas < sure * 0.5:          # şüpheli: kesme
        return 0.0, sure
    if bas > 0.05 or bit < sure - 0.05:
        log(f"[+] NotebookLM logo ekranları kesiliyor: baştan {bas:.1f} sn, sondan {sure - bit:.1f} sn.")
    return bas, bit


def whisper_kelimeleri(ses_dosyasi, log=print):
    """Metin vermeden Whisper'ın duyduğu kelimeler ve zamanları ([s, e, kelime, kelime])."""
    log("[+] Alt yazı için konuşma yazıya dökülüyor (Whisper)...")

    def coz(model):
        segs, _ = model.transcribe(ses_dosyasi, language=DIL, word_timestamps=True, beam_size=5,
                                   vad_filter=True)
        sonuc = []
        for s in segs:
            iptal_kontrol()
            sonuc += [(w.start, w.end, w.word.strip()) for w in (s.words or []) if w.word.strip()]
        return sonuc
    try:
        ws = coz(iptal_edilebilir(_whisper_al, log))
    except IptalHatasi:
        raise
    except Exception:
        ws = coz(iptal_edilebilir(_whisper_al, log, cpu=True))
    if not ws:
        return []
    z = _zaman_duzelt([(a, b) for a, b, _ in ws], [w for _, _, w in ws])
    return [[a, b, w, w] for (a, b), (_, _, w) in zip(z, ws)]


def nblm_altyazi_yaz(kelimeler, W, H, dosya, kanca="", kanca_sure=2.6):
    """BirAdım tarzı: krem kâğıt etiket üstünde el yazısı alt yazı + ilk saniyelerde büyük kanca yazısı."""
    taban = min(W, H)                       # yatay videoda da yazılar aynı oranda kalsın
    fs = int(taban * 0.062)
    satirlar = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 0",
        "ScaledBorderAndShadow: yes", "", "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
        "MarginR, MarginV, Encoding",
        f"Style: Etiket,Patrick Hand,{fs},&H00242A34,&H000000FF,&H00E1EEF8,&H50000000,0,0,0,0,100,100,0,0,3,"
        f"{max(8, fs // 4)},3,2,80,80,{int(H * 0.20)},1",
        f"Style: Kanca,Bebas Neue,{int(taban * 0.115)},&H00E1EEF8,&H000000FF,&H00242A34,&H64000000,0,0,0,0,100,100,2,0,3,"
        f"{int(taban * 0.03)},0,8,70,70,{int(H * 0.13)},1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    if kanca:
        k = re.sub(r"[{}\\]", "", buyuk(kanca)).strip()
        satirlar.append(f"Dialogue: 2,{_ass_zaman(0)},{_ass_zaman(kanca_sure)},Kanca,,0,0,0,,"
                        r"{\fad(0,250)\fscx112\fscy112\t(0,220,\fscx100\fscy100)}" + k)
    gruplar, g = [], []
    for i, w in enumerate(kelimeler):
        g.append(w)
        karakter = sum(len(x[2]) for x in g) + len(g) - 1
        sonraki = kelimeler[i + 1] if i + 1 < len(kelimeler) else None
        if (len(g) >= 4 or karakter >= 20 or w[2][-1:] in ".!?…,;:" or sonraki is None
                or sonraki[0] - w[1] > 0.5 or (sonraki and karakter + len(sonraki[2]) > 24)):
            gruplar.append(g)
            g = []
    for gi, grup in enumerate(gruplar):
        bas = grup[0][0]
        bit = grup[-1][1] + 0.25
        if gi + 1 < len(gruplar):
            bit = min(bit, gruplar[gi + 1][0][0])
        if kanca:
            if bit <= kanca_sure:
                continue
            bas = max(bas, kanca_sure)
        metin = re.sub(r"[{}\\]", "", " ".join(x[2] for x in grup)).strip().rstrip(".,;:")
        if metin:
            satirlar.append(f"Dialogue: 0,{_ass_zaman(bas)},{_ass_zaman(max(bit, bas + 0.2))},Etiket,,0,0,0,,{metin}")
    with open(dosya, "w", encoding="utf-8") as f:
        f.write("\n".join(satirlar) + "\n")


def _nblm_font_hazirla():
    _font_hazirla()
    hedef = os.path.join(GECICI, "fonts")
    for ad in ("PatrickHand-Regular.ttf", "BebasNeue-Regular.ttf"):
        k = yol("fontlar", ad)
        if os.path.exists(k) and not os.path.exists(os.path.join(hedef, ad)):
            shutil.copy(k, hedef)


def nblm_rozet():
    for p_ in (_nblm_dosya("rozet.png"), yol("biradim", "rozet_biradim.png")):
        if os.path.exists(p_):
            return p_
    return None


def nblm_isle(girdi, paket, ayar, log=print, asama=_bos, hedef=None):
    """İndirilen NotebookLM videosunu kanala hazır hale getirir; geçmişe 'uretildi' kaydı olarak ekler."""
    if not os.path.exists(girdi):
        raise RuntimeError(f"Video bulunamadı: {girdi}")
    boy = _video_boyut(girdi) or (1080, 1920)
    yatay = boy[0] > boy[1]
    W, H = (1920, 1080) if yatay else (1080, 1920)     # yatay video yatay kalır
    sure = medya_suresi(girdi)
    log(f"[+] NotebookLM videosu: {os.path.basename(girdi)} ({sure:.0f} sn)")
    asama("NotebookLM ekranları aranıyor", 5)
    bas, bit = nblm_kesim_bul(girdi, sure, log)
    ana = bit - bas
    ses = os.path.join(GECICI, "nblm_ses.wav")
    subprocess.run([FFMPEG, "-y", "-v", "error", "-ss", f"{bas:.3f}", "-t", f"{ana:.3f}", "-i", girdi, "-vn",
                    "-ac", "1", "-ar", "16000", ses], capture_output=True, creationflags=NO_WINDOW)
    kelimeler = []
    konusuz = not paket.get("id") or paket.get("baslik_yenile") or not paket.get("baslik")
    if ayar.get("nblm_altyazi", True) or konusuz:
        asama("Konuşma yazıya dökülüyor", 15)
        try:
            kelimeler = whisper_kelimeleri(ses, log)
        except IptalHatasi:
            raise
        except Exception as e:
            log(f"[!] Konuşma okunamadı ({str(e)[:120]})")
    if konusuz and not paket.get("baslik_yenile") and kelimeler:
        # dosya adı tutmadıysa konuşmayı kuyruktaki konuların kaynak metniyle karşılaştır
        metin_ = " ".join(w[2] for w in kelimeler)
        puanlar = sorted(((benzerlik(metin_, x.get("kaynak", "")), x) for x in nblm_kuyruk_oku()
                          if x.get("durum") == "video_bekliyor"), key=lambda t: t[0], reverse=True)
        if puanlar and puanlar[0][0] >= 0.3 and (len(puanlar) == 1 or puanlar[0][0] - puanlar[1][0] >= 0.08):
            paket = puanlar[0][1]
            konusuz = False
            log(f"[+] Video içeriği kuyruktaki konuyla eşleşti: {paket.get('baslik', '')}")
    if konusuz:     # kuyruktaki bir konuyla eşleşmedi: başlık/açıklama videonun kendi konuşmasından yazılır
        metin_ = " ".join(w[2] for w in kelimeler)
        b_, a_m, e_ = hazir_meta_uret(metin_, os.path.basename(girdi), log)
        paket = dict(paket, konu=paket.get("konu") if paket.get("id") else b_, baslik=b_, aciklama=a_m
                     + "\n\nBu video yapay zeka araçları (NotebookLM) yardımıyla hazırlanmıştır.", etiketler=e_,
                     kanca="")
        log(f"[+] Başlık videonun içeriğinden yazıldı: {b_}")
    altyazi_kelimeler = kelimeler if ayar.get("nblm_altyazi", True) else []
    hiz = min(2.0, max(1.0, float(ayar.get("nblm_hiz", 1.5) or 1.0)))
    if hiz != 1.0:
        log(f"[+] Video {hiz:g}x hızlandırılıyor.")
        altyazi_kelimeler = [[w[0] / hiz, w[1] / hiz, *w[2:]] for w in altyazi_kelimeler]
    ana_c = ana / hiz                       # çıktıda içeriğin süresi
    kanca = paket.get("kanca", "") if ayar.get("nblm_kanca", True) else ""
    nblm_altyazi_yaz(altyazi_kelimeler, W, H, os.path.join(GECICI, "nblm.ass"), kanca)
    _nblm_font_hazirla()
    asama("Video hazırlanıyor", 30)
    girisler = ["-ss", f"{bas:.3f}", "-t", f"{ana + 0.1:.3f}", "-i", girdi]
    filtre = [f"[0:v]scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=0xF9EDE0,"
              f"setsar=1,setpts=(PTS-STARTPTS)/{hiz:.4f},fps=30,format=yuv420p[v0]"]
    son = "v0"
    rozet = nblm_rozet() if ayar.get("nblm_rozet", True) else None
    if rozet:
        son = _rozet_filtre(girisler, filtre, son, W, H, ayar, rozet)
    filtre.append(f"[{son}]subtitles=nblm.ass:fontsdir=fonts[v2]")
    a_ = dict(ayar)
    v_etiket, toplam = _kapanis_ekle(girisler, filtre, "v2", ana_c, W, H, a_, log)
    tempo = f"atempo={hiz:.4f}," if hiz != 1.0 else ""
    # ses kapanış kartında da sürsün: orijinal ses kesim noktasında durmaz, kartın sonunda yavaşça kısılır
    ai = girisler.count("-i")
    girisler += ["-ss", f"{bas:.3f}", "-i", girdi]
    filtre.append(f"[{ai}:a]asetpts=PTS-STARTPTS,{tempo}apad,atrim=duration={toplam:.3f},"
                  f"afade=t=out:st={max(0.0, toplam - 1.2):.2f}:d=1.2[na]")
    ses_e = _kapanis_sesi_ekle(girisler, filtre, "na", toplam, a_, girdi)
    isim = re.sub(r"[^\wçğıöşüÇĞİÖŞÜ]+", "_", paket.get("konu", "video"))[:40].strip("_") or "video"
    cikti = hedef or os.path.join(CIKTI, f"{datetime.datetime.now():%Y%m%d_%H%M%S}_{isim}.mp4")
    gecici_cikti = cikti[:-4] + "_yeni.mp4" if hedef else cikti
    log("[+] Render başlıyor...")
    _render(girisler, filtre, [f"[{v_etiket}]", f"[{ses_e}]"], toplam, gecici_cikti, log,
            lambda o: asama(None, 30 + o * 60))
    if hedef:
        os.replace(gecici_cikti, cikti)
    hikaye = " ".join(w[2] for w in kelimeler) or paket.get("kaynak", "")
    kayit = {"tarih": datetime.datetime.now().isoformat(timespec="seconds"), "konu": paket.get("konu", ""),
             "dosya": cikti, "sure": round(toplam, 1), "yon": "yatay" if yatay else "dikey", "uzunluk": "kisa",
             "hikaye": hikaye, "baslik": baslik_sinirla(paket.get("baslik", "")),
             "aciklama": paket.get("aciklama", ""), "etiketler": paket.get("etiketler", []),
             "video_id": None, "durum": "uretildi", "format": "notebooklm", "paket_id": paket.get("id"),
             "kaynak_video": girdi, "plan_uretim": True, "hiz": hiz,
             "onay_bekliyor": bool(ayar.get("hazir_onay", True))}
    try:
        kapak_olustur(kayit, log)
    except Exception:
        pass
    gecmis_kaydet(kayit)
    if paket.get("id"):
        nblm_paket_guncelle(paket["id"], durum="islendi", dosya=cikti, kaynak_video=girdi)
    asama("Video hazır", 92)
    log(f"[✓] VİDEO HAZIR: {os.path.basename(cikti)} ({toplam:.0f} sn)")
    return kayit


def nblm_yeniden_isle(kayit, hiz, log=print, asama=_bos):
    """Henüz yüklenmemiş NotebookLM videosunu başka hızla yeniden üretir (aynı dosyanın üstüne).
    Başlık/açıklama/etiketlerde yapılan düzenlemeler korunur."""
    kaynak = kayit.get("kaynak_video", "")
    if not os.path.exists(kaynak):
        raise RuntimeError("NotebookLM'in orijinal videosu bulunamadı; hız değiştirilemiyor:\n" + kaynak)
    paket = next((x for x in nblm_kuyruk_oku() if x.get("id") == kayit.get("paket_id")), None) or {}
    paket = dict(paket, konu=kayit.get("konu", ""), baslik=kayit.get("baslik", ""),
                 aciklama=kayit.get("aciklama", ""), etiketler=kayit.get("etiketler", []), id=kayit.get("paket_id"))
    if kayit.get("_baslik_yenile"):
        paket["baslik_yenile"] = True
    a = dict(ayar_oku(), nblm_hiz=str(hiz))
    yeni = nblm_isle(kaynak, paket, a, log, asama, hedef=kayit["dosya"])
    for k_ in ("plan_slot",):
        if kayit.get(k_):
            yeni[k_] = kayit[k_]
    kayit.clear()
    kayit.update(yeni)
    gecmis_kaydet(kayit)
    return kayit


def nblm_hiz_degistir(kayit, hiz, log=print, asama=_bos):
    """Videonun hızını değiştirir.
    - Henüz yüklenmediyse: yeniden hazırlar (plan sonra yükler).
    - YouTube'da planlı (henüz yayınlanmadı) ise: yeni hızla hazırlar, aynı saate yeni video olarak planlar,
      eskisini gizliye alır (silmez; Studio'dan silebilirsin).
    - Yayınlandıysa: YouTube yayındaki videonun dosyasını değiştirmeye izin vermediği için yapılamaz."""
    eski_id = kayit.get("video_id")
    zaman = None
    if eski_id:
        try:
            zaman = datetime.datetime.strptime(kayit.get("yayin_zamani") or "", "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=datetime.timezone.utc)
        except ValueError:
            zaman = None
        if zaman is None or zaman <= datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=5):
            raise RuntimeError("Bu video YouTube'da yayınlandı. YouTube yayındaki bir videonun dosyasını değiştirmeye "
                               "izin vermiyor; hız sadece yüklenmemiş ya da henüz yayın saati gelmemiş videolarda "
                               "değiştirilebilir.")
    eski = dict(kayit)
    asama(f"Video {hiz:g}x hızla yeniden hazırlanıyor", 2)
    nblm_yeniden_isle(kayit, hiz, log, lambda a, y: asama(a, None if y is None else y * (0.6 if eski_id else 1)))
    if not eski_id:
        asama(f"Hazır: {hiz:g}x", 100)
        log(f"[✓] Video {hiz:g}x hızla yeniden hazırlandı; yayın planı onu sırası gelince yükleyecek.")
        return kayit
    yerel = zaman.astimezone()
    kayit["plan_slot"] = eski.get("plan_slot")
    asama("Yeni hızdaki video YouTube'a yükleniyor", 62)
    youtube_yukle(kayit, "public", yerel if yerel > datetime.datetime.now().astimezone() + datetime.timedelta(minutes=10)
                  else None, log, lambda o: asama(None, 62 + o * 33))
    kayit["eski_video_id"] = eski_id
    gecmis_kaydet(kayit)
    try:
        yt = yt_servis(True, log)
        r = yt.videos().list(part="status", id=eski_id).execute()
        if r.get("items"):
            st = r["items"][0]["status"]
            for alan in ("uploadStatus", "failureReason", "rejectionReason", "madeForKids", "publishAt"):
                st.pop(alan, None)
            st["privacyStatus"] = "private"
            yt.videos().update(part="status", body={"id": eski_id, "status": st}).execute()
            log(f"[✓] Eski ({float(eski.get('hiz') or 1.0):g}x) video gizliye alındı; Studio'dan silebilirsin: "
                f"https://studio.youtube.com/video/{eski_id}/edit")
    except Exception as e:
        log(f"[!] Eski video gizliye alınamadı, Studio'dan elle kaldır ({str(e)[:150]}): "
            f"https://studio.youtube.com/video/{eski_id}/edit")
    asama(f"Yeni hızla planlandı: {yerel:%d.%m %H:%M}", 100)
    return kayit


def nblm_onizleme(kaynak, hiz, log=print, saniye=12):
    """Seçilen hızın nasıl duyulduğunu görmek için videonun başından kısa, küçük bir önizleme üretir."""
    if not os.path.exists(kaynak):
        raise RuntimeError("Orijinal NotebookLM videosu bulunamadı.")
    sure = medya_suresi(kaynak)
    bas, bit = nblm_kesim_bul(kaynak, sure, lambda *_: None)
    hiz = float(hiz)
    uz = min(saniye * hiz, bit - bas)
    cikti = os.path.join(GECICI, f"onizleme_{str(hiz).replace('.', '_')}x.mp4")
    tempo = f",atempo={hiz:.4f}" if hiz != 1.0 else ""
    r = subprocess.run([FFMPEG, "-y", "-v", "error", "-ss", f"{bas:.2f}", "-t", f"{uz:.2f}", "-i", kaynak,
                        "-vf", f"scale=540:-2,setpts=PTS/{hiz:.4f}", "-af", f"asetpts=PTS-STARTPTS{tempo}",
                        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28", "-c:a", "aac", cikti],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
    if r.returncode != 0 or not os.path.exists(cikti):
        raise RuntimeError("Önizleme oluşturulamadı: " + r.stderr.strip()[-200:])
    return cikti


def hazir_klasoru():
    return os.path.join(profil_klasoru(AKTIF_PROFIL), "hazir_videolar")


def hazir_meta_uret(metin, dosya_adi, log=print):
    """Hazır videonun konuşmasından (yoksa dosya adından) başlık, açıklama ve etiket yazar."""
    if nblm_mi():
        kanal = f'"BirAdım" (kişisel gelişim, öğrenme, psikoloji; slogan "Öğren, düşün, ilerle.")\n{BIRADIM_DERSLER}'
    elif DIL == "en":
        kanal = '"Bir Adım Hikâyeler English" (short mystery/horror stories in English)'
    else:
        kanal = '"Bir Adım Hikâyeler" (kısa gizem/korku hikâyeleri)'
    dil = "İngilizce" if DIL == "en" else "Türkçe"
    prompt = f"""YouTube Shorts kanalı: {kanal}
Aşağıdaki hazır videonun YouTube bilgilerini {dil} yaz.
Dosya adı: {dosya_adi}
Videoda söylenenler: {" ".join(metin.split()[:400]) or "(konuşma yok, dosya adından çıkar)"}

- baslik: en fazla 60 karakter, merak uyandıran, sonu ya da cevabı ele vermeyen; sonda 1 uygun emoji olabilir;
  hashtag YOK.
- aciklama: 2-3 cümle + sonda 3-5 hashtag (#shorts dahil{', #biradım dahil' if nblm_mi() else ''}).
- etiketler: 8-12 etiket.
Yanıtı YALNIZCA şu JSON biçiminde ver: {{"baslik": "...", "aciklama": "...", "etiketler": ["..."]}}"""
    try:
        v = _json_coz(_gemini_uret(prompt, log, json_mod=True))
    except IptalHatasi:
        raise
    except Exception as e:
        log(f"[!] Başlık yazılamadı, dosya adı kullanılıyor ({str(e)[:100]})")
        v = {}
    ad = re.sub(r"[_\-]+", " ", os.path.splitext(dosya_adi)[0]).strip()
    baslik = baslik_sinirla(re.sub(r"\s*#\w+", "", str(v.get("baslik") or ad)).strip() or ad, 90)
    aciklama = str(v.get("aciklama") or "").strip() or ("#shorts #biradım" if nblm_mi() else "#shorts")
    etiketler = [str(e).strip().lstrip("#") for e in (v.get("etiketler") or []) if str(e).strip()][:15]
    return baslik, aciklama[:4900], etiketler


def hazir_videolari_al(log=print, asama=_bos, dosyalar=None):
    """'hazir_videolar' klasöründeki (ya da verilen) bitmiş videoları olduğu gibi kuyruğa alır: video işlenmez,
    sadece başlık/açıklama/etiket yazılır. Yayın planı bunları boş saatlere yükler. Yeni kayıtları döndürür."""
    klasor = hazir_klasoru()
    os.makedirs(klasor, exist_ok=True)
    if dosyalar:
        kopya = []
        for f_ in dosyalar:
            hedef = os.path.join(klasor, os.path.basename(f_))
            if os.path.abspath(f_) != os.path.abspath(hedef):
                if os.path.exists(hedef):
                    kok, uz = os.path.splitext(hedef)
                    hedef = f"{kok}_{datetime.datetime.now():%H%M%S}{uz}"
                shutil.copy2(f_, hedef)
            kopya.append(hedef)
        adaylar = kopya
    else:
        adaylar = sorted(_dosyalar(klasor, VIDEO_UZ), key=os.path.getmtime)
    bilinen = {os.path.abspath(g.get(alan) or "") for g in gecmis_oku() for alan in ("dosya", "kaynak_video")}
    yeni = []
    for i, v in enumerate(adaylar):
        if os.path.abspath(v) in bilinen:
            continue
        iptal_kontrol()
        asama(f"Hazır video {i + 1}/{len(adaylar)}: {os.path.basename(v)}", 5 + 85 * i / max(1, len(adaylar)))
        sure = medya_suresi(v)
        if nblm_mi() and _eski_kapanis_imzasi() and not eski_kart_var_mi(v, sure):
            log(f"[+] {os.path.basename(v)} kendi düzenlediğin video değil (NotebookLM'in ham videosu); "
                "hızlandırılıp NotebookLM videosu olarak hazırlanıyor.")
            yeni.append(nblm_isle(v, {}, ayar_oku(), log, asama))
            continue
        boy = _video_boyut(v) or (1080, 1920)
        dikey = boy[1] >= boy[0]
        if dikey and sure > 180:
            log(f"[!] {os.path.basename(v)} {sure:.0f} sn: Shorts en fazla 3 dakika olabilir; uzun video olarak "
                "yüklenecek.")
        metin = ""
        ses = os.path.join(GECICI, "hazir_ses.wav")
        try:
            subprocess.run([FFMPEG, "-y", "-v", "error", "-i", v, "-vn", "-ac", "1", "-ar", "16000", "-t", "240",
                            ses], capture_output=True, creationflags=NO_WINDOW)
            if os.path.exists(ses):
                metin = " ".join(w[2] for w in whisper_kelimeleri(ses, log))
        except IptalHatasi:
            raise
        except Exception as e:
            log(f"[~] Konuşma okunamadı, başlık dosya adından yazılacak ({str(e)[:100]})")
        baslik, aciklama, etiketler = hazir_meta_uret(metin, os.path.basename(v), log)
        kayit = {"tarih": datetime.datetime.now().isoformat(timespec="seconds"),
                 "konu": baslik, "dosya": v, "sure": round(sure, 1),
                 "yon": "dikey" if dikey else "yatay", "uzunluk": "kisa" if sure <= 180 else "uzun",
                 "hikaye": metin, "baslik": baslik, "aciklama": aciklama, "etiketler": etiketler,
                 "video_id": None, "durum": "uretildi", "format": "hazir", "plan_uretim": True}
        try:
            kapak_olustur(kayit, log)
        except Exception:
            pass
        gecmis_kaydet(kayit)
        yeni.append(kayit)
        log(f"[+] Hazır video sıraya alındı: {baslik}")
    a_ = ayar_oku()
    if a_.get("hazir_marka"):
        for k in [g for g in gecmis_oku() if g.get("format") == "hazir" and not g.get("video_id")
                  and int(g.get("marka_surum") or 0) < MARKA_SURUM
                  and os.path.exists(g.get("kaynak_video") or g.get("dosya", ""))]:
            iptal_kontrol()
            try:
                hazir_marka_ekle(k, a_, log, asama)
            except IptalHatasi:
                raise
            except Exception as e:
                log(f"[X] {os.path.basename(k.get('dosya', ''))}: rozet/kapanış eklenemedi ({str(e)[:200]})")
    if yeni:
        log(f"[✓] {len(yeni)} hazır video yayın sırasına eklendi; plan boş saatlere yükleyecek.")
    return yeni


MARKA_SURUM = 3        # rozet/kesim kuralı değişince eski işlenmiş (yüklenmemiş) hazır videolar yeniden işlenir


def hazir_marka_ekle(kayit, ayar, log=print, asama=_bos):
    """Hazır videoya sağ alta kanal rozetini ve sona kapanış kartını ekler (orijinal dosyaya dokunmaz).
    İşlenen video yüklenmeden önce onayını bekler (Son videolar → Oynat → Onayla)."""
    kaynak = kayit.get("kaynak_video") or kayit["dosya"]
    if not os.path.exists(kaynak):
        raise RuntimeError(f"Video bulunamadı: {kaynak}")
    W, H = (1080, 1920) if kayit.get("yon", "dikey") == "dikey" else (1920, 1080)
    sure = medya_suresi(kaynak)
    log(f"[+] Rozet ve kapanış ekleniyor: {os.path.basename(kaynak)}")
    kes = hazir_son_kesim(kaynak, sure, log)
    if kes:
        sure = kes
    girisler = ["-t", f"{sure + 0.05:.3f}", "-i", kaynak]
    filtre = [f"[0:v]scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:"
              f"color=0x000000,setsar=1,fps=30,format=yuv420p[v0]"]
    son = "v0"
    rozet = nblm_rozet() if ayar.get("nblm_rozet", True) else None
    if rozet:
        son = _rozet_filtre(girisler, filtre, son, W, H, ayar, rozet)
    v_etiket, toplam = _kapanis_ekle(girisler, filtre, son, sure, W, H, ayar, log)
    ses_var = True
    try:
        with av.open(kaynak) as c_:
            ses_var = len(c_.streams.audio) > 0
    except Exception:
        pass
    if ses_var:      # ses kapanış kartında da sürer (kesim noktasında durmaz), sonda yavaşça kısılır
        ai = girisler.count("-i")
        girisler += ["-i", kaynak]
        filtre.append(f"[{ai}:a]asetpts=PTS-STARTPTS,apad,atrim=duration={toplam:.3f},"
                      f"afade=t=out:st={max(0.0, toplam - 1.2):.2f}:d=1.2[na]")
    else:
        filtre.append(f"anullsrc=r=44100:cl=stereo,atrim=duration={toplam:.3f}[na]")
    ses_e = _kapanis_sesi_ekle(girisler, filtre, "na", toplam, ayar, kaynak if ses_var else None)
    os.makedirs(CIKTI, exist_ok=True)
    cikti = os.path.join(CIKTI, "hazir_" + os.path.splitext(os.path.basename(kaynak))[0][:50] + ".mp4")
    _render(girisler, filtre, [f"[{v_etiket}]", f"[{ses_e}]"], toplam, cikti, log, lambda o: asama(None, 20 + o * 70))
    eski_dosya = kayit["dosya"]
    kayit.update(kaynak_video=kaynak, dosya=cikti, sure=round(toplam, 1), marka_eklendi=True, marka_surum=MARKA_SURUM,
                 onay_bekliyor=bool(ayar.get("hazir_onay", True)))
    try:
        kapak_olustur(kayit, log)
    except Exception:
        pass
    g = [k for k in gecmis_oku() if k.get("dosya") != eski_dosya]      # eski kaydın yerine yenisi
    g.append(kayit)
    with _gecmis_kilit:
        _json_yaz(GECMIS_DOSYA, g[-500:])
    log(f"[✓] Hazır: {os.path.basename(cikti)} ({toplam:.0f} sn)"
        + (" · yüklemeden önce onayını bekliyor" if kayit["onay_bekliyor"] else ""))
    return kayit


def kayit_icerik_dogrula(kayit, log=print, asama=_bos):
    """Videonun konuşmasını dinler; başlık başka bir konuya aitse doğru konunun başlığını koyar, hiçbir konuya
    uymuyorsa başlığı konuşmadan yazar. Video yeniden işlenmez, sadece başlık/açıklama/etiket düzelir."""
    kaynak = kayit.get("kaynak_video") or ""
    if not os.path.exists(kaynak):
        log(f"[~] İçerik kontrolü yapılamadı, kaynak video yok: {kaynak}")
        return False
    asama(f"İçerik kontrol ediliyor: {kayit.get('baslik', '')}", 10)
    ses = os.path.join(GECICI, "dogrula_ses.wav")
    subprocess.run([FFMPEG, "-y", "-v", "error", "-i", kaynak, "-vn", "-ac", "1", "-ar", "16000", "-t", "150", ses],
                   capture_output=True, creationflags=NO_WINDOW)
    metin = " ".join(w[2] for w in whisper_kelimeleri(ses, log))
    if len(metin.split()) < 15:
        log("[~] İçerik kontrolü: konuşma okunamadı, başlık değiştirilmedi.")
        return False
    kuyruk = nblm_kuyruk_oku()
    adaylar = [x for x in kuyruk if x.get("kaynak") and (x.get("durum") == "video_bekliyor"
                                                          or x.get("id") == kayit.get("paket_id"))]
    puanlar = sorted(((benzerlik(metin, x["kaynak"]), x) for x in adaylar), key=lambda t: t[0], reverse=True)
    simdiki = next((x for x in adaylar if x.get("id") == kayit.get("paket_id")), None)
    sp = benzerlik(metin, simdiki["kaynak"]) if simdiki else 0
    if simdiki and sp >= 0.25 and (puanlar[0][1] is simdiki or sp >= puanlar[0][0] - 0.05):
        log(f"[✓] Başlık videoyla uyuşuyor: {kayit.get('baslik', '')}")
        return True
    eski_baslik = kayit.get("baslik", "")
    if simdiki:
        nblm_paket_guncelle(simdiki["id"], durum="video_bekliyor", dosya=None, kaynak_video=None)
    if puanlar and puanlar[0][0] >= 0.3 and puanlar[0][1] is not simdiki:
        pk = puanlar[0][1]
        kayit.update(konu=pk.get("konu", ""), baslik=pk.get("baslik", ""), aciklama=pk.get("aciklama", ""),
                     etiketler=pk.get("etiketler", []), paket_id=pk.get("id"))
        nblm_paket_guncelle(pk["id"], durum="islendi", dosya=kayit.get("dosya"), kaynak_video=kaynak)
    else:
        b_, a_m, e_ = hazir_meta_uret(metin, os.path.basename(kaynak), log)
        kayit.update(konu=b_, baslik=b_, aciklama=a_m + "\n\nBu video yapay zeka araçları (NotebookLM) yardımıyla "
                     "hazırlanmıştır.", etiketler=e_)
        kayit.pop("paket_id", None)
    kayit["hikaye"] = metin
    gecmis_kaydet(kayit)
    log(f"[✓] Başlık videonun içeriğine göre düzeltildi: '{eski_baslik}' → '{kayit['baslik']}'")
    return True


def hazir_onayla(kayit):
    kayit["onay_bekliyor"] = False
    gecmis_kaydet(kayit)


def nblm_gelenleri_isle(ayar, log=print, asama=_bos):
    """'gelen' klasörüne atılmış, henüz işlenmemiş NotebookLM videolarını işler. İşlenen kayıtları döndürür."""
    klasor = _nblm_dosya("gelen")
    os.makedirs(klasor, exist_ok=True)
    islenmis = {g.get("kaynak_video") for g in gecmis_oku()}
    yeni = [p_ for p_ in _dosyalar(klasor, VIDEO_UZ) if p_ not in islenmis]
    sonuc = []
    for v in sorted(yeni, key=os.path.getmtime):
        paket = nblm_eslesen_paket(v) or {"konu": os.path.splitext(os.path.basename(v))[0],
                                          "baslik": os.path.splitext(os.path.basename(v))[0][:60]}
        if not paket.get("id"):
            log(f"[!] {os.path.basename(v)} için bekleyen konu yok; başlık dosya adından alınacak, yüklemeden önce "
                "kontrol et.")
        try:
            sonuc.append(nblm_isle(v, paket, ayar, log, asama))
        except IptalHatasi:
            raise
        except Exception as e:
            log(f"[X] {os.path.basename(v)} işlenemedi: {str(e)[:300]}")
    return sonuc


# ---------------------------------------------------------------------------
# 10. OTOMATİK SERİ
# ---------------------------------------------------------------------------
def seri_calistir(adet, ayar, yukle, gizlilik, aralik_saat, log=print, asama=_bos,
                  durdur=lambda: False, video_bitti=_bos):
    t0 = datetime.datetime.now().astimezone()
    basarili = 0
    for k in range(adet):
        if durdur():
            log("[■] Seri durduruldu.")
            break
        log(f"\n===== VİDEO {k + 1}/{adet} =====")
        try:
            asama(f"[{k + 1}/{adet}] Fikir aranıyor", 2)
            konu = fikir_uret(ayar["tur"], log)
            log(f"[+] Konu: {konu}")
            kayit = video_uret(konu, ayar, log,
                               lambda a, y: asama(f"[{k + 1}/{adet}] {a}" if a else None, y))
            if yukle:
                zaman = None
                if aralik_saat and k > 0:
                    zaman = t0 + datetime.timedelta(hours=aralik_saat * k)
                    if zaman < datetime.datetime.now().astimezone() + datetime.timedelta(minutes=20):
                        zaman = None
                asama(f"[{k + 1}/{adet}] YouTube'a yükleniyor", 92)
                youtube_yukle(kayit, gizlilik, zaman, log,
                              lambda o: asama(None, 92 + o * 8))
            basarili += 1
            video_bitti(kayit)
        except Exception as e:
            if isinstance(e, IptalHatasi):
                raise
            log(f"[X] Video {k + 1} başarısız: {e}")
            if isinstance(e, YuklemeSiniriHatasi):
                log("[■] YouTube yükleme sınırı doldu; seri durduruldu (boşuna video üretilmesin).")
                break
    asama(f"Seri bitti: {basarili}/{adet} video", 100)
    log(f"\n[✓] SERİ TAMAMLANDI: {basarili}/{adet} başarılı.")
    return basarili


# ---------------------------------------------------------------------------
# 10b. GÜNLÜK YAYIN PLANI (videolar önceden yüklenir, belirlenen saatte YouTube yayınlar)
# ---------------------------------------------------------------------------
PLAN_GOREV_ADI = "ShortsStudyo Gunluk Plan"


def _gorev_adi(taban):
    return taban if AKTIF_PROFIL == "tr" else f"{taban} {AKTIF_PROFIL.upper()}"


def _profil_arg():
    return "" if AKTIF_PROFIL == "tr" else f" --profil {AKTIF_PROFIL}"


def saat_coz(x):
    m = re.match(r"^\s*(\d{1,2})\s*[:.]\s*(\d{2})\s*$", str(x))
    if not m:
        return None
    h, d = int(m.group(1)), int(m.group(2))
    return (h, d) if 0 <= h < 24 and 0 <= d < 60 else None


def _slot_anahtar(t):
    return t.strftime("%Y-%m-%dT%H:%M")


GUN_ADLARI = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]


def plan_listesi(ayar):
    """Plan satırları: [{'saat': '12:00', 'format': 'kisa'|'uzun', 'gunler': [0..6]}].
    Eski sürümdeki düz saat listesi (plan_saatler) Shorts + her gün olarak okunur."""
    pl = ayar.get("plan")
    if not isinstance(pl, list):
        pl = [{"saat": x, "format": "kisa", "gunler": list(range(7))} for x in ayar.get("plan_saatler", [])]
    sonuc = []
    for e in pl:
        hs = saat_coz(e.get("saat", ""))
        if not hs:
            continue
        gunler = sorted({int(g) for g in e.get("gunler", range(7)) if 0 <= int(g) <= 6})
        if gunler:
            sonuc.append({"saat": f"{hs[0]:02d}:{hs[1]:02d}", "format": "uzun" if e.get("format") == "uzun" else "kisa",
                          "gunler": gunler})
    return sonuc


def plan_slotlari(ayar, simdi=None, gecmis_dahil=False):
    """Önümüzdeki 'plan_gun' gün içindeki yayınlar: [(zaman, format), ...] (yerel saat)."""
    simdi = simdi or datetime.datetime.now().astimezone()
    gun = max(1, int(ayar.get("plan_gun", 1)))
    satirlar = plan_listesi(ayar)
    sonuc = {}
    for d in range(-1 if gecmis_dahil else 0, gun + 1):
        tarih = (simdi + datetime.timedelta(days=d)).date()
        for e in satirlar:
            if tarih.weekday() not in e["gunler"]:
                continue
            h, m = saat_coz(e["saat"])
            t = datetime.datetime.combine(tarih, datetime.time(h, m)).astimezone()
            if t > simdi + datetime.timedelta(days=gun):
                continue
            if (gecmis_dahil and t > simdi - datetime.timedelta(hours=12)) or t > simdi + datetime.timedelta(minutes=25):
                sonuc.setdefault(t, e["format"])
    return sorted(sonuc.items())


def plan_kayitlari():
    """Yayın saatine bağlı, YouTube'da hâlâ duran videolar (YouTube'dan silinenler sayılmaz)."""
    return {k["plan_slot"]: k for k in gecmis_oku()
            if k.get("plan_slot") and k.get("video_id") and not (k.get("istatistik") or {}).get("silindi")}


def bekleyen_isleri_yap(log=print, asama=_bos):
    """Kanal klasöründeki isler.json'da sıraya konmuş işleri yapar (plan doldurulurken, gece görevi dahil).
    İş türü 'yeniden_hazirla': NotebookLM videosunu güncel ayarlarla yeniden üretir; YouTube'da planlıysa aynı
    saate yeniden yükler, eskisini gizliye alır."""
    dosya = os.path.join(profil_klasoru(AKTIF_PROFIL), "isler.json")
    isler = _json_oku(dosya, [])
    if not isler:
        return
    kalan = []
    for is_ in isler:
        try:
            if is_.get("is") == "nblm_olarak_isle":
                kaynak = is_.get("kaynak")
                if not os.path.exists(kaynak or ""):
                    log(f"[~] İş atlandı, kaynak video yok: {kaynak}")
                    continue
                if any(os.path.normcase(g.get("kaynak_video") or "") == os.path.normcase(kaynak)
                       and g.get("format") == "notebooklm" and not g.get("reddedildi") for g in gecmis_oku()):
                    log(f"[~] '{is_.get('baslik')}' zaten yeniden hazırlanmış, iş atlandı.")
                    continue
                pk = next((x for x in nblm_kuyruk_oku() if is_.get("paket_id") and x.get("id") == is_["paket_id"]),
                          None)
                if not pk:
                    pk = {"id": "elle", "konu": is_.get("baslik", ""), "baslik": is_.get("baslik", ""),
                          "aciklama": is_.get("aciklama", ""), "etiketler": is_.get("etiketler", []), "kanca": ""}
                log(f"[+] Sıradaki iş: '{pk['baslik']}' NotebookLM videosu olarak (hızlandırılarak) hazırlanıyor...")
                yeni = nblm_isle(kaynak, pk, ayar_oku(), log, asama)
                if pk.get("id") == "elle":
                    yeni.pop("paket_id", None)
                gecmis_kaydet(yeni)
                if is_.get("yukle"):
                    # kullanıcı bu videonun hemen yayınlanmasını istedi
                    yeni.update(onay_bekliyor=False)
                    gecmis_kaydet(yeni)
                    youtube_yukle(yeni, "public", None, log)
                continue
            if is_.get("is") == "yukle":
                ad = lambda x: re.split(r"[\\/]", x or "")[-1]      # noqa: E731
                kayit = next((k for k in gecmis_oku() if ad(k.get("dosya")) == ad(is_.get("dosya"))), None)
                if kayit and not kayit.get("video_id") and os.path.exists(kayit.get("dosya", "")):
                    kayit.update(onay_bekliyor=False, reddedildi=False)
                    gecmis_kaydet(kayit)
                    youtube_yukle(kayit, "public", None, log)
                continue
            if is_.get("is") == "icerik_dogrula":
                kayit = next((k for k in gecmis_oku() if k.get("tarih") == is_.get("tarih")), None)
                if kayit and not kayit.get("video_id") and not kayit.get("reddedildi"):
                    kayit_icerik_dogrula(kayit, log, asama)
                continue
            if is_.get("is") == "yeniden_hazirla":
                ad = lambda x: re.split(r"[\\/]", x or "")[-1]      # noqa: E731
                kayit = next((k for k in gecmis_oku() if ad(k.get("dosya")) == ad(is_.get("dosya"))), None)
                if not kayit:
                    log(f"[~] İş atlandı, video kaydı yok: {is_.get('dosya')}")
                    continue
                log(f"[+] Sıradaki iş: '{kayit.get('baslik', '')}' güncel ayarlarla yeniden hazırlanıyor...")
                if is_.get("baslik_yenile"):
                    kayit["_baslik_yenile"] = True
                nblm_hiz_degistir(kayit, float(kayit.get("hiz") or is_.get("hiz") or 1.5), log, asama)
        except IptalHatasi:
            raise
        except Exception as e:
            is_["deneme"] = int(is_.get("deneme", 0)) + 1
            log(f"[X] İş başarısız ({is_.get('deneme')}. deneme): {str(e)[:200]}")
            if is_["deneme"] < 3:
                kalan.append(is_)
    _json_yaz(dosya, kalan)


def plan_cakisma_duzelt(bos, ayar, log=print):
    """Aynı yayın saatine iki video planlandıysa (iki işlem aynı anda doldurduğunda olabiliyor) fazla olanı
    YouTube'da ilk boş saate kaydırır. Kalan boş saatleri döndürür."""
    simdi = datetime.datetime.now(datetime.timezone.utc)
    gruplar = {}
    for k in gecmis_oku():
        if not (k.get("plan_slot") and k.get("video_id") and k.get("yayin_zamani")):
            continue
        try:
            z = datetime.datetime.strptime(k["yayin_zamani"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
        except ValueError:
            continue
        if z > simdi + datetime.timedelta(minutes=15):
            gruplar.setdefault(k["plan_slot"], []).append(k)
    fazlalar = [k for liste in gruplar.values() if len(liste) > 1 for k in sorted(liste, key=lambda x: x.get("tarih", ""))[1:]]
    if not fazlalar:
        return bos
    yt = yt_servis(True, log)
    bos = list(bos)
    dolu = plan_kayitlari()
    ileri = [(t, f) for t, f in plan_slotlari(dict(ayar, plan_gun=14))
             if _slot_anahtar(t) not in dolu and (t, f) not in bos]      # plan ufkunun ötesindeki boş saatler
    for k in fazlalar:
        uygun = next(((t, f) for t, f in bos + ileri if f == k.get("uzunluk", "kisa")
                      and t > datetime.datetime.now().astimezone() + datetime.timedelta(minutes=15)), None)
        if not uygun:
            log(f"[~] '{k.get('baslik', '')}' başka bir videoyla aynı saatte; kaydıracak boş saat yok, sonraki "
                "doldurmada denenecek.")
            continue
        t, _ = uygun
        yeni = t.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        r = yt.videos().list(part="status", id=k["video_id"]).execute()
        if not r.get("items"):
            continue
        st = r["items"][0]["status"]
        for alan in ("uploadStatus", "failureReason", "rejectionReason", "madeForKids"):
            st.pop(alan, None)
        st.update(privacyStatus="private", publishAt=yeni)
        yt.videos().update(part="status", body={"id": k["video_id"], "status": st}).execute()
        eski = k["plan_slot"]
        k.update(plan_slot=_slot_anahtar(t), yayin_zamani=yeni)
        gecmis_kaydet(k)
        (bos if uygun in bos else ileri).remove(uygun)
        log(f"[✓] Aynı saate düşen video kaydırıldı: '{k.get('baslik', '')}' {eski} → {t:%d.%m %H:%M}")
    return bos


def plan_doldur(ayar, log=print, asama=_bos, durdur=lambda: False, video_bitti=_bos, en_fazla=None):
    """Boş yayın saatleri için video üretir ve o saatte yayınlanacak şekilde YouTube'a yükler."""
    kilit = os.path.join(GECICI, "plan.kilit")
    if os.path.exists(kilit) and time.time() - os.path.getmtime(kilit) < 3 * 3600:
        log("[~] Plan şu anda başka bir işlemde dolduruluyor, atlandı.")
        return 0
    with open(kilit, "w") as f:
        f.write(str(os.getpid()))
    try:
        try:
            bekleyen_isleri_yap(log, asama)
        except IptalHatasi:
            raise
        except Exception as e:
            log(f"[!] Bekleyen işler: {str(e)[:200]}")
        try:
            bekleyen_ilk_yorumlar(log)
        except Exception as e:
            log(f"[!] Bekleyen ilk yorumlar: {str(e)[:150]}")
        nblm = nblm_mi()
        if nblm:
            try:
                nblm_gelenleri_isle(ayar, log, asama)
            except IptalHatasi:
                raise
            except Exception as e:
                log(f"[!] Gelen NotebookLM videoları işlenemedi: {str(e)[:200]}")
        try:
            hazir_videolari_al(log)
        except IptalHatasi:
            raise
        except Exception as e:
            log(f"[!] Hazır videolar okunamadı: {str(e)[:200]}")
        dolu = plan_kayitlari()
        bos = [(t, f) for t, f in plan_slotlari(ayar) if _slot_anahtar(t) not in dolu]
        try:
            bos = plan_cakisma_duzelt(bos, ayar, log)
            dolu = plan_kayitlari()
        except Exception as e:
            log(f"[!] Aynı saate düşen videolar düzeltilemedi: {str(e)[:200]}")
        if not bos:
            log("[✓] Plan dolu; hazırlanacak video yok.")
            asama("Plan dolu", 100)
            return 0
        if en_fazla:
            bos = bos[:en_fazla]
        log(f"[+] {len(bos)} boş yayın saati: " + ", ".join(
            t.strftime("%d.%m %H:%M") + (" (uzun)" if f == "uzun" else "") for t, f in bos))
        yt_servis(True, log)
        # Planın daha önce üretip yükleyemediği videolar (son 3 gün): önce bunlar kullanılır
        sinir = "0" if nblm else (datetime.datetime.now() - datetime.timedelta(days=3)).isoformat()
        bekleyen = [k for k in gecmis_oku() if k.get("plan_uretim") and not k.get("video_id")
                    and os.path.exists(k.get("dosya", "")) and (k.get("tarih", "") >= sinir or k.get("format") == "hazir")
                    and not k.get("onay_bekliyor")]
        onaysiz = [k for k in gecmis_oku() if k.get("onay_bekliyor") and not k.get("video_id")]
        if onaysiz:
            log(f"[i] {len(onaysiz)} video onayını bekliyor (Son videolar → Oynat → Onayla); onaylanınca planlanır.")
        if bekleyen:
            log(f"[+] Daha önce üretilip yüklenemeyen {len(bekleyen)} video var; önce bunlar kullanılacak.")
        n = 0
        for i, (t, fmt) in enumerate(bos):
            if durdur():
                log("[■] Plan doldurma durduruldu.")
                break
            on = f"[{i + 1}/{len(bos)} · {t.strftime('%d.%m %H:%M')} · {'Uzun' if fmt == 'uzun' else 'Shorts'}]"
            a_ = dict(ayar, uzunluk=fmt, yon="dikey" if fmt == "kisa" else "yatay")
            log(f"\n===== {on} =====")
            try:
                hazir = next((k for k in bekleyen if k.get("uzunluk", "kisa") == fmt), None)
                if hazir:
                    bekleyen.remove(hazir)
                    kayit = hazir
                    log(f"[+] Hazır video kullanılıyor: {kayit.get('baslik', '')}")
                elif nblm:
                    log("[~] Bu saat için işlenmiş NotebookLM videosu kalmadı. NotebookLM'den video indirip "
                        "'gelen' klasörüne at ya da Panel'den 'Videoyu işle' ile ekle.")
                    break
                else:
                    asama(f"{on} Konu aranıyor", 2)
                    konu = fikir_uret(ayar["tur"], log)
                    log(f"[+] Konu: {konu}")
                    kayit = video_uret(konu, a_, log, lambda a, y: asama(f"{on} {a}" if a else None, y))
                    kayit["plan_uretim"] = True
                    gecmis_kaydet(kayit)
                kayit["plan_slot"] = _slot_anahtar(t)
                zaman = t if t > datetime.datetime.now().astimezone() + datetime.timedelta(minutes=10) else None
                asama(f"{on} YouTube'a yükleniyor", 92)
                youtube_yukle(kayit, "public", zaman, log, lambda o: asama(None, 92 + o * 8))
                n += 1
                video_bitti(kayit)
            except YuklemeSiniriHatasi as e:
                kayit.pop("plan_slot", None)
                gecmis_kaydet(kayit)
                log(f"[X] {e}")
                log("[■] Sınır kalkana kadar yeni video üretilmeyecek. Bu video saklandı; bir sonraki plan "
                    "doldurmada önce o yüklenecek.")
                break
            except Exception as e:
                if isinstance(e, IptalHatasi):
                    raise
                if "quotaExceeded" in str(e) or "exceeded your quota" in str(e).lower():
                    kayit_ = locals().get("kayit")
                    if kayit_ and not kayit_.get("video_id"):
                        kayit_.pop("plan_slot", None)
                        gecmis_kaydet(kayit_)
                    log("[X] YouTube'un günlük API kotası doldu (günde yaklaşık 6 yükleme). Kota Türkiye saatiyle "
                        "10:00'da yenilenir; kalan saatler sonraki doldurmada hazırlanır. Üretilen video saklandı.")
                    break
                log(f"[X] {on} başarısız: {e}")
        asama(f"Plan dolduruldu: {n}/{len(bos)} video", 100)
        log(f"\n[✓] PLAN: {n}/{len(bos)} video hazırlandı ve yayın saatine planlandı.")
        return n
    finally:
        try:
            os.remove(kilit)
        except OSError:
            pass


KURAL_DEGISIMI = "2026-10-28T03:15"   # yeni hikâye kurallarından önce üretilen videolar


def planli_videolar():
    """İleri tarihe planlanmış, henüz yayınlanmamış videolar (yayın zamanına göre sıralı)."""
    simdi = datetime.datetime.now(datetime.timezone.utc)
    sonuc = []
    for k in gecmis_oku():
        ist = k.get("istatistik") or {}
        if not k.get("video_id") or ist.get("silindi") or k.get("geri_cekildi"):
            continue
        z = ist.get("publishAt") or k.get("yayin_zamani")
        if not z:
            continue
        try:
            t = datetime.datetime.fromisoformat(z.replace("Z", "+00:00"))
        except ValueError:
            continue
        if t > simdi:
            sonuc.append((t.astimezone(), k))
    return sorted(sonuc, key=lambda x: x[0])


def plandan_cek(kayit, log=print):
    """Planlı videoyu yayından kaldırır: gizliye alır ve yayın zamanını siler (SİLMEZ, geri alınabilir).
    Yayın saati boşalır; plan doldurma oraya yeni bir video koyar."""
    yt = yt_servis(True, log)
    kanal_dogrula(yt, log)
    r = yt.videos().list(part="status", id=kayit["video_id"]).execute()
    if not r.get("items"):
        raise RuntimeError("Video YouTube'da bulunamadı (silinmiş olabilir).")
    st = r["items"][0]["status"]
    for alan in ("uploadStatus", "failureReason", "rejectionReason", "madeForKids", "publishAt"):
        st.pop(alan, None)
    st["privacyStatus"] = "private"
    yt.videos().update(part="status", body={"id": kayit["video_id"], "status": st}).execute()
    kayit["eski_plan_slot"] = kayit.pop("plan_slot", None)
    kayit["geri_cekildi"] = datetime.datetime.now().isoformat(timespec="seconds")
    kayit["yayin_zamani"] = None
    kayit["gizlilik"] = "private"
    ist = kayit.get("istatistik") or {}
    ist.update(publishAt=None, gizlilik="private")
    kayit["istatistik"] = ist
    gecmis_kaydet(kayit)
    log(f"[✓] Yayından kaldırıldı (gizli): {kayit.get('baslik', '')}")


def _ps(komut):
    return subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", komut],
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          creationflags=NO_WINDOW)


def gorev_kur(saat):
    """Windows Görev Zamanlayıcı: her gün 'saat'te planı doldurur (kaçırırsa açılınca çalışır)."""
    if os.name != "nt":
        raise RuntimeError("Otomatik görev sadece Windows'ta kurulabilir.")
    hs = saat_coz(saat)
    if not hs:
        raise RuntimeError("Saat biçimi hatalı (örn. 03:00).")
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(pyw):
        pyw = sys.executable
    q = lambda x: str(x).replace("'", "''")  # noqa: E731
    ps = (f"$a=New-ScheduledTaskAction -Execute '{q(pyw)}' -Argument '\"{q(os.path.abspath(__file__))}\"{_profil_arg()} --planla' "
          f"-WorkingDirectory '{q(BASE)}';"
          f"$t=New-ScheduledTaskTrigger -Daily -At '{hs[0]:02d}:{hs[1]:02d}';"
          "$s=New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries "
          "-ExecutionTimeLimit (New-TimeSpan -Hours 6);"
          f"Register-ScheduledTask -TaskName '{_gorev_adi(PLAN_GOREV_ADI)}' -Action $a -Trigger $t -Settings $s "
          "-Description 'Shorts Studyo gunluk yayin planini doldurur' -Force | Out-Null; Write-Output TAMAM")
    r = _ps(ps)
    if r.returncode != 0 or "TAMAM" not in r.stdout:
        raise RuntimeError(r.stderr.strip()[-300:] or "Windows görevi oluşturulamadı.")


def gorev_kaldir():
    if os.name == "nt":
        _ps(f"Unregister-ScheduledTask -TaskName '{_gorev_adi(PLAN_GOREV_ADI)}' -Confirm:$false -ErrorAction SilentlyContinue")


def gorev_durumu():
    """Kuruluysa {'sonraki': '28.10 03:00', 'son': ...} döndürür, değilse None."""
    if os.name != "nt":
        return None
    r = _ps(f"$t=Get-ScheduledTask -TaskName '{_gorev_adi(PLAN_GOREV_ADI)}' -ErrorAction SilentlyContinue;"
            "if($t){$i=$t|Get-ScheduledTaskInfo;"
            "Write-Output ('VAR|'+$i.NextRunTime.ToString('dd.MM HH:mm')+'|'+$i.LastRunTime.ToString('dd.MM.yyyy HH:mm'))}")
    satir = r.stdout.strip()
    if not satir.startswith("VAR|"):
        return None
    _, sonraki, son = (satir.split("|") + ["", ""])[:3]
    return {"sonraki": sonraki, "son": "" if son.endswith("1999 00:00") or son.startswith("30.11.1999") else son}


# ---------------------------------------------------------------------------
# 11. ARAYÜZ
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# YORUMLARA OTOMATİK CEVAP
# ---------------------------------------------------------------------------
YORUM_DOSYA = yol("yorumlar.json")
YORUM_GOREV_ADI = "ShortsStudyo Yorum Cevap"
VARSAYILAN_YORUM_STIL = ("Samimi ve sıcak, hikâyeyi seven bir anlatıcı gibi; kısa tut, izleyiciyi bir sonraki "
                         "hikâyeye davet et.")
VARSAYILAN_YORUM_STIL_BIRADIM = ("Samimi, sıcak ve bilgili bir arkadaş gibi; kısa ve net. Teşekkür eden olursa yorumuna "
                                 "özel karşılık ver, soru sorana kısa bir ipucu ver, izleyiciyi denemeye teşvik et.")
VARSAYILAN_YORUM_STIL_EN = ("Warm and friendly, like a storyteller who loves the story; keep it short and invite the "
                            "viewer to the next story.")
YORUM_GUNLUK_SINIR = 100      # günlük en fazla cevap (YouTube kotası: cevap başına 50 birim)
YORUM_TUR_SINIR = 20          # bir kontrolde en fazla cevap
_yorum_kilit = threading.Lock()


def yorum_oku():
    try:
        with open(YORUM_DOSYA, encoding="utf-8") as f:
            v = json.load(f)
    except (OSError, ValueError):
        v = {}
    v.setdefault("kayit", [])          # [{id, video_id, video, yazar, yorum, cevap, durum, neden, tarih}]
    v.setdefault("gunluk", {})         # {"2026-10-28": 4}
    v.setdefault("son_kontrol", None)
    return v


def yorum_yaz(v):
    v["kayit"] = v["kayit"][-400:]
    v["gunluk"] = dict(sorted(v["gunluk"].items())[-14:])
    _json_yaz(YORUM_DOSYA, v)


def _yorum_cevaplari_uret(yorumlar, stil, onceki_cevaplar, log=print):
    """Tek Gemini isteğiyle tüm yeni yorumlara karar + cevap üretir."""
    satirlar = []
    for i, y in enumerate(yorumlar):
        satirlar.append(f'[Y{i + 1}] Video: "{y["video"] or "bilinmiyor"}" | Hikayenin özeti: {y["ozet"] or "-"} | '
                        f'Yorumu yazan: {y["yazar"]} | Yorum: "{y["yorum"]}"')
    kanal_tanim = ('"Bir Adım Hikâyeler" adlı Türkçe' if DIL == "tr" else
                   f'"{profil_adi() or "Bir Adım Hikâyeler English"}" (Bir Adım Hikâyeler English) adlı İngilizce')
    kanal_konu = "kanalda kısa korku, gizem ve gerilim hikayeleri yayınlanıyor"
    if nblm_mi():
        kanal_tanim = '"BirAdım" adlı Türkçe'
        kanal_konu = ('kanalda kişisel gelişim, öğrenme teknikleri ve psikoloji üzerine kısa, öğretici videolar '
                      'yayınlanıyor (slogan: "Öğren, düşün, ilerle."). Özet alanı videoda anlatılanlardır; bilgi '
                      'sorularına ona dayanarak kısa ve doğru cevap ver, emin olmadığın bilgiyi uydurma. Kişisel sağlık/'
                      'psikolojik sorun anlatan olursa nazik ol ve gerekiyorsa bir uzmana danışmasını öner')
    prompt = f"""Sen {kanal_tanim} YouTube kanalının sahibisin; {kanal_konu}. Aşağıdaki izleyici yorumlarına kanal adına cevap yaz.

Cevap tarzı: {stil}

Kurallar:
- Her cevap yoruma özel olsun: yorumda söylenen şeye değin. Genel geçer "teşekkürler" cevabı YASAK.
- 1-2 cümle, en fazla 180 karakter. Yorumun dilinde yaz (Türkçe yoruma Türkçe, İngilizceye İngilizce).
- En fazla 1 emoji. Link, hashtag, @etiket YOK. Abone ol diye yalvarma.
- Hikayenin/videonun sonunu soran ya da anlamayan olursa kısaca, nazikçe açıkla.
- Videoların gerçek olup olmadığı ya da yapay zekayla yapılıp yapılmadığı sorulursa dürüst ol: üretimde yapay zeka
  araçları kullanılır{'' if nblm_mi() else ', hikayeler kurgudur'}. Bunu asla inkâr etme.
- Olmayan bir şey vaat etme (belli bir tarihte devam videosu, çekiliş vb.).
- Şu cevapları tekrar etme, her cevap farklı olsun: {' | '.join(onceki_cevaplar[-15:]) or '-'}

karar: "cevapla" ya da "atla". SADECE şunları ATLA: spam, reklam, link içeren yorumlar, hakaret/nefret söylemi,
cinsel içerik, kışkırtma, tamamen anlamsız harf dizileri. Atlarsan "neden" kısa yazılsın, "cevap" boş kalsın.
Kısa tepkiler ("tehlikeli", "korktum", "neymiş yani") ve hikayeyle ilgili sorular ("sonra ne oldu?", "e kördü hani")
ASLA atlanmaz; sorulara hikayenin özetine dayanarak kısa bir cevap ver. Özet yoksa genel ama yoruma uygun cevap ver.
Listedeki HER yorum için, köşeli parantezdeki kimliği ("Y1", "Y2"...) "id" alanına yazarak bir kayıt döndür.

Yorumlar:
{chr(10).join(satirlar)}

Yanıtı YALNIZCA şu JSON biçiminde ver:
{{"cevaplar": [{{"id": "Y1", "karar": "cevapla", "neden": "", "cevap": "..."}}]}}"""
    v = _json_coz(_gemini_uret(prompt, log, json_mod=True))
    sonuc = {}
    for c in v.get("cevaplar") or []:
        m = re.search(r"(\d+)", str(c.get("id") or c.get("no") or ""))
        if m:
            sonuc[int(m.group(1)) - 1] = c          # Y1 -> 0
    return sonuc


def yorum_cevap_gonder(yt, parent_id, metin):
    yt.comments().insert(part="snippet", body={"snippet": {"parentId": parent_id,
                                                           "textOriginal": metin[:500]}}).execute()


def yorum_turu(log=print, gonder=None):
    """Yeni yorumları bulur, cevap üretir ve (ayara göre) gönderir ya da onaya bırakır.
    Döndürür: {'yeni': n, 'gonderilen': n, 'taslak': n, 'atlanan': n}"""
    ayar = ayar_oku()
    if gonder is None:
        gonder = ayar.get("yorum_mod", "oto") == "oto"
    with _yorum_kilit:
        kilit = os.path.join(GECICI, "yorum.kilit")
        if os.path.exists(kilit) and time.time() - os.path.getmtime(kilit) < 600:
            return {"yeni": 0, "gonderilen": 0, "taslak": 0, "atlanan": 0, "mesgul": True}
        with open(kilit, "w") as f:
            f.write(str(os.getpid()))
        try:
            return _yorum_turu(ayar, gonder, log)
        finally:
            try:
                os.remove(kilit)
            except OSError:
                pass


def _yorum_turu(ayar, gonder, log):
    yt = _yeni_servis("youtube", "v3")
    if yt is None:
        raise RuntimeError("YouTube bağlı değil.")
    try:
        bekleyen_ilk_yorumlar(log)
    except Exception as e:
        log(f"[!] Bekleyen ilk yorumlar: {str(e)[:150]}")
    kanal = kanal_bilgisi(yt)
    if not kanal:
        raise RuntimeError("Bağlı hesapta kanal bulunamadı.")
    hedef = ayar.get("hedef_kanal", "")
    if hedef and _kanal_norm(kanal["ad"]) != _kanal_norm(hedef):
        raise RuntimeError(f"Bağlı kanal '{kanal['ad']}', hedef '{hedef}' değil; yorumlara cevap verilmedi.")
    if not yorum_izni_var():
        raise RuntimeError("YORUM_IZNI: Yorumlara cevap yazmak için YouTube'dan ek izin gerekiyor. Yorumlar "
                           "sayfasındaki 'Yorum izni ver' butonuna bas.")
    v = yorum_oku()
    bilinen = {k["id"] for k in v["kayit"]}
    r = yt.commentThreads().list(part="snippet,replies", allThreadsRelatedToChannelId=kanal["id"], order="time",
                                 maxResults=50, textFormat="plainText").execute()
    gecmis_ = {k.get("video_id"): k for k in gecmis_oku() if k.get("video_id")}
    yeniler = []
    for th in r.get("items", []):
        ust = th["snippet"]["topLevelComment"]
        sn = ust["snippet"]
        yazar_kanal = (sn.get("authorChannelId") or {}).get("value")
        if th["id"] in bilinen or yazar_kanal == kanal["id"]:
            continue
        cevaplar = (th.get("replies") or {}).get("comments", [])
        if any((c["snippet"].get("authorChannelId") or {}).get("value") == kanal["id"] for c in cevaplar):
            continue   # zaten elle cevaplanmış
        vid = sn.get("videoId") or th["snippet"].get("videoId")
        k = gecmis_.get(vid, {})
        yeniler.append({"id": th["id"], "video_id": vid, "video": (k.get("baslik") or "").replace(" #shorts", ""),
                        "ozet": " ".join((k.get("hikaye") or "").split()[:60]),
                        "yazar": sn.get("authorDisplayName", ""), "yorum": sn.get("textDisplay", "")[:600],
                        "tarih": sn.get("publishedAt", "")})
    v["son_kontrol"] = datetime.datetime.now().isoformat(timespec="seconds")
    sonuc = {"yeni": len(yeniler), "gonderilen": 0, "taslak": 0, "atlanan": 0}
    if not yeniler:
        yorum_yaz(v)
        return sonuc
    bugun = datetime.date.today().isoformat()
    kalan = max(0, YORUM_GUNLUK_SINIR - v["gunluk"].get(bugun, 0))
    yeniler = list(reversed(yeniler))[:YORUM_TUR_SINIR]     # eskiden yeniye
    log(f"[+] {len(yeniler)} yeni yorum bulundu, cevaplar yazılıyor...")
    onceki = [k["cevap"] for k in v["kayit"] if k.get("cevap")]
    cevaplar = _yorum_cevaplari_uret(yeniler, ayar.get("yorum_stil") or VARSAYILAN_YORUM_STIL, onceki, log)
    denemeler = v.setdefault("deneme", {})
    for i, y in enumerate(yeniler):
        c = cevaplar.get(i)
        metin = str((c or {}).get("cevap") or "").strip().strip('"')
        if not c or (c.get("karar") == "cevapla" and not metin):
            # Gemini bu yoruma karar döndürmedi: kalıcı olarak atlama, sonraki kontrolde yeniden dene (en fazla 3 kez)
            denemeler[y["id"]] = denemeler.get(y["id"], 0) + 1
            if denemeler[y["id"]] < 3:
                log(f"[~] '{y['yorum'][:40]}' için cevap gelmedi, sonraki kontrolde yeniden denenecek.")
                continue
            c = {"karar": "atla", "neden": "Gemini 3 denemede cevap üretmedi"}
        denemeler.pop(y["id"], None)
        kayit = dict(y, cevap=metin, neden=str(c.get("neden") or "belirtilmedi"), zaman=v["son_kontrol"])
        if c.get("karar") != "cevapla" or not metin:
            kayit["durum"] = "atlandi"
            sonuc["atlanan"] += 1
        elif not gonder:
            kayit["durum"] = "taslak"
            sonuc["taslak"] += 1
        elif kalan <= 0:
            kayit["durum"] = "taslak"
            kayit["neden"] = "Günlük cevap sınırı doldu"
            sonuc["taslak"] += 1
        else:
            try:
                yorum_cevap_gonder(yt, y["id"], metin)
                kayit["durum"] = "gonderildi"
                sonuc["gonderilen"] += 1
                kalan -= 1
                v["gunluk"][bugun] = v["gunluk"].get(bugun, 0) + 1
                log(f"[✓] {y['yazar']}: \"{y['yorum'][:50]}\" → \"{metin[:60]}\"")
            except Exception as e:
                kayit["durum"] = "hata"
                kayit["neden"] = str(e)[:200]
        v["kayit"].append(kayit)
    yorum_yaz(v)
    return sonuc


def yorum_taslak_gonder(yorum_id, metin):
    """Onay bekleyen (ya da düzenlenen) cevabı gönderir."""
    yt = _yeni_servis("youtube", "v3")
    if yt is None:
        raise RuntimeError("YouTube bağlı değil.")
    yorum_cevap_gonder(yt, yorum_id, metin)
    v = yorum_oku()
    bugun = datetime.date.today().isoformat()
    for k in v["kayit"]:
        if k["id"] == yorum_id:
            k.update(cevap=metin, durum="gonderildi", neden="")
    v["gunluk"][bugun] = v["gunluk"].get(bugun, 0) + 1
    yorum_yaz(v)


def yorum_durum_degistir(yorum_id, durum_):
    v = yorum_oku()
    for k in v["kayit"]:
        if k["id"] == yorum_id:
            k["durum"] = durum_
    yorum_yaz(v)


def yorum_gorev_kur(dakika=10):
    """Program kapalıyken de: Windows her 'dakika' dakikada bir yorumları kontrol eder."""
    if os.name != "nt":
        raise RuntimeError("Bu özellik sadece Windows'ta çalışır.")
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(pyw):
        pyw = sys.executable
    q = lambda x: str(x).replace("'", "''")  # noqa: E731
    ps = (f"$a=New-ScheduledTaskAction -Execute '{q(pyw)}' -Argument '\"{q(os.path.abspath(__file__))}\"{_profil_arg()} --yorumlar' "
          f"-WorkingDirectory '{q(BASE)}';"
          f"$t=New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) "
          f"-RepetitionInterval (New-TimeSpan -Minutes {int(dakika)});"
          "$s=New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries "
          "-MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 9);"
          f"Register-ScheduledTask -TaskName '{_gorev_adi(YORUM_GOREV_ADI)}' -Action $a -Trigger $t -Settings $s "
          "-Description 'Shorts Studyo yorumlara cevap verir' -Force | Out-Null; Write-Output TAMAM")
    r = _ps(ps)
    if r.returncode != 0 or "TAMAM" not in r.stdout:
        raise RuntimeError(r.stderr.strip()[-300:] or "Windows görevi oluşturulamadı.")


def yorum_gorev_kaldir():
    if os.name == "nt":
        _ps(f"Unregister-ScheduledTask -TaskName '{_gorev_adi(YORUM_GOREV_ADI)}' -Confirm:$false -ErrorAction SilentlyContinue")


def yorum_gorev_var():
    if os.name != "nt":
        return False
    r = _ps(f"if(Get-ScheduledTask -TaskName '{_gorev_adi(YORUM_GOREV_ADI)}' -ErrorAction SilentlyContinue){{Write-Output VAR}}")
    return "VAR" in r.stdout


FONT_KLASOR = os.path.join(BASE, "fontlar")
ROBOTO_URL = ["https://github.com/googlefonts/roboto-2/raw/main/src/hinted/{ad}.ttf",
              "https://cdn.jsdelivr.net/gh/googlefonts/roboto-2@main/src/hinted/{ad}.ttf"]


def roboto_hazirla():
    """Arayüz yazı tipi Roboto'yu (YouTube Studio'nun yazı tipi) fontlar klasörüne indirir ve sadece bu
    program için Windows'a tanıtır. İnternet yoksa sessizce geçer; arayüz Segoe UI ile açılır."""
    if os.name != "nt":
        return
    import urllib.request
    import ctypes
    os.makedirs(FONT_KLASOR, exist_ok=True)
    isaret = os.path.join(FONT_KLASOR, ".denendi")
    for ad in ("Roboto-Regular", "Roboto-Medium", "Roboto-Bold"):
        hedef = os.path.join(FONT_KLASOR, ad + ".ttf")
        if not os.path.exists(hedef):
            if os.path.exists(isaret) and time.time() - os.path.getmtime(isaret) < 86400:
                continue   # bugün denendi, açılışı yavaşlatma
            for url in ROBOTO_URL:
                try:
                    with urllib.request.urlopen(url.format(ad=ad), timeout=4) as r:
                        veri = r.read()
                    if veri[:4] in (b"\x00\x01\x00\x00", b"true", b"OTTO") and len(veri) > 50000:
                        with open(hedef, "wb") as f:
                            f.write(veri)
                        break
                except Exception:
                    continue
            if not os.path.exists(hedef):
                try:
                    open(isaret, "w").close()
                except OSError:
                    pass
        if os.path.exists(hedef):
            try:
                ctypes.windll.gdi32.AddFontResourceExW(hedef, 0x10, 0)   # FR_PRIVATE: sadece bu program
            except Exception:
                pass


def tema_koyu_mu(ayar):
    """'koyu' / 'acik' ya da 'sistem' (Windows'un uygulama teması)."""
    t = ayar.get("tema", "acik")
    if t == "sistem":
        if os.name != "nt":
            return False
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
                return winreg.QueryValueEx(k, "AppsUseLightTheme")[0] == 0
        except Exception:
            return False
    return t == "koyu"


def pencere_koyu_baslik(pencere, koyu):
    """Windows 10/11'de pencerenin başlık çubuğunu da koyu yapar."""
    if os.name != "nt":
        return
    try:
        import ctypes
        pencere.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(pencere.winfo_id())
        deger = ctypes.c_int(1 if koyu else 0)
        for oz in (20, 19):   # DWMWA_USE_IMMERSIVE_DARK_MODE (yeni / eski Windows 10)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, oz, ctypes.byref(deger),
                                                          ctypes.sizeof(deger)) == 0:
                break
    except Exception:
        pass


def _donma_bekcisi(p):
    """Arayüz 4 sn'den uzun donarsa o anda ne çalıştığını gecici/donma_raporu.txt dosyasına yazar (hata ayıklama)."""
    import traceback
    kalp = {"t": time.time(), "yazildi": False}
    ana = threading.main_thread().ident

    def atis():
        kalp["t"] = time.time()
        kalp["yazildi"] = False
        try:
            p.after(500, atis)
        except Exception:
            pass
    p.after(500, atis)

    def izle():
        while True:
            time.sleep(1)
            gecen = time.time() - kalp["t"]
            if 4 < gecen < 600 and not kalp["yazildi"]:      # çok uzun boşluk = bilgisayar uykudaydı, donma değil
                kalp["yazildi"] = True
                try:
                    satirlar = [f"=== {datetime.datetime.now():%d.%m.%Y %H:%M:%S} · arayüz {gecen:.0f} sn yanıt vermiyor ==="]
                    for tid, cerceve in sys._current_frames().items():
                        ad = "ANA" if tid == ana else next((t.name for t in threading.enumerate() if t.ident == tid), "?")
                        satirlar.append(f"--- iş parçacığı {ad} ({tid})")
                        satirlar += [x.rstrip() for x in traceback.format_stack(cerceve)[-14:]]
                    with open(os.path.join(GECICI, "donma_raporu.txt"), "a", encoding="utf-8") as f:
                        f.write("\n".join(satirlar) + "\n\n")
                except Exception:
                    pass
    threading.Thread(target=izle, daemon=True, name="donma_bekcisi").start()


def arayuzu_baslat():
    import tkinter as tk
    import tkinter.font as tkfont
    from tkinter import ttk, messagebox
    import webbrowser
    import queue

    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)   # bulanık yazıyı engeller
        except Exception:
            pass

    ayar = ayar_oku()
    # YouTube Studio'nun açık ve koyu temaları
    koyu_tema = tema_koyu_mu(ayar)
    if koyu_tema:
        R = dict(bg="#0F0F0F", yan="#0F0F0F", yan_hover="#272727", kart="#0F0F0F", kart2="#272727",
                 kenar="#3F3F3F", cizgi="#3F3F3F", yazi="#F1F1F1", soluk="#AAAAAA", soluk2="#717171",
                 vurgu="#3EA6FF", vurgu2="#65B8FF", vurgu_yazi="#0F0F0F", kirmizi="#F28B82", marka="#FF0000",
                 yesil="#81C995", yesil2="#81C995", sari="#FDD663", mavi="#3EA6FF", mor="#C58AF9",
                 secili="#263850", cerceve="#4F4F4F", ayrac="#272727", hover_kenar="#717171",
                 ana_btn="#F1F1F1", ana_btn2="#D9D9D9", ana_yazi="#0F0F0F", metin2="#DDDDDD",
                 onizleme="#000000", basari_bg="#1E3A2A", hata_bg="#4A2424", uzun_ikon="#F1F1F1",
                 uzun_ok="#0F0F0F", grafik="#2D8FEA")
    else:
        R = dict(bg="#FFFFFF", yan="#FFFFFF", yan_hover="#F2F2F2", kart="#FFFFFF", kart2="#F2F2F2",
                 kenar="#E0E0E0", cizgi="#D9D9D9", yazi="#0F0F0F", soluk="#606060", soluk2="#909090",
                 vurgu="#065FD4", vurgu2="#0B57D0", vurgu_yazi="#FFFFFF", kirmizi="#C5221F", marka="#FF0000",
                 yesil="#1E8E3E", yesil2="#137333", sari="#B06000", mavi="#065FD4", mor="#8430CE",
                 secili="#E8F0FE", cerceve="#CCCCCC", ayrac="#F0F0F0", hover_kenar="#BDBDBD",
                 ana_btn="#0F0F0F", ana_btn2="#272727", ana_yazi="#FFFFFF", metin2="#303030",
                 onizleme="#1F1F1F", basari_bg="#E6F4EA", hata_bg="#FCE8E6", uzun_ikon="#0F0F0F",
                 uzun_ok="#FFFFFF", grafik="#065FD4")
    try:
        roboto_hazirla()
    except Exception:
        pass

    p = tk.Tk()
    _donma_bekcisi(p)
    p.title("Shorts Stüdyo")
    p.configure(bg=R["bg"])
    pencere_koyu_baslik(p, koyu_tema)
    _aileler = set(tkfont.families(p))
    YAZI = next((f for f in ("Roboto", "Segoe UI Variable Text", "Segoe UI") if f in _aileler), "Segoe UI")
    if "Roboto Medium" in _aileler:
        YAZI_ORTA = "Roboto Medium"
    elif YAZI.startswith("Segoe") and "Segoe UI Semibold" in _aileler:
        YAZI_ORTA = "Segoe UI Semibold"
    else:
        YAZI_ORTA = None          # Roboto'da yarı kalın yerine kalın kullanılır

    def F(boyut, agirlik="normal"):
        """Yazı tipi: 'orta' = Studio başlıklarındaki yarı kalın ağırlık."""
        if agirlik == "orta":
            return (YAZI_ORTA, boyut) if YAZI_ORTA else (YAZI, boyut, "bold")
        return (YAZI, boyut, agirlik)
    olcek = max(1.0, p.winfo_fpixels("1i") / 96)

    def px(x):
        return int(x * olcek)

    gen, yuk = px(1200), px(860)
    gen = min(gen, p.winfo_screenwidth() - 40)
    yuk = min(yuk, p.winfo_screenheight() - 90)
    p.geometry(f"{gen}x{yuk}")
    p.minsize(min(px(1000), gen), min(px(640), yuk))
    if os.path.exists(yol("simge.ico")):
        try:
            p.iconbitmap(yol("simge.ico"))
        except Exception:
            pass

    # ---------- ttk stilleri (combobox, spinbox, treeview, scrollbar, progress) ----------
    st = ttk.Style(p)
    st.theme_use("clam")
    st.configure(".", background=R["bg"], foreground=R["yazi"], fieldbackground=R["kart"], font=F(10),
                 bordercolor=R["cerceve"], lightcolor=R["kart"], darkcolor=R["kart"], troughcolor=R["kenar"],
                 focuscolor=R["kart"])
    st.configure("TEntry", fieldbackground=R["kart"], foreground=R["yazi"], insertcolor=R["yazi"], padding=8,
                 bordercolor=R["cerceve"])
    st.map("TEntry", bordercolor=[("focus", R["vurgu"])], fieldbackground=[("readonly", R["bg"])])
    st.configure("TCombobox", fieldbackground=R["kart"], background=R["kart"], foreground=R["yazi"],
                 arrowcolor=R["soluk"], padding=6, bordercolor=R["cerceve"])
    st.map("TCombobox", fieldbackground=[("readonly", R["kart"])], foreground=[("readonly", R["yazi"])],
           selectbackground=[("readonly", R["kart"])], selectforeground=[("readonly", R["yazi"])],
           bordercolor=[("focus", R["vurgu"])], arrowcolor=[("active", R["yazi"])])
    p.option_add("*TCombobox*Listbox.background", R["kart"])
    p.option_add("*TCombobox*Listbox.foreground", R["yazi"])
    p.option_add("*TCombobox*Listbox.selectBackground", R["secili"])
    p.option_add("*TCombobox*Listbox.selectForeground", R["yazi"])
    p.option_add("*TCombobox*Listbox.font", F(10))
    p.option_add("*TCombobox*Listbox.borderWidth", 0)
    st.configure("TSpinbox", fieldbackground=R["kart"], foreground=R["yazi"], arrowcolor=R["soluk"], padding=6,
                 bordercolor=R["cerceve"])
    st.configure("Horizontal.TProgressbar", background=R["vurgu"], troughcolor=R["kenar"], thickness=4,
                 borderwidth=0, lightcolor=R["vurgu"], darkcolor=R["vurgu"])
    st.configure("Horizontal.TScale", background=R["kart"], troughcolor=R["kenar"], bordercolor=R["kart"],
                 lightcolor=R["kart"], darkcolor=R["kart"])
    st.configure("Treeview", background=R["kart"], fieldbackground=R["kart"], foreground=R["yazi"],
                 rowheight=px(40), borderwidth=0, font=F(10))
    st.map("Treeview", background=[("selected", R["secili"])], foreground=[("selected", R["yazi"])])
    st.configure("Treeview.Heading", background=R["kart"], foreground=R["soluk"], font=F(9, "orta"),
                 borderwidth=0, relief="flat", padding=(px(10), px(8)))
    st.map("Treeview.Heading", background=[("active", R["kart2"])])
    st.configure("Liste.Treeview", rowheight=px(68))
    st.configure("Vertical.TScrollbar", background=R["cizgi"], troughcolor=R["kart"], bordercolor=R["kart"],
                 lightcolor=R["cizgi"], darkcolor=R["cizgi"], arrowcolor=R["soluk"], borderwidth=0,
                 arrowsize=px(10))
    st.map("Vertical.TScrollbar", background=[("active", R["soluk2"])])

    durum = {"mesgul": False, "durdur": False, "son": None, "seri": False, "mod": "uret",
             "bas": 0, "resimler": {}, "secili": None, "sayfa": None}

    # Fare tekerleği açılır menülerin/sayı kutularının değerini değiştirmesin; sadece sayfayı kaydırsın.
    for sinif in ("TCombobox", "TSpinbox"):
        for olay in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            p.bind_class(sinif, olay, lambda e: None)
    v = {}
    secim_kayit = {}

    # Arka plan işleri arayüze doğrudan dokunmaz; komutlar kuyruğa girer, ana döngü işler.
    kuyruk = queue.Queue()

    def ui(fn):
        kuyruk.put(fn)

    def kuyruk_isle():
        try:
            while True:
                fn = kuyruk.get_nowait()
                try:
                    fn()
                except Exception as e:
                    print("arayüz:", e)
        except queue.Empty:
            pass
        p.after(40, kuyruk_isle)
    p.after(40, kuyruk_isle)

    def kaydet(*_):
        for k_, x in v.items():
            try:
                ayar[k_] = x.get()
            except (tk.TclError, ValueError):
                pass
        ayar_yaz(ayar)

    def degisken(ad, tip):
        if ad in v:
            return v[ad]
        x = tip(value=ayar[ad])
        x.trace_add("write", kaydet)
        v[ad] = x
        return x

    def zemin(w):
        try:
            return w.cget("bg")
        except tk.TclError:
            return R["bg"]

    def yuvarlak_kart(ust, r=16, **kw):
        """Yeni Studio kartı: ince çerçeve + yuvarlak köşeler. Tk çerçevesinin üstüne kenar çizgileri ve köşe
        yayları yerleştirilir (place); içerik eskisi gibi pack/grid ile eklenir."""
        kw.pop("highlightthickness", None)
        kw.pop("highlightbackground", None)
        f = tk.Frame(ust, highlightthickness=0, bd=0, **kw)
        r = px(r)
        ic_renk, dis_renk, cizgi = kw.get("bg", R["kart"]), zemin(ust), R["kenar"]
        parcalar = []
        for x, y, w_, h_, rx, ry, rw, rh in (
                (r, 0, -2 * r, 1, 0, 0, 1, 0), (r, -1, -2 * r, 1, 0, 1, 1, 0),
                (0, r, 1, -2 * r, 0, 0, 0, 1), (-1, r, 1, -2 * r, 1, 0, 0, 1)):
            cz = tk.Frame(f, bg=cizgi, height=1, width=1, bd=0, highlightthickness=0)
            cz.place(x=x, y=y, relx=rx, rely=ry, relwidth=rw, relheight=rh, width=w_ if rw else 1,
                     height=h_ if rh else 1, bordermode="outside")
            parcalar.append(cz)
        for (rx, ry, bas) in ((0, 0, 90), (1, 0, 0), (0, 1, 180), (1, 1, 270)):
            k = tk.Canvas(f, width=r, height=r, bg=dis_renk, highlightthickness=0, bd=0)
            ox = 0 if rx == 0 else -r
            oy = 0 if ry == 0 else -r
            k.place(relx=rx, rely=ry, x=ox, y=oy, bordermode="outside")
            cx = r if rx == 0 else 0
            cy = r if ry == 0 else 0
            k.create_arc(cx - r, cy - r, cx + r, cy + r, start=bas, extent=90, fill=ic_renk, outline=ic_renk,
                         style="pieslice")
            k.create_arc(cx - r + 0.5, cy - r + 0.5, cx + r - 1, cy + r - 1, start=bas, extent=90, outline=cizgi,
                         style="arc")
            parcalar.append(k)

        def ustte_tut(_=None):
            for w_ in parcalar:
                try:
                    w_.lift()
                except tk.TclError:
                    pass
        f.bind("<Map>", ustte_tut, add="+")
        f.after_idle(ustte_tut)
        f._yuvarlak_parcalar = parcalar
        return f

    # ======================================================================
    # ANİMASYON ÇEKİRDEĞİ
    # ======================================================================
    def anim_acik():
        return bool(ayar.get("animasyon", True))

    def _hex(c):
        c = c.lstrip("#")
        return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))

    def karis(a, b, t):
        """İki renk arasında t (0..1) oranında geçiş."""
        try:
            x, y = _hex(a), _hex(b)
        except (ValueError, AttributeError):
            return b if t >= 0.5 else a
        t = max(0.0, min(1.0, t))
        return "#%02x%02x%02x" % tuple(int(x[i] + (y[i] - x[i]) * t) for i in range(3))

    def yumusak(t):
        return 1 - (1 - t) ** 3          # ease-out cubic

    _animler = {}

    def anim(anahtar, sure_ms, adim, bitti=None):
        """adim(t) fonksiyonunu t=0..1 arasında yumuşak geçişle çağırır. Aynı anahtarla yeni animasyon
        başlarsa eskisi iptal olur. Animasyonlar kapalıysa doğrudan son kare çizilir."""
        if not anim_acik() or sure_ms <= 0:
            adim(1.0)
            if bitti:
                bitti()
            return
        kimlik = object()
        _animler[anahtar] = kimlik
        bas = time.perf_counter()

        def kare():
            if _animler.get(anahtar) is not kimlik:
                return
            t = min(1.0, (time.perf_counter() - bas) * 1000 / sure_ms)
            try:
                adim(yumusak(t))
            except tk.TclError:
                return
            if t < 1.0:
                p.after(16, kare)
            else:
                _animler.pop(anahtar, None)
                if bitti:
                    bitti()
        kare()

    def sayac_anim(lbl, hedef, bicim=lambda x: f"{int(round(x)):,}".replace(",", "."), sure=700):
        """Sayıyı eski değerinden yenisine sayarak gösterir."""
        try:
            eski = float(getattr(lbl, "_sayi", 0) or 0)
            hedef = float(hedef)
        except (TypeError, ValueError):
            lbl.config(text=str(hedef))
            return
        lbl._sayi = hedef
        if eski == hedef:
            lbl.config(text=bicim(hedef))
            return
        anim(("sayac", id(lbl)), sure, lambda t: lbl.config(text=bicim(eski + (hedef - eski) * t)))

    def pencere_belir(w, sure=180):
        """Pencereyi şeffaftan görünüre yumuşakça açar (Windows'ta)."""
        try:
            w.attributes("-alpha", 0.0 if anim_acik() else 1.0)
        except tk.TclError:
            return
        anim(("pencere", id(w)), sure, lambda t: w.attributes("-alpha", t))

    # ======================================================================
    # BİLEŞENLER
    # ======================================================================
    def yuvarlak(c, x1, y1, x2, y2, r, **kw):
        n = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
             x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
        return c.create_polygon(n, smooth=True, **kw)

    def temiz(metin):
        """Baştaki renkli emojileri atar (Studio görünümü sade yazı kullanır)."""
        if not metin:
            return metin
        i = 0
        while i < len(metin) and (0x1F000 <= ord(metin[i]) <= 0x1FAFF or 0x2600 <= ord(metin[i]) <= 0x26FF
                                  or ord(metin[i]) in (0xFE0F, 0x23F3, 0x23F1, 0x2728, 0x270F, 0x23F0)
                                  or (metin[i] == " " and i > 0)):
            i += 1
        kalan = metin[i:].strip()
        return (kalan or metin).replace("＋", "+")

    class Dugme(tk.Canvas):
        """Studio tarzı hap (pill) buton."""
        RENK = {"ana": (R["ana_btn"], R["ana_btn2"], R["ana_yazi"]),
                "ikincil": (R["kart2"], R["kenar"], R["yazi"]),
                "yesil": (R["vurgu"], R["vurgu2"], R["vurgu_yazi"]),
                "hayalet": (None, R["kart2"], R["yazi"]),
                "tehlike": (None, R["hata_bg"], R["kirmizi"])}
        BOY = {"kucuk": (9, 32), "orta": (10, 36), "buyuk": (11, 44)}

        def __init__(self, ust, text="", command=None, tur="ikincil", boy="orta", genislik=None):
            self._z = zemin(ust)
            text = temiz(text)
            fs, h = self.BOY[boy]
            ff = F(fs, "orta")
            self._f = tkfont.Font(family=ff[0], size=fs, weight=ff[2] if len(ff) > 2 else "normal")
            self._h = px(h)
            self._text, self._cmd, self._tur, self._durum = text, command, tur, "normal"
            self._ust_mu, self._basili, self._hv, self._dalga = False, False, 0.0, None
            w = genislik or (self._f.measure(text) + px(34))
            super().__init__(ust, width=w, height=self._h, bg=self._z, highlightthickness=0, bd=0, cursor="hand2")
            self.bind("<Enter>", lambda e: self._ayarla(ust_mu=True))
            self.bind("<Leave>", lambda e: self._ayarla(ust_mu=False, basili=False))
            self.bind("<ButtonPress-1>", self._bas)
            self.bind("<ButtonRelease-1>", self._birak)
            self.bind("<Configure>", lambda e: self._ciz())
            self._ciz()

        def _ayarla(self, **kw):
            if "ust_mu" in kw and kw["ust_mu"] != self._ust_mu:
                self._ust_mu = kw["ust_mu"]
                bas_, hedef = self._hv, 1.0 if self._ust_mu else 0.0

                def adim(t):
                    self._hv = bas_ + (hedef - bas_) * t
                    self._ciz()
                anim(("dugme", id(self)), 140, adim)
            if "basili" in kw:
                self._basili = kw["basili"]
            self._ciz()

        def _bas(self, e):
            if self._durum == "disabled":
                return
            self._dalga = [e.x, e.y, 0.0]

            def adim(t):
                if self._dalga:
                    self._dalga[2] = t
                self._ciz()
            anim(("dalga", id(self)), 480, adim, bitti=lambda: (setattr(self, "_dalga", None), self._ciz()))
            self._ayarla(basili=True)

        def _dalga_ciz(self, w, h, dolgu):
            """Tıklanan noktadan yayılan halka; hap şeklinin dışına taşmasın diye kenara kırpılır."""
            import math
            x0, y0, t = self._dalga
            r_ = (h - 2) / 2 - 0.5
            cy = h / 2
            en_uzak = max(math.hypot(x0 - a, y0 - b) for a, b in ((0, 0), (w, 0), (0, h), (w, h)))
            rr = max(2.0, en_uzak * t)
            noktalar = []
            for i in range(48):
                a = 2 * math.pi * i / 48
                x, y = x0 + rr * math.cos(a), y0 + rr * math.sin(a)
                mx = min(max(x, 1 + r_), w - 1 - r_)          # hapın orta çizgisindeki en yakın nokta
                dx, dy = x - mx, y - cy
                d = math.hypot(dx, dy)
                if d > r_:
                    x, y = mx + dx / d * r_, cy + dy / d * r_
                noktalar += [x, y]
            rgb = _hex(dolgu) if dolgu.startswith("#") else (128, 128, 128)
            ton = "#FFFFFF" if (0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]) < 140 else "#000000"
            guc = 0.22 if ton == "#FFFFFF" else 0.12
            self.create_polygon(noktalar, fill=karis(dolgu, ton, guc * (1 - t)), outline="")

        def _birak(self, e):
            tikla = self._basili and self._ust_mu and self._durum != "disabled"
            self._ayarla(basili=False)
            if tikla and self._cmd:
                self._cmd()

        def _ciz(self):
            self.delete("all")
            w = max(self.winfo_width(), int(super().cget("width")))
            if self.winfo_width() > 1:
                w = self.winfo_width()
            h = self._h
            normal, hover, yazi = self.RENK[self._tur]
            normal = normal or self._z
            kenar = R["cerceve"] if self._tur in ("hayalet", "tehlike") else ""
            if self._durum == "disabled":
                dolgu, yazi = (R["kart2"] if self._tur not in ("hayalet", "tehlike") else self._z), R["soluk2"]
                kenar = R["kenar"] if kenar else ""
            else:
                dolgu = karis(normal, hover, self._hv)
                if self._basili:
                    dolgu = R["cizgi"] if self._tur in ("ikincil", "hayalet", "tehlike") else hover
            ic_ = 1 if (self._basili and self._durum != "disabled") else 0      # basınca hafif içe çöker
            yuvarlak(self, 1 + ic_, 1 + ic_, w - 1 - ic_, h - 1 - ic_, h // 2 - 1 - ic_, fill=dolgu, outline=kenar)
            if self._dalga and self._durum != "disabled" and anim_acik():
                self._dalga_ciz(w, h, dolgu)
            self.create_text(w / 2, h / 2, text=self._text, fill=yazi, font=self._f)
            super().configure(cursor="arrow" if self._durum == "disabled" else "hand2")

        def config(self, cnf=None, **kw):
            degisti = False
            for k_ in ("text", "state", "command", "tur"):
                if k_ in kw:
                    val = kw.pop(k_)
                    if k_ == "text":
                        self._text = temiz(val)
                    elif k_ == "state":
                        self._durum = val
                    elif k_ == "tur":
                        self._tur = val
                    else:
                        self._cmd = val
                    degisti = True
            kw.pop("style", None)
            if cnf or kw:
                super().configure(cnf, **kw)
            if degisti:
                self._ciz()
        configure = config

        def cget(self, k_):
            if k_ == "text":
                return self._text
            if k_ == "state":
                return self._durum
            return super().cget(k_)

        def invoke(self):
            if self._durum != "disabled" and self._cmd:
                self._cmd()

    class Anahtar(tk.Frame):
        """iOS tarzı açma/kapama anahtarı (BooleanVar'a bağlı)."""
        def __init__(self, ust, text, variable, alt=None):
            z = zemin(ust)
            super().__init__(ust, bg=z)
            self.v = variable
            self.c = tk.Canvas(self, width=px(42), height=px(24), bg=z, highlightthickness=0, cursor="hand2")
            self.c.pack(side="left", anchor="n", pady=(px(1), 0))
            lf = tk.Frame(self, bg=z)
            lf.pack(side="left", padx=(px(10), 0), fill="x", expand=True)
            l1 = tk.Label(lf, text=text, bg=z, fg=R["yazi"], font=F(10), cursor="hand2", anchor="w")
            l1.pack(anchor="w")
            if alt:
                al = tk.Label(lf, text=alt, bg=z, fg=R["soluk"], font=F(9), anchor="w", justify="left",
                              wraplength=px(420))
                al.pack(anchor="w", fill="x")
                lf.bind("<Configure>", lambda e: al.config(wraplength=max(px(120), e.width - 4)))
            for w in (self.c, l1):
                w.bind("<Button-1>", lambda e: self.v.set(not self.v.get()))
            self._k = 1.0 if self.v.get() else 0.0
            self.v.trace_add("write", lambda *_: self._kaydir())
            self._ciz()

        def _kaydir(self):
            bas_, hedef = self._k, 1.0 if self.v.get() else 0.0

            def adim(t):
                self._k = bas_ + (hedef - bas_) * t
                self._ciz()
            anim(("anahtar", id(self)), 170, adim)

        def _ciz(self):
            c = self.c
            c.delete("all")
            w, h = px(42), px(24)
            yuvarlak(c, 1, 1, w - 1, h - 1, h // 2, fill=karis(R["hover_kenar"], R["vurgu"], self._k), outline="")
            r = h // 2 - px(3)
            cx = h // 2 + (w - h) * self._k
            c.create_oval(cx - r, h // 2 - r, cx + r, h // 2 + r, fill="#ffffff", outline="")

    def secim(ust, ad, harita, genislik=28):
        """Görünen metni gösterip ayara anahtarı kaydeden combobox (aynı ayar her yerde eşitlenir)."""
        ters = {g: k_ for k_, g in harita.items()}
        x = tk.StringVar(value=harita.get(ayar[ad], list(harita.values())[0]))
        secim_kayit.setdefault(ad, []).append(x)

        def degisti(*_):
            yeni = ters.get(x.get())
            if yeni is None:
                return
            ayar[ad] = yeni
            ayar_yaz(ayar)
            for diger in secim_kayit[ad]:
                if diger is not x and diger.get() != x.get():
                    diger.set(x.get())
        x.trace_add("write", degisti)
        return ttk.Combobox(ust, textvariable=x, values=list(harita.values()), state="readonly", width=genislik)

    def sarmali(lbl, kap, bosluk=0):
        """Etiketin satır genişliğini kapsayıcının gerçek genişliğine göre ayarlar (taşma olmaz)."""
        kap.bind("<Configure>", lambda e: lbl.config(wraplength=max(px(120), e.width - bosluk)), add="+")

    def kart(ust, baslik=None, alt=None, dolu=False, sarma=560, alta=False):
        dis = yuvarlak_kart(ust, bg=R["kart"],
                       padx=px(22), pady=px(18))
        if alta:
            dis.pack(side="bottom", fill="x", pady=(px(16), 0))
        else:
            dis.pack(fill="both" if dolu else "x", expand=dolu, pady=(0, px(16)))
        if baslik:
            tk.Label(dis, text=temiz(baslik), bg=R["kart"], fg=R["yazi"], font=(YAZI, 13, "bold")).pack(anchor="w")
        if alt:
            al = tk.Label(dis, text=alt, bg=R["kart"], fg=R["soluk"], font=F(9), wraplength=px(sarma),
                          justify="left", anchor="w")
            al.pack(anchor="w", fill="x", pady=(px(3), 0))
            sarmali(al, dis, 2 * px(22) + 4)
        ic = tk.Frame(dis, bg=R["kart"])
        ic.pack(fill="both", expand=dolu, pady=(px(14) if baslik or alt else 0, 0))
        return ic

    def etiket(ust, text, soluk=False, kalin=False, boyut=10, **kw):
        return tk.Label(ust, text=text, bg=zemin(ust), fg=R["soluk"] if soluk else R["yazi"],
                        font=F(boyut, "orta") if kalin else F(boyut), **kw)

    def baslik_kutusu(ust, var, **kw):
        """En fazla 100 karakter yazılabilen başlık kutusu; altında Studio'daki gibi '57/100' sayacı."""
        dogrula = (p.register(lambda yeni: len(yeni) <= BASLIK_SINIR), "%P")
        giris = ttk.Entry(ust, textvariable=var, validate="key", validatecommand=dogrula, **kw)
        sayac_ = tk.Label(ust, text="", bg=zemin(ust), fg=R["soluk"], font=F(8), anchor="e")

        def say(*_):
            n = len(var.get())
            sayac_.config(text=f"{n}/{BASLIK_SINIR}", fg=R["kirmizi"] if n >= BASLIK_SINIR else R["soluk"])
        var.trace_add("write", say)
        say()
        return giris, sayac_

    def baglanti(ust, text, komut, boyut=10):
        """Studio'daki mavi metin bağlantısı ('Tümü', 'Planı düzenle')."""
        l_ = tk.Label(ust, text=text, bg=zemin(ust), fg=R["vurgu"], font=F(boyut, "orta"), cursor="hand2")
        l_.bind("<Button-1>", lambda e: komut())
        l_.bind("<Enter>", lambda e: l_.config(font=F(boyut, "orta") + ("underline",) if YAZI_ORTA
                                               else (YAZI, boyut, "bold underline")))
        l_.bind("<Leave>", lambda e: l_.config(font=F(boyut, "orta")))
        return l_

    def ikon_ciz(c, tur, renk, s=22):
        """Menü ve kartlardaki tek renkli çizgi ikonlar."""
        c.delete("all")
        k_ = px(s) / 24
        g = max(1, round(1.8 * k_))

        def P(*n):
            return [x * k_ for x in n]
        if tur == "panel":
            for x1, y1, x2, y2 in ((3, 3, 10, 12), (14, 3, 21, 8), (14, 12, 21, 21), (3, 16, 10, 21)):
                c.create_rectangle(*P(x1, y1, x2, y2), outline=renk, width=g)
        elif tur == "icerik":
            c.create_rectangle(*P(3, 5, 21, 19), outline=renk, width=g)
            c.create_polygon(*P(10, 9, 15, 12, 10, 15), fill=renk, outline=renk)
        elif tur == "plan":
            c.create_rectangle(*P(3, 4, 21, 21), outline=renk, width=g)
            c.create_line(*P(3, 9, 21, 9), fill=renk, width=g)
            c.create_line(*P(8, 2, 8, 6), fill=renk, width=g)
            c.create_line(*P(16, 2, 16, 6), fill=renk, width=g)
        elif tur == "ses":
            c.create_rectangle(*P(9, 3, 15, 14), outline=renk, width=g)
            c.create_arc(*P(5, 6, 19, 18), start=180, extent=180, style="arc", outline=renk, width=g)
            c.create_line(*P(12, 18, 12, 21), fill=renk, width=g)
        elif tur == "yorum":
            c.create_polygon(*P(3, 4, 21, 4, 21, 16, 9, 16, 4, 20, 5, 16, 3, 16), outline=renk, fill="", width=g)
        elif tur == "analiz":
            c.create_line(*P(3, 21, 21, 21), fill=renk, width=g)
            for x1, y1 in ((6, 13), (11, 6), (16, 10)):
                c.create_rectangle(*P(x1, y1, x1 + 3, 21), outline=renk, width=g)
        elif tur == "ayar":
            c.create_oval(*P(8, 8, 16, 16), outline=renk, width=g)
            for x1, y1, x2, y2 in ((12, 2, 12, 5), (12, 19, 12, 22), (2, 12, 5, 12), (19, 12, 22, 12),
                                   (5, 5, 7, 7), (17, 17, 19, 19), (5, 19, 7, 17), (17, 7, 19, 5)):
                c.create_line(*P(x1, y1, x2, y2), fill=renk, width=g)

    def kaydirma(ust):
        """İçeriği sığmazsa fare tekerleğiyle kayan alan. (dış çerçeve, iç çerçeve) döndürür."""
        dis = tk.Frame(ust, bg=R["bg"])
        c = tk.Canvas(dis, bg=R["bg"], highlightthickness=0, bd=0)
        sb = ttk.Scrollbar(dis, orient="vertical", command=c.yview)
        ic = tk.Frame(c, bg=R["bg"])
        pen = c.create_window(0, 0, window=ic, anchor="nw")
        c.configure(yscrollcommand=sb.set)
        c.pack(side="left", fill="both", expand=True)

        def sb_guncelle(_=None):
            c.configure(scrollregion=c.bbox("all"))
            if ic.winfo_reqheight() > c.winfo_height() + 2:
                if not sb.winfo_ismapped():
                    sb.pack(side="right", fill="y", before=c)   # önce çubuk yer alsın, içerik daralsın
            elif sb.winfo_ismapped():
                sb.pack_forget()
                c.yview_moveto(0)
        ic.bind("<Configure>", sb_guncelle)
        c.bind("<Configure>", lambda e: (c.itemconfigure(pen, width=e.width), sb_guncelle()))

        def teker(e):
            if ic.winfo_reqheight() > c.winfo_height() + 2:
                c.yview_scroll(int(-e.delta / 120) if e.delta else (1 if e.num == 5 else -1), "units")
        dis.bind("<Enter>", lambda e: (c.bind_all("<MouseWheel>", teker), c.bind_all("<Button-4>", teker),
                                       c.bind_all("<Button-5>", teker)))
        dis.bind("<Leave>", lambda e: (c.unbind_all("<MouseWheel>"), c.unbind_all("<Button-4>"),
                                       c.unbind_all("<Button-5>")))
        return dis, ic

    _kisalt_onbellek = {}

    def _kisalt_olcu(fnt, metin, genislik):
        """Metni piksel genişliğine sığacak şekilde '…' ile kısaltır (ikili arama + önbellek)."""
        anahtar = (str(fnt), metin, genislik)
        if anahtar in _kisalt_onbellek:
            return _kisalt_onbellek[anahtar]
        if fnt.measure(metin) <= genislik:
            sonuc = metin
        else:
            alt, ust = 3, len(metin)
            while alt < ust:
                orta = (alt + ust + 1) // 2
                if fnt.measure(metin[:orta] + "…") <= genislik:
                    alt = orta
                else:
                    ust = orta - 1
            sonuc = metin[:alt].rstrip() + "…"
        if len(_kisalt_onbellek) > 2000:
            _kisalt_onbellek.clear()
        _kisalt_onbellek[anahtar] = sonuc
        return sonuc

    class Grafik(tk.Canvas):
        """Tek seriden çizgi ya da yatay çubuk grafik; fareyle üzerine gelince değer kutusu gösterir.
        Renk tek: grafik mavisi. Izgara ve eksen yazıları soluk, değerler metin renginde."""

        def __init__(self, ust, yukseklik=220, bos_metin="Henüz veri yok"):
            super().__init__(ust, height=px(yukseklik), bg=zemin(ust), highlightthickness=0, bd=0)
            self._z = zemin(ust)
            self._tur, self._veri, self._bos, self._noktalar = None, None, bos_metin, []
            self._ipucu, self._p, self._imza = None, 1.0, None
            self._bekleyen = None
            self._son_boy = None
            self.bind("<Configure>", self._boyut_degisti)
            self.bind("<Motion>", self._hareket)
            self.bind("<Leave>", lambda e: self._ipucu_sil())
            self.bind("<Button-1>", lambda e: _grafik_tikla(self, e))

        # --- veri ---
        def cizgi(self, etiketler, degerler, bicim=str, ipucu=None, y_bicim=None, x_bicim=None, y_ust=None):
            self._tur = "cizgi"
            self._veri = dict(e=etiketler, d=degerler, b=bicim, i=ipucu or (lambda i: f"{etiketler[i]}  ·  "
                                                                          f"{bicim(degerler[i])}"),
                              yb=y_bicim or bicim, xb=x_bicim, yu=y_ust)
            self._belir()

        def cubuk(self, etiketler, degerler, bicim=str, ipucu=None, referans=None, ref_etiket="", tikla=None):
            self._tur = "cubuk"
            self._veri = dict(e=etiketler, d=degerler, b=bicim, i=ipucu, r=referans, re=ref_etiket, t=tikla)
            self._belir()

        def _belir(self):
            """Veri değiştiyse grafiği soldan sağa çizerek / çubukları büyüterek gösterir."""
            imza = (self._tur, tuple(self._veri["d"]), tuple(map(str, self._veri["e"])))
            if imza == self._imza:
                self._ciz()
                return
            self._imza = imza

            def adim(t):
                self._p = t
                self._ciz()
            anim(("grafik", id(self)), 650, adim)

        def bos(self, metin=None):
            self._tur, self._veri, self._imza = None, None, None
            if metin:
                self._bos = metin
            self._ciz()

        # --- çizim ---
        def _boyut_degisti(self, e):
            """Boyut değişimlerini birleştirir: pencere açılırken onlarca <Configure> gelse de tek çizim yapılır,
            aynı boyuta tekrar gelirse hiç çizilmez (yerleşim döngüsü arayüzü dondurmasın)."""
            boy = (e.width, e.height)
            if boy == self._son_boy:
                return
            self._son_boy = boy
            if self._bekleyen:
                try:
                    self.after_cancel(self._bekleyen)
                except Exception:
                    pass
            self._bekleyen = self.after(60, self._ertelenmis_ciz)

        def _ertelenmis_ciz(self):
            self._bekleyen = None
            self._ciz()

        def _ciz(self):
            self.delete("all")
            self._noktalar = []
            w, h = self.winfo_width(), int(super().cget("height"))
            if w < 50:
                return
            if not self._veri or not self._veri["d"]:
                self.create_text(w / 2, h / 2, text=self._bos, fill=R["soluk"], font=F(9), width=w - px(40),
                                 justify="center")
                return
            (self._cizgi_ciz if self._tur == "cizgi" else self._cubuk_ciz)(w, h)

        def _cizgi_ciz(self, w, h):
            v = self._veri
            d = v["d"]
            ust = v["yu"] or max(max(d), 1)
            # 'yuvarlak' bir üst sınır: 4 eşit ızgara aralığı
            adim = ust / 4
            kuvvet = 10 ** max(0, len(str(int(adim))) - 1)
            adim = max(1, -(-adim // kuvvet) * kuvvet) if not v["yu"] else adim
            ust = adim * 4
            yazi_gen = max(tkfont.Font(family=F(8)[0], size=8).measure(v["yb"](ust)), px(18)) + px(8)
            sol, sag, ust_k, alt = yazi_gen, w - px(8), px(10), h - px(24)
            for i in range(5):
                y = alt - (alt - ust_k) * i / 4
                self.create_line(sol, y, sag, y, fill=R["kenar"])
                self.create_text(sol - px(6), y, text=v["yb"](adim * i), anchor="e", fill=R["soluk"], font=F(8))
            n = len(d)
            xs = [sol + (sag - sol) * (i / max(1, n - 1)) for i in range(n)]
            ys = [alt - (alt - ust_k) * (min(x, ust) / ust) for x in d]
            # x etiketleri: baş, orta, son (çakışmasın)
            for i in sorted({0, n // 2, n - 1}):
                etk = v["xb"](v["e"][i]) if v["xb"] else v["e"][i]
                self.create_text(xs[i], alt + px(12), text=etk, fill=R["soluk"], font=F(8),
                                 anchor="w" if i == 0 else "e" if i == n - 1 else "center")
            if n == 1:
                self.create_oval(xs[0] - px(4), ys[0] - px(4), xs[0] + px(4), ys[0] + px(4), fill=R["grafik"],
                                 outline="")
            else:
                # çizgi soldan sağa çizilerek gelir (self._p: 0..1)
                son = self._p * (n - 1)
                k = int(son)
                pts = list(zip(xs[:k + 1], ys[:k + 1]))
                if k < n - 1:
                    f_ = son - k
                    pts.append((xs[k] + (xs[k + 1] - xs[k]) * f_, ys[k] + (ys[k + 1] - ys[k]) * f_))
                if len(pts) >= 2:
                    self.create_line(*[c for xy in pts for c in xy], fill=R["grafik"], width=max(2, px(2)),
                                     capstyle="round", joinstyle="round")
            self._noktalar = [(x, y, i) for i, (x, y) in enumerate(zip(xs, ys))]
            self._alan = (sol, ust_k, sag, alt)

        def _cubuk_ciz(self, w, h):
            v = self._veri
            d, n = v["d"], len(v["d"])
            ust = max(max(d), v["r"] or 0, 1e-9)
            etiket_gen = min(int(w * 0.38), px(260))
            deger_gen = max(tkfont.Font(family=F(9)[0], size=9).measure(v["b"](x)) for x in d) + px(10)
            sol, sag = etiket_gen + px(10), w - deger_gen
            satir = min(px(30), (h - px(8)) / n)
            kal = max(px(8), min(px(14), satir * 0.55))
            fnt = tkfont.Font(family=F(9)[0], size=9)
            if v["r"]:     # referans çizgisi çubukların arkasında kalsın
                rx = sol + (sag - sol) * (v["r"] / ust)
                self.create_line(rx, 0, rx, px(4) + satir * n, fill=R["soluk2"], dash=(3, 3))
                self.create_text(rx, px(4) + satir * n + px(2), text=v["re"], anchor="n", fill=R["soluk"],
                                 font=F(8))
            for i, x in enumerate(d):
                yo = px(4) + satir * i + satir / 2
                etk = str(v["e"][i])
                etk = _kisalt_olcu(fnt, etk, etiket_gen)
                self.create_text(0, yo, text=etk, anchor="w", fill=R["yazi"], font=F(9))
                bx = sol + (sag - sol) * (x / ust) * self._p
                if bx - sol >= 2:
                    yuvarlak(self, sol, yo - kal / 2, max(bx, sol + kal), yo + kal / 2, min(px(4), kal / 2),
                             fill=R["grafik"], outline="", tags=(f"c{i}",))
                self.create_text(max(bx, sol) + px(6), yo, text=v["b"](x), anchor="w", fill=R["yazi"], font=F(9))
                self._noktalar.append((0, yo - satir / 2, yo + satir / 2, i))
            self.config(height=int(px(4) + satir * n + (px(20) if v["r"] else px(6))))

        # --- fare ---
        def _ipucu_sil(self):
            self.delete("ipucu")

        def _ipucu_goster(self, x, y, metin):
            self._ipucu_sil()
            t = self.create_text(0, 0, text=metin, anchor="nw", fill=R["ana_yazi"], font=F(9), tags="ipucu")
            x1, y1, x2, y2 = self.bbox(t)
            gw, gh = x2 - x1 + px(16), y2 - y1 + px(10)
            w = self.winfo_width()
            bx = min(max(0, x + px(12)), w - gw)
            by = max(0, y - gh - px(8))
            arka = yuvarlak(self, bx, by, bx + gw, by + gh, px(6), fill=R["ana_btn"], outline="", tags="ipucu")
            self.coords(t, bx + px(8), by + px(5))
            self.tag_raise(t, arka)

        def _hareket(self, e):
            if not self._veri or not self._noktalar or self._p < 1:
                return
            v = self._veri
            if self._tur == "cizgi":
                x, y, i = min(self._noktalar, key=lambda p_: abs(p_[0] - e.x))
                self._ipucu_sil()
                sol, ust_k, sag, alt = self._alan
                self.create_line(x, ust_k, x, alt, fill=R["cizgi"], tags="ipucu")
                self.create_oval(x - px(5), y - px(5), x + px(5), y + px(5), fill=R["grafik"], outline=self._z,
                                 width=2, tags="ipucu")
                self._ipucu_goster(x, y, v["i"](i))
            else:
                for _, y1, y2, i in self._noktalar:
                    if y1 <= e.y <= y2:
                        metin = v["i"](i) if v["i"] else f"{v['e'][i]}\n{v['b'](v['d'][i])}"
                        self._ipucu_goster(e.x, y1, metin)
                        self.config(cursor="hand2" if v.get("t") else "")
                        return
                self._ipucu_sil()

    def _grafik_tikla(g, e):
        v = g._veri
        if g._tur == "cubuk" and v and v.get("t"):
            for _, y1, y2, i in g._noktalar:
                if y1 <= e.y <= y2:
                    v["t"](i)
                    return

    AYLAR = ["Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"]

    def gun_etiket(iso):
        try:
            d = datetime.date.fromisoformat(iso)
            return f"{d.day} {AYLAR[d.month - 1]}"
        except ValueError:
            return iso

    # ======================================================================
    # İSKELET: üst çubuk | yan menü | ana alan   (YouTube Studio düzeni)
    # ======================================================================
    ust_cubuk = tk.Frame(p, bg=R["kart"], height=px(60))
    ust_cubuk.pack(side="top", fill="x")
    ust_cubuk.pack_propagate(False)
    tk.Frame(p, bg=R["kenar"], height=1).pack(side="top", fill="x")
    govde_ana = tk.Frame(p, bg=R["bg"])
    govde_ana.pack(side="top", fill="both", expand=True)
    yan = tk.Frame(govde_ana, bg=R["yan"], width=px(232))
    yan.pack(side="left", fill="y")
    yan.pack_propagate(False)
    tk.Frame(govde_ana, bg=R["kenar"], width=1).pack(side="left", fill="y")
    ana = tk.Frame(govde_ana, bg=R["bg"])
    ana.pack(side="left", fill="both", expand=True)

    # --- üst çubuk: logo · (üretim göstergesi) · otomatik yayın · kanal ---
    lc = tk.Canvas(ust_cubuk, width=px(30), height=px(21), bg=R["kart"], highlightthickness=0)
    lc.pack(side="left", padx=(px(24), px(10)))
    yuvarlak(lc, 0, 0, px(30), px(21), px(6), fill=R["marka"], outline="")
    lc.create_polygon(px(12), px(6), px(12), px(15), px(20), px(10.5), fill="white", outline="")
    tk.Label(ust_cubuk, text="Shorts Stüdyo", bg=R["kart"], fg=R["yazi"], font=F(15, "orta")).pack(side="left")

    ust_avatar = tk.Canvas(ust_cubuk, width=px(32), height=px(32), bg=R["kart"], highlightthickness=0)
    ust_avatar.pack(side="right", padx=(px(14), px(24)))

    def avatar_ciz(c, boy, harf):
        c.delete("all")
        c.create_oval(1, 1, boy - 1, boy - 1, fill="#3E2723", outline="")
        c.create_text(boy / 2, boy / 2, text=harf, fill="#E9DCC0",
                      font=F(max(8, int(boy / olcek * (0.28 if len(harf) < 2 else 0.2))), "orta"))
    AVATAR = ("B" if AKTIF_PROFIL == "tr" else AKTIF_PROFIL.upper()[:2])
    avatar_ciz(ust_avatar, px(32), AVATAR)

    BETA_BG, BETA_FG = ("#7A4A00", "#FFD48A") if koyu_tema else ("#FFF1D6", "#9A5B00")

    def beta(ust, bg=None, kucuk=False):
        """Yeni ve henüz denenmekte olan özellikler için küçük 'BETA' etiketi."""
        return tk.Label(ust, text="BETA", bg=BETA_BG, fg=BETA_FG, font=F(7 if kucuk else 8, "orta"),
                        padx=px(5), pady=0)

    def hap(ust, metin="", bg=R["kart2"], fg=R["soluk"]):
        """Studio'daki yuvarlak durum etiketi (chip)."""
        f = tk.Frame(ust, bg=bg, padx=px(14), pady=px(7), cursor="hand2")
        nokta = tk.Label(f, text="●", bg=bg, fg=fg, font=F(8), cursor="hand2")
        nokta.pack(side="left")
        yazi_ = tk.Label(f, text=metin, bg=bg, fg=fg, font=F(10, "orta"), cursor="hand2")
        yazi_.pack(side="left", padx=(px(6), 0))

        def ayarla(metin_=None, bg_=None, fg_=None):
            for w in (f, nokta, yazi_):
                if bg_:
                    w.config(bg=bg_)
            for w in (nokta, yazi_):
                if fg_:
                    w.config(fg=fg_)
            if metin_ is not None:
                yazi_.config(text=metin_)

        def bagla(komut):
            for w in (f, nokta, yazi_):
                w.bind("<Button-1>", lambda e: komut())
        f.ayarla, f.bagla, f.nokta = ayarla, bagla, nokta
        return f

    tema_btn = tk.Canvas(ust_cubuk, width=px(36), height=px(36), bg=R["kart"], highlightthickness=0, cursor="hand2")

    def tema_btn_ciz(ust_mu=False):
        c, k_ = tema_btn, px(36)
        c.delete("all")
        if ust_mu:
            c.create_oval(1, 1, k_ - 1, k_ - 1, fill=R["kart2"], outline="")
        m, r_ = k_ / 2, px(8)
        if koyu_tema:      # koyudayken güneş: "açığa geç"
            c.create_oval(m - px(4.5), m - px(4.5), m + px(4.5), m + px(4.5), outline=R["yazi"], width=max(1, px(1.6)))
            import math
            for i in range(8):
                a_ = i * math.pi / 4
                c.create_line(m + math.cos(a_) * px(7.5), m + math.sin(a_) * px(7.5), m + math.cos(a_) * px(10),
                              m + math.sin(a_) * px(10), fill=R["yazi"], width=max(1, px(1.6)))
        else:              # açıktayken ay: "koyuya geç"
            c.create_oval(m - r_, m - r_, m + r_, m + r_, fill=R["yazi"], outline="")
            c.create_oval(m - r_ + px(5), m - r_ - px(3), m + r_ + px(5), m + r_ - px(3),
                          fill=R["kart2"] if ust_mu else R["kart"], outline="")
    tema_btn_ciz()
    tema_btn.bind("<Enter>", lambda e: tema_btn_ciz(True))
    tema_btn.bind("<Leave>", lambda e: tema_btn_ciz(False))
    tema_btn.bind("<Button-1>", lambda e: tema_degistir("acik" if koyu_tema else "koyu"))

    def tema_degistir(yeni, sor=False):
        if durum["mesgul"]:
            messagebox.showinfo("Tema", "Şu an bir video hazırlanıyor. Tema, iş bitince değiştirilebilir.")
            return
        ayar["tema"] = yeni
        ayar_yaz(ayar)
        if tema_koyu_mu(ayar) == koyu_tema:
            return
        if sor and not messagebox.askyesno("Tema", "Yeni tema için program yeniden açılacak. Şimdi açılsın mı?"):
            return
        try:
            subprocess.Popen([sys.executable, os.path.abspath(__file__)], cwd=BASE)
        except Exception as e:
            messagebox.showerror("Tema", f"Program yeniden açılamadı: {e}\nElle kapatıp açarsan tema uygulanır.")
            return
        p.destroy()
        os._exit(0)

    # --- kanal seçici (logonun yanında) ---
    tk.Frame(ust_cubuk, bg=R["kenar"], width=1, height=px(26)).pack(side="left", padx=(px(18), px(14)))
    kanal_hap = hap(ust_cubuk, f"{profil_adi()}  ▾", bg=R["kart2"], fg=R["yazi"])
    kanal_hap.nokta.config(fg=R["marka"] if AKTIF_PROFIL == "tr" else R["vurgu"])
    kanal_hap.pack(side="left")
    kanal_menu = tk.Menu(p, tearoff=0, bg=R["kart"], fg=R["yazi"], activebackground=R["secili"],
                         activeforeground=R["yazi"], bd=0, font=F(10))

    def kanal_degistir(pid):
        if pid == AKTIF_PROFIL:
            return
        if durum["mesgul"]:
            messagebox.showinfo("Kanal", "Şu an bir video hazırlanıyor. Kanal, iş bitince değiştirilebilir.")
            return
        profil_sec(pid)
        try:
            subprocess.Popen([sys.executable, os.path.abspath(__file__)], cwd=BASE)
        except Exception as e:
            messagebox.showerror("Kanal", f"Program yeniden açılamadı: {e}\nKapatıp açarsan seçtiğin kanalla açılır.")
            return
        p.destroy()
        os._exit(0)

    def kanal_menusu_ac():
        kanal_menu.delete(0, "end")
        for pid, bilgi in profiller_oku()["profiller"].items():
            dil_ = {"tr": "Türkçe", "en": "İngilizce"}.get(bilgi.get("dil"), bilgi.get("dil", ""))
            kanal_menu.add_command(label=("✓  " if pid == AKTIF_PROFIL else "     ") + f"{bilgi.get('ad', pid)}  ·  {dil_}"
                                   + ("  ·  BETA" if pid != "tr" else ""),
                                   command=lambda pid_=pid: kanal_degistir(pid_))
        kanal_menu.tk_popup(kanal_hap.winfo_rootx(), kanal_hap.winfo_rooty() + kanal_hap.winfo_height() + px(4))
    kanal_hap.bagla(kanal_menusu_ac)

    oto_hap = hap(ust_cubuk, "Otomatik yayın kapalı")
    oto_hap.pack(side="right")
    tema_btn.pack(side="right", padx=(0, px(10)))
    oto_hap.bagla(lambda: sayfa_goster("plan"))
    uretim_hap = hap(ust_cubuk, "", bg=R["secili"], fg=R["vurgu"])
    uretim_hap.bagla(lambda: uw_goster())

    # --- yan menü: kanal kartı + sayfalar ---
    kanal_f = tk.Frame(yan, bg=R["yan"])
    kanal_f.pack(fill="x", pady=(px(22), px(18)))
    yan_avatar = tk.Canvas(kanal_f, width=px(96), height=px(96), bg=R["yan"], highlightthickness=0)
    yan_avatar.pack()
    avatar_ciz(yan_avatar, px(96), AVATAR)
    tk.Label(kanal_f, text="Kanalınız", bg=R["yan"], fg=R["yazi"], font=F(11, "orta")).pack(pady=(px(10), 0))
    yt_ad = tk.Label(kanal_f, text=ayar.get("hedef_kanal", ""), bg=R["yan"], fg=R["soluk"], font=F(9),
                     wraplength=px(200), justify="center")
    yt_ad.pack()

    nav = {}
    nav_rozetler = {}

    def nav_rozet(sayi_, anahtar="yorumlar"):
        """Menüde sayaç rozeti (ör. onay bekleyen yorum sayısı)."""
        rz = nav_rozetler.get(anahtar)
        if not rz:
            return
        if sayi_:
            rz.config(text=str(sayi_))
            rz.pack(side="right", padx=(0, px(16)), before=nav[anahtar][2])
        else:
            rz.pack_forget()

    def nav_ekle(anahtar, ikon, metin, alta=False, beta_=False):
        f = tk.Frame(yan, bg=R["yan"], cursor="hand2", height=px(48))
        f.pack(fill="x", side="bottom" if alta else "top")
        f.pack_propagate(False)
        cubuk = tk.Frame(f, bg=R["yan"], width=px(3))
        cubuk.pack(side="left", fill="y")
        l0 = tk.Canvas(f, width=px(22), height=px(22), bg=R["yan"], highlightthickness=0, cursor="hand2")
        l0.pack(side="left", padx=(px(21), 0))
        rozet = tk.Label(f, text="", bg=R["vurgu"], fg=R["vurgu_yazi"], font=F(8, "orta"), padx=px(6))
        nav_rozetler[anahtar] = rozet
        lbl = tk.Label(f, text=metin, bg=R["yan"], fg=R["yazi"], font=F(10), anchor="w", cursor="hand2")
        if beta_:
            beta(f, kucuk=True).pack(side="right", padx=(0, px(14)))
        lbl.pack(side="left", fill="x", expand=True, padx=(px(20), 0))
        l0.ikon = ikon

        def boya(renk):
            for w in (f, l0, lbl):
                w.config(bg=renk)   # rozet kendi rengini korur

        def gir(_):
            if durum["sayfa"] != anahtar:
                boya(R["yan_hover"])

        def cik(_):
            if durum["sayfa"] != anahtar:
                boya(R["yan"])
        for w in (f, l0, lbl):
            w.bind("<Button-1>", lambda e: (sayfa_goster(anahtar), anim(
                ("navflash", anahtar), 320, lambda t: boya(karis(R["cizgi"], R["yan_hover"], t)))))
            w.bind("<Enter>", gir)
            w.bind("<Leave>", cik)
        nav[anahtar] = (f, l0, lbl, cubuk, boya)

    # yan menü altı: YouTube bağlantısı
    yt_kutu = tk.Frame(yan, bg=R["yan"], padx=px(20), pady=px(14))
    yt_kutu.pack(side="bottom", fill="x")
    ysat = tk.Frame(yt_kutu, bg=R["yan"])
    ysat.pack(fill="x")
    yt_nokta = tk.Label(ysat, text="●", bg=R["yan"], fg=R["soluk2"], font=F(9))
    yt_nokta.pack(side="left")
    yt_durum_lbl = tk.Label(ysat, text="YouTube bağlı değil", bg=R["yan"], fg=R["soluk"], font=F(9),
                            anchor="w", justify="left", wraplength=px(170))
    yt_durum_lbl.pack(side="left", padx=(px(6), 0), fill="x")
    yt_baglan_btn = Dugme(yt_kutu, "Bağlan", tur="hayalet", boy="kucuk")
    yt_baglan_btn.pack(fill="x", pady=(px(10), 0))
    tk.Frame(yan, bg=R["kenar"], height=1).pack(side="bottom", fill="x")

    # başlık
    bas_f = tk.Frame(ana, bg=R["bg"])
    bas_f.pack(fill="x", padx=px(36), pady=(px(26), 0))
    bas_sat = tk.Frame(bas_f, bg=R["bg"])
    bas_sat.pack(anchor="w")
    sayfa_baslik = tk.Label(bas_sat, text="", bg=R["bg"], fg=R["yazi"], font=(YAZI, 21, "bold"))
    sayfa_baslik.pack(side="left")
    baslik_beta = beta(bas_sat)
    BETA_SAYFALAR = {"analiz", "yorumlar"}
    sayfa_alt = tk.Label(bas_f, text="", bg=R["bg"], fg=R["soluk"], font=F(10))
    sayfa_alt.pack(anchor="w")

    # ======================================================================
    # ÜRETİM PENCERESİ (Studio'daki "yükleme" penceresi gibi)
    # ======================================================================
    uw = tk.Toplevel(p)
    uw.withdraw()
    uw.title("Shorts Stüdyo")
    uw.configure(bg=R["kart"])
    uw.transient(p)
    if os.path.exists(yol("simge.ico")):
        try:
            uw.iconbitmap(yol("simge.ico"))
        except Exception:
            pass
    uw.protocol("WM_DELETE_WINDOW", lambda: uw_gizle())
    uw_tema = {"yapildi": False}

    uw_ust = tk.Frame(uw, bg=R["kart"], padx=px(24), pady=px(16))
    uw_ust.pack(fill="x")
    uw_baslik = tk.Label(uw_ust, text="Shorts yayınla", bg=R["kart"], fg=R["yazi"], font=F(16, "orta"))
    uw_baslik.pack(side="left")
    uw_kapat = tk.Label(uw_ust, text="✕", bg=R["kart"], fg=R["soluk"], font=F(14), cursor="hand2")
    uw_kapat.pack(side="right")
    uw_kapat.bind("<Button-1>", lambda e: uw_gizle())
    uw_alt = tk.Label(uw_ust, text="", bg=R["kart"], fg=R["soluk"], font=F(9))
    uw_alt.pack(side="right", padx=px(16))
    tk.Frame(uw, bg=R["kenar"], height=1).pack(fill="x")

    ADIMLAR = ["Hikâye", "Seslendirme", "Video", "Yayın"]
    adim_c = tk.Canvas(uw, height=px(60), bg=R["kart"], highlightthickness=0)
    adim_c.pack(fill="x")
    adim_c.bind("<Configure>", lambda e: chip_guncelle(bar["value"]))
    tk.Frame(uw, bg=R["kenar"], height=1).pack(fill="x")

    uw_alt_cubuk = tk.Frame(uw, bg=R["kart"], padx=px(24), pady=px(14))
    uw_alt_cubuk.pack(side="bottom", fill="x")
    tk.Frame(uw, bg=R["kenar"], height=1).pack(side="bottom", fill="x")
    detay_btn = baglanti(uw_alt_cubuk, "Ayrıntılı kayıt", lambda: detay_ac())
    detay_btn.config(fg=R["soluk"])
    detay_btn.pack(side="left")
    uw_sag_btn = tk.Frame(uw_alt_cubuk, bg=R["kart"])
    uw_sag_btn.pack(side="right")
    iptal_btn = Dugme(uw_sag_btn, "İptal et", tur="tehlike")
    iptal_btn.config(state="disabled")
    onay_tekrar_btn = Dugme(uw_sag_btn, "Yeniden yaz", tur="hayalet")
    onay_btn = Dugme(uw_sag_btn, "Onayla ve devam et", tur="yesil")
    son_oynat_btn = Dugme(uw_sag_btn, "Oynat", tur="hayalet")
    son_klasor_btn = Dugme(uw_sag_btn, "Klasörde göster", tur="hayalet")
    son_yt_btn = Dugme(uw_sag_btn, "YouTube'da aç", tur="yesil")
    son_kapat_btn = Dugme(uw_sag_btn, "Kapat", tur="ana", command=lambda: uw_gizle())

    def uw_butonlar(*gosterilecek):
        for b in uw_sag_btn.winfo_children():
            b.pack_forget()
        for b in gosterilecek:
            b.pack(side="left", padx=(px(8), 0))

    uw_govde = tk.Frame(uw, bg=R["kart"], padx=px(24), pady=px(20))
    uw_govde.pack(fill="both", expand=True)
    uw_sag = tk.Frame(uw_govde, bg=R["kart"])
    uw_sag.pack(side="right", fill="y", padx=(px(26), 0))
    uw_resim = tk.Label(uw_sag, text="Video önizlemesi\nvideo hazır olunca", bg=R["onizleme"], fg=R["soluk2"],
                        font=F(9), width=24, height=17)
    uw_resim.pack()
    uw_sol = tk.Frame(uw_govde, bg=R["kart"])
    uw_sol.pack(side="left", fill="both", expand=True)
    etiket(uw_sol, "Başlık", soluk=True, boyut=9).pack(anchor="w")
    uw_baslik_var = tk.StringVar(value="")
    uw_baslik_giris, uw_baslik_sayac = baslik_kutusu(uw_sol, uw_baslik_var, font=F(12, "orta"), state="readonly")
    uw_baslik_giris.pack(fill="x", pady=(px(4), 0))
    uw_baslik_sayac.pack(fill="x", pady=(px(2), px(8)))
    uw_hikaye_lbl = etiket(uw_sol, "Hikâye", soluk=True, boyut=9)
    uw_hikaye_lbl.pack(anchor="w")
    uw_durum_f = tk.Frame(uw_sol, bg=R["kart"])
    uw_durum_f.pack(side="bottom", fill="x", pady=(px(16), 0))
    s1 = tk.Frame(uw_durum_f, bg=R["kart"])
    s1.pack(fill="x", pady=(0, px(8)))
    asama_lbl = tk.Label(s1, text="Hazır", bg=R["kart"], fg=R["soluk"], font=F(9), anchor="w")
    asama_lbl.pack(side="left")
    sure_lbl = tk.Label(s1, text="", bg=R["kart"], fg=R["soluk"], font=F(9))
    sure_lbl.pack(side="right")
    yuzde_lbl = tk.Label(s1, text="", bg=R["kart"], fg=R["yazi"], font=F(9, "orta"))
    yuzde_lbl.pack(side="right", padx=(0, px(10)))
    bar = ttk.Progressbar(uw_durum_f, mode="determinate", maximum=100)
    bar.pack(fill="x")
    uw_metin_f = tk.Frame(uw_sol, bg=R["bg"], highlightthickness=1, highlightbackground=R["kenar"])
    uw_metin_f.pack(fill="both", expand=True, pady=(px(4), 0))
    uw_hikaye = tk.Text(uw_metin_f, font=F(10), bg=R["bg"], fg=R["metin2"], insertbackground=R["yazi"], bd=0,
                        padx=px(14), pady=px(12), wrap="word", spacing2=4, highlightthickness=0, height=10)
    uw_hikaye.pack(fill="both", expand=True)
    log_kutu = tk.Text(uw_metin_f, font=("Consolas", 9), bg=R["bg"], fg=R["metin2"], insertbackground=R["yazi"],
                       bd=0, padx=px(14), pady=px(12), wrap="word", highlightthickness=0, height=10)
    log_kutu.tag_config("hata", foreground=R["kirmizi"])
    log_kutu.tag_config("ok", foreground=R["yesil2"])
    log_kutu.tag_config("uyari", foreground=R["sari"])

    def uw_hikaye_yaz(metin, duzenlenebilir=False):
        uw_hikaye.config(state="normal")
        uw_hikaye.delete("1.0", "end")
        uw_hikaye.insert("1.0", metin)
        n = len(metin.split())
        if n:
            sn = n / (2.6 if durum.get("uw_fmt") == "kisa" else 2.5)
            uw_hikaye_lbl.config(text=f"Hikâye · {n} kelime · ~{int(sn // 60)}:{int(sn % 60):02d}")
        else:
            uw_hikaye_lbl.config(text="Hikâye")
        uw_hikaye.config(state="normal" if duzenlenebilir else "disabled",
                         bg=R["kart"] if duzenlenebilir else R["bg"])
        uw_metin_f.config(highlightbackground=R["vurgu"] if duzenlenebilir else R["kenar"])

    def detay_ac(goster=None):
        acik = log_kutu.winfo_ismapped()
        if goster is None:
            goster = not acik
        if goster and not acik:
            uw_hikaye.pack_forget()
            log_kutu.pack(fill="both", expand=True)
            detay_btn.config(text="Hikâyeyi göster")
        elif not goster and acik:
            log_kutu.pack_forget()
            uw_hikaye.pack(fill="both", expand=True)
            detay_btn.config(text="Ayrıntılı kayıt")

    def uw_goster():
        if not uw.winfo_ismapped():
            g_, y_ = px(980), min(px(640), p.winfo_screenheight() - px(100))
            x_ = p.winfo_rootx() + max(0, (p.winfo_width() - g_) // 2)
            y0 = p.winfo_rooty() + max(0, (p.winfo_height() - y_) // 2)
            uw.geometry(f"{g_}x{y_}+{x_}+{y0}")
            uw.minsize(px(760), px(520))
            pencere_belir(uw)
            uw.deiconify()
            if not uw_tema["yapildi"]:
                pencere_koyu_baslik(uw, koyu_tema)
                uw_tema["yapildi"] = True
        uw.lift()
        uw.focus_force()

    def uw_gizle():
        if durum.get("onay_kapat"):        # hikâye onayı beklenirken pencere kapatılırsa: iptal
            iptal_et()
        uw.withdraw()

    def uw_hazirla(baslik_, fmt):
        durum["uw_fmt"] = fmt
        uw_baslik.config(text=baslik_)
        uw.title(baslik_)
        uw_alt.config(text=f"{ayar.get('g_ses', 'Enceladus')}  ·  {1 + int(ayar.get('hiz', 15)) / 100:.2f}x  ·  "
                           + (FORMATLAR["senaryo"] if format_senaryo(ayar) else
                              f"{ARKAPLANLAR.get(ayar.get('arkaplan'), '')}"))
        uw_baslik_var.set("Yazılıyor..." if fmt in ("kisa", "uzun") else "")
        uw_hikaye_yaz("")
        detay_ac(False)
        uw_resim.config(image="", text="Video önizlemesi\nvideo hazır olunca", width=24, height=17)
        uw_butonlar(iptal_btn)

    log_dosya = os.path.join(GECICI, "son_islem_log.txt")

    def log(m):
        try:
            with open(log_dosya, "a", encoding="utf-8") as f_:
                f_.write(f"{datetime.datetime.now():%H:%M:%S} {m}\n")
        except OSError:
            pass

        def yaz():
            et = ("hata" if "[X]" in m else "ok" if "[✓]" in m else "uyari" if "[!]" in m or "[~]" in m else None)
            log_kutu.insert("end", m + "\n", et)
            log_kutu.see("end")
            if et == "hata":
                detay_ac(True)
        ui(yaz)

    def chip_guncelle(yuzde):
        """Adım çubuğu: ✓ biten · mavi halka süren · gri bekleyen."""
        mod = durum["mod"]
        idx = 0 if yuzde < 15 else 1 if yuzde < 32 else 2 if yuzde < 90 else 3
        if mod == "yukle":
            idx = 3
        c = adim_c
        c.delete("all")
        durum["nabiz"] = None
        w = max(c.winfo_width(), px(600))
        h = px(60)
        sol, sag_ = px(24), w - px(24)
        olcu = [tkfont.Font(family=F(10)[0], size=10).measure(a) + px(34) for a in ADIMLAR]
        bosluk = (sag_ - sol - sum(olcu)) / max(1, len(ADIMLAR) - 1)
        x = sol
        r = px(12)
        for i, ad_ in enumerate(ADIMLAR):
            atlandi = (mod == "yukle" and i < 3) or (i == 3 and not durum.get("yukleme_var"))
            bitti = not atlandi and (yuzde >= 100 or i < idx)
            suruyor = not atlandi and not bitti and i == idx and durum["mesgul"]
            cy = h / 2
            if bitti:
                c.create_oval(x, cy - r, x + 2 * r, cy + r, fill=R["vurgu"], outline="")
                c.create_text(x + r, cy, text="✓", fill=R["vurgu_yazi"], font=F(9, "orta"))
                renk = R["yazi"]
            elif suruyor:
                durum["nabiz"] = (x + r, cy, r)
                c.create_oval(x + 1, cy - r + 1, x + 2 * r - 1, cy + r - 1, outline=R["vurgu"], width=2)
                c.create_text(x + r, cy, text=str(i + 1), fill=R["vurgu"], font=F(9, "orta"))
                renk = R["yazi"]
            else:
                c.create_oval(x + 1, cy - r + 1, x + 2 * r - 1, cy + r - 1, outline=R["cerceve"], width=2)
                c.create_text(x + r, cy, text="–" if atlandi else str(i + 1), fill=R["soluk2"], font=F(9))
                renk = R["soluk2"]
            c.create_text(x + 2 * r + px(8), cy, text=ad_, anchor="w", fill=renk,
                          font=F(10, "orta") if suruyor else F(10))
            x2 = x + olcu[i]
            if i < len(ADIMLAR) - 1:
                c.create_line(x2 + px(4), cy, x2 + bosluk - px(4), cy, width=2,
                              fill=R["vurgu"] if bitti else R["kenar"])
            x = x2 + bosluk

    def nabiz_dongu():
        """Süren adımın çevresinde genişleyip sönen halka ve üst çubuktaki yanıp sönen nokta."""
        if durum["mesgul"] and anim_acik():
            t = (time.perf_counter() % 1.4) / 1.4
            adim_c.delete("nabiz")
            nb = durum.get("nabiz")
            if nb and uw.winfo_ismapped():
                x_, y_, r_ = nb
                rr = r_ + px(2) + px(7) * t
                adim_c.create_oval(x_ - rr, y_ - rr, x_ + rr, y_ + rr, outline=karis(R["vurgu"], R["kart"], t),
                                   width=2, tags="nabiz")
            import math
            uretim_hap.nokta.config(fg=karis(R["secili"], R["vurgu"], 0.5 + 0.5 * math.sin(t * 2 * math.pi)))
            p.after(40, nabiz_dongu)
        else:
            adim_c.delete("nabiz")
            p.after(400, nabiz_dongu)
    p.after(400, nabiz_dongu)

    def asama(ad, yuzde):
        def guncelle():
            if ad:
                asama_lbl.config(text=ad, fg=R["yazi"])
            if yuzde is not None:
                eski = float(bar["value"] or 0)
                anim("ilerleme", 450 if yuzde > eski else 0, lambda t: bar.configure(value=eski + (yuzde - eski) * t))
                yuzde_lbl.config(text=f"%{int(yuzde)}")
                chip_guncelle(yuzde)
            if durum["mesgul"]:
                uretim_hap.ayarla(f"{(ad or asama_lbl.cget('text'))[:34]}  ·  "
                                  f"%{int(yuzde if yuzde is not None else bar['value'])}")
        ui(guncelle)

    def saat():
        if durum["mesgul"]:
            g = int(time.time() - durum["bas"])
            sure_lbl.config(text=f"{g // 60}:{g % 60:02d} geçti")
            p.after(1000, saat)

    # ---------- SAYFALAR ----------
    icerik = tk.Frame(ana, bg=R["bg"])
    icerik.pack(fill="both", expand=True, padx=px(36), pady=(px(18), px(20)))
    icerik.grid_rowconfigure(0, weight=1)
    icerik.grid_columnconfigure(0, weight=1)
    sayfalar = {}
    SAYFA_BILGI = {
        "panel": ("Kanal paneli", ""),
        "plan": ("Yayın planı", "Belirlediğin saatlerde kendiliğinden yayınlanan videolar."),
        "yorumlar": ("Yorumlar", "Yorumlara Gemini ile otomatik, yoruma özel cevap. Seçili yorumun cevabını "
                                 "düzenleyip kendin de gönderebilirsin."),
        "analiz": ("Analiz", "Kanalın son 28 günü, video karşılaştırması, izlenme oranı ve en iyi yayın saati."),
        "kutup": ("İçerik", "Tüm videolar ve canlı YouTube istatistikleri. Sütun başlığına tıklayarak sırala."),
        "ses": ("Ses", "Seslendiren, anlatım tarzı ve hız."),
        "ayar": ("Ayarlar", "Video, müzik, kapanış kartı ve YouTube hesabı."),
    }

    def sayfa(anahtar):
        f = tk.Frame(icerik, bg=R["bg"])
        f.grid(row=0, column=0, sticky="nsew")
        sayfalar[anahtar] = f
        return f

    def iki_kolon(f, sol_oran=3, sag_oran=2, kaydir_sag=True):
        f.grid_columnconfigure(0, weight=sol_oran, uniform="k")
        f.grid_columnconfigure(1, weight=sag_oran, uniform="k")
        f.grid_rowconfigure(0, weight=1)
        d1, sol_ = kaydirma(f)
        d1.grid(row=0, column=0, sticky="nsew", padx=(0, px(16)))
        if kaydir_sag:
            d2, sag_ = kaydirma(f)
            d2.grid(row=0, column=1, sticky="nsew")
        else:
            sag_ = tk.Frame(f, bg=R["bg"])
            sag_.grid(row=0, column=1, sticky="nsew")
        return sol_, sag_

    def sayfa_goster(anahtar):
        onceki = durum.get("sayfa")
        durum["sayfa"] = anahtar
        sayfalar[anahtar].tkraise()
        if onceki != anahtar and onceki is not None and anim_acik():
            yeni_f = sayfalar[anahtar]

            def kay(t):
                yeni_f.grid_configure(pady=(int(px(26) * (1 - t)), 0))
                sayfa_baslik.config(fg=karis(R["bg"], R["yazi"], t))
                sayfa_alt.config(fg=karis(R["bg"], R["soluk"], t))
            kay(0)
            anim("sayfa_gecis", 260, kay)
        b, a = SAYFA_BILGI[anahtar]
        a = f"{profil_adi()}  ·  {T('Türkçe', 'İngilizce')} kanal" + (f"  ·  {a}" if a else "")
        sayfa_baslik.config(text=b)
        if anahtar in BETA_SAYFALAR:
            baslik_beta.pack(side="left", padx=(px(10), 0), pady=(px(4), 0))
        else:
            baslik_beta.pack_forget()
        sayfa_alt.config(text=a)
        if a:
            sayfa_alt.pack(anchor="w")
        else:
            sayfa_alt.pack_forget()
        for k_, (f, l0, lbl, cubuk, boya) in nav.items():
            sec = k_ == anahtar
            boya(R["yan_hover"] if sec else R["yan"])
            lbl.config(font=F(10, "orta") if sec else F(10))
            ikon_ciz(l0, l0.ikon, R["yazi"] if sec else R["soluk"])
            cubuk.config(bg=R["yan"] if anim_acik() else (R["marka"] if sec else R["yan"]))
        isaret_tasi(anahtar)
        if anahtar == "kutup":
            kutuphane_yenile()
            canli_yenile()
        if anahtar == "plan":
            plan_yenile()
        if anahtar == "panel":
            panel_yenile()
            panel_grafik_ciz()
            analiz_yenile()
        if anahtar == "yorumlar":
            yorumlar_yenile()
        if anahtar == "analiz":
            analiz_ciz()
            analiz_yenile()

    nav_isaret = tk.Frame(yan, bg=R["marka"], width=px(3))

    def isaret_tasi(anahtar):
        """Seçili sayfayı gösteren kırmızı çubuk menüde yeni sayfaya kayar."""
        if not anim_acik():
            nav_isaret.place_forget()
            return
        f = nav[anahtar][0]
        if not f.winfo_ismapped() or f.winfo_height() < 2:
            p.after(120, lambda: durum["sayfa"] == anahtar and isaret_tasi(anahtar))
            return
        hedef, yuk_ = f.winfo_y(), f.winfo_height()
        bas_ = nav_isaret.winfo_y() if nav_isaret.winfo_ismapped() else hedef
        nav_isaret.lift()
        anim("nav_isaret", 260, lambda t: nav_isaret.place(x=0, y=int(bas_ + (hedef - bas_) * t), width=px(3),
                                                           height=yuk_))

    nav_ekle("panel", "panel", "Panel")
    nav_ekle("kutup", "icerik", "İçerik")
    nav_ekle("analiz", "analiz", "Analiz", beta_=True)
    nav_ekle("yorumlar", "yorum", "Yorumlar", beta_=True)
    nav_ekle("plan", "plan", "Yayın planı")
    nav_ekle("ses", "ses", "Ses")
    tk.Frame(yan, bg=R["yan"]).pack(fill="both", expand=True)
    nav_ekle("ayar", "ayar", "Ayarlar")

    kilitli = []

    # ---------- hız kontrolü (Üret ve Ses sayfasında ortak) ----------
    hiz_var = degisken("hiz", tk.IntVar)
    hiz_etiketleri = []

    def hiz_yaz(*_):
        try:
            h = int(hiz_var.get())
        except (tk.TclError, ValueError):
            return
        for e in hiz_etiketleri:
            e.config(text=f"{1 + h / 100:.2f}x")
    hiz_var.trace_add("write", hiz_yaz)

    def hiz_kontrol(ust):
        f = tk.Frame(ust, bg=zemin(ust))
        Dugme(f, "−", boy="kucuk", genislik=px(36),
              command=lambda: hiz_var.set(max(-10, int(hiz_var.get()) - 5))).pack(side="left")
        e = tk.Label(f, text="", bg=R["kart2"], fg=R["yazi"], font=F(11, "orta"), width=6, pady=px(4))
        e.pack(side="left", padx=px(6))
        hiz_etiketleri.append(e)
        Dugme(f, "+", boy="kucuk", genislik=px(36),
              command=lambda: hiz_var.set(min(60, int(hiz_var.get()) + 5))).pack(side="left")
        Dugme(f, "Normal", tur="hayalet", boy="kucuk",
              command=lambda: hiz_var.set(15)).pack(side="left", padx=(px(8), 0))
        hiz_yaz()
        return f

    # ======================================================================
    # SAYFA: PANEL (ana sayfa)
    # ======================================================================
    _pd, pn = kaydirma(sayfa("panel"))
    _pd.pack(fill="both", expand=True)

    # --- hareketli gece gökyüzü şeridi (kanalın kapanış kartıyla aynı ruh) ---
    import math
    AFIS_UST, AFIS_ALT = "#0B1026", "#241339"      # iki temada da aynı: bir illüstrasyon
    afis = tk.Canvas(pn, height=px(150), bg=AFIS_UST, highlightthickness=0, bd=0)
    afis.pack(fill="x", pady=(0, px(16)))
    afis_d = {"w": 0, "yildiz": [], "sis": [], "kayan": None, "sonraki_kayan": time.time() + 4}

    def afis_kur(w):
        """Genişlik değişince sahneyi baştan kurar (gradyan, yıldızlar, ay, sis, yazılar)."""
        h = px(150)
        c = afis
        c.delete("all")
        afis_d.update(w=w, yildiz=[], sis=[], kayan=None)
        bant = 24
        for i in range(bant):
            c.create_rectangle(0, h * i / bant, w, h * (i + 1) / bant + 1, outline="",
                               fill=karis(AFIS_UST, AFIS_ALT, i / (bant - 1)))
        rnd = random.Random(7)
        for _ in range(max(30, w // px(14))):
            x_, y_ = rnd.uniform(0, w), rnd.uniform(0, h * 0.8)
            if x_ < px(470) and px(18) < y_ < px(122):
                continue          # yazıların arkası sade kalsın, okunurluk bozulmasın
            r_ = rnd.choice((0.8, 1, 1, 1.3, 1.7)) * max(1, px(1))
            oge = c.create_oval(x_ - r_, y_ - r_, x_ + r_, y_ + r_, outline="", fill="#ffffff")
            afis_d["yildiz"].append((oge, y_, rnd.uniform(0, 6.28), rnd.uniform(0.6, 2.2)))
        # hilal ay ve hafif parıltı
        mx, my, mr = w - px(110), px(58), px(26)
        for i, (ek, t) in enumerate(((px(26), 0.06), (px(14), 0.10), (px(6), 0.16))):
            gok = karis(AFIS_UST, AFIS_ALT, my / h)
            c.create_oval(mx - mr - ek, my - mr - ek, mx + mr + ek, my + mr + ek, outline="",
                          fill=karis(gok, "#F4E9C8", t))
        c.create_oval(mx - mr, my - mr, mx + mr, my + mr, outline="", fill="#F4E9C8")
        gok = karis(AFIS_UST, AFIS_ALT, (my - px(8)) / h)
        c.create_oval(mx - mr + px(12), my - mr - px(8), mx + mr + px(12), my + mr - px(8), outline="",
                      fill=karis(gok, "#F4E9C8", 0.10))
        # sis bulutları (alt kısımda yavaşça kayar)
        for i in range(5):
            gx = rnd.uniform(-px(200), w)
            gy = h - rnd.uniform(px(6), px(34))
            gw, gh = rnd.uniform(px(220), px(380)), rnd.uniform(px(26), px(44))
            renk = karis(AFIS_ALT, "#B9A8E0", rnd.uniform(0.06, 0.12))
            oge = c.create_oval(gx, gy - gh / 2, gx + gw, gy + gh / 2, outline="", fill=renk)
            afis_d["sis"].append([oge, gx, gy, gw, gh, rnd.uniform(4, 12)])
        # yazılar
        saat_ = datetime.datetime.now().hour
        selam = (T("İyi geceler", "Good night") if saat_ < 5 or saat_ >= 22 else T("Günaydın", "Good morning")
                 if saat_ < 12 else T("İyi günler", "Good afternoon") if saat_ < 18 else T("İyi akşamlar", "Good evening"))
        c.create_text(px(28), px(36), text=selam, anchor="w", fill="#B8B3D6", font=F(10), tags="yazi")
        c.create_text(px(28), px(68), text=("Bugün ne öğrenelim?" if nblm_mi() else T("Bugün hangi hikâye anlatılsın?", "Which story shall we tell today?")), anchor="w", fill="#FFFFFF",
                      font=F(18, "orta"), tags="yazi")
        c.create_text(px(28), px(104), text=afis_d.get("alt", ""), anchor="w", fill="#CFC9EA", font=F(10),
                      tags=("yazi", "alt"))
        afis_kare(0 if not anim_acik() else time.perf_counter())

    def afis_alt_yaz(metin):
        afis_d["alt"] = metin
        afis.itemconfig("alt", text=metin)

    def afis_kare(t):
        c = afis
        gok_ust, gok_alt = AFIS_UST, AFIS_ALT
        h = px(150)
        for oge, y_, faz, hiz_ in afis_d["yildiz"]:
            parlak = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(faz + t * hiz_))
            c.itemconfig(oge, fill=karis(karis(gok_ust, gok_alt, y_ / h), "#FFFFFF", parlak))
        if not anim_acik():
            return
        w = afis_d["w"]
        for s_ in afis_d["sis"]:
            oge, gx, gy, gw, gh, hiz_ = s_
            x_ = (gx + t * hiz_) % (w + gw) - gw
            c.coords(oge, x_, gy - gh / 2, x_ + gw, gy + gh / 2)
        # kayan yıldız: arada bir sağ üstten sol aşağı doğru
        ky = afis_d["kayan"]
        if ky is None and time.time() > afis_d["sonraki_kayan"]:
            sx, sy = random.uniform(w * 0.35, w * 0.85), random.uniform(px(6), px(40))
            afis_d["kayan"] = ky = {"x": sx, "y": sy, "bas": t, "oge": c.create_line(sx, sy, sx, sy,
                                                                                    fill="#FFFFFF", width=2)}
        if ky:
            g = (t - ky["bas"]) / 0.9
            if g >= 1:
                c.delete(ky["oge"])
                afis_d["kayan"] = None
                afis_d["sonraki_kayan"] = time.time() + random.uniform(5, 11)
            else:
                bx, by = ky["x"] - px(170) * g, ky["y"] + px(55) * g
                kuyruk = px(70) * (1 - abs(0.5 - g) * 1.2)
                c.coords(ky["oge"], bx, by, bx + kuyruk, by - kuyruk * 0.32)
                c.itemconfig(ky["oge"], fill=karis(gok_ust, "#FFFFFF", 1 - g))
        c.tag_raise("yazi")

    def afis_dongu():
        try:
            gorunur = durum["sayfa"] == "panel" and p.state() != "iconic"
        except tk.TclError:
            return
        if afis.winfo_width() > 10 and afis.winfo_width() != afis_d["w"]:
            afis_kur(afis.winfo_width())
        if gorunur and anim_acik() and afis_d["w"]:
            afis_kare(time.perf_counter())
            p.after(40, afis_dongu)       # ~25 kare/sn
        else:
            p.after(500, afis_dongu)
    p.after(300, afis_dongu)

    # --- iki büyük yayın kartı ---
    yk = tk.Frame(pn, bg=R["bg"])
    yk.pack(fill="x")
    yk.grid_columnconfigure(0, weight=1, uniform="y")
    yk.grid_columnconfigure(1, weight=1, uniform="y")
    yayin_kartlari = {}

    def yayin_karti(sutun, fmt, baslik_, alt_):
        f = yuvarlak_kart(yk, bg=R["kart"], padx=px(24),
                     pady=px(22), cursor="hand2")
        f.grid(row=0, column=sutun, sticky="nsew", padx=(0, px(16)) if sutun == 0 else 0)
        ik = tk.Canvas(f, width=px(80), height=px(80), bg=R["kart"], highlightthickness=0, cursor="hand2")
        ik.pack(side="left")
        if fmt == "kisa":
            yuvarlak(ik, px(12), 0, px(68), px(80), px(10), fill=R["marka"], outline="")
        else:
            yuvarlak(ik, 0, px(12), px(80), px(68), px(10), fill=R["uzun_ikon"], outline="")
        ik.create_polygon(px(33), px(30), px(33), px(50), px(50), px(40),
                          fill="white" if fmt == "kisa" else R["uzun_ok"], outline="")
        yaz_ = tk.Frame(f, bg=R["kart"], cursor="hand2")
        yaz_.pack(side="left", fill="x", expand=True, padx=(px(20), px(12)))
        l1 = tk.Label(yaz_, text=baslik_, bg=R["kart"], fg=R["yazi"], font=F(16, "orta"), anchor="w", cursor="hand2")
        l1.pack(anchor="w")
        l2 = tk.Label(yaz_, text=alt_, bg=R["kart"], fg=R["soluk"], font=F(10), anchor="w", cursor="hand2")
        l2.pack(anchor="w", pady=(px(4), 0))
        b = Dugme(f, "Oluştur", tur="ana", command=lambda: yayinla(fmt))
        b.pack(side="right")

        def hover(acik):
            a_, b_ = (R["kenar"], R["hover_kenar"]) if acik else (R["hover_kenar"], R["kenar"])
            anim(("kart", fmt), 160, lambda t: f.config(highlightbackground=karis(a_, b_, t)))
        for w in (f, ik, yaz_, l1, l2):
            w.bind("<Button-1>", lambda e: (anim(("kart", fmt), 420, lambda t: f.config(
                highlightbackground=karis(R["vurgu"], R["hover_kenar"], t))), yayinla(fmt)))
            w.bind("<Enter>", lambda e: hover(True))
            w.bind("<Leave>", lambda e: hover(False))
        yayin_kartlari[fmt] = (b, l2, alt_)

    if nblm_mi():
        yayin_karti(0, "nblm_konu", "Konu hazırla", "Gemini konu + NotebookLM kaynak metni yazar")
        yayin_karti(1, "nblm_isle", "Videoyu işle", "NotebookLM videosu → alt yazı, kapanış, yükleme")
    else:
        yayin_karti(0, "kisa", T("Shorts yayınla", "Publish a Short"), T("40–90 saniye  ·  dikey video",
                                                                          "40–90 seconds  ·  vertical · English"))
        yayin_karti(1, "uzun", T("Video yayınla", "Publish a video"), T("~10 dakika  ·  yatay video",
                                                                         "~10 minutes  ·  horizontal · English"))

    # --- konu satırı (isteğe bağlı) ---
    ks = tk.Frame(pn, bg=R["bg"])
    ks.pack(fill="x", pady=(px(14), px(20)))
    etiket(ks, "Konu (isteğe bağlı)", soluk=True, boyut=9).pack(side="left")
    konu_var = tk.StringVar()
    konu_giris = ttk.Entry(ks, textvariable=konu_var, font=F(10))
    konu_giris.pack(side="left", fill="x", expand=True, padx=px(10))
    def hazir_ekle():
        if durum["mesgul"]:
            uw_goster()
            return
        from tkinter import filedialog
        dosyalar = filedialog.askopenfilenames(parent=p, title="Hazır videolarını seç (birden fazla seçebilirsin)",
                                               filetypes=[("Video", "*.mp4 *.mov *.webm *.mkv *.m4v"), ("Tümü", "*.*")])
        if not dosyalar:
            return
        dosyalar = list(dosyalar)

        def is_():
            yeni = hazir_videolari_al(log, asama, dosyalar)
            asama(f"{len(yeni)} hazır video yayın sırasına eklendi", 100)
            if yeni:
                ui(lambda: son_goster(yeni[-1]))
            ui(lambda: durum["sayfa"] == "panel" and panel_yenile())
        is_baslat(is_, mod="uret", baslik_="Hazır videolar ekleniyor", fmt="kisa")
    Dugme(ks, "📥  Hazır video ekle", tur="ikincil", boy="kucuk", command=hazir_ekle).pack(side="right",
                                                                                          padx=(px(10), 0))
    fikir_btn = Dugme(ks, "Fikir bul", tur="hayalet", boy="kucuk")
    fikir_btn.pack(side="left")
    etiket(ks, "Tür", soluk=True, boyut=9).pack(side="left", padx=(px(16), px(6)))
    secim(ks, "tur", {t: t for t in (BIRADIM_ALANLARI if nblm_mi() else TURLER)}, 16).pack(side="left")

    # --- BirAdım ana ekranı: Konular (toplu NotebookLM) | Videoları ver  +  Onay bekleyenler ---
    akis_w = {}
    if nblm_mi():
        yk.pack_forget()
        ks.pack_forget()
        afis.pack_forget()                       # yer açılsın: en çok kullanılanlar ilk ekranda

        def kutu(ust, **grid):
            f = yuvarlak_kart(ust, bg=R["kart"], padx=px(20),
                         pady=px(16))
            f.grid(sticky="nsew", **grid)
            return f

        def baslik_satiri(ust, metin, sayac=True):
            sat = tk.Frame(ust, bg=R["kart"])
            sat.pack(fill="x")
            tk.Label(sat, text=metin, bg=R["kart"], fg=R["yazi"], font=F(14, "orta")).pack(side="left")
            sl = tk.Label(sat, text="", bg=R["kart2"], fg=R["soluk"], font=F(9, "orta"), padx=px(8))
            if sayac:
                sl.pack(side="left", padx=(px(10), 0))
            return sat, sl

        ust_ = tk.Frame(pn, bg=R["bg"])
        ust_.pack(fill="x", pady=(0, px(16)))
        ust_.grid_columnconfigure(0, weight=3, uniform="bu")
        ust_.grid_columnconfigure(1, weight=2, uniform="bu")

        # ---------- KONULAR ----------
        kk = kutu(ust_, row=0, column=0, padx=(0, px(16)))
        ks_sat, konu_sayi = baslik_satiri(kk, "Konular")
        uret_b = Dugme(ks_sat, "＋  5 konu üret", tur="ikincil", boy="kucuk")
        uret_b.pack(side="right")
        tk.Label(kk, text="Her konu için: ① 📋 Kaynak → NotebookLM'de yeni not defteri, 'Kopyalanan metin' olarak "
                          "yapıştır.   ② 📝 İstem → Video Özeti (Kısa, Türkçe) kalem simgesine yapıştır → Oluştur.",
                 bg=R["kart"], fg=R["soluk"], font=F(9), wraplength=px(560), justify="left").pack(
            anchor="w", pady=(px(6), px(10)))
        tum_b = Dugme(kk, "↗  NotebookLM'i aç", tur="ana")
        tum_b.pack(fill="x")
        konu_liste = tk.Frame(kk, bg=R["kart"])
        konu_liste.pack(fill="x", pady=(px(12), 0))

        def bekleyen_konular():
            return [x for x in nblm_kuyruk_oku() if x.get("durum") == "video_bekliyor"]

        def istem_metni(pk):
            return f"Sadece şu konuyu anlat: \"{pk.get('baslik', '')}\". " + (pk.get("istem") or "")

        def tum_kaynak():
            if not bekleyen_konular():
                return konu_uret(5)
            webbrowser.open("https://notebooklm.google.com/")

        def kaynak_kopyala(pk):
            panoya(pk.get("kaynak", ""), f"'{pk.get('baslik', '')}' kaynağı")
            akis_w["not"] = f"✓ Kopyalandı: {pk.get('baslik', '')} — kaynağı. Sonra aynı konunun 📝 İstem'ini kopyala."
            akis_yenile()

        def istem_kopyala(pk):
            panoya(istem_metni(pk), f"'{pk.get('baslik', '')}' istemi")
            akis_w["not"] = f"✓ Kopyalandı: {pk.get('baslik', '')} — istemi. Video Özeti'ne yapıştırıp oluştur."
            akis_yenile()
        tum_b.config(command=tum_kaynak)

        def konu_uret(adet=5):
            uret_b.config(state="disabled", text="Hazırlanıyor...")
            tum_b.config(state="disabled")

            def is_():
                yapilan = 0
                for i in range(adet):
                    try:
                        ui(lambda i=i: uret_b.config(text=f"Hazırlanıyor {i + 1}/{adet}..."))
                        nblm_konu_uret(ayar.get("tur", "Karışık"), None, log)
                        yapilan += 1
                        ui(akis_yenile)
                    except Exception as e:
                        hata = str(e)[:300]
                        ui(lambda: messagebox.showerror("Konu hazırlanamadı", hata))
                        break
                ui(lambda: (uret_b.config(state="normal", text="＋  5 konu üret"), tum_b.config(state="normal"),
                            akis_yenile()))
            threading.Thread(target=is_, daemon=True).start()
        uret_b.config(command=konu_uret)

        def konu_atla(pk):
            nblm_paket_guncelle(pk["id"], durum="atlandi")
            log(f"[~] Konu çıkarıldı: {pk.get('baslik', '')}")
            akis_yenile()

        # ---------- VİDEOLARI VER ----------
        vk = kutu(ust_, row=0, column=1)
        baslik_satiri(vk, "Videoları ver", sayac=False)
        tk.Label(vk, text="NotebookLM'den indirdiğin videoları seç; birden çok seçebilirsin. Program her videonun "
                          "konusunu içeriğinden bulur, hızlandırır, NotebookLM yazılarını kaldırır, rozet ve kapanış "
                          "ekler. Kendi düzenlediğin videoları da buradan verebilirsin; program bunu kendisi anlar.",
                 bg=R["kart"], fg=R["soluk"], font=F(9), wraplength=px(360), justify="left").pack(
            anchor="w", pady=(px(6), px(12)))

        def video_ver():
            if durum["mesgul"]:
                uw_goster()
                return
            from tkinter import filedialog
            indir = os.path.join(os.path.expanduser("~"), "Downloads")
            dosyalar = filedialog.askopenfilenames(
                parent=p, title="Videoları seç (birden çok seçebilirsin)",
                initialdir=indir if os.path.isdir(indir) else BASE,
                filetypes=[("Video", "*.mp4 *.mov *.webm *.mkv *.m4v"), ("Tümü", "*.*")])
            if not dosyalar:
                return
            dosyalar = list(dosyalar)
            a = dict(ayar)
            onceki = {os.path.basename(g.get("kaynak_video") or "") for g in gecmis_oku()
                      if not g.get("reddedildi")}
            tekrar = [f_ for f_ in dosyalar if os.path.basename(f_) in onceki]
            if tekrar:
                if messagebox.askyesno(
                        "Daha önce işlenmiş video",
                        f"{len(tekrar)} video daha önce işlenmiş:\n\n" + "\n".join(os.path.basename(x) for x in tekrar[:6])
                        + "\n\nYeniden işlensin mi? (Yeni hali onay listesine düşer; yayındaki eski videoya "
                          "dokunulmaz, istersen Studio'dan silersin.)"):
                    tekrar = []
            atla = {os.path.basename(x) for x in tekrar}

            hazirlananlar = []

            def is_():
                for i, f_ in enumerate(dosyalar):
                    iptal_kontrol()
                    ad_ = os.path.basename(f_)
                    if ad_ in atla:
                        log(f"[~] {ad_} daha önce işlendi, atlandı.")
                        continue
                    asama(f"Video {i + 1}/{len(dosyalar)}: {ad_}", 2 + 95 * i / len(dosyalar))
                    try:
                        sure_ = medya_suresi(f_)
                        if eski_kart_var_mi(f_, sure_):
                            log(f"[+] {ad_}: kendi düzenlediğin hazır video olarak işleniyor.")
                            hazir_videolari_al(log, asama, [f_])
                        else:
                            yeni_ = nblm_isle(f_, {}, a, log, asama)
                            hazirlananlar.append(f"• {yeni_.get('baslik', '')}\n    ({ad_})")
                    except IptalHatasi:
                        raise
                    except Exception as e:
                        log(f"[X] {ad_} işlenemedi: {str(e)[:300]}")
                    ui(akis_yenile)
                asama("Hazır: aşağıdan izleyip onayla", 100)
                ui(lambda: (panel_yenile(), p.bell(), hazirlananlar and messagebox.showinfo(
                    "Videolar hazır", "Onay listesinin EN ÜSTÜNE eklendi (YENİ yazanlar):\n\n"
                    + "\n".join(hazirlananlar))))
            is_baslat(is_, mod="uret", baslik_=f"{len(dosyalar)} video hazırlanıyor", fmt="kisa")
        Dugme(vk, "🎬  Videoları seç", tur="ana", command=video_ver).pack(fill="x")
        baglanti(vk, "📂  ya da 'gelen' klasörüne at (plan doldurulurken işlenir)", lambda: (
            os.makedirs(_nblm_dosya("gelen"), exist_ok=True), klasor_ac(_nblm_dosya("gelen"))), 9).pack(
            anchor="w", pady=(px(10), 0))
        sira_l = tk.Label(vk, text="", bg=R["kart"], fg=R["yazi"], font=F(10), wraplength=px(360),
                          justify="left", anchor="w")
        sira_l.pack(fill="x", pady=(px(16), 0))

        # ---------- ONAY BEKLEYENLER ----------
        okap = tk.Frame(pn, bg=R["bg"])
        okap.pack(fill="x", pady=(0, px(16)))
        okap.grid_columnconfigure(0, weight=1)
        ok_ = kutu(okap, row=0, column=0)
        ok_sat, onay_sayi = baslik_satiri(ok_, "Onay bekleyen videolar")
        hepsi_b = Dugme(ok_sat, "✓  Hepsini onayla", tur="yesil", boy="kucuk")
        hepsi_b.pack(side="right")
        tk.Label(ok_, text="İzle'ye basınca video açılır. Onayladığın video yayın planındaki ilk boş saatte "
                           "kendiliğinden yayınlanır.", bg=R["kart"], fg=R["soluk"], font=F(9)).pack(
            anchor="w", pady=(px(4), px(8)))
        onay_liste = tk.Frame(ok_, bg=R["kart"])
        onay_liste.pack(fill="x")

        def onay_sirasi():
            return sorted([g for g in gecmis_oku() if g.get("onay_bekliyor") and not g.get("video_id")
                           and not g.get("reddedildi") and os.path.exists(g.get("dosya", ""))],
                          key=lambda g: g.get("tarih", ""), reverse=True)        # en son hazırlanan en üstte

        def onayla(k_):
            hazir_onayla(k_)
            log(f"[✓] Onaylandı, yayın sırasına girdi: {k_.get('baslik', '')}")
            panel_yenile()

        def reddet(k_):
            if messagebox.askyesno("Yayınlanmasın", f"'{k_.get('baslik', '')}' yayınlanmasın mı?\n"
                                                    "(Dosya silinmez, sadece yayın sırasından çıkar.)"):
                k_.update(onay_bekliyor=False, plan_uretim=False, reddedildi=True)
                gecmis_kaydet(k_)
                panel_yenile()

        def yeniden_hazirla(k_):
            """Videoyu güncel kurallarla (kesim, rozet, kapanış) orijinal dosyasından yeniden hazırlar."""
            if durum["mesgul"]:
                uw_goster()
                return
            a = dict(ayar)

            def is_():
                if k_.get("format") == "hazir":
                    hazir_marka_ekle(k_, a, log, asama)
                else:
                    nblm_hiz_degistir(k_, float(k_.get("hiz") or a.get("nblm_hiz") or 1.5), log, asama)
                asama("Yeniden hazırlandı: izleyip onayla", 100)
                ui(panel_yenile)
            is_baslat(is_, mod="uret", baslik_="Video yeniden hazırlanıyor", fmt="kisa")

        def hepsini_onayla():
            s_ = onay_sirasi()
            if s_ and messagebox.askyesno("Hepsini onayla", f"{len(s_)} video yayın sırasına girsin mi?"):
                for k_ in s_:
                    hazir_onayla(k_)
                log(f"[✓] {len(s_)} video onaylandı.")
                panel_yenile()
        hepsi_b.config(command=hepsini_onayla)

        def satir(ust, metin, alt_metin, dugmeler, cizgi=True):
            sat = tk.Frame(ust, bg=R["kart"])
            sat.pack(fill="x")
            if cizgi:
                tk.Frame(sat, bg=R["ayrac"], height=1).pack(fill="x")
            ic = tk.Frame(sat, bg=R["kart"], pady=px(7))
            ic.pack(fill="x")
            for t_, tur_, cmd in reversed(dugmeler):
                Dugme(ic, t_, tur=tur_, boy="kucuk", command=cmd).pack(side="right", padx=(px(6), 0))
            sol = tk.Frame(ic, bg=R["kart"])
            sol.pack(side="left", fill="x", expand=True)
            tk.Label(sol, text=metin, bg=R["kart"], fg=R["yazi"], font=F(10, "orta"), anchor="w",
                     justify="left").pack(fill="x")
            if alt_metin:
                tk.Label(sol, text=alt_metin, bg=R["kart"], fg=R["soluk"], font=F(9), anchor="w").pack(fill="x")

        def kisalt(m, n=58):
            return m if len(m) <= n else m[:n - 1].rstrip() + "…"

        def akis_yenile():
            # konular
            for w_ in konu_liste.winfo_children():
                w_.destroy()
            k_ = bekleyen_konular()
            konu_sayi.config(text=f"{len(k_)} konu bekliyor")
            if not k_:
                tk.Label(konu_liste, text="Bekleyen konu yok. '＋ 5 konu üret' ile kanalın en iyi videolarına göre "
                                          "yeni konular hazırlansın.", bg=R["kart"], fg=R["soluk"], font=F(10),
                         wraplength=px(560), justify="left").pack(anchor="w")
                tum_b.config(text="✨  5 konu üret")
            else:
                tum_b.config(text="↗  NotebookLM'i aç")
                for i, pk in enumerate(k_[:10]):
                    satir(konu_liste, f"{i + 1}.  {kisalt(pk.get('baslik', ''))}",
                          f"{pk.get('alan', '')}" + (f"  ·  açılış: {buyuk(pk['kanca'])}" if pk.get("kanca") else ""),
                          [("📋 Kaynak", "ana", lambda pk=pk: kaynak_kopyala(pk)),
                           ("📝 İstem", "ikincil", lambda pk=pk: istem_kopyala(pk)),
                           ("✕", "hayalet", lambda pk=pk: konu_atla(pk))], cizgi=i > 0)
                if len(k_) > 10:
                    tk.Label(konu_liste, text=f"+ {len(k_) - 10} konu daha", bg=R["kart"], fg=R["soluk"],
                             font=F(9)).pack(anchor="w", pady=(px(4), 0))
            if akis_w.get("not"):
                tk.Label(konu_liste, text=akis_w["not"], bg=R["kart"], fg=R["yesil2"], font=F(9),
                         wraplength=px(560), justify="left").pack(anchor="w", pady=(px(8), 0))
            # onay bekleyenler
            for w_ in onay_liste.winfo_children():
                w_.destroy()
            s_ = onay_sirasi()
            onay_sayi.config(text=f"{len(s_)} video")
            hepsi_b.config(state="normal" if len(s_) > 1 else "disabled")
            if not s_:
                tk.Label(onay_liste, text="Onay bekleyen video yok.", bg=R["kart"], fg=R["soluk"],
                         font=F(10)).pack(anchor="w")
            for i, g in enumerate(s_[:12]):
                yon_ = "yatay" if g.get("yon") == "yatay" else "dikey"
                try:
                    yas_ = (datetime.datetime.now() - datetime.datetime.fromisoformat(g.get("tarih", ""))).total_seconds()
                except ValueError:
                    yas_ = 1e9
                kaynak_ad = re.split(r"[\\/]", g.get("kaynak_video") or "")[-1]
                satir(onay_liste, ("🆕 YENİ  ·  " if yas_ < 3 * 3600 else "") + kisalt(g.get("baslik", ""), 70),
                      f"{sure_yaz(g.get('sure') or 0)}  ·  {yon_}  ·  "
                      f"{'hazır video' if g.get('format') == 'hazir' else 'NotebookLM'}"
                      + (f"  ·  dosya: {kisalt(kaynak_ad, 40)}" if kaynak_ad else ""),
                      [("▶ İzle", "ikincil", lambda g=g: klasor_ac(g["dosya"])),
                       ("↻", "hayalet", lambda g=g: yeniden_hazirla(g)),
                       ("✓ Onayla", "yesil", lambda g=g: onayla(g)),
                       ("✕", "hayalet", lambda g=g: reddet(g))], cizgi=i > 0)
            # yayın sırası
            sira = [g for g in gecmis_oku() if g.get("plan_uretim") and not g.get("video_id")
                    and not g.get("onay_bekliyor") and not g.get("reddedildi") and os.path.exists(g.get("dosya", ""))]
            simdi_ = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            planli = [g for g in gecmis_oku() if g.get("video_id") and (g.get("yayin_zamani") or "") > simdi_]
            gunluk = max(1, len(plan_listesi(ayar)))
            toplam_ = len(sira) + len(planli)
            yeter = toplam_ / gunluk
            sira_l.config(text=(f"Yayın sırasında {toplam_} video var — "
                                + ("1 günden az yeter." if yeter < 1 else f"yaklaşık {int(yeter)} gün yeter.")
                                + ("\nYeni video eklemeyi unutma." if yeter < 2 else "")))

        akis_w["yenile"] = akis_yenile

    # --- alt: son videolar | sıradaki yayınlar + kanal özeti ---
    alt_ = tk.Frame(pn, bg=R["bg"])
    alt_.pack(fill="both", expand=True)
    alt_.grid_columnconfigure(0, weight=16, uniform="a")
    alt_.grid_columnconfigure(1, weight=10, uniform="a")

    sv = yuvarlak_kart(alt_, bg=R["kart"])
    sv.grid(row=0, column=0, sticky="nsew", padx=(0, px(16)))
    svb = tk.Frame(sv, bg=R["kart"], padx=px(22), pady=px(16))
    svb.pack(fill="x")
    tk.Label(svb, text="Son videolar", bg=R["kart"], fg=R["yazi"], font=F(12, "orta")).pack(side="left")
    baglanti(svb, "Tümü", lambda: sayfa_goster("kutup")).pack(side="right")
    son_klasor = Dugme(svb, "Dosya konumunu aç", tur="hayalet", boy="kucuk",
                       command=lambda: son_islem("klasor"))
    son_klasor.pack(side="right", padx=(0, px(16)))
    son_oynat = Dugme(svb, "Oynat", tur="hayalet", boy="kucuk", command=lambda: son_islem("oynat"))
    son_oynat.pack(side="right", padx=(0, px(8)))
    def onayla_sec():
        k_ = son_secili()
        if k_ and k_.get("onay_bekliyor"):
            hazir_onayla(k_)
            log(f"[✓] Onaylandı, yayın planına girdi: {k_.get('baslik', '')}")
            panel_yenile()
    son_onay = Dugme(svb, "✓  Onayla", tur="ana", boy="kucuk", command=onayla_sec)
    son_hiz = Dugme(svb, "⏩  Hız / önizle", tur="hayalet", boy="kucuk",
                    command=lambda: son_secili() and hiz_penceresi(son_secili()))
    if nblm_mi():
        son_hiz.pack(side="right", padx=(0, px(8)))
    son_onay.pack(side="right", padx=(0, px(8)))
    son_onay.pack_forget()
    for b_ in (son_klasor, son_oynat, son_hiz):
        b_.config(state="disabled")
    son_agac = ttk.Treeview(sv, columns=("durum", "izlenme"), show="tree headings", selectmode="browse",
                            style="Liste.Treeview", height=5)
    son_agac.heading("#0", text="Video", anchor="w")
    son_agac.heading("durum", text="Durum", anchor="w")
    son_agac.heading("izlenme", text="Görüntüleme", anchor="e")
    son_agac.column("#0", width=px(300), stretch=True, anchor="w")
    son_agac.column("durum", width=px(150), stretch=False, anchor="w")
    son_agac.column("izlenme", width=px(110), stretch=False, anchor="e")
    son_agac.tag_configure("soluk", foreground=R["soluk2"])   # sadece silinen/eksik videolar soluk
    son_agac.pack(fill="both", expand=True, padx=px(8), pady=(0, px(8)))
    son_agac.bind("<Double-1>", lambda e: (lambda s_: s_ and son_ac(s_[0]))(son_agac.selection()))

    def son_secili():
        s_ = son_agac.selection()
        return son_kayitlar.get(s_[0]) if s_ else None

    def son_islem(ne):
        kayit = son_secili()
        if not kayit:
            return
        dosya = kayit.get("dosya", "")
        if ne in ("klasor", "oynat") and not os.path.exists(dosya):
            messagebox.showwarning("Dosya yok", "Bu videonun dosyası bilgisayarda bulunamadı:\n" + dosya)
            return
        if ne == "klasor":
            klasorde_goster(dosya)
        elif ne == "oynat":
            klasor_ac(dosya)
        elif ne == "yt" and kayit.get("url"):
            webbrowser.open(kayit["url"])
        elif ne == "yukle":
            duzenle_penceresi(kayit)

    def son_secim_degisti(_=None):
        kayit = son_secili()
        var = bool(kayit) and os.path.exists(kayit.get("dosya", ""))
        son_klasor.config(state="normal" if var else "disabled")
        son_oynat.config(state="normal" if var else "disabled")
        son_hiz.config(state="normal" if kayit and kayit.get("format") == "notebooklm" else "disabled")
        if kayit and kayit.get("onay_bekliyor") and not kayit.get("video_id"):
            son_onay.pack(side="right", padx=(0, px(8)), before=son_oynat)
        else:
            son_onay.pack_forget()
    son_agac.bind("<<TreeviewSelect>>", son_secim_degisti)

    son_menu = tk.Menu(p, tearoff=0, bg=R["kart"], fg=R["yazi"], activebackground=R["secili"],
                       activeforeground=R["yazi"], bd=0, font=F(10))

    def son_sag_tik(e):
        iid = son_agac.identify_row(e.y)
        if not iid:
            return
        son_agac.selection_set(iid)
        kayit = son_kayitlar.get(iid) or {}
        var = os.path.exists(kayit.get("dosya", ""))
        son_menu.delete(0, "end")
        son_menu.add_command(label="Oynat", command=lambda: son_islem("oynat"),
                             state="normal" if var else "disabled")
        son_menu.add_command(label="Dosya konumunu aç", command=lambda: son_islem("klasor"),
                             state="normal" if var else "disabled")
        if kayit.get("format") == "hazir" and not kayit.get("video_id"):
            def marka_(k_=kayit):
                a_ = dict(ayar)

                def is_():
                    hazir_marka_ekle(k_, a_, log, asama)
                    ui(lambda: son_goster(k_))
                    asama("Hazır: oynatıp bak, beğenirsen ✓ Onayla", 100)
                is_baslat(is_, mod="uret", baslik_="Rozet ve kapanış ekleniyor", fmt="kisa")
            son_menu.add_command(label="Rozet ve kapanışı yeniden ekle" if kayit.get("marka_eklendi")
                                 else "Rozet ve kapanış ekle", command=marka_)
        if kayit.get("onay_bekliyor") and not kayit.get("video_id"):
            son_menu.add_command(label="✓ Onayla (yayın planına koy)",
                                 command=lambda: (hazir_onayla(kayit), panel_yenile()))
        if kayit.get("format") == "notebooklm":
            son_menu.add_command(label="Hızı değiştir / yeniden hazırla", command=lambda: hiz_penceresi(kayit))
        if kayit.get("sahneler") and var:
            son_menu.add_command(label="Sahneleri gör / yeniden çiz", command=lambda: sahne_penceresi(kayit))
        if kayit.get("url"):
            son_menu.add_command(label="YouTube'da aç", command=lambda: son_islem("yt"))
        elif var and not kayit.get("video_id"):
            son_menu.add_command(label="Düzenle ve yükle", command=lambda: son_islem("yukle"))
        son_menu.tk_popup(e.x_root, e.y_root)
    son_agac.bind("<Button-3>", son_sag_tik)
    son_bos = tk.Label(sv, text="Henüz video yok. Yukarıdaki butonlardan biriyle ilk videonu oluştur.",
                       bg=R["kart"], fg=R["soluk"], font=F(10))

    sag_k = tk.Frame(alt_, bg=R["bg"])
    sag_k.grid(row=0, column=1, sticky="nsew")
    sk1 = yuvarlak_kart(sag_k, bg=R["kart"], padx=px(22),
                   pady=px(16))
    sk1.pack(fill="x")
    s1b = tk.Frame(sk1, bg=R["kart"])
    s1b.pack(fill="x")
    tk.Label(s1b, text="Sıradaki yayınlar", bg=R["kart"], fg=R["yazi"], font=F(12, "orta")).pack(side="left")
    baglanti(s1b, "Planı düzenle", lambda: sayfa_goster("plan")).pack(side="right")
    sirada_f = tk.Frame(sk1, bg=R["kart"])
    sirada_f.pack(fill="x", pady=(px(10), 0))

    sk2 = yuvarlak_kart(sag_k, bg=R["kart"], padx=px(22),
                   pady=px(16))
    sk2.pack(fill="x", pady=(px(16), 0))
    tk.Label(sk2, text="Kanal özeti", bg=R["kart"], fg=R["yazi"], font=F(12, "orta")).pack(anchor="w")
    tk.Label(sk2, text="Tüm zamanlar", bg=R["kart"], fg=R["soluk"], font=F(9)).pack(anchor="w", pady=(px(2), px(8)))
    kanal_ozet = {}
    for i, (anah, ad_) in enumerate([("abone", "Abone"), ("izlenme", "Görüntüleme"), ("video", "Video")]):
        if i:
            tk.Frame(sk2, bg=R["ayrac"], height=1).pack(fill="x")
        sat = tk.Frame(sk2, bg=R["kart"])
        sat.pack(fill="x", pady=px(8))
        tk.Label(sat, text=ad_, bg=R["kart"], fg=R["yazi"], font=F(10)).pack(side="left")
        kanal_ozet[anah] = tk.Label(sat, text="–", bg=R["kart"], fg=R["yazi"], font=F(10, "orta"))
        kanal_ozet[anah].pack(side="right")

    def sirada_satir(sol_metin, sag_metin, renk, ilk):
        if not ilk:
            tk.Frame(sirada_f, bg=R["ayrac"], height=1).pack(fill="x")
        sat = tk.Frame(sirada_f, bg=R["kart"])
        sat.pack(fill="x", pady=px(8))
        tk.Label(sat, text=sol_metin, bg=R["kart"], fg=R["yazi"], font=F(10)).pack(side="left")
        tk.Label(sat, text=sag_metin, bg=R["kart"], fg=renk, font=F(10)).pack(side="right")

    son_kayitlar = {}

    def son_ac(iid):
        kayit = son_kayitlar.get(iid)
        if not kayit:
            return
        if kayit.get("url"):
            webbrowser.open(kayit["url"])
        elif os.path.exists(kayit.get("dosya", "")):
            klasor_ac(kayit["dosya"])

    def kucuk_liste_resmi(iid, video, anahtar):
        def is_():
            yolu = kucuk_resim_kare(video, 56)

            def goster():
                if yolu and son_agac.exists(iid):
                    try:
                        img = tk.PhotoImage(file=yolu)
                    except tk.TclError:
                        return
                    durum["resimler"][anahtar] = img
                    son_agac.item(iid, image=img)
            ui(goster)
        threading.Thread(target=is_, daemon=True).start()

    def panel_yenile():
        if akis_w.get("yenile"):
            try:
                akis_w["yenile"]()
            except Exception:
                pass
        # son videolar
        son_agac.delete(*son_agac.get_children())
        son_kayitlar.clear()
        g_ = gecmis_oku()
        simdi = datetime.datetime.now(datetime.timezone.utc)
        liste = sorted(g_, key=lambda k_: k_.get("tarih", ""), reverse=True)[:8]
        for i, kayit in enumerate(liste):
            ist = kayit.get("istatistik") or {}
            if kayit.get("video_id") and not ist.get("silindi"):
                yz = ist.get("publishAt") or kayit.get("yayin_zamani")
                try:
                    t = datetime.datetime.fromisoformat(yz.replace("Z", "+00:00")) if yz else None
                except ValueError:
                    t = None
                if t and t > simdi:
                    yerel = t.astimezone()
                    gun = ("Bugün" if yerel.date() == datetime.date.today() else
                           "Yarın" if yerel.date() == datetime.date.today() + datetime.timedelta(days=1)
                           else f"{GUN_ADLARI[yerel.weekday()]} {yerel:%d.%m}")
                    d_, et = f"{gun} {yerel:%H:%M}", "planli"
                else:
                    d_ = {"private": "Özel", "unlisted": "Liste dışı"}.get(ist.get("gizlilik"), "Herkese açık")
                    et = "yayinda"
                izl = sayi(ist.get("izlenme")) if ist.get("izlenme") is not None else "–"
            elif ist.get("silindi"):
                d_, et, izl = "YouTube'dan silinmiş", "soluk", "–"
            elif os.path.exists(kayit.get("dosya", "")) and kayit.get("onay_bekliyor"):
                d_, et, izl = "Onayını bekliyor", "bekliyor", "–"
            elif os.path.exists(kayit.get("dosya", "")):
                d_, et, izl = "Yüklenmeyi bekliyor", "bekliyor", "–"
            else:
                d_, et, izl = "Dosya yok", "soluk", "–"
            iid = f"s{i}"
            son_kayitlar[iid] = kayit
            son_agac.insert("", "end", iid=iid, text="   " + kayit.get("baslik", kayit.get("konu", "")),
                            values=(d_, izl), tags=(et,))
            if os.path.exists(kayit.get("dosya", "")):
                kucuk_liste_resmi(iid, kayit["dosya"], f"liste{i}")
        if liste:
            son_bos.pack_forget()
            son_agac.config(height=len(liste))
        else:
            son_bos.pack(pady=px(30))
            son_agac.config(height=1)
        son_secim_degisti()
        # sıradaki yayınlar
        for w in sirada_f.winfo_children():
            w.destroy()
        simdi_y = datetime.datetime.now().astimezone()
        kayitlar = plan_kayitlari()
        slotlar = [(t, f) for t, f in plan_slotlari(ayar, simdi_y) if t > simdi_y][:4]
        if slotlar:
            t0, f0 = slotlar[0]
            gunler_en = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
            g0 = (T("Bugün", "Today") if t0.date() == simdi_y.date() else T("Yarın", "Tomorrow") if t0.date() == (
                simdi_y + datetime.timedelta(days=1)).date() else
                f"{T(GUN_ADLARI[t0.weekday()], gunler_en[t0.weekday()])} {t0:%d.%m}")
            afis_alt_yaz(f"{T('Sıradaki yayın', 'Next upload')}: {g0} {t0:%H:%M} · "
                         f"{T('Uzun video', 'Long video') if f0 == 'uzun' else 'Shorts'}"
                         + (T(" · hazır", " · ready") if _slot_anahtar(t0) in kayitlar else ""))
        else:
            afis_alt_yaz(T("Yayın planı boş. Aşağıdan hemen bir video yayınlayabilirsin.",
                           "The schedule is empty. Publish a video right below."))
        if not slotlar:
            tk.Label(sirada_f, text="Plan boş. Yayın saatlerini 'Planı düzenle'den ekleyebilirsin.", bg=R["kart"],
                     fg=R["soluk"], font=F(9), wraplength=px(300), justify="left").pack(anchor="w")
        for i, (t, f) in enumerate(slotlar):
            gun = ("Bugün" if t.date() == simdi_y.date() else
                   "Yarın" if t.date() == (simdi_y + datetime.timedelta(days=1)).date()
                   else f"{GUN_ADLARI[t.weekday()]} {t:%d.%m}")
            hazir = _slot_anahtar(t) in kayitlar
            sirada_satir(f"{gun} {t:%H:%M}  ·  {'Uzun video' if f == 'uzun' else 'Shorts'}",
                         "Hazır" if hazir else f"{ayar.get('plan_gorev_saat', '03:00')}'te hazırlanacak",
                         R["yesil2"] if hazir else R["soluk"], i == 0)

    # ---------- düzenle ve yükle penceresi (İçerik sayfasından) ----------
    def sahne_penceresi(kayit):
        """Senaryo videosunun sahne çizimleri: beğenilmeyen sahne tek tıkla yeniden çizilir, video yenilenir."""
        d = tk.Toplevel(p)
        d.title("Sahneler")
        pencere_belir(d)
        d.after(10, lambda: pencere_koyu_baslik(d, koyu_tema))
        d.configure(bg=R["kart"], padx=px(20), pady=px(16))
        d.geometry(f"{px(900)}x{px(620)}")
        d.transient(p)
        tk.Label(d, text="Sahneler", bg=R["kart"], fg=R["yazi"], font=F(16, "orta")).pack(anchor="w")
        bilgi_ = ("Bu video YouTube'a yüklendi; yeniden çizim sadece bilgisayardaki dosyayı değiştirir."
                  if kayit.get("video_id") else
                  "Beğenmediğin sahnenin altındaki 'Yeniden çiz'e bas; sahne yeniden çizilir ve video aynı ses ve "
                  "müzikle yenilenir (1-2 dk).")
        tk.Label(d, text=bilgi_, bg=R["kart"], fg=R["soluk"], font=F(9), wraplength=px(840), justify="left").pack(
            anchor="w", pady=(px(2), px(10)))
        durum_lbl = tk.Label(d, text="", bg=R["kart"], fg=R["soluk"], font=F(9))
        durum_lbl.pack(side="bottom", anchor="w", pady=(px(8), 0))
        dis, ic = kaydirma(d)
        for w_ in (dis, ic, *dis.winfo_children()):
            try:
                w_.config(bg=R["kart"])
            except tk.TclError:
                pass
        dis.pack(fill="both", expand=True)
        resimler = []
        dugmeler = []

        def ciz_kartlar():
            for w in ic.winfo_children():
                w.destroy()
            resimler.clear()
            dugmeler.clear()
            for i, s_ in enumerate(kayit.get("sahneler") or []):
                kt = tk.Frame(ic, bg=R["kart2"], padx=px(8), pady=px(8))
                kt.grid(row=i // 5, column=i % 5, padx=px(5), pady=px(5), sticky="n")
                lbl = tk.Label(kt, text="…", bg=R["kart2"], fg=R["soluk"], width=px(150) // 8)
                lbl.pack()
                kucuk = cizim_kucuk(s_.get("resim", ""), px(230)) if s_.get("resim") else None
                if kucuk:
                    try:
                        img = tk.PhotoImage(file=kucuk)
                        resimler.append(img)
                        lbl.config(image=img, text="", width=0)
                    except tk.TclError:
                        pass
                tk.Label(kt, text=s_.get("sayac", ""), bg=R["kart2"], fg=R["yazi"], font=F(10, "orta")).pack(
                    anchor="w", pady=(px(4), 0))
                tk.Label(kt, text=" ".join(s_.get("metin", "").split()[:14]) + "…", bg=R["kart2"], fg=R["soluk"],
                         font=F(8), wraplength=px(140), justify="left").pack(anchor="w")
                b_ = Dugme(kt, "Yeniden çiz", tur="hayalet", boy="kucuk", command=lambda n=i: yenile(n))
                b_.pack(anchor="w", pady=(px(4), 0))
                dugmeler.append(b_)

        def yenile(n):
            for b_ in dugmeler:
                b_.config(state="disabled")
            durum_lbl.config(text=f"Sahne {n + 1} yeniden çiziliyor ve video yenileniyor...", fg=R["soluk"])

            def is_():
                try:
                    senaryo_sahne_yenile(kayit, n, print)
                    ui(lambda: (ciz_kartlar(), durum_lbl.config(text=f"✓ Sahne {n + 1} yenilendi, video güncellendi.",
                                                               fg=R["yesil2"]), panel_yenile()))
                except Exception as e:
                    hata = str(e)
                    ui(lambda: (durum_lbl.config(text="Olmadı: " + hata[:200], fg=R["kirmizi"]),
                                [b_.config(state="normal") for b_ in dugmeler]))
            threading.Thread(target=is_, daemon=True).start()
        ciz_kartlar()
        alt_ = tk.Frame(d, bg=R["kart"])
        alt_.pack(side="bottom", fill="x", before=durum_lbl)
        Dugme(alt_, "📂  Sahne klasörü", tur="hayalet", boy="kucuk",
              command=lambda: klasor_ac(kayit["dosya"][:-4] + "_sahneler")).pack(side="left")
        Dugme(alt_, "▶  Videoyu oynat", tur="hayalet", boy="kucuk",
              command=lambda: klasor_ac(kayit["dosya"])).pack(side="left", padx=px(8))
        Dugme(alt_, "Kapat", tur="ikincil", boy="kucuk", command=d.destroy).pack(side="right")

    HIZLAR = {"1.0": "Normal (1x)", "1.25": "1.25x", "1.5": "1.5x", "1.75": "1.75x"}

    def hiz_satiri(ust, kaynak, baslangic):
        """'Video hızı' seçimi + kısa önizleme düğmesi. Seçili hızı (float) döndüren fonksiyon verir."""
        f_ = tk.Frame(ust, bg=R["kart"])
        f_.pack(fill="x", pady=(px(4), px(12)))
        etiket(f_, "Video hızı", soluk=True).pack(side="left")
        ters = {v_: k_ for k_, v_ in HIZLAR.items()}
        bas_ = f"{float(baslangic):g}" if f"{float(baslangic):g}" in ("1", "1.25", "1.5", "1.75") else "1.5"
        hv = tk.StringVar(value=HIZLAR["1.0" if bas_ == "1" else bas_])
        ttk.Combobox(f_, textvariable=hv, values=list(HIZLAR.values()), state="readonly", width=14).pack(
            side="left", padx=(px(12), px(8)))
        durum_l = tk.Label(f_, text="", bg=R["kart"], fg=R["soluk"], font=F(9))

        def onizle():
            ob.config(state="disabled", text="Hazırlanıyor...")
            h_ = float(ters.get(hv.get(), "1.5"))

            def is_():
                try:
                    yol_ = nblm_onizleme(kaynak, h_)
                    ui(lambda: (klasor_ac(yol_), durum_l.config(text=f"İlk 12 sn, {h_:g}x (alt yazısız önizleme)",
                                                                fg=R["soluk"])))
                except Exception as e:
                    hata = str(e)[:160]
                    ui(lambda: durum_l.config(text=hata, fg=R["kirmizi"]))
                finally:
                    ui(lambda: ob.config(state="normal", text="▶  Önizle"))
            threading.Thread(target=is_, daemon=True).start()
        ob = Dugme(f_, "▶  Önizle", tur="hayalet", boy="kucuk", command=onizle)
        ob.pack(side="left")
        if not os.path.exists(kaynak or ""):
            ob.config(state="disabled")
            durum_l.config(text="Orijinal NotebookLM videosu bulunamadı; hız değiştirilemez.", fg=R["sari"])
        durum_l.pack(side="left", padx=(px(10), 0))
        return lambda: float(ters.get(hv.get(), "1.5"))

    def hiz_penceresi(kayit):
        """NotebookLM videosunun hızını seç, önizle, uygula (planlı videoyu da yeni hızla yeniden planlar)."""
        d = tk.Toplevel(p)
        d.title("Video hızı")
        pencere_belir(d)
        d.after(10, lambda: pencere_koyu_baslik(d, koyu_tema))
        d.configure(bg=R["kart"], padx=px(24), pady=px(20))
        d.transient(p)
        d.grab_set()
        ust_ = tk.Frame(d, bg=R["kart"])
        ust_.pack(fill="x")
        tk.Label(ust_, text="Video hızı", bg=R["kart"], fg=R["yazi"], font=F(16, "orta")).pack(side="left")
        beta(ust_).pack(side="left", padx=(px(10), 0), pady=(px(4), 0))
        tk.Label(d, text=f"{kayit.get('baslik', '')}  ·  şu an {float(kayit.get('hiz') or 1.0):g}x", bg=R["kart"],
                 fg=R["soluk"], font=F(9), wraplength=px(520), justify="left").pack(anchor="w", pady=(px(2), px(12)))
        simdi = datetime.datetime.now(datetime.timezone.utc)
        try:
            zaman = datetime.datetime.strptime(kayit.get("yayin_zamani") or "", "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=datetime.timezone.utc)
        except ValueError:
            zaman = None
        if not kayit.get("video_id"):
            bilgi_, olur = "Video henüz yüklenmedi: yeni hızla yeniden hazırlanır, plan sırası gelince yükler.", True
        elif zaman and zaman > simdi + datetime.timedelta(minutes=5):
            bilgi_ = (f"Video {zaman.astimezone():%d.%m %H:%M} için planlı: yeni hızla hazırlanıp AYNI saate yeniden "
                      "yüklenir, eskisi gizliye alınır (Studio'dan silebilirsin).")
            olur = True
        else:
            bilgi_ = ("Bu video yayınlandı. YouTube yayındaki videonun dosyasını değiştirmeye izin vermediği için hız "
                      "değiştirilemez; önizlemeyi yine de izleyebilirsin.")
            olur = False
        tk.Label(d, text=bilgi_, bg=R["kart"], fg=R["yazi"] if olur else R["sari"], font=F(9), wraplength=px(520),
                 justify="left").pack(anchor="w", pady=(0, px(10)))
        hiz_al = hiz_satiri(d, kayit.get("kaynak_video", ""), 1.5 if float(kayit.get("hiz") or 1.0) == 1.0
                            else kayit.get("hiz"))
        alt_ = tk.Frame(d, bg=R["kart"])
        alt_.pack(fill="x", pady=(px(8), 0))

        def uygula():
            h_ = hiz_al()
            d.grab_release()
            d.destroy()

            def is_():
                nblm_hiz_degistir(kayit, h_, log, asama)
                ui(lambda: son_goster(kayit))
                ui(lambda: durum["sayfa"] == "panel" and panel_yenile())
            is_baslat(is_, mod="yukle", yukleme_var=bool(kayit.get("video_id")), baslik_=f"Hız: {h_:g}x")
        tk.Label(d, text="Aynı hızı seçip Uygula dersen video güncel ayarlarla (alt yazı, rozet, kapanış) yeniden "
                         "hazırlanır.", bg=R["kart"], fg=R["soluk"], font=F(9), wraplength=px(520),
                 justify="left").pack(anchor="w", before=alt_)
        ub = Dugme(alt_, "Uygula / yeniden hazırla", tur="ana", command=uygula)
        ub.pack(side="right")
        if not olur or not os.path.exists(kayit.get("kaynak_video", "")):
            ub.config(state="disabled")
        Dugme(alt_, "Kapat", tur="hayalet", command=lambda: (d.grab_release(), d.destroy())).pack(side="right",
                                                                                                padx=px(8))

    def duzenle_penceresi(kayit):
        d = tk.Toplevel(p)
        d.title("Düzenle ve yükle")
        pencere_belir(d)
        d.after(10, lambda: pencere_koyu_baslik(d, koyu_tema))
        d.configure(bg=R["kart"], padx=px(24), pady=px(20))
        d.geometry(f"{px(640)}x{px(560)}")
        d.transient(p)
        d.grab_set()
        tk.Label(d, text="Düzenle ve yükle", bg=R["kart"], fg=R["yazi"], font=F(16, "orta")).pack(anchor="w")
        tk.Label(d, text=f"Kanal: {ayar.get('hedef_kanal', '')}  ·  {GIZLILIK.get(ayar.get('gizlilik'), '')}",
                 bg=R["kart"], fg=R["soluk"], font=F(9)).pack(anchor="w", pady=(px(2), px(16)))
        etiket(d, "Başlık", soluk=True, boyut=9).pack(anchor="w")
        b_var = tk.StringVar(value=kayit.get("baslik", ""))
        b_giris, b_sayac = baslik_kutusu(d, b_var, font=F(11))
        b_giris.pack(fill="x", pady=(px(4), 0))
        b_sayac.pack(fill="x", pady=(px(2), px(8)))
        etiket(d, "Etiketler (virgülle)", soluk=True, boyut=9).pack(anchor="w")
        e_var = tk.StringVar(value=", ".join(kayit.get("etiketler", [])))
        alt_f = tk.Frame(d, bg=R["kart"])
        alt_f.pack(side="bottom", fill="x", pady=(px(16), 0))
        ttk.Entry(d, textvariable=e_var).pack(fill="x", pady=(px(4), px(12)))
        etiket(d, "Açıklama", soluk=True, boyut=9).pack(anchor="w")
        ack = tk.Text(d, height=6, font=F(10), bg=R["kart"], fg=R["yazi"], insertbackground=R["yazi"], bd=0,
                      padx=px(10), pady=px(8), wrap="word", highlightthickness=1, highlightbackground=R["cerceve"],
                      highlightcolor=R["vurgu"])
        ack.pack(fill="both", expand=True, pady=(px(4), 0))
        ack.insert("1.0", kayit.get("aciklama", ""))
        hiz_al = None
        if kayit.get("format") == "notebooklm":
            d.geometry(f"{px(640)}x{px(620)}")
            hiz_al = hiz_satiri(alt_f, kayit.get("kaynak_video", ""), kayit.get("hiz", 1.0))

        def yukle_():
            kayit["baslik"] = baslik_sinirla(b_var.get()) or kayit["baslik"]
            kayit["aciklama"] = ack.get("1.0", "end").strip()
            kayit["etiketler"] = [x.strip() for x in e_var.get().split(",") if x.strip()]
            yeni_hiz = hiz_al() if hiz_al else None
            d.grab_release()
            d.destroy()
            elle_yukle(kayit, yeni_hiz if yeni_hiz and abs(yeni_hiz - float(kayit.get("hiz", 1.0))) > 0.01 else None)
        Dugme(alt_f, "YouTube'a yükle", tur="yesil", command=yukle_).pack(side="right")
        Dugme(alt_f, "Vazgeç", tur="hayalet", command=lambda: (d.grab_release(), d.destroy())).pack(
            side="right", padx=px(8))

    def son_goster(kayit):
        """Son üretilen/yüklenen videoyu üretim penceresine ve panele yansıtır."""
        durum["son"] = kayit
        if kayit.get("baslik"):
            uw_baslik_var.set(kayit["baslik"])
        resim_yukle(uw_resim, kayit.get("dosya"), "son", 300)
        if durum["sayfa"] == "panel":
            panel_yenile()

    def resim_yukle(et, video, anahtar, kutu=240):
        def is_():
            yolu = kucuk_resim(video, kutu)

            def goster():
                if not yolu:
                    return
                try:
                    img = tk.PhotoImage(file=yolu)
                except tk.TclError:
                    return
                durum["resimler"][anahtar] = img
                et.config(image=img, text="", width=0, height=0)
            ui(goster)
        threading.Thread(target=is_, daemon=True).start()

    # ======================================================================
    # SAYFA: OTOMATİK YAYIN
    # ======================================================================
    psol, psag = iki_kolon(sayfa("plan"), 1, 1, kaydir_sag=False)

    k = kart(psol, "📅  Yayın planı",
             "Her satır bir yayın saati: format (Shorts / Uzun) ve hangi günler yayınlanacağını seç. Videolar önceden "
             "üretilip YouTube'a yüklenir ve o saatte kendiliğinden yayınlanır.", sarma=440)
    saat_kutu = tk.Frame(k, bg=R["kart"])
    saat_kutu.pack(fill="x")
    saat_satirlari = []

    def saatleri_kaydet(*_):
        liste, hatali = [], False
        for st_ in saat_satirlari:
            hs = saat_coz(st_["saat"].get())
            if hs:
                liste.append({"saat": f"{hs[0]:02d}:{hs[1]:02d}", "format": st_["format"].get(),
                              "gunler": sorted(st_["gunler"])})
            elif st_["saat"].get().strip():
                hatali = True
        liste.sort(key=lambda e: e["saat"])
        ayar["plan"] = liste
        ayar["plan_saatler"] = sorted({e["saat"] for e in liste if e["format"] == "kisa"})
        ayar_yaz(ayar)
        plan_bilgi.config(text=("⚠ Saat biçimi: 12:00 gibi yaz.  " if hatali else "") + plan_ozet(),
                          fg=R["sari"] if hatali else R["soluk"])
        plan_yenile()

    def saat_satiri_ekle(deger="", fmt="kisa", gunler=None):
        if len(saat_satirlari) >= 10:
            return None
        kap = tk.Frame(saat_kutu, bg=R["bg"], padx=px(12), pady=px(10), highlightthickness=1,
                       highlightbackground=R["kenar"])
        kap.pack(fill="x", pady=(0, px(8)))
        ust = tk.Frame(kap, bg=R["bg"])
        ust.pack(fill="x")
        var_ = tk.StringVar(value=deger)
        e = ttk.Entry(ust, textvariable=var_, width=6, font=F(12, "orta"), justify="center")
        e.pack(side="left", padx=(0, px(12)))
        e.bind("<FocusOut>", saatleri_kaydet)
        e.bind("<Return>", saatleri_kaydet)
        fvar = tk.StringVar(value=fmt)
        seg = tk.Frame(ust, bg=R["bg"])
        seg.pack(side="left")
        seg_lbl = {}
        for deger_, ad_ in (("kisa", "Shorts"), ("uzun", "Uzun video")):
            lb = tk.Label(seg, text=ad_, font=F(9, "orta"), padx=px(12), pady=px(5), cursor="hand2")
            lb.pack(side="left", padx=(0, px(2)))
            lb.bind("<Button-1>", lambda ev, d_=deger_: (fvar.set(d_), seg_boya(), saatleri_kaydet()))
            seg_lbl[deger_] = lb

        def seg_boya():
            for d_, lb in seg_lbl.items():
                sec = fvar.get() == d_
                lb.config(bg=R["ana_btn"] if sec else R["kart2"], fg=R["ana_yazi"] if sec else R["soluk"])
        seg_boya()
        satir = {"kap": kap, "saat": var_, "format": fvar, "gunler": set(range(7) if gunler is None else gunler)}

        def sil():
            saat_satirlari.remove(satir)
            kap.destroy()
            saatleri_kaydet()
        Dugme(ust, "✕", tur="hayalet", boy="kucuk", genislik=px(30), command=sil).pack(side="right")
        alt = tk.Frame(kap, bg=R["bg"])
        alt.pack(fill="x", pady=(px(6), 0))
        gun_lbl = []

        def gun_boya():
            for i_, lb in enumerate(gun_lbl):
                sec = i_ in satir["gunler"]
                lb.config(bg=R["vurgu"] if sec else R["kart2"], fg=R["vurgu_yazi"] if sec else R["soluk"])

        def gun_tikla(i_):
            if i_ in satir["gunler"]:
                if len(satir["gunler"]) > 1:
                    satir["gunler"].discard(i_)
            else:
                satir["gunler"].add(i_)
            gun_boya()
            saatleri_kaydet()
        for i_, ad_ in enumerate(GUN_ADLARI):
            lb = tk.Label(alt, text=ad_, font=F(8, "orta"), width=4, pady=px(4), cursor="hand2")
            lb.pack(side="left", padx=(0, px(3)))
            lb.bind("<Button-1>", lambda ev, i__=i_: gun_tikla(i__))
            gun_lbl.append(lb)
        hepsi = tk.Label(alt, text="her gün", bg=R["bg"], fg=R["vurgu"], font=F(8),
                         cursor="hand2")
        hepsi.pack(side="left", padx=(px(6), 0))
        hepsi.bind("<Button-1>", lambda ev: (satir["gunler"].update(range(7)), gun_boya(), saatleri_kaydet()))
        gun_boya()
        saat_satirlari.append(satir)
        return e

    for e_ in plan_listesi(ayar):
        saat_satiri_ekle(e_["saat"], e_["format"], e_["gunler"])
    ekle_sat = tk.Frame(k, bg=R["kart"])
    ekle_sat.pack(fill="x", pady=(px(2), 0))
    Dugme(ekle_sat, "＋  Shorts saati", tur="hayalet", boy="kucuk",
          command=lambda: (lambda e: e and e.focus_set())(saat_satiri_ekle(""))).pack(side="left")
    Dugme(ekle_sat, "＋  Uzun video saati", tur="hayalet", boy="kucuk",
          command=lambda: (lambda e: e and e.focus_set())(saat_satiri_ekle("", "uzun", [5, 6]))).pack(
        side="left", padx=px(8))
    g = tk.Frame(k, bg=R["kart"])
    g.pack(fill="x", pady=(px(14), 0))
    etiket(g, "Kaç gün ilerisi hazırlansın", soluk=True).pack(side="left")
    gun_var = degisken("plan_gun", tk.IntVar)
    ttk.Spinbox(g, from_=1, to=7, width=4, textvariable=gun_var).pack(side="left", padx=px(10))

    def plan_ozet():
        pl = plan_listesi(ayar)
        kisa = sum(len(e["gunler"]) for e in pl if e["format"] == "kisa")
        uzun = sum(len(e["gunler"]) for e in pl if e["format"] == "uzun")
        parca = [f"haftada {kisa} Shorts"] + ([f"{uzun} uzun video"] if uzun else [])
        return " + ".join(parca).capitalize() + "."
    plan_bilgi = etiket(k, "", soluk=True, boyut=9)
    plan_bilgi.pack(anchor="w", pady=(px(8), 0))
    gun_var.trace_add("write", lambda *_: plan_yenile())
    plan_bilgi.config(text=plan_ozet())

    pbt = tk.Frame(psol, bg=R["bg"])
    pbt.pack(fill="x", pady=(0, px(12)))
    plan_btn = Dugme(pbt, "Planı şimdi doldur", tur="ana", boy="buyuk")
    plan_btn.pack(side="left", fill="x", expand=True)
    kilitli.append(plan_btn)
    dur_btn = Dugme(pbt, "Durdur", tur="hayalet", boy="buyuk")
    dur_btn.pack(side="left", padx=(px(10), 0))
    dur_btn.config(state="disabled")
    yenile_btn = Dugme(psol, "Planlı videoları yenile  ·  BETA", tur="hayalet")
    yenile_btn.pack(fill="x", pady=(0, px(12)))
    kilitli.append(yenile_btn)

    def plan_yenile_penceresi():
        """Planlı videolardan seçilenleri yayından kaldırır (gizliye alır) ve yerlerine yenilerini hazırlatır."""
        liste = planli_videolar()
        if not liste:
            messagebox.showinfo("Planlı videolar", "İleri tarihe planlanmış video yok.")
            return
        d = tk.Toplevel(p)
        d.title("Planlı videoları yenile")
        pencere_belir(d)
        d.after(10, lambda: pencere_koyu_baslik(d, koyu_tema))
        d.configure(bg=R["kart"], padx=px(24), pady=px(20))
        d.geometry(f"{px(720)}x{min(px(720), p.winfo_screenheight() - px(120))}")
        d.transient(p)
        d.grab_set()
        tk.Label(d, text="Planlı videoları yenile", bg=R["kart"], fg=R["yazi"], font=F(16, "orta")).pack(anchor="w")
        acik = tk.Label(d, text="Seçtiğin videolar yayından kaldırılır: YouTube'da gizliye alınır ve yayın saatleri "
                                "silinir. Videolar silinmez; istersen sonra Studio'dan kendin silebilir ya da geri "
                                "açabilirsin. Boşalan saatlere yeni hikâye kurallarıyla video hazırlanır.",
                        bg=R["kart"], fg=R["soluk"], font=F(9), justify="left", anchor="w", wraplength=px(660))
        acik.pack(fill="x", pady=(px(4), px(12)))
        alt = tk.Frame(d, bg=R["kart"])
        alt.pack(side="bottom", fill="x", pady=(px(14), 0))
        ayr = tk.Frame(d, bg=R["kart"])
        ayr.pack(side="bottom", fill="x", pady=(px(10), 0))
        _ld, lf = kaydirma(d)
        _ld.pack(fill="both", expand=True)
        for w_ in (_ld, lf) + tuple(_ld.winfo_children()):
            try:
                w_.config(bg=R["kart"])
            except tk.TclError:
                pass
        secili = {}

        def satir(t, k_):
            eski = (k_.get("tarih") or "") < KURAL_DEGISIMI
            secili[k_["video_id"]] = tk.BooleanVar(value=eski)
            f = tk.Frame(lf, bg=R["kart"])
            f.pack(fill="x", pady=px(3))
            Anahtar(f, f"{GUN_ADLARI[t.weekday()]} {t:%d.%m %H:%M}  ·  {(k_.get('baslik') or '').replace(' #shorts', '')}",
                    secili[k_["video_id"]], "Eski kurallarla üretildi" if eski else "Yeni kurallarla üretildi").pack(
                fill="x")
        for t, k_ in liste:
            satir(t, k_)
        etiket(ayr, "Boşalan saatlerden şimdi kaç tanesi doldurulsun", soluk=True, boyut=9).pack(side="left")
        adet_var = tk.IntVar(value=4)
        ttk.Spinbox(ayr, from_=0, to=12, width=4, textvariable=adet_var).pack(side="left", padx=px(8))
        etiket(ayr, "(YouTube kotası günde ~6 yükleme)", soluk=True, boyut=8).pack(side="left")
        gece_var = tk.BooleanVar(value=True)
        Anahtar(d, "Kalanları her gece otomatik hazırla", gece_var,
                "Yayın planındaki 'Her gün otomatik hazırla' görevini açar.").pack(side="bottom", fill="x",
                                                                                  pady=(px(10), 0))

        def uygula():
            secilenler = [k_ for _, k_ in liste if secili[k_["video_id"]].get()]
            if not secilenler:
                messagebox.showwarning("Planlı videolar", "Hiç video seçmedin.", parent=d)
                return
            adet = max(0, int(adet_var.get() or 0))
            gece = gece_var.get()
            d.grab_release()
            d.destroy()
            if gece and not gorev_var.get():
                gorev_var.set(True)
            a = dict(ayar)

            def is_():
                asama("Planlı videolar yayından kaldırılıyor", 2)
                for i, k_ in enumerate(secilenler):
                    iptal_kontrol()
                    try:
                        plandan_cek(k_, log)
                    except IptalHatasi:
                        raise
                    except Exception as e:
                        log(f"[X] Kaldırılamadı: {k_.get('baslik', '')}: {str(e)[:200]}")
                    asama(None, 2 + 8 * (i + 1) / len(secilenler))
                log(f"[✓] {len(secilenler)} video yayından kaldırıldı (gizli). Studio'dan istersen silebilirsin.")
                ui(plan_yenile)
                if adet:
                    plan_doldur(a, log, asama, durdur=lambda: durum["durdur"], en_fazla=adet,
                                video_bitti=lambda kayit: (ui(lambda: son_goster(kayit)), ui(plan_yenile)))
                else:
                    asama("Planlı videolar kaldırıldı", 100)
            is_baslat(is_, seri=True, mod="plan", yukleme_var=bool(adet), baslik_="Planlı videoları yenile")
        Dugme(alt, f"Seçilenleri kaldır ve yenilerini hazırla", tur="yesil", command=uygula).pack(side="right")
        Dugme(alt, "Vazgeç", tur="hayalet", command=lambda: (d.grab_release(), d.destroy())).pack(
            side="right", padx=px(8))
    yenile_btn.config(command=plan_yenile_penceresi)

    k = kart(psol, "⏰  Her gün otomatik hazırla",
             "Açıkken Windows her gün aşağıdaki saatte bu programı arka planda çalıştırır ve boş yayın saatlerini "
             "doldurur. Bilgisayar o saatte kapalıysa, açıldığında çalışır.", sarma=440)
    gorev_var = tk.BooleanVar(value=False)
    gs = tk.Frame(k, bg=R["kart"])
    gs.pack(fill="x")
    Anahtar(gs, "Otomatik hazırlama", gorev_var).pack(side="left")
    gorev_saat_var = degisken("plan_gorev_saat", tk.StringVar)
    ttk.Entry(gs, textvariable=gorev_saat_var, width=7, justify="center", font=F(11, "orta")).pack(side="right")
    etiket(gs, "Çalışma saati", soluk=True, boyut=9).pack(side="right", padx=px(8))
    gorev_lbl = etiket(k, "Durum kontrol ediliyor...", soluk=True, boyut=9, justify="left", anchor="w",
                       wraplength=px(440))
    gorev_lbl.pack(fill="x", pady=(px(10), 0))
    sarmali(gorev_lbl, k, 4)
    gorev_kilit = {"aktif": False}

    def gorev_guncelle():
        def is_():
            d = gorev_durumu()

            def yaz():
                gorev_kilit["aktif"] = True
                gorev_var.set(bool(d))
                gorev_kilit["aktif"] = False
                if os.name != "nt":
                    gorev_lbl.config(text="Bu özellik sadece Windows'ta çalışır.", fg=R["soluk"])
                elif d:
                    gorev_lbl.config(text=f"✓ Kurulu  ·  sonraki çalışma: {d['sonraki']}"
                                          + (f"  ·  son çalışma: {d['son']}" if d["son"] else ""), fg=R["yesil2"])
                else:
                    gorev_lbl.config(text="Kapalı. Açarsan her gün otomatik hazırlanır.", fg=R["soluk"])
                if d:
                    oto_hap.ayarla("Otomatik yayın açık", R["basari_bg"], R["yesil2"])
                else:
                    oto_hap.ayarla("Otomatik yayın kapalı", R["kart2"], R["soluk"])
            ui(yaz)
        threading.Thread(target=is_, daemon=True).start()

    def gorev_degisti(*_):
        if gorev_kilit["aktif"]:
            return
        acik = gorev_var.get()

        def is_():
            try:
                if acik:
                    gorev_kur(ayar.get("plan_gorev_saat", "03:00"))
                    log(f"[✓] Otomatik hazırlama kuruldu: her gün {ayar.get('plan_gorev_saat')}")
                else:
                    gorev_kaldir()
                    log("[~] Otomatik hazırlama kapatıldı.")
            except Exception as e:
                mesaj = str(e)[:300]
                log(f"[X] Otomatik görev: {mesaj}")
                ui(lambda: messagebox.showerror("Otomatik görev", mesaj))
            gorev_guncelle()
        threading.Thread(target=is_, daemon=True).start()
    gorev_var.trace_add("write", gorev_degisti)

    def gorev_saat_degisti(_=None):
        if not saat_coz(gorev_saat_var.get()):
            gorev_lbl.config(text="⚠ Saat biçimi: 03:00 gibi yaz.", fg=R["sari"])
            return
        if gorev_var.get():
            gorev_degisti()
    for olay in ("<FocusOut>", "<Return>"):
        gs.winfo_children()[-2].bind(olay, gorev_saat_degisti)

    k = kart(psag, "⚡  Hızlı seri", "Planı beklemeden hemen birkaç video üretir.", sarma=420, alta=True)
    g = tk.Frame(k, bg=R["kart"])
    g.pack(fill="x")
    etiket(g, "Adet", soluk=True).pack(side="left")
    ttk.Spinbox(g, from_=1, to=30, width=4, textvariable=degisken("oto_adet", tk.IntVar)).pack(side="left",
                                                                                              padx=px(10))
    Anahtar(g, "Hemen YouTube'a yükle", degisken("oto_yukle", tk.BooleanVar)).pack(side="left", padx=(px(10), 0))
    seri_btn = Dugme(g, "Başlat", tur="ana")
    seri_btn.pack(side="right")
    kilitli.append(seri_btn)
    seri_ozet = etiket(k, "", soluk=True, boyut=9)
    seri_ozet.pack(anchor="w", pady=(px(8), 0))

    # sağ: yaklaşan yayınlar
    k = kart(psag, "🗓  Yaklaşan yayınlar", dolu=True)
    ust_ = tk.Frame(k, bg=R["kart"])
    ust_.pack(fill="x", pady=(0, px(8)))
    plan_sayac = etiket(ust_, "", soluk=True, boyut=9)
    plan_sayac.pack(side="left")
    Dugme(ust_, "↻  Yenile", tur="hayalet", boy="kucuk", command=lambda: plan_yenile()).pack(side="right")
    pf = tk.Frame(k, bg=R["kart"])
    pf.pack(fill="both", expand=True)
    plan_agac = ttk.Treeview(pf, columns=("gun", "saat", "format", "durum", "baslik"), show="headings",
                             selectmode="browse")
    for kol, bas_, gn, esnek in [("gun", "Gün", 85, False), ("saat", "Saat", 52, False), ("format", "Tür", 62, False),
                                 ("durum", "Durum", 100, False), ("baslik", "Video", 180, True)]:
        plan_agac.heading(kol, text=bas_, anchor="w")
        plan_agac.column(kol, width=px(gn), stretch=esnek, anchor="w")
    pkay = ttk.Scrollbar(pf, orient="vertical", command=plan_agac.yview)
    plan_agac.configure(yscrollcommand=pkay.set)
    plan_agac.pack(side="left", fill="both", expand=True)
    pkay.pack(side="right", fill="y")
    plan_agac.tag_configure("bos", foreground=R["sari"])
    plan_agac.tag_configure("hazir", foreground=R["yesil2"])
    plan_agac.tag_configure("gecti", foreground=R["soluk"])
    plan_agac.bind("<Double-1>", lambda e: (lambda s_: s_ and plan_agac.set(s_[0], "baslik") and
                                            durum.get("plan_url", {}).get(s_[0]) and
                                            webbrowser.open(durum["plan_url"][s_[0]]))(plan_agac.selection()))

    GUNLER = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]

    def plan_yenile():
        simdi = datetime.datetime.now().astimezone()
        kayitlar = plan_kayitlari()
        slotlar = {_slot_anahtar(t): (t, f) for t, f in plan_slotlari(ayar, simdi, gecmis_dahil=True)}
        for anah, kayit in kayitlar.items():          # plandaki saat değişse de yüklenmiş videolar görünür
            try:
                t = datetime.datetime.strptime(anah, "%Y-%m-%dT%H:%M").astimezone()
            except ValueError:
                continue
            if t > simdi - datetime.timedelta(hours=12):
                slotlar[anah] = (t, kayit.get("uzunluk", "kisa"))
        plan_agac.delete(*plan_agac.get_children())
        durum["plan_url"] = {}
        bos_say = hazir_say = 0
        for anah, (t, fmt) in sorted(slotlar.items(), key=lambda x: x[1][0]):
            kayit = kayitlar.get(anah)
            bugun = t.date() == simdi.date()
            gun = "Bugün" if bugun else ("Yarın" if t.date() == (simdi + datetime.timedelta(days=1)).date()
                                          else f"{GUNLER[t.weekday()]} {t:%d.%m}")
            if t <= simdi:
                d_, et = ("Yayınlandı" if kayit else "Geçti"), "gecti"
            elif kayit:
                d_, et = "Hazır", "hazir"
                hazir_say += 1
            else:
                d_, et = "Boş", "bos"
                bos_say += 1
            plan_agac.insert("", "end", iid=anah, tags=(et,),
                             values=(gun, t.strftime("%H:%M"), "Uzun video" if fmt == "uzun" else "Shorts", d_,
                                     (kayit or {}).get("baslik", "—")))
            if kayit and kayit.get("url"):
                durum["plan_url"][anah] = kayit["url"]
        plan_sayac.config(text=f"{hazir_say} hazır  ·  {bos_say} boş")

    # ======================================================================
    # SAYFA: VİDEOLARIM
    # ======================================================================
    sk = sayfa("kutup")
    # --- özet kartları (toplamlar) ---
    ozet_f = tk.Frame(sk, bg=R["bg"])
    ozet_f.pack(fill="x", pady=(0, px(12)))
    ozet_lbl = {}
    for i, (anah, ad_, renk) in enumerate([("video", "Video", R["yazi"]), ("izlenme", "Toplam görüntüleme", R["yazi"]),
                                            ("begeni", "Beğeni", R["yazi"]), ("yorum", "Yorum", R["yazi"])]):
        ozet_f.grid_columnconfigure(i, weight=1, uniform="o")
        kf = yuvarlak_kart(ozet_f, bg=R["kart"], padx=px(16),
                      pady=px(10))
        kf.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else px(10), 0))
        ozet_lbl[anah] = tk.Label(kf, text="–", bg=R["kart"], fg=renk, font=F(18, "orta"))
        ozet_lbl[anah].pack(anchor="w")
        tk.Label(kf, text=ad_, bg=R["kart"], fg=R["soluk"], font=F(9)).pack(anchor="w")
    ust_bar = tk.Frame(sk, bg=R["bg"])
    ust_bar.pack(fill="x", pady=(0, px(10)))
    canli_lbl = tk.Label(ust_bar, text="● Canlı istatistik: YouTube bağlantısı bekleniyor", bg=R["bg"],
                         fg=R["soluk"], font=F(9))
    canli_lbl.pack(side="left")
    Dugme(ust_bar, "📂  Çıktı klasörü", boy="kucuk", command=lambda: klasor_ac(CIKTI)).pack(side="right")
    Dugme(ust_bar, "↻  Şimdi yenile", tur="hayalet", boy="kucuk",
          command=lambda: canli_yenile(zorla=True)).pack(side="right", padx=px(8))

    govde = tk.Frame(sk, bg=R["bg"])
    govde.pack(fill="both", expand=True)
    agac_f = yuvarlak_kart(govde, bg=R["kart"])
    KOLONLAR = [("tarih", "Tarih", 92, False), ("baslik", "Başlık", 150, True), ("durum", "Durum", 100, False),
                ("izlenme", "Görüntüleme", 96, False), ("begeni", "Beğeni", 70, False),
                ("yorum", "Yorum", 66, False), ("sure", "Süre", 50, False)]
    agac = ttk.Treeview(agac_f, columns=[k_[0] for k_ in KOLONLAR], show="headings", selectmode="browse")
    durum["sirala"] = ("tarih", True)

    def sirala(kol):
        eski, ters = durum["sirala"]
        durum["sirala"] = (kol, not ters if eski == kol else True)
        kutuphane_yenile()
    for kol, bas_, gn, esnek in KOLONLAR:
        agac.heading(kol, text=bas_, anchor="w", command=lambda k_=kol: sirala(k_))
        agac.column(kol, width=px(gn), stretch=esnek, anchor="e" if kol in ("izlenme", "begeni", "yorum") else "w")
    kay = ttk.Scrollbar(agac_f, orient="vertical", command=agac.yview)
    agac.configure(yscrollcommand=kay.set)
    agac.pack(side="left", fill="both", expand=True)
    kay.pack(side="right", fill="y")
    agac.tag_configure("yuklendi", foreground=R["yesil2"])
    agac.tag_configure("bekliyor", foreground=R["sari"])
    agac.tag_configure("planli", foreground=R["mavi"])
    agac.tag_configure("yok", foreground=R["soluk"])
    agac.tag_configure("silindi", foreground=R["kirmizi"])

    dty_d, dty = kaydirma(govde)
    dty_d.configure(width=px(310))
    dty_d.pack(side="right", fill="y", padx=(px(14), 0))
    dty_d.pack_propagate(False)
    agac_f.pack(side="left", fill="both", expand=True)
    dk = kart(dty)
    kut_resim = tk.Label(dk, text="Bir video seç", bg=R["kart2"], fg=R["soluk"], height=10)
    kut_resim.pack(fill="x")
    kut_baslik = tk.Label(dk, text="", bg=R["kart"], fg=R["yazi"], font=F(10, "orta"), wraplength=px(270),
                          justify="left", anchor="w")
    kut_baslik.pack(fill="x", pady=(px(10), px(2)))
    kut_bilgi = tk.Label(dk, text="", bg=R["kart"], fg=R["soluk"], font=F(9), wraplength=px(270),
                         justify="left", anchor="w")
    kut_bilgi.pack(fill="x")

    # --- istatistik kutucukları ---
    stat_f = tk.Frame(dk, bg=R["kart"])
    stat_f.pack(fill="x", pady=(px(12), 0))
    stat_lbl = {}
    KUTULAR = [("izlenme", "Görüntüleme", R["yazi"]), ("begeni", "Beğeni", R["yazi"]), ("yorum", "Yorum", R["yazi"]),
               ("shares", "Paylaşım", R["yazi"]), ("averageViewDuration", "Ort. izlenme", R["yazi"]),
               ("averageViewPercentage", "İzlenme oranı", R["yazi"]),
               ("estimatedMinutesWatched", "İzlenme süresi", R["yazi"]), ("subscribersGained", "Yeni abone", R["yesil2"])]
    for i, (anah, ad_, renk) in enumerate(KUTULAR):
        stat_f.grid_columnconfigure(i % 2, weight=1, uniform="s")
        kf = tk.Frame(stat_f, bg=R["kart2"], padx=px(10), pady=px(7))
        kf.grid(row=i // 2, column=i % 2, sticky="nsew", padx=(0 if i % 2 == 0 else px(6), 0), pady=(0, px(6)))
        stat_lbl[anah] = tk.Label(kf, text="–", bg=R["kart2"], fg=renk, font=F(13, "orta"), anchor="w")
        stat_lbl[anah].pack(fill="x")
        tk.Label(kf, text=ad_, bg=R["kart2"], fg=R["soluk"], font=F(8), anchor="w").pack(fill="x")
    analitik_lbl = tk.Label(dk, text="", bg=R["kart"], fg=R["soluk"], font=F(8), wraplength=px(270),
                            justify="left", anchor="w")
    analitik_lbl.pack(fill="x", pady=(px(2), 0))
    etiket(dk, "İzleyici tutma", kalin=True, boyut=9).pack(anchor="w", pady=(px(12), 0))
    etiket(dk, "Videonun her anında izleyicilerin yüzde kaçının hâlâ izlediği", soluk=True, boyut=8,
           wraplength=px(270), justify="left").pack(anchor="w")
    gr_tutma = Grafik(dk, 120, "Bir video seç")
    gr_tutma.pack(fill="x", pady=(px(6), 0))
    tutma_onbellek = {}

    def tutma_ciz(kayit, veri):
        sure_ = float(kayit.get("sure") or 0)
        if not veri:
            gr_tutma.bos("YouTube bu veriyi videonun ilk izlenmelerinden 1–2 gün sonra hazırlar.")
            return

        def zaman(oran):
            sn = oran * sure_
            return f"{int(sn // 60)}:{int(sn % 60):02d}" if sure_ else f"%{oran * 100:.0f}"
        gr_tutma.cizgi([o for o, _ in veri], [y * 100 for _, y in veri], bicim=lambda x: f"%{x:.0f}",
                       x_bicim=zaman, y_ust=max(100, max(y * 100 for _, y in veri)),
                       ipucu=lambda i: f"{zaman(veri[i][0])}\n%{veri[i][1] * 100:.0f} izliyor")

    def tutma_getir(kayit):
        vid = kayit.get("video_id")
        if not vid or (kayit.get("istatistik") or {}).get("silindi"):
            gr_tutma.bos("Yüklenmemiş videoların tutma verisi yok.")
            return
        onb = tutma_onbellek.get(vid)
        if onb and time.time() - onb[0] < 1800:
            tutma_ciz(kayit, onb[1])
            return
        gr_tutma.bos("Yükleniyor...")

        def is_():
            try:
                veri = video_tutma(kayit)
                tutma_onbellek[vid] = (time.time(), veri)
                ui(lambda: durum.get("secili") and durum["secili"].get("video_id") == vid and tutma_ciz(kayit, veri))
            except Exception as e:
                m = str(e)[:140]
                ui(lambda: gr_tutma.bos(f"Alınamadı: {m}"))
        threading.Thread(target=is_, daemon=True).start()

    kut_btnler = {}
    for anahtar, metin, tur in [("oynat", "▶  Oynat", "ikincil"), ("goster", "📂  Klasörde göster", "ikincil"),
                                ("duzenle", "✏  Düzenle ve yükle", "yesil"), ("yt", "🔗  YouTube'da aç", "ikincil"),
                                ("kapak", "🖼  Kapak oluştur / yükle", "ikincil"),
                                ("itiraz", "📋  İtiraz metnini kopyala", "ikincil"),
                                ("sil", "🗑  Listeden kaldır", "hayalet")]:
        b = Dugme(dk, metin, tur=tur, boy="kucuk")
        b.pack(fill="x", pady=(px(6), 0))
        b.config(state="disabled")
        kut_btnler[anahtar] = b

    def sure_yaz(sn):
        sn = int(sn or 0)
        return f"{sn // 60}:{sn % 60:02d}"

    def sayi(n):
        if n is None or n == "":
            return "–"
        n = int(n)
        if n >= 1_000_000:
            return f"{n / 1_000_000:.1f} Mn".replace(".", ",")
        return f"{n:,}".replace(",", ".")

    def kutuphane_yenile():
        secili = agac.selection()
        agac.delete(*agac.get_children())
        g_ = gecmis_oku()
        yuklenen = 0
        top = {"izlenme": 0, "begeni": 0, "yorum": 0}
        simdi = datetime.datetime.now(datetime.timezone.utc)
        satirlar = []
        for i, kayit in enumerate(g_):
            var = os.path.exists(kayit.get("dosya", ""))
            ist = kayit.get("istatistik") or {}
            if kayit.get("video_id"):
                yuklenen += 1
                yz = ist.get("publishAt") or kayit.get("yayin_zamani")
                try:
                    ileride = bool(yz) and datetime.datetime.fromisoformat(yz.replace("Z", "+00:00")) > simdi
                except ValueError:
                    ileride = False
                if ist.get("silindi"):
                    dt, et = "Silinmiş", "silindi"
                elif ileride:
                    dt, et = "Planlandı", "planli"
                elif ist.get("gizlilik") == "private":
                    dt, et = "Özel", "yuklendi"
                elif ist.get("gizlilik") == "unlisted":
                    dt, et = "Liste dışı", "yuklendi"
                else:
                    dt, et = "Herkese açık", "yuklendi"
                for a_ in top:
                    top[a_] += int(ist.get(a_, 0) or 0)
            elif var:
                dt, et = "Yüklenmeyi bekliyor", "bekliyor"
            else:
                dt, et = "Dosya yok", "yok"
            try:
                tarih = datetime.datetime.fromisoformat(kayit.get("tarih", "")).strftime("%d.%m  %H:%M")
            except ValueError:
                tarih = kayit.get("tarih", "")[:16]
            vid = bool(kayit.get("video_id")) and not ist.get("silindi")
            satirlar.append((i, kayit, et, (
                tarih, kayit.get("baslik", kayit.get("konu", "")), dt,
                sayi(ist.get("izlenme")) if vid and ist else "–", sayi(ist.get("begeni")) if vid and ist else "–",
                sayi(ist.get("yorum")) if vid and ist else "–", sure_yaz(kayit.get("sure")))))
        kol, ters = durum["sirala"]
        anahtarlar = {"tarih": lambda r: r[1].get("tarih", ""), "baslik": lambda r: r[1].get("baslik", "").lower(),
                      "durum": lambda r: r[3][2], "sure": lambda r: float(r[1].get("sure") or 0),
                      "izlenme": lambda r: int((r[1].get("istatistik") or {}).get("izlenme", -1)),
                      "begeni": lambda r: int((r[1].get("istatistik") or {}).get("begeni", -1)),
                      "yorum": lambda r: int((r[1].get("istatistik") or {}).get("yorum", -1))}
        satirlar.sort(key=anahtarlar.get(kol, anahtarlar["tarih"]), reverse=ters)
        for i, kayit, et, degerler in satirlar:
            agac.insert("", "end", iid=str(i), tags=(et,), values=degerler)
        for k_, bas_, _gn, _e in KOLONLAR:
            agac.heading(k_, text=bas_ + ((" ▼" if ters else " ▲") if k_ == kol else ""))
        ozet_lbl["video"].config(text=f"{len(g_)}  ·  {yuklenen} yüklü")
        for a_ in top:
            ozet_lbl[a_].config(text=sayi(top[a_]) if yuklenen else "–")
        if secili and agac.exists(secili[0]):
            agac.selection_set(secili[0])

    def stat_goster(kayit, analitik=None):
        ist = kayit.get("istatistik") or {}
        canli_var = bool(kayit.get("video_id")) and ist and not ist.get("silindi")
        for a_ in ("izlenme", "begeni", "yorum"):
            stat_lbl[a_].config(text=sayi(ist.get(a_)) if canli_var else "–")
        a = analitik or {}
        stat_lbl["shares"].config(text=sayi(a.get("shares")) if a else "–")
        stat_lbl["averageViewDuration"].config(text=sure_yaz(a.get("averageViewDuration")) if a else "–")
        stat_lbl["averageViewPercentage"].config(
            text=f"%{float(a.get('averageViewPercentage', 0)):.0f}" if a else "–")
        stat_lbl["estimatedMinutesWatched"].config(
            text=f"{sayi(a.get('estimatedMinutesWatched'))} dk" if a else "–")
        stat_lbl["subscribersGained"].config(text=sayi(a.get("subscribersGained")) if a else "–")

    analitik_onbellek = {}

    def analitik_getir(kayit):
        vid = kayit.get("video_id")
        if not vid or (kayit.get("istatistik") or {}).get("silindi"):
            analitik_lbl.config(text="")
            return
        onb = analitik_onbellek.get(vid)
        if onb and time.time() - onb[0] < 600:
            stat_goster(kayit, onb[1])
            analitik_lbl.config(text=onb[2])
            return
        analitik_lbl.config(text="Detaylı analitik yükleniyor...")

        def is_():
            try:
                a = video_analitik(kayit)
                not_ = ("Detaylı analitik YouTube'da 1–2 gün gecikmeli işlenir." if not a else
                        f"Detaylı analitik · {datetime.datetime.now():%H:%M} (1–2 gün gecikmeli)")
            except Exception as e:
                a, not_ = {}, f"Analitik alınamadı: {str(e)[:160]}"
            analitik_onbellek[vid] = (time.time(), a, not_)

            def yaz():
                if durum.get("secili") and durum["secili"].get("video_id") == vid:
                    stat_goster(durum["secili"], a)
                    analitik_lbl.config(text=not_)
            ui(yaz)
        threading.Thread(target=is_, daemon=True).start()

    def kutup_secim(_=None):
        sec = agac.selection()
        if not sec:
            return
        g_ = gecmis_oku()
        i = int(sec[0])
        if i >= len(g_):
            return
        kayit = g_[i]
        durum["secili"] = kayit
        var = os.path.exists(kayit.get("dosya", ""))
        kut_baslik.config(text=kayit.get("baslik", ""))
        bilgi = f"Konu: {kayit.get('konu', '')}\nSüre: {sure_yaz(kayit.get('sure'))}"
        if kayit.get("plan_slot"):
            bilgi += f"\nYayın saati: {kayit['plan_slot'].replace('T', ' ')}"
        mz = kayit.get("muzik") or {}
        if mz:
            bilgi += f"\nMüzik: {mz.get('baslik') or mz.get('dosya')}" + (" (lisanslı)" if mz.get("lisans") else "")
        kut_bilgi.config(text=bilgi)
        for a_ in ("oynat", "goster", "kapak"):
            kut_btnler[a_].config(state="normal" if var else "disabled")
        kut_btnler["duzenle"].config(state="normal" if var and not kayit.get("video_id") else "disabled")
        kut_btnler["yt"].config(state="normal" if kayit.get("url") else "disabled")
        kut_btnler["itiraz"].config(state="normal" if mz.get("lisans") else "disabled")
        kut_btnler["sil"].config(state="normal")
        if var:
            resim_yukle(kut_resim, kayit["dosya"], "kutup", 190)
        else:
            kut_resim.config(image="", text="Dosya bulunamadı", height=10)
        stat_goster(kayit, (analitik_onbellek.get(kayit.get("video_id")) or (0, None))[1])
        analitik_getir(kayit)
        tutma_getir(kayit)

    # --- canlı istatistik döngüsü (sayfa açıkken her 60 sn) ---
    canli = {"calisiyor": False, "son": 0}

    def canli_yenile(zorla=False):
        if canli["calisiyor"] or not os.path.exists(TOKEN):
            if not os.path.exists(TOKEN):
                canli_lbl.config(text="● Canlı istatistik için YouTube'a bağlan (sol alt)", fg=R["soluk"])
            return
        if not zorla and time.time() - canli["son"] < 55:
            return
        idler = [k_["video_id"] for k_ in gecmis_oku() if k_.get("video_id")]
        if not idler:
            canli_lbl.config(text="● Henüz yüklenmiş video yok", fg=R["soluk"])
            return
        canli["calisiyor"] = True
        canli_lbl.config(text="● Güncelleniyor...", fg=R["sari"])

        def is_():
            try:
                sonuc = canli_istatistik(idler)
                istatistik_kaydet(sonuc)
                canli["son"] = time.time()

                def yaz():
                    canli_lbl.config(text=f"● Canlı  ·  son güncelleme {datetime.datetime.now():%H:%M:%S}  ·  "
                                          "her dakika yenilenir", fg=R["yesil"])
                    kutuphane_yenile()
                    if durum.get("secili") and durum["secili"].get("video_id") in sonuc:
                        durum["secili"]["istatistik"] = sonuc[durum["secili"]["video_id"]]
                        stat_goster(durum["secili"],
                                    (analitik_onbellek.get(durum["secili"]["video_id"]) or (0, None))[1])
                ui(yaz)
            except Exception as e:
                mesaj = str(e)[:140]
                ui(lambda: canli_lbl.config(text=f"● İstatistik alınamadı: {mesaj}", fg=R["kirmizi"]))
            finally:
                canli["calisiyor"] = False
        threading.Thread(target=is_, daemon=True).start()

    def canli_dongu():
        if durum["sayfa"] == "kutup":
            canli_yenile()
        p.after(15000, canli_dongu)
    p.after(3000, canli_dongu)

    agac.bind("<<TreeviewSelect>>", kutup_secim)
    agac.bind("<Double-1>", lambda e: durum["secili"] and klasor_ac(durum["secili"]["dosya"]))
    kut_btnler["oynat"].config(command=lambda: klasor_ac(durum["secili"]["dosya"]))
    kut_btnler["goster"].config(command=lambda: klasorde_goster(durum["secili"]["dosya"]))
    kut_btnler["yt"].config(command=lambda: webbrowser.open(durum["secili"]["url"]))

    def itiraz_kopyala():
        metin = itiraz_metni(durum["secili"])
        if not metin:
            messagebox.showwarning("İtiraz", "Bu videonun müziği için lisans dosyası bulunamadı.")
            return
        p.clipboard_clear()
        p.clipboard_append(metin)
        messagebox.showinfo("İtiraz metni kopyalandı",
                            "YouTube Studio → İçerik → videonun 'Kısıtlamalar' bölümü → Ayrıntılar → İtiraz et\n"
                            "'İzin veya lisansım var' seçeneğini seç ve metni gerekçe kutusuna yapıştır (Ctrl+V).")
    kut_btnler["itiraz"].config(command=itiraz_kopyala)

    def kapak_isle():
        kayit = durum["secili"]

        def is_():
            asama("Kapak hazırlanıyor", 30)
            kapak = kapak_olustur(kayit, log)
            gecmis_kaydet(kayit)
            klasor_ac(kapak)
            if kayit.get("video_id"):
                asama("Kapak YouTube'a yükleniyor", 70)
                kapak_yukle(kayit, log)
            asama("✓ Kapak hazır", 100)
        is_baslat(is_, mod="yukle", yukleme_var=bool(kayit.get("video_id")), baslik_="Kapak resmi")
        uw_baslik_var.set(kayit.get("baslik", ""))
    kut_btnler["kapak"].config(command=kapak_isle)

    def duzenle_yukle():
        duzenle_penceresi(durum["secili"])
    kut_btnler["duzenle"].config(command=duzenle_yukle)

    def listeden_kaldir():
        kayit = durum["secili"]
        if messagebox.askyesno("Listeden kaldır", "Video listeden kaldırılsın mı?\n(Dosyanın kendisi silinmez.)"):
            gecmis_sil(kayit.get("dosya"))
            durum["secili"] = None
            kut_resim.config(image="", text="Bir video seç", height=12)
            kut_baslik.config(text="")
            kut_bilgi.config(text="")
            for b in kut_btnler.values():
                b.config(state="disabled")
            kutuphane_yenile()
    kut_btnler["sil"].config(command=listeden_kaldir)

    # ======================================================================
    # SAYFA: ANALİZ (grafikler)
    # ======================================================================
    _ad, an = kaydirma(sayfa("analiz"))
    _ad.pack(fill="both", expand=True)
    analiz = {"gunluk": None, "oranlar": None, "zaman": 0, "hata": None, "calisiyor": False, "metrik": "izlenme"}

    # --- 1) son 28 gün ---
    k28 = kart(an, "Son 28 gün", "YouTube Analytics verisi; YouTube bu sayıları 1–2 gün gecikmeyle işler.")
    kpi_f = tk.Frame(k28, bg=R["kart"])
    kpi_f.pack(fill="x")
    kpi = {}
    for i, (anah, ad_) in enumerate([("izlenme", "Görüntüleme"), ("saat", "İzlenme süresi (saat)"),
                                     ("abone", "Net abone")]):
        kpi_f.grid_columnconfigure(i, weight=1, uniform="kpi")
        kf = tk.Frame(kpi_f, bg=R["kart"], cursor="hand2", padx=px(4))
        kf.grid(row=0, column=i, sticky="nsew")
        cizgi_ = tk.Frame(kf, bg=R["kart"], height=px(3))
        cizgi_.pack(fill="x", side="bottom")
        l1 = tk.Label(kf, text=ad_, bg=R["kart"], fg=R["soluk"], font=F(9), cursor="hand2")
        l1.pack(anchor="w")
        l2 = tk.Label(kf, text="–", bg=R["kart"], fg=R["yazi"], font=F(20, "orta"), cursor="hand2")
        l2.pack(anchor="w", pady=(px(2), px(8)))
        kpi[anah] = (kf, l1, l2, cizgi_)
        if anah != "saat":
            for w_ in (kf, l1, l2):
                w_.bind("<Button-1>", lambda e, a_=anah: (analiz.update(metrik=a_), analiz_ciz()))
        else:
            for w_ in (kf, l1, l2):
                w_.bind("<Button-1>", lambda e: (analiz.update(metrik="saat"), analiz_ciz()))
    gr28 = Grafik(k28, 230, "Veriler yükleniyor...")
    gr28.pack(fill="x", pady=(px(14), 0))
    an_durum = etiket(k28, "", soluk=True, boyut=8)
    an_durum.pack(anchor="w", pady=(px(8), 0))

    # --- 2) video karşılaştırma | izlenme oranı ---
    iki = tk.Frame(an, bg=R["bg"])
    iki.pack(fill="x")
    iki.grid_columnconfigure(0, weight=1, uniform="iki")
    iki.grid_columnconfigure(1, weight=1, uniform="iki")
    sol_k = tk.Frame(iki, bg=R["bg"])
    sol_k.grid(row=0, column=0, sticky="nsew", padx=(0, px(8)))
    sag_k2 = tk.Frame(iki, bg=R["bg"])
    sag_k2.grid(row=0, column=1, sticky="nsew", padx=(px(8), 0))
    kk = kart(sol_k, "Video karşılaştırma", "Görüntülemeye göre ilk 10 video (canlı sayılar). Çubuğa tıkla: videoyu aç.",
              sarma=380)
    gr_vid = Grafik(kk, 300, "Henüz yayınlanmış video yok.")
    gr_vid.pack(fill="x")
    ko = kart(sag_k2, "İzlenme oranı", "Videonun ortalama yüzde kaçı izlendi. Yüksek oran, izleyicinin sonuna kadar "
                                       "kaldığını gösterir; Shorts'ta algoritmanın en çok baktığı sinyal budur.",
              sarma=380)
    gr_oran = Grafik(ko, 300, "Veriler yükleniyor...")
    gr_oran.pack(fill="x")

    # --- 3) en iyi yayın saati | başarılı konular ---
    uc = tk.Frame(an, bg=R["bg"])
    uc.pack(fill="x")
    uc.grid_columnconfigure(0, weight=1, uniform="uc")
    uc.grid_columnconfigure(1, weight=1, uniform="uc")
    sol_u = tk.Frame(uc, bg=R["bg"])
    sol_u.grid(row=0, column=0, sticky="nsew", padx=(0, px(8)))
    sag_u = tk.Frame(uc, bg=R["bg"])
    sag_u.grid(row=0, column=1, sticky="nsew", padx=(px(8), 0))
    ks_ = kart(sol_u, "En iyi yayın saati", "Yayın saatine göre (3 saatlik dilimler) ortalama görüntüleme. "
                                           "İlk 24 saatini doldurmamış videolar sayılmaz.", sarma=380)
    gr_saat = Grafik(ks_, 200, "Henüz yeterli video yok.")
    gr_saat.pack(fill="x")
    saat_oneri = etiket(ks_, "", soluk=True, boyut=9, justify="left", anchor="w", wraplength=px(380))
    saat_oneri.pack(fill="x", pady=(px(10), 0))
    sarmali(saat_oneri, ks_, 4)
    kf_ = kart(sag_u, "Başarılı konulardan fikir",
               "Açıkken 'Fikir bul' ve otomatik yayın, en iyi performans gösteren videolarına benzeyen (ama aynısı "
               "olmayan) konular üretir. Fikirlerin %30'u yine tamamen yeni yönlerden gelir.", sarma=380)
    Anahtar(kf_, "Fikirleri başarılı videolarıma göre üret", degisken("fikir_basari", tk.BooleanVar)).pack(fill="x")
    etiket(kf_, "Şu an örnek alınan videolar", soluk=True, boyut=9).pack(anchor="w", pady=(px(14), px(4)))
    basari_f = tk.Frame(kf_, bg=R["kart"])
    basari_f.pack(fill="x")

    def oran_kaydet(oranlar):
        with _gecmis_kilit:
            g_ = gecmis_oku()
            for k_ in g_:
                o = oranlar.get(k_.get("video_id"))
                if o:
                    k_["izlenme_orani"] = round(o["oran"], 1)
                    k_["ort_izleme"] = round(o["sure"], 1)
            _json_yaz(GECMIS_DOSYA, g_)

    def analiz_yenile(zorla=False):
        if analiz["calisiyor"]:
            return
        if not os.path.exists(TOKEN):
            analiz["hata"] = "Grafikler için YouTube'a bağlan (sol alt)."
            analiz_ciz()
            return
        if not zorla and analiz["gunluk"] is not None and time.time() - analiz["zaman"] < 600:
            analiz_ciz()
            return
        analiz["calisiyor"] = True
        an_durum.config(text="Güncelleniyor...")

        def is_():
            hata = None
            try:
                gunluk = kanal_gunluk(28)
            except Exception as e:
                gunluk, hata = None, str(e)[:200]
            idler = [k_["video_id"] for k_ in gecmis_oku()
                     if k_.get("video_id") and not (k_.get("istatistik") or {}).get("silindi")]
            try:
                oranlar = videolar_analitik(idler) if idler else {}
                oran_kaydet(oranlar)
            except Exception as e:
                oranlar, hata = None, hata or str(e)[:200]

            def yaz():
                analiz.update(gunluk=gunluk if gunluk is not None else analiz["gunluk"],
                              oranlar=oranlar if oranlar is not None else analiz["oranlar"],
                              zaman=time.time(), hata=hata, calisiyor=False)
                analiz_ciz()
                panel_grafik_ciz()
            ui(yaz)
        threading.Thread(target=is_, daemon=True).start()

    def analiz_ciz():
        g_ = gecmis_oku()
        # 1) son 28 gün
        gun = analiz["gunluk"]
        met = analiz["metrik"]
        for anah, (kf, l1, l2, cz) in kpi.items():
            sec = anah == met
            cz.config(bg=R["grafik"] if sec else R["kart"])
            l1.config(fg=R["yazi"] if sec else R["soluk"])
        if gun:
            top_i = sum(x["izlenme"] for x in gun)
            top_s = sum(x["dakika"] for x in gun) / 60
            top_a = sum(x["abone"] for x in gun)
            sayac_anim(kpi["izlenme"][2], top_i, lambda x: sayi(int(round(x))))
            sayac_anim(kpi["saat"][2], top_s, lambda x: f"{x:.1f}".replace(".", ","))
            kpi["abone"][2].config(text=("+" if top_a > 0 else "") + sayi(top_a) if top_a >= 0 else str(top_a))
            if met == "izlenme":
                gr28.cizgi([x["gun"] for x in gun], [x["izlenme"] for x in gun], bicim=sayi, x_bicim=gun_etiket,
                           ipucu=lambda i: f"{gun_etiket(gun[i]['gun'])}\n{sayi(gun[i]['izlenme'])} görüntüleme")
            elif met == "saat":
                gr28.cizgi([x["gun"] for x in gun], [round(x["dakika"]) for x in gun], bicim=sayi,
                           x_bicim=gun_etiket,
                           ipucu=lambda i: f"{gun_etiket(gun[i]['gun'])}\n{gun[i]['dakika']:.0f} dakika izlendi")
            else:
                # net abone günlük değişim; negatifler 0'da gösterilir, değer ipucunda
                gr28.cizgi([x["gun"] for x in gun], [max(0, x["abone"]) for x in gun], bicim=sayi,
                           x_bicim=gun_etiket,
                           ipucu=lambda i: f"{gun_etiket(gun[i]['gun'])}\n{gun[i]['abone']:+d} abone")
        else:
            gr28.bos(analiz["hata"] or "Veriler yükleniyor...")
        an_durum.config(text=(f"Hata: {analiz['hata']}" if analiz["hata"] else
                              f"Son güncelleme {datetime.datetime.fromtimestamp(analiz['zaman']):%H:%M}"
                              if analiz["zaman"] else ""), fg=R["kirmizi"] if analiz["hata"] else R["soluk"])
        # 2) video karşılaştırma (canlı sayılar, analitik gerekmez)
        yay = [k_ for k_ in g_ if k_.get("video_id") and not (k_.get("istatistik") or {}).get("silindi")
               and (k_.get("istatistik") or {}).get("izlenme") is not None]
        yay.sort(key=lambda k_: int(k_["istatistik"]["izlenme"]), reverse=True)
        ilk = yay[:10]
        if ilk:
            gr_vid.cubuk([k_.get("baslik", "").replace(" #shorts", "") for k_ in ilk],
                         [int(k_["istatistik"]["izlenme"]) for k_ in ilk], bicim=sayi,
                         ipucu=lambda i: f"{ilk[i].get('baslik', '')}\n{sayi(ilk[i]['istatistik']['izlenme'])} "
                                         "görüntüleme · tıkla: aç",
                         tikla=lambda i: ilk[i].get("url") and webbrowser.open(ilk[i]["url"]))
        else:
            gr_vid.bos("Henüz yayınlanmış video yok. İçerik sayfası açıkken canlı sayılar güncellenir.")
        # 2b) izlenme oranı
        orl = [(k_, k_.get("izlenme_orani")) for k_ in g_ if k_.get("izlenme_orani") is not None
               and k_.get("video_id") and not (k_.get("istatistik") or {}).get("silindi")]
        orl.sort(key=lambda x: x[1], reverse=True)
        orl = orl[:10]
        if orl:
            ort = sum(o for _, o in orl) / len(orl)
            gr_oran.cubuk([k_.get("baslik", "").replace(" #shorts", "") for k_, _ in orl], [o for _, o in orl],
                          bicim=lambda x: f"%{x:.0f}", referans=ort, ref_etiket=f"ortalama %{ort:.0f}",
                          ipucu=lambda i: (f"{orl[i][0].get('baslik', '')}\n%{orl[i][1]:.0f} izlendi · ortalama "
                                           f"{orl[i][0].get('ort_izleme', 0):.0f} sn"))
        else:
            gr_oran.bos(analiz["hata"] or ("YouTube izlenme oranını 1–2 gün sonra hesaplar."
                                           if analiz["oranlar"] is not None else "Veriler yükleniyor..."))
        # 3) en iyi saat
        gruplar, oneri = saat_analizi(g_)
        if gruplar:
            gr_saat.cubuk([g["etiket"] for g in gruplar], [g["ort"] for g in gruplar],
                          bicim=lambda x: f"{x:.0f}",
                          ipucu=lambda i: (f"{gruplar[i]['etiket']} arası yayınlananlar\nortalama "
                                           f"{gruplar[i]['ort']:.0f} görüntüleme · {gruplar[i]['adet']} video"))
        else:
            gr_saat.bos("Yayınlanıp 24 saati dolmuş video olunca burada görünür.")
        adet = sum(g["adet"] for g in gruplar)
        saat_oneri.config(text=oneri or f"Öneri için en az 6 video ve 2 farklı saat dilimi gerekiyor (şu an {adet} "
                                        "video). Plan saatlerini farklı dilimlere yaymak, hangisinin iyi olduğunu "
                                        "daha hızlı gösterir.",
                          fg=R["yazi"] if oneri else R["soluk"])
        # başarılı konular
        for w_ in basari_f.winfo_children():
            w_.destroy()
        iyi = basarili_konular()
        if iyi:
            for i, b in enumerate(iyi):
                tk.Label(basari_f, text=f"{i + 1}.  {b.replace(' #shorts', '')}", bg=R["kart"], fg=R["yazi"],
                         font=F(9), anchor="w", justify="left").pack(fill="x", pady=px(2))
        else:
            tk.Label(basari_f, text="En az 3 izlenmiş video olunca örnekler burada listelenir. O zamana kadar "
                                    "fikirler her zamanki gibi üretilir.", bg=R["kart"], fg=R["soluk"], font=F(9),
                     anchor="w", justify="left", wraplength=px(360)).pack(fill="x")

    # --- panel: son 28 gün mini grafiği ---
    pk = yuvarlak_kart(sag_k, bg=R["kart"], padx=px(22),
                  pady=px(16))
    pk.pack(fill="x", pady=(px(16), 0))
    pkb = tk.Frame(pk, bg=R["kart"])
    pkb.pack(fill="x")
    tk.Label(pkb, text="Son 28 gün", bg=R["kart"], fg=R["yazi"], font=F(12, "orta")).pack(side="left")
    baglanti(pkb, "Analiz", lambda: sayfa_goster("analiz")).pack(side="right")
    pk_toplam = tk.Label(pk, text="", bg=R["kart"], fg=R["soluk"], font=F(9), anchor="w")
    pk_toplam.pack(fill="x", pady=(px(2), px(8)))
    gr_panel = Grafik(pk, 130, "Veriler yükleniyor...")
    gr_panel.pack(fill="x")

    def panel_grafik_ciz():
        gun = analiz["gunluk"]
        if gun:
            pk_toplam.config(text=f"{sayi(sum(x['izlenme'] for x in gun))} görüntüleme")
            gr_panel.cizgi([x["gun"] for x in gun], [x["izlenme"] for x in gun], bicim=sayi, x_bicim=gun_etiket,
                           ipucu=lambda i: f"{gun_etiket(gun[i]['gun'])}\n{sayi(gun[i]['izlenme'])} görüntüleme")
        else:
            gr_panel.bos(analiz["hata"] or "Veriler yükleniyor...")

    # ======================================================================
    # SAYFA: YORUMLAR (otomatik cevap)
    # ======================================================================
    yp = sayfa("yorumlar")
    yp.grid_columnconfigure(0, weight=5, uniform="y")
    yp.grid_columnconfigure(1, weight=3, uniform="y")
    yp.grid_rowconfigure(0, weight=1)
    ysol = tk.Frame(yp, bg=R["bg"])
    ysol.grid(row=0, column=0, sticky="nsew", padx=(0, px(16)))
    _yd, ysag = kaydirma(yp)
    _yd.grid(row=0, column=1, sticky="nsew")

    # --- sağ: ayarlar ---
    k = kart(ysag, "Otomatik cevap", "Program açıkken yorumlar 2 dakikada bir kontrol edilir; her yeni yoruma "
                                     "Gemini yoruma özel bir cevap yazar. Spam, hakaret ve link içeren yorumlar atlanır.",
             sarma=330)
    yorum_oto_var = degisken("yorum_oto", tk.BooleanVar)
    Anahtar(k, "Yorumlara otomatik cevap ver", yorum_oto_var).pack(fill="x")
    etiket(k, "Cevaplar", soluk=True, boyut=9).pack(anchor="w", pady=(px(14), px(4)))
    mod_f = tk.Frame(k, bg=R["kart"])
    mod_f.pack(anchor="w")
    mod_lbl = {}

    def mod_boya():
        for d_, lb in mod_lbl.items():
            sec = ayar.get("yorum_mod", "oto") == d_
            lb.config(bg=R["ana_btn"] if sec else R["kart2"], fg=R["ana_yazi"] if sec else R["soluk"])
    for d_, ad_ in (("oto", "Hemen gönder"), ("onay", "Önce bana sor")):
        lb = tk.Label(mod_f, text=ad_, font=F(9, "orta"), padx=px(12), pady=px(6), cursor="hand2")
        lb.pack(side="left", padx=(0, px(2)))
        lb.bind("<Button-1>", lambda e, d__=d_: (ayar.update(yorum_mod=d__), ayar_yaz(ayar), mod_boya()))
        mod_lbl[d_] = lb
    mod_boya()
    yorum_gorev_var_ = tk.BooleanVar(value=False)
    p.after(200, lambda: yorum_izin_guncelle())
    Anahtar(k, "Program kapalıyken de kontrol et", yorum_gorev_var_,
            "Bilgisayar açıkken Windows her 10 dakikada bir arka planda kontrol eder.").pack(fill="x",
                                                                                           pady=(px(14), 0))
    izin_f = tk.Frame(k, bg=R["hata_bg"], padx=px(12), pady=px(10))
    izin_lbl = tk.Label(izin_f, text="Yorumlara cevap yazmak için YouTube'dan bir kez ek izin gerekiyor.",
                        bg=R["hata_bg"], fg=R["yazi"], font=F(9), justify="left", anchor="w", wraplength=px(300))
    izin_lbl.pack(fill="x")
    sarmali(izin_lbl, izin_f, 4)
    izin_btn = Dugme(izin_f, "Yorum izni ver", tur="yesil", boy="kucuk")
    izin_btn.pack(anchor="w", pady=(px(8), 0))

    def yorum_izin_guncelle():
        if os.path.exists(TOKEN) and not yorum_izni_var():
            izin_f.pack(fill="x", pady=(px(14), 0), before=yorum_durum_lbl)
        else:
            izin_f.pack_forget()

    def yorum_izni_iste():
        if durum["mesgul"]:
            messagebox.showinfo("Yorumlar", "Şu an bir video hazırlanıyor. İzni iş bitince ver.")
            return
        if not messagebox.askokcancel(
                "Yorum izni",
                "Tarayıcıda Google izin ekranı açılacak.\n\n1) Kanalın bağlı olduğu Google hesabını ve "
                f"'{ayar.get('hedef_kanal', '')}' kanalını seç.\n2) İzin ekranındaki TÜM kutuları işaretle.\n\n"
                "Bağlantı yenilenir; video yükleme ve istatistikler aynen çalışmaya devam eder."):
            return
        yt_baglantiyi_kes()
        yt_durum_guncelle(True)
    izin_btn.config(command=yorum_izni_iste)
    yorum_durum_lbl = etiket(k, "", soluk=True, boyut=9, justify="left", anchor="w", wraplength=px(330))
    yorum_durum_lbl.pack(fill="x", pady=(px(12), 0))
    sarmali(yorum_durum_lbl, k, 4)
    yorum_kontrol_btn = Dugme(k, "Şimdi kontrol et", tur="hayalet", boy="kucuk")
    yorum_kontrol_btn.pack(anchor="w", pady=(px(10), 0))

    k = kart(ysag, "Cevap tarzı", "Cevapların nasıl yazılacağını kendi cümlenle anlat.", sarma=330)
    yorum_stil_var = degisken("yorum_stil", tk.StringVar)
    if not yorum_stil_var.get():
        yorum_stil_var.set(T(VARSAYILAN_YORUM_STIL, VARSAYILAN_YORUM_STIL_EN))
    stil_kutu = tk.Text(k, height=4, font=F(10), bg=R["kart"], fg=R["yazi"], insertbackground=R["yazi"], bd=0,
                        padx=px(10), pady=px(8), wrap="word", highlightthickness=1,
                        highlightbackground=R["cerceve"], highlightcolor=R["vurgu"])
    stil_kutu.pack(fill="x")
    stil_kutu.insert("1.0", yorum_stil_var.get())
    stil_kutu.bind("<FocusOut>", lambda e: yorum_stil_var.set(stil_kutu.get("1.0", "end").strip()
                                                               or T(VARSAYILAN_YORUM_STIL, VARSAYILAN_YORUM_STIL_EN)))
    Dugme(k, "Varsayılan tarz", tur="hayalet", boy="kucuk",
          command=lambda: (stil_kutu.delete("1.0", "end"),
                           stil_kutu.insert("1.0", T(VARSAYILAN_YORUM_STIL, VARSAYILAN_YORUM_STIL_EN)),
                           yorum_stil_var.set(T(VARSAYILAN_YORUM_STIL, VARSAYILAN_YORUM_STIL_EN)))).pack(
        anchor="w", pady=(px(10), 0))
    etiket(k, "Hikâyelerin kurgu olduğu ya da yapay zekayla yapıldığı sorulursa cevap bunu dürüstçe söyler.",
           soluk=True, boyut=8, wraplength=px(330), justify="left").pack(anchor="w", pady=(px(10), 0))

    # --- sol: yorum listesi ---
    yl = yuvarlak_kart(ysol, bg=R["kart"])
    yl.pack(fill="both", expand=True)
    ylb = tk.Frame(yl, bg=R["kart"], padx=px(22), pady=px(16))
    ylb.pack(fill="x")
    tk.Label(ylb, text="Son yorumlar", bg=R["kart"], fg=R["yazi"], font=F(12, "orta")).pack(side="left")
    yorum_say_lbl = tk.Label(ylb, text="", bg=R["kart"], fg=R["soluk"], font=F(9))
    yorum_say_lbl.pack(side="left", padx=px(12))
    yf = tk.Frame(yl, bg=R["kart"])
    yf.pack(fill="both", expand=True, padx=px(8))
    yorum_agac = ttk.Treeview(yf, columns=("yorum", "cevap", "durum"), show="headings", selectmode="browse")
    for kol, bas_, gn, esnek in [("yorum", "Yorum", 150, True), ("cevap", "Cevap", 150, True),
                                 ("durum", "Durum", 110, False)]:
        yorum_agac.heading(kol, text=bas_, anchor="w")
        yorum_agac.column(kol, width=px(gn), minwidth=px(80), stretch=esnek, anchor="w")
    ykay = ttk.Scrollbar(yf, orient="vertical", command=yorum_agac.yview)
    yorum_agac.configure(yscrollcommand=ykay.set)
    yorum_agac.pack(side="left", fill="both", expand=True)
    ykay.pack(side="right", fill="y")
    yorum_agac.tag_configure("soluk", foreground=R["soluk2"])
    yorum_agac.tag_configure("bekliyor", foreground=R["sari"])
    yorum_agac.tag_configure("hata", foreground=R["kirmizi"])

    # seçili yorumun ayrıntısı + düzenleme
    yd = tk.Frame(yl, bg=R["kart"], padx=px(22), pady=px(14))
    yd.pack(fill="x")
    tk.Frame(yl, bg=R["kenar"], height=1).pack(fill="x", before=yd)
    yd_yorum = tk.Label(yd, text="Bir yorum seç", bg=R["kart"], fg=R["soluk"], font=F(10), anchor="w",
                        justify="left", wraplength=px(600))
    yd_yorum.pack(fill="x")
    sarmali(yd_yorum, yd, 4)
    yd_cevap = tk.Text(yd, height=3, font=F(10), bg=R["kart"], fg=R["yazi"], insertbackground=R["yazi"], bd=0,
                       padx=px(10), pady=px(8), wrap="word", highlightthickness=1, highlightbackground=R["cerceve"],
                       highlightcolor=R["vurgu"])
    yd_cevap.pack(fill="x", pady=(px(8), 0))
    yd_btn = tk.Frame(yd, bg=R["kart"])
    yd_btn.pack(fill="x", pady=(px(10), 0))
    yd_gonder = Dugme(yd_btn, "Cevabı gönder", tur="yesil", boy="kucuk")
    yd_gonder.pack(side="right")
    yd_atla = Dugme(yd_btn, "Cevaplama", tur="hayalet", boy="kucuk")
    yd_atla.pack(side="right", padx=(0, px(8)))
    yd_ac = Dugme(yd_btn, "YouTube'da aç", tur="hayalet", boy="kucuk")
    yd_ac.pack(side="left")
    for b_ in (yd_gonder, yd_atla, yd_ac):
        b_.config(state="disabled")
    yorum_kayit = {}
    DURUM_AD = {"gonderildi": "Cevaplandı", "taslak": "Onay bekliyor", "atlandi": "Atlandı", "hata": "Gönderilemedi",
                "yoksay": "Cevaplanmayacak"}

    def yorumlar_yenile():
        v = yorum_oku()
        sec = yorum_agac.selection()
        yorum_agac.delete(*yorum_agac.get_children())
        yorum_kayit.clear()
        bekleyen = 0
        for k_ in reversed(v["kayit"][-200:]):
            d_ = k_.get("durum", "")
            if d_ == "taslak":
                bekleyen += 1
            et = {"taslak": "bekliyor", "hata": "hata", "atlandi": "soluk", "yoksay": "soluk"}.get(d_, "")
            durum_metin = DURUM_AD.get(d_, d_) + (f" · {k_['neden'][:24]}" if d_ == "atlandi" and k_.get("neden")
                                                    else "")
            yorum_agac.insert("", "end", iid=k_["id"], tags=(et,),
                              values=(f"{k_.get('yazar', '')}: {k_.get('yorum', '')}".replace("\n", " "),
                                      (k_.get("cevap") or "—").replace("\n", " "), durum_metin))
            yorum_kayit[k_["id"]] = k_
        if sec and yorum_agac.exists(sec[0]):
            yorum_agac.selection_set(sec[0])
        bugun = v["gunluk"].get(datetime.date.today().isoformat(), 0)
        yorum_say_lbl.config(text=f"bugün {bugun} cevap" + (f"  ·  {bekleyen} onay bekliyor" if bekleyen else ""))
        son = v.get("son_kontrol")
        if son:
            try:
                son = datetime.datetime.fromisoformat(son).strftime("%H:%M")
            except ValueError:
                pass
        acik = yorum_oto_var.get()
        yorum_durum_lbl.config(text=(("Açık · " if acik else "Kapalı · ") + (f"son kontrol {son}" if son else
                                                                             "henüz kontrol edilmedi")),
                               fg=R["yesil2"] if acik else R["soluk"])
        nav_rozet(bekleyen)
        yorum_izin_guncelle()

    def yorum_secildi(_=None):
        s_ = yorum_agac.selection()
        k_ = yorum_kayit.get(s_[0]) if s_ else None
        if not k_:
            return
        yd_yorum.config(text=f"{k_.get('yazar', '')} · {k_.get('video', '')}\n“{k_.get('yorum', '')}”",
                        fg=R["yazi"])
        yd_cevap.delete("1.0", "end")
        yd_cevap.insert("1.0", k_.get("cevap", ""))
        gonderilebilir = k_.get("durum") in ("taslak", "hata", "atlandi", "yoksay")
        yd_gonder.config(state="normal" if gonderilebilir else "disabled",
                         text="Cevabı gönder" if gonderilebilir else "Gönderildi")
        yd_atla.config(state="normal" if k_.get("durum") == "taslak" else "disabled")
        yd_ac.config(state="normal" if k_.get("video_id") else "disabled")
    yorum_agac.bind("<<TreeviewSelect>>", yorum_secildi)

    def yorum_gonder_tikla():
        s_ = yorum_agac.selection()
        k_ = yorum_kayit.get(s_[0]) if s_ else None
        metin = yd_cevap.get("1.0", "end").strip()
        if not k_ or not metin:
            return
        yd_gonder.config(state="disabled", text="Gönderiliyor...")

        def is_():
            try:
                yorum_taslak_gonder(k_["id"], metin)
                ui(yorumlar_yenile)
                ui(yorum_secildi)
            except Exception as e:
                m = str(e)[:300]
                ui(lambda: messagebox.showerror("Yorum", f"Cevap gönderilemedi:\n{m}"))
                ui(yorum_secildi)
        threading.Thread(target=is_, daemon=True).start()
    yd_gonder.config(command=yorum_gonder_tikla)
    yd_atla.config(command=lambda: (lambda s_: s_ and (yorum_durum_degistir(s_[0], "yoksay"), yorumlar_yenile(),
                                                       yorum_secildi()))(yorum_agac.selection()))
    yd_ac.config(command=lambda: (lambda s_: s_ and webbrowser.open(
        f"https://www.youtube.com/watch?v={yorum_kayit[s_[0]]['video_id']}&lc={s_[0]}"))(yorum_agac.selection()))

    yorum_calisiyor = {"v": False, "son": 0}

    def yorum_kontrol(elle=False):
        if yorum_calisiyor["v"]:
            return
        if not os.path.exists(TOKEN):
            if elle:
                messagebox.showwarning("Yorumlar", "Önce YouTube'a bağlan (sol alt).")
            return
        yorum_calisiyor["v"] = True
        yorum_calisiyor["son"] = time.time()
        yorum_kontrol_btn.config(state="disabled", text="Kontrol ediliyor...")

        def is_():
            try:
                s_ = yorum_turu(log)
                if elle or s_.get("yeni"):
                    log(f"[i] Yorumlar: {s_['yeni']} yeni · {s_['gonderilen']} cevaplandı · {s_['taslak']} onay "
                        f"bekliyor · {s_['atlanan']} atlandı")
            except IptalHatasi:
                pass
            except Exception as e:
                m = str(e)
                if "insufficient" in m.lower() or "YORUM_IZNI" in m:
                    m = ("Yorumlara cevap yazmak için YouTube'dan ek izin gerekiyor. Yorumlar sayfasındaki "
                         "'Yorum izni ver' butonuna bas.")
                    ui(yorum_izin_guncelle)
                m = m[:300]
                log(f"[X] Yorumlar: {m}")
                if elle:
                    ui(lambda: messagebox.showwarning("Yorumlar", m))
            finally:
                yorum_calisiyor["v"] = False
                ui(lambda: yorum_kontrol_btn.config(state="normal", text="Şimdi kontrol et"))
                ui(yorumlar_yenile)
        threading.Thread(target=is_, daemon=True).start()
    yorum_kontrol_btn.config(command=lambda: yorum_kontrol(True))

    def yorum_dongu():
        if yorum_oto_var.get() and time.time() - yorum_calisiyor["son"] >= 115:
            yorum_kontrol()
        p.after(20000, yorum_dongu)
    p.after(15000, yorum_dongu)
    yorum_oto_var.trace_add("write", lambda *_: (yorumlar_yenile(), yorum_oto_var.get() and yorum_kontrol()))

    yorum_gorev_kilit = {"v": True}

    def yorum_gorev_degisti(*_):
        if yorum_gorev_kilit["v"]:
            return
        acik = yorum_gorev_var_.get()

        def is_():
            try:
                if acik:
                    yorum_gorev_kur(10)
                    log("[✓] Yorumlar program kapalıyken de her 10 dakikada bir kontrol edilecek.")
                else:
                    yorum_gorev_kaldir()
                    log("[~] Arka plan yorum kontrolü kapatıldı.")
            except Exception as e:
                m = str(e)[:300]
                ui(lambda: messagebox.showerror("Yorumlar", m))
                ui(lambda: (yorum_gorev_kilit.update(v=True), yorum_gorev_var_.set(not acik),
                            yorum_gorev_kilit.update(v=False)))
        threading.Thread(target=is_, daemon=True).start()
    yorum_gorev_var_.trace_add("write", yorum_gorev_degisti)

    def yorum_gorev_oku():
        def is_():
            var_ = yorum_gorev_var()
            ui(lambda: (yorum_gorev_kilit.update(v=True), yorum_gorev_var_.set(var_),
                        yorum_gorev_kilit.update(v=False)))
        threading.Thread(target=is_, daemon=True).start()
    yorum_gorev_oku()

    # ======================================================================
    # SAYFA: SES
    # ======================================================================
    _d, sse = kaydirma(sayfa("ses"))
    _d.pack(fill="both", expand=True)
    k = kart(sse, "🎙  Seslendirme", "Kanalın sesi Gemini ile üretilir. Seçtiğin ses tüm Gemini ses modellerinde aynıdır; "
                                     "biri yanıt vermezse program sıradakini dener.")
    g = tk.Frame(k, bg=R["kart"])
    g.pack(fill="x")
    for i, (et, ad_, har) in enumerate([("Ses motoru", "ses_motoru", MOTORLAR), ("Gemini sesi", "g_ses", GEMINI_SESLER),
                                         ("Edge sesi (yedek)", "ses", SESLER)]):
        etiket(g, et, soluk=True).grid(row=i, column=0, sticky="w", pady=px(5))
        secim(g, ad_, har, 38).grid(row=i, column=1, sticky="w", padx=px(14))
    etiket(g, "Video hızı", soluk=True).grid(row=3, column=0, sticky="w", pady=(px(12), px(4)))
    hiz_kontrol(g).grid(row=3, column=1, sticky="w", padx=px(14), pady=(px(12), px(4)))
    Anahtar(k, "Sadece Gemini sesi kullan (Edge'e hiç geçme)", degisken("ses_sadece_gemini", tk.BooleanVar),
            "Açıkken Gemini sesi alınamazsa video üretilmez; kanala farklı sesli video gitmez. Planlı saat boş kalır "
            "ve bir sonraki doldurmada tekrar denenir. Kapalıyken video Edge sesiyle tamamlanır.").pack(
        fill="x", pady=(px(14), 0))
    etiket(k, "Hız anlatımın temposudur; video da onunla birlikte hızlanır/yavaşlar. "
              "Shorts'ta 40–90 sn sınırı yine korunur.", soluk=True, boyut=9).pack(anchor="w", pady=(px(8), 0))

    k = kart(sse, "🎭  Anlatım tarzı (Gemini)",
             "Sesin nasıl okuyacağını kendi cümlenle yaz. Örn: \"Fısıltıya yakın, ürkütücü bir tonla\" ya da "
             "\"Heyecanlı, hızlı bir YouTube anlatıcısı gibi\".")
    stil_var = degisken("stil", tk.StringVar)
    ttk.Entry(k, textvariable=stil_var).pack(fill="x")
    Dugme(k, "↺  Varsayılan tarz", tur="hayalet", boy="kucuk",
          command=lambda: stil_var.set(T(VARSAYILAN_STIL, VARSAYILAN_STIL_EN))).pack(anchor="w", pady=(px(10), 0))

    k = kart(sse, "🔊  Dene", "Seçtiğin ses, tarz ve hızla kısa bir örnek okutur ve çalar.")
    dene_btn = Dugme(k, "🔊  Sesi dene", tur="yesil")
    dene_btn.pack(anchor="w")

    DENEME_METNI = ("Dün gece kapım çaldığında delikten baktım... ve kapının önünde kendi yüzümü gördüm. "
                    "O an anladım ki, bu gece hiç bitmeyecekti.")

    def sesi_dene():
        a = dict(ayar)
        bas = time.time()
        sayac = {"aktif": True}

        def geri_say():
            if sayac["aktif"]:
                kalan = max(0, 45 - int(time.time() - bas))
                dene_btn.config(state="disabled", text=f"⏳  Gemini modelleri deneniyor... {kalan} sn")
                p.after(500, geri_say)
        if a.get("ses_motoru", "gemini") == "gemini":
            geri_say()
        else:
            dene_btn.config(state="disabled", text="⏳  Hazırlanıyor...")

        def is_():
            try:
                hedef = os.path.join(GECICI, f"deneme_{int(time.time())}.mp3")
                if a.get("ses_motoru", "gemini") != "gemini":
                    ses_olustur(DENEME_METNI, hedef, dict(a, ses_sadece_gemini=False), log, zamanla=False)
                    klasor_ac(hedef)
                    return
                ses = a.get("g_ses", "Enceladus")
                log(f"[+] Ses testi: {ses} sesi tüm Gemini ses modellerinde deneniyor (en fazla 45 sn)...")
                sonuc = gemini_ses_teshis(ses, a.get("stil", "").strip(), tts_metni(DENEME_METNI))
                satirlar = []
                for m, durum_, sure_, _v in sonuc:
                    satirlar.append(f"{durum_}  ·  {m}  ({sure_:.0f} sn)")
                    log(f"    {m}: {durum_} ({sure_:.0f} sn)")
                calisan = next((x for x in sonuc if x[3]), None)
                if calisan:
                    pcm, hz = calisan[3]
                    wav = os.path.join(GECICI, "deneme_ham.wav")
                    with wave.open(wav, "wb") as w:
                        w.setnchannels(1)
                        w.setsampwidth(2)
                        w.setframerate(hz)
                        w.writeframes(pcm)
                    ses_son_islem(wav, hedef, 1 + int(a.get("hiz", 15)) / 100)
                    klasor_ac(hedef)
                    log(f"[✓] Ses testi başarılı; videolarda önce {calisan[0]} kullanılacak.")
                    ui(lambda: messagebox.showinfo(
                        "Ses testi", f"{ses} sesi çalışıyor.\n\n" + "\n".join(satirlar) +
                        f"\n\nVideolarda önce '{calisan[0]}' kullanılacak."))
                else:
                    kota = any("kota" in x[1] for x in sonuc)
                    oneri = ("Gemini'nin ücretsiz ses kotası dolmuş görünüyor. Kota her gün Türkiye saatiyle "
                             "yaklaşık 10:00'da sıfırlanır; faturalandırmayı açmak bu sınırı kaldırır."
                             if kota else
                             "Google'ın ses servisi şu an yanıt vermiyor. Birkaç dakika sonra tekrar dene.")
                    log("[X] Ses testi: hiçbir Gemini ses modeli çalışmadı.")
                    ui(lambda: messagebox.showwarning(
                        "Ses testi", f"{ses} sesi şu an alınamıyor.\n\n" + "\n".join(satirlar) + "\n\n" + oneri))
            except IptalHatasi:
                pass
            except Exception as e:
                mesaj = str(e)[:300]
                log(f"[X] Ses denenemedi: {mesaj}")
                ui(lambda: messagebox.showerror("Ses testi", mesaj))
            finally:
                sayac["aktif"] = False
                ui(lambda: dene_btn.config(state="normal", text="🔊  Sesi dene"))
        threading.Thread(target=is_, daemon=True).start()
    dene_btn.config(command=sesi_dene)

    # ======================================================================
    # SAYFA: AYARLAR
    # ======================================================================
    a_sol, a_sag = iki_kolon(sayfa("ayar"), 1, 1)

    k = kart(a_sol, "Kanal", f"Bu pencere '{profil_adi()}' kanalı için açık ({T('Türkçe', 'İngilizce')}). Kanal "
                             "değiştirmek için üst çubuktaki kanal adına tıkla.", sarma=400)
    if AKTIF_PROFIL != "tr":
        Anahtar(k, "Türkçe videolarla eşleştir", degisken("eslestir", tk.BooleanVar),
                "Kapalıyken (önerilen) bu kanal kendi hikâyelerini üretir; iki kanal asla aynı hikâyeyi yayınlamaz. "
                "Açıkken Türkçe kanaldaki yeni hikâyelerin İngilizce versiyonlarını yayınlar.").pack(
            fill="x", pady=(0, px(12)))
    cs_lbl = etiket(k, "", soluk=True, boyut=9, justify="left", anchor="w")
    cs_lbl.pack(fill="x")

    def cs_yaz():
        cs_lbl.config(text=("✓ Google bağlantı dosyası (client_secret.json) hazır" if os.path.exists(CLIENT_SECRET)
                            else "✗ Bu kanal için client_secret.json henüz yok; kurulumda ekleyeceğiz") +
                      ("\n✓ YouTube'a bağlı" if os.path.exists(TOKEN) else "\n○ YouTube'a henüz bağlanmadı"))
    cs_yaz()

    def cs_sec():
        from tkinter import filedialog
        dosya = filedialog.askopenfilename(parent=p, title="client_secret.json dosyasını seç",
                                           filetypes=[("JSON", "*.json")])
        if not dosya:
            return
        try:
            veri = _json_oku(dosya, {})
            if not (veri.get("installed") or veri.get("web")):
                raise RuntimeError("Bu dosya bir Google OAuth istemci dosyası değil.")
            shutil.copyfile(dosya, CLIENT_SECRET)
            log("[✓] client_secret.json bu kanal için eklendi.")
        except Exception as e:
            messagebox.showerror("client_secret.json", str(e)[:300])
        cs_yaz()
    if AKTIF_PROFIL != "tr":
        Dugme(k, "client_secret.json seç", tur="hayalet", boy="kucuk", command=cs_sec).pack(anchor="w",
                                                                                          pady=(px(10), 0))

    k = kart(a_sol, "Görünüm")
    g = tk.Frame(k, bg=R["kart"])
    g.pack(fill="x")
    etiket(g, "Tema", soluk=True).pack(side="left")
    tema_kutu = secim(g, "tema", {"acik": "Açık", "koyu": "Koyu", "sistem": "Windows ile aynı"}, 20)
    tema_kutu.pack(side="left", padx=(px(14), 0))
    tema_kutu.bind("<<ComboboxSelected>>", lambda e: p.after(50, lambda: tema_degistir(ayar["tema"], sor=True)))
    anim_var = degisken("animasyon", tk.BooleanVar)
    Anahtar(k, "Animasyonlar", anim_var, "Geçişler, kayan menü çubuğu, çizilerek gelen grafikler ve Panel'deki "
                                         "gece gökyüzü. Yavaş bilgisayarda kapatabilirsin.").pack(fill="x",
                                                                                               pady=(px(14), 0))
    anim_var.trace_add("write", lambda *_: p.after(50, lambda: (sayfa_goster(durum["sayfa"]), afis_d.update(w=0))))

    if nblm_mi():
        k = kart(a_sol, "🎬  NotebookLM videoları", "İndirdiğin NotebookLM videosu işlenirken baştaki/sondaki "
                                                    "NotebookLM logo ekranı kendiliğinden kesilir ve kapanış kartı "
                                                    "eklenir.", sarma=400)
        Anahtar(k, "Alt yazı ekle", degisken("nblm_altyazi", tk.BooleanVar),
                "Konuşma Whisper ile yazıya dökülür, krem kâğıt etiket tarzında yazılır. NotebookLM videoları kendi alt "
                "yazısıyla geldiği için kapalı tut; açarsan iki alt yazı olur.").pack(fill="x")
        Anahtar(k, "Açılışta büyük kanca yazısı", degisken("nblm_kanca", tk.BooleanVar),
                "İlk 2,5 saniyede konunun çarpıcı cümlesi büyük yazılır (izleyicilerin çoğu ilk saniyelerde "
                "kaydırıyor).").pack(fill="x", pady=(px(10), 0))
        Anahtar(k, "Köşedeki NotebookLM yazısını BirAdım rozetiyle kapat", degisken("nblm_rozet", tk.BooleanVar)
                ).pack(fill="x", pady=(px(10), 0))
        Anahtar(k, "Hazır videolara da rozet ve kapanış ekle", degisken("hazir_marka", tk.BooleanVar),
                "📥 Hazır video ekle ile gelen videolara da sağ alta rozet, sona kapanış kartı eklenir.").pack(
            fill="x", pady=(px(10), 0))
        Anahtar(k, "Yüklemeden önce onayımı bekle", degisken("hazir_onay", tk.BooleanVar),
                "Rozet/kapanış eklenen hazır video 'Onayını bekliyor' olur; Son videolar'dan oynatıp bakarsın, "
                "✓ Onayla deyince yayın planına girer.").pack(fill="x", pady=(px(10), 0))
        hf = tk.Frame(k, bg=R["kart"])
        hf.pack(fill="x", pady=(px(12), 0))
        etiket(hf, "Video hızı", soluk=True).pack(side="left")
        secim(hf, "nblm_hiz", {"1.0": "Normal (1x)", "1.25": "1.25x", "1.5": "1.5x (önerilen)", "1.75": "1.75x"},
              18).pack(side="left", padx=(px(14), 0))
        Dugme(k, "📂  Gelen klasörü", tur="hayalet", boy="kucuk",
              command=lambda: (os.makedirs(_nblm_dosya("gelen"), exist_ok=True), klasor_ac(_nblm_dosya("gelen")))
              ).pack(anchor="w", pady=(px(12), 0))

    k = kart(a_sol, "Video", "Video havuzu: arkaplan_videolari klasöründeki videolardan biri her videoda "
                             "rastgele seçilir ve rastgele bir yerinden başlar (klasör boşsa Subway Surfers "
                             "kullanılır).", sarma=400)
    g = tk.Frame(k, bg=R["kart"])
    g.pack(fill="x")
    g.grid_columnconfigure(1, weight=1)
    etiket(g, "Arka plan", soluk=True).grid(row=0, column=0, sticky="w", pady=px(4))
    secim(g, "arkaplan", ARKAPLANLAR, 30).grid(row=0, column=1, sticky="ew", padx=(px(14), 0))
    etiket(g, "Altyazı", soluk=True).grid(row=1, column=0, sticky="w", pady=px(4))
    secim(g, "altyazi", ALTYAZILAR, 30).grid(row=1, column=1, sticky="ew", padx=(px(14), 0))
    etiket(g, "Video hızı", soluk=True).grid(row=2, column=0, sticky="w", pady=(px(10), px(4)))
    hiz_kontrol(g).grid(row=2, column=1, sticky="w", padx=(px(14), 0), pady=(px(10), px(4)))
    Anahtar(k, "Hikâyeyi yayından önce bana göster", degisken("onizle", tk.BooleanVar),
            "Açıkken hikâye üretim penceresinde düzenlenip onaylanır; kapalıyken beklemeden devam eder.").pack(
        fill="x", pady=(px(14), 0))
    bs = tk.Frame(k, bg=R["kart"])
    bs.pack(fill="x", pady=(px(10), 0))
    Dugme(bs, f"📂  Arka plan videoları ({len(_dosyalar(HAVUZ, VIDEO_UZ))})", tur="ikincil", boy="kucuk",
          command=lambda: klasor_ac(HAVUZ)).pack(side="left")
    Dugme(bs, "📂  Klipler", tur="hayalet", boy="kucuk",
          command=lambda: klasor_ac(KLIP)).pack(side="left", padx=px(8))
    Dugme(bs, "📂  Resimler", tur="hayalet", boy="kucuk", command=lambda: klasor_ac(RESIM)).pack(side="left")

    k = kart(a_sol, "🎵  Arka plan müziği",
             "muzik klasöründeki parçalardan biri her videoda rastgele ve kısık sesle çalar.", sarma=400)
    Anahtar(k, "Müzik ekle", degisken("muzik", tk.BooleanVar)).pack(fill="x")
    g = tk.Frame(k, bg=R["kart"])
    g.pack(fill="x", pady=(px(12), 0))
    etiket(g, "Ses seviyesi", soluk=True).pack(side="left")
    ms_var = degisken("muzik_ses", tk.IntVar)
    ms_lbl = etiket(g, f"%{ms_var.get()}", kalin=True, width=4)
    ttk.Scale(g, from_=0, to=40, variable=ms_var, length=px(170),
              command=lambda x: (ms_var.set(int(float(x))), ms_lbl.config(text=f"%{int(float(x))}"))
              ).pack(side="left", padx=(px(12), px(6)))
    ms_lbl.pack(side="left")
    Dugme(k, f"📂  Müzik klasörü ({len(_dosyalar(MUZIK, MUZIK_UZ))})", tur="hayalet", boy="kucuk",
          command=lambda: klasor_ac(MUZIK)).pack(anchor="w", pady=(px(12), 0))

    k = kart(a_sol, "🖥  Kısayol ve klasörler")
    g = tk.Frame(k, bg=R["kart"])
    g.pack(fill="x")
    kisayol_btn = Dugme(g, "🖥  Masaüstüne kısayol", boy="kucuk")
    kisayol_btn.pack(side="left")
    Dugme(g, "📂  Program klasörü", tur="hayalet", boy="kucuk", command=lambda: klasor_ac(BASE)).pack(side="left",
                                                                                                    padx=px(8))

    k = kart(a_sag, "YouTube hesabı",
             f"Yüklemeler sadece '{ayar.get('hedef_kanal', '')}' kanalına yapılır; başka kanal bağlanırsa program "
             "yüklemeyi durdurur.", sarma=400)
    g = tk.Frame(k, bg=R["kart"])
    g.pack(fill="x")
    baglan_btn2 = Dugme(g, "🔗  Bağlan", tur="yesil", boy="kucuk")
    baglan_btn2.pack(side="left")
    kes_btn = Dugme(g, "Bağlantıyı kaldır", tur="hayalet", boy="kucuk")
    kes_btn.pack(side="left", padx=px(8))
    g = tk.Frame(k, bg=R["kart"])
    g.pack(fill="x", pady=(px(14), 0))
    etiket(g, "Yayın gizliliği", soluk=True).pack(side="left")
    secim(g, "gizlilik", GIZLILIK, 16).pack(side="left", padx=(px(14), 0))
    iyf = Anahtar(k, "Videolarıma otomatik ilk yorum at  ", degisken("ilk_yorum", tk.BooleanVar),
            "Her videonun altına hikâyeye özel bir soru yorumu atılır (ör. \"Sen olsan kapıyı açar mıydın?\"). "
            "Planlı videolarda yorum, video yayınlanınca atılır. Sadece kendi videolarına; yorumu Studio'dan "
            "sabitleyebilirsin.")
    iyf.pack(fill="x", pady=(px(14), 0))
    beta(iyf).place(relx=1.0, y=px(2), anchor="ne")      # place: yerleşimi etkilemez (pack döngüsü olmasın)
    etiket(k, "✓ client_secret.json bulundu" if os.path.exists(CLIENT_SECRET) else "✗ client_secret.json henüz yok",
           soluk=True, boyut=9).pack(anchor="w", pady=(px(10), 0))

    k = kart(a_sag, "🎬  Kapanış kartı", "Her videonun sonuna aynı kart eklenir. Ana klasördeki resim otomatik "
                                       "bulunur; istersen başka bir resim seçebilirsin.", sarma=400)
    Anahtar(k, "Her videonun sonuna ekle", degisken("kapanis", tk.BooleanVar)).pack(fill="x")
    g = tk.Frame(k, bg=R["kart"])
    g.pack(fill="x", pady=(px(12), 0))
    g.grid_columnconfigure(1, weight=1)
    etiket(g, "Geçiş", soluk=True).grid(row=0, column=0, sticky="w", pady=px(4))
    secim(g, "kapanis_gecis", GECISLER, 26).grid(row=0, column=1, columnspan=2, sticky="ew", padx=(px(14), 0))
    etiket(g, "Süre", soluk=True).grid(row=1, column=0, sticky="w", pady=px(4))
    ks_var = degisken("kapanis_sure", tk.IntVar)
    ks_lbl = etiket(g, f"{ks_var.get()} sn", kalin=True, width=5)
    ttk.Scale(g, from_=2, to=8, variable=ks_var, length=px(150),
              command=lambda x: (ks_var.set(int(float(x))), ks_lbl.config(text=f"{int(float(x))} sn"))
              ).grid(row=1, column=1, sticky="w", padx=(px(14), px(4)))
    ks_lbl.grid(row=1, column=2, sticky="w")
    kart_lbl = etiket(k, "", soluk=True, boyut=9, wraplength=px(400), justify="left")
    kart_lbl.pack(anchor="w", pady=(px(8), 0))

    def kart_yaz():
        kb_ = kapanis_bul(ayar)
        kart_lbl.config(text=f"Kart: {os.path.basename(kb_)}" if kb_ else "Kart: bulunamadı (ana klasöre resim koy)")
    kart_yaz()
    kbs = tk.Frame(k, bg=R["kart"])
    kbs.pack(fill="x", pady=(px(10), 0))

    def kart_sec():
        from tkinter import filedialog
        yeni = filedialog.askopenfilename(parent=p, initialdir=BASE, title="Kapanış kartı seç",
                                          filetypes=[("Resim", "*.png *.jpg *.jpeg *.webp *.bmp")])
        if yeni:
            ayar["kapanis_dosya"] = yeni
            ayar_yaz(ayar)
            kart_yaz()
    Dugme(kbs, "🖼  Kart seç", tur="hayalet", boy="kucuk", command=kart_sec).pack(side="left")
    kapanis_dene_btn = Dugme(kbs, "▶  Geçişi önizle", boy="kucuk")
    kapanis_dene_btn.pack(side="left", padx=px(8))

    def kapanis_dene():
        kapanis_dene_btn.config(state="disabled", text="⏳  Hazırlanıyor...")
        a = dict(ayar)

        def is_():
            try:
                klasor_ac(kapanis_onizle(a, log))
            except Exception as e:
                mesaj = str(e)[:300]
                log(f"[X] Önizleme: {mesaj}")
                ui(lambda: messagebox.showerror("Kapanış", mesaj))
            finally:
                ui(lambda: kapanis_dene_btn.config(state="normal", text="▶  Geçişi önizle"))
        threading.Thread(target=is_, daemon=True).start()
    kapanis_dene_btn.config(command=kapanis_dene)

    def kisayol_yap(sessiz=False):
        def is_():
            try:
                y = kisayol_olustur()
                ayar["kisayol_kuruldu"] = True
                ayar_yaz(ayar)
                log(f"[✓] Masaüstü kısayolu oluşturuldu: {y}")
                if not sessiz:
                    ui(lambda: messagebox.showinfo("Kısayol", "Masaüstüne 'Shorts Studyo' kısayolu eklendi."))
            except Exception as e:
                mesaj = str(e)[:300]
                log(f"[!] Kısayol oluşturulamadı: {mesaj}")
                if not sessiz:
                    ui(lambda: messagebox.showerror("Kısayol", mesaj))
        threading.Thread(target=is_, daemon=True).start()
    kisayol_btn.config(command=kisayol_yap)

    # ======================================================================
    # İŞ ÇALIŞTIRMA
    # ======================================================================
    def mesgul_yap(m):
        durum["mesgul"] = m
        for b in kilitli:
            b.config(state="disabled" if m else "normal")
        iptal_btn.config(state="normal" if m else "disabled", text="İptal et")
        dur_btn.config(state="normal" if m and durum["seri"] else "disabled")
        for fmt_, (b, l2, alt_) in yayin_kartlari.items():
            b.config(text="Sürüyor..." if m else "Oluştur", tur="ikincil" if m else "ana")
        plan_btn.config(text="Plan dolduruluyor..." if m and durum["mod"] == "plan" else "Planı şimdi doldur")
        if m:
            durum["bas"] = time.time()
            uretim_hap.ayarla("Başlıyor...")
            uretim_hap.pack(side="right", padx=(0, px(10)), before=oto_hap)
            saat()
        else:
            chip_guncelle(bar["value"])
            p.after(6000, lambda: durum["mesgul"] or uretim_hap.pack_forget())

    def is_baslat(fn, seri=False, mod="uret", yukleme_var=False, baslik_="Video hazırlanıyor", fmt=None,
                  goster=True):
        if durum["mesgul"]:
            uw_goster()
            return
        durum.update(seri=seri, durdur=False, mod=mod, yukleme_var=yukleme_var, sonuc=None)
        IPTAL.clear()
        uw_hazirla(baslik_, fmt)
        mesgul_yap(True)
        log_kutu.delete("1.0", "end")
        try:
            with open(log_dosya, "w", encoding="utf-8") as f_:
                f_.write(f"=== {datetime.datetime.now():%d.%m.%Y %H:%M:%S} · iş başladı ({mod}) ===\n")
        except OSError:
            pass
        asama("Başlıyor...", 0)
        if goster:
            uw_goster()

        def sar():
            durum_ = "hata"
            try:
                fn()
                durum_ = "tamam"
            except IptalHatasi:
                durum_ = "iptal"
                log("\n[■] İşlem iptal edildi. Yarım kalan dosyalar silindi, hiçbir şey yüklenmedi.")
                asama("İptal edildi", 0)
            except Exception as e:
                mesaj = str(e)[:800]
                log(f"\n[X] HATA: {mesaj}")
                asama("Hata: " + (mesaj.splitlines() or [""])[0][:90], None)
                if "iptal" not in mesaj.lower():
                    ui(lambda: messagebox.showerror("Hata", mesaj, parent=uw if uw.winfo_ismapped() else p))
            finally:
                IPTAL.clear()
                ui(lambda: mesgul_yap(False))
                ui(lambda: is_bitti(durum_))
                ui(lambda: durum["sayfa"] == "kutup" and kutuphane_yenile())
                ui(lambda: durum["sayfa"] == "plan" and plan_yenile())
                ui(lambda: durum["sayfa"] == "panel" and panel_yenile())
        threading.Thread(target=sar, daemon=True).start()

    def is_bitti(sonuc):
        """İş bitince pencerenin altındaki butonlar sonuca göre değişir."""
        kayit = durum.get("son") if sonuc == "tamam" else None
        uw_hikaye.config(state="disabled")
        if sonuc == "tamam":
            uretim_hap.ayarla("Tamamlandı", R["secili"], R["vurgu"])
        elif sonuc == "iptal":
            uretim_hap.ayarla("İptal edildi", R["kart2"], R["soluk"])
        else:
            uretim_hap.ayarla("Hata oluştu", R["hata_bg"], R["kirmizi"])
        p.after(6000, lambda: uretim_hap.ayarla(None, R["secili"], R["vurgu"]))
        dugmeler = []
        if kayit and os.path.exists(kayit.get("dosya", "")) and durum["mod"] in ("uret", "yukle"):
            son_oynat_btn.config(command=lambda: klasor_ac(kayit["dosya"]))
            son_klasor_btn.config(command=lambda: klasorde_goster(kayit["dosya"]))
            dugmeler += [son_oynat_btn, son_klasor_btn]
            if kayit.get("url"):
                son_yt_btn.config(text="YouTube'da aç", command=lambda: webbrowser.open(kayit["url"]))
                dugmeler.append(son_yt_btn)
            elif not kayit.get("video_id"):
                son_yt_btn.config(text="YouTube'a yükle", command=lambda: duzenle_penceresi(kayit))
                dugmeler.append(son_yt_btn)
        uw_butonlar(*(dugmeler + [son_kapat_btn]))
        if sonuc == "tamam" and not uw.winfo_ismapped() and durum["mod"] in ("uret", "yukle"):
            uw_goster()

    # --- hikâye onayı: üretim penceresinin içinde ---
    def hikaye_onay(icerik_):
        olay, sonuc = threading.Event(), {}

        def ac():
            uw_baslik_var.set(icerik_["baslik"])
            uw_baslik_giris.config(state="normal")
            uw_hikaye_yaz(icerik_["hikaye"], duzenlenebilir=True)
            detay_ac(False)
            asama_lbl.config(text="Hikâye hazır. İstersen düzenle, sonra onayla.", fg=R["vurgu"])
            uw_butonlar(iptal_btn, onay_tekrar_btn, onay_btn)
            uw_goster()
            uw_hikaye.focus_set()

            def bitir(deger):
                durum.pop("onay_kapat", None)
                sonuc["d"] = deger
                uw_baslik_giris.config(state="readonly")
                uw_hikaye.config(state="disabled", bg=R["bg"])
                uw_metin_f.config(highlightbackground=R["kenar"])
                uw_butonlar(iptal_btn)
                olay.set()

            def onayla():
                yeni = dict(icerik_)
                yeni["baslik"] = baslik_sinirla(uw_baslik_var.get()) or icerik_["baslik"]
                yeni["hikaye"] = uw_hikaye.get("1.0", "end").strip()
                if len(yeni["hikaye"].split()) < 20:
                    messagebox.showwarning("Kısa", "Hikâye çok kısa.", parent=uw)
                    return
                bitir(yeni)
            onay_btn.config(command=onayla)
            onay_tekrar_btn.config(command=lambda: (uw_hikaye_yaz("Yeniden yazılıyor..."), bitir("tekrar")))
            durum["onay_kapat"] = lambda: bitir(None)
        ui(ac)
        olay.wait()
        return sonuc.get("d")

    def hikaye_goster(icerik_):
        """Önizleme kapalıyken de hikâye pencerede okunur; onay beklemeden devam eder."""
        ui(lambda: (uw_baslik_var.set(icerik_["baslik"]), uw_hikaye_yaz(icerik_["hikaye"])))
        return icerik_

    def fikir_bul():
        fikir_btn.config(state="disabled", text="Aranıyor...")

        def is_():
            try:
                f = fikir_uret(ayar["tur"], log)
                ui(lambda: konu_var.set(f))
            except Exception as e:
                log(f"[X] Fikir bulunamadı: {e}")
            finally:
                ui(lambda: fikir_btn.config(state="normal", text="Fikir bul"))
        threading.Thread(target=is_, daemon=True).start()
    fikir_btn.config(command=fikir_bul)
    konu_giris.bind("<Return>", lambda e: yayinla("kisa"))

    # --- NotebookLM kanalı (BirAdım): konu kuyruğu ve video işleme ---
    NBLM_DURUM = {"video_bekliyor": "Video bekleniyor", "islendi": "İşlendi, yayın bekliyor", "yuklendi": "Yüklendi"}

    def nblm_durum_metni(p_):
        if p_.get("durum") == "islendi":
            k_ = next((g for g in gecmis_oku() if g.get("paket_id") == p_.get("id")), None)
            if k_ and k_.get("video_id"):
                return "Yüklendi"
        return NBLM_DURUM.get(p_.get("durum"), p_.get("durum", ""))

    def panoya(metin, ne):
        p.clipboard_clear()
        p.clipboard_append(metin)
        log(f"[i] {ne} panoya kopyalandı.")

    def nblm_konu_baslat():
        b_ = yayin_kartlari.get("nblm_konu", (None,))[0]
        konu = konu_var.get().strip()
        if b_:
            b_.config(state="disabled", text="Hazırlanıyor...")

        def is_():
            try:
                pk = nblm_konu_uret(ayar.get("tur", "Karışık"), konu or None, log)
                ui(lambda: (konu and konu_var.get().strip() == konu and konu_var.set(""),
                            nblm_kuyruk_penceresi(pk["id"])))
            except Exception as e:
                hata = str(e)[:400]
                ui(lambda: messagebox.showerror("Konu hazırlanamadı", hata))
            finally:
                if b_:
                    ui(lambda: b_.config(state="normal", text="Oluştur"))
        threading.Thread(target=is_, daemon=True).start()

    def nblm_kuyruk_penceresi(sec_id=None):
        d = tk.Toplevel(p)
        d.title("BirAdım · konu kuyruğu")
        pencere_belir(d)
        d.after(10, lambda: pencere_koyu_baslik(d, koyu_tema))
        d.configure(bg=R["kart"], padx=px(20), pady=px(16))
        d.geometry(f"{px(1040)}x{px(700)}")
        d.transient(p)
        ust_ = tk.Frame(d, bg=R["kart"])
        ust_.pack(fill="x")
        tk.Label(ust_, text="Konu kuyruğu", bg=R["kart"], fg=R["yazi"], font=F(16, "orta")).pack(side="left")
        beta(ust_).pack(side="left", padx=(px(10), 0), pady=(px(4), 0))
        tk.Label(d, text="1) Kaynağı kopyala → NotebookLM'de yeni not defteri aç, 'Kopyalanan metin' olarak yapıştır.   "
                         "2) Video Özeti'nin kalem simgesine bas, istemi yapıştır, oluştur.   3) Videoyu indir ve "
                         "'gelen' klasörüne at (plan doldurulurken kendiliğinden işlenir) ya da 'Videoyu seç ve işle'.",
                 bg=R["kart"], fg=R["soluk"], font=F(9), wraplength=px(990), justify="left").pack(anchor="w",
                                                                                                   pady=(px(4), px(10)))
        alt_ = tk.Frame(d, bg=R["kart"])
        alt_.pack(side="bottom", fill="x", pady=(px(12), 0))
        govde = tk.Frame(d, bg=R["kart"])
        govde.pack(fill="both", expand=True)
        govde.grid_columnconfigure(0, weight=2, uniform="g")
        govde.grid_columnconfigure(1, weight=3, uniform="g")
        govde.grid_rowconfigure(0, weight=1)
        agac = ttk.Treeview(govde, columns=("durum", "baslik"), show="headings", selectmode="browse")
        agac.heading("durum", text="Durum")
        agac.heading("baslik", text="Başlık")
        agac.column("durum", width=px(150), stretch=False)
        agac.column("baslik", width=px(240))
        agac.grid(row=0, column=0, sticky="nsew", padx=(0, px(14)))
        sag_ = tk.Frame(govde, bg=R["kart"])
        sag_.grid(row=0, column=1, sticky="nsew")
        b_lbl = tk.Label(sag_, text="", bg=R["kart"], fg=R["yazi"], font=F(12, "orta"), wraplength=px(560),
                         justify="left", anchor="w")
        b_lbl.pack(fill="x")
        k_lbl = tk.Label(sag_, text="", bg=R["kart"], fg=R["vurgu"], font=F(10, "orta"), anchor="w")
        k_lbl.pack(fill="x", pady=(px(2), px(8)))

        def kutu(baslik_, yuk):
            etiket(sag_, baslik_, soluk=True, boyut=9).pack(anchor="w")
            t_ = tk.Text(sag_, height=yuk, font=F(10), bg=R["bg"], fg=R["yazi"], bd=0, wrap="word", padx=px(10),
                         pady=px(8), highlightthickness=1, highlightbackground=R["cerceve"])
            t_.pack(fill="both", expand=yuk > 6, pady=(px(4), px(8)))
            return t_
        kaynak_t = kutu("Kaynak metin (NotebookLM'e)", 12)
        istem_t = kutu("Video Özeti istemi", 4)
        bt = tk.Frame(sag_, bg=R["kart"])
        bt.pack(fill="x")
        secili = {"p": None}

        def doldur(sec=None):
            agac.delete(*agac.get_children())
            for p_ in reversed(nblm_kuyruk_oku()):
                agac.insert("", "end", iid=p_["id"], values=(nblm_durum_metni(p_), p_.get("baslik", "")))
            hedef = sec or (agac.get_children() or [None])[0]
            if hedef and agac.exists(hedef):
                agac.selection_set(hedef)
                agac.see(hedef)
            goster()

        def goster(_=None):
            sel = agac.selection()
            p_ = next((x for x in nblm_kuyruk_oku() if sel and x["id"] == sel[0]), None)
            secili["p"] = p_
            for t_, alan in ((kaynak_t, "kaynak"), (istem_t, "istem")):
                t_.config(state="normal")
                t_.delete("1.0", "end")
                t_.insert("1.0", (p_ or {}).get(alan, ""))
                t_.config(state="disabled")
            b_lbl.config(text=(p_ or {}).get("baslik", "Kuyrukta konu yok. 'Yeni konu' ile başla."))
            k_lbl.config(text=f"Açılış yazısı: {buyuk(p_['kanca'])}" if p_ and p_.get("kanca") else "")
        agac.bind("<<TreeviewSelect>>", goster)
        Dugme(bt, "1 · Kaynağı kopyala", tur="ana", boy="kucuk",
              command=lambda: secili["p"] and panoya(secili["p"]["kaynak"], "Kaynak metin")).pack(side="left")
        Dugme(bt, "2 · İstemi kopyala", tur="ikincil", boy="kucuk",
              command=lambda: secili["p"] and panoya(secili["p"]["istem"], "NotebookLM istemi")).pack(
            side="left", padx=px(8))
        Dugme(bt, "NotebookLM'i aç ↗", tur="hayalet", boy="kucuk",
              command=lambda: webbrowser.open("https://notebooklm.google.com/")).pack(side="left")

        def yeni():
            yb.config(state="disabled", text="Hazırlanıyor...")

            def is_():
                try:
                    pk = nblm_konu_uret(ayar.get("tur", "Karışık"), None, log)
                    ui(lambda: doldur(pk["id"]))
                except Exception as e:
                    hata = str(e)[:300]
                    ui(lambda: messagebox.showerror("Konu hazırlanamadı", hata, parent=d))
                finally:
                    ui(lambda: yb.config(state="normal", text="＋ Yeni konu"))
            threading.Thread(target=is_, daemon=True).start()

        def sil():
            p_ = secili["p"]
            if p_ and messagebox.askyesno("Sil", f"'{p_.get('baslik')}' kuyruktan silinsin mi?", parent=d):
                nblm_kuyruk_yaz([x for x in nblm_kuyruk_oku() if x["id"] != p_["id"]])
                doldur()
        yb = Dugme(alt_, "＋ Yeni konu", tur="ana", boy="kucuk", command=yeni)
        yb.pack(side="left")
        Dugme(alt_, "🎬  Videoyu seç ve işle", tur="ikincil", boy="kucuk",
              command=lambda: (d.destroy(), nblm_isle_baslat(secili["p"]))).pack(side="left", padx=px(8))
        Dugme(alt_, "📂  Gelen klasörü", tur="hayalet", boy="kucuk",
              command=lambda: (os.makedirs(_nblm_dosya("gelen"), exist_ok=True), klasor_ac(_nblm_dosya("gelen")))
              ).pack(side="left")
        Dugme(alt_, "Kapat", tur="ikincil", boy="kucuk", command=d.destroy).pack(side="right")
        Dugme(alt_, "Sil", tur="hayalet", boy="kucuk", command=sil).pack(side="right", padx=px(8))
        doldur(sec_id)

    def nblm_isle_baslat(paket=None):
        if durum["mesgul"]:
            uw_goster()
            return
        from tkinter import filedialog
        indir = os.path.join(os.path.expanduser("~"), "Downloads")
        dosya = filedialog.askopenfilename(parent=p, title="NotebookLM'den indirdiğin videoyu seç",
                                           initialdir=indir if os.path.isdir(indir) else BASE,
                                           filetypes=[("Video", "*.mp4 *.mov *.webm *.mkv *.m4v"), ("Tümü", "*.*")])
        if not dosya:
            return
        onceki = next((g for g in gecmis_oku() if os.path.basename(g.get("kaynak_video") or "") ==
                       os.path.basename(dosya)), None)
        if onceki and not messagebox.askyesno(
                "Bu video zaten işlendi",
                f"Bu dosya daha önce '{onceki.get('baslik', '')}' olarak işlendi.\n\nAynı videoyu başka bir konuyla "
                "yeniden işlersen kanalda aynı video iki farklı başlıkla çıkar. Yine de devam edilsin mi?"):
            return
        bekleyen = [x for x in nblm_kuyruk_oku() if x.get("durum") == "video_bekliyor"]
        if paket is None or paket.get("durum") != "video_bekliyor":
            paket = nblm_eslesen_paket(dosya)
        d = tk.Toplevel(p)
        d.title("Videoyu işle")
        pencere_belir(d)
        d.after(10, lambda: pencere_koyu_baslik(d, koyu_tema))
        d.configure(bg=R["kart"], padx=px(24), pady=px(20))
        d.transient(p)
        d.grab_set()
        tk.Label(d, text="Videoyu işle", bg=R["kart"], fg=R["yazi"], font=F(16, "orta")).pack(anchor="w")
        tk.Label(d, text=os.path.basename(dosya), bg=R["kart"], fg=R["soluk"], font=F(9)).pack(anchor="w",
                                                                                               pady=(px(2), px(14)))
        etiket(d, "Bu video hangi konunun?", soluk=True, boyut=9).pack(anchor="w")
        secenek = {f"{x.get('baslik', '')}": x for x in bekleyen}
        konu_sec = tk.StringVar(value=(paket or {}).get("baslik", "") if paket else "")
        ttk.Combobox(d, textvariable=konu_sec, values=list(secenek), state="readonly" if secenek else "normal",
                     width=60).pack(fill="x", pady=(px(4), px(12)))
        if not secenek:
            tk.Label(d, text="Kuyrukta bekleyen konu yok; yukarıya başlığı kendin yaz.", bg=R["kart"], fg=R["sari"],
                     font=F(9)).pack(anchor="w", pady=(0, px(8)))
        ne = tk.StringVar(value="plan" if plan_listesi(ayar) else "hemen")
        for deger, metin in (("plan", "Yayın planındaki ilk boş saate koy"), ("hemen", "Hemen yayınla"),
                             ("hazirla", "Sadece hazırla (yüklemeden)")):
            ttk.Radiobutton(d, text=metin, value=deger, variable=ne).pack(anchor="w", pady=px(2))
        tk.Frame(d, bg=R["kart"], height=px(10)).pack()
        hiz_al = hiz_satiri(d, dosya, ayar.get("nblm_hiz", "1.5"))
        alt_ = tk.Frame(d, bg=R["kart"])
        alt_.pack(fill="x", pady=(px(16), 0))

        def basla():
            secim_ = konu_sec.get().strip()
            pk = secenek.get(secim_) or {"konu": secim_ or os.path.splitext(os.path.basename(dosya))[0],
                                         "baslik": secim_ or os.path.splitext(os.path.basename(dosya))[0][:60],
                                         "aciklama": "#biradım #shorts", "etiketler": ["biradım"]}
            mod = ne.get()
            secilen_hiz = hiz_al()
            d.grab_release()
            d.destroy()
            a = dict(ayar, nblm_hiz=str(secilen_hiz))
            yukle = os.path.exists(TOKEN) and mod != "hazirla"

            def is_():
                kayit = nblm_isle(dosya, pk, a, log, asama)
                ui(lambda: son_goster(kayit))
                if yukle and mod == "hemen":
                    asama("YouTube'a yükleniyor", 92)
                    youtube_yukle(kayit, a["gizlilik"], None, log, lambda o: asama(None, 92 + o * 8))
                    ui(lambda: son_goster(kayit))
                    yt_durum_guncelle()
                    asama("Yayınlandı: " + kayit["baslik"], 100)
                elif yukle and mod == "plan":
                    plan_doldur(a, log, asama, en_fazla=1)
                    ui(lambda: son_goster(next((g for g in gecmis_oku() if g.get("dosya") == kayit["dosya"]),
                                               kayit)))
                else:
                    asama("Video hazır (yüklenmedi)", 100)
                ui(p.bell)
            is_baslat(is_, yukleme_var=yukle, baslik_="NotebookLM videosu işleniyor", fmt="kisa")
        Dugme(alt_, "İşle", tur="ana", command=basla).pack(side="right")
        Dugme(alt_, "Vazgeç", tur="hayalet", command=lambda: (d.grab_release(), d.destroy())).pack(side="right",
                                                                                                 padx=px(8))

    def yayinla(fmt):
        """Panel'deki 'Shorts yayınla' / 'Video yayınla': hikâye → ses → video → YouTube."""
        if nblm_mi():
            if fmt == "nblm_isle":
                nblm_isle_baslat()
            else:
                nblm_konu_baslat()
            return
        if durum["mesgul"]:
            uw_goster()
            return
        yukle = os.path.exists(TOKEN)
        if not yukle and not messagebox.askyesno(
                "YouTube bağlı değil",
                "YouTube hesabı bağlı olmadığı için video kanala yüklenemez.\n\n"
                "Video yine de üretilsin mi? (Sonra İçerik sayfasından yükleyebilirsin.)"):
            return
        konu = konu_var.get().strip()
        a = dict(ayar, uzunluk=fmt, yon="dikey" if fmt == "kisa" else "yatay")
        ayar["uzunluk"], ayar["yon"] = a["uzunluk"], a["yon"]
        ayar_yaz(ayar)

        def is_():
            k_ = konu
            if not k_:
                asama("Konu aranıyor", 2)
                k_ = fikir_uret(a["tur"], log)
                log(f"[+] Konu: {k_}")
            kayit = video_uret(k_, a, log, asama, onay=hikaye_onay if a.get("onizle") else hikaye_goster)
            # konu kutusunu sadece bu videoda kullanılan konu hâlâ oradaysa temizle (iş sürerken yazılan yeni konu kalsın)
            ui(lambda: konu and konu_var.get().strip() == konu and konu_var.set(""))
            ui(lambda: son_goster(kayit))
            if yukle:
                asama("YouTube'a yükleniyor", 92)
                youtube_yukle(kayit, a["gizlilik"], None, log, lambda o: asama(None, 92 + o * 8))
                ui(lambda: son_goster(kayit))
                yt_durum_guncelle()
                asama("Yayınlandı: " + kayit["baslik"], 100)
            else:
                asama("Video hazır (YouTube'a yüklenmedi)", 100)
            ui(p.bell)
        is_baslat(is_, yukleme_var=yukle, baslik_="Shorts yayınla" if fmt == "kisa" else "Video yayınla", fmt=fmt)

    def elle_yukle(kayit, hiz=None):
        gizlilik = ayar["gizlilik"]

        def is_():
            if hiz:
                asama(f"Video {hiz:g}x hızla yeniden hazırlanıyor", 0)
                nblm_yeniden_isle(kayit, hiz, log, lambda a, y: asama(a, y * 0.6 if y is not None else None))
                ui(lambda: son_goster(kayit))
            asama("YouTube'a yükleniyor", 60 if hiz else 0)
            youtube_yukle(kayit, gizlilik, None, log, lambda o: asama(None, (60 + o * 40) if hiz else o * 100))
            ui(lambda: son_goster(kayit))
            asama("YouTube'a yüklendi", 100)
            yt_durum_guncelle()
        ui(lambda: (uw_baslik_var.set(kayit.get("baslik", "")), uw_hikaye_yaz(kayit.get("hikaye", ""))))
        is_baslat(is_, mod="yukle", yukleme_var=True, baslik_="YouTube'a yükle")
        durum["son"] = kayit
        resim_yukle(uw_resim, kayit.get("dosya"), "son", 300)

    def plani_doldur():
        saatleri_kaydet()
        if not plan_listesi(ayar):
            messagebox.showwarning("Plan", "Önce en az bir yayın saati ekle.")
            return
        a = dict(ayar)

        def bitti(kayit):
            ui(lambda: son_goster(kayit))
            ui(plan_yenile)
            ui(lambda: uw_hikaye_yaz(kayit.get("hikaye", "")))
        is_baslat(lambda: plan_doldur(a, log, asama, durdur=lambda: durum["durdur"], video_bitti=bitti),
                  seri=True, mod="plan", yukleme_var=True, baslik_="Plan dolduruluyor")
    plan_btn.config(command=plani_doldur)

    def seri():
        a = dict(ayar)
        adet = max(1, int(a["oto_adet"]))
        sayac = {"n": 0}

        def bitti(kayit):
            sayac["n"] += 1
            ui(lambda: son_goster(kayit))
            ui(lambda: uw_hikaye_yaz(kayit.get("hikaye", "")))
            ui(lambda: seri_ozet.config(text=f"✓ {sayac['n']}/{adet} video  ·  son: {kayit['baslik']}"))
        seri_ozet.config(text=f"0/{adet} video")
        is_baslat(lambda: seri_calistir(adet, a, bool(a["oto_yukle"]), a["gizlilik"], 0, log, asama,
                                        durdur=lambda: durum["durdur"], video_bitti=bitti),
                  seri=True, mod="seri", yukleme_var=bool(a["oto_yukle"]), baslik_=f"Hızlı seri · {adet} video")
    seri_btn.config(command=seri)

    def iptal_et():
        if not durum["mesgul"] or IPTAL.is_set():
            return
        # önce ekranı güncelle, sonra işi durdur (sıra önemli: "İptal edildi" yazısı en son gelsin)
        iptal_btn.config(state="disabled", text="İptal ediliyor...")
        log("[~] İptal ediliyor... (o anki adım biter bitmez durur)")
        asama("İptal ediliyor...", None)
        durum["durdur"] = True
        IPTAL.set()
        if durum.get("onay_kapat"):
            durum["onay_kapat"]()
    iptal_btn.config(command=iptal_et)

    def durdur():
        durum["durdur"] = True
        dur_btn.config(state="disabled")
        log("[~] Mevcut video bitince durulacak.")
        asama("Mevcut video bitince durulacak", None)
    dur_btn.config(command=durdur)

    # ---------- YOUTUBE DURUMU ----------
    def yt_yaz(renk, metin, btn, ad=None, bilgi=None):
        yt_nokta.config(fg=renk)
        yt_durum_lbl.config(text=metin, fg=R["kirmizi"] if renk == R["kirmizi"] else R["soluk"])
        yt_baglan_btn.config(text=btn)
        yt_ad.config(text=ad or ayar.get("hedef_kanal", ""))
        if bilgi:
            toplam = sum(int((k_.get("istatistik") or {}).get("izlenme", 0) or 0) for k_ in gecmis_oku()
                         if k_.get("video_id") and not (k_.get("istatistik") or {}).get("silindi"))
            if str(bilgi.get("izlenme", "")).isdigit():
                bilgi = dict(bilgi, izlenme=str(max(int(bilgi["izlenme"]), toplam)))
            for k_ in ("abone", "video", "izlenme"):
                if str(bilgi.get(k_, "")).isdigit():
                    sayac_anim(kanal_ozet[k_], int(bilgi[k_]), lambda x: sayi(int(round(x))))
                else:
                    kanal_ozet[k_].config(text="–")
            avatar_ciz(ust_avatar, px(32), AVATAR)
            avatar_ciz(yan_avatar, px(96), AVATAR)

    def yt_durum_guncelle(etkilesimli=False):
        def is_():
            try:
                yt = yt_servis(etkilesimli, log)
                if yt is None:
                    ui(lambda: yt_yaz(R["soluk2"], "YouTube bağlı değil", "Bağlan"))
                    return
                b = kanal_bilgisi(yt)
                hedef = ayar.get("hedef_kanal", "")
                if b and hedef and _kanal_norm(b["ad"]) != _kanal_norm(hedef):
                    ui(lambda: yt_yaz(R["kirmizi"], f"Yanlış kanal: {b['ad']}", "Yeniden bağlan"))
                    log(f"[X] Bağlı kanal '{b['ad']}', ama hedef '{hedef}'. Bağlantıyı kaldırıp doğru kanalı seç.")
                    return
                if b:
                    ui(lambda: yt_yaz(R["yesil"], "YouTube'a bağlı", "Yenile", b["ad"], b))
                    ui(yorum_izin_guncelle)
                    if etkilesimli:
                        log(f"[✓] YouTube kanalı bağlandı: {b['ad']}")
            except Exception as e:
                mesaj = str(e)[:800]
                ui(lambda: yt_yaz(R["kirmizi"], "Bağlantı hatası", "Yeniden bağlan"))
                if etkilesimli:
                    log(f"[X] YouTube bağlantısı: {mesaj}")
                    ui(lambda: messagebox.showerror("YouTube", mesaj))
        threading.Thread(target=is_, daemon=True).start()

    def kes():
        yt_baglantiyi_kes()
        yt_yaz(R["soluk2"], "YouTube bağlı değil", "Bağlan")
        log("[~] YouTube bağlantısı kaldırıldı.")
    kes_btn.config(command=kes)

    def baglan_tikla():
        if "Yeniden" in yt_baglan_btn.cget("text"):
            kes()
        yt_durum_guncelle(True)
    yt_baglan_btn.config(command=baglan_tikla)
    baglan_btn2.config(command=baglan_tikla)

    # ---------- AÇILIŞ ----------
    sayfa_goster("panel")
    gecmis = gecmis_oku()
    for kayit in reversed(gecmis):
        if os.path.exists(kayit.get("dosya", "")):
            durum["son"] = kayit
            break
    if os.path.exists(TOKEN):
        yt_durum_guncelle(False)
    if not ayar.get("kisayol_kuruldu") and os.name == "nt":
        kisayol_yap(sessiz=True)
    gorev_guncelle()
    yorumlar_yenile()
    log(f"[i] Hazır. Üretilen video: {len(gecmis)}, müzik: {len(_dosyalar(MUZIK, MUZIK_UZ))}")

    ilk_yorum_son = {"t": 0.0}

    def periyodik():
        if os.path.exists(TOKEN) and time.time() - ilk_yorum_son["t"] > 300:
            ilk_yorum_son["t"] = time.time()

            def iy():
                try:
                    if bekleyen_ilk_yorumlar(log):
                        ui(lambda: panel_yenile() if durum["sayfa"] == "panel" else None)
                except Exception as e:
                    log(f"[!] Bekleyen ilk yorumlar: {str(e)[:150]}")
            threading.Thread(target=iy, daemon=True).start()
        if not durum["mesgul"] and _json_oku(os.path.join(profil_klasoru(AKTIF_PROFIL), "isler.json"), []):
            p.after(100, bekleyen_isler_baslat)      # program açıkken sıraya eklenen işler de yapılsın
        if not durum["mesgul"]:
            if durum["sayfa"] == "plan":
                plan_yenile()
            elif durum["sayfa"] == "panel":
                panel_yenile()
        p.after(60000, periyodik)
    p.after(60000, periyodik)

    def bekleyen_isler_baslat():
        # isler.json'da sıra bekleyen iş varsa (ör. yanlış işlenmiş videonun hızlandırılmış hali) program açılınca hemen yap
        try:
            if durum["mesgul"]:
                return p.after(60000, bekleyen_isler_baslat)
            if not _json_oku(os.path.join(profil_klasoru(AKTIF_PROFIL), "isler.json"), []):
                return

            def is_():
                bekleyen_isleri_yap(log, asama)
                asama("Hazır: onay listesinde izleyip onayla", 100)
                ui(lambda: panel_yenile() if durum["sayfa"] == "panel" else None)
            is_baslat(is_, mod="uret", baslik_="Bekleyen işler yapılıyor", fmt="kisa")
        except Exception as e:
            log(f"[!] Bekleyen işler başlatılamadı: {str(e)[:150]}")
    p.after(4000, bekleyen_isler_baslat)

    def kapatirken():
        if durum["mesgul"] and not messagebox.askyesno("Dikkat", "İşlem devam ediyor. Yine de kapatılsın mı?"):
            return
        p.destroy()
        os._exit(0)
    p.protocol("WM_DELETE_WINDOW", kapatirken)
    p.mainloop()


# ---------------------------------------------------------------------------
# 12. KOMUT SATIRI (Görev Zamanlayıcı için)
# ---------------------------------------------------------------------------
def komut_satiri(a):
    ayar = ayar_oku()
    log_dosya = os.path.join(CIKTI, "otomatik_log.txt")

    def log(m):
        satir = f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {m}"
        try:
            print(satir, flush=True)
        except UnicodeEncodeError:
            print(satir.encode("ascii", "replace").decode(), flush=True)
        with open(log_dosya, "a", encoding="utf-8") as f:
            f.write(satir + "\n")

    gizlilik = a.gizlilik or ayar["gizlilik"]
    if a.yorumlar:
        if not ayar.get("yorum_oto"):
            return
        try:
            s_ = yorum_turu(log)
            if s_.get("yeni"):
                log(f"[i] Yorumlar: {s_['yeni']} yeni, {s_['gonderilen']} cevaplandı, {s_['taslak']} onayda, "
                    f"{s_['atlanan']} atlandı")
        except Exception as e:
            log(f"[X] Yorumlar: {e}")
        return
    if a.planla:
        try:
            plan_doldur(ayar, log)
        except Exception as e:
            log(f"[X] Plan doldurulamadı: {e}")
        return
    if a.konu:
        kayit = video_uret(a.konu, ayar, log)
        if a.yukle:
            youtube_yukle(kayit, gizlilik, None, log)
    else:
        seri_calistir(a.oto, ayar, a.yukle, gizlilik, a.aralik, log)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Shorts Hikaye Stüdyosu")
    ap.add_argument("--oto", type=int, help="Arayüzsüz N video üret")
    ap.add_argument("--konu", help="Arayüzsüz tek video, verilen konuyla")
    ap.add_argument("--yukle", action="store_true", help="YouTube'a yükle")
    ap.add_argument("--gizlilik", choices=list(GIZLILIK), help="public / unlisted / private")
    ap.add_argument("--aralik", type=float, default=0, help="Seride yayın aralığı (saat)")
    ap.add_argument("--planla", action="store_true", help="Günlük yayın planındaki boş saatleri doldur")
    ap.add_argument("--yorumlar", action="store_true", help="Yeni yorumlara otomatik cevap ver")
    ap.add_argument("--profil", help="Kanal profili (tr, en ...); verilmezse son seçilen kanal")
    argumanlar = ap.parse_args()
    profil_etkinlestir(argumanlar.profil or profiller_oku()["aktif"])
    if argumanlar.oto or argumanlar.konu or argumanlar.planla or argumanlar.yorumlar:
        komut_satiri(argumanlar)
    else:
        arayuzu_baslat()
