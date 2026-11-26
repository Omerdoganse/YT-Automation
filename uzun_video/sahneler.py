# Milgram bölümü sahne çizimleri (2016x1134 tuval; 1920x1080'e kırpılarak hafif kaydırılır)
import math, random
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H = 2016, 1134
CX = W // 2
KAGIT = (245, 239, 228)
MUREKKEP = (43, 36, 32)
KIRMIZI = (200, 55, 45)
ALTIN = (214, 158, 52)
YESIL = (96, 145, 112)
GRI = (138, 123, 107)
ACIK = (226, 216, 200)

FD = "/usr/share/fonts/truetype/crosextra/"
FI = "/usr/share/fonts/opentype/inter/"
_fc = {}
def F(name, size):
    k = (name, size)
    if k not in _fc:
        path = {"serif": FD + "Caladea-Bold.ttf", "serif_r": FD + "Caladea-Regular.ttf",
                "serif_i": FD + "Caladea-Italic.ttf", "serif_bi": FD + "Caladea-BoldItalic.ttf",
                "sans": FI + "Inter-SemiBold.otf", "sans_b": FI + "Inter-ExtraBold.otf",
                "sans_r": FI + "Inter-Regular.otf", "sans_m": FI + "Inter-Medium.otf"}[name]
        _fc[k] = ImageFont.truetype(path, size)
    return _fc[k]

_kagit = None
def kagit():
    global _kagit
    if _kagit is None:
        rnd = random.Random(7)
        im = Image.new("RGB", (W, H), KAGIT)
        import numpy as np
        a = np.array(im).astype(np.float32)
        n = np.random.default_rng(3).normal(0, 3.2, (H, W, 1))
        a += n
        yy, xx = np.mgrid[0:H, 0:W]
        r = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
        a *= (1 - 0.10 * np.clip(r - 0.55, 0, 1)[..., None])
        im = Image.fromarray(np.clip(a, 0, 255).astype("uint8"))
        d = ImageDraw.Draw(im)
        # küçük yıldız süsleri
        for (x, y, s, c) in [(150, 170, 22, ALTIN), (1880, 220, 18, YESIL), (120, 900, 16, YESIL), (1900, 880, 22, ALTIN)]:
            yildiz(d, x, y, s, c)
        _kagit = im
    return _kagit.copy()

def yildiz(d, x, y, s, c, w=3):
    pts = []
    for i in range(8):
        r = s if i % 2 == 0 else s * 0.28
        a = math.pi / 2 + i * math.pi / 4
        pts.append((x + r * math.cos(a), y - r * math.sin(a)))
    d.polygon(pts, fill=c)

def metin(d, xy, t, font, fill=MUREKKEP, anchor="mm", **kw):
    d.text(xy, t, font=font, fill=fill, anchor=anchor, **kw)

def cizgi_alt(d, x, y, w, c=GRI):
    d.line([(x - w // 2, y), (x - 18, y)], fill=c, width=3)
    d.line([(x + 18, y), (x + w // 2, y)], fill=c, width=3)
    d.polygon([(x, y - 10), (x + 10, y), (x, y + 10), (x - 10, y)], fill=YESIL)

def baslik(d, t, y=150, size=78, c=MUREKKEP):
    metin(d, (CX, y), t, F("serif", size), c)
    tw = d.textlength(t, font=F("serif", size))
    cizgi_alt(d, CX, y + size // 2 + 26, int(min(tw + 120, 1100)))

def kart(im, box, fill=(252, 249, 243), r=28, golge=True, kenar=MUREKKEP, kw=4):
    if golge:
        sh = Image.new("L", im.size, 0)
        ImageDraw.Draw(sh).rounded_rectangle((box[0] + 10, box[1] + 16, box[2] + 10, box[3] + 16), r, fill=70)
        sh = sh.filter(ImageFilter.GaussianBlur(14))
        im.paste((120, 100, 80), mask=sh)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle(box, r, fill=fill, outline=kenar, width=kw)
    return d

def insan(d, x, y, s=1.0, c=MUREKKEP, kollar="asagi", w=6, govde_renk=None, bas_renk=None):
    """y = ayak tabanı. Basit el çizimi figür."""
    hb = 34 * s
    bas_y = y - 250 * s
    d.ellipse((x - hb, bas_y - hb, x + hb, bas_y + hb), outline=c, width=int(w), fill=bas_renk or KAGIT)
    omuz = bas_y + hb + 14 * s
    kalca = y - 105 * s
    if govde_renk:
        d.rounded_rectangle((x - 40 * s, omuz, x + 40 * s, kalca + 10 * s), int(22 * s), fill=govde_renk, outline=c, width=int(w))
    else:
        d.line([(x, omuz), (x, kalca)], fill=c, width=int(w))
    d.line([(x, kalca), (x - 38 * s, y)], fill=c, width=int(w))
    d.line([(x, kalca), (x + 38 * s, y)], fill=c, width=int(w))
    ky = omuz + 18 * s
    if kollar == "asagi":
        d.line([(x - 5, ky), (x - 55 * s, ky + 95 * s)], fill=c, width=int(w))
        d.line([(x + 5, ky), (x + 55 * s, ky + 95 * s)], fill=c, width=int(w))
    elif kollar == "ileri":
        d.line([(x, ky), (x + 85 * s, ky + 40 * s)], fill=c, width=int(w))
        d.line([(x, ky), (x + 80 * s, ky + 55 * s)], fill=c, width=int(w))
    elif kollar == "yukari":
        d.line([(x, ky), (x - 60 * s, ky - 80 * s)], fill=c, width=int(w))
        d.line([(x, ky), (x + 60 * s, ky - 80 * s)], fill=c, width=int(w))
    elif kollar == "dur":
        d.line([(x, ky), (x + 95 * s, ky - 10 * s)], fill=c, width=int(w))
        d.line([(x + 95 * s, ky - 10 * s), (x + 95 * s, ky - 60 * s)], fill=c, width=int(w))
        d.line([(x, ky), (x - 50 * s, ky + 90 * s)], fill=c, width=int(w))
    return bas_y

def baloncuk(im, x, y, t, font, fill=(255, 252, 246), c=MUREKKEP, kuyruk="sol", pad=28, renk=MUREKKEP):
    d = ImageDraw.Draw(im)
    bb = d.textbbox((0, 0), t, font=font)
    w, h = bb[2] - bb[0] + pad * 2, bb[3] - bb[1] + pad * 2
    box = (x, y, x + w, y + h)
    d.rounded_rectangle(box, 26, fill=fill, outline=c, width=4)
    if kuyruk == "sol":
        d.polygon([(x + 40, y + h - 2), (x + 20, y + h + 34), (x + 80, y + h - 2)], fill=fill, outline=None)
        d.line([(x + 40, y + h), (x + 20, y + h + 34), (x + 80, y + h)], fill=c, width=4)
    elif kuyruk == "sag":
        d.polygon([(x + w - 40, y + h - 2), (x + w - 20, y + h + 34), (x + w - 80, y + h - 2)], fill=fill)
        d.line([(x + w - 40, y + h), (x + w - 20, y + h + 34), (x + w - 80, y + h)], fill=c, width=4)
    d.text((x + pad - bb[0], y + pad - bb[1]), t, font=font, fill=renk)
    return box

def simsek(d, x, y, s=1.0, c=ALTIN):
    pts = [(0, 0), (40, 0), (20, 50), (55, 50), (-5, 130), (12, 70), (-20, 70)]
    d.polygon([(x + px * s, y + py * s) for px, py in pts], fill=c, outline=MUREKKEP)

# ---------------- Şok makinesi ----------------
def makine(im, box, aktif=0, vurgula_son=False, etiketler=True):
    x0, y0, x1, y1 = box
    d = kart(im, box, fill=(70, 62, 56), r=22, kenar=MUREKKEP, kw=5)
    d.rounded_rectangle((x0 + 18, y0 + 18, x1 - 18, y0 + 78), 10, fill=(58, 51, 46))
    metin(d, ((x0 + x1) // 2, y0 + 48), "ŞOK JENERATÖRÜ  ·  TİP ZLB", F("sans", 30), (230, 220, 200))
    n = 30
    gx0, gx1 = x0 + 50, x1 - 50
    step = (gx1 - gx0) / (n - 1)
    sy = y0 + 200
    for i in range(n):
        cx = gx0 + i * step
        on = i < aktif
        tehlike = i >= 24
        col = (KIRMIZI if tehlike else ALTIN) if on else (140, 128, 116)
        d.ellipse((cx - 13, sy - 13 - 50, cx + 13, sy + 13 - 50), fill=(255, 210, 90) if on else (95, 86, 78))
        d.rounded_rectangle((cx - 15, sy - 22, cx + 15, sy + 38), 6, fill=col, outline=(30, 25, 22), width=3)
        if etiketler and (i % 3 == 0 or i == n - 1):
            metin(d, (cx, sy + 72), f"{15 * (i + 1)}", F("sans", 22), (230, 220, 200))
    # bölge etiketleri
    zones = [(0, 3, "Hafif"), (4, 7, "Orta"), (8, 11, "Güçlü"), (12, 15, "Çok güçlü"), (16, 19, "Yoğun"),
             (20, 23, "Aşırı yoğun"), (24, 27, "TEHLİKE: AĞIR ŞOK"), (28, 29, "XXX")]
    if etiketler:
        for a, b, t in zones:
            xa, xb = gx0 + a * step - 14, gx0 + b * step + 14
            c = (255, 120, 100) if a >= 24 else (200, 188, 170)
            if vurgula_son and a >= 24:
                d.rounded_rectangle((xa - 4, sy + 104, xb + 4, sy + 150), 8, fill=KIRMIZI)
                c = (255, 255, 255)
            d.line([(xa, sy + 110), (xb, sy + 110)], fill=c, width=3)
            f = F("sans_b" if a >= 24 else "sans_m", 19 if a < 24 else 20)
            metin(d, ((xa + xb) / 2, sy + 132), t, f, c)
    return d

# ---------------- Sahneler ----------------
# her sahne: ciz(durum) -> Image ; durum 0..n-1

def s0(k):  # kanca
    im = kagit(); d = ImageDraw.Draw(im)
    # büyük volt kadranı
    cx, cy, R = CX, 520, 300
    d.arc((cx - R, cy - R, cx + R, cy + R), 180, 360, fill=MUREKKEP, width=10)
    for i in range(0, 31):
        a = math.pi - i * math.pi / 30
        r1, r2 = R - 12, R - (52 if i % 5 == 0 else 32)
        c = KIRMIZI if i >= 24 else MUREKKEP
        d.line([(cx + r1 * math.cos(a), cy - r1 * math.sin(a)), (cx + r2 * math.cos(a), cy - r2 * math.sin(a))], fill=c, width=6 if i % 5 == 0 else 3)
    for v, i in [(15, 0), (150, 9), (300, 19), (450, 29)]:
        a = math.pi - i * math.pi / 30
        metin(d, (cx + (R - 100) * math.cos(a), cy - (R - 100) * math.sin(a)), str(v), F("sans", 30), KIRMIZI if v == 450 else MUREKKEP)
    oran = [0.03, 0.03, 0.97][min(k, 2)] if k < 3 else 0.97
    a = math.pi - oran * math.pi
    d.line([(cx, cy), (cx + (R - 60) * math.cos(a), cy - (R - 60) * math.sin(a))], fill=KIRMIZI, width=12)
    d.ellipse((cx - 26, cy - 26, cx + 26, cy + 26), fill=MUREKKEP)
    metin(d, (cx, cy + 90), "VOLT", F("sans_b", 44), GRI)
    if k == 0:
        metin(d, (CX, 140), "Kaç volta kadar giderdin?", F("serif", 92))
        metin(d, (cx, cy - 130), "?", F("serif", 170), KIRMIZI)
    if k == 1:
        metin(d, (CX, 140), "Kaç volta kadar giderdin?", F("serif", 92))
        baloncuk(im, 1360, 300, "“Hiç!”", F("serif", 80), kuyruk="sol")
        insan(d, 1430, 900, 1.05, kollar="dur")
    if k >= 2:
        metin(d, (CX, 120), "PSİKOLOJİNİN EN ÜNLÜ DENEYLERİ", F("sans_b", 40), KIRMIZI)
        metin(d, (CX, 200), "Bölüm 1 · Milgram İtaat Deneyi", F("serif", 84))
        metin(d, (CX, cy + 170), "Yale Üniversitesi · 1961", F("serif_i", 46), GRI)
    return im

def s1(k):  # Yale + ilan
    im = kagit(); d = ImageDraw.Draw(im)
    # bina
    bx, by = 330, 840
    d.rectangle((bx - 230, by - 330, bx + 230, by), outline=MUREKKEP, width=6, fill=(236, 226, 210))
    d.polygon([(bx - 260, by - 330), (bx, by - 470), (bx + 260, by - 330)], outline=MUREKKEP, fill=(226, 212, 190), width=6)
    d.line([(bx - 260, by - 330), (bx, by - 470), (bx + 260, by - 330), (bx - 260, by - 330)], fill=MUREKKEP, width=6)
    for i in range(5):
        x = bx - 180 + i * 90
        d.rectangle((x - 14, by - 300, x + 14, by - 20), outline=MUREKKEP, width=4)
    d.rectangle((bx - 300, by, bx + 300, by + 24), fill=MUREKKEP)
    metin(d, (bx, by + 80), "Yale Üniversitesi", F("serif", 50))
    metin(d, (bx, by + 132), "New Haven, ABD", F("serif_i", 36), GRI)
    if k >= 1:
        # gazete ilanı
        box = (820, 150, 1560, 760)
        d = kart(im, box, fill=(250, 246, 236))
        metin(d, (1190, 215), "GÜNLÜK GAZETE", F("serif", 40), GRI)
        d.line([(860, 250), (1520, 250)], fill=MUREKKEP, width=3)
        metin(d, (1190, 330), "GÖNÜLLÜ", F("serif", 110), KIRMIZI)
        metin(d, (1190, 430), "ARANIYOR", F("serif", 80), MUREKKEP)
        metin(d, (1190, 520), "Hafıza ve öğrenme", F("serif_i", 46))
        metin(d, (1190, 572), "üzerine bilimsel araştırma", F("serif_i", 46))
        d.line([(900, 630), (1480, 630)], fill=ACIK, width=3)
        metin(d, (1190, 690), "Saati 4 dolar · Yale Üniversitesi", F("sans_m", 32), GRI)
    if k >= 2:
        etiket = ["öğretmen", "memur", "satıcı", "işçi"]
        for i, e in enumerate(etiket):
            x = 1700 + (i % 2) * 170 - 40
            y = 560 + (i // 2) * 0
        xs = [1660, 1800, 1660, 1800]
        for i, (x, e) in enumerate(zip([1640, 1790], ["öğretmen", "memur"])):
            insan(d, x, 640, 0.85, govde_renk=[(170, 196, 180), (214, 180, 140)][i])
            metin(d, (x, 680), e, F("sans_m", 28), GRI)
        for i, (x, e) in enumerate(zip([1640, 1790], ["satıcı", "işçi"])):
            insan(d, x, 960, 0.85, govde_renk=[(200, 160, 150), (160, 175, 205)][i])
            metin(d, (x, 1000), e, F("sans_m", 28), GRI)
    return im

def odalar(im, k, ses=None, sessiz=False, ogretmen_terli=False):
    d = ImageDraw.Draw(im)
    # sol: öğretmen odası, sağ: öğrenci odası
    d.rounded_rectangle((120, 230, 980, 930), 20, outline=MUREKKEP, width=5, fill=(250, 245, 236))
    d.rounded_rectangle((1040, 230, 1900, 930), 20, outline=MUREKKEP, width=5, fill=(240, 232, 220))
    d.rectangle((990, 230, 1030, 930), fill=(120, 105, 92))
    metin(d, (550, 280), "ÖĞRETMEN", F("sans_b", 36), GRI)
    metin(d, (1470, 280), "ÖĞRENCİ", F("sans_b", 36), GRI)
    return d

def ogrenci(d, x=1470, y=880, rahat=False):
    # sandalye
    d.rectangle((x - 70, y - 120, x + 70, y - 100), fill=(150, 120, 90), outline=MUREKKEP, width=4)
    d.line([(x - 60, y - 100), (x - 60, y)], fill=MUREKKEP, width=6)
    d.line([(x + 60, y - 100), (x + 60, y)], fill=MUREKKEP, width=6)
    d.rectangle((x + 50, y - 330, x + 75, y - 110), fill=(150, 120, 90), outline=MUREKKEP, width=4)
    hb = 34; by = y - 320
    d.ellipse((x - hb, by - hb, x + hb, by + hb), outline=MUREKKEP, width=6, fill=KAGIT)
    d.line([(x, by + hb + 10), (x, y - 125)], fill=MUREKKEP, width=6)
    d.line([(x, y - 125), (x - 80, y - 115), (x - 80, y)], fill=MUREKKEP, width=6)
    # kollar sandalye koluna bağlı
    d.line([(x, by + 70), (x - 70, by + 150), (x - 120, by + 150)], fill=MUREKKEP, width=6)
    d.rectangle((x - 135, by + 140, x - 95, by + 162), fill=GRI)  # kayış
    # elektrot
    d.line([(x - 120, by + 150), (x - 260, by + 60), (x - 420, by + 60)], fill=KIRMIZI, width=4)
    d.ellipse((x - 128, by + 142, x - 112, by + 158), fill=KIRMIZI)

def s2(k):  # roller + makine
    im = kagit()
    if k <= 1:
        d = odalar(im, k)
        insan(d, 400, 880, 1.15, kollar="ileri", govde_renk=(170, 196, 180))
        metin(d, (400, 980) if False else (400, 400), "", F("sans", 10))
        baloncuk(im, 200, 360, "Rol: ÖĞRETMEN", F("sans", 38), fill=(255, 250, 235))
        if k >= 1:
            ogrenci(d)
            baloncuk(im, 1150, 360, "“öğrenci”", F("serif_i", 44))
            metin(d, (1300, 900), "elektrotlar", F("sans_m", 28), KIRMIZI)
        return im
    d = ImageDraw.Draw(im)
    metin(d, (CX, 150), "Otuz düğmeli şok makinesi", F("serif", 78))
    vurgu = k >= 4
    makine(im, (110, 300, 1906, 820), aktif=30 if k >= 3 else 1, vurgula_son=vurgu)
    d = ImageDraw.Draw(im)
    if k >= 3:
        metin(d, (330, 880), "15 V", F("serif", 64), ALTIN)
        d.line([(440, 880), (1560, 880)], fill=GRI, width=5)
        d.polygon([(1560, 864), (1594, 880), (1560, 896)], fill=GRI)
        metin(d, (1700, 880), "450 V", F("serif", 64), KIRMIZI)
    return im

def s3(k):  # kural
    im = kagit(); d = ImageDraw.Draw(im)
    baslik(d, "Kural çok basit", 140)
    d = kart(im, (240, 330, 860, 700), fill=(253, 240, 236))
    metin(d, (550, 440), "✗", F("sans_b", 130), KIRMIZI)
    metin(d, (550, 600), "Yanlış cevap", F("serif", 60))
    d.line([(920, 515), (1080, 515)], fill=MUREKKEP, width=8)
    d.polygon([(1080, 490), (1130, 515), (1080, 540)], fill=MUREKKEP)
    d = kart(im, (1170, 330, 1790, 700), fill=(255, 247, 228))
    metin(d, (1480, 450), "+15 V", F("serif", 120), ALTIN)
    metin(d, (1480, 600), "Bir üst düğme", F("serif", 60))
    # basamaklar
    for i in range(10):
        x = 420 + i * 120; y = 900 - i * 14
        c = KIRMIZI if i >= 8 else ALTIN
        d.rounded_rectangle((x, y, x + 90, 930), 8, fill=c, outline=MUREKKEP, width=3)
    return im

def s4(k):  # sır
    im = kagit(); d = ImageDraw.Draw(im)
    if k == 0:
        metin(d, (CX, 470), "Ama bir sır var…", F("serif_i", 120))
        d.line([(CX - 120, 580), (CX + 120, 580)], fill=KIRMIZI, width=6)
        return im
    # öğrenci = oyuncu
    d = kart(im, (240, 220, 900, 900), fill=(252, 249, 243))
    insan(d, 570, 760, 1.05, kollar="yukari", govde_renk=(214, 180, 140))
    # maske
    d.ellipse((520, 450, 620, 520), outline=MUREKKEP, width=4)
    metin(d, (570, 830), "OYUNCU", F("sans_b", 58), KIRMIZI)
    metin(d, (570, 290), "“Öğrenci” aslında…", F("serif_i", 44), GRI)
    # elektrik yok
    simsek(d, 760, 330, 0.8, ALTIN)
    d.line([(730, 330), (830, 450)], fill=KIRMIZI, width=10)
    d.line([(830, 330), (730, 450)], fill=KIRMIZI, width=10)
    if k >= 2:
        d = kart(im, (1080, 300, 1780, 520), fill=(252, 249, 243))
        metin(d, (1430, 410), "Hafıza", F("serif", 90), GRI)
        d.line([(1270, 415), (1590, 405)], fill=KIRMIZI, width=10)
        d = kart(im, (1080, 590, 1780, 820), fill=(253, 238, 232), kenar=KIRMIZI, kw=6)
        metin(d, (1430, 705), "İTAAT", F("serif", 130), KIRMIZI)
        metin(d, (1430, 250), "Deneyin asıl konusu:", F("serif_i", 46), GRI)
    return im

def s5(k):  # sesler
    im = kagit()
    d = odalar(im, k)
    insan(d, 400, 880, 1.15, kollar="ileri", govde_renk=(170, 196, 180))
    # mini makine
    d.rounded_rectangle((560, 640, 920, 760), 14, fill=(70, 62, 56), outline=MUREKKEP, width=4)
    for i in range(10):
        c = KIRMIZI if i >= 7 else ALTIN
        on = i < [5, 8, 10][min(k, 2)]
        d.rounded_rectangle((585 + i * 33, 680, 605 + i * 33, 725), 4, fill=c if on else (130, 118, 108))
    v = [150, 285, 450][min(k, 2)]
    metin(d, (740, 600), f"{v} V", F("serif", 64), KIRMIZI if v >= 300 else ALTIN)
    ogrenci(d)
    if k == 0:
        baloncuk(im, 1150, 340, "ahh…", F("serif_i", 56), kuyruk="sag")
        for i in range(3):
            d.arc((1040 - 60 - i * 40, 520 - 60 - i * 40, 1040 + 60 + i * 40, 520 + 60 + i * 40), 150, 210, fill=GRI, width=5)
    if k == 1:
        baloncuk(im, 1095, 330, "“Bırakın beni!", F("serif_bi", 50), kuyruk="sag", renk=KIRMIZI)
        baloncuk(im, 1240, 450, "Kalbim ağrıyor!”", F("serif_bi", 50), kuyruk="sag", renk=KIRMIZI)
    if k >= 2:
        d2 = ImageDraw.Draw(im)
        ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
        ImageDraw.Draw(ov).rounded_rectangle((1040, 230, 1900, 930), 20, fill=(30, 26, 24, 150))
        im.paste(ov, mask=ov)
        d = ImageDraw.Draw(im)
        metin(d, (1470, 560), "…sessizlik", F("serif_i", 84), (240, 230, 215))
    return im

def s6(k):  # araştırmacı ısrarları
    im = kagit(); d = ImageDraw.Draw(im)
    # araştırmacı (beyaz önlük)
    insan(d, 360, 930, 1.35, kollar="asagi", govde_renk=(255, 255, 255))
    metin(d, (360, 1000), "Araştırmacı", F("sans_m", 34), GRI)
    if k == 0:
        # gönüllü terliyor
        insan(d, 1350, 930, 1.35, kollar="asagi", govde_renk=(170, 196, 180))
        for (x, y) in [(1290, 470), (1420, 455), (1440, 520)]:
            d.polygon([(x, y), (x - 10, y + 24), (x + 10, y + 24)], fill=(120, 170, 220))
            d.ellipse((x - 10, y + 14, x + 10, y + 34), fill=(120, 170, 220))
        metin(d, (1350, 160), "Terliyor · titriyor · gergin gülüşler", F("serif_i", 52), GRI)
        for i in range(4):
            d.arc((1250 - i * 6, 520, 1300 - i * 6, 640), 100, 260, fill=GRI, width=3)
        return im
    dizi = ["“Lütfen devam edin.”", "“Deneyin devam etmesi gerekiyor.”", "“Başka seçeneğiniz yok,", "devam etmelisiniz.”"]
    y = 230
    for i, t in enumerate(dizi):
        baloncuk(im, 640, y + i * 175, t, F("serif_i", 58), kuyruk="sol" if i < 3 else None, fill=(255, 252, 246))
    return im

def s7(k):  # tahmin vs sonuç
    im = kagit(); d = ImageDraw.Draw(im)
    baslik(d, "Kaç kişi 450 volta kadar gider?", 140)
    # sol kart: tahmin
    d = kart(im, (170, 290, 880, 900))
    metin(d, (525, 360), "Psikiyatristlerin tahmini", F("serif_i", 46), GRI)
    if k >= 1:
        metin(d, (525, 560), "%0,1", F("serif", 190), MUREKKEP)
        metin(d, (525, 720), "binde bir", F("serif", 64), GRI)
    else:
        metin(d, (525, 600), "?", F("serif", 200), ACIK)
    d = kart(im, (1000, 290, 1846, 900), kenar=KIRMIZI if k >= 2 else MUREKKEP)
    metin(d, (1423, 360), "Gerçek sonuç", F("serif_i", 46), GRI)
    if k >= 2:
        # 40 nokta: 26 kırmızı
        for i in range(40):
            r, c = divmod(i, 10)
            x = 1110 + c * 63; y = 440 + r * 63
            d.ellipse((x - 22, y - 22, x + 22, y + 22), fill=KIRMIZI if i < 26 else ACIK, outline=MUREKKEP, width=2)
        metin(d, (1423, 760), "%65", F("serif", 150), KIRMIZI)
        metin(d, (1423, 860), "40 kişiden 26'sı · 450 volta kadar", F("sans_m", 32), MUREKKEP)
    return im

def s8(k):  # sorumluluk devri
    im = kagit(); d = ImageDraw.Draw(im)
    if k == 0:
        metin(d, (CX, 430), "Bu insanlar kötü müydü?", F("serif", 110))
        metin(d, (CX, 600), "Milgram'a göre: HAYIR", F("serif_i", 80), KIRMIZI)
        return im
    baslik(d, "Sorumluluğu devretmek", 140)
    insan(d, 470, 900, 1.3, kollar="ileri", govde_renk=(170, 196, 180))
    metin(d, (470, 980), "gönüllü", F("sans_m", 36), GRI)
    insan(d, 1560, 900, 1.3, govde_renk=(255, 255, 255))
    metin(d, (1560, 980), "emri veren", F("sans_m", 36), GRI)
    # sorumluluk kutusu taşınıyor
    x = 1015 if k >= 1 else 640
    d = kart(im, (x - 230, 420, x + 230, 560), fill=(255, 247, 228), kenar=ALTIN, kw=6)
    metin(d, (x, 490), "SORUMLULUK", F("sans_b", 46), MUREKKEP)
    d.line([(720, 640), (1310, 640)], fill=GRI, width=6)
    d.polygon([(1310, 620), (1350, 640), (1310, 660)], fill=GRI)
    if k >= 2:
        baloncuk(im, 640, 700, "“Ben sadece bir aracım.”", F("serif_i", 50), kuyruk="sol")
    return im

def bar_grafik(im, veriler, box, en_buyuk=70):
    d = ImageDraw.Draw(im)
    x0, y0, x1, y1 = box
    n = len(veriler)
    bw = (x1 - x0) / n
    taban = y1 - 120
    d.line([(x0, taban), (x1, taban)], fill=MUREKKEP, width=4)
    for i, (et, v, c, goster) in enumerate(veriler):
        cx = x0 + bw * (i + 0.5)
        if not goster:
            metin(d, (cx, taban + 60), et, F("serif", 40), ACIK)
            continue
        h = (taban - y0 - 80) * v / en_buyuk
        d.rounded_rectangle((cx - bw * 0.3, taban - h, cx + bw * 0.3, taban), 14, fill=c, outline=MUREKKEP, width=4)
        metin(d, (cx, taban - h - 50), f"%{v:g}".replace(".", ","), F("serif", 64), c if c != ACIK else GRI)
        for j, s in enumerate(et.split("\n")):
            metin(d, (cx, taban + 50 + j * 46), s, F("serif", 40))

def s9(k):  # varyasyonlar
    im = kagit(); d = ImageDraw.Draw(im)
    baslik(d, "Küçük ayrıntılar her şeyi değiştirdi", 130)
    veriler = [("Temel\ndeney", 65, GRI, True),
               ("Emir\ntelefonla", 20.5, ALTIN, k >= 1),
               ("Eli plakaya\nbastırmak", 30, ALTIN, k >= 2),
               ("İki kişi\nreddedince", 10, YESIL, k >= 3)]
    bar_grafik(im, veriler, (200, 270, 1816, 930))
    return im

def s10(k):  # eleştiri
    im = kagit(); d = ImageDraw.Draw(im)
    baslik(d, "Deney bugün tartışmalı", 140)
    # arşiv klasörleri
    for i in range(3):
        x = 300 + i * 40; y = 330 + i * 30
        d = kart(im, (x, y, x + 520, y + 400), fill=(232, 210, 160), golge=i == 0)
    metin(d, (640, 620), "ARŞİV", F("sans_b", 64), MUREKKEP)
    madde = [(k >= 1, "Bazı gönüllüler düzenden şüphelendi"),
             (k >= 1, "Araştırmacı zaman zaman talimat dışına çıktı"),
             (k >= 2, "Ağır stres → etik kurallar değişti")]
    y = 380
    for g, t in madde:
        if g:
            d.ellipse((1000, y - 12, 1024, y + 12), fill=KIRMIZI)
            metin(d, (1050, y), t, F("serif", 44), anchor="lm")
        y += 120
    if k >= 3:
        d = kart(im, (1000, 760, 1800, 880), fill=(236, 245, 238), kenar=YESIL, kw=5)
        metin(d, (1400, 820), "Ama ana mesaj hâlâ güçlü", F("serif", 52), YESIL)
    return im

def s11(k):
    im = kagit(); d = ImageDraw.Draw(im)
    metin(d, (CX, 330), "Peki bu senin hayatında", F("serif", 96))
    metin(d, (CX, 450), "ne işe yarar?", F("serif", 96))
    if k >= 1:
        metin(d, (CX, 660), "3 DERS", F("sans_b", 150), KIRMIZI)
        for i in range(3):
            yildiz(d, CX - 260 + i * 260, 820, 26, ALTIN)
    return im

def ders_bas(d, n, t):
    d.ellipse((150, 110, 270, 230), fill=KIRMIZI)
    metin(d, (210, 172), str(n), F("serif", 84), (255, 255, 255))
    metin(d, (310, 172), t, F("serif", 76), anchor="lm")

def s12(k):  # ders 1 merdiven
    im = kagit(); d = ImageDraw.Draw(im)
    ders_bas(d, 1, "Küçük adımlara dikkat et")
    # merdiven
    n = 10
    for i in range(n):
        x = 260 + i * 150; y = 930 - (i + 1) * 58
        c = KIRMIZI if i >= 8 else (ALTIN if i >= 4 else (230, 205, 150))
        d.rectangle((x, y, x + 150, 930), fill=c, outline=MUREKKEP, width=4)
        if k >= 2:
            metin(d, (x + 75, y - 30), f"+15", F("sans", 28), GRI)
    insan(d, 330, 930 - 58, 0.7, govde_renk=(170, 196, 180))
    if k >= 1:
        metin(d, (1800, 280), "450 V", F("serif", 80), KIRMIZI)
    if k >= 3:
        baloncuk(im, 600, 300, "“tamam…” “tamam…” “tamam…”", F("serif_i", 52))
    return im

def s13(k):
    im = kagit(); d = ImageDraw.Draw(im)
    ders_bas(d, 2, "Sorumluluğu kimseye devretme")
    if k >= 1:
        box = baloncuk(im, 560, 380, "“Bana söylediler.”", F("serif_i", 100), kuyruk="sol")
        d = ImageDraw.Draw(im)
        d.line([(box[0] - 20, box[3] - 20), (box[2] + 20, box[1] + 20)], fill=KIRMIZI, width=14)
        metin(d, (CX, 800), "Sonucu ortadan kaldırmaz.", F("serif", 70), KIRMIZI)
    return im

def s14(k):
    im = kagit(); d = ImageDraw.Draw(im)
    ders_bas(d, 3, "Tek bir itiraz bile güç verir")
    xs = [420, 720, 1020, 1320, 1620]
    for i, x in enumerate(xs):
        if i == 0:
            insan(d, x, 900, 1.15, kollar="dur", govde_renk=(170, 196, 180))
        elif k >= 1 and i <= 2:
            insan(d, x, 900, 1.15, kollar="dur", govde_renk=(200, 225, 205))
        else:
            insan(d, x, 900, 1.15, govde_renk=ACIK, c=GRI)
    baloncuk(im, 300, 340, "HAYIR", F("sans_b", 70), kuyruk="sol", renk=KIRMIZI)
    if k >= 2:
        baloncuk(im, 1150, 300, "…belki de o kişi sensin.", F("serif_i", 58), kuyruk="sag")
    return im

def s15(k):
    im = kagit(); d = ImageDraw.Draw(im)
    metin(d, (CX, 230), "“", F("serif", 260), ALTIN)
    metin(d, (CX, 430), "Kötülük çoğu zaman canavarlardan değil,", F("serif_i", 76))
    metin(d, (CX, 540), "itiraz etmeyen", F("serif_bi", 96), KIRMIZI)
    metin(d, (CX, 650), "sıradan insanlardan doğar.", F("serif_i", 76))
    cizgi_alt(d, CX, 760, 600)
    metin(d, (CX, 830), "Milgram İtaat Deneyi · 1961", F("sans_m", 36), GRI)
    return im

def s16(k):
    im = kagit(); d = ImageDraw.Draw(im)
    metin(d, (CX, 140), "SIRADAKİ BÖLÜM", F("sans_b", 44), KIRMIZI)
    metin(d, (CX, 230), "Asch Uyum Deneyi", F("serif", 100))
    # çizgi kartları
    d = kart(im, (280, 340, 860, 840))
    d.line([(570, 420), (570, 760)], fill=MUREKKEP, width=14)
    metin(d, (570, 800), "Referans", F("sans_m", 32), GRI)
    d = kart(im, (960, 340, 1740, 840))
    for i, (h, t) in enumerate([(260, "A"), (340, "B"), (200, "C")]):
        x = 1100 + i * 250
        d.line([(x, 760 - h), (x, 760)], fill=MUREKKEP, width=14)
        metin(d, (x, 800), t, F("serif", 44))
    if k >= 1:
        for i in range(3):
            metin(d, (1100 + i * 250, 380), "?", F("serif", 70), KIRMIZI)
        metin(d, (570, 380), "?", F("serif", 70), KIRMIZI)
    return im

SAHNELER = [s0, s1, s2, s3, s4, s5, s6, s7, s8, s9, s10, s11, s12, s13, s14, s15, s16]

def ust_bilgi(im1920, rozet):
    """1920x1080 sabit katman: rozet + bölüm etiketi (RGBA)."""
    ov = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
    r = rozet.copy(); r.thumbnail((210, 80))
    ov.paste(r, (40, 34), r)
    d = ImageDraw.Draw(ov)
    return ov
    t = ""
    f = F("sans_m", 26)
    tw = d.textlength(t, font=f)
    d.rounded_rectangle((1880 - tw - 40, 44, 1880, 100), 28, fill=(252, 249, 243, 230), outline=(43, 36, 32, 255), width=2)
    d.text((1880 - tw - 20, 72), t, font=f, fill=MUREKKEP, anchor="lm")
    return ov
