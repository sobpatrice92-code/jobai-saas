import os, bcrypt, re
from datetime import datetime
from pathlib import Path

TRIAL_DAYS = 30

# ── Détection base de données ──────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "")

if DATABASE_URL:
    import psycopg2
    import psycopg2.extras
    import psycopg2.errors

    def get_db():
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        return conn

    def _row(cursor):
        if cursor.description is None:
            return None
        cols = [d[0] for d in cursor.description]
        row  = cursor.fetchone()
        return dict(zip(cols, row)) if row else None

    def _rows(cursor):
        if cursor.description is None:
            return []
        cols = [d[0] for d in cursor.description]
        return [dict(zip(cols, r)) for r in cursor.fetchall()]

    PH  = "%s"          # placeholder PostgreSQL
    PK  = "SERIAL PRIMARY KEY"
    NOW = "NOW()"
    IntegrityError = psycopg2.IntegrityError

    def init_db():
        conn = get_db()
        cur  = conn.cursor()
        cur.execute(f"""
        CREATE TABLE IF NOT EXISTS users (
            id          {PK},
            email       TEXT    UNIQUE NOT NULL,
            password    TEXT    NOT NULL,
            name        TEXT    NOT NULL,
            created_at  TEXT    DEFAULT ({NOW}::text),
            setup_done  INTEGER DEFAULT 0,
            trial_start TEXT    DEFAULT ({NOW}::text),
            plan        TEXT    DEFAULT 'trial'
        )""")
        cur.execute(f"""
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
            linkedin_email    TEXT DEFAULT '',
            linkedin_password TEXT DEFAULT '',
            cv_content        TEXT DEFAULT '',
            FOREIGN KEY(user_id) REFERENCES users(id)
        )""")
        for col in ["cv_content TEXT DEFAULT ''", "linkedin_cookies TEXT DEFAULT ''", "linkedin_li_at TEXT DEFAULT ''", "linkedin_cookies_json TEXT DEFAULT ''", "linkedin_cookies_updated_at TEXT DEFAULT ''", "notif_email TEXT DEFAULT ''"]:
            try:
                cur.execute(f"ALTER TABLE user_config ADD COLUMN IF NOT EXISTS {col}")
                conn.commit()
            except Exception:
                conn.rollback()
        cur.execute(f"""
        CREATE TABLE IF NOT EXISTS candidatures (
            id          {PK},
            user_id     INTEGER NOT NULL,
            date        TEXT,
            entreprise  TEXT,
            poste       TEXT,
            lien        TEXT,
            plateforme  TEXT,
            score       TEXT,
            statut      TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )""")
        cur.execute(f"""
        CREATE TABLE IF NOT EXISTS agent_logs (
            id         {PK},
            user_id    INTEGER NOT NULL,
            agent      TEXT,
            started_at TEXT DEFAULT ({NOW}::text),
            status     TEXT DEFAULT 'running',
            output     TEXT DEFAULT '',
            FOREIGN KEY(user_id) REFERENCES users(id)
        )""")
        conn.commit()
        cur.close()
        conn.close()

else:
    import sqlite3
    DB_PATH = Path(__file__).parent / "jobai.db"

    def get_db():
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        return conn

    def _row(cursor):
        r = cursor.fetchone()
        return dict(r) if r else None

    def _rows(cursor):
        return [dict(r) for r in cursor.fetchall()]

    PH  = "?"
    PK  = "INTEGER PRIMARY KEY AUTOINCREMENT"
    NOW = "datetime('now')"
    IntegrityError = sqlite3.IntegrityError

    def init_db():
        conn = get_db()
        conn.executescript(f"""
        CREATE TABLE IF NOT EXISTS users (
            id          {PK},
            email       TEXT    UNIQUE NOT NULL,
            password    TEXT    NOT NULL,
            name        TEXT    NOT NULL,
            created_at  TEXT    DEFAULT ({NOW}),
            setup_done  INTEGER DEFAULT 0,
            trial_start TEXT    DEFAULT ({NOW}),
            plan        TEXT    DEFAULT 'trial'
        );
        CREATE TABLE IF NOT EXISTS user_config (
            user_id           INTEGER PRIMARY KEY,
            openai_key        TEXT DEFAULT '',
            gmail_address     TEXT DEFAULT '',
            gmail_password    TEXT DEFAULT '',
            nom_complet       TEXT DEFAULT '',
            telephone         TEXT DEFAULT '',
            adresse           TEXT DEFAULT '',
            ville             TEXT DEFAULT '',
            province          TEXT DEFAULT '',
            profession        TEXT DEFAULT '',
            keywords          TEXT DEFAULT '',
            cv_path           TEXT DEFAULT '',
            linkedin_email    TEXT DEFAULT '',
            linkedin_password TEXT DEFAULT '',
            cv_content        TEXT DEFAULT '',
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS candidatures (
            id          {PK},
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
            id         {PK},
            user_id    INTEGER NOT NULL,
            agent      TEXT,
            started_at TEXT DEFAULT ({NOW}),
            status     TEXT DEFAULT 'running',
            output     TEXT DEFAULT '',
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        """)
        for col in ["cv_content TEXT DEFAULT ''", "linkedin_cookies TEXT DEFAULT ''", "linkedin_li_at TEXT DEFAULT ''", "linkedin_cookies_json TEXT DEFAULT ''", "linkedin_cookies_updated_at TEXT DEFAULT ''", "notif_email TEXT DEFAULT ''"]:
            try:
                conn.execute(f"ALTER TABLE user_config ADD COLUMN {col}")
            except Exception:
                pass
        conn.commit()
        conn.close()


# ── Helpers communs ────────────────────────────────────────────
def _exec(sql, args=(), fetch="none"):
    conn = get_db()
    if DATABASE_URL:
        cur = conn.cursor()
        cur.execute(sql, args)
        if fetch == "one":
            result = _row(cur)
        elif fetch == "all":
            result = _rows(cur)
        elif fetch == "scalar":
            row = cur.fetchone()
            result = row[0] if row else None
        else:
            result = None
        conn.commit()
        cur.close()
        conn.close()
        return result
    else:
        cur = conn.execute(sql, args)
        if fetch == "one":
            r = cur.fetchone()
            result = dict(r) if r else None
        elif fetch == "all":
            result = [dict(r) for r in cur.fetchall()]
        elif fetch == "scalar":
            r = cur.fetchone()
            result = r[0] if r else None
        else:
            result = None
        conn.commit()
        conn.close()
        return result


def _ph(n):
    """Génère n placeholders adaptés à la DB."""
    return ",".join([PH] * n)


# ── Users ──────────────────────────────────────────────────────
def create_user(email, password, name):
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    conn = get_db()
    try:
        if DATABASE_URL:
            cur = conn.cursor()
            cur.execute(
                f"INSERT INTO users (email, password, name) VALUES ({_ph(3)}) RETURNING id",
                (email.lower(), hashed, name)
            )
            user_id = cur.fetchone()[0]
            cur.execute(f"INSERT INTO user_config (user_id) VALUES ({PH})", (user_id,))
            conn.commit()
            cur.close()
        else:
            conn.execute(
                f"INSERT INTO users (email, password, name) VALUES ({_ph(3)})",
                (email.lower(), hashed, name)
            )
            user_id = conn.execute(
                f"SELECT id FROM users WHERE email={PH}", (email.lower(),)
            ).fetchone()["id"]
            conn.execute(f"INSERT INTO user_config (user_id) VALUES ({PH})", (user_id,))
            conn.commit()
        return user_id, None
    except IntegrityError:
        return None, "Email déjà utilisé"
    finally:
        conn.close()


def verify_user(email, password):
    row = _exec(f"SELECT * FROM users WHERE email={PH}", (email.lower(),), fetch="one")
    if not row:
        return None, "Email introuvable"
    if not bcrypt.checkpw(password.encode(), row["password"].encode()):
        return None, "Mot de passe incorrect"
    return row, None


def get_user(user_id):
    return _exec(f"SELECT * FROM users WHERE id={PH}", (user_id,), fetch="one")


def get_config(user_id):
    row = _exec(f"SELECT * FROM user_config WHERE user_id={PH}", (user_id,), fetch="one")
    return row if row else {}


def save_cv_content(user_id, content_b64):
    _exec(f"UPDATE user_config SET cv_content={PH} WHERE user_id={PH}", (content_b64, user_id))

def get_cv_content(user_id):
    row = _exec(f"SELECT cv_content FROM user_config WHERE user_id={PH}", (user_id,), fetch="one")
    return (row or {}).get("cv_content", "")

def save_linkedin_cookies(user_id, cookies_json):
    """Sauvegarde les cookies LinkedIn en base pour survivre aux redéploiements."""
    now = datetime.now().isoformat()
    _exec(f"UPDATE user_config SET linkedin_cookies={PH}, linkedin_cookies_updated_at={PH} WHERE user_id={PH}",
          (cookies_json, now, user_id))

def get_linkedin_cookies(user_id):
    row = _exec(f"SELECT linkedin_cookies FROM user_config WHERE user_id={PH}", (user_id,), fetch="one")
    return (row or {}).get("linkedin_cookies", "")

def get_cookie_age_days(user_id):
    """Retourne le nombre de jours depuis la dernière mise à jour des cookies (999 = jamais configurés)."""
    row = _exec(
        f"SELECT linkedin_cookies_updated_at, linkedin_cookies_json FROM user_config WHERE user_id={PH}",
        (user_id,), fetch="one"
    )
    if not row:
        return 999
    has_cookies = bool((row.get("linkedin_cookies_json") or "").strip())
    updated_at  = (row.get("linkedin_cookies_updated_at") or "").strip()
    if not has_cookies:
        return 999
    if not updated_at:
        return 25  # cookies présents mais pas de date → considérer comme anciens
    try:
        dt = datetime.fromisoformat(updated_at)
        return (datetime.now() - dt).days
    except Exception:
        return 25

def save_config(user_id, data):
    if "linkedin_cookies_json" in data and data["linkedin_cookies_json"].strip():
        data["linkedin_cookies_updated_at"] = datetime.now().isoformat()
    fields = ["openai_key","gmail_address","gmail_password","nom_complet",
              "telephone","adresse","ville","province","profession","keywords",
              "cv_path","linkedin_email","linkedin_password","cv_content",
              "linkedin_li_at","linkedin_cookies_json","linkedin_cookies_updated_at",
              "notif_email"]
    conn = get_db()
    if DATABASE_URL:
        cur = conn.cursor()
        for f in fields:
            if f in data:
                cur.execute(f"UPDATE user_config SET {f}={PH} WHERE user_id={PH}", (data[f], user_id))
        cur.execute(f"UPDATE users SET setup_done=1 WHERE id={PH}", (user_id,))
        conn.commit()
        cur.close()
    else:
        for f in fields:
            if f in data:
                conn.execute(f"UPDATE user_config SET {f}={PH} WHERE user_id={PH}", (data[f], user_id))
        conn.execute(f"UPDATE users SET setup_done=1 WHERE id={PH}", (user_id,))
        conn.commit()
    conn.close()


# ── Candidatures ───────────────────────────────────────────────
def get_candidatures(user_id, q="", statut="", limit=50, offset=0):
    sql  = f"SELECT * FROM candidatures WHERE user_id={PH}"
    args = [user_id]
    if q:
        sql += f" AND (entreprise LIKE {PH} OR poste LIKE {PH} OR statut LIKE {PH})"
        args += [f"%{q}%", f"%{q}%", f"%{q}%"]
    if statut:
        sql += f" AND statut LIKE {PH}"
        args.append(f"%{statut}%")
    count_sql = sql.replace("SELECT *", "SELECT COUNT(*)")
    total = _exec(count_sql, tuple(args), fetch="scalar") or 0
    sql  += f" ORDER BY date DESC LIMIT {PH} OFFSET {PH}"
    args += [limit, offset]
    rows  = _exec(sql, tuple(args), fetch="all") or []
    return rows, total


def add_candidature(user_id, row):
    _exec(
        f"""INSERT INTO candidatures
        (user_id,date,entreprise,poste,lien,plateforme,score,statut)
        VALUES ({_ph(8)})""",
        (user_id, row.get("date",""), row.get("entreprise",""), row.get("poste",""),
         row.get("lien",""), row.get("plateforme",""), row.get("score","0"), row.get("statut",""))
    )


def update_candidature(cand_id, user_id, field, value):
    allowed = ["entreprise","poste","lien","plateforme","score","statut"]
    if field not in allowed:
        return
    _exec(f"UPDATE candidatures SET {field}={PH} WHERE id={PH} AND user_id={PH}",
          (value, cand_id, user_id))


# ── Trial ──────────────────────────────────────────────────────
def get_trial_info(user_id):
    row = _exec(f"SELECT trial_start, plan FROM users WHERE id={PH}", (user_id,), fetch="one")
    if not row:
        return 0, False, "trial"
    plan = row["plan"] or "trial"
    if plan == "paid":
        return 999, True, "paid"
    try:
        start = datetime.fromisoformat(str(row["trial_start"]).split(".")[0])
    except Exception:
        start = datetime.now()
    delta    = (datetime.now() - start).days
    restants = max(0, TRIAL_DAYS - delta)
    return restants, restants > 0, plan


# ── Stats dashboard ────────────────────────────────────────────
def get_stats(user_id):
    today   = datetime.now().strftime("%Y-%m-%d")
    total   = _exec(f"SELECT COUNT(*) FROM candidatures WHERE user_id={PH}", (user_id,), fetch="scalar") or 0
    auj     = _exec(
        f"SELECT COUNT(*) FROM candidatures WHERE user_id={PH} AND date LIKE {PH}",
        (user_id, f"{today}%"), fetch="scalar"
    ) or 0
    scores_rows = _exec(f"SELECT score FROM candidatures WHERE user_id={PH}", (user_id,), fetch="all") or []
    nums = []
    for r in scores_rows:
        m = re.search(r"\d+", str(r.get("score") or "0"))
        if m: nums.append(int(m.group()))
    score_moyen = sum(nums)//len(nums) if nums else 0

    POSITIFS = ["email","easy apply","postule","lien","soumis","relance","rh","direct"]
    statut_rows = _exec(f"SELECT statut FROM candidatures WHERE user_id={PH}", (user_id,), fetch="all") or []
    positifs = sum(1 for r in statut_rows if any(p in (r.get("statut") or "").lower() for p in POSITIFS))
    taux = round(positifs*100/total) if total else 0

    pfrows = _exec(
        f"SELECT plateforme, COUNT(*) as n FROM candidatures WHERE user_id={PH} GROUP BY plateforme ORDER BY n DESC LIMIT 6",
        (user_id,), fetch="all"
    ) or []
    plateformes = {(r.get("plateforme") or "Autre"): r["n"] for r in pfrows}

    dernieres = _exec(
        f"SELECT * FROM candidatures WHERE user_id={PH} ORDER BY date DESC LIMIT 8",
        (user_id,), fetch="all"
    ) or []

    return {"total": total, "aujourd_hui": auj, "score_moyen": score_moyen,
            "taux": taux, "plateformes": plateformes, "dernieres": dernieres}
