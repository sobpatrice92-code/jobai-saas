import sys
sys.stdout.reconfigure(encoding="utf-8")
from dotenv import load_dotenv
load_dotenv()

import os
import csv
import time
import random
import requests
from datetime import datetime
from pathlib import Path
from bs4 import BeautifulSoup

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

def sauvegarder_csv(offres):
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    existe = Path(CSV_FILE).exists()

    with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "titre", "company", "lieu", "source", "keyword", "lien", "date"
        ])
        if not existe:
            writer.writeheader()
        writer.writerows(offres)

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
    log(f"🎯 {len(toutes_offres)} offres uniques trouvées")

    # Sauvegarder
    sauvegarder_csv(toutes_offres)
    log(f"💾 Sauvegardé : {CSV_FILE}")

    # Afficher
    afficher(toutes_offres)
    log("✅ Job Hunter terminé !")
    log(f"📁 Résultats dans : {OUTPUT_DIR}/")