# Valuora-nı internetə açmaq — 10 dəqiqəlik quraşdırma

Bu paket public deployment üçün hazırlanıb. Başqa ölkədəki istənilən şəxs brauzerdən Render-in verdiyi `https://...onrender.com` linkini açaraq Valuora-ya daxil ola bilər.

## 1. GitHub-a yüklə

1. GitHub-da yeni repository yarat: `valuora-public`
2. Bu ZIP-i çıxart.
3. ZIP-in içindəki faylları repository-nin əsas qovluğuna yüklə.
4. `render.yaml` faylı repository root-da qalmalıdır.

## 2. Render-də deploy et

1. Render hesabına daxil ol.
2. **New → Blueprint** seç.
3. GitHub repository-ni qoş.
4. `render.yaml` seçildikdən sonra **Deploy Blueprint** et.
5. Build bitdikdən sonra Render sənə `https://valuora-public-....onrender.com` tipli public URL verəcək.

## 3. Linki paylaş

Məsələn:

`https://valuora-public-xxxx.onrender.com`

Bu linki WhatsApp, Telegram, Instagram, e-mail və s. ilə istənilən ölkədəki istifadəçiyə göndərə bilərsən.

## Niyə bu versiyada disk var?

Valuora loginlər, məhsullar, analizlər, alertlər və digər məlumatları SQLite-də saxlayır. Render-in free web service fayl sistemi qalıcı deyil; restart/deploy zamanı lokal SQLite məlumatları itə bilər. Bu deployment buna görə paid web service + persistent disk istifadə edir.

## Vacib təhlükəsizlik

- `VALUORA_SECRET` Render tərəfindən avtomatik yaradılır.
- HTTPS Render tərəfindən idarə olunur.
- `COOKIE_SECURE=1` aktivdir.
- Admin hesabı üçün `admin@...` qeydiyyat qaydası demo səviyyəsindədir; real production üçün ayrıca admin provisioning istifadə etmək lazımdır.

## Free test istəyirsənsə

Render-də Web Service-i `free` planına dəyişə bilərsən. Sayt public olacaq, amma free xidmət 15 dəqiqə aktivlik olmadıqda sleep edir və lokal SQLite məlumatları qalıcı saxlanmır.
