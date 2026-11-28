# Bölüm 3 · Stanford Hapishane Deneyi — sahneler
from sahneler import *

TETIK = [[None, '"Ben', "1971'de"], [None, "Psikolog", "Başvuranlar", "Ve"],
         [None, "Üniversitenin", "Mahkûmlara", "Gardiyanlara"], [None, "Ama", "Gardiyanlar", "Bazı"],
         [None, "Diğerleri", "Ve"], [None, "Peki", "Hapishaneyi", "Onlarca"], [None, "Yani", "Bu"],
         [None, "Yıllar", "Gardiyanlara", "Krize", "Ve"], [None, "En"], [None, "Üç"], [None, "Yeni"],
         [None, "İnsanlar"], [None, "Milgram'da,"], [None], [None, "Neden?"]]

MAVI = (120, 140, 170)
BEYAZ = (240, 236, 226)

def gozluk(d, x, y, s=1.0):
    d.rounded_rectangle((x - 46 * s, y - 14 * s, x - 6 * s, y + 14 * s), int(8 * s), fill=(60, 70, 90), outline=MUREKKEP, width=3)
    d.rounded_rectangle((x + 6 * s, y - 14 * s, x + 46 * s, y + 14 * s), int(8 * s), fill=(60, 70, 90), outline=MUREKKEP, width=3)
    d.line([(x - 6 * s, y - 4 * s), (x + 6 * s, y - 4 * s)], fill=MUREKKEP, width=3)
    d.line([(x - 36 * s, y - 8 * s), (x - 22 * s, y + 6 * s)], fill=(200, 210, 230), width=3)

def gardiyan(d, x, y, s=1.0, cop=True):
    by = insan(d, x, y, s, govde_renk=MAVI)
    d.rounded_rectangle((x - 46 * s, by - 44 * s, x + 46 * s, by - 26 * s), int(6 * s), fill=MUREKKEP)
    d.rectangle((x - 34 * s, by - 70 * s, x + 34 * s, by - 40 * s), fill=MAVI, outline=MUREKKEP, width=4)
    gozluk(d, x, by + 2 * s, 0.75 * s)
    if cop:
        d.line([(x + 60 * s, by + 120 * s), (x + 110 * s, by + 230 * s)], fill=MUREKKEP, width=int(14 * s))

def mahkum(d, x, y, s=1.0, no=None):
    by = insan(d, x, y, s, govde_renk=BEYAZ)
    d.chord((x - 36 * s, by - 40 * s, x + 36 * s, by + 10 * s), 180, 360, fill=(150, 140, 130), outline=MUREKKEP, width=3)
    if no:
        d.rectangle((x - 30 * s, by + 80 * s, x + 30 * s, by + 110 * s), fill=(255, 255, 255), outline=MUREKKEP, width=2)
        metin(d, (x, by + 95 * s), no, F("sans_b", int(20 * s)))

def parmaklik(d, x0, y0, x1, y1, n=9, c=MUREKKEP):
    for i in range(n):
        x = x0 + (x1 - x0) * i / (n - 1)
        d.line([(x, y0), (x, y1)], fill=c, width=10)
    d.line([(x0, y0), (x1, y0)], fill=c, width=12)
    d.line([(x0, (y0 + y1) // 2), (x1, (y0 + y1) // 2)], fill=c, width=8)

def s0(k):
    im = kagit(); d = ImageDraw.Draw(im)
    if k == 2:
        metin(d, (CX, 120), "PSİKOLOJİNİN EN ÜNLÜ DENEYLERİ", F("sans_b", 40), KIRMIZI)
        metin(d, (CX, 205), "Bölüm 3 · Stanford Hapishane Deneyi", F("serif", 84))
        cizgi_alt(d, CX, 268, 820)
        gardiyan(d, 760, 820, 1.1); mahkum(d, 1260, 820, 1.1, "416")
        parmaklik(d, 1080, 380, 1440, 860, n=6, c=(90, 80, 72))
        metin(d, (CX, 895), "Stanford Üniversitesi · 1971", F("serif_i", 46), GRI)
        return im
    metin(d, (CX, 130), "Sen nasıl biri olurdun?", F("serif", 92))
    # üniforma eşyaları
    d = kart(im, (220, 300, 620, 700)); metin(d, (420, 640), "üniforma", F("sans_m", 34), GRI)
    d.rounded_rectangle((330, 380, 510, 590), 26, fill=MAVI, outline=MUREKKEP, width=5)
    d = kart(im, (680, 300, 1080, 700)); metin(d, (880, 640), "aynalı gözlük", F("sans_m", 34), GRI)
    gozluk(d, 880, 470, 2.6)
    d = kart(im, (1140, 300, 1540, 700)); metin(d, (1340, 640), "cop", F("sans_m", 34), GRI)
    d.line([(1260, 560), (1420, 400)], fill=MUREKKEP, width=26)
    d = kart(im, (1600, 300, 1800, 700), fill=(253, 238, 232), kenar=KIRMIZI)
    metin(d, (1700, 480), "+", F("serif", 90), KIRMIZI); metin(d, (1700, 600), "YETKİ", F("sans_b", 34), KIRMIZI)
    if k == 1:
        baloncuk(im, 640, 760, "“Ben yine ben olurum.”", F("serif_i", 60), kuyruk="sol")
    else:
        metin(d, (CX, 820), "?", F("serif", 150), KIRMIZI)
    return im

def s1(k):
    im = kagit(); d = ImageDraw.Draw(im)
    if k == 0:
        bx, by = CX, 760
        d.rectangle((bx - 420, by - 300, bx + 420, by), outline=MUREKKEP, width=6, fill=(236, 214, 190))
        for i in range(7):
            x = bx - 330 + i * 110
            d.arc((x - 40, by - 260, x + 40, by - 180), 180, 360, fill=MUREKKEP, width=5)
            d.rectangle((x - 40, by - 220, x + 40, by - 30), outline=MUREKKEP, width=5)
        d.polygon([(bx - 460, by - 300), (bx + 460, by - 300), (bx + 420, by - 350), (bx - 420, by - 350)], fill=(200, 90, 70), outline=MUREKKEP)
        d.rectangle((bx - 480, by, bx + 480, by + 24), fill=MUREKKEP)
        metin(d, (CX, 160), "Stanford Üniversitesi", F("serif", 90))
        metin(d, (CX, 260), "Kaliforniya · Ağustos 1971", F("serif_i", 48), GRI)
        return im
    if k == 1:
        d = kart(im, (520, 150, 1500, 860), fill=(250, 246, 236))
        metin(d, (1010, 220), "GÜNLÜK GAZETE", F("serif", 40), GRI)
        d.line([(570, 255), (1450, 255)], fill=MUREKKEP, width=3)
        metin(d, (1010, 360), "GÖNÜLLÜ ARANIYOR", F("serif", 84), KIRMIZI)
        metin(d, (1010, 470), "Hapishane hayatı üzerine", F("serif_i", 56))
        metin(d, (1010, 535), "psikoloji araştırması", F("serif_i", 56))
        d.rounded_rectangle((830, 620, 1190, 740), 20, fill=(255, 247, 228), outline=ALTIN, width=5)
        metin(d, (1010, 680), "15 $ / gün", F("serif", 70), MUREKKEP)
        metin(d, (1010, 800), "1-2 hafta · Stanford Üniversitesi", F("sans_m", 32), GRI)
        return im
    metin(d, (CX, 130), "24 üniversite öğrencisi" if k == 2 else "Yazı tura: rastgele ikiye bölündü", F("serif", 76))
    for i in range(24):
        r, c = divmod(i, 12)
        x = 220 + c * 135; y = 560 + r * 330
        if k == 3:
            if c < 6:
                gardiyan(d, x - 40, y, 0.55, cop=False)
            else:
                mahkum(d, x + 40, y, 0.55)
        else:
            insan(d, x, y, 0.55, govde_renk=(200, 225, 205))
    if k == 3:
        d.line([(CX, 260), (CX, 930)], fill=GRI, width=4)
        metin(d, (560, 240), "GARDİYAN", F("sans_b", 46), MAVI)
        metin(d, (1460, 240), "MAHKÛM", F("sans_b", 46), KIRMIZI)
    return im

def s2(k):
    im = kagit(); d = ImageDraw.Draw(im)
    if k == 0:
        metin(d, (CX, 130), "Pazar sabahı: gerçek polis!", F("serif", 84))
        # polis arabası
        d.rounded_rectangle((420, 520, 1300, 760), 40, fill=(250, 250, 250), outline=MUREKKEP, width=6)
        d.polygon([(600, 520), (700, 400), (1020, 400), (1120, 520)], fill=(250, 250, 250), outline=MUREKKEP)
        d.line([(600, 520), (700, 400), (1020, 400), (1120, 520)], fill=MUREKKEP, width=6)
        d.rectangle((420, 600, 1300, 660), fill=(40, 50, 80))
        metin(d, (860, 630), "POLİS", F("sans_b", 44), (255, 255, 255))
        d.rounded_rectangle((820, 360, 900, 400), 8, fill=KIRMIZI)
        for x in (560, 1160):
            d.ellipse((x - 70, 700, x + 70, 840), fill=MUREKKEP); d.ellipse((x - 30, 740, x + 30, 800), fill=GRI)
        # kelepçe
        for cx in (1520, 1660):
            d.ellipse((cx - 70, 470, cx + 70, 610), outline=MUREKKEP, width=16)
        d.line([(1590, 540), (1590, 540)], fill=MUREKKEP, width=8)
        d.line([(1580, 530), (1600, 550)], fill=MUREKKEP, width=10)
        return im
    if k == 1:
        metin(d, (CX, 130), "Bodrum kat → hapishane", F("serif", 84))
        d = kart(im, (220, 260, 1800, 900), fill=(205, 195, 182))
        for i, x0 in enumerate([300, 820, 1340]):
            d.rectangle((x0, 360, x0 + 400, 860), fill=(120, 110, 100), outline=MUREKKEP, width=5)
            parmaklik(d, x0 + 20, 380, x0 + 380, 850, n=7)
            metin(d, (x0 + 200, 320), f"HÜCRE {i + 1}", F("sans_b", 32), MUREKKEP)
        return im
    metin(d, (CX, 130), "İsim yok, sadece numara" if k == 2 else "Gücün kıyafeti", F("serif", 84))
    mahkum(d, 600, 830, 1.5, "416")
    for i, n in enumerate(["5704", "7258"]):
        mahkum(d, 330 + i * 540, 920, 0.9, n) if False else None
    if k >= 3:
        gardiyan(d, 1350, 830, 1.5)
        d.line([(1500, 330), (1700, 260)], fill=GRI, width=3)
        metin(d, (1720, 240), "aynalı gözlük", F("sans_m", 32), GRI, anchor="lm")
        metin(d, (1350, 890), "haki üniforma · cop", F("sans_m", 34), GRI)
    metin(d, (600, 890), "isim yerine numara", F("sans_m", 34), GRI)
    return im

def s3(k):
    im = kagit(); d = ImageDraw.Draw(im)
    baslik(d, "Günler geçtikçe…", 120)
    gunler = ["1. Gün", "2. Gün", "3. Gün", "4. Gün", "5. Gün", "6. Gün"]
    for i, g in enumerate(gunler):
        x = 260 + i * 300
        c = YESIL if i == 0 else (KIRMIZI if (k >= 1 and i == 1) else GRI)
        d.ellipse((x - 18, 300, x + 18, 336), fill=c)
        metin(d, (x, 370), g, F("sans", 32), c)
    d.line([(260, 318), (1760, 318)], fill=GRI, width=4)
    metin(d, (260, 450), "sakin", F("serif_i", 46), YESIL)
    if k >= 1:
        baloncuk(im, 470, 430, "İSYAN!", F("sans_b", 60), renk=KIRMIZI)
    if k >= 2:
        d = ImageDraw.Draw(im)
        for i, t in enumerate(["şınav cezaları", "uykusuz geceler", "hücre hapsi"]):
            d = kart(im, (820 + i * 0, 440 + i * 140, 1500, 550 + i * 140), fill=(253, 238, 232), kenar=KIRMIZI, kw=4)
            metin(d, (1160, 495 + i * 140), t, F("serif", 52), KIRMIZI)
    if k >= 3:
        d = ImageDraw.Draw(im)
        for i in range(5):
            h = 60 + i * 60
            d.rounded_rectangle((1580 + i * 50, 880 - h, 1620 + i * 50, 880), 8, fill=KIRMIZI if i > 2 else ALTIN)
        metin(d, (1700, 905), "sertlik", F("sans_m", 30), GRI)
    return im

def s4(k):
    im = kagit(); d = ImageDraw.Draw(im)
    # saat
    d = kart(im, (180, 240, 720, 860))
    d.ellipse((290, 300, 610, 620), outline=MUREKKEP, width=8, fill=(255, 253, 246))
    d.line([(450, 460), (450, 340)], fill=MUREKKEP, width=8); d.line([(450, 460), (550, 500)], fill=KIRMIZI, width=8)
    metin(d, (450, 720), "36. saat", F("serif", 80), KIRMIZI)
    metin(d, (450, 800), "ilk kriz", F("sans_m", 34), GRI)
    mahkum(d, 1000, 840, 1.15, "8612")
    baloncuk(im, 1080, 300, "“Çıkarın beni!”", F("serif_bi", 56), renk=KIRMIZI)
    d = ImageDraw.Draw(im)
    if k >= 1:
        for i, x in enumerate([1350, 1500]):
            mahkum(d, x, 820, 0.75)
        metin(d, (1430, 870), "birer birer…", F("serif_i", 40), GRI)
    if k >= 2:
        d = kart(im, (1260, 420, 1820, 620), fill=(255, 247, 228), kenar=ALTIN, kw=6)
        metin(d, (1540, 480), "Zimbardo artık:", F("serif_i", 40), GRI)
        metin(d, (1540, 560), "HAPİSHANE MÜDÜRÜ", F("sans_b", 44), MUREKKEP)
    return im

def s5(k):
    im = kagit(); d = ImageDraw.Draw(im)
    if k == 0:
        baslik(d, "Planlanan: 14 gün", 130)
        for i in range(14):
            r, c = divmod(i, 7)
            x = 300 + c * 200; y = 330 + r * 230
            d = kart(im, (x, y, x + 160, y + 180), golge=False, fill=(252, 249, 243))
            metin(d, (x + 80, y + 90), str(i + 1), F("serif", 64), MUREKKEP if i < 6 else ACIK)
            if i == 5:
                d.line([(x + 10, y + 10), (x + 150, y + 170)], fill=KIRMIZI, width=10)
                d.line([(x + 150, y + 10), (x + 10, y + 170)], fill=KIRMIZI, width=10)
        metin(d, (CX, 860), "6. günde durduruldu", F("serif", 60), KIRMIZI)
        return im
    if k == 1:
        metin(d, (CX, 470), "Peki kim durdurdu?", F("serif", 130))
        return im
    insan(d, 520, 820, 1.3, govde_renk=(200, 225, 205))
    metin(d, (520, 885), "Christina Maslach", F("serif", 46))
    baloncuk(im, 700, 260, "“Bu çocuklara yaptığınız\nşey korkunç!”", F("serif_bi", 60), kuyruk="sol", renk=KIRMIZI)
    if k >= 3:
        d = ImageDraw.Draw(im)
        for i in range(10):
            insan(d, 1000 + i * 80, 820, 0.42, govde_renk=ACIK, c=GRI)
        metin(d, (1360, 875), "onlarca ziyaretçi… ilk itiraz eden: o", F("serif_i", 40), GRI)
    return im

def s6(k):
    im = kagit(); d = ImageDraw.Draw(im)
    baslik(d, "Zimbardo'nun sonucu", 130)
    d = kart(im, (200, 300, 640, 700)); insan(d, 420, 640, 0.9, govde_renk=(200, 225, 205)); metin(d, (420, 340), "iyi insan", F("serif_i", 40), YESIL)
    metin(d, (720, 500), "+", F("serif", 120))
    d = kart(im, (800, 300, 1240, 700), fill=(225, 215, 205)); parmaklik(d, 860, 380, 1180, 660, n=6); metin(d, (1020, 340), "kötü sistem", F("serif_i", 40), KIRMIZI)
    metin(d, (1320, 500), "=", F("serif", 120))
    metin(d, (1580, 500), "?" if k == 0 else "kötü\ndavranış", F("serif", 100 if k == 0 else 70), KIRMIZI)
    if k >= 1:
        d = kart(im, (460, 760, 1560, 880), fill=(255, 247, 228), kenar=ALTIN, kw=5)
        metin(d, (1010, 820), "Suç kişide değil, DURUMDA", F("serif", 58))
    if k >= 2:
        for i in range(3):
            d.rounded_rectangle((1640 + i * 22, 760 - i * 40, 1820 + i * 22, 800 - i * 40), 6, fill=[KIRMIZI, YESIL, ALTIN][i], outline=MUREKKEP, width=3)
    return im

def s7(k):
    im = kagit(); d = ImageDraw.Draw(im)
    if k == 0:
        metin(d, (CX, 420), "SÜRPRİZ!", F("sans_b", 200), KIRMIZI)
        metin(d, (CX, 600), "Hikâye o kadar basit değil…", F("serif_i", 70))
        return im
    baslik(d, "Yıllar sonra ortaya çıkanlar", 120)
    items = [(k >= 1, "Kayıtlar ve arşivler", ALTIN), (k >= 2, "Gardiyanlara “sert olun” denmişti", KIRMIZI),
             (k >= 3, "Krize giren mahkûm: “Kısmen rol yaptım”", KIRMIZI), (k >= 4, "2002 BBC deneyi: gardiyanlar zalimleşmedi", YESIL)]
    y = 300
    for g, t, c in items:
        if g:
            d = kart(im, (260, y - 55, 1760, y + 55), fill=(252, 249, 243), kenar=c, kw=5)
            d.ellipse((300, y - 18, 336, y + 18), fill=c)
            metin(d, (370, y), t, F("serif", 52), anchor="lm")
        y += 150
    return im

def s8(k):
    im = kagit(); d = ImageDraw.Draw(im)
    metin(d, (CX, 200), "Bu deney bir ders:", F("serif_i", 70), GRI)
    d = kart(im, (560, 300, 1460, 520)); metin(d, (1010, 410), "“ÜNLÜ DENEY”", F("serif", 90))
    d.ellipse((1300, 220, 1560, 480), outline=MUREKKEP, width=14)
    d.line([(1530, 450), (1680, 600)], fill=MUREKKEP, width=26)
    if k >= 1:
        metin(d, (CX, 720), "En ünlüsü bile sorgulanmalı!", F("serif", 80), KIRMIZI)
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
    ders_bas(d, 1, "Roller insanı değiştirebilir")
    gardiyan(d, 600, 860, 1.2)
    # ayna
    d.ellipse((1100, 300, 1500, 840), fill=(225, 232, 240), outline=MUREKKEP, width=10)
    insan(d, 1300, 780, 0.8, govde_renk=(200, 225, 205))
    if k >= 1:
        baloncuk(im, 640, 300, "“Bu ben miyim,\nyoksa rolüm mü?”", F("serif_bi", 52), kuyruk="sag")
    return im

def s11(k):
    im = kagit(); d = ImageDraw.Draw(im)
    ders_bas(d, 2, "Sistemin beklentisine dikkat et")
    d = kart(im, (300, 290, 900, 900), fill=(255, 253, 246))
    metin(d, (600, 360), "SENARYO", F("sans_b", 56), KIRMIZI)
    for i, w in enumerate([420, 360, 460, 300, 400, 340]):
        d.line([(370, 450 + i * 70), (370 + w, 450 + i * 70)], fill=MUREKKEP, width=5)
    if k >= 1:
        for i, x in enumerate([1150, 1350, 1550]):
            insan(d, x, 880, 0.9, govde_renk=ACIK)
            d.line([(x, 880 - 250 * 0.9 - 40), (x, 300)], fill=GRI, width=2)
        d.line([(1100, 300), (1600, 300)], fill=MUREKKEP, width=8)
        metin(d, (1350, 250), "verilen role göre…", F("serif_i", 46), GRI)
    return im

def s12(k):
    im = kagit(); d = ImageDraw.Draw(im)
    ders_bas(d, 3, "İtiraz eden ilk kişi ol")
    for i, (t, x) in enumerate([("Milgram", 420), ("Asch", 1010), ("Stanford", 1600)]):
        d = kart(im, (x - 230, 320, x + 230, 820))
        metin(d, (x, 380), t, F("serif", 52))
        for j in range(3):
            yes = j == 1
            insan(d, x - 130 + j * 130, 760, 0.6, kollar="dur" if yes else "asagi", govde_renk=YESIL if yes else ACIK, c=MUREKKEP if yes else GRI)
    if k >= 1:
        metin(d, (CX, 885), "Tek bir cesur ses her şeyi değiştirebilir", F("serif", 56), YESIL)
    return im

def s13(k):
    im = kagit(); d = ImageDraw.Draw(im)
    metin(d, (CX, 230), "“", F("serif", 260), ALTIN)
    metin(d, (CX, 430), "Hikâye ne kadar güçlü olursa olsun…", F("serif_i", 76))
    metin(d, (CX, 560), "kanıtı her zaman sorgula.", F("serif_bi", 96), KIRMIZI)
    cizgi_alt(d, CX, 680, 600)
    metin(d, (CX, 750), "Stanford Hapishane Deneyi · 1971", F("sans_m", 36), GRI)
    return im

def s14(k):
    im = kagit(); d = ImageDraw.Draw(im)
    metin(d, (CX, 140), "SIRADAKİ BÖLÜM", F("sans_b", 44), KIRMIZI)
    metin(d, (CX, 240), "Seyirci Etkisi" if k >= 1 else "Kimse kıpırdamıyor…", F("serif", 100 if k >= 1 else 80))
    # yerde yatan kişi + çevresinde kalabalık
    d.line([(860, 860), (1160, 860)], fill=MUREKKEP, width=8)
    d.ellipse((1160, 820, 1230, 890), outline=MUREKKEP, width=6, fill=KAGIT)
    baloncuk(im, 900, 640, "yardım!", F("serif_i", 44), renk=KIRMIZI)
    d = ImageDraw.Draw(im)
    for i, x in enumerate([300, 450, 600, 1450, 1600, 1750]):
        insan(d, x, 900, 0.85, govde_renk=ACIK, c=GRI)
    return im

SAHNELER = [s0, s1, s2, s3, s4, s5, s6, s7, s8, s9, s10, s11, s12, s13, s14]
