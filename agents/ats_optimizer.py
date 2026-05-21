import sys
sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
from dotenv import load_dotenv
load_dotenv()
from openai import OpenAI
from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
import os, csv, re, requests as _req
from datetime import datetime
from pathlib import Path

# ============================================================
# CONFIG
# ============================================================

_openai_key  = os.getenv("OPENAI_API_KEY", "")
client       = OpenAI(api_key=_openai_key) if _openai_key else None
CV_PDF_PATH  = os.getenv("CV_PATH", "cv.pdf")
OUTPUT_DIR   = os.path.join(os.getenv("PROFILE_PATH", "."), "cv_optimises")
CSV_SUIVI    = os.path.join(os.getenv("PROFILE_PATH", "."), "suivi_candidatures.csv")

# Statuts qui méritent un CV optimisé
STATUTS_OK = [
    "easy apply", "lien externe", "email envoye", "email envoyé", "email direct",
    "postule", "interesse", "intéressé", "soumis", "lien job bank",
    "email chasseur", "chasseur envoye", "formulaire", "relance", "rh",
]

# Score minimum pour optimiser le CV
SCORE_MIN = 65

# Nombre maximum de CV à générer par session
MAX_CV = 10

# ============================================================
# LOGGER
# ============================================================

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

# ============================================================
# LIRE LE CV PDF
# ============================================================

def lire_pdf(path):
    reader = PdfReader(path)
    return "\n".join(p.extract_text() or "" for p in reader.pages).strip()

# ============================================================
# LIRE LES MEILLEURES CANDIDATURES DU CSV
# ============================================================

def lire_candidatures_saas():
    """Lit les candidatures depuis l'API SaaS (Railway)."""
    api_url = os.getenv("SAAS_API_URL", "")
    token   = os.getenv("SAAS_USER_TOKEN", "")
    if not api_url or not token:
        return []
    if not api_url.startswith("http"):
        api_url = "https://" + api_url
    try:
        resp = _req.get(
            f"{api_url}/api/candidatures",
            headers={"X-User-Token": token},
            timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            rows = data.get("rows", [])
            log(f"SaaS : {len(rows)} candidatures recuperees")
            return rows
    except Exception as e:
        log(f"SaaS API erreur : {e}")
    return []


def lire_meilleures_candidatures():
    """
    Lit le CSV de suivi et retourne les meilleures candidatures
    (score élevé, statut positif, dédoublonnées par entreprise).
    """
    vues = set()
    candidatures = []

    # Essayer d'abord l'API SaaS (Railway)
    rows_saas = lire_candidatures_saas()
    if rows_saas:
        for c in rows_saas:
            entreprise = c.get("entreprise", "")
            poste      = c.get("poste", "")
            statut     = c.get("statut", "").lower()
            score_str  = str(c.get("score", "0"))
            try:
                score = int(re.search(r"\d+", score_str).group()) if re.search(r"\d+", score_str) else 0
            except Exception:
                score = 0
            if not entreprise or not poste:
                continue
            if not any(s in statut for s in STATUTS_OK):
                continue
            if score < SCORE_MIN:
                continue
            cle = entreprise.lower()[:25]
            if cle in vues:
                continue
            vues.add(cle)
            candidatures.append({
                "entreprise": entreprise,
                "poste":      poste,
                "score":      score,
                "lien":       c.get("lien", ""),
                "plateforme": c.get("plateforme", "LinkedIn"),
            })
    else:
        # Fallback CSV local
        chemin = Path(CSV_SUIVI)
        if not chemin.exists():
            log(f"CSV introuvable : {CSV_SUIVI}")
            return []
        for encoding in ["utf-8", "utf-8-sig", "latin-1", "cp1252"]:
            try:
                with open(chemin, "r", encoding=encoding, errors="replace") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        c = {k.strip(): (v or "").strip() for k, v in row.items() if k}
                        entreprise = c.get("entreprise", "")
                        poste      = c.get("poste", "")
                        statut     = c.get("statut", "").lower()
                        score_str  = c.get("score", "0")
                        if not entreprise or not poste:
                            continue
                        try:
                            score = int(re.search(r"\d+", score_str).group())
                        except Exception:
                            score = 0
                        if not any(s in statut for s in STATUTS_OK):
                            continue
                        if score < SCORE_MIN:
                            continue
                        cle = entreprise.lower()[:25]
                        if cle in vues:
                            continue
                        vues.add(cle)
                        candidatures.append({
                            "entreprise": entreprise,
                            "poste":      poste,
                            "score":      score,
                            "lien":       c.get("lien", ""),
                            "plateforme": c.get("plateforme", "LinkedIn"),
                        })
                break
            except Exception:
                continue

    # Trier par score décroissant
    candidatures.sort(key=lambda x: x["score"], reverse=True)
    return candidatures[:MAX_CV]

# ============================================================
# OPTIMISER LE CV AVEC GPT-4o
# ============================================================

def optimiser_cv(cv_texte, entreprise, poste):
    prompt = f"""
Tu es un expert en recrutement et optimisation ATS (Applicant Tracking System).

Voici le CV original du candidat :
---
{cv_texte}
---

Poste visé : {poste}
Entreprise : {entreprise}

MISSION :
Réécris le CV en l'optimisant pour ce poste spécifique chez {entreprise}.

RÈGLES STRICTES :
1. Conserver toutes les informations vraies du CV — ne rien inventer
2. Réorganiser et reformuler pour maximiser la compatibilité ATS
3. Intégrer les mots-clés du poste là où c'est pertinent et honnête
4. Mettre en avant les expériences les plus pertinentes pour ce poste
5. Utiliser des verbes d'action forts au début de chaque point
6. Format clair : sections en MAJUSCULES
7. Langue française

SECTIONS (dans cet ordre) :
- INFORMATIONS PERSONNELLES
- RÉSUMÉ PROFESSIONNEL (3-4 lignes ciblées sur ce poste chez {entreprise})
- COMPÉTENCES CLÉS (mots-clés ATS du poste)
- EXPÉRIENCE PROFESSIONNELLE
- FORMATION
- CERTIFICATIONS

Retourne uniquement le CV optimisé, sans explication ni commentaire.
"""
    if not client:
        raise Exception("OPENAI_API_KEY non configurée — ajoutez-la dans les paramètres Railway")
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=2000
    )
    return response.choices[0].message.content.strip()

# ============================================================
# SAUVEGARDER EN PDF
# ============================================================

def _nom_fichier_safe(s):
    """Supprime les caractères illégaux Windows dans un nom de fichier."""
    return re.sub(r'[<>:"/\\|?*()\[\]]', '', s).replace(' ', '_').strip('._')[:30]

def sauvegarder_pdf(texte, entreprise):
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    date   = datetime.now().strftime("%Y%m%d_%H%M%S")
    nom_f  = f"CV_{_nom_fichier_safe(entreprise)}_{date}.pdf"
    chemin = Path(OUTPUT_DIR) / nom_f

    doc    = SimpleDocTemplate(str(chemin), pagesize=letter,
                               topMargin=0.75*inch, bottomMargin=0.75*inch,
                               leftMargin=inch, rightMargin=inch)
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "TitleStyle", parent=styles["Heading1"],
        fontSize=13, textColor=colors.HexColor("#1a3a5c"), spaceAfter=4
    )
    body_style = ParagraphStyle(
        "BodyStyle", parent=styles["Normal"],
        fontSize=10, leading=14, spaceAfter=4
    )
    section_style = ParagraphStyle(
        "SectionStyle", parent=styles["Heading2"],
        fontSize=11, textColor=colors.HexColor("#1a3a5c"),
        spaceBefore=12, spaceAfter=4
    )

    story = []
    for line in texte.split("\n"):
        line = line.strip()
        if not line:
            story.append(Spacer(1, 6))
        elif line.isupper() and len(line) > 3:
            story.append(Paragraph(line, section_style))
        elif line.startswith("•") or line.startswith("-"):
            story.append(Paragraph(f"&nbsp;&nbsp;{line}", body_style))
        else:
            story.append(Paragraph(line, body_style))

    doc.build(story)
    return str(chemin)

# ============================================================
# SAUVEGARDER EN TXT (backup)
# ============================================================

def sauvegarder_txt(texte, entreprise):
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    date   = datetime.now().strftime("%Y%m%d_%H%M%S")
    nom_f  = f"CV_{_nom_fichier_safe(entreprise)}_{date}.txt"
    chemin = Path(OUTPUT_DIR) / nom_f
    with open(chemin, "w", encoding="utf-8") as f:
        f.write(texte)
    return str(chemin)

# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    log("🚀 ATS Optimizer démarré")
    print()

    # Vérifier le CV
    if not Path(CV_PDF_PATH).exists():
        log(f"❌ CV introuvable : {CV_PDF_PATH}")
        exit()

    # Lire le CV
    log(f"📄 Lecture du CV : {CV_PDF_PATH}")
    try:
        cv_texte = lire_pdf(CV_PDF_PATH)
        log(f"✅ CV lu ({len(cv_texte)} caractères)")
    except Exception as e:
        log(f"❌ Erreur lecture CV : {e}")
        exit()

    # Lire les meilleures candidatures du CSV
    log(f"📋 Lecture des candidatures depuis le CSV...")
    candidatures = lire_meilleures_candidatures()

    if not candidatures:
        log("⚠️  Aucune candidature éligible trouvée dans le CSV")
        log(f"   → Score minimum requis : {SCORE_MIN}/100")
        log(f"   → Statuts acceptés : Easy Apply, Email envoyé, Lien externe...")
        exit()

    log(f"✅ {len(candidatures)} candidature(s) retenues pour optimisation")
    print()
    print("─" * 60)
    for i, c in enumerate(candidatures, 1):
        print(f"  {i:2d}. [{c['score']:3d}/100] {c['entreprise'][:35]} — {c['poste'][:30]}")
    print("─" * 60)
    print()

    # Optimiser un CV par candidature
    succes = 0
    for i, cand in enumerate(candidatures, 1):
        entreprise = cand["entreprise"]
        poste      = cand["poste"]
        score      = cand["score"]

        log(f"[{i}/{len(candidatures)}] {entreprise} — {poste[:40]}")
        log(f"   Score : {score}/100 | Plateforme : {cand['plateforme']}")

        try:
            log("   🤖 Optimisation ATS en cours...")
            cv_optimise = optimiser_cv(cv_texte, entreprise, poste)

            # Sauvegarder PDF
            chemin_pdf = sauvegarder_pdf(cv_optimise, entreprise)
            log(f"   ✅ PDF : {Path(chemin_pdf).name}")

            # Sauvegarder TXT backup
            sauvegarder_txt(cv_optimise, entreprise)

            succes += 1
            print()

        except Exception as e:
            log(f"   ❌ Erreur : {str(e)[:60]}")
            print()

    # Résultats
    print("=" * 60)
    print(f"  ATS OPTIMIZER — RÉSULTATS")
    print(f"  CV optimisés : {succes}/{len(candidatures)}")
    print(f"  Dossier      : {OUTPUT_DIR}/")
    print("=" * 60)
    log("✅ ATS Optimizer terminé !")
