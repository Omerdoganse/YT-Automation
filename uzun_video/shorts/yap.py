import json, math, subprocess, sys, os
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

OUT = '/mnt/user-data/outputs'
W, H = 1080, 1920
KAGIT = (245, 239, 228); MUREKKEP = (43, 36, 32); KIRMIZI = (200, 55, 45)
ALTIN = (214, 158, 52); YESIL = (96, 145, 112); GRI = (138, 123, 107)
FD = "/usr/share/fonts/truetype/crosextra/"; FI = "/usr/share/fonts/opentype/inter/"
def F(n, s):
    return ImageFont.truetype({"serif": FD + "Caladea-Bold.ttf", "serif_i": FD + "Caladea-Italic.ttf",
                               "sans_b": FI + "Inter-ExtraBold.otf", "black": FI + "Inter-Black.otf",
                               "sans_m": FI + "Inter-Medium.otf"}[n], s)

def yildiz(d, x, y, s, c):
    pts = []
    for i in range(8):
        r = s if i % 2 == 0 else s * 0.28
        a = math.pi / 2 + i * math.pi / 4
        pts.append((x + r * math.cos(a), y - r * math.sin(a)))
    d.polygon(pts, fill=c)

def kagit():
    a = np.full((H, W, 3), KAGIT, np.float32)
    a += np.random.default_rng(3).normal(0, 3.2, (H, W, 1))
    yy, xx = np.mgrid[0:H, 0:W]
    r = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
    a *= (1 - 0.10 * np.clip(r - 0.55, 0, 1)[..., None])
    im = Image.fromarray(np.clip(a, 0, 255).astype('uint8'))
    d = ImageDraw.Draw(im)
    for x, y, s, c in [(90, 420, 20, ALTIN), (1000, 360, 16, YESIL), (70, 1330, 16, YESIL), (1020, 1300, 20, ALTIN)]:
        yildiz(d, x, y, s, c)
    return im

FX, FY, FW, FH = 40, 700, 1000, 562   # video çerçevesi

def arka(baslik, bolum):
    im = kagit(); d = ImageDraw.Draw(im)
    r = Image.open(OUT + '/rozet_biradim.png').convert('RGBA'); r.thumbnail((230, 84))
    im.paste(r, ((W - r.width) // 2, 150), r)
    d.text((W // 2, 300), "PSİKOLOJİNİN EN ÜNLÜ DENEYLERİ", font=F("sans_b", 34), fill=KIRMIZI, anchor="mm")
    d.text((W // 2, 348), bolum, font=F("serif_i", 40), fill=GRI, anchor="mm")
    y = 462
    for i, satir in enumerate(baslik):
        d.text((W // 2, y), satir, font=F("black", 96), fill=(255, 255, 255) if i == 0 else KIRMIZI,
               anchor="mm", stroke_width=7, stroke_fill=MUREKKEP)
        y += 112
    # çerçeve gölgesi + kenar
    sh = Image.new('L', (W, H), 0)
    ImageDraw.Draw(sh).rounded_rectangle((FX + 8, FY + 16, FX + FW + 8, FY + FH + 16), 30, fill=90)
    im.paste((110, 92, 74), mask=sh.filter(ImageFilter.GaussianBlur(16)))
    ImageDraw.Draw(im).rounded_rectangle((FX - 6, FY - 6, FX + FW + 6, FY + FH + 6), 34, fill=MUREKKEP)
    return im

def maske():
    m = Image.new('L', (FW, FH), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, FW - 1, FH - 1), 28, fill=255)
    return m

def cta_png(path):
    im = Image.new('RGBA', (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    y = FY + FH + 70
    d.rounded_rectangle((140, y, 940, y + 130), 65, fill=KIRMIZI, outline=MUREKKEP, width=6)
    d.polygon([(205, y + 40), (205, y + 90), (250, y + 65)], fill=(255, 255, 255))
    d.text((585, y + 65), "TAM BÖLÜMÜ İZLE", font=F("black", 54), fill=(255, 255, 255), anchor="mm")
    # aşağı ok
    ax, ay = W // 2, y + 175
    d.polygon([(ax - 50, ay), (ax + 50, ay), (ax, ay + 60)], fill=MUREKKEP)
    im.save(path)

def ts(t):
    t = max(0, t); return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"

def ass(kelimeler, path, cta_bas):
    chunks, cur = [], []
    for k, w in enumerate(kelimeler):
        cur.append(k)
        L = len(' '.join(kelimeler[j]['t'] for j in cur))
        son = w['t'][-1] in '.!?:' or w['t'].endswith(('...', '…', '."', '!"', '?"'))
        if son or L > 22 or w.get('kes') or (w['t'].endswith(',') and L > 12):
            chunks.append(cur); cur = []
    if cur: chunks.append(cur)
    hdr = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: A,Inter Black,84,&H00FFFFFF,&H00FFFFFF,&H00202428,&H64000000,0,0,0,0,100,100,0,0,1,7,4,8,110,110,{FY + FH + 70},1
Style: B,Inter Black,70,&H00FFFFFF,&H00FFFFFF,&H00202428,&H64000000,0,0,0,0,100,100,0,0,1,7,4,8,110,110,{FY + FH + 330},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    for ci, c in enumerate(chunks):
        stil = 'B' if kelimeler[c[0]]['s'] >= cta_bas - 0.05 else 'A'
        for n, k in enumerate(c):
            a = kelimeler[k]['s'] - (0.06 if n == 0 else 0)
            if n + 1 < len(c): b = kelimeler[c[n + 1]]['s']
            else:
                b = kelimeler[k]['e'] + 0.3
                if ci + 1 < len(chunks): b = min(b, kelimeler[chunks[ci + 1][0]]['s'] - 0.07)
            parts = [(r'{\c&H3BC4FF&}' + tr_upper(kelimeler[j]['t']) + r'{\c&HFFFFFF&}') if j == k
                     else tr_upper(kelimeler[j]['t']) for j in c]
            ev.append(f"Dialogue: 0,{ts(a)},{ts(b)},{stil},,0,0,0,,{' '.join(parts)}")
    open(path, 'w', encoding='utf-8').write(hdr + '\n'.join(ev) + '\n')

def tr_upper(s):
    return s.replace('i', 'İ').replace('ı', 'I').upper()

def yap(ad, uzun, kapak, parcalar, cta_mp3, cta_metin, cta_cumle, baslik, bolum):
    os.makedirs(ad, exist_ok=True)
    P = json.load(open(f'{ad}.json'))
    arka(baslik, bolum).save(f'{ad}/arka.png')
    maske().save(f'{ad}/maske.png')
    cta_png(f'{ad}/cta.png')
    kel = []; t0 = 0.0; klipler = []
    for i, pi in enumerate(parcalar):
        p = P[pi]
        a, b = p['a'] - 0.12, p['b'] + 0.22
        dur = b - a
        for w in p['words']:
            kel.append({'t': w['t'], 's': w['s'] - a + t0, 'e': w['e'] - a + t0})
        kel[-1]['kes'] = True
        out = f'{ad}/k{i}.mp4'
        subprocess.run(['ffmpeg', '-y', '-v', 'error', '-ss', f'{a:.3f}', '-i', uzun, '-t', f'{dur:.3f}',
            '-vf', f'crop=1920:930:0:0,scale={FW}:-2,pad={FW}:{FH}:0:(oh-ih)/2:color=0xF5EFE4,fps=30,'
                   f'fade=t=in:st=0:d=0.2:color=0xF5EFE4,fade=t=out:st={dur - 0.2:.3f}:d=0.2:color=0xF5EFE4,format=yuv420p',
            '-af', f'afade=t=in:d=0.05,afade=t=out:st={dur - 0.08:.3f}:d=0.08', '-ar', '48000', '-ac', '2',
            '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '16', '-c:a', 'aac', '-b:a', '192k', out], check=True)
        klipler.append(out); t0 += dur
    cta_bas = t0
    cdur = float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', cta_mp3],
                                capture_output=True, text=True).stdout) + 0.9
    # CTA kelimeleri: cümle aralıklarına karakter oranıyla dağıt
    for (sa, sb), cumle in zip(cta_cumle, cta_metin):
        ws = cumle.split(); tot = sum(len(x) + 1 for x in ws); t = sa
        for x in ws:
            dd = (sb - sa) * (len(x) + 1) / tot
            kel.append({'t': x, 's': cta_bas + t, 'e': cta_bas + t + dd}); t += dd
        kel[-1]['kes'] = True
    out = f'{ad}/k_cta.mp4'
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-loop', '1', '-framerate', '30', '-i', kapak, '-i', cta_mp3,
        '-filter_complex', f'[0:v]scale={FW}:{FH},trim=duration={cdur:.3f},fade=t=in:st=0:d=0.25:color=0xF5EFE4,format=yuv420p[v];'
                           f'[1:a]aresample=48000,aformat=channel_layouts=stereo,loudnorm=I=-14:TP=-1.5,aresample=48000,apad=whole_dur={cdur:.3f}[a]',
        '-map', '[v]', '-map', '[a]', '-t', f'{cdur:.3f}', '-r', '30', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '16',
        '-c:a', 'aac', '-b:a', '192k', out], check=True)
    klipler.append(out)
    open(f'{ad}/liste.txt', 'w').write(''.join(f"file '{os.path.basename(k)}'\n" for k in klipler))
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-f', 'concat', '-safe', '0', '-i', f'{ad}/liste.txt', '-c', 'copy', f'{ad}/orta.mp4'], check=True)
    ass(kel, f'{ad}/alt.ass', cta_bas)
    toplam = t0 + cdur
    son = f'{OUT}/BirAdim_Shorts_{ad}.mp4'
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-loop', '1', '-framerate', '30', '-i', f'{ad}/arka.png', '-i', f'{ad}/orta.mp4',
        '-loop', '1', '-i', f'{ad}/maske.png', '-loop', '1', '-i', f'{ad}/cta.png',
        '-filter_complex',
        f'[1:v]format=rgba[o];[2:v]format=gray,scale={FW}:{FH}[m];[o][m]alphamerge[om];'
        f'[0:v][om]overlay={FX}:{FY}:shortest=1[b];'
        f'[3:v]format=rgba,fade=t=in:st={cta_bas + 0.2:.3f}:d=0.3:alpha=1[c];[b][c]overlay=0:0:enable=\'gte(t,{cta_bas:.3f})\'[b2];'
        f'[b2]subtitles={ad}/alt.ass,format=yuv420p[v];[1:a]loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[a]',
        '-map', '[v]', '-map', '[a]', '-t', f'{toplam:.3f}', '-r', '30', '-c:v', 'libx264', '-preset', 'veryfast',
        '-crf', '18', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', f'{ad}/tmp.mp4'], check=True)
    import shutil; shutil.copy(f'{ad}/tmp.mp4', son)
    print(ad, round(toplam, 2), 'cta', round(cta_bas, 2))

if __name__ == '__main__':
    hangi = sys.argv[1]
    if hangi == 'milgram':
        yap('milgram', OUT + '/BirAdim_B01_Milgram.mp4', OUT + '/BirAdim_B01_Milgram_kapak.jpg', [0, 7],
            'cta_milgram.mp3',
            ["Peki bu insanlar kötü müydü?", "Cevabı ve hayatına üç dersi tam bölümde anlattım.", "Hemen aşağıdaki videoya dokun!"],
            [(0.0, 2.05), (2.44, 5.57), (5.97, 7.34)],
            ["KAÇ VOLTA", "KADAR GİDERDİN?"], "Bölüm 1 · Milgram İtaat Deneyi")
    else:
        yap('asch', OUT + '/BirAdim_B02_Asch.mp4', OUT + '/BirAdim_B02_Asch_kapak.jpg', [0, 3, 4],
            'cta_asch.mp3',
            ["Peki tek bir kişi bütün bunları nasıl değiştirdi?", "Cevabı tam bölümde!", "Hemen aşağıdaki videoya dokun!"],
            [(0.0, 2.88), (3.26, 4.62), (4.99, 6.36)],
            ["HERKES YANLIŞ", "SÖYLERSE?"], "Bölüm 2 · Asch Uyum Deneyi")
