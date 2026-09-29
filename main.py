import os, re, sqlite3, hashlib, secrets, statistics, json
from datetime import datetime, timedelta
from urllib.parse import urlparse
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from itsdangerous import URLSafeSerializer
import requests
from bs4 import BeautifulSoup

BASE=os.path.dirname(os.path.dirname(__file__))
DB=os.getenv('VALUORA_DB', os.path.join(BASE,'valuora.db'))
os.makedirs(os.path.dirname(os.path.abspath(DB)), exist_ok=True)
SECRET=os.getenv('VALUORA_SECRET','change-this-secret-in-production')
signer=URLSafeSerializer(SECRET,'session')
app=FastAPI(title='Valuora AZ', version='5.0')
app.mount('/static',StaticFiles(directory=os.path.join(BASE,'app/static')),name='static')
templates=Jinja2Templates(directory=os.path.join(BASE,'app/templates'))

def now(): return datetime.utcnow().isoformat()

def db():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c

def init():
    c=db(); c.executescript('''
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,email TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,created_at TEXT,full_name TEXT DEFAULT '',role TEXT DEFAULT 'user',avatar TEXT DEFAULT '',last_login TEXT);
    CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY,signature TEXT NOT NULL,name TEXT NOT NULL,brand TEXT,model TEXT,category TEXT,created_at TEXT,image TEXT DEFAULT '',source_url TEXT DEFAULT '');
    CREATE TABLE IF NOT EXISTS price_observations(id INTEGER PRIMARY KEY,product_id INTEGER NOT NULL,url TEXT NOT NULL,source_domain TEXT,price REAL NOT NULL,currency TEXT,observed_at TEXT);
    CREATE TABLE IF NOT EXISTS analyses(id INTEGER PRIMARY KEY,user_id INTEGER,product_id INTEGER,url TEXT NOT NULL,current_price REAL,currency TEXT,market_price REAL,difference REAL,difference_percent REAL,status TEXT NOT NULL,created_at TEXT);
    CREATE TABLE IF NOT EXISTS alerts(id INTEGER PRIMARY KEY,user_id INTEGER,product_id INTEGER,target_price REAL,currency TEXT,active INTEGER DEFAULT 1,created_at TEXT);
    CREATE TABLE IF NOT EXISTS saved_products(id INTEGER PRIMARY KEY,user_id INTEGER,product_id INTEGER,created_at TEXT);
    CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY,user_id INTEGER,title TEXT,message TEXT,read INTEGER DEFAULT 0,created_at TEXT);
    CREATE TABLE IF NOT EXISTS api_keys(id INTEGER PRIMARY KEY,user_id INTEGER,name TEXT,key_hash TEXT,last_used TEXT,created_at TEXT);
    CREATE TABLE IF NOT EXISTS support_tickets(id INTEGER PRIMARY KEY,user_id INTEGER,subject TEXT,message TEXT,status TEXT DEFAULT 'open',created_at TEXT);
    CREATE TABLE IF NOT EXISTS user_settings(user_id INTEGER PRIMARY KEY,theme TEXT DEFAULT 'dark',currency TEXT DEFAULT 'AZN',email_alerts INTEGER DEFAULT 1,compact_mode INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS subscriptions(id INTEGER PRIMARY KEY,user_id INTEGER UNIQUE,plan TEXT DEFAULT 'free',status TEXT DEFAULT 'active',started_at TEXT,renewal_at TEXT);
    CREATE TABLE IF NOT EXISTS audit_logs(id INTEGER PRIMARY KEY,user_id INTEGER,action TEXT,meta TEXT,created_at TEXT);
    CREATE TABLE IF NOT EXISTS teams(id INTEGER PRIMARY KEY,user_id INTEGER,name TEXT,created_at TEXT);
    CREATE TABLE IF NOT EXISTS team_members(id INTEGER PRIMARY KEY,team_id INTEGER,email TEXT,role TEXT DEFAULT 'member',created_at TEXT);
    ''')
    for sql in [
        "ALTER TABLE users ADD COLUMN full_name TEXT DEFAULT ''", "ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'user'", "ALTER TABLE users ADD COLUMN avatar TEXT DEFAULT ''", "ALTER TABLE users ADD COLUMN last_login TEXT",
        "ALTER TABLE products ADD COLUMN image TEXT DEFAULT ''", "ALTER TABLE products ADD COLUMN source_url TEXT DEFAULT ''", "ALTER TABLE products ADD COLUMN brand TEXT DEFAULT ''", "ALTER TABLE products ADD COLUMN model TEXT DEFAULT ''"
    ]:
        try: c.execute(sql)
        except sqlite3.OperationalError: pass
    c.commit()
    # Fresh-install discovery catalog: real-looking demo data makes Explore useful immediately.
    if c.execute('SELECT COUNT(*) n FROM products').fetchone()['n']==0:
        demos=[
          ('demo-iphone-15','iPhone 15 128GB','Apple','A3090','Smartfon',899,'kontakt.az'),
          ('demo-galaxy-s24','Galaxy S24 256GB','Samsung','SM-S921B','Smartfon',1199,'irshad.az'),
          ('demo-macbook-air-m3','MacBook Air M3 13','Apple','A3113','Noutbuk',2399,'bakuelectronics.az'),
          ('demo-sony-xm5','WH-1000XM5','Sony','WH1000XM5','Audio',699,'soliton.az'),
          ('demo-ps5-slim','PlayStation 5 Slim','Sony','CFI-2016','Oyun',1099,'kontakt.az'),
          ('demo-lg-oled','LG OLED C4 55','LG','OLED55C4','TV',2499,'irshad.az'),
          ('demo-dyson-v15','Dyson V15 Detect','Dyson','V15','Məişət',1499,'bakuelectronics.az'),
          ('demo-ipad-air','iPad Air M2 11','Apple','MUWD3','Planşet',1299,'kontakt.az')
        ]
        for sig,name,brand,model,cat,price,domain in demos:
            cur=c.execute('INSERT INTO products(signature,name,brand,model,category,image,source_url,created_at) VALUES(?,?,?,?,?,?,?,?)',(sig,name,brand,model,cat,'','https://'+domain,now()))
            pid=cur.lastrowid
            for delta in (-0.08,-0.04,0,0.03,0.01):
                c.execute('INSERT INTO price_observations(product_id,url,source_domain,price,currency,observed_at) VALUES(?,?,?,?,?,?)',(pid,'https://'+domain+'/demo',domain,round(price*(1+delta),2),'AZN',(datetime.utcnow()-timedelta(days=4-abs(int(delta*100)))).isoformat()))
    c.commit(); c.close()
init()

def pw_hash(p,s=None):
    s=s or secrets.token_hex(16); return s+':'+hashlib.pbkdf2_hmac('sha256',p.encode(),bytes.fromhex(s),160000).hex()
def pw_ok(p,h):
    try: s,x=h.split(':',1); return secrets.compare_digest(pw_hash(p,s).split(':',1)[1],x)
    except: return False

def current_user(req):
    token=req.cookies.get('valuora_session')
    if not token:return None
    try:
        uid=int(signer.loads(token)); c=db(); u=c.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone(); c.close(); return dict(u) if u else None
    except: return None

def unread_count(uid):
    c=db(); n=c.execute('SELECT COUNT(*) n FROM notifications WHERE user_id=? AND read=0',(uid,)).fetchone()['n']; c.close(); return n

def page(req,name,**ctx):
    u=current_user(req); ctx.update(user=u, unread_count=unread_count(u['id']) if u else 0)
    return templates.TemplateResponse(name,{'request':req,**ctx})

def notify(uid,title,msg):
    c=db(); c.execute('INSERT INTO notifications(user_id,title,message,created_at) VALUES(?,?,?,?)',(uid,title,msg,now())); c.commit(); c.close()

def parse_price(s):
    if not s:return None
    m=re.search(r'(\d[\d\s.,]{0,20})',str(s).replace('\xa0',' '))
    if not m:return None
    x=m.group(1).strip().replace(' ','')
    if ',' in x and '.' in x: x=x.replace('.','').replace(',','.') if x.rfind(',')>x.rfind('.') else x.replace(',','')
    elif ',' in x: x=x.replace(',','.')
    try:return float(x)
    except:return None

def scrape(url):
    r=requests.get(url,headers={'User-Agent':'Mozilla/5.0 (Valuora/3.0; +price-analysis)'},timeout=15); r.raise_for_status()
    s=BeautifulSoup(r.text,'html.parser'); domain=urlparse(url).netloc.lower()
    title=s.find('meta',property='og:title') or s.find('meta',name='twitter:title')
    name=title.get('content') if title else (s.title.string.strip() if s.title and s.title.string else 'Naməlum məhsul')
    image=(s.find('meta',property='og:image') or s.find('meta',name='twitter:image')); image=image.get('content') if image else ''
    price=None; currency='AZN'
    for tag,attrs in [('meta',{'property':'product:price:amount'}),('meta',{'property':'og:price:amount'}),('meta',{'itemprop':'price'})]:
        x=s.find(tag,attrs)
        if x and x.get('content'): price=parse_price(x['content']); break
    for script in s.find_all('script',type='application/ld+json'):
        try:
            data=json.loads(script.string or ''); items=data if isinstance(data,list) else [data]
            for d in items:
                if isinstance(d,dict):
                    if d.get('name') and name=='Naməlum məhsul': name=d['name']
                    offers=d.get('offers',{}); offers=offers[0] if isinstance(offers,list) and offers else offers
                    if price is None and isinstance(offers,dict): price=parse_price(offers.get('price'))
                    if isinstance(offers,dict): currency=offers.get('priceCurrency',currency)
                    if not image and d.get('image'): image=d['image'][0] if isinstance(d['image'],list) else d['image']
        except: pass
    txt=' '.join(s.stripped_strings[:6000])
    if price is None: price=parse_price(txt[:30000])
    if '₼' in txt or 'AZN' in txt: currency='AZN'
    elif '$' in txt or 'USD' in txt: currency='USD'
    elif '€' in txt or 'EUR' in txt: currency='EUR'
    brand=''; model=''
    for key in ['brand','model']:
        m=s.find(attrs={'itemprop':key});
        if m: locals()[key]=m.get('content') or m.get_text(strip=True)
    return {'name':name[:500],'price':price,'currency':currency,'image':image,'domain':domain,'brand':brand,'model':model}

def analyze(uid,url):
    p=scrape(url); c=db(); norm=re.sub(r'[^a-z0-9]','',p['name'].lower()); sig=hashlib.sha256(norm.encode()).hexdigest()[:64]
    row=c.execute('SELECT id FROM products WHERE signature=?',(sig,)).fetchone()
    if row:
        pid=row['id']; c.execute('UPDATE products SET image=COALESCE(NULLIF(?,\'\'),image),source_url=?,brand=COALESCE(NULLIF(?,\'\'),brand),model=COALESCE(NULLIF(?,\'\'),model) WHERE id=?',(p['image'],url,p['brand'],p['model'],pid))
    else:
        cur=c.execute('INSERT INTO products(signature,name,brand,model,category,image,source_url,created_at) VALUES(?,?,?,?,?,?,?,?)',(sig,p['name'],p['brand'],p['model'],'Elektronika',p['image'],url,now())); pid=cur.lastrowid
    rows=c.execute('SELECT price FROM price_observations WHERE product_id=?',(pid,)).fetchall(); vals=[float(x['price']) for x in rows]
    market=statistics.median(vals) if vals else (p['price'] or 0); diff=(p['price']-market) if p['price'] is not None else 0; pct=(diff/market*100) if market else 0
    status='uyğun' if abs(pct)<5 else ('ucuz' if pct<0 else 'bahalı')
    if p['price'] is not None:c.execute('INSERT INTO price_observations(product_id,url,source_domain,price,currency,observed_at) VALUES(?,?,?,?,?,?)',(pid,url,p['domain'],p['price'],p['currency'],now()))
    c.execute('INSERT INTO analyses(user_id,product_id,url,current_price,currency,market_price,difference,difference_percent,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(uid,pid,url,p['price'],p['currency'],market,diff,pct,status,now())); c.commit(); c.close(); notify(uid,'Yeni analiz hazır',f'{p["name"][:55]} — nəticə: {status}.')
    return {**p,'market':market,'difference':diff,'percent':pct,'status':status,'product_id':pid}

def require_user(req): return current_user(req)

@app.get('/',response_class=HTMLResponse)
def home(req:Request): return page(req,'home.html',title='Valuora — Ağıllı qiymət platforması')
@app.get('/login',response_class=HTMLResponse)
def login(req:Request): return page(req,'auth.html',mode='login',title='Giriş')
@app.get('/register',response_class=HTMLResponse)
def register(req:Request): return page(req,'auth.html',mode='register',title='Qeydiyyat')
@app.post('/auth')
def auth(req:Request,email:str=Form(...),password:str=Form(...),mode:str=Form(...),full_name:str=Form('')):
    c=db(); email=email.lower().strip(); row=c.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()
    if mode=='register':
        if row:return RedirectResponse('/register?error=Bu+e-poçt+artıq+qeydiyyatdan+keçib',303)
        role='admin' if email.startswith('admin@') else 'user'; cur=c.execute('INSERT INTO users(email,password_hash,full_name,role,created_at) VALUES(?,?,?,?,?)',(email,pw_hash(password),full_name.strip(),role,now())); uid=cur.lastrowid; c.execute('INSERT OR IGNORE INTO user_settings(user_id) VALUES(?)',(uid,)); c.execute('INSERT OR IGNORE INTO subscriptions(user_id,plan,status,started_at) VALUES(?,?,?,?)',(uid,'free','active',now()))
    else:
        if not row or not pw_ok(password,row['password_hash']): return RedirectResponse('/login?error=E-poçt+və+ya+şifrə+səhvdir',303)
        uid=row['id']; c.execute('UPDATE users SET last_login=? WHERE id=?',(now(),uid)); c.execute('INSERT OR IGNORE INTO user_settings(user_id) VALUES(?)',(uid,)); c.execute('INSERT OR IGNORE INTO subscriptions(user_id,plan,status,started_at) VALUES(?,?,?,?)',(uid,'free','active',now()))
    c.commit(); c.close(); token=signer.dumps(uid); r=RedirectResponse('/dashboard',303); r.set_cookie('valuora_session',token,httponly=True,samesite='lax',secure=os.getenv('COOKIE_SECURE','0')=='1',max_age=2592000); return r
@app.get('/logout')
def logout(req:Request): r=RedirectResponse('/'); r.delete_cookie('valuora_session'); return r

@app.post('/analyze')
def do_analyze(req:Request,url:str=Form(...)):
    u=require_user(req)
    if not u:return RedirectResponse('/login',303)
    if not re.match(r'^https?://',url.strip()):return RedirectResponse('/dashboard?error=Keçərli+URL+daxil+et',303)
    try: x=analyze(u['id'],url.strip()); return RedirectResponse('/result?analysis='+str(x['product_id']),303)
    except Exception:return RedirectResponse('/dashboard?error=Bu+link+oxuna+bilinmədi.+Başqa+mağaza+linki+yoxla',303)

@app.get('/dashboard',response_class=HTMLResponse)
def dashboard(req:Request):
    u=require_user(req)
    if not u:return RedirectResponse('/login',303)
    c=db(); analyses=c.execute('SELECT a.*,p.name,p.image FROM analyses a LEFT JOIN products p ON p.id=a.product_id WHERE a.user_id=? ORDER BY a.id DESC LIMIT 12',(u['id'],)).fetchall(); stats={'analyses':c.execute('SELECT COUNT(*) n FROM analyses WHERE user_id=?',(u['id'],)).fetchone()['n'],'saved':c.execute('SELECT COUNT(*) n FROM saved_products WHERE user_id=?',(u['id'],)).fetchone()['n'],'alerts':c.execute('SELECT COUNT(*) n FROM alerts WHERE user_id=? AND active=1',(u['id'],)).fetchone()['n']}; c.close(); return page(req,'dashboard.html',analyses=analyses,stats=stats)

@app.get('/result',response_class=HTMLResponse)
def result(req:Request,analysis:int):
    u=require_user(req)
    if not u:return RedirectResponse('/login',303)
    c=db(); a=c.execute('SELECT a.*,p.name,p.category,p.image,p.brand,p.model FROM analyses a LEFT JOIN products p ON p.id=a.product_id WHERE a.product_id=? AND a.user_id=? ORDER BY a.id DESC LIMIT 1',(analysis,u['id'])).fetchone(); hist=c.execute('SELECT price,currency,source_domain,observed_at,url FROM price_observations WHERE product_id=? ORDER BY id ASC LIMIT 60',(analysis,)).fetchall(); saved=bool(c.execute('SELECT 1 FROM saved_products WHERE user_id=? AND product_id=?',(u['id'],analysis)).fetchone()); c.close()
    if not a:return RedirectResponse('/dashboard',303)
    score=max(0,min(100,100-abs(float(a['difference_percent'] or 0))*4)); return page(req,'result.html',a=a,hist=hist,chart=[{'x':h['observed_at'][:16],'y':h['price']} for h in hist],saved=saved,score=score)

@app.get('/history',response_class=HTMLResponse)
def history(req:Request):
    u=require_user(req)
    if not u:return RedirectResponse('/login',303)
    c=db(); rows=c.execute('SELECT a.*,p.name,p.image FROM analyses a LEFT JOIN products p ON p.id=a.product_id WHERE a.user_id=? ORDER BY a.id DESC',(u['id'],)).fetchall(); c.close(); return page(req,'history.html',rows=rows)
@app.get('/saved',response_class=HTMLResponse)
def saved(req:Request):
    u=require_user(req)
    if not u:return RedirectResponse('/login',303)
    c=db(); rows=c.execute('SELECT s.*,p.name,p.image,p.category,p.brand,p.model FROM saved_products s JOIN products p ON p.id=s.product_id WHERE s.user_id=? ORDER BY s.id DESC',(u['id'],)).fetchall(); c.close(); return page(req,'saved.html',rows=rows)
@app.post('/saved/toggle')
def toggle_saved(req:Request,product_id:int=Form(...)):
    u=require_user(req)
    if not u:return RedirectResponse('/login',303)
    c=db(); row=c.execute('SELECT id FROM saved_products WHERE user_id=? AND product_id=?',(u['id'],product_id)).fetchone();
    if row:c.execute('DELETE FROM saved_products WHERE id=?',(row['id'],))
    else:c.execute('INSERT INTO saved_products(user_id,product_id,created_at) VALUES(?,?,?)',(u['id'],product_id,now()))
    c.commit(); c.close(); return RedirectResponse(f'/result?analysis={product_id}',303)

@app.get('/compare',response_class=HTMLResponse)
def compare(req:Request):
    u=require_user(req)
    if not u:return RedirectResponse('/login',303)
    ids=[int(x) for x in req.query_params.getlist('id') if x.isdigit()][:4]
    c=db(); products=[]
    if ids:
        q=','.join('?'*len(ids)); products=c.execute(f'SELECT p.*, (SELECT price FROM price_observations o WHERE o.product_id=p.id ORDER BY o.id DESC LIMIT 1) latest_price FROM products p WHERE p.id IN ({q})',ids).fetchall()
    else:
        products=c.execute('SELECT p.*, (SELECT price FROM price_observations o WHERE o.product_id=p.id ORDER BY o.id DESC LIMIT 1) latest_price FROM products p ORDER BY p.id DESC LIMIT 8').fetchall()
    c.close(); return page(req,'compare.html',products=products)

@app.get('/explore',response_class=HTMLResponse)
def explore(req:Request):
    c=db(); q=req.query_params.get('q','').strip(); category=req.query_params.get('category','').strip(); sort=req.query_params.get('sort','new').strip()
    sql='''SELECT p.*, (SELECT price FROM price_observations o WHERE o.product_id=p.id ORDER BY o.id DESC LIMIT 1) latest_price, (SELECT COUNT(*) FROM price_observations o WHERE o.product_id=p.id) observations FROM products p WHERE 1=1'''; args=[]
    if q:
        like=f'%{q}%'; sql+=' AND (p.name LIKE ? OR p.brand LIKE ? OR p.model LIKE ? OR p.category LIKE ?)'; args += [like,like,like,like]
    if category: sql+=' AND p.category=?'; args.append(category)
    order={'price_low':'latest_price ASC','price_high':'latest_price DESC','activity':'observations DESC','new':'p.id DESC'}.get(sort,'p.id DESC')
    sql+=f' ORDER BY {order} LIMIT 60'; products=c.execute(sql,args).fetchall()
    cats=[r['category'] for r in c.execute('SELECT DISTINCT category FROM products WHERE category IS NOT NULL AND category!="" ORDER BY category').fetchall()]
    total=c.execute('SELECT COUNT(*) n FROM products').fetchone()['n']; observation_total=c.execute('SELECT COUNT(*) n FROM price_observations').fetchone()['n']; store_total=c.execute('SELECT COUNT(DISTINCT source_domain) n FROM price_observations').fetchone()['n']; c.close()
    return page(req,'explore.html',products=products,categories=cats,q=q,category=category,sort=sort,total=total,observation_total=observation_total,store_total=store_total,title='Kəşf et — Valuora')

@app.get('/api/explore')
def api_explore(q:str='',category:str='',sort:str='new',limit:int=24):
    limit=max(1,min(limit,100)); c=db(); sql='''SELECT p.id,p.name,p.brand,p.model,p.category,p.image,(SELECT price FROM price_observations o WHERE o.product_id=p.id ORDER BY o.id DESC LIMIT 1) latest_price,(SELECT COUNT(*) FROM price_observations o WHERE o.product_id=p.id) observations FROM products p WHERE 1=1'''; args=[]
    if q.strip():
        like=f'%{q.strip()}%'; sql+=' AND (p.name LIKE ? OR p.brand LIKE ? OR p.model LIKE ? OR p.category LIKE ?)'; args += [like]*4
    if category.strip(): sql+=' AND p.category=?'; args.append(category.strip())
    order={'price_low':'latest_price ASC','price_high':'latest_price DESC','activity':'observations DESC','new':'p.id DESC'}.get(sort,'p.id DESC'); sql+=f' ORDER BY {order} LIMIT ?'; args.append(limit); rows=c.execute(sql,args).fetchall(); c.close(); return {'items':[dict(r) for r in rows],'count':len(rows)}

@app.get('/stores',response_class=HTMLResponse)
def stores(req:Request):
    c=db(); rows=c.execute('SELECT source_domain,COUNT(*) n,MIN(price) min_price,MAX(price) max_price,AVG(price) avg_price FROM price_observations GROUP BY source_domain ORDER BY n DESC').fetchall(); c.close(); return page(req,'stores.html',stores=rows)
@app.get('/plans',response_class=HTMLResponse)
def plans(req:Request): return page(req,'plans.html',title='Valuora planları')
@app.get('/api-docs',response_class=HTMLResponse)
def api_docs(req:Request): return page(req,'api_docs.html',title='Valuora API')

@app.get('/alerts',response_class=HTMLResponse)
def alerts(req:Request):
    u=require_user(req)
    if not u:return RedirectResponse('/login',303)
    c=db(); rows=c.execute('SELECT al.*,p.name FROM alerts al JOIN products p ON p.id=al.product_id WHERE al.user_id=? ORDER BY al.id DESC',(u['id'],)).fetchall(); products=c.execute('SELECT id,name FROM products ORDER BY id DESC LIMIT 50').fetchall(); c.close(); return page(req,'alerts.html',rows=rows,products=products)
@app.post('/alerts')
def create_alert(req:Request,product_id:int=Form(...),target_price:float=Form(...),currency:str=Form('AZN')):
    u=require_user(req)
    if not u:return RedirectResponse('/login',303)
    c=db(); c.execute('INSERT INTO alerts(user_id,product_id,target_price,currency,created_at) VALUES(?,?,?,?,?)',(u['id'],product_id,target_price,currency,now())); c.commit(); c.close(); notify(u['id'],'Qiymət xəbərdarlığı yaradıldı',f'Məqsəd qiymət: {target_price:.2f} {currency}.'); return RedirectResponse('/alerts',303)
@app.post('/alerts/delete')
def delete_alert(req:Request,alert_id:int=Form(...)):
    u=require_user(req)
    if not u:return RedirectResponse('/login',303)
    c=db(); c.execute('DELETE FROM alerts WHERE id=? AND user_id=?',(alert_id,u['id'])); c.commit(); c.close(); return RedirectResponse('/alerts',303)

@app.get('/notifications',response_class=HTMLResponse)
def notifications(req:Request):
    u=require_user(req)
    if not u:return RedirectResponse('/login',303)
    c=db(); rows=c.execute('SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 80',(u['id'],)).fetchall(); c.execute('UPDATE notifications SET read=1 WHERE user_id=?',(u['id'],)); c.commit(); c.close(); return page(req,'notifications.html',rows=rows)
@app.get('/profile',response_class=HTMLResponse)
def profile(req:Request):
    u=require_user(req)
    if not u:return RedirectResponse('/login',303)
    return page(req,'profile.html')
@app.post('/profile')
def profile_save(req:Request,full_name:str=Form('')):
    u=require_user(req)
    if not u:return RedirectResponse('/login',303)
    c=db(); c.execute('UPDATE users SET full_name=? WHERE id=?',(full_name.strip(),u['id'])); c.commit(); c.close(); return RedirectResponse('/profile?saved=1',303)

@app.get('/settings',response_class=HTMLResponse)
def settings(req:Request):
    u=require_user(req)
    if not u:return RedirectResponse('/login',303)
    c=db(); s=c.execute('SELECT * FROM user_settings WHERE user_id=?',(u['id'],)).fetchone() or {'theme':'dark','currency':'AZN','email_alerts':1,'compact_mode':0}; c.close(); return page(req,'settings.html',settings=s)
@app.post('/settings')
def settings_save(req:Request,theme:str=Form('dark'),currency:str=Form('AZN'),email_alerts:int=Form(0),compact_mode:int=Form(0)):
    u=require_user(req)
    if not u:return RedirectResponse('/login',303)
    c=db(); c.execute('INSERT INTO user_settings(user_id,theme,currency,email_alerts,compact_mode) VALUES(?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET theme=excluded.theme,currency=excluded.currency,email_alerts=excluded.email_alerts,compact_mode=excluded.compact_mode',(u['id'],theme,currency,email_alerts,compact_mode)); c.commit(); c.close(); return RedirectResponse('/settings?saved=1',303)

@app.get('/support',response_class=HTMLResponse)
def support(req:Request):
    u=require_user(req)
    if not u:return RedirectResponse('/login',303)
    c=db(); tickets=c.execute('SELECT * FROM support_tickets WHERE user_id=? ORDER BY id DESC',(u['id'],)).fetchall(); c.close(); return page(req,'support.html',tickets=tickets)
@app.post('/support')
def support_create(req:Request,subject:str=Form(...),message:str=Form(...)):
    u=require_user(req)
    if not u:return RedirectResponse('/login',303)
    c=db(); c.execute('INSERT INTO support_tickets(user_id,subject,message,created_at) VALUES(?,?,?,?)',(u['id'],subject.strip(),message.strip(),now())); c.commit(); c.close(); notify(u['id'],'Dəstək müraciəti yaradıldı',subject.strip()); return RedirectResponse('/support',303)

@app.get('/admin',response_class=HTMLResponse)
def admin(req:Request):
    u=require_user(req)
    if not u or u.get('role')!='admin':return RedirectResponse('/dashboard',303)
    c=db(); stats={'users':c.execute('select count(*) n from users').fetchone()['n'],'products':c.execute('select count(*) n from products').fetchone()['n'],'analyses':c.execute('select count(*) n from analyses').fetchone()['n'],'observations':c.execute('select count(*) n from price_observations').fetchone()['n'],'alerts':c.execute('select count(*) n from alerts').fetchone()['n'],'tickets':c.execute('select count(*) n from support_tickets where status="open"').fetchone()['n']}; recent=c.execute('select * from analyses order by id desc limit 25').fetchall(); users=c.execute('select id,email,full_name,role,created_at,last_login from users order by id desc limit 25').fetchall(); tickets=c.execute('select t.*,u.email from support_tickets t left join users u on u.id=t.user_id order by t.id desc limit 20').fetchall(); c.close(); return page(req,'admin.html',stats=stats,recent=recent,users=users,tickets=tickets)

@app.post('/admin/ticket')
def admin_ticket(req:Request,ticket_id:int=Form(...),status:str=Form(...)):
    u=require_user(req)
    if not u or u.get('role')!='admin':return RedirectResponse('/dashboard',303)
    c=db(); c.execute('UPDATE support_tickets SET status=? WHERE id=?',(status,ticket_id)); row=c.execute('SELECT user_id,subject FROM support_tickets WHERE id=?',(ticket_id,)).fetchone(); c.commit(); c.close();
    if row: notify(row['user_id'],'Dəstək müraciəti yeniləndi',f'{row["subject"]} — status: {status}.')
    return RedirectResponse('/admin',303)

@app.get('/api/health')
def health():return {'status':'ok','app':'Valuora AZ','version':'5.0','time':now()}
@app.get('/api/stats')
def api_stats(req:Request):
    u=require_user(req)
    if not u:return JSONResponse({'error':'unauthorized'},401)
    c=db(); rows=c.execute('SELECT status,COUNT(*) n FROM analyses WHERE user_id=? GROUP BY status',(u['id'],)).fetchall(); c.close(); return {'status_breakdown':{r['status']:r['n'] for r in rows}}
@app.get('/api/products/{product_id}')
def api_product(product_id:int):
    c=db(); p=c.execute('SELECT * FROM products WHERE id=?',(product_id,)).fetchone(); obs=c.execute('SELECT price,currency,source_domain,observed_at FROM price_observations WHERE product_id=? ORDER BY id DESC LIMIT 100',(product_id,)).fetchall(); c.close()
    if not p:return JSONResponse({'error':'not_found'},404)
    return {'product':dict(p),'observations':[dict(x) for x in obs]}
@app.get('/api/compare')
def api_compare(ids:str=''):
    values=[int(x) for x in ids.split(',') if x.strip().isdigit()][:6]
    if not values:return {'products':[]}
    c=db(); q=','.join('?'*len(values)); rows=c.execute(f'SELECT p.id,p.name,p.brand,p.model,(SELECT price FROM price_observations o WHERE o.product_id=p.id ORDER BY o.id DESC LIMIT 1) latest_price FROM products p WHERE p.id IN ({q})',values).fetchall(); c.close(); return {'products':[dict(r) for r in rows]}
@app.post('/api/keys')
def create_api_key(req:Request,name:str=Form('Yeni açar')):
    u=require_user(req)
    if not u:return JSONResponse({'error':'unauthorized'},401)
    raw='vlu_'+secrets.token_urlsafe(28); h=hashlib.sha256(raw.encode()).hexdigest(); c=db(); c.execute('INSERT INTO api_keys(user_id,name,key_hash,created_at) VALUES(?,?,?,?)',(u['id'],name,h,now())); c.commit(); c.close(); return {'name':name,'api_key':raw,'warning':'Bu açar yalnız bir dəfə göstərilir.'}

# --- VALUORA 4.0 PRODUCT SUITE ---
def log_action(uid, action, meta=''):
    c=db(); c.execute('INSERT INTO audit_logs(user_id,action,meta,created_at) VALUES(?,?,?,?)',(uid,action,meta,now())); c.commit(); c.close()

def admin_only(req):
    u=require_user(req); return u if u and u.get('role')=='admin' else None

@app.get('/product/{product_id}',response_class=HTMLResponse)
def product_page(req:Request,product_id:int):
    c=db(); p=c.execute("SELECT p.*, (SELECT price FROM price_observations o WHERE o.product_id=p.id ORDER BY o.id DESC LIMIT 1) latest_price, (SELECT COUNT(*) FROM price_observations o WHERE o.product_id=p.id) observations FROM products p WHERE p.id=?",(product_id,)).fetchone(); obs=c.execute('SELECT * FROM price_observations WHERE product_id=? ORDER BY id DESC LIMIT 100',(product_id,)).fetchall(); c.close()
    if not p:return RedirectResponse('/explore',303)
    return page(req,'product.html',product=p,observations=obs,chart=[{'x':o['observed_at'][:16],'y':o['price']} for o in reversed(obs)],title=p['name'])

@app.get('/store/{domain:path}',response_class=HTMLResponse)
def store_page(req:Request,domain:str):
    domain=domain.strip('/')
    c=db(); obs=c.execute('SELECT o.*,p.name,p.id product_id FROM price_observations o JOIN products p ON p.id=o.product_id WHERE o.source_domain=? ORDER BY o.id DESC LIMIT 120',(domain,)).fetchall(); summary=c.execute('SELECT COUNT(*) n,MIN(price) min_price,MAX(price) max_price,AVG(price) avg_price FROM price_observations WHERE source_domain=?',(domain,)).fetchone(); c.close()
    return page(req,'store.html',domain=domain,observations=obs,summary=summary,title=f'{domain} — Mağaza')

@app.get('/insights',response_class=HTMLResponse)
def insights(req:Request):
    c=db(); total=c.execute('SELECT COUNT(*) n FROM price_observations').fetchone()['n']; products=c.execute('SELECT COUNT(*) n FROM products').fetchone()['n']; stores=c.execute('SELECT COUNT(DISTINCT source_domain) n FROM price_observations').fetchone()['n']; avg=c.execute('SELECT AVG(price) n FROM price_observations').fetchone()['n'] or 0
    movers=c.execute('''SELECT p.id,p.name,MIN(o.price) low,MAX(o.price) high,COUNT(o.id) n FROM products p JOIN price_observations o ON o.product_id=p.id GROUP BY p.id ORDER BY (MAX(o.price)-MIN(o.price)) DESC LIMIT 12''').fetchall()
    categories=c.execute('SELECT category,COUNT(*) n FROM products GROUP BY category ORDER BY n DESC LIMIT 12').fetchall(); c.close(); return page(req,'insights.html',total=total,products=products,stores=stores,avg=avg,movers=movers,categories=categories,title='Market Insights')

@app.get('/billing',response_class=HTMLResponse)
def billing(req:Request):
    u=require_user(req)
    if not u:return RedirectResponse('/login',303)
    c=db(); sub=c.execute('SELECT * FROM subscriptions WHERE user_id=?',(u['id'],)).fetchone(); c.close(); return page(req,'billing.html',sub=sub,title='Abunəlik və Billing')

@app.post('/billing/plan')
def billing_plan(req:Request,plan:str=Form(...)):
    u=require_user(req)
    if not u:return RedirectResponse('/login',303)
    allowed={'free','pro','business'}; plan=plan if plan in allowed else 'free'; c=db(); c.execute('INSERT INTO subscriptions(user_id,plan,status,started_at) VALUES(?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET plan=excluded.plan,status=excluded.status,renewal_at=excluded.renewal_at',(u['id'],plan,'active',now(),(datetime.utcnow()+timedelta(days=30)).isoformat())); c.commit(); c.close(); notify(u['id'],'Plan yeniləndi',f'Cari plan: {plan.upper()}.'); log_action(u['id'],'subscription_change',plan); return RedirectResponse('/billing',303)

@app.get('/integrations',response_class=HTMLResponse)
def integrations(req:Request):
    u=require_user(req)
    if not u:return RedirectResponse('/login',303)
    c=db(); keys=c.execute('SELECT id,name,last_used,created_at FROM api_keys WHERE user_id=? ORDER BY id DESC',(u['id'],)).fetchall(); c.close(); return page(req,'integrations.html',keys=keys,title='İnteqrasiyalar')

@app.get('/security',response_class=HTMLResponse)
def security(req:Request):
    u=require_user(req)
    if not u:return RedirectResponse('/login',303)
    c=db(); logs=c.execute('SELECT action,meta,created_at FROM audit_logs WHERE user_id=? ORDER BY id DESC LIMIT 30',(u['id'],)).fetchall(); c.close(); return page(req,'security.html',logs=logs,title='Təhlükəsizlik')

@app.get('/team',response_class=HTMLResponse)
def team(req:Request):
    u=require_user(req)
    if not u:return RedirectResponse('/login',303)
    c=db(); t=c.execute('SELECT * FROM teams WHERE user_id=? ORDER BY id DESC LIMIT 1',(u['id'],)).fetchone(); members=[]
    if t: members=c.execute('SELECT * FROM team_members WHERE team_id=? ORDER BY id DESC',(t['id'],)).fetchall()
    c.close(); return page(req,'team.html',team=t,members=members,title='Komanda')

@app.post('/team')
def team_save(req:Request,name:str=Form(...),email:str=Form('')):
    u=require_user(req)
    if not u:return RedirectResponse('/login',303)
    c=db(); t=c.execute('SELECT * FROM teams WHERE user_id=? LIMIT 1',(u['id'],)).fetchone()
    if not t:
        cur=c.execute('INSERT INTO teams(user_id,name,created_at) VALUES(?,?,?)',(u['id'],name.strip(),now())); tid=cur.lastrowid
    else: tid=t['id']; c.execute('UPDATE teams SET name=? WHERE id=?',(name.strip(),tid))
    if email.strip(): c.execute('INSERT INTO team_members(team_id,email,role,created_at) VALUES(?,?,?,?)',(tid,email.strip().lower(),'member',now()))
    c.commit(); c.close(); return RedirectResponse('/team',303)

@app.get('/admin/users',response_class=HTMLResponse)
def admin_users(req:Request):
    u=admin_only(req)
    if not u:return RedirectResponse('/dashboard',303)
    c=db(); users=c.execute('SELECT u.*,COALESCE(s.plan,"free") plan,(SELECT COUNT(*) FROM analyses a WHERE a.user_id=u.id) analyses FROM users u LEFT JOIN subscriptions s ON s.user_id=u.id ORDER BY u.id DESC').fetchall(); c.close(); return page(req,'admin_users.html',users=users,title='Admin — İstifadəçilər')

@app.post('/admin/user-role')
def admin_user_role(req:Request,user_id:int=Form(...),role:str=Form(...)):
    u=admin_only(req)
    if not u:return RedirectResponse('/dashboard',303)
    role='admin' if role=='admin' else 'user'; c=db(); c.execute('UPDATE users SET role=? WHERE id=?',(role,user_id)); c.commit(); c.close(); return RedirectResponse('/admin/users',303)

@app.get('/admin/products',response_class=HTMLResponse)
def admin_products(req:Request):
    u=admin_only(req)
    if not u:return RedirectResponse('/dashboard',303)
    c=db(); products=c.execute('''SELECT p.*,COUNT(o.id) observations,MAX(o.price) latest_price FROM products p LEFT JOIN price_observations o ON o.product_id=p.id GROUP BY p.id ORDER BY p.id DESC LIMIT 150''').fetchall(); c.close(); return page(req,'admin_products.html',products=products,title='Admin — Məhsullar')

@app.post('/admin/product-delete')
def admin_product_delete(req:Request,product_id:int=Form(...)):
    u=admin_only(req)
    if not u:return RedirectResponse('/dashboard',303)
    c=db(); c.execute('DELETE FROM price_observations WHERE product_id=?',(product_id,)); c.execute('DELETE FROM products WHERE id=?',(product_id,)); c.commit(); c.close(); return RedirectResponse('/admin/products',303)

@app.get('/admin/tickets',response_class=HTMLResponse)
def admin_tickets(req:Request):
    u=admin_only(req)
    if not u:return RedirectResponse('/dashboard',303)
    c=db(); tickets=c.execute('SELECT t.*,u.email FROM support_tickets t LEFT JOIN users u ON u.id=t.user_id ORDER BY t.id DESC').fetchall(); c.close(); return page(req,'admin_tickets.html',tickets=tickets,title='Admin — Dəstək')

@app.get('/changelog',response_class=HTMLResponse)
def changelog(req:Request): return page(req,'changelog.html',title='Valuora Changelog')

@app.get('/api/v1/products/{product_id}')
def api_v1_product(product_id:int,request:Request):
    key=request.headers.get('x-api-key',''); h=hashlib.sha256(key.encode()).hexdigest() if key else ''
    c=db(); owner=c.execute('SELECT user_id FROM api_keys WHERE key_hash=?',(h,)).fetchone()
    if not owner:return JSONResponse({'error':'invalid_api_key'},401)
    p=c.execute('SELECT * FROM products WHERE id=?',(product_id,)).fetchone(); obs=c.execute('SELECT price,currency,source_domain,observed_at FROM price_observations WHERE product_id=? ORDER BY id DESC LIMIT 100',(product_id,)).fetchall(); c.execute('UPDATE api_keys SET last_used=? WHERE key_hash=?',(now(),h)); c.commit(); c.close()
    if not p:return JSONResponse({'error':'not_found'},404)
    return {'product':dict(p),'observations':[dict(x) for x in obs]}

@app.get('/manifest.webmanifest')
def manifest(): return FileResponse(os.path.join(BASE,'app/static/manifest.webmanifest'),media_type='application/manifest+json')
@app.get('/sw.js')
def sw(): return FileResponse(os.path.join(BASE,'app/static/sw.js'),media_type='application/javascript')
