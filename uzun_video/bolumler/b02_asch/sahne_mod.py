# Bölüm 2 · Asch Uyum Deneyi — sahneler
from sahneler import *

ETIKET = "#2"
TETIK = [[None, "Ama", "Bugün"], [None, "Bir", "Önlerine", "Soru"], [None, "Ama", "Masadaki", "Gerçek"],
         [None, "Ama", "Sıra"], [None, "Ama", "Kritik"], [None, "Bazıları", "Ama"], [None, "Masaya", "Sonuç"],
         [None, "Üç", "Bir"], [None, "1980'de", "Ama"], [None, "Üç"], [None, "fikre"], [None, "Deney"],
         [None, "Böylece"], [None], [None, "Stanford"]]

YESIL_A = (200, 225, 205)
EKIP = (226, 190, 170)

def cizgi_kartlari(im, x, y, s=1.0, dogru_vurgu=False, kucuk=False):
    """Referans kart + A/B/C kartı. (x,y) sol üst."""
    w1, w2, h = int(300 * s), int(460 * s), int(380 * s)
    d = kart(im, (x, y, x + w1, y + h))
    cx = x + w1 // 2
    d.line([(cx, y + 100 * s), (cx, y + 300 * s)], fill=MUREKKEP, width=max(6, int(12 * s)))
    if not kucuk:
        metin(d, (cx, y + 340 * s), "Referans", F("sans_m", int(30 * s)), GRI)
    x2 = x + w1 + int(50 * s)
    d = kart(im, (x2, y, x2 + w2, y + h))
    for i, (L, t) in enumerate([(150, "A"), (250, "B"), (200, "C")]):
        lx = x2 + int((90 + i * 140) * s)
        c = YESIL if (dogru_vurgu and t == "C") else MUREKKEP
        if dogru_vurgu and t == "C":
            d.rounded_rectangle((lx - 45 * s, y + 30 * s, lx + 45 * s, y + h - 15 * s), int(16 * s), outline=YESIL, width=max(3, int(6 * s)))
        d.line([(lx, y + (300 - L) * s), (lx, y + 300 * s)], fill=c, width=max(6, int(12 * s)))
        metin(d, (lx, y + 340 * s), t, F("serif", int(44 * s)), c)
    return x2 + w2

def masa(d, x0, x1, y):
    d.rounded_rectangle((x0, y, x1, y + 40), 10, fill=(170, 135, 100), outline=MUREKKEP, width=5)
    d.line([(x0 + 40, y + 40), (x0 + 40, y + 200)], fill=MUREKKEP, width=8)
    d.line([(x1 - 40, y + 40), (x1 - 40, y + 200)], fill=MUREKKEP, width=8)

def sira(d, xs, ytaban, renkler, s=0.9):
    for x, r in zip(xs, renkler):
        insan(d, x, ytaban, s, govde_renk=r)

XS7 = [300, 520, 740, 960, 1180, 1400, 1620]

def s0(k):
    im = kagit(); d = ImageDraw.Draw(im)
    if k < 2:
        metin(d, (CX, 130), "Hangisi aynı uzunlukta?", F("serif", 90))
        cizgi_kartlari(im, 560, 230, 0.95)
        d = ImageDraw.Draw(im)
        if k == 1:
            for i, x in enumerate([260, 460, 1560, 1760]):
                insan(d, x, 940, 0.7, govde_renk=EKIP)
                baloncuk(im, x - 40, 560, "A!", F("sans_b", 52), renk=KIRMIZI)
                d = ImageDraw.Draw(im)
            metin(d, (CX, 820), "…herkes yanlış söylüyor", F("serif_i", 60), KIRMIZI)
        return im
    metin(d, (CX, 120), "PSİKOLOJİNİN EN ÜNLÜ DENEYLERİ", F("sans_b", 40), KIRMIZI)
    metin(d, (CX, 205), "Bölüm 2 · Asch Uyum Deneyi", F("serif", 88))
    cizgi_alt(d, CX, 268, 760)
    cizgi_kartlari(im, 640, 340, 0.75, dogru_vurgu=True)
    d = ImageDraw.Draw(im)
    metin(d, (CX, 690), "Swarthmore Koleji · 1951", F("serif_i", 48), GRI)
    return im

def s1(k):
    im = kagit(); d = ImageDraw.Draw(im)
    if k == 0:
        metin(d, (CX, 330), "1951", F("serif", 230), KIRMIZI)
        metin(d, (CX, 520), "Psikolog Solomon Asch", F("serif", 80))
        d = kart(im, (CX - 330, 620, CX + 330, 740), fill=(255, 247, 228), kenar=ALTIN, kw=5)
        metin(d, (CX, 680), "“Görme testi” için davet", F("serif_i", 52))
        return im
    xs = [200, 360, 520, 680, 840, 1000, 1160] if k >= 2 else XS7
    masa(d, xs[0] - 110, xs[-1] + 110, 720)
    for x in xs:
        insan(d, x, 760, 0.85, govde_renk=YESIL_A)
    d.rounded_rectangle((xs[0] - 110, 740, xs[-1] + 110, 760), 6, fill=(170, 135, 100))
    if k >= 2:
        cizgi_kartlari(im, 1300, 250, 0.62)
        d = ImageDraw.Draw(im)
        d.line([(1450, 486), (1450, 880)], fill=MUREKKEP, width=6)
        d.line([(1750, 486), (1750, 880)], fill=MUREKKEP, width=6)
    if k >= 3:
        baloncuk(im, 700, 300, "Hangisi aynı uzunlukta?", F("serif_i", 46), kuyruk="sag")
    metin(d, (680 if k >= 2 else CX, 150 if k < 3 else 150), "Masada 7-8 kişi", F("serif", 64))
    return im

def s2(k):
    im = kagit(); d = ImageDraw.Draw(im)
    if k == 1:
        metin(d, (CX, 470), "Ama yine bir sır var…", F("serif_i", 120))
        d.line([(CX - 120, 580), (CX + 120, 580)], fill=KIRMIZI, width=6)
        return im
    gercek = 5
    renk = [YESIL_A] * 7 if k == 0 else [EKIP if i != gercek else YESIL_A for i in range(7)]
    masa(d, 190, 1730, 720)
    sira(d, XS7, 760, renk, 0.85)
    d.rounded_rectangle((190, 740, 1730, 760), 6, fill=(170, 135, 100))
    if k == 0:
        metin(d, (CX, 150), "İlk turlar: herkes doğru cevap veriyor", F("serif", 62))
        for x in XS7:
            baloncuk(im, x - 40, 330, "C ✓", F("sans_b", 40), renk=YESIL)
        return im
    metin(d, (CX, 150), "Masadakilerin hepsi… bir kişi hariç", F("serif", 62))
    d = ImageDraw.Draw(im)
    for i, x in enumerate(XS7):
        if i == gercek:
            continue
        d.rounded_rectangle((x - 70, 280, x + 70, 330), 14, fill=KIRMIZI)
        metin(d, (x, 305), "EKİP", F("sans_b", 30), (255, 255, 255))
    x = XS7[gercek]
    d.rounded_rectangle((x - 120, 260, x + 120, 340), 16, fill=YESIL)
    metin(d, (x, 300), "GERÇEK", F("sans_b", 36), (255, 255, 255))
    if k >= 3:
        for i, xx in enumerate(XS7):
            d.ellipse((xx - 26, 830, xx + 26, 882), fill=MUREKKEP if i != gercek else YESIL)
            metin(d, (xx, 856), str(i + 1), F("sans_b", 30), (255, 255, 255))
        d.line([(x, 400), (x, 450)], fill=YESIL, width=6)
        baloncuk(im, x - 520, 380, "Önce herkesi duyuyor…", F("serif_i", 44), kuyruk="sag")
    return im

def s3(k):
    im = kagit(); d = ImageDraw.Draw(im)
    if k == 0:
        metin(d, (CX, 130), "Cevap açıkça C", F("serif", 90), YESIL)
        cizgi_kartlari(im, 540, 250, 1.05, dogru_vurgu=True)
        return im
    xs = [260, 470, 680, 890, 1100, 1450, 1720]
    renk = [EKIP] * 5 + [YESIL_A, EKIP]
    masa(d, 160, 1820, 720)
    sira(d, xs, 760, renk, 0.85)
    d.rounded_rectangle((160, 740, 1820, 760), 6, fill=(170, 135, 100))
    for i, x in enumerate(xs[:5]):
        baloncuk(im, x - 45, 300, "“A”", F("serif_bi", 52), renk=KIRMIZI)
    d = ImageDraw.Draw(im)
    metin(d, (680, 150), "1… 2… 3… 4… 5… hepsi “A”!", F("serif", 64), KIRMIZI)
    if k >= 2:
        ov = Image.new("RGBA", im.size, (30, 26, 24, 150))
        m = Image.new("L", im.size, 255)
        ImageDraw.Draw(m).ellipse((1450 - 230, 300, 1450 + 230, 900), fill=0)
        m = m.filter(ImageFilter.GaussianBlur(40))
        im.paste((40, 34, 30), mask=Image.eval(m, lambda v: int(v * 0.62)))
        d = ImageDraw.Draw(im)
        metin(d, (1450, 220), "?", F("serif", 150), (255, 220, 120))
        metin(d, (700, 940), "Sıra sende…", F("serif_i", 72), (250, 240, 225))
    return im

def s4(k):
    im = kagit(); d = ImageDraw.Draw(im)
    baslik(d, "Sonuç", 130)
    d = kart(im, (150, 290, 680, 880))
    metin(d, (415, 360), "Tek başına", F("serif_i", 46), GRI)
    insan(d, 415, 700, 0.9, govde_renk=YESIL_A)
    metin(d, (415, 790), "hata < %1", F("serif", 64), YESIL)
    if k >= 1:
        d = kart(im, (740, 290, 1270, 880), kenar=KIRMIZI)
        metin(d, (1005, 360), "Grupla birlikte", F("serif_i", 46), GRI)
        for i in range(4):
            x = 860 + i * 95
            insan(d, x, 640, 0.6, govde_renk=KIRMIZI if i < 3 else YESIL_A)
        metin(d, (1005, 730), "4 kişiden 3'ü", F("serif", 62), KIRMIZI)
        metin(d, (1005, 810), "en az bir kez uydu", F("sans_m", 34))
    if k >= 2:
        d = kart(im, (1330, 290, 1866, 880), kenar=KIRMIZI)
        metin(d, (1598, 360), "Kritik turlarda", F("serif_i", 46), GRI)
        metin(d, (1598, 560), "~1/3", F("serif", 170), KIRMIZI)
        metin(d, (1598, 730), "yanlışa katıldı", F("serif", 50))
        metin(d, (1598, 800), "(yaklaşık %32)", F("sans_m", 34), GRI)
    return im

def s5(k):
    im = kagit(); d = ImageDraw.Draw(im)
    if k == 0:
        metin(d, (CX, 460), "Peki neden?", F("serif", 150))
        return im
    baslik(d, "Neden uydular?", 130)
    d = kart(im, (170, 290, 950, 880))
    metin(d, (560, 360), "1 · Bilgi etkisi", F("sans_b", 44), ALTIN)
    insan(d, 400, 840, 0.95, govde_renk=YESIL_A)
    baloncuk(im, 470, 430, "“Galiba ben yanlış\ngörüyorum…”", F("serif_i", 44))
    if k >= 2:
        d = kart(im, (1066, 290, 1846, 880), kenar=KIRMIZI)
        metin(d, (1456, 360), "2 · Uyum baskısı", F("sans_b", 44), KIRMIZI)
        insan(d, 1290, 840, 0.95, govde_renk=YESIL_A)
        baloncuk(im, 1360, 430, "“Tek farklı kişi\nolmak istemiyorum.”", F("serif_i", 44))
    return im

def s6(k):
    im = kagit(); d = ImageDraw.Draw(im)
    baslik(d, "Tek bir müttefik yeter!", 130)
    veriler = [("Normal\ngrup", 32, KIRMIZI, True), ("Bir kişi\ndoğruyu söyleyince", 5.5, YESIL, k >= 2)]
    bar_grafik(im, veriler, (120, 290, 980, 930), en_buyuk=40)
    d = ImageDraw.Draw(im)
    xs = [1120, 1300, 1480, 1660]
    for i, x in enumerate(xs):
        dost = k >= 1 and i == 1
        insan(d, x, 860, 0.75, govde_renk=YESIL if dost else EKIP)
        baloncuk(im, x - 40, 420, "C!" if dost else "A", F("sans_b", 44), renk=YESIL if dost else KIRMIZI)
        d = ImageDraw.Draw(im)
    if k >= 1:
        metin(d, (1390, 330), "doğruyu söyleyen 1 kişi", F("serif_i", 44), YESIL)
    return im

def s7(k):
    im = kagit(); d = ImageDraw.Draw(im)
    if k < 2:
        baslik(d, "Kaç kişi yanlış söylerse?", 130)
        veriler = [("1 kişi", 3, ALTIN, True), ("2 kişi", 13, ALTIN, True), ("3 kişi", 32, KIRMIZI, k >= 1),
                   ("15 kişi", 31, KIRMIZI, k >= 1)]
        bar_grafik(im, veriler, (200, 270, 1816, 930), en_buyuk=40)
        if k >= 1:
            d = ImageDraw.Draw(im)
            metin(d, (1450, 300), "3'ten sonra pek değişmiyor", F("serif_i", 44), GRI)
        return im
    baslik(d, "Cevap kâğıda yazılınca…", 130)
    d = kart(im, (620, 280, 1400, 860), fill=(255, 253, 246))
    for i in range(6):
        d.line([(680, 380 + i * 70), (1340, 380 + i * 70)], fill=ACIK, width=3)
    metin(d, (1010, 470), "Cevabım: C", F("serif_bi", 90), YESIL)
    d.line([(1450, 380), (1650, 740)], fill=ALTIN, width=26)
    d.polygon([(1640, 722), (1668, 772), (1680, 714)], fill=MUREKKEP)
    metin(d, (1010, 760), "uyma ciddi şekilde azaldı", F("serif", 52), YESIL)
    return im

def s8(k):
    im = kagit(); d = ImageDraw.Draw(im)
    baslik(d, "Deneyin eleştirileri", 130)
    d = kart(im, (170, 290, 950, 650))
    metin(d, (560, 350), "Katılımcılar", F("serif_i", 44), GRI)
    metin(d, (560, 410), "ABD · erkek · üniversite öğrencisi", F("sans_m", 32))
    for i in range(5):
        insan(d, 340 + i * 110, 625, 0.55, govde_renk=(160, 175, 205))
    if k >= 1:
        d = kart(im, (1066, 290, 1846, 650))
        metin(d, (1456, 360), "1980 · İngiltere tekrarı", F("serif_i", 44), GRI)
        metin(d, (1456, 470), "uyma çok daha düşük", F("serif", 58), YESIL)
        metin(d, (1456, 545), "→ dönemin kültürü etkili olabilir", F("sans_m", 32))
    if k >= 2:
        # telefon
        d = kart(im, (820, 640, 1200, 1000) if False else (880, 690, 1140, 930), fill=(40, 36, 34), r=30)
        d.rounded_rectangle((900, 715, 1120, 905), 12, fill=(252, 249, 243))
        for i in range(3):
            y = 750 + i * 60
            d.ellipse((895, y - 18, 931, y + 18), fill=KIRMIZI)
            d.rounded_rectangle((945, y - 10, 1120 - i * 30, y + 10), 6, fill=ACIK)
        metin(d, (560, 800), "Sosyal baskı bugün de", F("serif", 56), anchor="mm")
        metin(d, (1500, 800), "…belki daha da fazla!", F("serif_i", 56), KIRMIZI)
    return im

def s9(k):
    im = kagit(); d = ImageDraw.Draw(im)
    metin(d, (CX, 330), "Peki bu senin hayatında", F("serif", 96))
    metin(d, (CX, 450), "ne işe yarar?", F("serif", 96))
    if k >= 1:
        metin(d, (CX, 660), "3 DERS", F("sans_b", 150), KIRMIZI)
        for i in range(3):
            yildiz(d, CX - 260 + i * 260, 820, 26, ALTIN)
    return im

def s10(k):
    im = kagit(); d = ImageDraw.Draw(im)
    ders_bas(d, 1, "Herkesin söylemesi, doğru yapmaz")
    for i, x in enumerate([330, 520, 710]):
        insan(d, x, 860, 0.8, govde_renk=EKIP)
        baloncuk(im, x - 40, 400, "A", F("sans_b", 46), renk=KIRMIZI)
        d = ImageDraw.Draw(im)
    metin(d, (1000, 620), "≠", F("serif", 220), MUREKKEP)
    metin(d, (1000, 800), "doğru", F("serif", 60), GRI)
    if k >= 1:
        cizgi_kartlari(im, 1180, 360, 0.55, dogru_vurgu=True, kucuk=True)
        d = ImageDraw.Draw(im)
        d.ellipse((1560, 330, 1760, 530), outline=MUREKKEP, width=12)
        d.line([(1740, 510), (1840, 620)], fill=MUREKKEP, width=22)
        metin(d, (1500, 700), "Kanıtına bak!", F("serif", 70), YESIL)
    return im

def s11(k):
    im = kagit(); d = ImageDraw.Draw(im)
    ders_bas(d, 2, "Doğruyu söyleyen ilk kişi ol")
    xs = [360, 660, 960, 1260, 1560]
    for i, x in enumerate(xs):
        yes = i == 2 or (k >= 1 and i in (1, 3))
        insan(d, x, 900, 1.05, kollar="yukari" if i == 2 else "asagi", govde_renk=YESIL if yes else ACIK, c=MUREKKEP if yes else GRI)
    baloncuk(im, 900, 330, "C!", F("sans_b", 70), renk=YESIL)
    if k >= 1:
        d = ImageDraw.Draw(im)
        metin(d, (CX, 300), "", F("sans", 10))
        baloncuk(im, 1330, 300, "Tek kişi bile\nodayı değiştirir.", F("serif_i", 48), kuyruk="sol")
    return im

def s12(k):
    im = kagit(); d = ImageDraw.Draw(im)
    ders_bas(d, 3, "Fikrini önce kâğıda yaz")
    d = kart(im, (260, 300, 900, 860), fill=(255, 253, 246))
    for i in range(6):
        d.line([(310, 400 + i * 70), (850, 400 + i * 70)], fill=ACIK, width=3)
    metin(d, (580, 360), "Benim fikrim:", F("serif_bi", 52))
    for i, w in enumerate([420, 360, 460, 300]):
        d.line([(320, 465 + i * 70), (320 + w, 465 + i * 70)], fill=MUREKKEP, width=5)
    d.line([(930, 380), (1100, 700)], fill=ALTIN, width=24)
    if k >= 1:
        masa(d, 1180, 1820, 760)
        for i, x in enumerate([1270, 1430, 1590, 1740]):
            insan(d, x, 800, 0.6, govde_renk=YESIL if i == 1 else EKIP)
        d.rounded_rectangle((1395, 520, 1465, 600), 6, fill=(255, 253, 246), outline=MUREKKEP, width=4)
        metin(d, (1500, 400), "Fikrini kaybetme", F("serif", 58), YESIL)
    return im

def s13(k):
    im = kagit(); d = ImageDraw.Draw(im)
    metin(d, (CX, 230), "“", F("serif", 260), ALTIN)
    metin(d, (CX, 430), "Çoğu zaman bizi yanıltan gözlerimiz değil,", F("serif_i", 76))
    metin(d, (CX, 560), "başkalarına uyma isteğimiz.", F("serif_bi", 92), KIRMIZI)
    cizgi_alt(d, CX, 680, 600)
    metin(d, (CX, 750), "Asch Uyum Deneyi · 1951", F("sans_m", 36), GRI)
    return im

def s14(k):
    im = kagit(); d = ImageDraw.Draw(im)
    metin(d, (CX, 140), "SIRADAKİ BÖLÜM", F("sans_b", 44), KIRMIZI)
    # gardiyan
    insan(d, 700, 860, 1.25, govde_renk=(120, 140, 170))
    d.rounded_rectangle((640, 450, 760, 480), 8, fill=MUREKKEP)
    d.rectangle((660, 420, 740, 455), fill=(120, 140, 170), outline=MUREKKEP, width=4)
    d.line([(770, 560), (830, 700)], fill=MUREKKEP, width=14)
    metin(d, (700, 940), "Gardiyan", F("serif", 52))
    # mahkûm
    insan(d, 1320, 860, 1.25, govde_renk=(240, 236, 226))
    for i in range(5):
        y = 560 + i * 40
        d.line([(1272, y), (1368, y)], fill=MUREKKEP, width=6)
    metin(d, (1320, 940), "Mahkûm", F("serif", 52))
    if k >= 1:
        metin(d, (CX, 245), "Stanford Hapishane Deneyi", F("serif", 96))
    else:
        metin(d, (CX, 245), "Roller dağıtıldı…", F("serif_i", 80), GRI)
    return im

SAHNELER = [s0, s1, s2, s3, s4, s5, s6, s7, s8, s9, s10, s11, s12, s13, s14]
