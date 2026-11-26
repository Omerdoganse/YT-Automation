import json, re, sys, os, subprocess
sys.path.insert(0, os.path.dirname(__file__))
from sahneler import *
D = sys.argv[1]; os.chdir(D)
TETIK = [[None,"Hemen","Ama"],[None,"Psikolog","Gelenler"],[None,"Yan","Öğretmenin","On","Son"],[None],
 [None,"Öğrenci","Deneyin"],[None,"sonra","Ve"],[None,"Durmak"],[None,"Tahmin:","Kırk"],[None,"Bu","Kendilerini"],
 [None,"Araştırmacı","Öğretmen,","Ama"],[None,"Arşivleri","Gönüllülerin","Ama"],[None,"Üç"],[None,"Kimse","Her","Hayatta"],
 [None,'"Bana'],[None,"Deneyde","Ve"],[None],[None,"Odadaki"]]
sys.path.insert(0, os.getcwd())
if os.path.exists('sahne_mod.py'):
    import sahne_mod
    SAHNELER, TETIK = sahne_mod.SAHNELER, sahne_mod.TETIK
raw = open('senaryo_v2.txt', encoding='utf-8').read().strip()
paras = [re.sub(r'\[[^\]]*\] ?', '', p).split() for p in raw.split('\n\n')]
w = [x for x in json.load(open('kelimeler_v2.json')) if not x['text'].startswith('[')]
assert len(w) == sum(map(len, paras)), (len(w), sum(map(len, paras)))
ses = float(subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0','ses_v2.mp3'],capture_output=True,text=True).stdout)
# paragraf başlangıçları & tetik zamanları
idx = 0; sahne = []
for pi, p in enumerate(paras):
    ts = []
    j0 = 0
    for tw in TETIK[pi]:
        if tw is None: ts.append(None); continue
        j = next(j for j in range(j0, len(p)) if p[j] == tw)
        ts.append(w[idx + j]['start'] - 0.15); j0 = j + 1
    sahne.append({'bas': w[idx]['start'], 'ts': ts, 'w0': idx, 'w1': idx + len(p)})
    idx += len(p)
for i, s in enumerate(sahne):
    s['a'] = 0.0 if i == 0 else sahne[i]['bas'] - 0.25
for i, s in enumerate(sahne):
    s['b'] = sahne[i + 1]['a'] if i + 1 < len(sahne) else ses + 0.6
os.makedirs('sahne', exist_ok=True)
PAPER = '0xF5EFE4'
dosyalar = []
for i, s in enumerate(sahne):
    dur = round(s['b'] - s['a'], 3)
    n = len(s['ts'])
    ins = []; fc = []
    for k in range(n):
        pth = f'sahne/s{i:02d}_{k}.png'; SAHNELER[i](k).save(pth); ins += ['-framerate','30','-i',pth]
    fc.append(f'[0:v]loop=-1:1,trim=duration={dur},setpts=PTS-STARTPTS,format=rgba[c0]')
    for k in range(1, n):
        st = max(0.05, s['ts'][k] - s['a'])
        fc.append(f'[{k}:v]loop=-1:1,trim=duration={dur},setpts=PTS-STARTPTS,format=rgba,fade=t=in:st={st:.3f}:d=0.35:alpha=1[l{k}]')
        fc.append(f'[c{k-1}][l{k}]overlay=format=auto[c{k}]')
    z0, z1 = (0.9524, 0.9524*1.035) if i % 2 == 0 else (0.9524*1.035, 0.9524)
    zx = f'({z0}+({z1}-{z0})*t/{dur})'
    fc.append(f"[c{n-1}]scale=w='2*trunc(2016*{zx}/2)':h='2*trunc(1134*{zx}/2)':eval=frame:flags=bicubic,crop=1920:1080,"
              f"fade=t=in:st=0:d={0.3 if i else 0.01}:color={PAPER},format=yuv420p[v]")
    out = f'sahne/v{i:02d}.mp4'
    if not os.path.exists(out):
        cmd = ['ffmpeg','-y','-v','error'] + ins + ['-filter_complex',';'.join(fc),'-map','[v]','-r','30','-t',str(dur),
               '-c:v','libx264','-preset','veryfast','-crf','17','-pix_fmt','yuv420p','sahne/tmp.mp4']
        subprocess.run(cmd, check=True); os.rename('sahne/tmp.mp4', out)
    dosyalar.append(out); print(i, dur, flush=True)
# kapanış
out = 'sahne/v99.mp4'
if not os.path.exists(out):
    subprocess.run(['ffmpeg','-y','-v','error','-framerate','30','-i','kapanis_yatay.png','-vf',
        f'format=yuv420p,loop=-1:1,trim=duration=5.2,fade=t=in:st=0:d=0.4:color={PAPER}','-r','30',
        '-c:v','libx264','-preset','veryfast','-crf','17','-pix_fmt','yuv420p','sahne/tmp.mp4'],check=True)
    os.rename('sahne/tmp.mp4', out)
dosyalar.append(out)
open('sahne/liste.txt','w').write(''.join(f"file '{os.path.basename(f)}'\n" for f in dosyalar))
json.dump({'sahne': sahne, 'ses': ses}, open('sahne/plan.json','w'), ensure_ascii=False, indent=1)
# ---- ASS altyazı: kelime kelime vurgulu ----
def ts(t):
    t = max(0, t); h = int(t // 3600); m = int(t % 3600 // 60); s = t % 60
    return f'{h}:{m:02d}:{s:05.2f}'
sw = [x for p in paras for x in p]
chunks = []; cur = []
for k, word in enumerate(sw):
    cur.append(k)
    txtlen = len(' '.join(sw[j] for j in cur))
    son = word[-1] in '.!?:' or word.endswith('...') or word.endswith('…') or word.endswith('."') or word.endswith('!"') or word.endswith('?"')
    yeni_par = any(k + 1 == sahne[i]['w1'] for i in range(len(sahne)))
    if yeni_par or son or txtlen > 34 or (word.endswith(',') and txtlen > 20):
        chunks.append(cur); cur = []
if cur: chunks.append(cur)
hdr = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: A,Inter SemiBold,60,&H00202428,&H00202428,&H18F3F9FC,&H50000000,0,0,0,0,100,100,0,0,3,22,0,2,80,80,58,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
ev = []
KIR = r'{\c&H2D37C8&}'; NORM = r'{\c&H202428&}'
for c in chunks:
    for n, k in enumerate(c):
        a = w[k]['start'] if n else w[k]['start'] - 0.08
        if n + 1 < len(c): b = w[c[n + 1]]['start']
        else:
            ci = chunks.index(c)
            b = w[k]['end'] + 0.25
            if ci + 1 < len(chunks): b = min(b, w[chunks[ci + 1][0]]['start'] - 0.09)
        parts = []
        for j in c:
            t = sw[j].replace('{', '(').replace('}', ')')
            parts.append(KIR + t + NORM if j == k else t)
        ev.append(f"Dialogue: 0,{ts(a)},{ts(b)},A,,0,0,0,,{' '.join(parts)}")
open('altyazi.ass','w',encoding='utf-8').write(hdr + '\n'.join(ev) + '\n')
ust_bilgi(None, Image.open('rozet.png').convert('RGBA')).save('ust.png')
print('ok', len(chunks))
