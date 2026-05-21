#!/usr/bin/env python3
"""
JobAI Local Runner
==================
Lance l'orchestrateur sur TON PC (IP résidentielle).
LinkedIn ne bloque pas les IP résidentielles → zéro CAPTCHA.
Les résultats sont envoyés automatiquement au dashboard Railway.

Usage :
  python local_runner.py                  # orchestrateur (défaut)
  python local_runner.py followup         # follow-up engine
  python local_runner.py ats              # ATS optimizer
  python local_runner.py job_hunter       # job hunter
"""
import os, sys, subprocess, json, base64, requests
from pathlib import Path
from getpass import getpass
from datetime import datetime

# ── Config ────────────────────────────────────────────────────
CONFIG_FILE  = Path.home() / ".jobai_local.json"
CV_FILE      = Path.home() / ".jobai_cv.pdf"
PROFILE_DIR  = Path.home() / ".jobai_chrome"
AGENTS_DIR   = Path(__file__).parent / "agents"

AGENT_MAP = {
    "orchestrateur": "orchestrateur.py",
    "followup":      "followup_engine.py",
    "ats":           "ats_optimizer.py",
    "job_hunter":    "job_hunter.py",
    "indeed":        "indeed_agent.py",
    "linkedin":      "linkedin_agent.py",
    "profile":       "profile_optimizer.py",
}

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

# ── Chargement / demande de config ────────────────────────────
def charger_config():
    if CONFIG_FILE.exists():
        cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        log(f"Config : {cfg['saas_url']} (user {cfg['user_id']})")
        return cfg

    print()
    print("=" * 55)
    print("  JobAI Local Runner — Première configuration")
    print("=" * 55)
    saas_url = input("\nURL Railway (ex: https://jobai-pro-production.up.railway.app) : ").strip().rstrip("/")
    email    = input("Email JobAI : ").strip()
    password = getpass("Mot de passe JobAI : ")

    try:
        resp = requests.post(
            f"{saas_url}/api/login",
            json={"email": email, "password": password},
            timeout=10
        )
        data = resp.json()
        if "error" in data:
            print(f"\n❌ Erreur : {data['error']}")
            sys.exit(1)
    except Exception as e:
        print(f"\n❌ Impossible de joindre Railway : {e}")
        sys.exit(1)

    cfg = {"saas_url": saas_url, "user_id": data["user_id"]}
    CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    print(f"\n✅ Connecté en tant que {data['name']} !")
    print(f"   Config sauvegardée dans {CONFIG_FILE}")
    return cfg

# ── Récupération config depuis Railway ────────────────────────
def recuperer_config(saas_url, user_id):
    log("Récupération de la config depuis Railway...")
    try:
        resp = requests.get(
            f"{saas_url}/api/my-config",
            headers={"X-User-Token": str(user_id)},
            timeout=15
        )
        if resp.status_code != 200:
            print(f"❌ Erreur Railway ({resp.status_code}): {resp.text[:200]}")
            sys.exit(1)
        return resp.json()
    except Exception as e:
        print(f"❌ Connexion Railway impossible : {e}")
        sys.exit(1)

# ── Restaurer le CV depuis la DB ──────────────────────────────
def restaurer_cv(cfg):
    cv_b64 = cfg.get("cv_content", "")
    if cv_b64:
        try:
            CV_FILE.write_bytes(base64.b64decode(cv_b64))
            log(f"CV restauré : {CV_FILE}")
            return str(CV_FILE)
        except Exception as e:
            log(f"Erreur restauration CV : {e}")
    cv_path = cfg.get("cv_path", "")
    if cv_path and Path(cv_path).exists():
        return cv_path
    log("⚠️  CV non trouvé — l'agent continuera sans CV")
    return str(CV_FILE)

# ── Construire l'environnement ────────────────────────────────
def construire_env(cfg, saas_url, user_id, cv_path):
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update({
        "OPENAI_API_KEY":        cfg.get("openai_key", os.getenv("OPENAI_API_KEY", "")),
        "GMAIL_ADDRESS":         cfg.get("gmail_address", ""),
        "GMAIL_APP_PASSWORD":    cfg.get("gmail_password", ""),
        "CV_PATH":               cv_path,
        "USER_NAME":             cfg.get("nom_complet", ""),
        "USER_PHONE":            cfg.get("telephone", ""),
        "USER_ADDRESS":          (cfg.get("adresse", "") + " " + cfg.get("ville", "")).strip(),
        "USER_KEYWORDS":         cfg.get("keywords", ""),
        "USER_PROFESSION":       cfg.get("profession", ""),
        "USER_EMAIL":            cfg.get("gmail_address", ""),
        "PROFILE_PATH":          str(PROFILE_DIR),
        "LINKEDIN_EMAIL":        cfg.get("linkedin_email", ""),
        "LINKEDIN_PASSWORD":     cfg.get("linkedin_password", ""),
        "LINKEDIN_LI_AT":        cfg.get("linkedin_li_at", ""),
        "LINKEDIN_COOKIES_JSON": cfg.get("linkedin_cookies_json", ""),
        "SAAS_API_URL":          saas_url,
        "SAAS_USER_TOKEN":       str(user_id),
        "SAAS_USER_ID":          str(user_id),
        "PYTHONUNBUFFERED":      "1",
        "PYTHONIOENCODING":      "utf-8",
        # Pas de Smartproxy en local — IP résidentielle directe
        "SMARTPROXY_USER":       "",
        "SMARTPROXY_PASS":       "",
    })
    return env

# ── MAIN ──────────────────────────────────────────────────────
def main():
    agent_key = sys.argv[1] if len(sys.argv) > 1 else "orchestrateur"
    if agent_key not in AGENT_MAP:
        print(f"Agent inconnu : {agent_key}")
        print(f"Agents disponibles : {', '.join(AGENT_MAP.keys())}")
        sys.exit(1)

    script = AGENTS_DIR / AGENT_MAP[agent_key]
    if not script.exists():
        print(f"❌ Script introuvable : {script}")
        sys.exit(1)

    print()
    print("=" * 55)
    print(f"  JobAI Local Runner")
    print(f"  Agent : {agent_key}")
    print(f"  IP locale résidentielle — LinkedIn non bloqué")
    print("=" * 55)
    print()

    local_cfg  = charger_config()
    saas_url   = local_cfg["saas_url"]
    user_id    = local_cfg["user_id"]

    user_cfg   = recuperer_config(saas_url, user_id)
    cv_path    = restaurer_cv(user_cfg)
    env        = construire_env(user_cfg, saas_url, user_id, cv_path)

    log(f"OpenAI : {'OK' if env.get('OPENAI_API_KEY') else 'MANQUANT'}")
    log(f"LinkedIn : {env.get('LINKEDIN_EMAIL') or 'MANQUANT'}")
    log(f"CV : {cv_path}")
    log(f"Dashboard : {saas_url}/dashboard")
    print()

    proc = subprocess.run(
        [sys.executable, "-u", str(script)],
        env=env,
        cwd=str(AGENTS_DIR)
    )

    print()
    print("=" * 55)
    print(f"  Terminé — Code : {proc.returncode}")
    print(f"  Résultats visibles sur : {saas_url}/candidatures")
    print("=" * 55)

if __name__ == "__main__":
    main()
