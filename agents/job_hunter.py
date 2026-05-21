import sys
sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
from dotenv import load_dotenv
load_dotenv()

import os
import csv
import re
import time
import random
import requests
from datetime import datetime
from pathlib import Path
from bs4 import BeautifulSoup

# ── OpenAI pour scoring ──────────────────────────────────────
try:
    from openai import OpenAI
    from pypdf import PdfReader
    _openai_ok = bool(os.getenv("OPENAI_API_KEY"))
except ImportError:
    _openai_ok = False

SEUIL_SCORE = 65  # score minimum pour retenir une offre

# ============================================================
# CONFIG
# ============================================================

_kw_env = os.getenv("USER_KEYWORDS", "")
KEYWORDS = [k.strip() for k in _kw_env.split(",") if k.strip()] or [
    "chargé de projets construction",
    "gestionnaire de projets génie civil",
    "coordinateur de chantier",
]

LOCATION   = os.getenv("USER_ADDRESS", "Ottawa, ON")
_profile   = os.getenv("PROFILE_PATH", ".")
OUTPUT_DIR = os.path.join(_profile, "offres_trouvees")
CSV_FILE   = os.path.join(OUTPUT_DIR, f"offres_{datetime.now().strftime('%Y%m%d')}.csv")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

# ============================================================
# LOGGER
# ============================================================

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

# ============================================================
# INDEED SCRAPER
# ============================================================

def chercher_indeed(keyword, location):
    offres = []
    query  = keyword.replace(" ", "+")
    loc    = location.replace(" ", "+").replace(",", "%2C")
    url    = f"https://ca.indeed.com/jobs?q={query}&l={loc}&lang=fr"

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")

        cards = soup.find_all("div", class_="job_seen_beacon")

        for card in cards[:10]:
            try:
                titre_el  = card.find("h2", class_="jobTitle")
                titre     = titre_el.get_text(strip=True) if titre_el else "N/A"

                co_el     = card.find("span", {"data-testid": "company-name"})
                company   = co_el.get_text(strip=True) if co_el else "N/A"

                loc_el    = card.find("div", {"data-testid": "text-location"})
                lieu      = loc_el.get_text(strip=True) if loc_el else location

                link_el   = card.find("a", href=True)
                lien      = "https://ca.indeed.com" + link_el["href"] if link_el else "N/A"

                offres.append({
                    "titre":    titre,
                    "company":  company,
                    "lieu":     lieu,
                    "source":   "Indeed",
                    "keyword":  keyword,
                    "lien":     lien,
                    "date":     datetime.now().strftime("%Y-%m-%d"),
                })
            except Exception:
                continue

    except Exception as e:
        log(f"  ⚠️ Indeed erreur : {e}")

    return offres

# ============================================================
# LINKEDIN SCRAPER (public jobs)
# ============================================================

def chercher_linkedin(keyword, location):
    offres = []
    query  = keyword.replace(" ", "%20")
    loc    = location.replace(" ", "%20").replace(",", "%2C")
    url    = (
        f"https://www.linkedin.com/jobs/search/"
        f"?keywords={query}&location={loc}&f_TPR=r604800"
    )

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")

        cards = soup.find_all("div", class_="base-card")

        for card in cards[:10]:
            try:
                titre_el = card.find("h3", class_="base-search-card__title")
                titre    = titre_el.get_text(strip=True) if titre_el else "N/A"

                co_el    = card.find("h4", class_="base-search-card__subtitle")
                company  = co_el.get_text(strip=True) if co_el else "N/A"

                loc_el   = card.find("span", class_="job-search-card__location")
                lieu     = loc_el.get_text(strip=True) if loc_el else location

                link_el  = card.find("a", href=True)
                lien     = link_el["href"] if link_el else "N/A"

                offres.append({
                    "titre":   titre,
                    "company": company,
                    "lieu":    lieu,
                    "source":  "LinkedIn",
                    "keyword": keyword,
                    "lien":    lien,
                    "date":    datetime.now().strftime("%Y-%m-%d"),
                })
            except Exception:
                continue

    except Exception as e:
        log(f"  ⚠️ LinkedIn erreur : {e}")

    return offres

# ============================================================
# SAUVEGARDER EN CSV
# ============================================================

def lire_cv():
    cv_path = os.getenv("CV_PATH", "")
    if not cv_path or not Path(cv_path).exists():
        return ""
    try:
        reader = PdfReader(cv_path)
        return " ".join(p.extract_text() or "" for p in reader.pages)[:1500]
    except Exception:
        return ""

def scorer_offre(client, cv_texte, offre):
    prompt = (
        "Evalue la compatibilite entre ce profil et cette offre d'emploi.\n"
        "Reponds UNIQUEMENT par un entier entre 0 et 100.\n"
        "Profil : " + cv_texte[:800] + "\n"
        "Offre : " + offre.get("titre","") + " chez " + offre.get("company","") + "\n"
        "Score :"
    )
    try:
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role":"user","content":prompt}],
            max_tokens=5
        )
        return int(re.search(r"\d+", resp.choices[0].message.content).group())
    except Exception:
        return 70

def matcher_ai(offres):
    """Score chaque offre avec GPT-4o et ne garde que celles >= SEUIL_SCORE."""
    if not _openai_ok:
        log("IA scoring desactive (pas de cle OpenAI) — toutes les offres conservees")
        for o in offres:
            o["score"] = 0
        return offres

    client   = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    cv_texte = lire_cv()
    if not cv_texte:
        log("CV introuvable — scoring desactive")
        for o in offres:
            o["score"] = 0
        return offres

    log(f"PHASE 2 - Matcher AI ({len(offres)} offres)")
    retenues = []
    for i, offre in enumerate(offres, 1):
        score = scorer_offre(client, cv_texte, offre)
        offre["score"] = score
        statut = "OK" if score >= SEUIL_SCORE else ("~" if score >= 50 else "X")
        log(f"  [{i}/{len(offres)}] {statut} {score}/100 {offre.get('titre','')[:45]}")
        if score >= SEUIL_SCORE:
            retenues.append(offre)
    log(f"{len(retenues)} offres retenues (score >= {SEUIL_SCORE})")
    return retenues

def sauvegarder_csv(offres):
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    existe = Path(CSV_FILE).exists()
    with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "titre", "company", "lieu", "source", "keyword", "lien", "date", "score"
        ], extrasaction="ignore")
        if not existe:
            writer.writeheader()
        writer.writerows(offres)

def sauvegarder_saas(offres):
    """Envoie les offres à l'API SaaS pour les sauvegarder en base."""
    api_url   = os.getenv("SAAS_API_URL", "")
    user_token = os.getenv("SAAS_USER_TOKEN", "")
    if not api_url or not user_token:
        return
    # Assurer le bon format d'URL
    if not api_url.startswith("http"):
        api_url = "https://" + api_url
    ok = 0
    for o in offres:
        try:
            requests.post(
                f"{api_url}/api/candidature",
                json={
                    "date":       o.get("date", datetime.now().strftime("%Y-%m-%d %H:%M")),
                    "entreprise": o.get("company", ""),
                    "poste":      o.get("titre", ""),
                    "lien":       o.get("lien", ""),
                    "plateforme": o.get("source", ""),
                    "score":      str(o.get("score", 0)),
                    "statut":     "A postuler",
                },
                headers={"X-User-Token": user_token},
                timeout=5
            )
            ok += 1
        except Exception:
            pass
    if ok:
        log(f"  SaaS : {ok} offres sauvegardées en base")

# ============================================================
# DÉDUPLIQUER
# ============================================================

def deduplicer(offres):
    vus  = set()
    uniq = []
    for o in offres:
        cle = f"{o['titre'].lower()}_{o['company'].lower()}"
        if cle not in vus:
            vus.add(cle)
            uniq.append(o)
    return uniq

# ============================================================
# AFFICHER RÉSULTATS
# ============================================================

def afficher(offres):
    print()
    print("=" * 65)
    print(f"  {'TITRE':<35} {'ENTREPRISE':<20} SOURCE")
    print("=" * 65)
    for o in offres:
        titre   = o['titre'][:34]
        company = o['company'][:19]
        print(f"  {titre:<35} {company:<20} {o['source']}")
    print("=" * 65)
    print(f"  TOTAL : {len(offres)} offres trouvées")
    print("=" * 65)
    print()

# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    log("🚀 Job Hunter démarré")
    log(f"📍 Localisation : {LOCATION}")
    log(f"🔑 {len(KEYWORDS)} mots-clés configurés")
    print()

    toutes_offres = []

    for i, keyword in enumerate(KEYWORDS, 1):
        log(f"[{i}/{len(KEYWORDS)}] 🔍 '{keyword}'")

        # Indeed
        log("  📡 Indeed...")
        offres_indeed = chercher_indeed(keyword, LOCATION)
        log(f"  ✅ {len(offres_indeed)} offres Indeed")
        toutes_offres.extend(offres_indeed)

        # LinkedIn
        log("  📡 LinkedIn...")
        offres_linkedin = chercher_linkedin(keyword, LOCATION)
        log(f"  ✅ {len(offres_linkedin)} offres LinkedIn")
        toutes_offres.extend(offres_linkedin)

        # Délai humain entre les requêtes
        attente = random.randint(3, 7)
        log(f"  ⏳ Pause {attente}s...")
        time.sleep(attente)
        print()

    # Dédupliquer
    toutes_offres = deduplicer(toutes_offres)
    log(f"PHASE 1 terminee : {len(toutes_offres)} offres uniques")

    # Scorer avec GPT-4o et filtrer
    toutes_offres = matcher_ai(toutes_offres)

    if not toutes_offres:
        log("Aucune offre retenue apres scoring.")
    else:
        # Sauvegarder CSV local
        sauvegarder_csv(toutes_offres)
        log(f"Sauvegarde CSV : {CSV_FILE}")

        # Sauvegarder en base SaaS
        sauvegarder_saas(toutes_offres)

        # Afficher
        afficher(toutes_offres)

    log("Job Hunter termine !")