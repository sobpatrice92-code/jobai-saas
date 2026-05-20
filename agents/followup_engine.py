import sys
sys.stdout.reconfigure(encoding="utf-8")
from dotenv import load_dotenv
load_dotenv()

from openai import OpenAI
import os, csv, smtplib, re, unicodedata
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime, timedelta
from pathlib import Path

# ============================================================
# CONFIG
# ============================================================

client         = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
GMAIL_ADDRESS  = os.getenv("GMAIL_ADDRESS")
GMAIL_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
CV_PATH        = os.getenv("CV_PATH", "cv.pdf")

CSV_PRINCIPAL  = os.path.join(os.getenv("PROFILE_PATH", "."), "suivi_candidatures.csv")
CSV_RELANCES   = os.path.join(os.getenv("PROFILE_PATH", "."), "suivi_relances.csv")

DELAI_RELANCE_MIN = 5
DELAI_RELANCE_MAX = 10

# Tous les statuts méritent une relance (y compris manuelle requise)
STATUTS_A_RELANCER = [
    "lien externe", "easy apply", "email envoye", "email envoyé",
    "email direct", "email chasseur", "chasseur envoye",
    "postule", "interesse", "intéressé", "externe (manuel)", "timeout",
    "soumis", "lien job bank", "formulaire", "manuelle", "rh",
]

STATUTS_EXCLURE = [
    "refusé", "refuse", "échec", "echec",
]

# ============================================================
# EMAILS RH DIRECTS
# ============================================================

EMAILS_RH = {
    "ville d'ottawa": "recrutement@ottawa.ca", "city of ottawa": "recrutement@ottawa.ca",
    "city of / ville d'": "recrutement@ottawa.ca",
    "ville de gatineau": "rh@gatineau.ca", "defence construction": "careers@dcc-cdc.gc.ca",
    "national research": "careers@nrc-cnrc.gc.ca", "conseil national": "careers@nrc-cnrc.gc.ca",
    "national capital": "careers@ncc-ccn.ca", "commission de la capitale": "careers@ncc-ccn.ca",
    "stantec": "careers@stantec.com", "wsp": "careers@wsp.com", "aecom": "careers@aecom.ca",
    "artelia": "recrutement@artelia.com", "vinci": "recrutement@vinci.com",
    "bird construction": "hr@bird.ca", "minto": "careers@minto.com",
    "broccolini": "rh@broccolini.ca", "pcl": "careers@pcl.com", "ellisdon": "careers@ellisdon.com",
    "hays": "ottawa@hays.com", "randstad": "ottawa@randstad.ca",
    "robert half": "ottawa@roberthalf.com", "michael page": "canada@michaelpage.com",
    "bpdl": "rh@bpdl.ca", "tehora": "rh@tehora.ca", "coffrages synergy": "rh@coffragessynergy.com",
    "parisien": "rh@parisien.ca", "groupe emd": "rh@emdbatimo.com", "emd batimo": "rh@emdbatimo.com",
    "constructions genix": "rh@genix.ca", "genix": "rh@genix.ca",
    "precision drain": "info@precisiondrain.ca", "bourg": "rh@bourgconstruction.ca",
    "turner": "ottawa@turnerandtownsend.com", "direct construction": "hr@directconstruction.ca",
    "bgis": "careers@bgis.com", "qualnet": "info@qualnet.ca",
    "cima": "carrieres@cima.ca", "exp": "careers@exp.com",
    "englobe": "careers@englobe.com", "geos": "info@groupegeos.com",
    "bank of canada": "careers@bankofcanada.ca", "banque du canada": "careers@bankofcanada.ca",
    "structure pvl": "info@structurepvl.com", "bhullar": "hr@bhullar.ca",
    "promu": "rh@promu.ca", "tango": "rh@tangosolutionsrh.ca",
    "rooney": "careers@rooneyirving.ca", "st-denis thompson": "rh@stdenis.ca",
    "lro staffing": "ottawa@lrostaffing.com", "prodigy": "hr@prodigygroup.ca",
    "gemtec": "hr@gemtec.ca", "cheo": "careers@cheo.on.ca",
    "conseil des ecoles": "rh@ecolescatholiques.ca", "cepeo": "rh@cepeo.on.ca",
}

def _norm(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s)
                   if unicodedata.category(c) != 'Mn').lower()

def trouver_email_rh(company):
    c = _norm(company)
    for cle, email_rh in EMAILS_RH.items():
        if _norm(cle) in c or c in _norm(cle):
            return email_rh
    return None

# ============================================================
# LOGGER
# ============================================================

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

# ============================================================
# LIRE LE CSV PRINCIPAL
# ============================================================

def lire_candidatures():
    """
    Lit le CSV principal et retourne toutes les candidatures.
    Gère les encodages corrompus (latin-1, utf-8-sig).
    """
    candidatures = []
    chemin = Path(CSV_PRINCIPAL)

    if not chemin.exists():
        log(f"❌ CSV introuvable : {CSV_PRINCIPAL}")
        return []

    # Essayer plusieurs encodages
    PLATEFORMES = {"linkedin", "indeed", "job bank", "glassdoor", "workopolis", "n/a", "autre"}

    def corriger_colonnes(c):
        p  = c.get("poste", "")
        pf = c.get("plateforme", "")
        e  = c.get("entreprise", "")
        li = c.get("lien", "")
        if p.startswith("http") and pf.lower() not in PLATEFORMES:
            if "indeed" in p:      pf_ok = "Indeed"
            elif "linkedin" in p:  pf_ok = "LinkedIn"
            elif "jobbank" in p:   pf_ok = "Job Bank Canada"
            elif "glassdoor" in p: pf_ok = "Glassdoor"
            else:                  pf_ok = li if li.lower() in PLATEFORMES else "Autre"
            return dict(c, entreprise=pf, poste=e, lien=p, plateforme=pf_ok)
        return c

    for encoding in ["utf-8", "utf-8-sig", "latin-1", "cp1252"]:
        try:
            with open(chemin, "r", encoding=encoding, errors="replace") as f:
                reader = csv.DictReader(f)
                candidatures = []
                for row in reader:
                    clean = {k.strip(): (v or "").strip() for k, v in row.items() if k}
                    clean = corriger_colonnes(clean)
                    candidatures.append(clean)
            log(f"✅ CSV lu ({encoding}) : {len(candidatures)} entrées")
            break
        except Exception as e:
            continue

    return candidatures

# ============================================================
# LIRE LES RELANCES DÉJÀ ENVOYÉES
# ============================================================

def lire_relances_envoyees():
    """Retourne un set de clés (entreprise+poste) déjà relancées."""
    deja_relances = set()
    chemin = Path(CSV_RELANCES)
    if not chemin.exists():
        return deja_relances
    try:
        with open(chemin, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            for row in reader:
                cle = (row.get("entreprise", "").lower().strip() +
                       row.get("poste", "").lower().strip()[:20])
                deja_relances.add(cle)
    except Exception:
        pass
    return deja_relances

# ============================================================
# SAUVEGARDER UNE RELANCE
# ============================================================

def sauvegarder_relance(entreprise, poste, lien, statut):
    chemin = Path(CSV_RELANCES)
    existe = chemin.exists()
    try:
        with open(chemin, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "date_relance", "entreprise", "poste", "lien", "statut"
            ])
            if not existe:
                writer.writeheader()
            writer.writerow({
                "date_relance": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "entreprise":   entreprise,
                "poste":        poste,
                "lien":         lien,
                "statut":       statut
            })
    except Exception as e:
        log(f"⚠️ Erreur sauvegarde relance : {e}")

# ============================================================
# IDENTIFIER LES CANDIDATURES À RELANCER
# ============================================================

def identifier_relances(candidatures, deja_relances):
    """
    Sélectionne les candidatures :
    - envoyées il y a entre DELAI_MIN et DELAI_MAX jours
    - avec un statut positif (pas refusé/échec)
    - pas encore relancées
    - dédoublonnées (garder la plus récente par entreprise+poste)
    """
    maintenant  = datetime.now()
    date_min    = maintenant - timedelta(days=DELAI_RELANCE_MAX)
    date_max    = maintenant - timedelta(days=DELAI_RELANCE_MIN)

    # Dédoublonner : garder la candidature la plus récente par entreprise+poste
    vues = {}
    for c in candidatures:
        entreprise = c.get("entreprise", "").strip()
        poste      = c.get("poste", "").strip()
        statut     = c.get("statut", "").lower().strip()
        date_str   = c.get("date", "").strip()

        if not entreprise or not date_str:
            continue

        # Parser la date
        try:
            date_cand = datetime.strptime(date_str[:16], "%Y-%m-%d %H:%M")
        except Exception:
            try:
                date_cand = datetime.strptime(date_str[:10], "%Y-%m-%d")
            except Exception:
                continue

        cle = entreprise.lower()[:20] + poste.lower()[:20]

        # Garder la plus récente
        if cle not in vues or date_cand > vues[cle]["date"]:
            vues[cle] = {
                "entreprise": entreprise,
                "poste":      poste,
                "lien":       c.get("lien", ""),
                "statut":     statut,
                "date":       date_cand,
                "cle":        cle
            }

    # Filtrer
    a_relancer = []
    for cle, c in vues.items():
        statut = c["statut"]

        # Exclure refus/échecs
        if any(ex in statut for ex in STATUTS_EXCLURE):
            continue

        # Vérifier que le statut mérite une relance
        statut_ok = any(s in statut for s in STATUTS_A_RELANCER)
        if not statut_ok:
            continue

        # Vérifier la fenêtre de temps
        if not (date_min <= c["date"] <= date_max):
            continue

        # Pas encore relancé
        if cle in deja_relances:
            continue

        a_relancer.append(c)

    # Trier par date (les plus anciennes en premier)
    a_relancer.sort(key=lambda x: x["date"])
    return a_relancer

# ============================================================
# GÉNÉRER LA LETTRE DE RELANCE
# ============================================================

def generer_lettre_relance(entreprise, poste, date_candidature):
    date_str      = datetime.now().strftime("%d %B %Y")
    date_cand_str = date_candidature.strftime("%d %B %Y")

    entete = (
        "Patrice Arnold Sob Feukam\n"
        "Vanier, Ottawa, Ontario\n"
        "Tél : 514-236-4628 | Email : sobpatrice@yahoo.fr\n\n"
        f"{date_str}\n\n"
        f"Objet : Relance — Candidature pour le poste de {poste} chez {entreprise}\n\n"
        "Madame, Monsieur,\n\n"
    )

    prompt = (
        f"Rédige une lettre de relance professionnelle et humaine en français.\n"
        f"Candidat : Patrice Arnold Sob Feukam\n"
        f"Poste visé : {poste}\n"
        f"Entreprise : {entreprise}\n"
        f"Date de candidature initiale : {date_cand_str}\n\n"
        f"RÈGLES STRICTES :\n"
        f"- Ton chaleureux, professionnel, jamais insistant\n"
        f"- P1 : Rappel de la candidature envoyée le {date_cand_str} pour le poste de {poste}\n"
        f"- P2 : Réaffirmer l'intérêt et mentionner 1 compétence clé concrète "
        f"(AutoCAD, Revit, Civil 3D, MS Project, 8 ans SPA Construction Cameroun, carte ASP, PMP en cours)\n"
        f"- P3 : Disponibilité immédiate Ottawa-Gatineau, invitation à un entretien\n"
        f"- ZERO crochet [X], ZERO placeholder\n"
        f"- Maximum 4 paragraphes courts\n"
        f"Retourne uniquement les paragraphes du corps, sans entête ni signature."
    )

    try:
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500
        )
        corps = resp.choices[0].message.content.strip()
    except Exception as e:
        log(f"⚠️ GPT erreur : {e}")
        corps = (
            f"Je me permets de revenir vers vous concernant ma candidature pour le poste de "
            f"{poste}, que je vous ai adressée le {date_cand_str}.\n\n"
            f"Fort de 8 ans d'expérience en gestion de projets de construction chez SPA Construction SARL "
            f"au Cameroun, et actuellement étudiant en Technologie de la construction à La Cité (Ottawa), "
            f"je reste très motivé par cette opportunité au sein de {entreprise}.\n\n"
            f"Je suis disponible immédiatement dans la région Ottawa-Gatineau et serais ravi de vous "
            f"rencontrer pour discuter de ma candidature."
        )

    signature = (
        "\n\nCordialement,\n\n"
        "Patrice Arnold Sob Feukam\n"
        "514-236-4628 | sobpatrice@yahoo.fr\n"
        "Ottawa, Ontario"
    )
    return entete + corps + signature

# ============================================================
# ENVOYER EMAIL DE RELANCE — DIRECTEMENT AU RH
# ============================================================

def envoyer_relance(entreprise, poste, lien, lettre):
    # Chercher l'email RH de l'entreprise
    email_rh = trouver_email_rh(entreprise)

    if not email_rh:
        log(f"   ⚠️ Email RH introuvable pour : {entreprise} — relance ignorée")
        return False, None

    try:
        # Email direct au recruteur
        msg = MIMEMultipart()
        msg["From"]    = GMAIL_ADDRESS
        msg["To"]      = email_rh
        msg["Subject"] = f"Relance candidature — {poste} | {entreprise}"
        msg.attach(MIMEText(lettre, "plain", "utf-8"))

        cv = Path(CV_PATH)
        if cv.exists():
            with open(cv, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition",
                'attachment; filename="CV_Patrice_Arnold_Sob_Feukam.pdf"')
            msg.attach(part)

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_ADDRESS, GMAIL_PASSWORD)
            server.sendmail(GMAIL_ADDRESS, email_rh, msg.as_string())

        # Notification à soi-même
        notif = MIMEMultipart()
        notif["From"]    = GMAIL_ADDRESS
        notif["To"]      = GMAIL_ADDRESS
        notif["Subject"] = f"[RELANCE ENVOYÉE] {poste} | {entreprise} → {email_rh}"
        corps_notif = (
            f"Relance envoyée automatiquement !\n\n"
            f"Entreprise : {entreprise}\n"
            f"Poste      : {poste}\n"
            f"Email RH   : {email_rh}\n"
            f"Lien       : {lien}\n\n"
            f"{'─'*44}\n\n"
            f"{lettre}"
        )
        notif.attach(MIMEText(corps_notif, "plain", "utf-8"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_ADDRESS, GMAIL_PASSWORD)
            server.sendmail(GMAIL_ADDRESS, GMAIL_ADDRESS, notif.as_string())

        return True, email_rh

    except Exception as e:
        log(f"   ⚠️ Email erreur : {str(e)[:60]}")
        return False, None

# ============================================================
# AFFICHER STATISTIQUES DU CSV
# ============================================================

def afficher_stats(candidatures):
    total     = len(candidatures)
    par_statut = {}
    for c in candidatures:
        s = c.get("statut", "Inconnu").strip()
        # Simplifier l'affichage
        if "easy apply" in s.lower():
            s = "Easy Apply ✅"
        elif "lien externe" in s.lower():
            s = "Lien externe"
        elif "email envoye" in s.lower() or "email envoyé" in s.lower():
            s = "Email envoyé"
        elif "refus" in s.lower():
            s = "Refusé ❌"
        elif "echec" in s.lower() or "échec" in s.lower():
            s = "Échec ❌"
        elif "timeout" in s.lower():
            s = "Timeout ⏰"
        elif "interesse" in s.lower() or "intéressé" in s.lower():
            s = "Intéressé 🟡"
        elif "manuelle" in s.lower():
            s = "Manuelle requise ⚠️"
        par_statut[s] = par_statut.get(s, 0) + 1

    print()
    print("─" * 50)
    print(f"  BILAN CANDIDATURES ({total} total)")
    print("─" * 50)
    for statut, nb in sorted(par_statut.items(), key=lambda x: -x[1]):
        print(f"  {nb:3d}  {statut}")
    print("─" * 50)
    print()

# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    log("🚀 Follow-up Engine démarré")
    print()

    # 1. Lire toutes les candidatures
    candidatures = lire_candidatures()
    if not candidatures:
        log("⛔ Aucune candidature trouvée.")
        exit()

    # 2. Afficher les stats
    afficher_stats(candidatures)

    # 3. Lire les relances déjà envoyées
    deja_relances = lire_relances_envoyees()
    log(f"📋 {len(deja_relances)} entreprises déjà relancées (historique)")

    # 4. Identifier les candidatures à relancer
    a_relancer = identifier_relances(candidatures, deja_relances)
    log(f"🎯 {len(a_relancer)} candidature(s) à relancer aujourd'hui "
        f"(entre {DELAI_RELANCE_MIN} et {DELAI_RELANCE_MAX} jours)")

    if not a_relancer:
        log("✅ Aucune relance nécessaire aujourd'hui.")
        print()

        # Afficher ce qui arrive bientôt
        maintenant = datetime.now()
        bientot = []
        vues = set()
        for c in candidatures:
            statut = c.get("statut", "").lower()
            if any(ex in statut for ex in STATUTS_EXCLURE):
                continue
            if not any(s in statut for s in STATUTS_A_RELANCER):
                continue
            try:
                date_cand = datetime.strptime(c.get("date", "")[:16], "%Y-%m-%d %H:%M")
            except Exception:
                continue
            jours_restants = DELAI_RELANCE_MIN - (maintenant - date_cand).days
            if 0 < jours_restants <= 3:
                cle = c.get("entreprise", "").lower()[:20] + c.get("poste", "").lower()[:20]
                if cle not in vues and cle not in deja_relances:
                    vues.add(cle)
                    bientot.append({
                        "entreprise": c.get("entreprise", ""),
                        "poste":      c.get("poste", ""),
                        "dans":       jours_restants
                    })

        if bientot:
            bientot.sort(key=lambda x: x["dans"])
            log("📅 Prochaines relances :")
            for b in bientot[:5]:
                log(f"   Dans {b['dans']}j → {b['entreprise']} — {b['poste'][:40]}")
        exit()

    # 5. Envoyer les relances
    print()
    stats = {"ok": 0, "erreur": 0, "ignore": 0}

    for i, c in enumerate(a_relancer, 1):
        entreprise = c["entreprise"]
        poste      = c["poste"]
        lien       = c["lien"]
        date_cand  = c["date"]
        jours      = (datetime.now() - date_cand).days

        log(f"[{i}/{len(a_relancer)}] {entreprise} — {poste[:40]}")
        log(f"   Candidature du {date_cand.strftime('%d/%m/%Y')} ({jours} jours)")

        try:
            lettre = generer_lettre_relance(entreprise, poste, date_cand)
            log(f"   ✉️  Lettre générée")

            ok, email_rh = envoyer_relance(entreprise, poste, lien, lettre)
            if ok:
                log(f"   ✅ Relance envoyée directement à : {email_rh}")
                sauvegarder_relance(entreprise, poste, lien, f"Relance → {email_rh}")
                stats["ok"] += 1
            else:
                log(f"   ⏭️  Ignorée (email RH introuvable)")
                stats["ignore"] += 1

        except Exception as e:
            log(f"   ❌ Erreur : {str(e)[:60]}")
            stats["erreur"] += 1

        print()

    # 6. Résultats
    print("=" * 50)
    print(f"  RÉSULTATS FOLLOW-UP ENGINE")
    print(f"  Relances envoyées : {stats['ok']} (directs au RH)")
    print(f"  Ignorées          : {stats['ignore']} (email RH introuvable)")
    print(f"  Erreurs           : {stats['erreur']}")
    print("=" * 50)
    log("✅ Follow-up Engine terminé !")
