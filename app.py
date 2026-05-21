import sys
sys.stdout.reconfigure(encoding="utf-8")

from flask import (Flask, render_template, request, redirect, url_for,
                   session, jsonify, Response, stream_with_context, flash)
from flask_login import (LoginManager, UserMixin, login_user, logout_user,
                          login_required, current_user)
from werkzeug.utils import secure_filename
import subprocess, threading, os, json, re, base64
from pathlib import Path
from datetime import datetime
import models

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "jobai-saas-secret-2026-x9z")

models.init_db()

@app.context_processor
def inject_trial():
    """Injecte les infos trial dans tous les templates."""
    if current_user.is_authenticated:
        jours, actif, plan = models.get_trial_info(current_user.id)
        return {"trial_jours": jours, "trial_actif": actif, "trial_plan": plan}
    return {"trial_jours": 30, "trial_actif": True, "trial_plan": "trial"}

# ── Flask-Login ───────────────────────────────────────────────
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Connectez-vous pour accéder au dashboard."

class User(UserMixin):
    def __init__(self, data):
        self.id       = data["id"]
        self.email    = data["email"]
        self.name     = data["name"]
        self.setup_done = data["setup_done"]

@login_manager.user_loader
def load_user(user_id):
    data = models.get_user(int(user_id))
    return User(data) if data else None

# ── Config ────────────────────────────────────────────────────
UPLOAD_FOLDER = Path(__file__).parent / "uploads"
UPLOAD_FOLDER.mkdir(exist_ok=True)
USER_DATA     = Path(__file__).parent / "user_data"
USER_DATA.mkdir(exist_ok=True)
AGENTS_DIR    = Path(__file__).parent / "agents"
PYTHON        = sys.executable
MAX_CV_SIZE   = 5 * 1024 * 1024  # 5 MB

AGENTS = {
    "job_hunter":      {"nom": "Job Hunter",       "script": "job_hunter.py",      "desc": "Scrape les offres LinkedIn, Indeed, Job Bank"},
    "orchestrateur":   {"nom": "Orchestrateur",    "script": "orchestrateur.py",   "desc": "Postule automatiquement aux offres trouvées"},
    "indeed_agent":    {"nom": "Indeed Agent",     "script": "indeed_agent.py",    "desc": "Postule sur Indeed"},
    "followup_engine": {"nom": "Follow-up",        "script": "followup_engine.py", "desc": "Envoie des relances aux recruteurs"},
    "ats_optimizer":   {"nom": "ATS Optimizer",    "script": "ats_optimizer.py",   "desc": "Optimise le CV pour chaque poste"},
    "linkedin_agent":  {"nom": "LinkedIn Post",    "script": "linkedin_agent.py",  "desc": "Publie des posts LinkedIn professionnels"},
    "profile_optimizer": {"nom": "Profil LinkedIn 10/10", "script": "profile_optimizer.py", "desc": "Optimise ton profil LinkedIn avec GPT-4o pour score 10/10"},
}

running_procs = {}  # (user_id, agent_id) → Popen

# ── Auth ──────────────────────────────────────────────────────
@app.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    return render_template("landing.html")

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        name  = request.form.get("name","").strip()
        email = request.form.get("email","").strip()
        pwd   = request.form.get("password","")
        pwd2  = request.form.get("password2","")
        if not name or not email or not pwd:
            return render_template("register.html", error="Tous les champs sont requis")
        if pwd != pwd2:
            return render_template("register.html", error="Les mots de passe ne correspondent pas")
        if len(pwd) < 6:
            return render_template("register.html", error="Mot de passe trop court (6 caractères min)")
        uid, err = models.create_user(email, pwd, name)
        if err:
            return render_template("register.html", error=err)
        user_data = models.get_user(uid)
        login_user(User(user_data))
        return redirect(url_for("setup"))
    return render_template("register.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email","").strip()
        pwd   = request.form.get("password","")
        data, err = models.verify_user(email, pwd)
        if err:
            return render_template("login.html", error=err)
        user = User(data)
        login_user(user, remember=True)
        if not data["setup_done"]:
            return redirect(url_for("setup"))
        return redirect(url_for("dashboard"))
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("index"))

# ── Setup wizard ──────────────────────────────────────────────
@app.route("/setup", methods=["GET","POST"])
@login_required
def setup():
    if request.method == "POST":
        data = {
            "gmail_address":    request.form.get("gmail_address","").strip(),
            "gmail_password":   request.form.get("gmail_password","").strip(),
            "linkedin_email":   request.form.get("linkedin_email","").strip(),
            "linkedin_password":request.form.get("linkedin_password","").strip(),
            "nom_complet":      request.form.get("nom_complet","").strip(),
            "telephone":        request.form.get("telephone","").strip(),
            "adresse":          request.form.get("adresse","").strip(),
            "ville":            request.form.get("ville","").strip(),
            "province":         request.form.get("province","").strip(),
            "profession":       request.form.get("profession","").strip(),
            "keywords":         request.form.get("keywords","").strip(),
        }
        # CV Upload — sauvegarde fichier + contenu en base (Railway = filesystem éphémère)
        cv = request.files.get("cv")
        if cv and cv.filename.lower().endswith(".pdf"):
            user_dir = UPLOAD_FOLDER / str(current_user.id)
            user_dir.mkdir(exist_ok=True)
            cv_path = user_dir / "cv.pdf"
            cv_bytes = cv.read()
            cv_path.write_bytes(cv_bytes)
            data["cv_path"]    = str(cv_path)
            data["cv_content"] = base64.b64encode(cv_bytes).decode("utf-8")
        models.save_config(current_user.id, data)
        return redirect(url_for("dashboard"))
    cfg = models.get_config(current_user.id)
    return render_template("setup.html", cfg=cfg)

# ── Dashboard ─────────────────────────────────────────────────
@app.route("/dashboard")
@login_required
def dashboard():
    if not current_user.setup_done:
        return redirect(url_for("setup"))
    stats = models.get_stats(current_user.id)
    return render_template("dashboard.html", stats=stats, active="dashboard")

# ── Agents ────────────────────────────────────────────────────
@app.route("/agents")
@login_required
def agents():
    uid     = current_user.id
    running = [aid for (u,aid) in running_procs if u == uid]
    return render_template("agents.html", agents=AGENTS, running=running, active="agents")

@app.route("/agents/run/<agent_id>", methods=["POST"])
@login_required
def run_agent(agent_id):
    uid = current_user.id
    # Vérifier trial
    jours, actif, plan = models.get_trial_info(uid)
    if not actif:
        return jsonify({"error": "Essai gratuit expiré — passez à un plan payant pour continuer."}), 403
    key = (uid, agent_id)
    if key in running_procs and running_procs[key].poll() is None:
        return jsonify({"error": "Déjà en cours"}), 400
    if agent_id not in AGENTS:
        return jsonify({"error": "Agent inconnu"}), 404

    cfg  = models.get_config(uid)
    user = models.get_user(uid)

    # Vérifier que le setup est fait
    if not user.get("setup_done"):
        return jsonify({"error": "Complétez d'abord le Setup avant de lancer un agent."}), 400

    # Vérifier identifiants LinkedIn pour les agents qui en ont besoin
    AGENTS_LINKEDIN = {"orchestrateur","indeed_agent","linkedin_agent","profile_optimizer"}
    if agent_id in AGENTS_LINKEDIN and not cfg.get("linkedin_email"):
        return jsonify({"error": "Ajoutez votre email et mot de passe LinkedIn dans le Setup."}), 400

    user_profile_dir = UPLOAD_FOLDER / str(uid) / "chrome_profile"
    user_profile_dir.mkdir(parents=True, exist_ok=True)

    # Restaurer le CV depuis la DB si le fichier a disparu (Railway filesystem éphémère)
    cv_path = cfg.get("cv_path", "")
    if cv_path and not Path(cv_path).exists():
        cv_content = models.get_cv_content(uid)
        if cv_content:
            try:
                Path(cv_path).parent.mkdir(parents=True, exist_ok=True)
                Path(cv_path).write_bytes(base64.b64decode(cv_content))
                app.logger.warning(f"[CV] Restauré depuis DB pour user {uid}: {cv_path}")
            except Exception as e:
                app.logger.error(f"[CV] Erreur restauration: {e}")

    env = os.environ.copy()
    env.update({
        # Clé OpenAI = celle du serveur (l'utilisateur ne la fournit pas)
        "OPENAI_API_KEY":    os.getenv("OPENAI_API_KEY", ""),
        "GMAIL_ADDRESS":     cfg.get("gmail_address",""),
        "GMAIL_APP_PASSWORD":cfg.get("gmail_password",""),
        "CV_PATH":           cfg.get("cv_path",""),
        "USER_ID":           str(uid),
        "USER_NAME":         cfg.get("nom_complet", user["name"]),
        "USER_PHONE":        cfg.get("telephone",""),
        "USER_ADDRESS":      cfg.get("adresse","") + " " + cfg.get("ville",""),
        "USER_KEYWORDS":     cfg.get("keywords",""),
        "USER_PROFESSION":   cfg.get("profession",""),
        "USER_EMAIL":        cfg.get("gmail_address",""),
        "PROFILE_PATH":      cfg.get("linkedin_profile_path", str(user_profile_dir)),
        "LINKEDIN_EMAIL":    cfg.get("linkedin_email",""),
        "LINKEDIN_PASSWORD": cfg.get("linkedin_password",""),
        "SAAS_API_URL":      os.getenv("RAILWAY_PUBLIC_DOMAIN", "http://localhost:8080"),
        "SAAS_USER_TOKEN":   str(uid),
        "PYTHONUNBUFFERED":  "1",
        "PYTHONIOENCODING":  "utf-8",
    })

    try:
        proc = subprocess.Popen(
            [PYTHON, "-u", str(AGENTS_DIR / AGENTS[agent_id]["script"])],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            cwd=str(AGENTS_DIR), encoding="utf-8", errors="replace",
            bufsize=1, env=env
        )
    except Exception as e:
        app.logger.error(f"Popen failed for {agent_id}: {e}")
        return jsonify({"error": f"Impossible de lancer l'agent : {e}"}), 500

    running_procs[key] = proc
    return jsonify({"status": "started"})

@app.route("/agents/stop/<agent_id>", methods=["POST"])
@login_required
def stop_agent(agent_id):
    key = (current_user.id, agent_id)
    if key in running_procs:
        running_procs[key].terminate()
        running_procs.pop(key, None)
    return jsonify({"status": "stopped"})

@app.route("/agents/stream/<agent_id>")
@login_required
def stream_agent(agent_id):
    key  = (current_user.id, agent_id)
    proc = running_procs.get(key)
    if not proc:
        def empty():
            yield "data: [ERREUR] Agent non trouvé — vérifiez la configuration (setup)\n\n"
            yield "data: [TERMINÉ]\n\n"
        return Response(stream_with_context(empty()), mimetype="text/event-stream")
    def generate():
        try:
            for line in proc.stdout:
                line = line.rstrip()
                if line:
                    app.logger.warning(f"[AGENT:{agent_id}] {line}")
                    yield f"data: {line}\n\n"
        except Exception as e:
            app.logger.error(f"[AGENT:{agent_id}] stream error: {e}")
            yield f"data: [ERREUR] {e}\n\n"
        finally:
            running_procs.pop(key, None)
        app.logger.warning(f"[AGENT:{agent_id}] TERMINÉ")
        yield "data: [TERMINÉ]\n\n"
    return Response(stream_with_context(generate()), mimetype="text/event-stream",
                    headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})

@app.route("/agents/status")
@login_required
def agents_status():
    uid = current_user.id
    status = {aid: running_procs.get((uid,aid), None) is not None and
              running_procs[(uid,aid)].poll() is None
              for aid in AGENTS if (uid,aid) in running_procs}
    return jsonify(status)

# ── Profile Optimizer approval ────────────────────────────────
@app.route("/profile/pending")
@login_required
def profile_pending():
    uid      = current_user.id
    pending  = UPLOAD_FOLDER / str(uid) / "pending_profile.json"
    if not pending.exists():
        return jsonify({"status": "none"})
    try:
        data = json.loads(pending.read_text(encoding="utf-8"))
        return jsonify(data)
    except Exception:
        return jsonify({"status": "none"})

@app.route("/profile/approve", methods=["POST"])
@login_required
def profile_approve():
    uid     = current_user.id
    pending = Path(f"C:/ai_linkedin_bot/user_data/{uid}/pending_profile.json")
    if pending.exists():
        data = json.loads(pending.read_text(encoding="utf-8"))
        data["status"] = "approved"
        pending.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return jsonify({"ok": True})

@app.route("/profile/reject", methods=["POST"])
@login_required
def profile_reject():
    uid     = current_user.id
    pending = Path(f"C:/ai_linkedin_bot/user_data/{uid}/pending_profile.json")
    if pending.exists():
        data = json.loads(pending.read_text(encoding="utf-8"))
        data["status"] = "rejected"
        pending.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return jsonify({"ok": True})

# ── Candidatures ──────────────────────────────────────────────
@app.route("/candidatures")
@login_required
def candidatures():
    q       = request.args.get("q","")
    statut  = request.args.get("statut","")
    page    = int(request.args.get("page",1))
    per     = 50
    rows, total = models.get_candidatures(current_user.id, q, statut, per, (page-1)*per)
    pages   = max(1, (total + per - 1) // per)
    return render_template("candidatures.html", rows=rows, total=total,
                           page=page, pages=pages, q=q, statut_f=statut, active="candidatures")

@app.route("/candidatures/update", methods=["POST"])
@login_required
def update_candidature():
    d = request.json
    models.update_candidature(d["id"], current_user.id, d["field"], d["value"])
    return jsonify({"status": "ok"})

# ── Settings ──────────────────────────────────────────────────
@app.route("/settings", methods=["GET","POST"])
@login_required
def settings():
    cfg = models.get_config(current_user.id)
    if request.method == "POST":
        data = {k: request.form.get(k,"").strip()
                for k in ["openai_key","gmail_address","gmail_password","nom_complet",
                           "telephone","adresse","ville","province","profession","keywords"]}
        cv = request.files.get("cv")
        if cv and cv.filename.lower().endswith(".pdf"):
            user_dir = UPLOAD_FOLDER / str(current_user.id)
            user_dir.mkdir(exist_ok=True)
            cv.save(str(user_dir / "cv.pdf"))
            data["cv_path"] = str(user_dir / "cv.pdf")
        models.save_config(current_user.id, data)
        flash("Paramètres sauvegardés !", "success")
        return redirect(url_for("settings"))
    return render_template("settings.html", cfg=cfg, active="settings")

# ── API import CSV (pour intégration agents existants) ────────
@app.route("/api/candidature", methods=["POST"])
def api_add_candidature():
    token = request.headers.get("X-User-Token","")
    try:
        uid = int(token)
    except:
        return jsonify({"error": "token invalide"}), 401
    data = request.json or {}
    models.add_candidature(uid, data)
    return jsonify({"status": "ok"})

@app.route("/api/candidatures")
def api_get_candidatures():
    token = request.headers.get("X-User-Token","")
    try:
        uid = int(token)
    except:
        return jsonify({"error": "token invalide"}), 401
    q      = request.args.get("q", "")
    statut = request.args.get("statut", "")
    rows, total = models.get_candidatures(uid, q, statut, 200, 0)
    return jsonify({"rows": rows, "total": total})

if __name__ == "__main__":
    models.init_db()
    print("=" * 55)
    print("  JobAI SaaS — démarrage")
    print("  http://localhost:5000")
    print("=" * 55)
    app.run(host="0.0.0.0", port=5000, threaded=True, debug=False)
