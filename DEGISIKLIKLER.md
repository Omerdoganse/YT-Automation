# Değişiklikler

## 2026-11-15
**Yeni**
- Tuşların yanında **( ! )** bilgi simgeleri ve tuşların üstüne gelince açılan açıklama balonları
- Üst çubukta **? Kılavuz**: program içi kullanım kılavuzu (`KULLANIM_KILAVUZU.md`)
- Konu üretirken kanaldaki **bütün videolarla** tekrar kontrolü (aynı teknik/fikir ikinci kez seçilmez)
- İş kuyruğunda zamanlanmış yayın: `{"is": "yukle", "yayin": "2026-11-15T12:00:00+03:00"}`
- `baslat.bat`: programı konsol penceresi olmadan açar

**Düzeltmeler**
- Elle zamanlanan videolar artık yayın planında o saati dolu gösterir (aynı saate ikinci video yüklenmez)
- Aynı kanal için ikinci pencere açılamaz; iş kuyruğu kilitlidir (çift yükleme/çift işleme önlenir)
- Sıradaki işler arka planda sessizce yapılır; iş bitince açık kalan pencere sorunu giderildi
- Reddedilen videolar listelerde "Yüklenmeyi bekliyor" yerine "Yayınlanmayacak" görünür
- Yeni yüklenen videoda ilk yorum "video bulunamadı" hatası alırsa sonradan yeniden denenir
- Windows konsolunda emoji/Türkçe karakter yazarken oluşan kodlama hatası giderildi
- Sayfa geçiş animasyonu takılma yapıyordu; yeniden yerleşim gerektirmeyen yumuşak geçişe çevrildi

**Arayüz**
- Konu ve onay satırlarında sıra numarası / YENİ rozetleri
- YouTube Studio'nun güncel görünümü: siyah zemin, ince çerçeveli yuvarlak kartlar

## 2026-11-13
- İlk sürüm: hikâye kanalları, NotebookLM kanalı, yayın planı, analiz, yorumlar
