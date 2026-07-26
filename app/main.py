import os
import uuid
import markdown
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, send_file
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from app.models import init_db, User, get_posts, get_post, get_post_by_id
from app.models import create_post, update_post, delete_post
from app.models import get_setting, set_setting, slugify, get_categories
from app.models import get_category, create_category, update_category, delete_category
from app.models import get_gallery_images, add_gallery_image, delete_gallery_image
from app.models import get_subscribers, add_subscriber, toggle_subscriber, delete_subscriber, get_subscriber_count
from app.models import get_pageview_stats, record_pageview

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), 'data', 'uploads')
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)
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

@login_manager.user_loader
def load_user(user_id):
    return User.get(int(user_id))

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
    }

@app.route('/')
def index():
    page = request.args.get('page', 1, type=int)
    posts, total = get_posts(page=page, per_page=20)
    total_pages = (total + 19) // 20
    return render_template('index.html', posts=posts, page=page, total_pages=total_pages)

@app.route('/post/<slug>')
def post(slug):
    post = get_post(slug)
    if not post:
        flash('Yazı bulunamadı.', 'error')
        return redirect(url_for('index'))
    post = dict(post)
    return render_template('post.html', post=post)

@app.route('/about')
def about():
    return render_template('about.html')

# --- Admin ---

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

# --- Admin: Categories ---

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

# --- Admin: Gallery ---

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

# --- Admin: Subscribers ---

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

        # Brevo API ile gönder
        try:
            import httpx
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

            import asyncio
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

# --- Admin: Stats ---

@app.route('/admin/stats')
@login_required
def admin_stats():
    stats = get_pageview_stats(days=30)
    sub_count = get_subscriber_count()
    from app.models import get_db
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
        for key in ['site_title', 'site_description', 'primary_color',
                     'secondary_color', 'bg_color', 'text_color',
                     'font_heading', 'font_body']:
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
        color_presets=COLOR_PRESETS,
        default_fonts=DEFAULT_FONTS,
    )

@app.route('/admin/change-password', methods=['POST'])
@login_required
def admin_change_password():
    from werkzeug.security import generate_password_hash
    from app.models import get_db
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

@app.route('/admin/ai-content', methods=['GET', 'POST'])
@login_required
def admin_ai_content():
    generated = ''
    topic = ''
    if request.method == 'POST':
        topic = request.form.get('topic', '').strip()
        tone = request.form.get('tone', 'profesyonel')
        length = request.form.get('length', '500')
        if topic:
            try:
                import httpx
                prompt = f'{topic} hakkında {tone} tonda, {length} kelimelik SEO uyumlu blog yazısı yaz.'
                resp = httpx.post('https://insightmap.tr/api/ollama/generate', json={
                    'model': 'qwen2.5:14b',
                    'system': 'Sen profesyonel blog yazarısın. Türkçe, akıcı, SEO uyumlu içerik üret. Başlık ve alt başlıklar kullan.',
                    'prompt': prompt,
                    'stream': False,
                    'options': {'temperature': 0.7, 'num_predict': 2048}
                }, timeout=120, verify=False)
                if resp.status_code == 200:
                    data = resp.json()
                    generated = data.get('response', '')
                else:
                    flash(f'API hatası: {resp.status_code}', 'error')
            except Exception as e:
                flash(f'Hata: {str(e)[:100]}', 'error')
    return render_template('admin/ai_content.html', topic=topic, generated=generated)

@app.route('/theme.css')
def theme_css():
    primary = get_setting('primary_color', '#3d6b4f')
    secondary = get_setting('secondary_color', '#2d4f3a')
    bg = get_setting('bg_color', '#ffffff')
    text = get_setting('text_color', '#333333')
    font_h = get_setting('font_heading', 'Georgia, serif')
    font_b = get_setting('font_body', 'sans-serif')
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
.footer {{ background: var(--secondary); }}
'''
    from flask import Response
    return Response(css, mimetype='text/css')

@app.route('/static/<path:path>')
def static_files(path):
    return send_from_directory(os.path.join(app.root_path, '..', 'src'), path)

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
