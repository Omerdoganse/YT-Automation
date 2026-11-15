# Shorts Stüdyo — Kullanım Kılavuzu

Bu kılavuz programın içinde de var: üst çubuktaki **? Kılavuz** tuşuna bas.

Tuşların yanındaki **( ! )** simgesinin üstüne gelirsen ya da tıklarsan o tuşun ne işe yaradığı yazar.

## 1. Program ne yapar?

- Shorts Stüdyo, YouTube kanallarının videolarını hazırlar, sıraya koyar ve belirlediğin saatlerde yayınlar.
- Her kanal ayrı bir profildir. Sol üstteki kanal adına tıklayarak kanal değiştirirsin.
- Tuşların yanındaki ( ! ) simgesinin üstüne gelirsen o tuşun ne işe yaradığı yazar.

## 2. BirAdım kanalı: NotebookLM ile video

- Panel > Konular: '＋ 5 konu üret' ile yeni konular hazırlat. Program kanaldaki bütün videolara bakar, aynı konuyu ikinci kez seçmez.
- Bir konunun '📋 Kaynak' tuşuna bas; NotebookLM'de yeni not defteri aç, 'Kopyalanan metin' seçip yapıştır.
- Aynı konunun '📝 İstem' tuşuna bas; NotebookLM'de Video Özeti'nin yanındaki oka tıkla, Kısa + Türkçe seç, istemi kutuya yapıştır ve oluştur.
- Video hazır olunca indir. Panel > 'Videoları seç' ile programa ver.
- Program NotebookLM logolarını keser, videoyu hızlandırır, köşeye rozet ve sona kapanış kartı ekler.
- Video 'Onay bekleyen videolar' listesine düşer. '▶ İzle' ile kontrol et, '✓ Onayla' ile yayın sırasına al.
> **Not:** Sen onaylamadan hiçbir video yayınlanmaz.

## 3. Hikâye kanalları: baştan sona otomatik

- Panel'de 'Oluştur'a basınca program konu bulur, hikâyeyi yazar, seslendirir, alt yazı ekler ve videoyu hazırlar.
- Arka plan videoları 'arkaplan_videolari', müzikler 'muzik' klasöründen alınır.
- Ses sayfasından seslendireni, anlatım tarzını ve hızı değiştirebilirsin.

## 4. Yayın planı

- Yayın planı sayfasında videoların hangi gün ve saatte yayınlanacağını belirlersin (ör. her gün 12:00).
- 'Planı şimdi doldur': boş saatler için onaylı videoları YouTube'a zamanlanmış olarak yükler. Video o saatte kendiliğinden yayınlanır; bilgisayarın kapalı olsa bile.
- 'Otomatik hazırlama' açıksa Windows bu işi her gün belirlediğin saatte kendisi yapar.
- Yaklaşan yayınlar listesinde hangi saatin dolu, hangisinin boş olduğunu görürsün.

## 5. İçerik, Analiz ve Yorumlar

- İçerik: tüm videoların ve canlı izlenme sayıları. Bir videoyu seçince ayrıntıları sağda görünür.
- Analiz: son 28 günün izlenmeleri, hangi videonun daha iyi tuttuğu ve en iyi yayın saati.
- Yorumlar: yeni yorumlara kanalın tonunda cevap yazılır. İstersen cevabı düzenleyip kendin gönderirsin.
- Her yeni videonun altına, sohbet başlatan bir ilk yorum otomatik atılır.

## 6. Sık karşılaşılan durumlar

- 'YouTube bağlı değil' yazıyorsa sol alttaki Bağlan'a bas ve kanalın bağlı olduğu Google hesabını seç.
- Video YouTube'a gitmediyse önce 'Onay bekleyen videolar' listesine bak: onaylanmamış video yüklenmez.
- Yanlış hazırlanan videoyu '↻' ile baştan hazırlat ya da '✕' ile listeden çıkar (dosya silinmez).
- Hata olursa pencerenin altındaki kayıt ekranında nedeni yazar; aynı kayıt kanal klasöründeki gecici/son_islem_log.txt dosyasında da durur.
> **Not:** Program YouTube'dan video silmez. Silmek istediğin videoyu YouTube Studio'dan kendin silersin.

## 7. Gizli dosyalar

- gizli.json (Gemini API anahtarı), client_secret.json ve token.json (YouTube girişi) kimseyle paylaşılmaz.
- Bu dosyalar GitHub'a gönderilmez; .gitignore bunu engeller.

## Ekran rehberi

| Sayfa | Ne için |
|---|---|
| Panel | Günlük iş: konular, video verme, onay listesi, son videolar |
| İçerik | Tüm videolar ve canlı istatistikler |
| Analiz | Son 28 gün, izlenme oranı, en iyi yayın saati |
| Yorumlar | Otomatik cevaplar ve elle cevap |
| Yayın planı | Yayın saatleri, planı doldurma, otomatik hazırlama |
| Ses | Seslendiren, anlatım tarzı, hız (hikâye kanalları) |
| Ayarlar | Kanal, görünüm, NotebookLM ayarları, YouTube hesabı, kapanış kartı |

## Tuşlar ne işe yarar?

| Tuş | Açıklama |
|---|---|
| ＋ 5 konu üret | Kanalda olmayan 5 yeni konu hazırlatır |
| 📋 Kaynak | Konunun kaynak metnini kopyalar (NotebookLM'e yapıştırılır) |
| 📝 İstem | NotebookLM Video Özeti talimatını kopyalar |
| 🎬 Videoları seç | İndirdiğin videoları programa verir; program işler ve onay listesine koyar |
| ▶ İzle | Hazırlanan videoyu oynatır |
| ↻ | Videoyu güncel ayarlarla baştan hazırlar |
| ✓ Onayla | Videoyu yayın sırasına alır |
| ✕ | Listeden çıkarır (dosya silinmez) |
| ⏩ Hız / önizle | Videonun hızını değiştirir ve önizleme gösterir |
| Planı şimdi doldur | Boş yayın saatlerine videoları zamanlanmış olarak yükler |
| Planlı videoları yenile | Seçilen planlı videoları gizliye alıp yenilerini hazırlar |
| ↻ Şimdi yenile | İstatistikleri YouTube'dan yeniden çeker |
