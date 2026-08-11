import sqlite3
import json
import uuid
from datetime import datetime
from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, flash, session as flask_session
from werkzeug.security import generate_password_hash, check_password_hash
from app.models import get_db, get_setting, set_setting, slugify

portal_bp = Blueprint("portal", __name__, url_prefix="/portal")

# --- Database helpers ---

def init_portal_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS portal_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            full_name TEXT NOT NULL,
            phone TEXT DEFAULT "",
            company TEXT DEFAULT "",
            email_verified INTEGER DEFAULT 0,
            two_factor_enabled INTEGER DEFAULT 0,
            two_factor_secret TEXT DEFAULT "",
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS portal_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token TEXT UNIQUE NOT NULL,
            expires_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS anlatilari (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            data_json TEXT NOT NULL,
            durum TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS vaka_template (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data_json TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    conn.close()


def create_portal_user(email, password, full_name, phone="", company=""):
    conn = get_db()
    existing = conn.execute("SELECT id FROM portal_users WHERE email=?", (email,)).fetchone()
    if existing:
        conn.close()
        return None
    conn.execute(
        "INSERT INTO portal_users (email, password_hash, full_name, phone, company) VALUES (?,?,?,?,?)",
        (email, generate_password_hash(password), full_name, phone, company),
    )
    uid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    return uid


def auth_portal_user(email, password):
    conn = get_db()
    u = conn.execute("SELECT * FROM portal_users WHERE email=?", (email,)).fetchone()
    conn.close()
    if u and check_password_hash(u["password_hash"], password):
        return dict(u)
    return None


def get_portal_user(user_id):
    conn = get_db()
    u = conn.execute("SELECT * FROM portal_users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    return dict(u) if u else None


def update_portal_user(user_id, **kwargs):
    conn = get_db()
    allowed = ["full_name", "phone", "company", "email_verified", "two_factor_enabled", "two_factor_secret"]
    for k, v in kwargs.items():
        if k in allowed:
            conn.execute(f"UPDATE portal_users SET {k}=? WHERE id=?", (v, user_id))
    conn.commit()
    conn.close()


def update_portal_login(user_id):
    conn = get_db()
    conn.execute("UPDATE portal_users SET last_login=CURRENT_TIMESTAMP WHERE id=?", (user_id,))
    conn.commit()
    conn.close()


def get_all_portal_users():
    conn = get_db()
    users = conn.execute(
        "SELECT id, email, full_name, phone, company, email_verified, two_factor_enabled, created_at, last_login FROM portal_users ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(u) for u in users]


def delete_portal_user(user_id):
    conn = get_db()
    conn.execute("DELETE FROM portal_users WHERE id=?", (user_id,))
    conn.execute("DELETE FROM portal_sessions WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()


# --- Session management ---

def make_session_token(user_id):
    token = uuid.uuid4().hex + uuid.uuid4().hex
    conn = get_db()
    conn.execute(
        "DELETE FROM portal_sessions WHERE user_id=? OR expires_at < CURRENT_TIMESTAMP",
        (user_id,),
    )
    conn.execute(
        "INSERT INTO portal_sessions (user_id, token) VALUES (?, ?)",
        (user_id, token),
    )
    conn.commit()
    conn.close()
    return token


def get_session_user():
    token = flask_session.get("portal_token")
    if not token:
        return None
    conn = get_db()
    s = conn.execute(
        "SELECT user_id FROM portal_sessions WHERE token=? AND (expires_at > CURRENT_TIMESTAMP OR expires_at IS NULL)",
        (token,),
    ).fetchone()
    conn.close()
    if not s:
        return None
    return get_portal_user(s["user_id"])


def logout_session():
    token = flask_session.pop("portal_token", None)
    if token:
        conn = get_db()
        conn.execute("DELETE FROM portal_sessions WHERE token=?", (token,))
        conn.commit()
        conn.close()


def portal_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_session_user()
        if not user:
            flash("Lutfen giris yapin.", "error")
            return redirect(url_for("portal.login"))
        return f(*args, **kwargs)
    return decorated_function


# --- Routes ---


@portal_bp.route("/kayit")
def register_disabled():
    return redirect(url_for("portal.login"))


@portal_bp.route("/kayit", methods=["POST"])
def register_disabled_post():
    flash("Kayit su an kapalidir. Lutfen yoneticinizle iletisime gecin.", "error")
    return redirect(url_for("portal.login"))

@portal_bp.route("/kayit-eski", methods=["GET", "POST"])
def register():
    if get_session_user():
        return redirect(url_for("portal.dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        full_name = request.form.get("full_name", "").strip()
        phone = request.form.get("phone", "").strip()
        company = request.form.get("company", "").strip()

        if not email or "@" not in email:
            flash("Gecerli bir e-posta adresi girin.", "error")
        elif len(password) < 6:
            flash("Sifre en az 6 karakter olmali.", "error")
        elif not full_name:
            flash("Ad soyad zorunludur.", "error")
        else:
            uid = create_portal_user(email, password, full_name, phone, company)
            if uid:
                flash(f"Kayit basarili! Zeyna portali: https://wez.zeyna.net.tr", "success")
                return redirect(url_for("portal.login"))
            flash("Bu e-posta zaten kayitli.", "error")

    return render_template("portal/register.html")


@portal_bp.route("/giris", methods=["GET", "POST"])
def login():
    return redirect("https://wez.zk.net.tr")


@portal_bp.route("/cikis")
def logout():
    logout_session()
    flash("Cikis yapildi.", "info")
    return redirect(url_for("index"))


@portal_bp.route("/dashboard")
@portal_login_required
def dashboard():
    user = get_session_user()
    return render_template("portal/dashboard.html", portal_user=user)


@portal_bp.route("/profil", methods=["GET", "POST"])
@portal_login_required
def profile():
    user = get_session_user()
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        phone = request.form.get("phone", "").strip()
        company = request.form.get("company", "").strip()
        if full_name:
            update_portal_user(user["id"], full_name=full_name, phone=phone, company=company)
            flash("Profil guncellendi.", "success")
        else:
            flash("Ad soyad zorunludur.", "error")
        return redirect(url_for("portal.profile"))
    return render_template("portal/profile.html", portal_user=user)


@portal_bp.route("/rehber")
@portal_login_required
def guide():
    user = get_session_user()
    return render_template("portal/guide.html", portal_user=user)


@portal_bp.route("/pulsecare")
@portal_login_required
def pulsecare():
    user = get_session_user()
    return render_template("portal/pulsecare.html", portal_user=user)


# --- Homepage sections API ---

def get_homepage_sections():
    raw = get_setting("homepage_sections", "[]")
    try:
        return json.loads(raw)
    except:
        return []


def set_homepage_sections(sections):
    set_setting("homepage_sections", json.dumps(sections))


@portal_bp.route("/anlati/randevu", methods=["POST"])
def vaka_randevu_kaydet():
    """Save vaka appointment. Public endpoint."""
    data = request.get_json(force=True, silent=True) or {}
    if not data:
        return {"ok": False, "msg": "Veri gerekli"}, 400
    conn = get_db()
    conn.execute(
        "INSERT INTO anlatilari (user_id, data_json, durum) VALUES (?, ?, 'pending')",
        (None, json.dumps(data)),
    )
    conn.commit()
    conn.close()
    return {"ok": True}

@portal_bp.route("/anlati/randevular", methods=["GET"])
@portal_login_required
def vaka_randevular():
    """List vaka appointments (admin)."""
    conn = get_db()
    rows = conn.execute(
        "SELECT id, durum, created_at, data_json FROM anlatilari ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    items = []
    for r in rows:
        d = json.loads(r["data_json"]) if r["data_json"] else {}
        items.append({
            "id": r["id"],
            "status": r["durum"],
            "created_at": r["created_at"],
            "lead": d.get("lead", {}),
            "answers": d.get("answers", {}),
        })
    return items

@portal_bp.route("/anlati/randevu/<int:id>/durum", methods=["POST"])
@portal_login_required
def vaka_randevu_durum(id):
    durum = request.form.get("durum", "pending")
    conn = get_db()
    conn.execute("UPDATE anlatilari SET durum=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (durum, id))
    conn.commit()
    conn.close()
    return {"ok": True}

@portal_bp.route("/anlati/kaydet", methods=["POST"])
def anlati_kaydet():
    """Save vaka form data. Public endpoint — no login required."""
    data = request.get_json(force=True, silent=True) or {}
    lead_name = (data.get("lead", {}) or {}).get("name", "").strip()
    user_id = None
    if lead_name:
        conn = get_db()
        conn.execute(
            "INSERT INTO anlatilari (user_id, data_json, durum) VALUES (?, ?, 'pending')",
            (user_id, json.dumps(data)),
        )
        conn.commit()
        conn.close()
        return {"ok": True, "msg": "Kaydedildi"}
    return {"ok": False, "msg": "Isim zorunlu"}, 400


@portal_bp.route("/anlati/template", methods=["GET"])
def vaka_template_get():
    """Get the shared form template (editable by admin)."""
    conn = get_db()
    row = conn.execute(
        "SELECT data_json FROM vaka_template ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    if row:
        return json.loads(row["data_json"])
    return {}


@portal_bp.route("/anlati/template", methods=["POST"])
def vaka_template_save():
    """Save the shared form template (public)."""
    data = request.get_json(force=True, silent=True) or {}
    conn = get_db()
    conn.execute("DELETE FROM vaka_template")
    conn.execute("INSERT INTO vaka_template (data_json) VALUES (?)", (json.dumps(data),))
    conn.commit()
    conn.close()
    return {"ok": True}


@portal_bp.route("/anlati/list", methods=["GET"])
@portal_login_required
def vaka_list():
    user = get_session_user()
    conn = get_db()
    rows = conn.execute(
        "SELECT id, user_id, durum, created_at FROM anlatilari ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    items = []
    for r in rows:
        items.append(dict(r))
    return render_template("portal/vaka_list.html", items=items, portal_user=user)


@portal_bp.route("/anlati/<int:id>", methods=["GET"])
@portal_login_required
def vaka_detail(id):
    user = get_session_user()
    conn = get_db()
    row = conn.execute("SELECT * FROM anlatilari WHERE id=?", (id,)).fetchone()
    conn.close()
    if not row:
        flash("Kayit bulunamadi.", "error")
        return redirect(url_for("portal.vaka_list"))
    data = json.loads(row["data_json"])
    return render_template("portal/vaka_detail.html", item=dict(row), data=data, portal_user=user)


@portal_bp.route("/anlati/<int:id>/durum", methods=["POST"])
@portal_login_required
def vaka_durum(id):
    durum = request.form.get("durum", "pending")
    conn = get_db()
    conn.execute("UPDATE anlatilari SET durum=? WHERE id=?", (durum, id))
    conn.commit()
    conn.close()
    flash("Durum guncellendi.", "success")
    return redirect(url_for("portal.vaka_list"))
