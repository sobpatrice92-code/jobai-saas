import sqlite3, bcrypt, os
from pathlib import Path
from datetime import datetime, timezone

TRIAL_DAYS = 30

DB_PATH = Path(__file__).parent / "jobai.db"

def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        email       TEXT    UNIQUE NOT NULL,
        password    TEXT    NOT NULL,
        name        TEXT    NOT NULL,
        created_at  TEXT    DEFAULT (datetime('now')),
        setup_done  INTEGER DEFAULT 0,
        trial_start TEXT    DEFAULT (datetime('now')),
        plan        TEXT    DEFAULT 'trial'
    );
    CREATE TABLE IF NOT EXISTS user_config (
        user_id         INTEGER PRIMARY KEY,
        openai_key      TEXT DEFAULT '',
        gmail_address   TEXT DEFAULT '',
        gmail_password  TEXT DEFAULT '',
        nom_complet     TEXT DEFAULT '',
        telephone       TEXT DEFAULT '',
        adresse         TEXT DEFAULT '',
        ville           TEXT DEFAULT '',
        province        TEXT DEFAULT '',
        profession      TEXT DEFAULT '',
        keywords        TEXT DEFAULT '',
        cv_path         TEXT DEFAULT '',
        FOREIGN KEY(user_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS candidatures (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER NOT NULL,
        date        TEXT,
        entreprise  TEXT,
        poste       TEXT,
        lien        TEXT,
        plateforme  TEXT,
        score       TEXT,
        statut      TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS agent_logs (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id    INTEGER NOT NULL,
        agent      TEXT,
        started_at TEXT DEFAULT (datetime('now')),
        status     TEXT DEFAULT 'running',
        output     TEXT DEFAULT '',
        FOREIGN KEY(user_id) REFERENCES users(id)
    );
    """)
    conn.commit()
    conn.close()

# ── Users ─────────────────────────────────────────────────────
def create_user(email, password, name):
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    conn = get_db()
    try:
        conn.execute("INSERT INTO users (email, password, name) VALUES (?,?,?)",
                     (email.lower(), hashed, name))
        user_id = conn.execute("SELECT id FROM users WHERE email=?", (email.lower(),)).fetchone()["id"]
        conn.execute("INSERT INTO user_config (user_id) VALUES (?)", (user_id,))
        conn.commit()
        return user_id, None
    except sqlite3.IntegrityError:
        return None, "Email déjà utilisé"
    finally:
        conn.close()

def verify_user(email, password):
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE email=?", (email.lower(),)).fetchone()
    conn.close()
    if not row:
        return None, "Email introuvable"
    if not bcrypt.checkpw(password.encode(), row["password"].encode()):
        return None, "Mot de passe incorrect"
    return dict(row), None

def get_user(user_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def get_config(user_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM user_config WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else {}

def save_config(user_id, data):
    conn = get_db()
    fields = ["openai_key","gmail_address","gmail_password","nom_complet",
              "telephone","adresse","ville","province","profession","keywords","cv_path"]
    for f in fields:
        if f in data:
            conn.execute(f"UPDATE user_config SET {f}=? WHERE user_id=?", (data[f], user_id))
    conn.execute("UPDATE users SET setup_done=1 WHERE id=?", (user_id,))
    conn.commit()
    conn.close()

# ── Candidatures ──────────────────────────────────────────────
def get_candidatures(user_id, q="", statut="", limit=50, offset=0):
    conn = get_db()
    sql  = "SELECT * FROM candidatures WHERE user_id=?"
    args = [user_id]
    if q:
        sql += " AND (entreprise LIKE ? OR poste LIKE ? OR statut LIKE ?)"
        args += [f"%{q}%", f"%{q}%", f"%{q}%"]
    if statut:
        sql += " AND statut LIKE ?"
        args.append(f"%{statut}%")
    total = conn.execute(sql.replace("SELECT *","SELECT COUNT(*)"), args).fetchone()[0]
    sql  += " ORDER BY date DESC LIMIT ? OFFSET ?"
    args += [limit, offset]
    rows  = [dict(r) for r in conn.execute(sql, args).fetchall()]
    conn.close()
    return rows, total

def add_candidature(user_id, row):
    conn = get_db()
    conn.execute("""INSERT INTO candidatures
        (user_id,date,entreprise,poste,lien,plateforme,score,statut)
        VALUES (?,?,?,?,?,?,?,?)""",
        (user_id, row.get("date",""), row.get("entreprise",""), row.get("poste",""),
         row.get("lien",""), row.get("plateforme",""), row.get("score","0"), row.get("statut","")))
    conn.commit()
    conn.close()

def update_candidature(cand_id, user_id, field, value):
    allowed = ["entreprise","poste","lien","plateforme","score","statut"]
    if field not in allowed:
        return
    conn = get_db()
    conn.execute(f"UPDATE candidatures SET {field}=? WHERE id=? AND user_id=?",
                 (value, cand_id, user_id))
    conn.commit()
    conn.close()

def get_trial_info(user_id):
    """Retourne (jours_restants, est_actif, plan)."""
    conn = get_db()
    row  = conn.execute("SELECT trial_start, plan FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    if not row:
        return 0, False, "trial"
    plan = row["plan"] or "trial"
    if plan == "paid":
        return 999, True, "paid"
    try:
        start = datetime.fromisoformat(row["trial_start"])
    except Exception:
        start = datetime.now()
    delta = (datetime.now() - start).days
    restants = max(0, TRIAL_DAYS - delta)
    return restants, restants > 0, plan

def get_stats(user_id):
    conn   = get_db()
    total  = conn.execute("SELECT COUNT(*) FROM candidatures WHERE user_id=?", (user_id,)).fetchone()[0]
    today  = datetime.now().strftime("%Y-%m-%d")
    auj    = conn.execute("SELECT COUNT(*) FROM candidatures WHERE user_id=? AND date LIKE ?",
                          (user_id, f"{today}%")).fetchone()[0]
    scores = conn.execute("SELECT score FROM candidatures WHERE user_id=?", (user_id,)).fetchall()
    nums   = []
    for r in scores:
        try:
            import re
            m = re.search(r"\d+", r["score"] or "0")
            if m: nums.append(int(m.group()))
        except: pass
    score_moyen = sum(nums)//len(nums) if nums else 0
    POSITIFS = ["email","easy apply","postule","lien","soumis","relance","rh","direct"]
    positifs = sum(1 for r in conn.execute("SELECT statut FROM candidatures WHERE user_id=?", (user_id,))
                   if any(p in (r["statut"] or "").lower() for p in POSITIFS))
    taux     = round(positifs*100/total) if total else 0
    # plateformes
    pfrows = conn.execute("SELECT plateforme, COUNT(*) as n FROM candidatures WHERE user_id=? GROUP BY plateforme ORDER BY n DESC LIMIT 6", (user_id,)).fetchall()
    plateformes = {r["plateforme"] or "Autre": r["n"] for r in pfrows}
    # dernières
    dernieres = [dict(r) for r in conn.execute("SELECT * FROM candidatures WHERE user_id=? ORDER BY date DESC LIMIT 8", (user_id,)).fetchall()]
    conn.close()
    return {"total": total, "aujourd_hui": auj, "score_moyen": score_moyen,
            "taux": taux, "plateformes": plateformes, "dernieres": dernieres}
