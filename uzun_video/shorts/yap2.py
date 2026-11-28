import sys, os, subprocess, shutil
from yap import *
from kel2 import M, A, oku

def gizem_karti(ad, path):
    """1920x1080 'sonuç gizli' kartı."""
    im = Image.new('RGB', (1920, 1080), KAGIT)
    a = np.array(im).astype(np.float32) + np.random.default_rng(5).normal(0, 3, (1080, 1920, 1))
    im = Image.fromarray(np.clip(a, 0, 255).astype('uint8')); d = ImageDraw.Draw(im)
    for x, y, s, c in [(160, 160, 24, ALTIN), (1760, 200, 20, YESIL), (150, 900, 20, YESIL), (1780, 880, 26, ALTIN)]:
        yildiz(d, x, y, s, c)
    if ad == 'milgram':
        d.text((960, 150), "KAÇ KİŞİ 450 VOLTA KADAR GİTTİ?", font=F("sans_b", 58), fill=MUREKKEP, anchor="mm")
        # tahmin kartı
        d.rounded_rectangle((200, 280, 820, 860), 30, fill=(252, 249, 243), outline=MUREKKEP, width=5)
        d.text((510, 350), "Psikiyatristlerin tahmini", font=F("serif_i", 44), fill=GRI, anchor="mm")
        d.text((510, 560), "%0,1", font=F("serif", 180), fill=MUREKKEP, anchor="mm")
        d.text((510, 730), "binde bir", font=F("serif", 60), fill=GRI, anchor="mm")
        x0, x1, bas = 960, 1720, "Gerçek sonuç"
    else:
        d.text((960, 150), "KAÇ KİŞİ YANLIŞA UYDU?", font=F("sans_b", 64), fill=MUREKKEP, anchor="mm")
        d.rounded_rectangle((200, 280, 820, 860), 30, fill=(252, 249, 243), outline=MUREKKEP, width=5)
        d.text((510, 350), "Tek başına", font=F("serif_i", 44), fill=GRI, anchor="mm")
        d.text((510, 560), "%1'den az", font=F("serif", 120), fill=YESIL, anchor="mm")
        d.text((510, 730), "hata yaptı", font=F("serif", 60), fill=GRI, anchor="mm")
        x0, x1, bas = 960, 1720, "Grupla birlikte"
    d.rounded_rectangle((x0, 280, x1, 860), 30, fill=(253, 238, 232), outline=KIRMIZI, width=8)
    d.text(((x0 + x1) // 2, 350), bas, font=F("serif_i", 44), fill=GRI, anchor="mm")
    d.text(((x0 + x1) // 2, 590), "%??", font=F("black", 230), fill=KIRMIZI, anchor="mm",
           stroke_width=8, stroke_fill=MUREKKEP)
    d.text(((x0 + x1) // 2, 780), "cevap tam bölümde", font=F("sans_b", 44), fill=MUREKKEP, anchor="mm")
    # kilit simgesi
    kx, ky = (x0 + x1) // 2 + 300, 330
    d.rounded_rectangle((kx - 40, ky, kx + 40, ky + 60), 10, fill=MUREKKEP)
    d.arc((kx - 28, ky - 40, kx + 28, ky + 20), 180, 360, fill=MUREKKEP, width=10)
    im.save(path)

def klip(ad, i, src, dur, uzun, maxlen=None):
    out = f'{ad}2/c{i:02d}.mp4'
    vf_ortak = f'scale={FW}:-2,pad={FW}:{FH}:0:(oh-ih)/2:color=0xF5EFE4'
    if src == 'kart':
        z = f'(1+0.10*t/{dur:.3f})'
        cmd = ['ffmpeg', '-y', '-v', 'error', '-loop', '1', '-framerate', '30', '-i', f'{ad}2/kart.png',
               '-vf', f"scale=w='2*trunc(1920*{z}/2)':h='2*trunc(1080*{z}/2)':eval=frame,crop=1920:1080,crop=1920:930:0:75,{vf_ortak},format=yuv420p",
               '-t', f'{dur:.3f}']
    else:
        L = min(dur, maxlen or dur)
        cmd = ['ffmpeg', '-y', '-v', 'error', '-ss', f'{src:.3f}', '-i', uzun, '-an',
               '-vf', f'crop=1920:930:0:0,{vf_ortak},fps=30,tpad=stop_mode=clone:stop_duration={max(0, dur - L) + 0.1:.3f},format=yuv420p',
               '-t', f'{dur:.3f}']
    subprocess.run(cmd + ['-r', '30', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '16', out], check=True)
    return out

def yap2(ad, uzun, kel, plan, cta_bas, mp3, baslik, bolum):
    os.makedirs(f'{ad}2', exist_ok=True)
    arka(baslik, bolum).save(f'{ad}2/arka.png'); maske().save(f'{ad}2/maske.png'); cta_png(f'{ad}2/cta.png')
    gizem_karti(ad, f'{ad}2/kart.png')
    sure = float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', mp3],
                                capture_output=True, text=True).stdout)
    toplam = sure + 0.8
    sinirlar = [p[0] for p in plan] + [toplam]
    klipler = []
    for i, (t0, src, mx) in enumerate(plan):
        klipler.append(klip(ad, i, src, sinirlar[i + 1] - t0, uzun, mx))
    open(f'{ad}2/liste.txt', 'w').write(''.join(f"file '{os.path.basename(k)}'\n" for k in klipler))
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-f', 'concat', '-safe', '0', '-i', f'{ad}2/liste.txt', '-c', 'copy', f'{ad}2/orta.mp4'], check=True)
    for w in kel:
        if w['t'][-1] in '.!?' or w['t'].endswith(('...', '".', '"!')): w['kes'] = True
    ass(kel, f'{ad}2/alt.ass', cta_bas)
    son = f'{OUT}/BirAdim_Shorts_{ad}.mp4'
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-loop', '1', '-framerate', '30', '-i', f'{ad}2/arka.png', '-i', f'{ad}2/orta.mp4',
        '-loop', '1', '-i', f'{ad}2/maske.png', '-loop', '1', '-i', f'{ad}2/cta.png', '-i', mp3,
        '-filter_complex',
        f'[1:v]format=rgba[o];[2:v]format=gray,scale={FW}:{FH}[m];[o][m]alphamerge[om];'
        f'[0:v][om]overlay={FX}:{FY}:shortest=1[b];'
        f'[3:v]format=rgba,fade=t=in:st={cta_bas:.3f}:d=0.3:alpha=1[c];[b][c]overlay=0:0:enable=\'gte(t,{cta_bas:.3f})\'[b2];'
        f'[b2]subtitles={ad}2/alt.ass,format=yuv420p[v];'
        f'[4:a]aresample=48000,aformat=channel_layouts=stereo,apad=whole_dur={toplam:.3f},loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[a]',
        '-map', '[v]', '-map', '[a]', '-t', f'{toplam:.3f}', '-r', '30', '-c:v', 'libx264', '-preset', 'veryfast',
        '-crf', '18', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', f'{ad}2/tmp.mp4'], check=True)
    shutil.copy(f'{ad}2/tmp.mp4', son)
    print(ad, round(toplam, 2))

if sys.argv[1] == 'milgram':
    plan = [(0.0, 57.0, 3.4), (2.1, 48.0, 4.2), (6.05, 61.0, 5.3), (10.3, 52.5, 3.7), (13.25, 80.0, 2.3),
            (15.6, 82.8, 2.8), (17.25, 108.0, 3.9), (18.9, 112.2, 2.8), (21.72, 'kart', None)]
    yap2('milgram', OUT + '/BirAdim_B01_Milgram.mp4', oku(M), plan, 24.78, 'v2_milgram.mp3',
         ["BU DÜĞMEYE", "BASAR MIYDIN?"], "Bölüm 1 · Milgram İtaat Deneyi")
else:
    plan = [(0.0, 2.0, 3.2), (3.15, 62.8, 1.9), (5.1, 6.2, 3.5), (8.5, 65.0, 5.9), (15.6, 71.1, 2.5),
            (19.95, 'kart', None)]
    yap2('asch', OUT + '/BirAdim_B02_Asch.mp4', oku(A), plan, 25.6, 'v2_asch.mp3',
         ["SEN NE", "DERDİN?"], "Bölüm 2 · Asch Uyum Deneyi")
