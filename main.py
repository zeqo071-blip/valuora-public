import os
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

BASE = os.path.dirname(os.path.abspath(__file__))

app = FastAPI(title="Valuora")

# Static fayllar (CSS, JS, Şəkillər) üçün qovluq təyini
static_dir = os.path.join(BASE, 'app/static') if os.path.exists(os.path.join(BASE, 'app/static')) else os.path.join(BASE, 'static')
if os.path.exists(static_dir):
    app.mount('/static', StaticFiles(directory=static_dir), name='static')

# Templates qovluğunun təyini
templates_dir = os.path.join(BASE, 'app/templates') if os.path.exists(os.path.join(BASE, 'app/templates')) else os.path.join(BASE, 'templates')
if not os.path.exists(templates_dir):
    templates_dir = BASE

templates = Jinja2Templates(directory=templates_dir)

@app.get("/api/health")
def health_check():
    return {"status": "ok"}

@app.get("/", response_class=HTMLResponse)
def read_root(request: Request):
    possible_paths = [
        os.path.join(BASE, 'app/templates/index.html'),
        os.path.join(BASE, 'templates/index.html'),
        os.path.join(BASE, 'index.html')
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
                
    return "
