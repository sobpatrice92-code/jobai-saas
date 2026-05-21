import sys
sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
from dotenv import load_dotenv
load_dotenv()

from openai import OpenAI
from pypdf import PdfReader
from playwright.async_api import async_playwright
import asyncio, random, os, csv, smtplib, re, requests as _req
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
from pathlib import Path

_openai_key    = os.getenv("OPENAI_API_KEY", "")
client         = OpenAI(api_key=_openai_key) if _openai_key else None
CV_PATH        = os.getenv("CV_PATH", "cv.pdf")
GMAIL_ADDRESS  = os.getenv("GMAIL_ADDRESS")
GMAIL_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
EMAIL_NOTIF    = os.getenv("GMAIL_ADDRESS")

SMARTPROXY_USER = os.getenv("SMARTPROXY_USER", "")
SMARTPROXY_PASS = os.getenv("SMARTPROXY_PASS", "")
SAAS_USER_ID    = os.getenv("SAAS_USER_ID", "0")

USER_NAME         = os.getenv("USER_NAME", "Candidat")
USER_EMAIL_ENV    = os.getenv("USER_EMAIL", os.getenv("GMAIL_ADDRESS", ""))
USER_PHONE        = os.getenv("USER_PHONE", "")
USER_ADDR         = os.getenv("USER_ADDRESS", "Ottawa, Ontario")
USER_PROFESSION   = os.getenv("USER_PROFESSION", "professionnel")
LINKEDIN_EMAIL    = os.getenv("LINKEDIN_EMAIL", "")
LINKEDIN_PASSWORD = os.getenv("LINKEDIN_PASSWORD", "")
HEADLESS          = os.getenv("DISPLAY", "") == ""

_parts  = USER_NAME.split()
_prenom = " ".join(_parts[:-1]) if len(_parts) > 1 else USER_NAME
_nom    = _parts[-1] if len(_parts) > 1 else ""
_ville  = USER_ADDR.split(",")[0].strip() if "," in USER_ADDR else USER_ADDR

OUTPUT_DIR  = os.path.join(os.getenv("PROFILE_PATH", "."), "candidatures_envoyees")
SEUIL_SCORE = 65

CANDIDAT = {
    "prenom":      _prenom,
    "nom":         _nom,
    "nom_complet": USER_NAME,
    "email":       USER_EMAIL_ENV,
    "telephone":   USER_PHONE,
    "ville":       _ville,
    "province":    "Ontario",
}

KEYWORDS = [k.strip() for k in os.getenv("USER_KEYWORDS", "").split(",") if k.strip()] or [
    "chargé de projets construction",
    "gestionnaire projets génie civil",
    "coordinateur de chantier",
    "technicien génie civil",
    "estimateur construction",
]

EMAILS_RH = {
    "ville d'ottawa":        "recrutement@ottawa.ca",
    "city of ottawa":        "recrutement@ottawa.ca",
    "ville de gatineau":     "rh@gatineau.ca",
    "defence construction":  "careers@dcc-cdc.gc.ca",
    "bank of canada":        "careers@bankofcanada.ca",
    "banque du canada":      "careers@bankofcanada.ca",
    "stantec":               "careers@stantec.com",
    "wsp":                   "careers@wsp.com",
    "aecom":                 "careers@aecom.com",
    "ghd":                   "careers@ghd.com",
    "hdr":                   "careers@hdrinc.com",
    "cima":                  "carrieres@cima.ca",
    "exp":                   "carrieres@exp.com",
    "artelia":               "recrutement@artelia.com",
    "vinci":                 "recrutement@vinci.com",
    "bpa":                   "rh@bpa.ca",
    "bird construction":     "hr@bird.ca",
    "broccolini":            "rh@broccolini.ca",
    "pcl":                   "careers@pcl.com",
    "ellisdon":              "careers@ellisdon.com",
    "coffrages synergy":     "rh@coffragessynergy.com",
    "constructions genix":   "rh@genix.ca",
    "groupe emd batimo":     "rh@emdbatimo.com",
    "ebc":                   "carrieres@ebc.ca",
    "bpdl":                  "rh@bpdl.ca",
    "precision drain":       "info@precisiondrain.ca",
    "polygon":               "rh@polygonrestauration.ca",
    "parisien":              "rh@parisien.ca",
    "hays":                  "ottawa@hays.com",
    "randstad":              "ottawa@randstad.ca",
    "robert half":           "ottawa@roberthalf.com",
    "adecco":                "ottawa@adecco.ca",
    "michael page":          "canada@michaelpage.com",
}

CSV_COLONNES = ["date", "entreprise", "poste", "lien", "plateforme", "score", "statut"]

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def lire_pdf(path):
    reader = PdfReader(path)
    return "\n".join(p.extract_text() or "" for p in reader.pages).strip()

def scorer_offre(cv_texte, titre, description):
    prompt = (
        "Evalue compatibilite profil/offre. Reponds UNIQUEMENT par un nombre 0-100.\n"
        "Profil:" + cv_texte[:600] + "\nOffre:" + titre + "\n" + description[:300] + "\nScore:"
    )
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=5
    )
    try:
        return int(re.search(r'\d+', resp.choices[0].message.content).group())
    except Exception:
        return 50

def generer_lettre(cv_texte, titre, company, description=""):
    date_str = datetime.now().strftime("%d %B %Y")
    entete = (
        USER_NAME + "\n"
        + USER_ADDR + "\n"
        + "Tel : " + USER_PHONE + " | Email : " + USER_EMAIL_ENV + "\n\n"
        + date_str + "\n\n"
        + "Objet : Candidature - " + titre + " chez " + company + "\n\n"
        + "Madame, Monsieur,\n\n"
    )
    prompt = (
        "Redige UNIQUEMENT les 3 paragraphes du corps en francais. INTERDICTION de crochets [X].\n"
        "P1 : interet pour " + titre + " chez " + company + "\n"
        "P2 : 2 realisations chiffrees lies a " + USER_PROFESSION + "\n"
        "P3 : disponibilite + appel a action\n"
        "Profil : " + cv_texte[:500] + "\n"
        "Poste : " + titre + " chez " + company
    )
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=500
    )
    corps = resp.choices[0].message.content.strip()
    corps = "\n".join([l for l in corps.split("\n") if not re.search(r"\[.+?\]", l)])
    return (entete + corps + "\n\nCordialement,\n\n"
            + USER_NAME + "\n" + USER_PHONE + " | " + USER_EMAIL_ENV + "\n" + USER_ADDR)

def trouver_email_rh(company):
    company_lower = company.lower()
    for cle, email in EMAILS_RH.items():
        if cle in company_lower or company_lower in cle:
            return email
    return None

def construire_email_auto(company):
    nom = company.lower()
    nom = re.sub(r'\s+(inc|ltd|corp|sarl|canada|construction|group|groupe)\s*$', '', nom)
    nom = re.sub(r'[^a-z0-9]', '', nom)[:20]
    if not nom:
        return None
    return f"careers@{nom}.ca"

def envoyer_email(offre, lettre, email_dest):
    try:
        msg = MIMEMultipart()
        msg["From"]    = GMAIL_ADDRESS
        msg["To"]      = email_dest
        msg["Subject"] = "Candidature — " + offre.get("titre","") + " | " + offre.get("company","")
        corps = lettre if email_dest != EMAIL_NOTIF else (
            "[IndeedAgent] " + offre.get("titre","") + " | " + offre.get("company","") +
            " - " + str(offre.get("score",0)) + "/100\nLien : " + offre.get("lien","") +
            "\n\n" + "-"*40 + "\n" + lettre
        )
        msg.attach(MIMEText(corps, "plain", "utf-8"))
        cv = Path(CV_PATH)
        if cv.exists():
            with open(cv, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
            encoders.encode_base64(part)
            safe_name = re.sub(r'[^a-zA-Z_]', '_', USER_NAME.replace(' ', '_'))
            part.add_header("Content-Disposition", f"attachment; filename=\"CV_{safe_name}.pdf\"")
            msg.attach(part)
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_ADDRESS, GMAIL_PASSWORD)
            server.sendmail(GMAIL_ADDRESS, email_dest, msg.as_string())
        return True
    except Exception as e:
        log(f"  Email erreur : {str(e)[:50]}")
        return False

def sauvegarder_suivi(offre, statut):
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    csv_path = Path(OUTPUT_DIR) / "suivi_candidatures.csv"
    ecrire_entete = True
    if csv_path.exists():
        try:
            with open(csv_path, "r", encoding="utf-8") as f:
                if "plateforme" in f.readline():
                    ecrire_entete = False
        except Exception:
            pass
    try:
        with open(csv_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLONNES)
            if ecrire_entete:
                writer.writeheader()
            writer.writerow({
                "date":       datetime.now().strftime("%Y-%m-%d %H:%M"),
                "plateforme": offre.get("plateforme", "Indeed"),
                "entreprise": offre.get("company", ""),
                "poste":      offre.get("titre", ""),
                "lien":       offre.get("lien", ""),
                "score":      offre.get("score", 0),
                "statut":     statut,
            })
    except Exception as e:
        log(f"  CSV erreur : {str(e)[:50]}")

def sauvegarder_saas(offre, statut):
    api_url = os.getenv("SAAS_API_URL", "")
    token   = os.getenv("SAAS_USER_TOKEN", "")
    if not api_url or not token:
        return
    if not api_url.startswith("http"):
        api_url = "https://" + api_url
    try:
        _req.post(
            f"{api_url}/api/candidature",
            json={
                "date":       datetime.now().strftime("%Y-%m-%d %H:%M"),
                "entreprise": offre.get("company", ""),
                "poste":      offre.get("titre", ""),
                "lien":       offre.get("lien", ""),
                "plateforme": offre.get("plateforme", "Indeed"),
                "score":      str(offre.get("score", 0)),
                "statut":     statut,
            },
            headers={"X-User-Token": token},
            timeout=5
        )
    except Exception:
        pass

async def postuler_offre(page, offre, lettre):
    lien    = offre.get("lien", "")
    company = offre.get("company", "")

    if not lien:
        email_rh = trouver_email_rh(company) or construire_email_auto(company)
        if email_rh:
            ok = envoyer_email(offre, lettre, email_rh)
            if ok:
                log(f"  -> Email direct RH : {email_rh}")
                return "Email direct RH"
        envoyer_email(offre, lettre, EMAIL_NOTIF)
        return "Email suivi"

    try:
        await page.goto(lien, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)

        champs = [
            (["input[name*='firstName']","input[id*='first']","input[placeholder*='First']"], CANDIDAT["prenom"]),
            (["input[name*='lastName']","input[id*='last']","input[placeholder*='Last']"], CANDIDAT["nom"]),
            (["input[type='email']","input[name*='email']"], CANDIDAT["email"]),
            (["input[type='tel']","input[name*='phone']"], CANDIDAT["telephone"]),
            (["input[name*='city']","input[placeholder*='City']"], CANDIDAT["ville"]),
        ]
        for selecteurs, valeur in champs:
            for sel in selecteurs:
                try:
                    el = page.locator(sel).first
                    if await el.count() > 0 and await el.is_visible():
                        await el.fill(valeur)
                        await asyncio.sleep(0.3)
                        break
                except Exception:
                    pass

        try:
            fi = page.locator("input[type='file']").first
            if await fi.count() > 0 and Path(CV_PATH).exists():
                await fi.set_input_files(CV_PATH)
                await asyncio.sleep(2)
                log("    CV uploade")
        except Exception:
            pass

        for sel in ["textarea[name*='cover']","textarea[name*='lettre']","textarea"]:
            try:
                ta = page.locator(sel).first
                if await ta.count() > 0 and await ta.is_visible():
                    await ta.fill(lettre[:2000])
                    break
            except Exception:
                pass

        labels_submit = ["soumettre","submit","envoyer","postuler","apply now","send"]
        labels_next   = ["suivant","next","continuer"]
        labels_excl   = ["annuler","cancel","retour","back"]

        for etape in range(1, 6):
            await asyncio.sleep(2)
            buttons = page.locator("button, input[type='submit']")
            count   = await buttons.count()

            soumis = False
            for i in range(count):
                try:
                    b = buttons.nth(i)
                    if not await b.is_visible(): continue
                    t = (await b.inner_text()).strip().lower()
                    if any(ex in t for ex in labels_excl): continue
                    if any(lb in t for lb in labels_submit):
                        await b.click()
                        await asyncio.sleep(3)
                        log(f"    Soumis etape {etape} : '{t}'")
                        return "Formulaire soumis"
                except Exception:
                    pass

            for i in range(count):
                try:
                    b = buttons.nth(i)
                    if not await b.is_visible(): continue
                    t = (await b.inner_text()).strip().lower()
                    if any(ex in t for ex in labels_excl): continue
                    if any(lb in t for lb in labels_next):
                        await b.click()
                        await asyncio.sleep(2)
                        soumis = True
                        break
                except Exception:
                    pass
            if not soumis:
                break

    except Exception as e:
        log(f"  Erreur formulaire : {str(e)[:60]}")

    email_rh = trouver_email_rh(company) or construire_email_auto(company)
    if email_rh:
        ok = envoyer_email(offre, lettre, email_rh)
        if ok:
            log(f"  -> Email direct RH : {email_rh}")
            return "Email direct RH"

    envoyer_email(offre, lettre, EMAIL_NOTIF)
    return "Email suivi"

async def run():
    print()
    print("="*60)
    print("  INDEED AGENT v2 — 100% Automatique")
    print("  Indeed · Job Bank Canada · Workopolis")
    print("="*60)

    if not Path(CV_PATH).exists():
        log(f"CV non trouve : {CV_PATH}")
        return
    cv_texte = lire_pdf(CV_PATH)
    log(f"CV charge ({len(cv_texte)} car)")

    all_offres = []
    _args = ["--no-sandbox", "--disable-dev-shm-usage"] if HEADLESS else []

    async with async_playwright() as p:
        _launch_args = ["--no-sandbox", "--disable-dev-shm-usage"]
        _ctx_kwargs = dict(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
        )
        if SMARTPROXY_USER and SMARTPROXY_PASS:
            _ctx_kwargs["proxy"] = {
                "server":   "http://gate.smartproxy.com:10001",
                "username": SMARTPROXY_USER + "-session-u" + SAAS_USER_ID,
                "password": SMARTPROXY_PASS,
            }
        browser = await p.chromium.launch(headless=True, args=_launch_args)
        context = await browser.new_context(**_ctx_kwargs)
        page = await context.new_page()

        log("PHASE 1 - Scraping Indeed")
        for kw in KEYWORDS:
            log(f"  -> {kw}")
            url = f"https://ca.indeed.com/jobs?q={kw.replace(' ', '+')}&l={_ville.replace(' ', '+')}%2C+ON&fromage=7"
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(random.randint(2000, 3500) / 1000)
                cards = await page.query_selector_all(".job_seen_beacon")
                for card in cards[:10]:
                    try:
                        titre_el   = await card.query_selector("h2.jobTitle span")
                        company_el = await card.query_selector("[data-testid='company-name']")
                        lien_el    = await card.query_selector("h2 a")
                        desc_el    = await card.query_selector(".job-snippet")
                        if titre_el and company_el:
                            titre   = (await titre_el.inner_text()).strip()
                            company = (await company_el.inner_text()).strip()
                            lien, desc = "", ""
                            if lien_el:
                                href = await lien_el.get_attribute("href")
                                lien = f"https://ca.indeed.com{href}" if href and href.startswith("/") else href or ""
                            if desc_el:
                                desc = (await desc_el.inner_text()).strip()
                            if titre and company:
                                all_offres.append({"titre": titre, "company": company, "lien": lien, "description": desc, "plateforme": "Indeed"})
                    except Exception:
                        pass
                log(f"    {len(cards)} offres")
            except Exception as e:
                log(f"    Erreur : {str(e)[:60]}")
            await asyncio.sleep(random.randint(1000, 2000) / 1000)

        log("PHASE 1b - Scraping Job Bank Canada")
        for kw in KEYWORDS[:3]:
            log(f"  -> {kw}")
            url = f"https://www.jobbank.gc.ca/jobsearch/jobsearch?searchstring={kw.replace(' ', '+')}&locationstring={_ville.replace(' ', '+')}%2C+ON"
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(2)
                articles = await page.query_selector_all("article.resultJobItem")
                for article in articles[:8]:
                    try:
                        titre_el   = await article.query_selector("span.noctitle, h3.title")
                        company_el = await article.query_selector("li.business span")
                        lien_el    = await article.query_selector("a")
                        if titre_el:
                            titre   = (await titre_el.inner_text()).strip()
                            company = (await company_el.inner_text()).strip() if company_el else "N/A"
                            lien    = ""
                            if lien_el:
                                href = await lien_el.get_attribute("href")
                                lien = f"https://www.jobbank.gc.ca{href}" if href and href.startswith("/") else href or ""
                            if titre:
                                all_offres.append({"titre": titre, "company": company, "lien": lien, "description": "", "plateforme": "Job Bank"})
                    except Exception:
                        pass
            except Exception as e:
                log(f"    Erreur : {str(e)[:60]}")

        await browser.close()

    vus, uniques = set(), []
    for o in all_offres:
        key = o["titre"][:18].lower() + o["company"][:8].lower()
        if key not in vus:
            vus.add(key)
            uniques.append(o)
    log(f"{len(uniques)} offres uniques")

    log("PHASE 2 - Scoring IA")
    retenues = []
    for i, offre in enumerate(uniques, 1):
        score = scorer_offre(cv_texte, offre["titre"], offre["description"])
        offre["score"] = score
        emoji = "OK" if score >= 75 else "~" if score >= SEUIL_SCORE else "X"
        log(f"  [{i}/{len(uniques)}] {emoji} {score}/100 {offre['titre'][:35]} | {offre['company'][:20]}")
        if score >= SEUIL_SCORE:
            retenues.append(offre)
    log(f"{len(retenues)} offres retenues")

    if not retenues:
        log("Aucune offre retenue")
        return

    log("PHASE 3 - Generation lettres")
    for offre in retenues:
        offre["lettre"] = generer_lettre(cv_texte, offre["titre"], offre["company"], offre["description"])
        log(f"  Lettre OK : {offre['company']}")

    log("PHASE 4 - Candidatures 100% automatique")
    stats = {"formulaire": 0, "email_rh": 0, "email_suivi": 0}

    async with async_playwright() as p:
        _apply_kwargs = dict(headless=HEADLESS,
                             args=["--no-sandbox", "--disable-dev-shm-usage"] if HEADLESS else [])
        _apply_ctx = {}
        if SMARTPROXY_USER and SMARTPROXY_PASS:
            _apply_ctx["proxy"] = {
                "server":   "http://gate.smartproxy.com:10001",
                "username": SMARTPROXY_USER + "-session-u" + SAAS_USER_ID,
                "password": SMARTPROXY_PASS,
            }
        browser = await p.chromium.launch(**_apply_kwargs)
        context = await browser.new_context(**_apply_ctx)
        page    = await context.new_page()

        for i, offre in enumerate(retenues, 1):
            log(f"[{i}/{len(retenues)}] {offre['company']} - {offre['titre'][:35]}")
            lettre = offre.get("lettre", "")
            statut = await postuler_offre(page, offre, lettre)
            sauvegarder_suivi(offre, statut)
            sauvegarder_saas(offre, statut)

            if "soumis" in statut.lower():
                stats["formulaire"] += 1
            elif "direct" in statut.lower():
                stats["email_rh"] += 1
            else:
                stats["email_suivi"] += 1

            await asyncio.sleep(random.randint(2000, 4000) / 1000)

        await browser.close()

    total = sum(stats.values())
    taux  = round((stats["formulaire"] + stats["email_rh"]) / total * 100) if total > 0 else 0

    print()
    print("="*60)
    print("  RESULTATS INDEED AGENT v2")
    print(f"  Formulaire soumis : {stats['formulaire']}")
    print(f"  Email direct RH   : {stats['email_rh']}")
    print(f"  Email suivi       : {stats['email_suivi']}")
    print(f"  TOTAL             : {total}")
    print(f"  TAUX DE SUCCES    : {taux}%")
    print("="*60)
    log("TERMINE !")

if __name__ == "__main__":
    asyncio.run(run())
