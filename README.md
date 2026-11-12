# Shorts Stüdyo

YouTube Shorts kanallarını uçtan uca otomatikleştiren, YouTube Studio görünümünde bir masaüstü uygulaması (Python + Tkinter, Windows).

Tek programdan birden çok kanal yönetilir; her kanal ayrı bir **profil** olarak çalışır.

## Neler yapıyor?

**Hikâye kanalı (yapay zekâ ile baştan sona video)**
- Gemini ile konu bulur, kısa gizem/korku hikâyesi yazar, editör puanıyla en iyisini seçer
- Gemini TTS (ya da Edge TTS) ile seslendirir
- Whisper ile kelime kelime zamanlanmış alt yazı çıkarır
- Arka plan videosu, müzik ve kapanış kartıyla ffmpeg'de dikey video hazırlar
- Kapak resmi üretir, başlık/açıklama/etiket yazar
- Türkçe ve İngilizce kanal desteği

**NotebookLM kanalı (kişisel gelişim videoları)**
- Kanalın en çok izlenen videolarına bakarak yeni konular ve NotebookLM için kaynak metni + istem hazırlar
- NotebookLM'den indirilen videoyu işler:
  - Baştaki/sondaki NotebookLM logo ekranlarını otomatik keser (beyaz ve siyah kapanış)
  - Sağ alttaki filigranın üstüne kanal rozeti koyar
  - Videoyu hızlandırır (1.5x vb., önizlemeli hız seçici)
  - Kapanış kartı ve kapanış sesi ekler, dikey/yatay videoyu korur
- Videonun konuşmasını dinleyip doğru konuyu/başlığı bulur
- Yayından önce **onay listesi**: izle → onayla → plan yükler

**Yayın ve kanal yönetimi**
- YouTube Data API ile yükleme (kopan bağlantıda kaldığı yerden devam eder), zamanlanmış yayın planı
- Windows Görev Zamanlayıcı ile her gün otomatik çalışma
- Kanal analizi panelleri (YouTube Analytics)
- Yorumlara kanalın tonunda otomatik cevap, yeni videolara otomatik ilk yorum
- Arka planda iş kuyruğu (`isler.json`)

## Kurulum

1. **Python 3.10+** kur (Windows).
2. Paketler ilk açılışta otomatik kurulur; elle kurmak istersen:
   ```
   pip install -r requirements.txt
   ```
3. **Gemini API anahtarı:** `gizli.ornek.json` dosyasını `gizli.json` adıyla kopyala ve anahtarını yaz.
   Ya da `GEMINI_API_KEY` ortam değişkenini ayarla.
4. **YouTube bağlantısı:** Google Cloud Console'da bir proje aç, *YouTube Data API v3* ve *YouTube Analytics API*'yi etkinleştir,
   "Masaüstü uygulaması" türünde OAuth istemcisi oluştur ve indirdiğin dosyayı program klasörüne `client_secret.json` adıyla koy.
   İlk yüklemede tarayıcıda izin ekranı açılır; oluşan `token.json` da gizlidir.
5. Çalıştır:
   ```
   python main.py
   ```

Kanal adı, logo, rozet, kapanış kartı, müzik ve arka plan videoları gibi dosyalar depoda yok; kendi kanalının dosyalarını program klasörüne koymalısın.

## Güvenlik

Şu dosyalar `.gitignore` ile **depoya hiç gönderilmez**: `gizli.json`, `client_secret.json`, `token.json`, kanal profilleri, geçmiş ve yorum kayıtları, üretilen videolar.
Bu dosyaları kimseyle paylaşma.

## Not

Videolar yapay zekâ araçlarıyla hazırlanır; program açıklamalara bunu belirten bir not ekler.
YouTube'un spam ve yapay zekâ içerik kurallarına uyarak kullan.
