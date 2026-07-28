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
import shutil
import base64
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, send_file, Response
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash
from app.models import init_db, User, get_posts, get_post, get_post_by_id, search_posts
from app.portal import portal_bp, init_portal_db
from app.models import create_post, update_post, delete_post
from app.models import get_setting, set_setting, slugify, get_categories
from app.models import get_category, create_category, update_category, delete_category
from app.models import get_gallery_images, add_gallery_image, delete_gallery_image
from app.models import get_subscribers, add_subscriber, toggle_subscriber, delete_subscriber, get_subscriber_count
from app.models import get_pageview_stats, record_pageview, get_db

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), 'data', 'uploads')
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)
app.config.update(
)
app.register_blueprint(portal_bp)
app.secret_key = os.environ.get('SECRET_KEY', 'zeyna-homeopathy-secret-2026')
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
        'footer_text': get_setting('footer_text', ''),
        'weather_data': fetch_weather(get_setting('weather_location', 'İstanbul')),
        'homepage_sections': __import__('json').loads(get_setting('homepage_sections', '[]')) if get_setting('homepage_sections', '[]') else [],
    }

@app.route('/')
def index():
    per_page = int(get_setting("posts_per_page", "12") or "12")
    page = request.args.get('page', 1, type=int)
    posts, total = get_posts(page=page, per_page=per_page)
    total_pages = (total + per_page - 1) // per_page
    return render_template('index.html', posts=posts, page=page, total_pages=total_pages)

@app.route('/post/<slug>')
def post(slug):
    post = get_post(slug)
    if not post:
        flash('Yazı bulunamadı.', 'error')
        return redirect(url_for('index'))
    post = dict(post)
    return render_template('post.html', post=post)

@app.route('/search')
def search():
    q = request.args.get('q', '').strip()
    if not q:
        return redirect(url_for('index'))
    page = request.args.get('page', 1, type=int)
    per_page = int(get_setting("posts_per_page", "12") or "12")
    posts, total = search_posts(q, page=page, per_page=per_page)
    total_pages = (total + per_page - 1) // per_page
    return render_template('index.html', posts=posts, page=page, total_pages=total_pages, search_query=q)

@app.route('/about')
def about():
    return render_template('about.html')

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
    return render_template('admin/dashboard.html', posts=posts, total=total)

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
    if request.path == '/theme.css':
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
            api_key = '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'
            sender_name = get_setting('site_title', 'Homeopati Blog')
            sender_email = 'zafer@zaferkaraca.net'

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
                            'htmlContent': message.replace('\n', '<br>'),
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
    conn.close()
    return render_template('admin/stats.html', stats=stats, sub_count=sub_count, post_count=post_count)

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
        create_post(title, slug, category, content, excerpt, published)
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
        update_post(id, title, slug, category, content, excerpt, published)
        flash('Yazı güncellendi.', 'success')
        return redirect(url_for('admin_dashboard'))
    return render_template('admin/post_form.html', post=post)

@app.route('/admin/post/<int:id>/delete', methods=['POST'])
@login_required
def admin_post_delete(id):
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
            'hero_title', 'hero_description', 'footer_text',
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
        custom_css_val=get_setting('custom_css', ''),
        hero_title_val=get_setting('hero_title', ''),
        hero_description_val=get_setting('hero_description', ''),
        footer_text_val=get_setting('footer_text', ''),
        color_presets=COLOR_PRESETS,
        default_fonts=DEFAULT_FONTS,
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
        sys_prompt = 'Sen profesyonel blog yazarisin. Turkce, akici, SEO uyumlu icerik uret. Baslik ve alt basliklar kullan.'
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

@app.route('/theme.css')
def theme_css():
    primary = get_setting('primary_color', '#3d6b4f')
    secondary = get_setting('secondary_color', '#2d4f3a')
    bg = get_setting('bg_color', '#ffffff')
    text = get_setting('text_color', '#333333')
    font_h = get_setting('font_heading', 'Georgia, serif')
    font_b = get_setting('font_body', 'sans-serif')
    custom = get_setting('custom_css', '')
    css = f'''/* Dynamic theme */
:root {{
  --primary: {primary};
  --secondary: {secondary};
  --bg: {bg};
  --text: {text};
  --font-heading: {font_h};
  --font-body: {font_b};
  --green: {primary};
  --green-dark: {secondary};
}}
body {{ font-family: var(--font-body); color: var(--text); background: var(--bg); }}
h1, h2, h3, h4, h5, h6, .logo, .post-title, .hero h1 {{ font-family: var(--font-heading); }}
a {{ color: var(--primary); }}
.post-card:hover {{ border-color: var(--primary); }}
.post-read {{ color: var(--primary); }}
.site-footer {{ background: var(--secondary); }}
{custom}
'''
    return Response(css, mimetype='text/css')

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
            if titles[i].strip():
                sections.append({
                    'title': titles[i].strip(),
                    'content': contents[i].strip() if i < len(contents) else '',
                    'type': types[i] if i < len(types) else 'text',
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
