import os
import sys
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Uygulamanın ana dizinini belirle
BASE = os.path.dirname(os.path.abspath(__file__))

# 1. Gerekli tüm klasörlerin (static, templates, data) varlığını kontrol et ve otomatik oluştur
REQUIRED_DIRS = [
    os.path.join(BASE, 'app/static'),
    os.path.join(BASE, 'app/templates'),
    os.path.join(BASE, 'static'),
    os.path.join(BASE, 'templates'),
    '/tmp'
]

for directory in REQUIRED_DIRS:
    if not os.path.exists(directory):
        try:
            os.makedirs(directory, exist_ok=True)
        except Exception as e:
            print(f"Klasör oluşturulamadı ({directory}): {e}")

# 2. Veritabanı dosya dizinini kontrol et ve oluştur
db_path = os.getenv("VALUORA_DB", "/tmp/valuora.db")
db_dir = os.path.dirname(db_path)
if db_dir and not os.path.exists(db_dir):
    os.makedirs(db_dir, exist_ok=True)

# 3. FastAPI uygulamasını başlat
app = FastAPI(title="Valuora")

# 4. Statik dosyaları bağla (Static directory mounting)
static_dir = os.path.join(BASE, 'app/static') if os.path.exists(os.path.join(BASE, 'app/static')) else os.path.join(BASE, 'static')
app.mount('/static', StaticFiles(directory=static_dir), name='static')

# 5. Template dizinini belirle
templates_dir = os.path.join(BASE, 'app/templates') if os.path.exists(os.path.join(BASE, 'app/templates')) else os.path.join(BASE, 'templates')
templates = Jinja2Templates(directory=templates_dir)

# Sağlık kontrolü (Health check) endpoint'i
@app.get("/api/health")
def health_check():
    return {"status": "ok"}

# Ana sayfa yönlendirmesi
@app.get("/")
def read_root():
    return {"message": "Valuora API sunucusu sorunsuz çalışıyor!"}
