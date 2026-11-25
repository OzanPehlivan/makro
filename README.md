# Makro Studio

Windows için hızlı, hafif ve bağımlılıksız makro programı. Klavye yazılımlarındaki makro ekranları gibi bir arayüzü var: klavyede bir tuşa tıklıyorsun, ona istediğin işi atıyorsun.

## Neler yapabilir

Her tuşa (ve Ctrl / Shift / Alt / Win kombinasyonlarına) ayrı bir iş atanabilir:

| Aksiyon | Ne yapar |
|---|---|
| **Tıklama** | Sol, sağ, orta veya yan fare tuşuna saniyede 1–1000 kez tıklar |
| **Tuş tekrarı** | Bir tuşa veya kısayola saniyede 1–1000 kez basar |
| **Metin yaz** | Kelime, cümle, paragraf yazar. Türkçe karakter ve emoji olur. İstersen sonunda Enter'a basar |
| **Makro dizisi** | Tuş, tıklama, metin, bekleme ve kaydırma adımlarından oluşan sıra. **Kayıt** düğmesiyle yaptıklarını beklemeleriyle birlikte kaydedebilirsin |
| **Tuş ata** | Tuşu başka bir tuşa, kısayola (ör. Ctrl + C) veya fare tuşuna çevirir |
| **Program aç** | Program, dosya, klasör veya web sitesi açar |
| **Devre dışı** | Tuşu tamamen kapatır (ör. oyunda Windows tuşu) |

Çalışma şekilleri: **Basılı tut** (basılıyken çalışır), **Aç / kapat** (bir basışta başlar, tekrar basınca durur), **Bir kez** (her basışta bir kez).

Diğer özellikler:

- **Profiller:** Her oyun veya iş için ayrı profil. Profile uygulama eklersen (ör. `valorant.exe`) o uygulama öne gelince profil kendiliğinden açılır.
- **Hızlı aç/kapat kısayolu:** Varsayılanı `Pause`. Tüm makroları anında kapatır veya açar.
- **Fare tuşları:** Orta tuş ve yan tuşlar (4, 5) tetik olabilir.
- **Tepside çalışır:** Pencereyi kapatınca makrolar saat yanındaki ikonda çalışmaya devam eder.
- **Windows ile başlat** seçeneği.
- Profilleri dosyaya aktarma ve dosyadan alma.

## Kurulum

1. [Python 3.11 veya daha yenisini](https://www.python.org/downloads/) kur (kurarken "Add python.exe to PATH" kutusunu işaretle).
2. Bu depoyu indir veya klonla.
3. `MakroStudio.pyw` dosyasına çift tıkla (ya da `MakroStudio.bat`).

Başka hiçbir paket gerekmez: her şey Python'un kendi kütüphaneleri ve Windows API'si ile yazıldı. Arayüz, Microsoft Edge'in adres çubuksuz uygulama penceresinde açılır.

## Neden hızlı

- **Motor ayrı bir süreçte çalışır.** Arayüz ne yaparsa yapsın makro zamanlamasını etkileyemez.
- **Klavye hook'u olay tabanlıdır.** Tuşlar sürekli yoklanmaz; boştayken işlemci kullanımı neredeyse sıfırdır. Hook geri çağrısı iş yapmaz, sadece bayrak kurar, böylece sisteme gecikme eklemez.
- **Fare hook'u sadece gerektiğinde kurulur** (bir fare tuşuna atama varsa). Fare hareketleri ilk kontrolde geçirilir.
- **Her atama için önceden açılmış bir thread** vardır. Tuşa basınca yeni thread açılmaz.
- **Mutlak zaman çizelgesi:** Tıklama aralıkları birikip kaymaz. Geride kalınırsa tıklamalar tek `SendInput` çağrısında toplu gönderilir.
- **Hassas bekleme:** Hedefe kadar uyur, son milisaniyenin altını hassas bekler.
- **Windows'un güç kısıtlaması kapatılır:** Pencere arkadayken zamanlayıcı yavaşlamaz.
- **Tuşlar asla basılı kalmaz:** Makro durunca bastığı her tuşu ve fare tuşunu bırakır.

Ölçülen değerler (gerçek Windows hook'larıyla): tetiğe ilk tepki ~0,3 ms, 500 basış/sn'de hız tam 500,0, en uzun aralık ~3 ms.

## Uyarı

Birçok çevrim içi oyun makro ve otomatik tıklayıcı kullanımını yasaklar ve hesap kapatabilir. Kullanmadan önce oyunun kurallarına bak.

Oyun yönetici olarak çalışıyorsa Makro Studio'yu da yönetici olarak çalıştırman gerekebilir; yoksa Windows makronun gönderdiği girişleri o oyuna iletmez.

## Proje yapısı

```
MakroStudio.pyw    Giriş noktası (konsolsuz)
core/
  app.py           Ana süreç: arayüz sunucusu, tepsi ikonu, motor gözetmeni
  engine.py        Makro motoru (ayrı süreç): hook'lar, aksiyonlar
  config.py        Ayar doğrulama, yükleme, kaydetme
  keys.py          Tuş adları ve SendInput dizileri
  winapi.py        ctypes Windows API tanımları
  tray.py          Bildirim alanı ikonu
web/               Arayüz (HTML, CSS, JS)
tests/             Motor testleri
tools/make_icon.py İkon üretici
```

Ayarlar `%APPDATA%\MakroStudio\config.json` dosyasında, günlük `%LOCALAPPDATA%\MakroStudio\makro.log` dosyasında tutulur.

## Testler

```
python tests/test_engine.py
```

Testler gerçek tıklama veya tuş göndermez: gönderme fonksiyonu sahte bir kaydediciyle değiştirilir.

## Güvenlik

Arayüz sadece `127.0.0.1` üzerinde, her açılışta değişen rastgele bir anahtarla çalışır. Başka bir web sitesi bu arayüze istek gönderemez (anahtar, Host başlığı kontrolü ve içerik güvenlik politikası).
