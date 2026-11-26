# Uzun yatay video (BirAdım · "Psikolojinin En Ünlü Deneyleri")

- `senaryo_v2.txt`: heyecanlı anlatım + ElevenLabs v4 duygu etiketleri ([excited], [whispers]...).
- Seslendirme: ElevenLabs `eleven_v4`, ses "Eray | Cinematic Turkish Voice".
- Kelime zamanları: ElevenLabs Scribe ile çıkarılır (`kelimeler_v2.json`).
- `sahneler.py`: her paragraf için el çizimi tarzında sahne durumları (krem kâğıt, kırmızı/altın vurgular).
- `kur.py <bölüm klasörü>`: sahne kliplerini (yumuşak geçiş + hafif yakınlaşma), kelime kelime vurgulu ASS altyazıyı ve rozet katmanını üretir.
- Son birleştirme: `ffmpeg -f concat` ile `gorsel.mp4`, ardından altyazı + rozet + ses + kapanış sesi (loudnorm -14 LUFS).
