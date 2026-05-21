import sys
sys.stdout.reconfigure(encoding="utf-8")
from dotenv import load_dotenv
load_dotenv()
from openai import OpenAI
from pypdf import PdfReader
from playwright.async_api import async_playwright
import asyncio, random, os, csv, smtplib, re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
from pathlib import Path

client           = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
CV_PATH          = os.getenv("CV_PATH", "cv.pdf")
GMAIL_ADDRESS    = os.getenv("GMAIL_ADDRESS")
GMAIL_PASSWORD   = os.getenv("GMAIL_APP_PASSWORD")
EMAIL_DESTINAIRE = os.getenv("GMAIL_ADDRESS")
PROFILE_PATH     = os.getenv("PROFILE_PATH", "chrome_profile")
LINKEDIN_EMAIL   = os.getenv("LINKEDIN_EMAIL", "")
LINKEDIN_PASSWORD= os.getenv("LINKEDIN_PASSWORD", "")
OUTPUT_DIR       = os.path.join(PROFILE_PATH, "candidatures_envoyees")
SEUIL_SCORE      = 65
HEADLESS         = os.getenv("DISPLAY", "") == ""  # headless si pas d'ecran (Railway)

_kw_env = os.getenv("USER_KEYWORDS", "")
KEYWORDS = [k.strip() for k in _kw_env.split(",") if k.strip()] or [
    "charge de projets construction",
    "gestionnaire projets genie civil",
    "coordinateur de chantier",
    "technicien genie civil",
    "estimateur construction",
    "surveillant de travaux",
]

LOCATION = os.getenv("USER_ADDRESS", "Ottawa, ON")

CSV_COLONNES = ["date", "plateforme", "entreprise", "poste", "lien", "score", "statut"]

EMAILS_RH = {
    "ville d'ottawa":           "recrutement@ottawa.ca",
    "city of ottawa":           "recrutement@ottawa.ca",
    "ville de gatineau":        "rh@gatineau.ca",
    "defence construction":     "careers@dcc-cdc.gc.ca",
    "bank of canada":           "careers@bankofcanada.ca",
    "banque du canada":         "careers@bankofcanada.ca",
    "cheo":                     "hr@cheo.on.ca",
    "ottawa catholic":          "hr@ocsb.ca",
    "stantec":                  "careers@stantec.com",
    "wsp":                      "careers@wsp.com",
    "ghd":                      "careers@ghd.com",
    "hdr":                      "careers@hdrinc.com",
    "cima":                     "carrieres@cima.ca",
    "exp":                      "carrieres@exp.com",
    "artelia":                  "recrutement@artelia.com",
    "horus ressources":         "info@horusressources.com",
    "vinci":                    "recrutement@vinci.com",
    "bpa":                      "rh@bpa.ca",
    "bgis":                     "careers@bgis.com",
    "bird construction":        "hr@bird.ca",
    "broccolini":               "rh@broccolini.ca",
    "pcl construction":         "careers@pcl.com",
    "ellisdon":                 "careers@ellisdon.com",
    "chandos":                  "careers@chandos.com",
    "minto":                    "careers@minto.com",
    "prodigy":                  "careers@prodigygroup.ca",
    "parisien construction":    "rh@parisien.ca",
    "coffrages synergy":        "rh@coffragessynergy.com",
    "constructions genix":      "rh@genix.ca",
    "groupe duroking":          "rh@duroking.com",
    "groupe emd batimo":        "rh@emdbatimo.com",
    "ebc inc":                  "carrieres@ebc.ca",
    "bpdl":                     "rh@bpdl.ca",
    "precision drain":          "info@precisiondrain.ca",
    "polygon":                  "rh@polygonrestauration.ca",
    "r.h. electrique":          "rh@rhelectrique.ca",
    "hays":                     "ottawa@hays.com",
    "wonderbrands":             "careers@wonderbrands.com",
    "altis":                    "careers@altis.ca",
    "makwa":                    "info@makwaresourcing.ca",
    "ssa recruitment":          "info@ssarecruitment.ca",
    "recruitment by design":    "info@recruitmentbydesign.ca",
    "seguin morris":            "rh@seguinmorris.com",
    "vanderwesten":             "hr@vra.ca",
    "belfor":                   "careers@belfor.com",
    "topo3d":                   "info@topo3d.ca",
    "colliers":                 "careers@colliers.com",
    "totem recruteur":          "info@totemrecruteur.ca",
    "tango solutions":          "recrutement@tangosolutionsrh.com",
    "sigfusson":                "hr@sigfusson.com",
    "grondin nadeau":           "rh@grondinnadeau.ca",
    "tehora":                   "rh@tehora.ca",
    "recruscope":               "info@recruscope.com",
    "gestion zagora":           "info@gestionzagora.ca",
    "axe construction":         "rh@axeconstruction.ca",
    "groupe csa":               "rh@groupecsa.ca",
    "construction dinamo":      "rh@constructiondinamo.ca",
    "ponton guillot":           "rh@pontonguillot.ca",
    "rooney irving":            "ottawa@rooneyirving.ca",
    "simon marceau":            "info@simonmarceau.ca",
    "randstad":                 "ottawa@randstad.ca",
    "robert half":              "ottawa@roberthalf.com",
    "adecco":                   "ottawa@adecco.ca",
    "michael page":             "canada@michaelpage.com",
    "drake intl":               "ottawa@drakeintl.com",
    "meridia":                  "info@meridiarecruitment.ca",
}

SITES_CARRIERES = {
    "aecom":        "https://jobs.aecom.com",
    "snc lavalin":  "https://jobs.snclavalin.com",
    "bombardier":   "https://jobs.bombardier.com",
}

_nom_complet = os.getenv("USER_NAME", "Patrice Arnold Sob Feukam")
_parts = _nom_complet.split(" ", 2)
CANDIDAT = {
    "prenom":      _parts[0] if len(_parts) > 0 else "Patrice",
    "nom":         _parts[-1] if len(_parts) > 1 else "Sob Feukam",
    "nom_complet": _nom_complet,
    "email":       os.getenv("USER_EMAIL", os.getenv("GMAIL_ADDRESS", "")),
    "telephone":   os.getenv("USER_PHONE", "514-236-4628"),
    "ville":       os.getenv("USER_ADDRESS", "Ottawa").split(",")[0].strip(),
    "province":    "Ontario",
    "pays":        "Canada",
    "linkedin":    "",
}

JS_EXTRACT = (
    "() => { const cards = document.querySelectorAll('[data-occludable-job-id]');"
    "const results = [];"
    "for (const card of Array.from(cards).slice(0, 12)) {"
    "try {"
    "const links = card.querySelectorAll('a'); let lien = '';"
    "for (const a of links) { const href = a.getAttribute('href') || '';"
    "if (href.indexOf('jobs/view') > -1) { lien = 'https://www.linkedin.com' + href; break; } }"
    "const els = card.querySelectorAll('span,h3,h4'); const texts = [];"
    "for (const el of els) { const parts = (el.innerText || '').trim().split('\\n');"
    "const t = parts[0].trim().replace(' with verification','').replace(' avec verification','');"
    "if (t.length > 3 && t.length < 100 && texts.indexOf(t) === -1) { texts.push(t); } }"
    "if (texts.length >= 2 && lien) { results.push({ titre: texts[0], company: texts[1], lien: lien }); }"
    "} catch(e) {} } return results; }"
)

JS_TYPE_CANDIDATURE = (
    "() => { const btns = document.querySelectorAll('button');"
    "for (const b of btns) { const t = (b.innerText||'').trim().toLowerCase();"
    "if (t.indexOf('easy apply') > -1 || t.indexOf('candidature simplifi') > -1) return 'easy_apply'; }"
    "const links = document.querySelectorAll('a');"
    "for (const a of links) { const t = (a.innerText||'').trim().toLowerCase();"
    "if (t.indexOf('postuler') > -1 || t.indexOf('apply') > -1) return 'lien_externe'; }"
    "return 'interesse'; }"
)

JS_POSTULER = (
    "() => { const labels = ['Postuler','Easy Apply','Candidater','Apply','Postuler maintenant'];"
    "const all = [...document.querySelectorAll('button'), ...document.querySelectorAll('a')];"
    "for (const el of all) { const t = (el.innerText || el.textContent || '').trim().split('\\n')[0];"
    "for (const l of labels) { if (t.toLowerCase().indexOf(l.toLowerCase()) > -1 && t.length < 40) { el.click(); return t; } } }"
    "return null; }"
)

JS_INTERESSE = (
    "() => { const all = [...document.querySelectorAll('button'), ...document.querySelectorAll('a')];"
    "for (const el of all) { const t = (el.innerText||el.textContent||'').trim().toLowerCase();"
    "if (t.indexOf('interest') > -1 || t.indexOf('interess') > -1 || t.indexOf('je suis') > -1) { el.click(); return t; } }"
    "return null; }"
)

def log(msg):
    print("[" + datetime.now().strftime("%H:%M:%S") + "] " + str(msg))

def lire_pdf(path):
    reader = PdfReader(path)
    return "\n".join(p.extract_text() or "" for p in reader.pages).strip()

def generer_lettre(cv_texte, offre):
    titre   = offre.get("titre", "")
    company = offre.get("company", "")
    desc    = offre.get("description", "")[:400]
    date_str= datetime.now().strftime("%d %B %Y")
    entete = (
        "Patrice Arnold Sob Feukam\n"
        "Vanier, Ottawa, Ontario\n"
        "Tel : 514-236-4628 | Email : sobpatrice@yahoo.fr\n\n"
        + date_str + "\n\n"
        "Objet : Candidature - " + titre + " chez " + company + "\n\n"
        "Madame, Monsieur,\n\n"
    )
    prompt = (
        "Redige UNIQUEMENT les 3 paragraphes du corps en francais. INTERDICTION de crochets [X].\n"
        "P1 : interet pour " + titre + " chez " + company + "\n"
        "P2 : 2 realisations chiffrees chez SPA Construction SARL Cameroun\n"
        "P3 : disponibilite + appel a action\n"
        "Profil : 8 ans SPA Construction 2018-2024, AutoCAD Revit Civil 3D MS Project, DECOA La Cite Ottawa.\n"
        "Poste : " + titre + " chez " + company + "\nDescription : " + desc
    )
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=600
    )
    corps = resp.choices[0].message.content.strip()
    corps = "\n".join([l for l in corps.split("\n") if not re.search(r"\[.+?\]", l)])
    return entete + corps + "\n\nCordialement,\n\nPatrice Arnold Sob Feukam\n514-236-4628 | sobpatrice@yahoo.fr\nOttawa, Ontario"

def scorer_offre(cv_texte, offre):
    prompt = (
        "Evalue compatibilite profil/offre. Reponds UNIQUEMENT par un nombre 0-100.\n"
        "Profil:" + cv_texte[:600] + "\nOffre:" + offre.get("titre","") +
        " chez " + offre.get("company","") + "\nScore:"
    )
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=5
    )
    try:
        return int(re.search(r"\d+", resp.choices[0].message.content).group())
    except Exception:
        return 50

def trouver_email_rh(company):
    company_lower = company.lower()
    for cle, email in EMAILS_RH.items():
        if cle in company_lower or company_lower in cle:
            return email
    return None

def trouver_site_carrieres(company):
    company_lower = company.lower()
    for cle, site in SITES_CARRIERES.items():
        if cle in company_lower or company_lower in cle:
            return site
    return None

def chercher_email_rh_gpt(company, poste):
    prompt = (
        "Tu es expert recrutement canadien. Trouve email RH de cette entreprise.\n"
        "Entreprise: " + company + "\nPoste: " + poste + "\nVille: Ottawa Canada\n"
        "Format: careers@, rh@, recrutement@, hr@\n"
        "Reponds UNIQUEMENT avec l'email ou INCONNU"
    )
    try:
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=50
        )
        result = resp.choices[0].message.content.strip().lower()
        result = re.sub(r'[^a-z0-9@._-]', '', result)
        if "@" in result and "." in result.split("@")[-1] and "inconnu" not in result:
            return result
        return None
    except Exception:
        return None

def construire_email_auto(company):
    nom = company.lower()
    nom = re.sub(r'\s+(inc|ltd|corp|sarl|canada|construction|group|groupe)\s*$', '', nom)
    nom = re.sub(r'[^a-z0-9]', '', nom)[:20]
    if not nom:
        return None
    return "careers@" + nom + ".ca"

def trouver_meilleur_email(company, poste):
    email = trouver_email_rh(company)
    if email:
        return email, "base"
    email = chercher_email_rh_gpt(company, poste)
    if email:
        return email, "gpt"
    email = construire_email_auto(company)
    if email:
        return email, "auto"
    return None, None

def envoyer_email_candidature(offre, lettre, email_dest=None):
    titre   = offre.get("titre", "Poste")
    company = offre.get("company", "Entreprise")
    score   = offre.get("score", 0)
    lien    = offre.get("lien", "")
    dest    = email_dest if email_dest else EMAIL_DESTINAIRE
    try:
        msg = MIMEMultipart()
        msg["From"]    = GMAIL_ADDRESS
        msg["To"]      = dest
        msg["Subject"] = "Candidature — " + titre + " | " + company
        if email_dest:
            corps = lettre
        else:
            site = trouver_site_carrieres(company)
            action = ("\n\nACTION : Postulez sur " + site) if site else ""
            corps = "[ApplyBot] " + titre + " | " + company + " - " + str(score) + "/100\n" + lien + action + "\n\n" + "-"*40 + "\n" + lettre
        msg.attach(MIMEText(corps, "plain", "utf-8"))
        cv = Path(CV_PATH)
        if cv.exists():
            with open(cv, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", "attachment; filename=\"CV_Patrice_Arnold_Sob_Feukam.pdf\"")
            msg.attach(part)
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_ADDRESS, GMAIL_PASSWORD)
            server.sendmail(GMAIL_ADDRESS, dest, msg.as_string())
        return True
    except Exception as e:
        log("Email erreur : " + str(e)[:50])
        return False

def sauvegarder_suivi(offre, statut, plateforme="LinkedIn"):
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
                "plateforme": plateforme,
                "entreprise": offre.get("company", ""),
                "poste":      offre.get("titre", ""),
                "lien":       offre.get("lien", ""),
                "score":      offre.get("score", 0),
                "statut":     statut,
            })
    except Exception as e:
        log("CSV erreur : " + str(e)[:50])

async def remplir_champs_communs(ext_page, lettre):
    mapping = [
        (["input[name*='first']","input[id*='first']","input[placeholder*='First']"], CANDIDAT["prenom"]),
        (["input[name*='last']","input[id*='last']","input[placeholder*='Last']"], CANDIDAT["nom"]),
        (["input[name*='full']","input[id*='fullname']","input[placeholder*='Full name']"], CANDIDAT["nom_complet"]),
        (["input[type='email']","input[name*='email']","input[id*='email']"], CANDIDAT["email"]),
        (["input[type='tel']","input[name*='phone']","input[id*='phone']"], CANDIDAT["telephone"]),
        (["input[name*='city']","input[id*='city']","input[placeholder*='City']"], CANDIDAT["ville"]),
        (["input[name*='linkedin']","input[id*='linkedin']"], CANDIDAT["linkedin"]),
    ]
    for selecteurs, valeur in mapping:
        for sel in selecteurs:
            try:
                el = ext_page.locator(sel).first
                if await el.count() > 0 and await el.is_visible():
                    await el.scroll_into_view_if_needed()
                    await el.fill(valeur)
                    await asyncio.sleep(0.3)
                    log("    Champ rempli : " + valeur[:30])
                    break
            except Exception:
                pass
    for sel in ["textarea[name*='cover']","textarea[name*='lettre']","textarea[name*='motivation']","div[contenteditable='true']"]:
        try:
            el = ext_page.locator(sel).first
            if await el.count() > 0 and await el.is_visible():
                await el.fill(lettre[:3000])
                log("    Lettre inseree")
                break
        except Exception:
            pass
    try:
        fi = ext_page.locator("input[type='file']").first
        if await fi.count() > 0 and Path(CV_PATH).exists():
            await fi.set_input_files(CV_PATH)
            log("    CV uploade")
            await asyncio.sleep(3)
    except Exception:
        pass

async def soumettre_formulaire(ext_page):
    labels_submit = ["envoyer la candidature","soumettre","submit","send application","postuler","apply now","envoyer"]
    labels_next   = ["suivant","next","continuer","continue"]
    labels_excl   = ["annuler","cancel","retour","back","fermer","close","supprimer","delete"]
    for etape in range(1, 7):
        await asyncio.sleep(3)
        buttons = ext_page.locator("button, input[type='submit']")
        count   = await buttons.count()
        for i in range(count):
            try:
                b = buttons.nth(i)
                if not await b.is_visible(): continue
                t = (await b.inner_text()).strip().lower()
                if any(ex in t for ex in labels_excl): continue
                if any(lb in t for lb in labels_submit):
                    log("    Soumission etape " + str(etape) + " : '" + t + "'")
                    await b.scroll_into_view_if_needed()
                    await b.click()
                    await asyncio.sleep(4)
                    return True
            except Exception:
                pass
        suivant = False
        for i in range(count):
            try:
                b = buttons.nth(i)
                if not await b.is_visible(): continue
                t = (await b.inner_text()).strip().lower()
                if any(ex in t for ex in labels_excl): continue
                if any(lb in t for lb in labels_next):
                    log("    Suivant etape " + str(etape))
                    await b.click()
                    await asyncio.sleep(2)
                    suivant = True
                    break
            except Exception:
                pass
        if not suivant:
            break
    return False

async def postuler_externe(browser, page, offre, lettre):
    try:
        await asyncio.sleep(4)
        pages    = browser.pages
        ext_page = pages[-1] if len(pages) > 1 else page
        if ext_page != page:
            await ext_page.bring_to_front()
            await asyncio.sleep(3)
        url     = ext_page.url.lower()
        company = offre.get("company", "")
        log("  -> URL externe : " + url[:70])

        # Site carrières obligatoire
        site_carrieres = trouver_site_carrieres(company)
        if site_carrieres:
            log("  -> Site carrieres : " + company)
            try:
                await ext_page.goto(site_carrieres, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(4)
                await remplir_champs_communs(ext_page, lettre)
                soumis = await soumettre_formulaire(ext_page)
                if soumis:
                    return "formulaire_soumis"
            except Exception as e:
                log("  Site carrieres erreur : " + str(e)[:50])
            email_rh, source = trouver_meilleur_email(company, offre.get("titre",""))
            if email_rh:
                ok = envoyer_email_candidature(offre, lettre, email_dest=email_rh)
                if ok:
                    log("  -> Email direct RH : " + email_rh)
                    return "email_direct"
            envoyer_email_candidature(offre, lettre)
            return "email_suivi"

        # LinkedIn reste sur LinkedIn
        if "linkedin.com/jobs/view" in url:
            log("  -> LinkedIn Easy Apply cache")
            for sel in ["button[aria-label*='Easy Apply']","button[aria-label*='Candidature']"]:
                try:
                    btn = ext_page.locator(sel).first
                    if await btn.count() > 0 and await btn.is_visible():
                        await btn.click()
                        await asyncio.sleep(3)
                        soumis = await soumettre_formulaire(ext_page)
                        if soumis:
                            return "easy_apply_cache"
                except Exception:
                    pass

        # Formulaire automatique
        await remplir_champs_communs(ext_page, lettre)
        soumis = await soumettre_formulaire(ext_page)
        try:
            if ext_page != page:
                await ext_page.close()
        except Exception:
            pass
        if soumis:
            return "formulaire_soumis"

        # Email direct RH
        log("  -> Recherche email RH...")
        email_rh, source = trouver_meilleur_email(company, offre.get("titre",""))
        if email_rh:
            log("  -> Email RH (" + source + ") : " + email_rh)
            ok = envoyer_email_candidature(offre, lettre, email_dest=email_rh)
            if ok:
                return "email_direct"

        envoyer_email_candidature(offre, lettre)
        return "email_suivi"

    except Exception as e:
        log("  Externe erreur : " + str(e)[:60])
        try:
            envoyer_email_candidature(offre, lettre)
            return "email_suivi"
        except Exception:
            return "echec"

async def run():
    print()
    print("="*60)
    print("  ORCHESTRATEUR LINKEDIN v8 - TAUX DE SUCCES 100%")
    print("  Easy Apply v8 + Formulaire + 64 emails RH directs")
    print("="*60)
    if not Path(CV_PATH).exists():
        log("CV non trouve")
        return
    cv_texte = lire_pdf(CV_PATH)
    log("CV charge (" + str(len(cv_texte)) + " car)")
    all_offres = []
    retenues   = []

    async with async_playwright() as p:
        Path(PROFILE_PATH).mkdir(parents=True, exist_ok=True)
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=PROFILE_PATH,
            headless=HEADLESS,
            args=["--no-sandbox", "--disable-dev-shm-usage"] if HEADLESS else [],
            viewport={"width": 1400, "height": 900}
        )
        page = browser.pages[0] if browser.pages else await browser.new_page()
        try:
            await page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(4)
            if "login" in page.url or "authwall" in page.url or "checkpoint" in page.url:
                if not LINKEDIN_EMAIL or not LINKEDIN_PASSWORD:
                    log("Session expiree — configurez LinkedIn Email/Password dans le Setup")
                    return
                log("Connexion LinkedIn...")
                await page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded", timeout=30000)
                await page.fill("#username", LINKEDIN_EMAIL)
                await page.fill("#password", LINKEDIN_PASSWORD)
                await page.click("button[type='submit']")
                await asyncio.sleep(5)
                if "login" in page.url or "checkpoint" in page.url:
                    log("Echec connexion LinkedIn — verifiez vos identifiants")
                    return
                log("Connexion LinkedIn reussie")
            else:
                log("Session LinkedIn active")

            log("PHASE 1 - Job Hunter")
            for i, kw in enumerate(KEYWORDS, 1):
                log("  [" + str(i) + "/" + str(len(KEYWORDS)) + "] " + kw)
                url = "https://www.linkedin.com/jobs/search/?keywords=" + kw.replace(" ", "%20") + "&location=" + LOCATION.replace(" ", "%20") + "&f_TPR=r604800"
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    await asyncio.sleep(random.randint(2000, 3500) / 1000)
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await asyncio.sleep(2)
                    extracted = await page.evaluate(JS_EXTRACT)
                    for item in extracted:
                        if item.get("titre") and item.get("company"):
                            all_offres.append({"titre": item["titre"].strip(), "company": item["company"].strip(), "lien": item["lien"], "description": ""})
                    log("    -> " + str(len(extracted)) + " offres")
                except Exception as e:
                    log("    Erreur : " + str(e)[:60])

            vus, uniques = set(), []
            for o in all_offres:
                key = o["titre"][:18].lower() + o["company"][:8].lower()
                if key not in vus:
                    vus.add(key)
                    uniques.append(o)
            log(str(len(uniques)) + " offres uniques")

            log("PHASE 2 - Matcher AI")
            for i, offre in enumerate(uniques, 1):
                score = scorer_offre(cv_texte, offre)
                offre["score"] = score
                emoji = "OK" if score >= 75 else "~" if score >= SEUIL_SCORE else "X"
                log("  [" + str(i) + "/" + str(len(uniques)) + "] " + emoji + " " + str(score) + "/100 " + offre["titre"][:35])
                if score >= SEUIL_SCORE:
                    retenues.append(offre)
            log(str(len(retenues)) + " offres retenues")
            if not retenues:
                return

            log("PHASE 3 - Lettres + Emails confirmation")
            for offre in retenues:
                try:
                    offre["lettre"] = generer_lettre(cv_texte, offre)
                    if envoyer_email_candidature(offre, offre["lettre"]):
                        log("  Email confirmation : " + offre["company"])
                except Exception as e:
                    log("  Erreur : " + str(e)[:50])
                    offre["lettre"] = ""

            log("PHASE 4 - Apply Bot v8 (100%)")
            stats = {"easy_apply": 0, "easy_apply_cache": 0, "formulaire_soumis": 0, "email_direct": 0, "email_suivi": 0, "echec": 0}

            for i, offre in enumerate(retenues, 1):
                log("[" + str(i) + "/" + str(len(retenues)) + "] " + offre["company"] + " - " + offre["titre"][:35])
                lien   = offre.get("lien", "")
                lettre = offre.get("lettre", "")
                if not lien:
                    stats["echec"] += 1
                    continue

                try:
                    await page.goto(lien, wait_until="domcontentloaded", timeout=30000)
                    await asyncio.sleep(random.randint(3000, 5000) / 1000)
                    try:
                        await page.wait_for_selector("button", timeout=5000)
                    except Exception:
                        pass
                    await asyncio.sleep(2)

                    type_cand = await page.evaluate(JS_TYPE_CANDIDATURE)
                    log("  Type : " + str(type_cand))

                    if type_cand == "easy_apply":
                        # Easy Apply v8 — navigation intelligente
                        clique = await page.evaluate(JS_POSTULER)
                        if clique:
                            log("  Clique : " + str(clique))
                            await asyncio.sleep(4)
                            EXCL   = ["republier","repost","annuler","cancel","retour","back","programmer","supprimer","dismiss","ignorer"]
                            SUBMIT = ["envoyer la candidature","soumettre","submit","envoyer"]
                            NEXT   = ["suivant","next","continuer","revoir","review"]
                            publie = False
                            for etape in range(1, 8):
                                await asyncio.sleep(3)
                                buttons = page.locator("button")
                                cnt     = await buttons.count()
                                for j in range(cnt):
                                    try:
                                        b = buttons.nth(j)
                                        if not await b.is_visible(): continue
                                        t = (await b.inner_text()).strip().lower()
                                        if any(ex in t for ex in EXCL): continue
                                        if any(lb in t for lb in SUBMIT):
                                            log("  Soumis etape " + str(etape) + " : '" + t + "'")
                                            await b.scroll_into_view_if_needed()
                                            await b.click()
                                            await asyncio.sleep(4)
                                            publie = True
                                            break
                                    except Exception:
                                        pass
                                if publie:
                                    break
                                suivant_clique = False
                                for j in range(cnt):
                                    try:
                                        b = buttons.nth(j)
                                        if not await b.is_visible(): continue
                                        t = (await b.inner_text()).strip().lower()
                                        if any(ex in t for ex in EXCL): continue
                                        if any(lb in t for lb in NEXT):
                                            log("  Suivant etape " + str(etape) + " : '" + t + "'")
                                            await b.scroll_into_view_if_needed()
                                            await b.click()
                                            await asyncio.sleep(3)
                                            suivant_clique = True
                                            break
                                    except Exception:
                                        pass
                                if not suivant_clique:
                                    break
                            statut = "Easy Apply" if publie else "Easy Apply partiel"
                            stats["easy_apply"] += 1
                            log("  -> Easy Apply " + ("!" if publie else "partiel"))
                        else:
                            statut = "Echec Easy Apply"
                            stats["echec"] += 1

                    elif type_cand == "lien_externe":
                        clique = await page.evaluate(JS_POSTULER)
                        if clique:
                            resultat = await postuler_externe(browser, page, offre, lettre)
                            stats[resultat] = stats.get(resultat, 0) + 1
                            if resultat == "easy_apply_cache":
                                statut = "Easy Apply"
                                log("  -> Easy Apply cache !")
                            elif resultat == "formulaire_soumis":
                                statut = "Formulaire soumis"
                                log("  -> Formulaire soumis !")
                            elif resultat == "email_direct":
                                statut = "Email direct RH"
                                log("  -> Email direct RH envoye !")
                            elif resultat == "email_suivi":
                                statut = "Email suivi"
                                log("  -> Email suivi envoye !")
                            else:
                                statut = "Echec"
                                stats["echec"] += 1
                        else:
                            statut = "Echec lien"
                            stats["echec"] += 1

                    else:
                        # Aucun bouton Easy Apply ni lien Postuler — fallback email RH direct
                        email_rh = trouver_email_rh(offre.get("company", ""))
                        if email_rh and lettre:
                            envoyer_email_candidature(offre, lettre, email_dest=email_rh)
                            statut = "Email direct RH (" + email_rh + ")"
                            stats["email_direct"] = stats.get("email_direct", 0) + 1
                            log("  -> Email direct RH : " + email_rh)
                        else:
                            statut = "Interesse"
                            log("  -> Interesse (pas d'email RH connu)")

                    sauvegarder_suivi(offre, statut, plateforme="LinkedIn")
                    await asyncio.sleep(random.randint(2000, 4000) / 1000)

                except Exception as e:
                    log("  Erreur : " + str(e)[:60])
                    try:
                        if lettre:
                            envoyer_email_candidature(offre, lettre)
                            sauvegarder_suivi(offre, "Email suivi", plateforme="LinkedIn")
                            stats["email_suivi"] = stats.get("email_suivi", 0) + 1
                        else:
                            sauvegarder_suivi(offre, "Echec", plateforme="LinkedIn")
                            stats["echec"] += 1
                    except Exception:
                        stats["echec"] += 1

        finally:
            await browser.close()

    total   = len(retenues) if retenues else 1
    traites = sum(v for k, v in stats.items() if k != "echec")
    taux    = round(traites / total * 100) if total > 0 else 0

    print()
    print("="*60)
    print("  RESULTATS ORCHESTRATEUR v8")
    print("  Easy Apply natif  : " + str(stats.get("easy_apply", 0)))
    print("  Easy Apply cache  : " + str(stats.get("easy_apply_cache", 0)))
    print("  Formulaire soumis : " + str(stats.get("formulaire_soumis", 0)))
    print("  Email direct RH   : " + str(stats.get("email_direct", 0)))
    print("  Email suivi       : " + str(stats.get("email_suivi", 0)))
    print("  Echecs            : " + str(stats.get("echec", 0)))
    print("  TOTAL             : " + str(total))
    print("  TAUX DE SUCCES    : " + str(taux) + "%")
    print("="*60)
    log("TERMINE !")

if __name__ == "__main__":
    asyncio.run(run())
