import sys
sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
from dotenv import load_dotenv
load_dotenv()
from openai import OpenAI
from pypdf import PdfReader
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import asyncio, random, os, csv, smtplib, re, json, requests as _req
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
from pathlib import Path

_openai_key      = os.getenv("OPENAI_API_KEY", "")
client           = OpenAI(api_key=_openai_key) if _openai_key else None
CV_PATH          = os.getenv("CV_PATH", "cv.pdf")
GMAIL_ADDRESS    = os.getenv("GMAIL_ADDRESS")
GMAIL_PASSWORD   = os.getenv("GMAIL_APP_PASSWORD")
EMAIL_DESTINAIRE = os.getenv("GMAIL_ADDRESS")
PROFILE_PATH     = os.getenv("PROFILE_PATH", "chrome_profile")
LINKEDIN_EMAIL   = os.getenv("LINKEDIN_EMAIL", "")
LINKEDIN_PASSWORD= os.getenv("LINKEDIN_PASSWORD", "")
LINKEDIN_LI_AT        = os.getenv("LINKEDIN_LI_AT", "")
LINKEDIN_COOKIES_JSON = os.getenv("LINKEDIN_COOKIES_JSON", "")
OUTPUT_DIR       = os.path.join(PROFILE_PATH, "candidatures_envoyees")
SEUIL_SCORE      = 65
HEADLESS         = os.getenv("DISPLAY", "") == ""
SAAS_API_URL     = os.getenv("SAAS_API_URL", "")
SAAS_TOKEN       = os.getenv("SAAS_USER_TOKEN", "")
SAAS_USER_ID     = os.getenv("SAAS_USER_ID", "0")
if SAAS_API_URL and not SAAS_API_URL.startswith("http"):
    SAAS_API_URL = "https://" + SAAS_API_URL

SMARTPROXY_USER  = os.getenv("SMARTPROXY_USER", "")
SMARTPROXY_PASS  = os.getenv("SMARTPROXY_PASS", "")

def _save_cookies(cookies):
    if not SAAS_API_URL or not SAAS_TOKEN:
        return
    try:
        _req.post(f"{SAAS_API_URL}/api/linkedin/cookies",
                  json={"cookies": cookies},
                  headers={"X-User-Token": SAAS_TOKEN}, timeout=5)
    except Exception:
        pass

def _load_cookies():
    if not SAAS_API_URL or not SAAS_TOKEN:
        return []
    try:
        r = _req.get(f"{SAAS_API_URL}/api/linkedin/cookies",
                     headers={"X-User-Token": SAAS_TOKEN}, timeout=5)
        if r.status_code == 200:
            return r.json().get("cookies", [])
    except Exception:
        pass
    return []

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
    print("[" + datetime.now().strftime("%H:%M:%S") + "] " + str(msg), flush=True)

def lire_pdf(path):
    reader = PdfReader(path)
    return "\n".join(p.extract_text() or "" for p in reader.pages).strip()

def generer_lettre(cv_texte, offre):
    titre      = offre.get("titre", "")
    company    = offre.get("company", "")
    desc       = offre.get("description", "")[:1800]
    date_str   = datetime.now().strftime("%d %B %Y")
    ville_prov = CANDIDAT["ville"] + ", " + CANDIDAT["province"]
    signature  = (CANDIDAT["nom_complet"] + "\n"
                  + CANDIDAT["telephone"] + " | " + CANDIDAT["email"] + "\n"
                  + ville_prov)
    entete = (
        CANDIDAT["nom_complet"] + "\n"
        + ville_prov + "\n"
        + "Tél : " + CANDIDAT["telephone"] + "  |  Courriel : " + CANDIDAT["email"] + "\n\n"
        + date_str + "\n\n"
        + "Objet : Candidature — " + titre + " chez " + company + "\n\n"
        + "Madame, Monsieur,\n\n"
    )
    if not client:
        return (entete + "Veuillez trouver ci-joint mon CV pour le poste de "
                + titre + " chez " + company + ".\n\nCordialement,\n\n" + signature)
    prompt = (
        "Tu es expert RH canadien certifié, spécialiste ATS (Applicant Tracking Systems).\n"
        "Rédige une lettre de motivation ATS-optimisée UNIQUE pour CE poste précis.\n\n"
        "RÈGLES ABSOLUES :\n"
        "1. Utilise les mots-clés EXACTS de la description du poste (logiciels, certifications, verbes d'action)\n"
        "2. Zéro crochet [X], zéro placeholder, zéro phrase générique\n"
        "3. Exactement 3 paragraphes, 80-100 mots chacun (total 250-300 mots)\n"
        "4. Chiffres concrets tirés du profil (%, $, m², années, nombre d'unités)\n"
        "5. Commence P1 par une phrase d'accroche forte mentionnant EXACTEMENT « " + titre + " »\n"
        "6. Adapte le vocabulaire au secteur et à l'entreprise « " + company + " »\n\n"
        "P1 : Accroche percutante + intérêt spécifique pour ce poste + lien direct avec l'offre\n"
        "P2 : 2-3 réalisations chiffrées du profil, directement liées aux exigences du poste\n"
        "P3 : Valeur ajoutée différenciante + disponibilité immédiate + appel à l'action\n\n"
        "POSTE : " + titre + " chez " + company + "\n"
        "DESCRIPTION DU POSTE :\n" + (desc if desc else "Poste en " + titre) + "\n\n"
        "PROFIL DU CANDIDAT :\n" + cv_texte[:1200] + "\n\n"
        "Rédige UNIQUEMENT les 3 paragraphes du corps. Pas d'entête, pas de signature."
    )
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=750,
        temperature=0.7,
    )
    corps = resp.choices[0].message.content.strip()
    corps = "\n".join([l for l in corps.split("\n") if not re.search(r"\[.+?\]", l)])
    return entete + corps + "\n\nCordialement,\n\n" + signature


def generer_cv_tailored(cv_texte: str, offre: dict) -> str:
    """Génère un CV PDF ATS-optimisé et personnalisé pour cette offre. Retourne le chemin."""
    titre   = offre.get("titre", "")
    company = offre.get("company", "")
    desc    = offre.get("description", "")[:1500]
    cv_dir  = Path(PROFILE_PATH) / "cvs_tailored"
    cv_dir.mkdir(parents=True, exist_ok=True)
    safe    = re.sub(r"[^\w]", "_", titre)[:25]
    cv_out  = str(cv_dir / ("CV_" + CANDIDAT["prenom"] + "_" + safe + ".pdf"))

    data = {}
    if client:
        prompt = (
            "Analyse ce profil et génère un CV ATS-optimisé pour ce poste précis.\n"
            "Réponds UNIQUEMENT en JSON valide (sans markdown, sans ```).\n\n"
            "POSTE CIBLE : " + titre + " chez " + company + "\n"
            "DESCRIPTION : " + (desc if desc else titre) + "\n"
            "PROFIL SOURCE : " + cv_texte[:2500] + "\n\n"
            '{"titre_professionnel":"...","resume":"3 phrases ATS avec mots-clés exacts du poste",'
            '"competences":["comp1","comp2","comp3","comp4","comp5","comp6","comp7","comp8"],'
            '"experiences":[{"poste":"...","entreprise":"...","lieu":"...","periode":"...",'
            '"points":["réalisation chiffrée 1","réalisation chiffrée 2","réalisation 3"]}],'
            '"formations":[{"diplome":"...","etablissement":"...","lieu":"...","annee":"..."}],'
            '"langues":["Français (natif)","Anglais (professionnel)"],'
            '"certifications":[]}'
        )
        try:
            resp = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1600,
            )
            raw = resp.choices[0].message.content.strip()
            m   = re.search(r'\{[\s\S]*\}', raw)
            if m:
                data = json.loads(m.group())
        except Exception as e:
            log("  CV tailored GPT erreur : " + str(e)[:60])

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import cm
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
        from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
        from reportlab.lib import colors

        BLEU = colors.HexColor("#1a3c5e")
        GRIS = colors.HexColor("#555555")

        s_nom   = ParagraphStyle("Nom",  fontName="Helvetica-Bold", fontSize=20,
                                  alignment=TA_CENTER, textColor=BLEU, spaceAfter=2)
        s_sub   = ParagraphStyle("Sub",  fontName="Helvetica",      fontSize=11,
                                  alignment=TA_CENTER, textColor=BLEU, spaceAfter=3)
        s_con   = ParagraphStyle("Con",  fontName="Helvetica",      fontSize=8.5,
                                  alignment=TA_CENTER, textColor=GRIS, spaceAfter=6)
        s_sec   = ParagraphStyle("Sec",  fontName="Helvetica-Bold", fontSize=10,
                                  textColor=BLEU, spaceBefore=10, spaceAfter=3)
        s_body  = ParagraphStyle("Body", fontName="Helvetica",      fontSize=9,
                                  leading=13, alignment=TA_JUSTIFY, spaceAfter=3)
        s_bul   = ParagraphStyle("Bul",  fontName="Helvetica",      fontSize=9,
                                  leading=13, leftIndent=10, spaceAfter=2)
        s_job   = ParagraphStyle("Job",  fontName="Helvetica-Bold", fontSize=9.5, spaceAfter=1)
        s_meta  = ParagraphStyle("Meta", fontName="Helvetica",      fontSize=8.5,
                                  textColor=GRIS, spaceAfter=3)

        doc   = SimpleDocTemplate(cv_out, pagesize=A4,
                                  leftMargin=1.8*cm, rightMargin=1.8*cm,
                                  topMargin=1.5*cm,  bottomMargin=1.5*cm)
        story = []
        hr    = lambda: story.append(HRFlowable(width="100%", thickness=0.5,
                                                color=BLEU, spaceAfter=4))

        story.append(Paragraph(CANDIDAT["nom_complet"], s_nom))
        story.append(Paragraph(data.get("titre_professionnel", titre), s_sub))
        story.append(Paragraph(
            CANDIDAT["ville"] + ", " + CANDIDAT["province"] +
            " | " + CANDIDAT["telephone"] + " | " + CANDIDAT["email"], s_con))
        story.append(HRFlowable(width="100%", thickness=2, color=BLEU, spaceAfter=8))

        resume = data.get("resume", "") or cv_texte[:300]
        if resume:
            story.append(Paragraph("PROFIL PROFESSIONNEL", s_sec)); hr()
            story.append(Paragraph(resume, s_body))

        skills = data.get("competences", [])
        if skills:
            story.append(Paragraph("COMPÉTENCES CLÉS", s_sec)); hr()
            for i in range(0, len(skills), 2):
                line = "✓ " + skills[i]
                if i + 1 < len(skills):
                    line += "      ✓ " + skills[i + 1]
                story.append(Paragraph(line, s_bul))

        exps = data.get("experiences", [])
        if exps:
            story.append(Paragraph("EXPÉRIENCE PROFESSIONNELLE", s_sec)); hr()
            for exp in exps:
                story.append(Paragraph("<b>" + exp.get("poste", "") + "</b>", s_job))
                story.append(Paragraph(
                    exp.get("entreprise","") + " | " + exp.get("lieu","") +
                    " | " + exp.get("periode",""), s_meta))
                for pt in exp.get("points", []):
                    story.append(Paragraph("• " + pt, s_bul))
                story.append(Spacer(1, 4))

        formations = data.get("formations", [])
        if formations:
            story.append(Paragraph("FORMATION", s_sec)); hr()
            for f in formations:
                story.append(Paragraph("<b>" + f.get("diplome","") + "</b>", s_job))
                story.append(Paragraph(
                    f.get("etablissement","") + " | " + f.get("lieu","") +
                    " | " + f.get("annee",""), s_meta))

        langues = data.get("langues", [])
        certs   = data.get("certifications", [])
        if langues or certs:
            story.append(Paragraph("LANGUES & CERTIFICATIONS", s_sec)); hr()
            story.append(Paragraph(" · ".join(langues + certs), s_body))

        doc.build(story)
        log("  CV personnalisé : " + Path(cv_out).name)
        return cv_out

    except Exception as e:
        log("  CV tailored erreur : " + str(e)[:80])
        return CV_PATH

def scorer_offre(cv_texte, offre):
    if not client:
        return 75
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
    if not client:
        return None
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

def envoyer_email_candidature(offre, lettre, email_dest=None, cv_tailored=None):
    from email_helper import send_email
    titre   = offre.get("titre", "Poste")
    company = offre.get("company", "Entreprise")
    score   = offre.get("score", 0)
    lien    = offre.get("lien", "")
    dest    = email_dest if email_dest else EMAIL_DESTINAIRE
    if email_dest:
        corps = lettre
    else:
        site   = trouver_site_carrieres(company)
        action = ("\n\nACTION : Postulez sur " + site) if site else ""
        corps  = ("[ApplyBot] " + titre + " | " + company + " - " + str(score) + "/100\n"
                  + lien + action + "\n\n" + "-"*40 + "\n" + lettre)
    subject  = "Candidature — " + titre + " | " + company
    cv_file  = cv_tailored if cv_tailored and Path(cv_tailored).exists() else CV_PATH
    cv_nom   = "CV_" + CANDIDAT["prenom"] + "_" + re.sub(r"[^\w]","_",titre)[:20] + ".pdf"
    att      = [{"path": cv_file, "name": cv_nom}] if cv_file and Path(cv_file).exists() else []
    ok, err  = send_email(dest, subject, corps, reply_to=GMAIL_ADDRESS, attachments=att)
    if not ok:
        log("Email erreur : " + err)
    return ok

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

def _proxy_dict() -> dict:
    """Retourne le dict proxies Smartproxy si configuré."""
    if not SMARTPROXY_USER or not SMARTPROXY_PASS:
        return {}
    p_url = ("http://" + SMARTPROXY_USER + "-session-u" + SAAS_USER_ID +
             ":" + SMARTPROXY_PASS + "@gate.smartproxy.com:10001")
    return {"http": p_url, "https": p_url}

_LI_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/124.0.0.0 Safari/537.36"),
    "Accept-Language": "fr-CA,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.linkedin.com/jobs/",
}


def scraper_jobs_http(kw: str, location: str) -> list:
    """LinkedIn public guest API — aucun navigateur requis, aucun crash."""
    offres = []
    for start in (0, 25):
        try:
            resp = _req.get(
                "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search",
                params={"keywords": kw, "location": location,
                        "f_TPR": "r604800", "start": start},
                headers=_LI_HEADERS, proxies=_proxy_dict(), timeout=20,
            )
            if resp.status_code != 200:
                log("  LinkedIn HTTP " + str(resp.status_code) + " pour " + kw[:25])
                break
            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.find_all("div", class_=lambda c: c and "base-card" in c)
            for card in cards[:12]:
                try:
                    a  = card.find("a", href=lambda h: h and "/jobs/view/" in h)
                    h3 = card.find("h3")
                    h4 = card.find("h4")
                    if not (a and h3):
                        continue
                    href = a.get("href", "")
                    lien = ("https://www.linkedin.com" + href.split("?")[0]
                            if href.startswith("/") else href.split("?")[0])
                    titre   = h3.get_text(strip=True)
                    company = h4.get_text(strip=True) if h4 else ""
                    # Snippet description depuis la card
                    snip = card.find("p") or card.find("div", class_=lambda c: c and "snippet" in (c or ""))
                    snippet = snip.get_text(strip=True)[:300] if snip and snip not in (h3, h4) else ""
                    if titre and company and lien:
                        offres.append({"titre": titre, "company": company,
                                       "lien": lien, "description": snippet})
                except Exception:
                    pass
            if len(cards) < 10:
                break
        except Exception as e:
            log("  HTTP erreur scraping : " + str(e)[:60])
            break
    return offres


def get_job_description_http(lien: str) -> str:
    """Récupère la description complète du poste via l'API publique LinkedIn."""
    m = re.search(r'/jobs/view/(\d+)', lien)
    if not m:
        return ""
    job_id = m.group(1)
    try:
        resp = _req.get(
            "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/" + job_id,
            headers=_LI_HEADERS, proxies=_proxy_dict(), timeout=15,
        )
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            desc = (soup.find("div", class_=lambda c: c and "description__text" in (c or "")) or
                    soup.find("div", {"id": "job-details"}) or
                    soup.find("section", class_=lambda c: c and "description" in (c or "")))
            if desc:
                return desc.get_text(separator=" ", strip=True)[:2500]
    except Exception:
        pass
    return ""


async def _linkedin_login(page, browser) -> bool:
    """Auto-login LinkedIn avec email/password + JS direct. Retourne True si connecté."""
    if not LINKEDIN_EMAIL or not LINKEDIN_PASSWORD:
        log("Auto-login impossible : LINKEDIN_EMAIL ou LINKEDIN_PASSWORD manquant dans le Setup")
        return False
    log("Auto-login LinkedIn en cours (" + LINKEDIN_EMAIL + ")...")

    JS_FILL = """([email, pwd]) => {
        const allInputs = Array.from(document.querySelectorAll('input'));
        let emailInp = null, pwdInp = null;
        for (const inp of allInputs) {
            const t = inp.type || '', n = (inp.name||'').toLowerCase(),
                  id = (inp.id||'').toLowerCase(), ac = (inp.autocomplete||'').toLowerCase();
            if (!emailInp && (t==='email' || t==='text' ||
                n.includes('session_key') || n.includes('email') || n.includes('user') ||
                id.includes('username') || id.includes('email') || ac.includes('username')))
                emailInp = inp;
            else if (!pwdInp && (t==='password' || n.includes('password') || ac.includes('password')))
                pwdInp = inp;
        }
        if (!emailInp || !pwdInp) return false;
        emailInp.focus();
        emailInp.value = email;
        emailInp.dispatchEvent(new Event('input', {bubbles:true}));
        emailInp.dispatchEvent(new Event('change', {bubbles:true}));
        pwdInp.focus();
        pwdInp.value = pwd;
        pwdInp.dispatchEvent(new Event('input', {bubbles:true}));
        pwdInp.dispatchEvent(new Event('change', {bubbles:true}));
        const btn = document.querySelector('button[type="submit"]') ||
                    Array.from(document.querySelectorAll('button')).find(b =>
                        (b.innerText||'').toLowerCase().includes('sign') ||
                        (b.innerText||'').toLowerCase().includes('connect'));
        if (btn) btn.click();
        return true;
    }"""

    login_urls = [
        page.url if ("login" in page.url or "uas" in page.url) else "",
        "https://www.linkedin.com/login",
        "https://www.linkedin.com/uas/login",
    ]

    for login_url in login_urls:
        if not login_url:
            continue
        try:
            if page.url != login_url:
                await page.goto(login_url, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(8)
            log("URL login tentée : " + page.url[:80])
        except Exception as e:
            log("Goto login erreur : " + str(e)[:50])
            continue

        # Approche 1 : sélecteurs Playwright classiques
        for sel in ["#username", "input[name='session_key']", "input[autocomplete='username']",
                    "input[type='email']", "input[autocomplete='email']"]:
            try:
                await page.wait_for_selector(sel, timeout=8000)
                await page.fill(sel, LINKEDIN_EMAIL)
                log("Email rempli via sélecteur : " + sel)
                for psel in ["#password", "input[name='session_password']", "input[type='password']"]:
                    try:
                        await page.fill(psel, LINKEDIN_PASSWORD)
                        log("Password rempli via sélecteur : " + psel)
                        break
                    except Exception:
                        continue
                await asyncio.sleep(random.uniform(0.8, 1.5))
                await page.click("button[type='submit']")
                await asyncio.sleep(10)
                if "login" not in page.url and "uas" not in page.url and "authwall" not in page.url:
                    log("Connexion réussie (sélecteurs) !")
                    cookies = await browser.cookies()
                    _save_cookies(cookies)
                    return True
                break
            except Exception:
                continue

        # Approche 2 : injection JavaScript directe (contourne le React non rendu)
        log("  Tentative login JS direct...")
        await asyncio.sleep(3)
        try:
            ok = await page.evaluate(JS_FILL, [LINKEDIN_EMAIL, LINKEDIN_PASSWORD])
            if ok:
                log("  JS direct : formulaire soumis")
                await asyncio.sleep(12)
                url_now = page.url
                log("  URL apres JS login : " + url_now[:80])
                if "checkpoint" in url_now or "challenge" in url_now:
                    log("LinkedIn demande une vérification 2FA")
                    return False
                if "login" not in url_now and "uas" not in url_now and "authwall" not in url_now:
                    log("Connexion LinkedIn reussie (JS) !")
                    cookies = await browser.cookies()
                    _save_cookies(cookies)
                    log("Nouveaux cookies sauvegardes (" + str(len(cookies)) + ")")
                    return True
            else:
                log("  JS direct : aucun champ trouvé sur " + page.url[:60])
        except Exception as e:
            log("  JS direct erreur : " + str(e)[:60])

    log("Impossible de se connecter après toutes les tentatives")
    log("=> Rafraichissez les cookies LinkedIn dans le Setup (Cookie-Editor)")
    return False


async def run():
    print("="*60, flush=True)
    print("  ORCHESTRATEUR LINKEDIN v9 - HTTP SCRAPING + EASY APPLY", flush=True)
    print("  Phase 1 HTTP (sans navigateur) + Phase 4 Playwright", flush=True)
    print("="*60, flush=True)
    log("OpenAI : " + ("OK" if client else "MANQUANT (OPENAI_API_KEY non configuree)"))
    log("LinkedIn email : " + (LINKEDIN_EMAIL if LINKEDIN_EMAIL else "MANQUANT"))
    log("CV path : " + CV_PATH)
    if SMARTPROXY_USER and SMARTPROXY_PASS:
        log("Proxy : Smartproxy résidentiel (session u" + SAAS_USER_ID + ")")
    else:
        log("Proxy : non configuré")
    if not Path(CV_PATH).exists():
        log("CV non trouve : " + CV_PATH)
        return
    cv_texte = lire_pdf(CV_PATH)
    log("CV charge (" + str(len(cv_texte)) + " car)")

    # ── PHASE 1 : Scraping HTTP (pas de navigateur, zéro crash) ────────────────
    log("PHASE 1 - Job Hunter (HTTP, sans navigateur)")
    all_offres = []
    for i, kw in enumerate(KEYWORDS, 1):
        log("  [" + str(i) + "/" + str(len(KEYWORDS)) + "] " + kw)
        found = scraper_jobs_http(kw, LOCATION)
        all_offres.extend(found)
        log("    -> " + str(len(found)) + " offres")

    vus, uniques = set(), []
    for o in all_offres:
        key = o["titre"][:18].lower() + o["company"][:8].lower()
        if key not in vus:
            vus.add(key)
            uniques.append(o)
    log(str(len(uniques)) + " offres uniques")

    # ── PHASE 2 : Matcher AI ────────────────────────────────────────────────────
    log("PHASE 2 - Matcher AI")
    retenues = []
    for i, offre in enumerate(uniques, 1):
        score = scorer_offre(cv_texte, offre)
        offre["score"] = score
        emoji = "OK" if score >= 75 else "~" if score >= SEUIL_SCORE else "X"
        log("  [" + str(i) + "/" + str(len(uniques)) + "] " + emoji + " " + str(score) + "/100 " + offre["titre"][:35])
        if score >= SEUIL_SCORE:
            retenues.append(offre)
    log(str(len(retenues)) + " offres retenues")
    if not retenues:
        log("Aucune offre retenue - terminé")
        return

    # ── PHASE 2.5 : Descriptions complètes pour les offres retenues ─────────────
    log("PHASE 2.5 - Descriptions complètes des offres retenues")
    for i, offre in enumerate(retenues, 1):
        if not offre.get("description") or len(offre["description"]) < 100:
            log("  [" + str(i) + "/" + str(len(retenues)) + "] " + offre["company"][:30] + " — fetch desc...")
            desc_full = get_job_description_http(offre.get("lien", ""))
            if desc_full:
                offre["description"] = desc_full
                log("    -> " + str(len(desc_full)) + " caractères")

    # ── PHASE 3 : Lettres ATS + CV personnalisés + Emails ───────────────────────
    log("PHASE 3 - Lettres ATS personnalisées + CV tailored")
    for offre in retenues:
        try:
            offre["lettre"]     = generer_lettre(cv_texte, offre)
            offre["cv_tailored"]= generer_cv_tailored(cv_texte, offre)
            if envoyer_email_candidature(offre, offre["lettre"],
                                         cv_tailored=offre.get("cv_tailored")):
                log("  Email + CV tailored : " + offre["company"])
        except Exception as e:
            log("  Erreur : " + str(e)[:50])
            offre["lettre"]      = ""
            offre["cv_tailored"] = None

    # ── PHASE 4 : Apply Bot v9 (navigateur UNIQUEMENT ici) ─────────────────────
    log("PHASE 4 - Apply Bot v9 (Easy Apply)")
    stats = {"easy_apply": 0, "easy_apply_cache": 0, "formulaire_soumis": 0,
             "email_direct": 0, "email_suivi": 0, "echec": 0}

    async with async_playwright() as p:
        Path(PROFILE_PATH).mkdir(parents=True, exist_ok=True)
        for lock in ["LOCK", "SingletonLock", "SingletonCookie", "lockfile"]:
            lp = Path(PROFILE_PATH) / lock
            if lp.exists():
                try:
                    lp.unlink()
                    log("Lock supprime : " + lock)
                except Exception:
                    pass
        stealth_args = [
            "--no-sandbox", "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
            "--window-size=1920,1080",
            "--disable-extensions", "--disable-gpu",
            "--no-first-run", "--no-default-browser-check",
            "--disable-default-apps", "--disable-background-networking",
            "--disable-background-timer-throttling",
            "--disable-renderer-backgrounding",
            "--disable-backgrounding-occluded-windows",
            "--memory-pressure-off", "--renderer-process-limit=1",
            "--disable-ipc-flooding-protection",
            "--force-color-profile=srgb",
            "--metrics-recording-only",
            "--password-store=basic",
            "--use-mock-keychain",
            "--export-tagged-pdf",
            "--lang=fr-CA",
        ]
        launch_kwargs = dict(
            user_data_dir=PROFILE_PATH,
            headless=HEADLESS,
            args=stealth_args,
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="fr-CA",
            timezone_id="America/Toronto",
            ignore_default_args=["--enable-automation", "--enable-blink-features=IdleDetection"],
        )
        if SMARTPROXY_USER and SMARTPROXY_PASS:
            session_id = "u" + SAAS_USER_ID
            launch_kwargs["proxy"] = {
                "server":   "http://gate.smartproxy.com:10001",
                "username": SMARTPROXY_USER + "-session-" + session_id,
                "password": SMARTPROXY_PASS,
            }
        browser = await p.chromium.launch_persistent_context(**launch_kwargs)
        page = browser.pages[0] if browser.pages else await browser.new_page()
        STEALTH_JS = """
() => {
  // 1. Cache webdriver
  Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
  // 2. Plugins réalistes
  const pluginData = [
    {name:'Chrome PDF Plugin',filename:'internal-pdf-viewer',description:'Portable Document Format'},
    {name:'Chrome PDF Viewer',filename:'mhjfbmdgcfjbbpaeojofohoefgiehjai',description:''},
    {name:'Native Client',filename:'internal-nacl-plugin',description:''},
  ];
  Object.defineProperty(navigator, 'plugins', {get: () => pluginData});
  Object.defineProperty(navigator, 'mimeTypes', {get: () => []});
  // 3. Langues canadiennes
  Object.defineProperty(navigator, 'languages', {get: () => ['fr-CA','fr','en-CA','en']});
  // 4. Chrome runtime complet
  window.chrome = {runtime:{}, loadTimes:()=>{}, csi:()=>{}, app:{}};
  // 5. Permissions
  try {
    const orig = navigator.permissions.query.bind(navigator.permissions);
    navigator.permissions.query = (p) => p.name==='notifications'
      ? Promise.resolve({state:Notification.permission}) : orig(p);
  } catch(e) {}
  // 6. Hardware
  Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
  Object.defineProperty(navigator, 'deviceMemory', {get: () => 8});
  Object.defineProperty(navigator, 'platform', {get: () => 'Win32'});
  // 7. Écran réaliste
  ['width','height','availWidth','availHeight'].forEach((k,i) => {
    Object.defineProperty(screen, k, {get: () => [1920,1080,1920,1040][i]});
  });
  Object.defineProperty(screen, 'colorDepth', {get: () => 24});
  Object.defineProperty(screen, 'pixelDepth', {get: () => 24});
  // 8. WebGL masqué
  try {
    const h = {apply:(t,c,a) => {
      if(a[0]===37445) return 'Intel Inc.';
      if(a[0]===37446) return 'Intel(R) UHD Graphics 630';
      return Reflect.apply(t,c,a);
    }};
    WebGLRenderingContext.prototype.getParameter =
      new Proxy(WebGLRenderingContext.prototype.getParameter, h);
  } catch(e) {}
  // 9. Cacher les traces Playwright dans Error stack
  const err = new Error(); const orig = err.stack;
  Object.defineProperty(window, 'Error', {value: class extends Error {
    constructor(m){super(m); if(this.stack) this.stack=this.stack.replace(/playwright/gi,'Chrome');}
  }});
}
"""
        await page.add_init_script(STEALTH_JS)
        try:
            # Injection cookies LinkedIn
            if LINKEDIN_COOKIES_JSON:
                try:
                    raw_cookies = json.loads(LINKEDIN_COOKIES_JSON)
                    pw_cookies = []
                    for c in raw_cookies:
                        same_site = c.get("sameSite", "None")
                        if same_site not in ("Strict", "Lax", "None"):
                            same_site = "None"
                        pw_c = {
                            "name":     c.get("name", ""),
                            "value":    c.get("value", ""),
                            "domain":   c.get("domain", ".linkedin.com"),
                            "path":     c.get("path", "/"),
                            "secure":   bool(c.get("secure", True)),
                            "httpOnly": bool(c.get("httpOnly", False)),
                            "sameSite": same_site,
                            "expires":  int(c.get("expirationDate", 2000000000)),
                        }
                        if pw_c["name"] and pw_c["value"]:
                            pw_cookies.append(pw_c)
                    await browser.add_cookies(pw_cookies)
                    log("Cookies LinkedIn injectes : " + str(len(pw_cookies)) + " cookies")
                except Exception as e:
                    log("Erreur injection cookies : " + str(e)[:80])
            elif LINKEDIN_LI_AT:
                li_at_val = LINKEDIN_LI_AT.strip()
                log("Cookie li_at seul : " + str(len(li_at_val)) + " chars")
                await browser.add_cookies([{
                    "name": "li_at", "value": li_at_val,
                    "domain": ".linkedin.com", "path": "/",
                    "httpOnly": True, "secure": True, "sameSite": "None",
                    "expires": 2000000000,
                }])
            else:
                saved_cookies = _load_cookies()
                if saved_cookies:
                    try:
                        await browser.add_cookies(saved_cookies)
                        log("Cookies LinkedIn charges depuis DB (" + str(len(saved_cookies)) + " cookies)")
                    except Exception as e:
                        log("Cookies (avertissement) : " + str(e)[:50])

            # Vérifier la session LinkedIn
            await page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(4)
            log("URL apres goto feed : " + page.url[:80])
            if "login" in page.url or "authwall" in page.url or "checkpoint" in page.url or "uas" in page.url:
                connecte = await _linkedin_login(page, browser)
                if not connecte:
                    log("Phase 4 annulée — session LinkedIn invalide")
                    return
            else:
                log("Session LinkedIn active")
                cookies = await browser.cookies()
                _save_cookies(cookies)
                log("Cookies mis a jour en base")

            # Postuler à chaque offre retenue
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
                            envoyer_email_candidature(offre, lettre, cv_tailored=offre.get("cv_tailored"))
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
    print("  RESULTATS ORCHESTRATEUR v9")
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
