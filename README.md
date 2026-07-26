# Homeopati Kişisel Web Sitesi

Miranda Castro tarzında, klasik homeopati pratiği için tasarlanmış kişisel web sitesi.

## Özellikler

- **Tek Sayfa Uygulama (SPA)** — JavaScript ile sayfalar arası geçiş, yeniden yükleme yok
- **Responsive Tasarım** — Mobil, tablet ve masaüstü uyumlu
- **Hafif ve Hızlı** — Saf HTML/CSS/JS, bağımlılık yok
- **SEO Dostu** — Semantic HTML, meta etiketler, temiz URL'ler
- **Güvenlik** — Nginx güvenlik header'ları, XSS koruması
- **Performans** — Gzip sıkıştırma, statik asset cache, optimize edilmiş görseller

## Proje Yapısı

```
.
├── docker-compose.yml      # Docker Compose konfigürasyonu
├── nginx/
│   ├── Dockerfile          # Nginx image yapılandırması
│   └── nginx.conf          # Nginx sunucu ayarları
└── src/
    ├── index.html          # Ana HTML dosyası
    ├── css/
    │   └── style.css       # Tüm stiller
    ├── js/
    │   └── main.js         # Navigasyon ve form işlemleri
    └── assets/             # Görseller ve diğer dosyalar
```

## Kurulum

### Gereksinimler
- Docker
- Docker Compose

### Çalıştırma

```bash
# Projeyi klonlayın
cd homeopathy-website

# Container'ları başlatın
docker-compose up -d

# Tarayıcıda açın
open http://localhost
```

### Durum Kontrolü

```bash
# Container logları
docker-compose logs -f nginx

# Container durumu
docker-compose ps

# Container'ları durdurun
docker-compose down
```

## HTTPS (Production)

`docker-compose.yml` içindeki certbot servisini yorum satırından kaldırın ve domain adınızı ayarlayın:

```yaml
certbot:
  image: certbot/certbot
  volumes:
    - ./certbot/conf:/etc/letsencrypt
    - ./certbot/www:/var/www/certbot
```

## Özelleştirme

- **İçerik:** `src/index.html` dosyasındaki metinleri düzenleyin
- **Renkler:** `src/css/style.css` dosyasındaki `:root` değişkenlerini değiştirin
- **İletişim Formu:** Şu an frontend-only. Backend entegrasyonu için `src/js/main.js` içindeki `handleSubmit` fonksiyonunu güncelleyin.

## Teknolojiler

| Katman | Teknoloji |
|--------|-----------|
| Web Sunucu | Nginx (Alpine) |
| Frontend | HTML5, CSS3, Vanilla JS |
| Container | Docker + Docker Compose |
| SSL | Let's Encrypt (Certbot) |

## Lisans

MIT
