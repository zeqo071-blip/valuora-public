# Valuora AZ — Professional Edition

Valuora məhsul linkini analiz edib qiyməti bazar müşahidələri ilə müqayisə edən Azərbaycan dilli web tətbiqidir.

## Yeni versiyada
- Premium responsive UI və micro-animationlar
- Azərbaycan dili
- Login / qeydiyyat / sessiya cookie
- Şəxsi dashboard
- Analiz tarixçəsi
- Seçilmiş məhsullar
- Qiymət xəbərdarlıqları
- Bildiriş mərkəzi
- Profil səhifəsi
- Admin Control Center
- Qiymət qrafiki
- JSON-LD / OpenGraph / meta scraping
- Mövcud `valuora.db` ilə uyğunluq
- Docker ilə serverə yerləşdirmə
- Render üçün deploy konfiqurasiyası

## Lokal Windows
1. ZIP-i çıxar.
2. Python 3.11+ qur.
3. `run_windows.bat` aç.
4. `http://127.0.0.1:8000` aç.

## Lokal Docker
```bash
docker compose up --build
```
Sonra `http://localhost:8000`.

## İstənilən cihazdan giriş
Lokal `127.0.0.1` yalnız həmin kompüter üçündür. Telefon, planşet və başqa kompüterdən giriş üçün tətbiqi internetdə olan serverə deploy etmək lazımdır.

Ən sadə yol Render kimi Docker dəstəkləyən hostingdə `render.yaml` ilə deploy etməkdir. Deploy-dan sonra hosting sənə `https://...` ünvanı verir və həmin linklə telefon/kompüterdən daxil olmaq mümkündür.

Production üçün:
- `VALUORA_SECRET` uzun və təsadüfi saxla.
- HTTPS aktiv et.
- `COOKIE_SECURE=1` saxla.
- Real kommersiya trafikində SQLite əvəzinə PostgreSQL istifadə etmək tövsiyə olunur.
- Böyük scraping yükü üçün Playwright + Redis + background worker əlavə edilməlidir.

## Admin
Qeydiyyatda e-poçt `admin@...` ilə başlayan hesab admin rolu alır. Production sistemində bunu ayrıca təhlükəsiz admin provisioning mexanizminə keçirmək lazımdır.

## Məhdudiyyət
Bütün mağazalar scraping-ə icazə vermir. JavaScript-render olunan, Cloudflare/anti-bot istifadə edən və ya xüsusi API tələb edən mağazalar üçün ayrıca adapter və browser-rendering qatına ehtiyac var.


## Valuora 4.0
Yeni Commerce Intelligence qatları: Product Detail, Store Intelligence, Market Insights, Billing, Integrations, Security Center, Team Workspace və geniş Admin modulları. API v1 üçün API key authentication əlavə edilib.

## Public deployment — istənilən ölkədən giriş

Bu paket public internet deployment üçün `render.yaml` ilə hazırlanıb. GitHub repository-ni Render-də **New → Blueprint** vasitəsilə qoşduqda Render public `onrender.com` URL-i verir. Web service `0.0.0.0:$PORT` üzərindən işləyir və HTTPS Render tərəfindən təmin edilir.

SQLite məlumatlarının qorunması üçün public deployment konfiqurasiyası `/var/data/valuora.db` persistent diskindən istifadə edir.

Ətraflı addımlar: `DEPLOY_PUBLIC_AZ.md`
