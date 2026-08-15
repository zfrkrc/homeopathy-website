import sqlite3
import os
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin

DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'database.sqlite')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            category TEXT DEFAULT '',
            content TEXT NOT NULL,
            excerpt TEXT DEFAULT '',
            published INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            sort_order INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS gallery_images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            title TEXT DEFAULT '',
            alt_text TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS subscribers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            name TEXT DEFAULT '',
            active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS pageviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT NOT NULL,
            ip TEXT DEFAULT '',
            user_agent TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS content_pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            kicker TEXT DEFAULT '',
            lede TEXT DEFAULT '',
            body_md TEXT DEFAULT '',
            group_name TEXT DEFAULT '',
            reading_step INTEGER DEFAULT 0,
            read_minutes INTEGER DEFAULT 0,
            next_slug TEXT DEFAULT '',
            sort_order INTEGER DEFAULT 0,
            is_published INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    ''')
    # Lightweight migrations for existing databases
    for ddl in [
        "ALTER TABLE posts ADD COLUMN image TEXT DEFAULT ''",
        "ALTER TABLE posts ADD COLUMN views INTEGER DEFAULT 0",
    ]:
        try:
            conn.execute(ddl)
        except sqlite3.OperationalError:
            pass  # column already exists
    # Default admin user
    existing = conn.execute('SELECT id FROM users WHERE username=?', ('admin',)).fetchone()
    if not existing:
        conn.execute('INSERT INTO users (username, password_hash) VALUES (?, ?)',
                     ('admin', generate_password_hash('admin123')))
    existing_cats = conn.execute('SELECT COUNT(*) FROM categories').fetchone()[0]
    if existing_cats == 0:
        default_cats = ['Bilim & Kanıtlar', 'Kronik Sağlık', 'Çocuk Sağlığı', 'Duygusal Sağlık', 'Beslenme']
        for i, name in enumerate(default_cats):
            slug = slugify(name)
            conn.execute('INSERT INTO categories (name, slug, sort_order) VALUES (?, ?, ?)',
                         (name, slug, i))
    defaults = [
        ('site_title', 'Homeopati Blog'),
        ('site_description', 'Doğal İyileşme Yolculuğu'),
        ('primary_color', '#3d6b4f'),
        ('secondary_color', '#2d4f3a'),
        ('bg_color', '#ffffff'),
        ('text_color', '#333333'),
        ('font_heading', 'Georgia, serif'),
        ('font_body', 'sans-serif'),
        ('logo_path', ''),
        ('weather_location', 'İstanbul'),
        ('show_weather', '1'),
        ('social_instagram', ''),
        ('social_twitter', ''),
        ('social_facebook', ''),
        ('social_youtube', ''),
        ('show_social', '1'),
        ('sidebar_position', 'right'),
        ('posts_per_page', '12'),
        ('custom_css', ''),
        ('hero_title', ''),
        ('hero_description', ''),
        ('footer_text', ''),
    ]
    for k, v in defaults:
        conn.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', (k, v))
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS custom_pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            blocks_json TEXT DEFAULT '[]',
            is_published INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    seed_content_pages(conn)
    conn.close()

class User(UserMixin):
    def __init__(self, id, username):
        self.id = id
        self.username = username

    @staticmethod
    def get(user_id):
        conn = get_db()
        u = conn.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
        conn.close()
        if u:
            return User(u['id'], u['username'])
        return None

    @staticmethod
    def authenticate(username, password):
        conn = get_db()
        u = conn.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
        conn.close()
        if u and check_password_hash(u['password_hash'], password):
            return User(u['id'], u['username'])
        return None

def get_posts(page=1, per_page=10, published_only=True, search='', category=''):
    conn = get_db()
    offset = (page - 1) * per_page
    clauses = []
    params = []
    if published_only:
        clauses.append('published=1')
    if search:
        clauses.append('(title LIKE ? OR excerpt LIKE ? OR content LIKE ?)')
        like = f'%{search}%'
        params.extend([like, like, like])
    if category:
        clauses.append('category=?')
        params.append(category)
    where = ('WHERE ' + ' AND '.join(clauses)) if clauses else ''
    total = conn.execute(f'SELECT COUNT(*) FROM posts {where}', params).fetchone()[0]
    posts = conn.execute(
        f'SELECT * FROM posts {where} ORDER BY created_at DESC LIMIT ? OFFSET ?',
        (*params, per_page, offset)
    ).fetchall()
    conn.close()
    return posts, total

def search_posts(query, page=1, per_page=20):
    conn = get_db()
    offset = (page - 1) * per_page
    like = f'%{query}%'
    total = conn.execute(
        'SELECT COUNT(*) FROM posts WHERE published=1 AND (title LIKE ? OR content LIKE ? OR excerpt LIKE ?)',
        (like, like, like)
    ).fetchone()[0]
    posts = conn.execute(
        'SELECT * FROM posts WHERE published=1 AND (title LIKE ? OR content LIKE ? OR excerpt LIKE ?) ORDER BY created_at DESC LIMIT ? OFFSET ?',
        (like, like, like, per_page, offset)
    ).fetchall()
    conn.close()
    return posts, total

def get_post(slug):
    conn = get_db()
    post = conn.execute('SELECT * FROM posts WHERE slug=?', (slug,)).fetchone()
    conn.close()
    return post

def get_post_by_id(id):
    conn = get_db()
    post = conn.execute('SELECT * FROM posts WHERE id=?', (id,)).fetchone()
    conn.close()
    return post

def create_post(title, slug, category, content, excerpt, published=1, image=''):
    conn = get_db()
    now = datetime.now().isoformat()
    conn.execute(
        'INSERT INTO posts (title, slug, category, content, excerpt, published, image, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)',
        (title, slug, category, content, excerpt, published, image, now, now)
    )
    conn.commit()
    conn.close()

def update_post(id, title, slug, category, content, excerpt, published=1, image=''):
    conn = get_db()
    now = datetime.now().isoformat()
    conn.execute(
        'UPDATE posts SET title=?, slug=?, category=?, content=?, excerpt=?, published=?, image=?, updated_at=? WHERE id=?',
        (title, slug, category, content, excerpt, published, image, now, id)
    )
    conn.commit()
    conn.close()

def increment_post_views(id):
    conn = get_db()
    conn.execute('UPDATE posts SET views = COALESCE(views, 0) + 1 WHERE id=?', (id,))
    conn.commit()
    conn.close()

def get_related_posts(category, exclude_id, limit=3):
    conn = get_db()
    posts = conn.execute(
        'SELECT * FROM posts WHERE published=1 AND category=? AND id!=? ORDER BY created_at DESC LIMIT ?',
        (category, exclude_id, limit)
    ).fetchall()
    if len(posts) < limit:
        fill = conn.execute(
            'SELECT * FROM posts WHERE published=1 AND category!=? AND id!=? ORDER BY created_at DESC LIMIT ?',
            (category, exclude_id, limit - len(posts))
        ).fetchall()
        posts = list(posts) + list(fill)
    conn.close()
    return posts

def delete_post(id):
    conn = get_db()
    conn.execute('DELETE FROM posts WHERE id=?', (id,))
    conn.commit()
    conn.close()


# ── Content pages (makale/yazı — admin'den yönetilen sabit sayfalar) ─────────

def seed_content_pages(conn=None):
    """content_seed.json'daki içeriği idempotent biçimde içe aktarır.
    Mevcut satırları bozmaz; yalnızca eksik slug'ları ekler."""
    import json as _json
    seed_path = os.path.join(os.path.dirname(__file__), 'content_seed.json')
    if not os.path.exists(seed_path):
        return
    try:
        with open(seed_path, encoding='utf-8') as f:
            entries = _json.load(f)
    except Exception:
        return
    own = conn is None
    if own:
        conn = get_db()
    for e in entries:
        exists = conn.execute('SELECT id FROM content_pages WHERE slug=?', (e.get('slug'),)).fetchone()
        if exists:
            continue
        conn.execute(
            'INSERT INTO content_pages (slug, title, kicker, lede, body_md, group_name, '
            'reading_step, read_minutes, next_slug, sort_order, is_published) '
            'VALUES (?,?,?,?,?,?,?,?,?,?,1)',
            (e.get('slug'), e.get('title', ''), e.get('kicker', ''), e.get('lede', ''),
             e.get('body_md', ''), e.get('group', ''), e.get('reading_step', 0),
             e.get('read_minutes', 0), e.get('next_slug', ''), e.get('sort_order', 0))
        )
    conn.commit()
    if own:
        conn.close()


def get_content_pages(published_only=True):
    conn = get_db()
    q = 'SELECT * FROM content_pages'
    if published_only:
        q += ' WHERE is_published=1'
    q += ' ORDER BY sort_order, id'
    rows = conn.execute(q).fetchall()
    conn.close()
    return rows


def get_content_page(slug):
    conn = get_db()
    row = conn.execute('SELECT * FROM content_pages WHERE slug=?', (slug,)).fetchone()
    conn.close()
    return row


def get_content_page_by_id(id):
    conn = get_db()
    row = conn.execute('SELECT * FROM content_pages WHERE id=?', (id,)).fetchone()
    conn.close()
    return row


def update_content_page(slug, title, kicker, lede, body_md, group_name, reading_step,
                        read_minutes, next_slug, sort_order, is_published):
    conn = get_db()
    now = datetime.now().isoformat()
    conn.execute(
        'UPDATE content_pages SET title=?, kicker=?, lede=?, body_md=?, group_name=?, '
        'reading_step=?, read_minutes=?, next_slug=?, sort_order=?, is_published=?, updated_at=? '
        'WHERE slug=?',
        (title, kicker, lede, body_md, group_name, reading_step, read_minutes, next_slug,
         sort_order, int(is_published), now, slug)
    )
    conn.commit()
    conn.close()


def create_content_page(slug, title):
    conn = get_db()
    conn.execute(
        'INSERT INTO content_pages (slug, title, is_published) VALUES (?, ?, 0)', (slug, title)
    )
    conn.commit()
    conn.close()


def delete_content_page(slug):
    conn = get_db()
    conn.execute('DELETE FROM content_pages WHERE slug=?', (slug,))
    conn.commit()
    conn.close()

def get_setting(key, default=''):
    conn = get_db()
    row = conn.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
    conn.close()
    return row['value'] if row else default

def set_setting(key, value):
    conn = get_db()
    conn.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, value))
    conn.commit()
    conn.close()

def get_all_settings():
    conn = get_db()
    rows = conn.execute('SELECT key, value FROM settings').fetchall()
    conn.close()
    return {row['key']: row['value'] for row in rows}

def slugify(text):
    import re
    text = text.lower().strip()
    text = re.sub(r'[çÇ]', 'c', text)
    text = re.sub(r'[ğĞ]', 'g', text)
    text = re.sub(r'[ıİ]', 'i', text)
    text = re.sub(r'[öÖ]', 'o', text)
    text = re.sub(r'[şŞ]', 's', text)
    text = re.sub(r'[üÜ]', 'u', text)
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    text = re.sub(r'[\s-]+', '-', text).strip('-')
    return text

def get_categories():
    conn = get_db()
    cats = conn.execute('SELECT * FROM categories ORDER BY sort_order, name').fetchall()
    conn.close()
    return cats

def get_category(id):
    conn = get_db()
    cat = conn.execute('SELECT * FROM categories WHERE id=?', (id,)).fetchone()
    conn.close()
    return cat

def create_category(name):
    conn = get_db()
    slug = slugify(name)
    conn.execute('INSERT INTO categories (name, slug) VALUES (?, ?)', (name, slug))
    conn.commit()
    conn.close()

def update_category(id, name):
    conn = get_db()
    slug = slugify(name)
    conn.execute('UPDATE categories SET name=?, slug=? WHERE id=?', (name, slug, id))
    conn.commit()
    conn.close()

def delete_category(id):
    conn = get_db()
    conn.execute('DELETE FROM categories WHERE id=?', (id,))
    conn.commit()
    conn.close()

def get_gallery_images(page=1, per_page=50):
    conn = get_db()
    offset = (page - 1) * per_page
    total = conn.execute('SELECT COUNT(*) FROM gallery_images').fetchone()[0]
    items = conn.execute(
        'SELECT * FROM gallery_images ORDER BY created_at DESC LIMIT ? OFFSET ?',
        (per_page, offset)
    ).fetchall()
    conn.close()
    return items, total

def add_gallery_image(filename, title='', alt_text=''):
    conn = get_db()
    conn.execute(
        'INSERT INTO gallery_images (filename, title, alt_text) VALUES (?, ?, ?)',
        (filename, title, alt_text)
    )
    conn.commit()
    id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
    conn.close()
    return id

def delete_gallery_image(id):
    conn = get_db()
    img = conn.execute('SELECT filename FROM gallery_images WHERE id=?', (id,)).fetchone()
    if img:
        conn.execute('DELETE FROM gallery_images WHERE id=?', (id,))
        conn.commit()
        conn.close()
        return img['filename']
    conn.close()
    return None

def get_subscribers(page=1, per_page=50, active_only=True):
    conn = get_db()
    offset = (page - 1) * per_page
    where = 'WHERE active=1' if active_only else ''
    total = conn.execute(f'SELECT COUNT(*) FROM subscribers {where}').fetchone()[0]
    items = conn.execute(
        f'SELECT * FROM subscribers {where} ORDER BY created_at DESC LIMIT ? OFFSET ?',
        (per_page, offset)
    ).fetchall()
    conn.close()
    return items, total

def add_subscriber(email, name=''):
    conn = get_db()
    existing = conn.execute('SELECT * FROM subscribers WHERE email=?', (email,)).fetchone()
    if existing:
        if not existing['active']:
            conn.execute('UPDATE subscribers SET active=1, name=? WHERE email=?', (name, email))
            conn.commit()
            conn.close()
            return 'reactivated'
        conn.close()
        return 'exists'
    conn.execute('INSERT INTO subscribers (email, name) VALUES (?, ?)', (email, name))
    conn.commit()
    conn.close()
    return 'added'

def toggle_subscriber(id, active):
    conn = get_db()
    conn.execute('UPDATE subscribers SET active=? WHERE id=?', (active, id))
    conn.commit()
    conn.close()

def delete_subscriber(id):
    conn = get_db()
    conn.execute('DELETE FROM subscribers WHERE id=?', (id,))
    conn.commit()
    conn.close()

def get_subscriber_count():
    conn = get_db()
    total = conn.execute('SELECT COUNT(*) FROM subscribers WHERE active=1').fetchone()[0]
    conn.close()
    return total

def record_pageview(path, ip='', user_agent=''):
    conn = get_db()
    conn.execute(
        'INSERT INTO pageviews (path, ip, user_agent) VALUES (?, ?, ?)',
        (path, ip[:100], user_agent[:200] if user_agent else '')
    )
    conn.commit()
    conn.close()

def get_pageview_stats(days=30):
    conn = get_db()
    total = conn.execute('SELECT COUNT(*) FROM pageviews').fetchone()[0]
    from datetime import timedelta
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    recent = conn.execute('SELECT COUNT(*) FROM pageviews WHERE created_at > ?', (cutoff,)).fetchone()[0]
    top_pages = conn.execute(
        'SELECT path, COUNT(*) as cnt FROM pageviews GROUP BY path ORDER BY cnt DESC LIMIT 10'
    ).fetchall()
    daily = conn.execute(
        "SELECT DATE(created_at) as day, COUNT(*) as cnt FROM pageviews WHERE created_at > ? GROUP BY day ORDER BY day DESC LIMIT 30",
        (cutoff,)
    ).fetchall()
    conn.close()
    return {'total': total, 'recent': recent, 'top_pages': top_pages, 'daily': daily}
