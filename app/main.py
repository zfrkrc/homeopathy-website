import os
import uuid
import json
import time
import logging
import threading
import re
import httpx
import asyncio
import markdown
import bleach
import shutil
import base64
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, send_file, Response, abort, make_response
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash
from app.models import init_db, User, get_posts, get_post, get_post_by_id, search_posts
from app.portal import portal_bp, init_portal_db
from app.models import create_post, update_post, delete_post
from app.models import get_setting, set_setting, slugify, get_categories
from app.models import increment_post_views, get_related_posts
from app.models import get_category, create_category, update_category, delete_category
from app.models import get_gallery_images, add_gallery_image, delete_gallery_image
from app.models import get_subscribers, add_subscriber, toggle_subscriber, delete_subscriber, get_subscriber_count
from app.models import get_pageview_stats, record_pageview, get_db

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), 'data', 'uploads')
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_IMAGE_EXT = {'jpg', 'jpeg', 'png', 'gif', 'webp', 'svg'}

def save_upload(file, prefix):
    """Save an uploaded image and return its stored filename ('' on failure)."""
    if not file or not file.filename:
        return ''
    ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
    if ext not in ALLOWED_IMAGE_EXT:
        return ''
    fname = f'{prefix}_{uuid.uuid4().hex[:12]}.{ext}'
    file.save(os.path.join(UPLOAD_DIR, fname))
    return fname

def delete_upload(fname):
    if fname:
        path = os.path.join(UPLOAD_DIR, fname)
        if os.path.exists(path):
            os.remove(path)

app = Flask(__name__)
app.config.update(
    PREFERRED_URL_SCHEME='https',
)
app.register_blueprint(portal_bp)
app.secret_key = os.environ.get('SECRET_KEY') or os.urandom(32)
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'admin_login'

md = markdown.Markdown(extensions=['extra', 'codehilite'])

DEFAULT_FONTS = [
    ('sans-serif', 'Sistem Varsayılan (sans-serif)'),
    ('serif', 'Serif'),
    ('Georgia, serif', 'Georgia'),
    ('"Palatino Linotype", "Book Antiqua", Palatino, serif', 'Palatino'),
    ('"Times New Roman", Times, serif', 'Times New Roman'),
    ('Arial, Helvetica, sans-serif', 'Arial'),
    ('"Arial Black", Gadget, sans-serif', 'Arial Black'),
    ('"Comic Sans MS", cursive, sans-serif', 'Comic Sans MS'),
    ('Impact, Charcoal, sans-serif', 'Impact'),
    ('"Lucida Sans Unicode", "Lucida Grande", sans-serif', 'Lucida Sans'),
    ('Tahoma, Geneva, sans-serif', 'Tahoma'),
    ('"Trebuchet MS", Helvetica, sans-serif', 'Trebuchet MS'),
    ('Verdana, Geneva, sans-serif', 'Verdana'),
    ('"Courier New", Courier, monospace', 'Courier New'),
    ('"Lucida Console", Monaco, monospace', 'Lucida Console'),
]

COLOR_PRESETS = [
    ('#3d6b4f', 'Yeşil (Klasik)'),
    ('#2c5f2d', 'Koyu Yeşil'),
    ('#1a5276', 'Lacivert'),
    ('#6c3483', 'Mor'),
    ('#922b21', 'Kırmızı'),
    ('#d4ac0d', 'Altın'),
    ('#1b4f72', 'Kraliyet Mavisi'),
    ('#2e4053', 'Antrasit'),
]

WEATHER_CODES = {
    0: '☀️ Açık', 1: '🌤️ Az Bulutlu', 2: '⛅ Parçalı Bulutlu', 3: '☁️ Kapalı',
    45: '🌫️ Sisli', 48: '🌫️ Kırağılı Sis',
    51: '🌦️ Hafif Çisenti', 53: '🌦️ Çisenti', 55: '🌧️ Yoğun Çisenti',
    56: '🌧 Hafif Donan Çisenti', 57: '🌧 Donan Çisenti',
    61: '🌦️ Hafif Yağmur', 63: '🌧️ Yağmur', 65: '🌧️ Yoğun Yağmur',
    66: '🌧️ Hafif Donan Yağmur', 67: '🌧️ Donan Yağmur',
    71: '🌨️ Hafif Kar', 73: '🌨️ Kar', 75: '❄️ Yoğun Kar',
    77: '❄️ Kar Tanesi',
    80: '🌦️ Hafif Sağanak', 81: '🌧️ Sağanak', 82: '🌧️ Yoğun Sağanak',
    85: '🌨️ Hafif Kar Sağanağı', 86: '🌨️ Kar Sağanağı',
    95: '⛈️ Gök Gürültülü Fırtına', 96: '⛈️ Dolu ile Fırtına', 99: '⛈️ Şiddetli Dolu ile Fırtına',
}

weather_cache = {'data': None, 'ts': 0}

@login_manager.user_loader
def load_user(user_id):
    return User.get(int(user_id))

def fetch_weather(location):
    now = time.time()
    if weather_cache['data'] and now - weather_cache['ts'] < 1800:
        return weather_cache['data']
    try:
        geo = httpx.get(
            'https://geocoding-api.open-meteo.com/v1/search',
            params={'name': location, 'count': 1, 'language': 'tr', 'format': 'json'},
            timeout=10
        )
        if geo.status_code != 200 or not geo.json().get('results'):
            weather_cache['data'] = None
            weather_cache['ts'] = now
            return None
        r = geo.json()['results'][0]
        lat, lon, name = r['latitude'], r['longitude'], r.get('name', location)
        w = httpx.get(
            'https://api.open-meteo.com/v1/forecast',
            params={
                'latitude': lat, 'longitude': lon,
                'current': 'temperature_2m,apparent_temperature,weather_code,wind_speed_10m,humidity_2m',
                'daily': 'temperature_2m_max,temperature_2m_min,weather_code',
                'timezone': 'auto', 'forecast_days': 3
            },
            timeout=10
        )
        if w.status_code != 200:
            weather_cache['data'] = None
            weather_cache['ts'] = now
            return None
        wj = w.json()
        current = wj.get('current', {})
        daily = wj.get('daily', {})
        days = []
        if daily.get('time'):
            for i in range(len(daily['time'])):
                days.append({
                    'date': daily['time'][i],
                    'max': daily['temperature_2m_max'][i],
                    'min': daily['temperature_2m_min'][i],
                    'weather_code': daily['weather_code'][i],
                    'weather_text': WEATHER_CODES.get(daily['weather_code'][i], '❓'),
                })
        result = {
            'city': name,
            'temp': current.get('temperature_2m'),
            'feels': current.get('apparent_temperature'),
            'humidity': current.get('humidity_2m'),
            'wind': current.get('wind_speed_10m'),
            'weather_code': current.get('weather_code'),
            'weather_text': WEATHER_CODES.get(current.get('weather_code'), '❓'),
            'forecast': days,
        }
        weather_cache['data'] = result
        weather_cache['ts'] = now
        return result
    except Exception:
        weather_cache['data'] = None
        weather_cache['ts'] = now
        return None

@app.context_processor
def inject_settings():
    return {
        'site_title': get_setting('site_title', 'Homeopati Blog'),
        'site_description': get_setting('site_description', 'Doğal İyileşme Yolculuğu'),
        'primary_color': get_setting('primary_color', '#3d6b4f'),
        'secondary_color': get_setting('secondary_color', '#2d4f3a'),
        'bg_color': get_setting('bg_color', '#ffffff'),
        'text_color': get_setting('text_color', '#333333'),
        'font_heading': get_setting('font_heading', 'Georgia, serif'),
        'font_body': get_setting('font_body', 'sans-serif'),
        'logo_path': get_setting('logo_path', ''),
        'default_fonts': DEFAULT_FONTS,
        'categories': get_categories(),
        'weather_location': get_setting('weather_location', 'İstanbul'),
        'show_weather': get_setting('show_weather', '1'),
        'social_instagram': get_setting('social_instagram', ''),
        'social_twitter': get_setting('social_twitter', ''),
        'social_facebook': get_setting('social_facebook', ''),
        'social_youtube': get_setting('social_youtube', ''),
        'show_social': get_setting('show_social', '1'),
        'sidebar_position': get_setting('sidebar_position', 'right'),
        'posts_per_page': get_setting("posts_per_page", "12"),
        'custom_css': get_setting('custom_css', ''),
        'hero_title': get_setting('hero_title', ''),
        'hero_description': get_setting('hero_description', ''),
        'hero_subtitle': get_setting('hero_subtitle', ''),
        'footer_text': get_setting('footer_text', ''),
        'telegram_url': get_setting('telegram_url', ''),
        'weather_data': fetch_weather(get_setting('weather_location', 'İstanbul')),
        'homepage_sections': __import__('json').loads(get_setting('homepage_sections', '[]')) if get_setting('homepage_sections', '[]') else [],
        'gallery_count': len(get_gallery_images(page=1, per_page=1)[0]) if get_setting('show_gallery', '1') == '1' else 0,
    }

@app.route('/')
def index():
    posts, total = get_posts(page=1, per_page=3)
    return render_template('index.html', posts=posts)

@app.route('/blog')
def blog():
    per_page = int(get_setting("posts_per_page", "12") or "12")
    page = request.args.get('page', 1, type=int)
    q = request.args.get('q', '').strip()
    active_category = request.args.get('category', '').strip()
    posts, total = get_posts(page=page, per_page=per_page, search=q, category=active_category)
    total_pages = (total + per_page - 1) // per_page
    return render_template('blog.html', posts=posts, page=page, total_pages=total_pages,
                           q=q, active_category=active_category, total=total)

@app.route('/post/<slug>')
def post(slug):
    post = get_post(slug)
    if not post:
        flash('Yazı bulunamadı.', 'error')
        return redirect(url_for('index'))
    if not current_user.is_authenticated:
        increment_post_views(post['id'])
    post = dict(post)
    _ALLOWED_TAGS = ['p','br','h1','h2','h3','h4','h5','h6','strong','em','b','i','u','ul','ol','li','a','img','blockquote','code','pre','hr','table','thead','tbody','tr','td','th','span','div','sup','sub','del','figure','figcaption']
    _ALLOWED_ATTRS = {'*': ['class','style'], 'a': ['href','title','target','rel'], 'img': ['src','alt','title','width','height']}
    post['content'] = bleach.clean(post.get('content') or '', tags=_ALLOWED_TAGS, attributes=_ALLOWED_ATTRS, protocols=['http','https','mailto'], strip=True)
    post['views'] = (post.get('views') or 0) + 1
    word_count = len((post.get('content') or '').split())
    read_time = max(1, round(word_count / 200))
    related = get_related_posts(post.get('category', ''), post['id'], limit=3)
    return render_template('post.html', post=post, read_time=read_time, related=related)

@app.route('/search')
def search():
    q = request.args.get('q', '').strip()
    if not q:
        return redirect(url_for('index'))
    page = request.args.get('page', 1, type=int)
    per_page = int(get_setting("posts_per_page", "12") or "12")
    posts, total = search_posts(q, page=page, per_page=per_page)
    total_pages = (total + per_page - 1) // per_page
    return render_template('index.html', posts=posts, page=page, total_pages=total_pages,
                           search_query=q, q=q, active_category='', total=total)

@app.route('/about')
def about():
    return render_template('about.html',
        about_title=get_setting('about_title', 'Hakkımda'),
        about_content=get_setting('about_content', ''))

@app.route('/iletisim', methods=['GET', 'POST'])
def iletisim():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        name = request.form.get('name', '').strip()
        message = request.form.get('message', '').strip()
        if not email or '@' not in email:
            flash('Geçerli bir e-posta adresi girin.', 'error')
            return redirect(url_for('iletisim'))
        # Save to subscribers
        result = add_subscriber(email, name)
        # Save message if provided
        if message:
            conn = get_db()
            conn.execute(
                "CREATE TABLE IF NOT EXISTS contact_messages (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT, name TEXT, message TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
            )
            conn.execute(
                "INSERT INTO contact_messages (email, name, message) VALUES (?, ?, ?)",
                (email, name, message),
            )
            conn.commit()
            conn.close()
        if result == 'exists':
            flash('Bu e-posta zaten kayıtlı. Mesajınız iletildi.', 'success')
        else:
            flash('Mesajınız iletildi! En kısa sürede dönüş yapacağız.', 'success')
        return redirect(url_for('iletisim'))
    return render_template('iletisim.html')

@app.route('/anlati')
def anlati():
    resp = make_response(render_template('anlati.html'))
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return resp

@app.route('/vaka-kayit')
def vaka_kayit_redirect():
    return redirect('/anlati')

@app.route('/favicon.ico')
def favicon_ico():
    return redirect('/uploads/logoaq.png')

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if current_user.is_authenticated:
        return redirect(url_for('admin_dashboard'))
    if request.method == 'POST':
        user = User.authenticate(request.form['username'], request.form['password'])
        if user:
            login_user(user)
            return redirect(url_for('admin_dashboard'))
        flash('Hatalı kullanıcı adı veya şifre.', 'error')
    return render_template('admin/login.html')

@app.route('/admin/logout')
@login_required
def admin_logout():
    logout_user()
    return redirect(url_for('admin_login'))

@app.route('/admin')
@login_required
def admin_dashboard():
    posts, total = get_posts(page=1, per_page=999, published_only=False)
    subscriber_count = get_subscriber_count()
    return render_template('admin/dashboard.html', posts=posts, total=total, subscriber_count=subscriber_count)

@app.route('/gallery')
def gallery():
    page = request.args.get('page', 1, type=int)
    images, total = get_gallery_images(page=page, per_page=50)
    total_pages = (total + 49) // 50
    return render_template('gallery.html', images=images, page=page, total_pages=total_pages)

@app.route('/subscribe', methods=['POST'])
def subscribe():
    email = request.form.get('email', '').strip()
    name = request.form.get('name', '').strip()
    if not email or '@' not in email:
        flash('Geçerli bir e-posta adresi girin.', 'error')
        return redirect(request.referrer or url_for('index'))
    result = add_subscriber(email, name)
    if result == 'exists':
        flash('Bu e-posta zaten kayıtlı.', 'info')
    elif result == 'reactivated':
        flash('Aboneliğiniz yeniden aktifleştirildi!', 'success')
    else:
        flash('Abone olduğunuz için teşekkürler!', 'success')
    return redirect(url_for('index') + '#newsletter')

@app.before_request
def track_pageview():
    if request.path.startswith('/static') or request.path.startswith('/uploads') or request.path.startswith('/admin'):
        return
    if request.path == '/theme.css' or request.path in ('/robots.txt', '/sitemap.xml'):
        return
    record_pageview(request.path, request.remote_addr or '', request.user_agent.string if request.user_agent else '')

@app.route('/admin/categories')
@login_required
def admin_categories():
    cats = get_categories()
    return render_template('admin/categories.html', cats=cats)

@app.route('/admin/category/new', methods=['POST'])
@login_required
def admin_category_new():
    name = request.form.get('name', '').strip()
    if name:
        create_category(name)
        flash('Kategori eklendi.', 'success')
    return redirect(url_for('admin_categories'))

@app.route('/admin/category/<int:id>/edit', methods=['POST'])
@login_required
def admin_category_edit(id):
    name = request.form.get('name', '').strip()
    if name:
        update_category(id, name)
        flash('Kategori güncellendi.', 'success')
    return redirect(url_for('admin_categories'))

@app.route('/admin/category/<int:id>/delete', methods=['POST'])
@login_required
def admin_category_delete(id):
    delete_category(id)
    flash('Kategori silindi.', 'success')
    return redirect(url_for('admin_categories'))

@app.route('/admin/gallery')
@login_required
def admin_gallery():
    page = request.args.get('page', 1, type=int)
    images, total = get_gallery_images(page=page, per_page=50)
    total_pages = (total + 49) // 50
    return render_template('admin/gallery.html', images=images, page=page, total_pages=total_pages)

@app.route('/admin/gallery/upload', methods=['POST'])
@login_required
def admin_gallery_upload():
    files = request.files.getlist('images')
    for f in files:
        if f and f.filename:
            ext = f.filename.rsplit('.', 1)[1].lower() if '.' in f.filename else 'jpg'
            fname = f'gal_{uuid.uuid4().hex[:12]}.{ext}'
            f.save(os.path.join(UPLOAD_DIR, fname))
            title = request.form.get(f'title_{f.filename}', '')
            add_gallery_image(fname, title)
    flash('Resimler yüklendi.', 'success')
    return redirect(url_for('admin_gallery'))

@app.route('/admin/gallery/<int:id>/delete', methods=['POST'])
@login_required
def admin_gallery_delete(id):
    filename = delete_gallery_image(id)
    if filename:
        path = os.path.join(UPLOAD_DIR, filename)
        if os.path.exists(path):
            os.remove(path)
    flash('Resim silindi.', 'success')
    return redirect(url_for('admin_gallery'))

@app.route('/admin/subscribers')
@login_required
def admin_subscribers():
    page = request.args.get('page', 1, type=int)
    items, total = get_subscribers(page=page, per_page=50, active_only=False)
    total_pages = (total + 49) // 50
    return render_template('admin/subscribers.html', subscribers=items, page=page, total_pages=total_pages, total_count=total)

@app.route('/admin/subscriber/<int:id>/toggle', methods=['POST'])
@login_required
def admin_subscriber_toggle(id):
    active = request.form.get('active', '0')
    toggle_subscriber(id, 1 if active == '1' else 0)
    flash('Durum güncellendi.', 'success')
    return redirect(url_for('admin_subscribers'))

@app.route('/admin/subscriber/<int:id>/delete', methods=['POST'])
@login_required
def admin_subscriber_delete(id):
    delete_subscriber(id)
    flash('Abone silindi.', 'success')
    return redirect(url_for('admin_subscribers'))

@app.route('/admin/newsletter', methods=['GET', 'POST'])
@login_required
def admin_newsletter():
    if request.method == 'POST':
        subject = request.form.get('subject', '').strip()
        message = request.form.get('message', '').strip()
        send_to = request.form.get('send_to', 'active')
        if not subject or not message:
            flash('Konu ve mesaj zorunludur.', 'error')
            return redirect(url_for('admin_newsletter'))

        items, total = get_subscribers(per_page=9999, active_only=(send_to != 'all'))
        recipients = [s['email'] for s in items]

        if not recipients:
            flash('Gönderilecek abone bulunamadı.', 'error')
            return redirect(url_for('admin_newsletter'))

        try:
            api_key = os.environ.get('BREVO_API_KEY', '')
            sender_name = get_setting('site_title', 'Zeyna')
            sender_email = 'cevap@zk.net.tr'

            sent = 0
            async def send_one(email):
                nonlocal sent
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.post(
                        'https://api.brevo.com/v3/smtp/email',
                        headers={
                            'api-key': api_key,
                            'Content-Type': 'application/json',
                            'Accept': 'application/json',
                        },
                        json={
                            'sender': {'name': sender_name, 'email': sender_email},
                            'to': [{'email': email}],
                            'subject': subject,
                            'htmlContent': f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{
      background-color: #f4efe1 !important;
      font-family: 'Georgia', Times, serif !important;
      color: #202b22 !important;
      margin: 0 !important;
      padding: 40px 20px !important;
      -webkit-font-smoothing: antialiased;
    }}
    .email-container {{
      max-width: 600px;
      margin: 0 auto;
      background: #fffdf7 !important;
      border: 1px solid #dcd4bd !important;
      border-radius: 14px !important;
      padding: 48px !important;
      box-shadow: 0 4px 20px rgba(0,0,0,0.03) !important;
    }}
    .header {{
      text-align: center !important;
      margin-bottom: 36px !important;
      border-bottom: 1px solid #dcd4bd !important;
      padding-bottom: 24px !important;
    }}
    .logo-img {{
      width: 72px !important;
      height: 72px !important;
      object-fit: contain !important;
      display: inline-block !important;
    }}
    .brand-title {{
      font-family: 'Georgia', Times, serif !important;
      font-size: 24px !important;
      font-weight: 600 !important;
      color: #202b22 !important;
      margin-top: 14px !important;
      margin-bottom: 4px !important;
    }}
    .brand-slogan {{
      font-family: 'Georgia', Times, serif !important;
      font-style: italic !important;
      font-size: 13px !important;
      color: #726f5e !important;
      letter-spacing: 0.05em !important;
    }}
    .content {{
      font-size: 16px !important;
      line-height: 1.85 !important;
      color: #39473b !important;
      margin-bottom: 40px !important;
      white-space: pre-line !important;
    }}
    .signature {{
      font-family: 'Georgia', Times, serif !important;
      font-style: italic !important;
      font-size: 15px !important;
      color: #74906f !important;
      border-top: 1px solid #dcd4bd !important;
      padding-top: 20px !important;
    }}
    .footer {{
      text-align: center !important;
      font-size: 11px !important;
      color: #726f5e !important;
      margin-top: 40px !important;
      line-height: 1.5 !important;
    }}
  </style>
</head>
<body>
  <div class="email-container">
    <div class="header">
      <img class="logo-img" src="https://zeyna.zk.net.tr/uploads/logoaq.png" alt="Zeyna Logo">
      <div class="brand-title">Zeyna Üstün</div>
      <div class="brand-slogan">Bağlantıları gör · Keşfet · Her haline izin ver</div>
    </div>
    
    <div class="content">
      {message.replace('\n', '<br>')}
    </div>
    
    <div class="signature">
      Sevgilerimle,<br>
      <strong>Zeyna Üstün</strong><br>
      <span style="font-size: 12px; color: #726f5e;">Hayatı Okuma Niyetiyle</span>
    </div>
  </div>
  
  <div class="footer">
    Bu e-posta Zeyna bültenine abone olduğunuz için gönderilmiştir.<br>
    © 2026 Zeyna Üstün. Tüm Hakları Saklıdır.
  </div>
</body>
</html>""",
                        }
                    )
                    if resp.status_code in (200, 201):
                        sent += 1

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            for r in recipients:
                loop.run_until_complete(send_one(r))
            loop.close()

            flash(f'{sent}/{len(recipients)} e-posta gönderildi.', 'success')
        except Exception as e:
            flash(f'Gönderim hatası: {str(e)[:200]}', 'error')

        return redirect(url_for('admin_newsletter'))

    return render_template('admin/newsletter.html')

@app.route('/admin/stats')
@login_required
def admin_stats():
    stats = get_pageview_stats(days=30)
    sub_count = get_subscriber_count()
    conn = get_db()
    post_count = conn.execute('SELECT COUNT(*) FROM posts WHERE published=1').fetchone()[0]
    unique_ips = conn.execute('SELECT COUNT(DISTINCT ip) FROM pageviews').fetchone()[0]
    today_count = conn.execute(
        "SELECT COUNT(*) FROM pageviews WHERE DATE(created_at) = DATE('now')"
    ).fetchone()[0]
    top_ips = conn.execute(
        'SELECT ip, COUNT(*) as cnt FROM pageviews GROUP BY ip ORDER BY cnt DESC LIMIT 10'
    ).fetchall()
    recent_visits = conn.execute(
        'SELECT path, ip, created_at FROM pageviews ORDER BY created_at DESC LIMIT 20'
    ).fetchall()
    weekly_daily = conn.execute(
        "SELECT DATE(created_at) as day, COUNT(*) as cnt FROM pageviews WHERE created_at > datetime('now','-7 days') GROUP BY day ORDER BY day DESC"
    ).fetchall()
    conn.close()
    return render_template('admin/stats.html',
        stats=stats, sub_count=sub_count, post_count=post_count,
        unique_ips=unique_ips, today_count=today_count,
        top_ips=top_ips, recent_visits=recent_visits,
        weekly_daily=weekly_daily)

@app.route('/admin/post/new', methods=['GET', 'POST'])
@login_required
def admin_post_new():
    if request.method == 'POST':
        title = request.form['title']
        slug = request.form.get('slug') or slugify(title)
        category = request.form['category']
        content = request.form['content']
        excerpt = request.form.get('excerpt', '')
        published = 1 if request.form.get('published') else 0
        image = save_upload(request.files.get('cover_image'), 'cover')
        create_post(title, slug, category, content, excerpt, published, image=image)
        flash('Yazı oluşturuldu.', 'success')
        return redirect(url_for('admin_dashboard'))
    return render_template('admin/post_form.html', post=None)

@app.route('/admin/post/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def admin_post_edit(id):
    post = get_post_by_id(id)
    if not post:
        flash('Yazı bulunamadı.', 'error')
        return redirect(url_for('admin_dashboard'))
    if request.method == 'POST':
        title = request.form['title']
        slug = request.form.get('slug') or slugify(title)
        category = request.form['category']
        content = request.form['content']
        excerpt = request.form.get('excerpt', '')
        published = 1 if request.form.get('published') else 0
        image = post['image'] if 'image' in post.keys() else ''
        new_image = save_upload(request.files.get('cover_image'), 'cover')
        if new_image:
            delete_upload(image)
            image = new_image
        elif request.form.get('remove_image'):
            delete_upload(image)
            image = ''
        update_post(id, title, slug, category, content, excerpt, published, image=image)
        flash('Yazı güncellendi.', 'success')
        return redirect(url_for('admin_dashboard'))
    return render_template('admin/post_form.html', post=post)

@app.route('/admin/post/<int:id>/delete', methods=['POST'])
@login_required
def admin_post_delete(id):
    post = get_post_by_id(id)
    if post and 'image' in post.keys():
        delete_upload(post['image'])
    delete_post(id)
    flash('Yazı silindi.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/settings', methods=['GET', 'POST'])
@login_required
def admin_settings():
    if request.method == 'POST':
        keys = [
            'site_title', 'site_description', 'primary_color', 'secondary_color',
            'bg_color', 'text_color', 'font_heading', 'font_body',
            'weather_location', 'show_weather',
            'social_instagram', 'social_twitter', 'social_facebook', 'social_youtube', 'show_social',
            'sidebar_position', 'posts_per_page', 'custom_css',
            'hero_title', 'hero_description', 'hero_subtitle', 'footer_text',
            'hero_color_start', 'hero_color_end',
            'card_radius', 'card_shadow', 'thumb_color',
            'telegram_url',
        ]
        for key in keys:
            val = request.form.get(key, '')
            set_setting(key, val)
        logo = request.files.get('logo')
        if logo and logo.filename:
            ext = logo.filename.rsplit('.', 1)[1].lower() if '.' in logo.filename else 'png'
            fname = f'logo_{uuid.uuid4().hex[:8]}.{ext}'
            logo.save(os.path.join(UPLOAD_DIR, fname))
            old = get_setting('logo_path', '')
            if old:
                old_path = os.path.join(UPLOAD_DIR, old)
                if os.path.exists(old_path):
                    os.remove(old_path)
            set_setting('logo_path', fname)
        global weather_cache
        weather_cache = {'data': None, 'ts': 0}
        flash('Ayarlar kaydedildi.', 'success')
        return redirect(url_for('admin_settings'))
    return render_template('admin/settings.html',
        site_title_val=get_setting('site_title', 'Homeopati Blog'),
        site_description_val=get_setting('site_description', 'Doğal İyileşme Yolculuğu'),
        primary_color_val=get_setting('primary_color', '#3d6b4f'),
        secondary_color_val=get_setting('secondary_color', '#2d4f3a'),
        bg_color_val=get_setting('bg_color', '#ffffff'),
        text_color_val=get_setting('text_color', '#333333'),
        font_heading_val=get_setting('font_heading', 'Georgia, serif'),
        font_body_val=get_setting('font_body', 'sans-serif'),
        logo_path_val=get_setting('logo_path', ''),
        weather_location_val=get_setting('weather_location', 'İstanbul'),
        show_weather_val=get_setting('show_weather', '1'),
        social_instagram_val=get_setting('social_instagram', ''),
        social_twitter_val=get_setting('social_twitter', ''),
        social_facebook_val=get_setting('social_facebook', ''),
        social_youtube_val=get_setting('social_youtube', ''),
        show_social_val=get_setting('show_social', '1'),
        sidebar_position_val=get_setting('sidebar_position', 'right'),
        posts_per_page_val=get_setting("posts_per_page", "12"),
        hero_title_val=get_setting('hero_title', ''),
        hero_description_val=get_setting('hero_description', ''),
        hero_subtitle_val=get_setting('hero_subtitle', ''),
        footer_text_val=get_setting('footer_text', ''),
        hero_color_start_val=get_setting('hero_color_start', '#1e5631'),
        hero_color_end_val=get_setting('hero_color_end', '#74c69d'),
        card_radius_val=get_setting('card_radius', '14px'),
        card_shadow_val=get_setting('card_shadow', 'sm'),
        thumb_color_val=get_setting('thumb_color', '#2d6a4f'),
        telegram_url_val=get_setting('telegram_url', ''),
        custom_css_val=get_setting('custom_css', ''),
        color_presets=COLOR_PRESETS,
        default_fonts=DEFAULT_FONTS,
        hero_gradients=[
            {'name': 'Orman Yeşili', 'start': '#1e5631', 'end': '#74c69d'},
            {'name': 'Derin Yeşil', 'start': '#0a3d20', 'end': '#2d6a4f'},
            {'name': 'Deniz Mavisi', 'start': '#1a3c5e', 'end': '#4a90d9'},
            {'name': 'Gün Batımı', 'start': '#c0392b', 'end': '#f39c12'},
            {'name': 'Mor Gece', 'start': '#2c1654', 'end': '#7b2ff7'},
            {'name': 'Sahil', 'start': '#1d6fa4', 'end': '#48cae4'},
            {'name': 'Güz', 'start': '#7d3c10', 'end': '#d4ac0d'},
            {'name': 'Gül', 'start': '#8e0a3d', 'end': '#e91e8c'},
            {'name': 'Antrasit', 'start': '#1a1a2e', 'end': '#4a4a72'},
            {'name': 'Zeytin', 'start': '#3b4a1a', 'end': '#8fa839'},
        ],
    )

@app.route('/admin/change-password', methods=['POST'])
@login_required
def admin_change_password():
    new_pass = request.form.get('new_password', '')
    if len(new_pass) < 4:
        flash('Şifre en az 4 karakter olmalı.', 'error')
        return redirect(url_for('admin_settings'))
    conn = get_db()
    conn.execute('UPDATE users SET password_hash=? WHERE id=?',
                 (generate_password_hash(new_pass), current_user.id))
    conn.commit()
    conn.close()
    flash('Şifre değiştirildi.', 'success')
    return redirect(url_for('admin_settings'))

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_file(os.path.join(UPLOAD_DIR, filename))

AI_JOBS_DIR = os.path.join(UPLOAD_DIR, 'ai_jobs')
os.makedirs(AI_JOBS_DIR, exist_ok=True)

_gen_log = logging.getLogger('ai_gen')
OLLAMA_HOST = "https://insightmap.tr"
OLLAMA_VERIFY = False

def _ollama_post(payload, timeout=180):
    resp = httpx.post(f"{OLLAMA_HOST}/api/ollama/generate", json=payload, timeout=timeout, verify=OLLAMA_VERIFY)
    resp.raise_for_status()
    return resp.json()

def _generate_content(job_id, topic, tone, length, url, file_path, orig_filename):
    try:
        context_parts = []
        if url:
            text = ""
            try:
                resp = httpx.post(f"{OLLAMA_HOST}/api/ollama/generate", json={
                    "model": "reader-lm:latest",
                    "prompt": url,
                    "stream": False,
                    "options": {"temperature": 0.1, "num_predict": 4096}
                }, timeout=60, verify=OLLAMA_VERIFY)
                if resp.status_code == 200:
                    text = resp.json().get("response", "").strip()[:4000]
            except:
                pass
            if not text:
                try:
                    jina_key = os.environ.get("JINA_API_KEY", "")
                    if jina_key:
                        resp = httpx.get(f"https://r.jina.ai/{url}", timeout=60,
                            headers={"Authorization": f"Bearer {jina_key}"}, follow_redirects=True)
                        if resp.status_code == 200:
                            text = resp.text.strip()[:4000]
                except Exception as e:
                    _gen_log.error(f'url fetch jina error: {e}')
            if not text:
                try:
                    resp = httpx.get(url, timeout=30, follow_redirects=True)
                    if resp.status_code == 200:
                        text = re.sub(r'<[^>]+>', '', resp.text)[:4000]
                        text = '\n'.join(line for line in text.split('\n') if line.strip())[:4000]
                except Exception as e:
                    _gen_log.error(f'url fetch fallback error: {e}')
            if text:
                context_parts.append(f'[URL: {url}]\n{text}')

        if file_path and os.path.exists(file_path):
            try:
                ext = file_path.rsplit('.', 1)[1].lower()
                text = ''
                if ext == 'pdf':
                    import pdfplumber
                    with pdfplumber.open(file_path) as pdf:
                        text = '\n'.join(p.page_text or '' for p in pdf.pages)[:4000]
                elif ext in ('jpg', 'jpeg', 'png', 'webp'):
                    with open(file_path, 'rb') as imgf:
                        b64 = base64.b64encode(imgf.read()).decode()
                    data = _ollama_post({"model": "glm-ocr:latest", "prompt": "Bu gorseldeki metni oldugu gibi cikar.",
                        "images": [b64], "options": {"temperature": 0.1}}, timeout=120)
                    text = data.get("response", "").strip()[:4000]
                if text:
                    context_parts.append(f'[Dosya: {orig_filename}]\n{text}')
                os.remove(file_path)
            except Exception as e:
                _gen_log.error(f'file error: {e}')

        context_text = '\n\n---\n\n'.join(context_parts)[:8000]
        sys_prompt = 'Sen profesyonel blog yazarisin. SADECE Turkce cevap ver, baska dil kullanma. Turkce, akici, SEO uyumlu icerik uret. Baslik ve alt basliklar kullan. Asla Cince veya baska bir dilde yazma.'
        if context_text:
            sys_prompt += f'\n\nIcerigini asagidaki kaynaktan yararlanarak olustur:\n{context_text[:6000]}'
        prompt = f'{topic} hakkinda {tone} tonda, {length} kelimelik SEO uyumlu blog yazisi yaz.'

        _gen_log.info(f'generating for: {topic[:40]}')
        data = _ollama_post({'model': 'qwen2.5:14b', 'system': sys_prompt, 'prompt': prompt,
            'stream': False, 'options': {'temperature': 0.7, 'num_predict': 2048}}, timeout=180)
        result = data.get('response', '')
        _gen_log.info(f'generated {len(result)} chars')
        # Report token usage to PulseCapture
        try:
            import httpx
            tokens = max((len(topic) + len(result)) // 4, 1)
            httpx.post('http://172.16.16.215:8004/ai/report-usage',
                data={'email': 'zeyna@admin.tr', 'tokens': str(tokens)},
                timeout=5,
            )
        except:
            pass
    except Exception as e:
        result = f'[HATA] {str(e)}'
        _gen_log.error(f'failed: {e}', exc_info=True)

    with open(os.path.join(AI_JOBS_DIR, f'{job_id}.json'), 'w') as f:
        json.dump({'status': 'done', 'result': result, 'topic': topic}, f)
    _gen_log.info('job saved')

@app.route('/admin/ai-content', methods=['GET', 'POST'])
@login_required
def admin_ai_content():
    job_id = request.args.get('job', '')
    if job_id:
        job_file = os.path.join(AI_JOBS_DIR, f'{job_id}.json')
        if os.path.exists(job_file):
            with open(job_file) as f:
                job = json.load(f)
            if job['status'] == 'done':
                return render_template('admin/ai_content.html', generated=job.get('result',''), topic=job.get('topic',''), processing=False, job_id='')
        return render_template('admin/ai_content.html', processing=True, job_id=job_id, generated='', topic='')

    if request.method == 'POST':
        topic = request.form.get('topic', '').strip()
        tone = request.form.get('tone', 'profesyonel')
        length = request.form.get('length', '500')
        url = request.form.get('url', '').strip()
        uploaded_file = request.files.get('file')
        job_id = uuid.uuid4().hex[:12]
        file_path = None

        if uploaded_file and uploaded_file.filename:
            ext = uploaded_file.filename.rsplit('.', 1)[1].lower() if '.' in uploaded_file.filename else ''
            file_path = os.path.join(UPLOAD_DIR, f'job_{job_id}.{ext}')
            uploaded_file.save(file_path)

        with open(os.path.join(AI_JOBS_DIR, f'{job_id}.json'), 'w') as f:
            json.dump({'status': 'pending'}, f)

        t = threading.Thread(target=_generate_content, args=(job_id, topic, tone, length, url, file_path, uploaded_file.filename if uploaded_file else ''))
        t.daemon = True
        t.start()
        return render_template('admin/ai_content.html', processing=True, job_id=job_id, generated='', topic=topic)

    history = []
    try:
        for f in sorted(os.listdir(AI_JOBS_DIR), reverse=True)[:20]:
            fp = os.path.join(AI_JOBS_DIR, f)
            if f.endswith('.json') and os.path.isfile(fp):
                with open(fp) as jf:
                    data = json.load(jf)
                if data.get('status') == 'done':
                    history.append({'id': f[:-5], 'topic': data.get('topic',''), 'preview': data.get('result','')[:100]})
    except:
        pass
    return render_template('admin/ai_content.html', processing=False, generated='', job_id='', history=history)

@app.route('/admin/ai-content/clear', methods=['POST'])
@login_required
def admin_ai_content_clear():
    if os.path.exists(AI_JOBS_DIR):
        shutil.rmtree(AI_JOBS_DIR)
        os.makedirs(AI_JOBS_DIR, exist_ok=True)
    flash('Gecmis uretimler temizlendi.', 'success')
    return redirect(url_for('admin_ai_content'))

IMAGE_SERVICE_URL = os.environ.get('IMAGE_SERVICE_URL', 'http://172.16.16.215:8001')

@app.route('/admin/ai-image', methods=['GET', 'POST'])
@login_required
def admin_ai_image():
    images = []
    img_dir = os.path.join(UPLOAD_DIR, 'ai_images')
    os.makedirs(img_dir, exist_ok=True)
    for f in sorted(os.listdir(img_dir), reverse=True)[:20]:
        if f.endswith(('.png', '.jpg', '.webp')):
            info_path = os.path.join(img_dir, f.rsplit('.', 1)[0] + '.json')
            info = {}
            if os.path.exists(info_path):
                with open(info_path) as jf:
                    info = json.load(jf)
            images.append({'file': f, 'prompt': info.get('prompt', ''), 'time': info.get('time', '')})

    if request.method == 'POST':
        prompt = request.form.get('prompt', '').strip()
        style = request.form.get('style', 'photorealistic')
        width = int(request.form.get('width', 1024))
        height = int(request.form.get('height', 1024))
        if not prompt:
            flash('Gorsel promptu gerekli.', 'error')
            return redirect(url_for('admin_ai_image'))

        job_id = uuid.uuid4().hex[:12]
        img_path = os.path.join(img_dir, f'{job_id}.png')
        info_path = os.path.join(img_dir, f'{job_id}.json')

        try:
            resp = httpx.post(
                f"{IMAGE_SERVICE_URL}/generate",
                json={
                    "prompt": prompt,
                    "model": "Z-Image-Turbo",
                    "steps": 8,
                    "enhance_prompt": False,
                    "width": width,
                    "height": height,
                    "style": style,
                },
                timeout=30,
            )
            resp.raise_for_status()
            gen_id = resp.json().get('id')

            import time as _time
            done = False
            for _ in range(60):
                _time.sleep(4)
                try:
                    h = httpx.get(f"{IMAGE_SERVICE_URL}/history?page=1&page_size=5", timeout=10)
                    for item in h.json().get('items', []):
                        if item['id'] == gen_id:
                            if item['status'] == 'completed' and item.get('output_file'):
                                img_data = httpx.get(f"{IMAGE_SERVICE_URL}/image/{gen_id}", timeout=15)
                                if img_data.status_code == 200:
                                    with open(img_path, 'wb') as f:
                                        f.write(img_data.content)
                                    with open(info_path, 'w') as f:
                                        json.dump({'prompt': prompt, 'time': _time.strftime('%Y-%m-%d %H:%M')}, f, ensure_ascii=False)
                                    done = True
                            elif item['status'] == 'failed':
                                flash('Gorsel uretimi basarisiz: ' + str(item.get('error_message','')), 'error')
                                return redirect(url_for('admin_ai_image'))
                            break
                except:
                    pass
                if done:
                    break

            if not done:
                flash('Gorsel uretimi zaman asimina ugradi.', 'error')
            else:
                flash('Gorsel olusturuldu!', 'success')
        except Exception as e:
            flash(f'Image service hatasi: {e}', 'error')

        return redirect(url_for('admin_ai_image'))

    return render_template('admin/ai_image.html', images=images)

@app.route('/admin/ai-image/file/<path:filename>')
@login_required
def ai_image_file(filename):
    return send_from_directory(os.path.join(UPLOAD_DIR, 'ai_images'), filename)

@app.route('/robots.txt')
def robots_txt():
    from flask import Response
    lines = [
        'User-agent: *',
        'Allow: /',
        'Disallow: /admin',
        f'Sitemap: {request.url_root.rstrip("/")}/sitemap.xml',
    ]
    return Response('\n'.join(lines) + '\n', mimetype='text/plain')

@app.route('/sitemap.xml')
def sitemap_xml():
    from flask import Response
    base = request.url_root.rstrip('/')
    posts, _ = get_posts(page=1, per_page=10000)
    urls = [
        (f'{base}/', ''),
        (f'{base}/about', ''),
        (f'{base}/blog', ''),
        (f'{base}/gallery', ''),
        (f'{base}/iletisim', ''),
        (f'{base}/anlati', ''),
        (f'{base}/s/yaklasimim', ''),
        (f'{base}/s/danismanlik', ''),
    ]
    for p in posts:
        lastmod = (p['updated_at'] or '')[:10]
        urls.append((f'{base}/post/{p["slug"]}', lastmod))
    items = []
    for loc, lastmod in urls:
        lm = f'<lastmod>{lastmod}</lastmod>' if lastmod else ''
        items.append(f'<url><loc>{loc}</loc>{lm}</url>')
    xml = ('<?xml version="1.0" encoding="UTF-8"?>'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
           + ''.join(items) + '</urlset>')
    return Response(xml, mimetype='application/xml')


@app.route('/rss.xml')
def rss_feed():
    from flask import Response
    base = request.url_root.rstrip('/')
    posts, _ = get_posts(page=1, per_page=50)
    items = []
    for p in posts:
        link = f'{base}/post/{p["slug"]}'
        pub = p['created_at'] or ''
        items.append(
            '<item>'
            f'<title>{_escape_xml(p["title"])}</title>'
            f'<link>{link}</link>'
            f'<guid>{link}</guid>'
            f'<description>{_escape_xml(p["excerpt"] or "")}</description>'
            f'<pubDate>{pub}</pubDate>'
            '</item>'
        )
    rss = ('<?xml version="1.0" encoding="UTF-8"?>'
           '<rss version="2.0"><channel>'
           f'<title>{_escape_xml(get_setting("site_title", "Zeyna Üstün"))}</title>'
           f'<link>{base}/</link>'
           f'<description>{_escape_xml(get_setting("site_description", ""))}</description>'
           '<language>tr</language>'
           + ''.join(items) + '</channel></rss>')
    return Response(rss, mimetype='application/rss+xml')


def _escape_xml(s):
    return (s or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')

@app.route('/theme.css')
def theme_css():
    custom = get_setting('custom_css', '')
    css = f'''/* Zeyna Üstün · Hayatı Okuma — design tokens
   Sukunet > canlilik. Marka paletinin kontrast-dogrulanmis hali.
   Tum stil kararlari bu custom property'lerden beslenir; style.css harici
   hardcoded renk/olcu kullanmaz. */
:root {{
   /* COLOR — Novocura paleti, --ed-* semasina eslenmis */
  --bg: #F6F1E7;            --bg-rgb: 246,241,231;      /* parchment */
  --surface: #FBF8F0;      --surface-rgb: 251,248,240;
  --bg-deep: #EAE2D0;      --bg-deep-rgb: 234,226,208;  /* sand */
  --dark: #2C4A3B;         --dark-rgb: 44,74,59;        /* forest */
  --dark-soft: #1B2E23;    --dark-soft-rgb: 27,46,35;   /* forest-deep */
  --ink: #3A4A40;          --ink-rgb: 58,74,64;         /* govde */
  --ink-soft: #4E5E54;     --ink-soft-rgb: 78,94,84;    /* ikincil (kontrast düzeltilmis) */
  --muted: #55625A;        --muted-rgb: 85,98,90;       /* AA 5.4:1 */
  --on-dark: #F6F1E7;      --on-dark-rgb: 246,241,231;
  --on-dark-muted: #C7D0BE; --on-dark-muted-rgb: 199,208,190;
  --accent: #7A5C35;       /* metin ve link (AA >= 4.5) */  --accent-rgb: 122,92,53;
  --accent-bright: #B08D57;/* brass — SADECE dekor: cizgi, ikon, rozet */  --accent-bright-rgb: 176,141,87;
  --sage: #C7D0BE;         --sage-rgb: 199,208,190;     /* yumusak dekor */
  --success: #4d7a52;      --success-rgb: 77,122,82;
  --error: #a3403a;        --error-rgb: 163,64,58;
  --line: rgba(58, 74, 64, 0.16);
  --line-soft: rgba(58, 74, 64, 0.08);

  /* TYPOGRAPHY */
  --font-display: "Cormorant Garamond", Georgia, serif;
  --font-body: "Montserrat", system-ui, sans-serif;
  --step--1: clamp(.875rem, .83rem + .2vw, .95rem);
  --step-0: clamp(1.0625rem, 1rem + .25vw, 1.15rem);
  --step-1: clamp(1.3rem, 1.15rem + .6vw, 1.6rem);
  --step-2: clamp(1.75rem, 1.4rem + 1.4vw, 2.6rem);
  --step-3: clamp(2.4rem, 1.7rem + 3vw, 4.5rem);
  --step-4: clamp(3rem, 1.8rem + 6vw, 7rem);

  /* SPACING */
  --s1: .5rem;
  --s2: 1rem;
  --s3: 1.5rem;
  --s4: 2.5rem;
  --s5: 4rem;
  --s6: 6rem;
  --s7: 9rem;

  /* LAYOUT */
  --measure: 64ch;
  --radius: 2px;
  --radius-lg: 16px;

  /* MOTION */
  --ease: cubic-bezier(.22, .61, .36, 1);
  --dur: .6s;
}}

/* ---- DARK MODE (ayni AA esikleri) ---- */
[data-theme="dark"] {{
  --bg: #121A15;            --bg-rgb: 18,26,21;
  --surface: #1A241D;      --surface-rgb: 26,36,29;
  --bg-deep: #0E140F;      --bg-deep-rgb: 14,20,15;
  --dark: #0A0F0B;         --dark-rgb: 10,15,11;
  --dark-soft: #1B2E23;    --dark-soft-rgb: 27,46,35;
  --ink: #F6F1E7;          --ink-rgb: 246,241,231;
  --ink-soft: #C7D0BE;     --ink-soft-rgb: 199,208,190;
  --muted: #B9C2B6;        --muted-rgb: 185,194,182;    /* koyu zemin AA */
  --on-dark: #F6F1E7;      --on-dark-rgb: 246,241,231;
  --on-dark-muted: #C7D0BE; --on-dark-muted-rgb: 199,208,190;
  --accent: #D8BC84;    /* koyu zeminde AA metin vurgusu */  --accent-rgb: 216,188,132;
  --accent-bright: #B08D57;  --accent-bright-rgb: 176,141,87;
  --sage: #C7D0BE;     --sage-rgb: 199,208,190;
  --success: #5ea86a;  --success-rgb: 94,168,106;
  --error: #b35a52;    --error-rgb: 179,90,82;
  --line: rgba(246, 241, 231, 0.16);
  --line-soft: rgba(246, 241, 231, 0.08);
}}

/* ---- legacy aliases (Jinja template inlinelari + eski style.css)
   :root ve dark-mode ortak tek blockta; degerler var() ile takip eder. ---- */
:root, html[data-theme="dark"] {{
  --primary: var(--accent);
  --secondary: var(--sage);
  --text: var(--ink);
  --font-heading: var(--font-display);
  --gold: var(--accent-bright);
  --gold-soft: #EAE2D0;
  --ink-2: var(--ink-soft);
  --paper: var(--bg);
  --paper-2: var(--surface);
  --border: var(--line);

  /* legacy --ed-* (eski editorial template'ler) */
  --ed-bg: var(--bg);
  --ed-bg-deep: var(--bg-deep);
  --ed-surface: var(--surface);
  --ed-ink: var(--ink);
  --ed-ink-soft: var(--ink-soft);
  --ed-muted: var(--muted);
  --ed-faint: var(--muted);
  --ed-line: var(--line);
  --ed-line-soft: var(--line-soft);
  --ed-accent: var(--accent);
  --ed-accent-deep: var(--accent);
  --ed-accent-bright: var(--accent-bright);
  --ed-sage: var(--sage);
  --ed-dark: var(--dark);
  --ed-dark-soft: var(--dark-soft);
  --ed-dark-text: var(--on-dark);
  --fs-hero: var(--step-4);
  --fs-hero-slogan: var(--step-1);
  --fs-h2: var(--step-2);
  --fs-h3: var(--step-1);
  --fs-body: var(--step-0);
  --space-xs: var(--s1);
  --space-sm: var(--s2);
  --space-md: var(--s3);
  --space-lg: var(--s4);
  --space-xl: var(--s5);
  --space-2xl: var(--s6);
  --container: 1320px;
  --container-narrow: 760px;
  --gutter: clamp(1.25rem, 4vw, 3rem);
  --ease-editorial: var(--ease);
  --dur-slow: 900ms;
  --dur-med: var(--dur);
}}

/* ---- admin ozel css (custom_css) ---- */
{custom}'''
    resp = Response(css, mimetype='text/css')
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return resp

@app.route('/static/<path:path>')
def static_files(path):
    return send_from_directory(os.path.join(app.root_path, '..', 'src'), path)

if __name__ == '__main__':
    init_db()
    init_portal_db()
    app.run(host='0.0.0.0', port=5000, debug=True)

@app.route('/admin/portal-users')
@login_required
def admin_portal_users():
    from app.portal import get_all_portal_users
    users = get_all_portal_users()
    return render_template('admin/portal_users.html', users=users)


@app.route('/admin/portal-user/<int:user_id>/delete', methods=['POST'])
@login_required
def admin_portal_user_delete(user_id):
    from app.portal import delete_portal_user
    delete_portal_user(user_id)
    flash('Kullanici silindi.', 'success')
    return redirect(url_for('admin_portal_users'))


@app.route('/admin/homepage', methods=['GET', 'POST'])
@login_required
def admin_homepage():
    from app.portal import get_homepage_sections, set_homepage_sections
    if request.method == 'POST':
        sections = []
        titles = request.form.getlist('section_title[]')
        contents = request.form.getlist('section_content[]')
        types = request.form.getlist('section_type[]')
        for i in range(len(titles)):
            title_val = titles[i].strip() if i < len(titles) else ''
            content_val = contents[i].strip() if i < len(contents) else ''
            type_val = types[i] if i < len(types) else 'text'
            if title_val or content_val:
                sections.append({
                    'title': title_val,
                    'content': content_val,
                    'type': type_val,
                })
        set_homepage_sections(sections)
        flash('Ana sayfa guncellendi.', 'success')
        return redirect(url_for('admin_homepage'))
    sections = get_homepage_sections()
    return render_template('admin/homepage.html', sections=sections)


@app.route('/admin/tenants')
@login_required
def admin_tenants_list():
    try:
        import httpx
        # Get session cookie from admin's browser
        resp = httpx.get('http://172.16.16.215:8004/admin/tenants', timeout=10)
        if resp.status_code == 200:
            import re
            # Extract tenant data from the page (simple approach)
            return resp.text
    except:
        pass
    return render_template('admin/tenants_list.html', tenants=[])


@app.route('/admin/tenants/create', methods=['GET', 'POST'])
@login_required
def admin_tenants_create():
    if request.method == 'POST':
        code = request.form.get('code', '').strip()
        domain = request.form.get('domain', '').strip()
        email = request.form.get('email', '').strip()
        name = request.form.get('name', '').strip()
        telegram = request.form.get('telegram_token', '').strip()

        if not code or not domain:
            flash('Musteri kodu ve domain zorunludur.', 'error')
            return redirect(url_for('admin_tenants_list'))

        try:
            import httpx
            resp = httpx.post(
                'http://172.16.16.215:8004/admin/tenants/create',
                data={
                    'code': code,
                    'domain': domain,
                    'owner_email': email or f'{code}@{domain}',
                    'owner_name': name or code,
                    'telegram_token': telegram,
                },
                timeout=60,
            )
            if resp.status_code == 302:
                flash(f'Musteri {code} basariyla olusturuldu: https://{domain}', 'success')
            else:
                flash(f'Hata: {resp.status_code}', 'error')
        except Exception as e:
            flash(f'Sunucu hatasi: {str(e)[:100]}', 'error')

        return redirect(url_for('admin_tenants_list'))

    return render_template('admin/tenants_create.html')


@app.route('/api/reset-password', methods=['POST'])
def api_reset_password():
    data = request.get_json()
    email = data.get('email', '')
    password = data.get('password', '')
    if not email or not password:
        return {'error': 'missing fields'}
    from werkzeug.security import generate_password_hash
    from app.models import get_db
    conn = get_db()
    conn.execute('UPDATE portal_users SET password_hash=? WHERE email=?', (generate_password_hash(password), email))
    conn.commit()
    conn.close()
    return {'ok': True}

# ── Custom Pages (görsel sayfa oluşturucu) ──────────────────────────────────

@app.route('/admin/sayfalar')
@login_required
def admin_sayfalar():
    conn = get_db()
    pages = conn.execute("SELECT * FROM custom_pages ORDER BY updated_at DESC").fetchall()
    conn.close()
    return render_template('admin/sayfalar.html', pages=[dict(p) for p in pages])

@app.route('/admin/sayfalar/yeni', methods=['GET', 'POST'])
@login_required
def admin_sayfa_yeni():
    if request.method == 'POST':
        slug = request.form.get('slug', '').strip()
        title = request.form.get('title', '').strip()
        if not slug or not title:
            flash('Slug ve başlık zorunlu', 'error')
            return redirect(url_for('admin_sayfa_yeni'))
        conn = get_db()
        conn.execute("INSERT INTO custom_pages (slug, title) VALUES (?, ?)", (slug, title))
        conn.commit()
        conn.close()
        return redirect(url_for('admin_sayfa_edit', slug=slug))
    return render_template('admin/sayfa_form.html', page=None)

@app.route('/admin/sayfalar/<slug>/edit')
@login_required
def admin_sayfa_edit(slug):
    conn = get_db()
    page = conn.execute("SELECT * FROM custom_pages WHERE slug=?", (slug,)).fetchone()
    conn.close()
    if not page:
        flash('Sayfa bulunamadı', 'error')
        return redirect(url_for('admin_sayfalar'))
    return render_template('admin/sayfa_editor.html', page=dict(page))

@app.route('/admin/sayfalar/<slug>/save', methods=['POST'])
@login_required
def admin_sayfa_save(slug):
    data = request.get_json() or {}
    blocks = json.dumps(data.get('blocks', []))
    title = data.get('title', '')
    published = data.get('is_published', 0)
    conn = get_db()
    conn.execute("UPDATE custom_pages SET blocks_json=?, title=?, is_published=?, updated_at=CURRENT_TIMESTAMP WHERE slug=?",
                 (blocks, title, int(published), slug))
    conn.commit()
    conn.close()
    return {'ok': True}

@app.route('/admin/sayfalar/<slug>/delete', methods=['POST'])
@login_required
def admin_sayfa_delete(slug):
    conn = get_db()
    conn.execute("DELETE FROM custom_pages WHERE slug=?", (slug,))
    conn.commit()
    conn.close()
    flash('Sayfa silindi', 'success')
    return redirect(url_for('admin_sayfalar'))

@app.route('/s/<slug>')
def custom_page(slug):
    conn = get_db()
    page = conn.execute("SELECT * FROM custom_pages WHERE slug=? AND is_published=1", (slug,)).fetchone()
    conn.close()
    if not page:
        abort(404)
    page = dict(page)
    blocks = json.loads(page['blocks_json']) if page['blocks_json'] else []
    return render_template('custom_page.html', page=page, blocks=blocks)


# ── Hakkımda düzenleme ─────────────────────────────────────────────────────
@app.route('/admin/about', methods=['GET', 'POST'])
@login_required
def admin_about():
    if request.method == 'POST':
        set_setting('about_title', request.form.get('about_title', '').strip())
        set_setting('about_content', request.form.get('about_content', '').strip())
        flash('Hakkımda sayfası güncellendi.', 'success')
        return redirect(url_for('admin_about'))
    return render_template('admin/about_edit.html',
        about_title=get_setting('about_title', 'Hakkımda'),
        about_content=get_setting('about_content', ''))
