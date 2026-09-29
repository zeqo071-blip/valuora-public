import os
import sys
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

BASE = os.path.dirname(os.path.abspath(__file__))

app = FastAPI(title="Valuora")

static_dir = os.path.join(BASE, 'app/static') if os.path.exists(os.path.join(BASE, 'app/static')) else os.path.join(BASE, 'static')
if os.path.exists(static_dir):
    app.mount('/static', StaticFiles(directory=static_dir), name='static')

templates_dir = os.path.join(BASE, 'app/templates') if os.path.exists(os.path.join(BASE, 'app/templates')) else os.path.join(BASE, 'templates')
if not os.path.exists(templates_dir):
    templates_dir = BASE

templates = Jinja2Templates(directory=templates_dir)

@app.get("/api/health")
def health_check():
    return {"status": "ok"}

@app.get("/", response_class=HTMLResponse)
def read_root():
    possible_paths = [
        os.path.join(BASE, 'app/templates/index.html'),
        os.path.join(BASE, 'templates/index.html'),
        os.path.join(BASE, 'index.html')
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
                
    msg_bytes = [60, 104, 49, 62, 86, 97, 108, 117, 111, 114, 97, 60, 47, 104, 49, 62]
    return HTMLResponse(content=bytes(msg_bytes).decode())
