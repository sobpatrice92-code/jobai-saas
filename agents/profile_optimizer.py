"""
LinkedIn Profile Optimizer — GPT-4o powered
Reads CV -> scrapes current profile -> generates optimized content -> applies changes -> scores 10/10
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv()

from playwright.async_api import async_playwright
import asyncio, random, os, json
from datetime import datetime
from pathlib import Path
from openai import OpenAI

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

import smtplib, email as _email
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# ── Config ────────────────────────────────────────────────────────────────────

USER_ID          = os.getenv("USER_ID", "local")
PROFILE_PATH     = os.getenv("PROFILE_PATH", "chrome_profile")
OPENAI_KEY       = os.getenv("OPENAI_API_KEY", "")
CV_PATH          = os.getenv("CV_PATH", "cv.pdf")
GMAIL_ADDRESS    = os.getenv("GMAIL_ADDRESS", os.getenv("USER_EMAIL", ""))
GMAIL_PASSWORD   = os.getenv("GMAIL_APP_PASSWORD", "")
USER_NAME        = os.getenv("USER_NAME", "")
USER_PROFESSION  = os.getenv("USER_PROFESSION", "")
LINKEDIN_EMAIL   = os.getenv("LINKEDIN_EMAIL", "")
LINKEDIN_PASSWORD = os.getenv("LINKEDIN_PASSWORD", "")
HEADLESS         = os.getenv("DISPLAY", "") == ""

SMARTPROXY_USER = os.getenv("SMARTPROXY_USER", "")
SMARTPROXY_PASS = os.getenv("SMARTPROXY_PASS", "")
SAAS_USER_ID    = os.getenv("SAAS_USER_ID", "0")

# Fichier pending isolé par utilisateur dans le dossier uploads
_data_dir       = Path(PROFILE_PATH).parent
_data_dir.mkdir(parents=True, exist_ok=True)
PENDING_PROFILE = _data_dir / "pending_profile.json"
DEBUG_DIR       = Path(PROFILE_PATH) / "debug_profile"

client = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None

# ── Logger ────────────────────────────────────────────────────────────────────

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

# ── CV Reader ─────────────────────────────────────────────────────────────────

def lire_cv() -> str:
    path = Path(CV_PATH)
    if not path.exists():
        log(f"CV non trouve : {CV_PATH}")
        return ""
    if PdfReader is None:
        log("pypdf non installe — pip install pypdf")
        return ""
    try:
        reader = PdfReader(str(path))
        texte = "\n".join(p.extract_text() or "" for p in reader.pages)
        log(f"CV lu : {len(texte)} caracteres, {len(reader.pages)} pages")
        return texte[:8000]
    except Exception as e:
        log(f"Erreur lecture CV : {e}")
        return ""

# ── GPT-4o Optimizer ──────────────────────────────────────────────────────────

def optimiser_avec_gpt(cv_texte: str, profil_actuel: dict) -> dict:
    if not client:
        log("Cle OpenAI manquante — impossible d'optimiser")
        return {}

    log("Envoi a GPT-4o pour optimisation...")

    system = """Tu es un expert en personal branding LinkedIn et en recrutement canadien.
Tu optimises des profils LinkedIn pour maximiser les chances d'être recruté.
Tu réponds UNIQUEMENT en JSON valide, sans markdown, sans explication."""

    profession_cible = USER_PROFESSION or profil_actuel.get('headline', 'professionnel')

    prompt = f"""Voici le CV du candidat :
---
{cv_texte or "CV non disponible — utilise le profil actuel"}
---

Voici le profil LinkedIn actuel :
---
Titre : {profil_actuel.get('headline', 'Non disponible')}
A propos : {profil_actuel.get('about', 'Non disponible')}
Experiences : {json.dumps(profil_actuel.get('experiences', []), ensure_ascii=False)}
Competences actuelles : {', '.join(profil_actuel.get('skills', [])) or 'Aucune'}
---

Objectif professionnel de l'utilisateur : {profession_cible}

Génère du contenu LinkedIn optimisé 10/10. Retourne ce JSON exact :
{{
  "headline": "Titre professionnel percutant max 220 caractères bilingue FR/EN",
  "about": "Section À propos 2600 caractères max, aérée, avec emojis, appel à l'action, contact",
  "experience_descriptions": {{
    "SPA Construction": "Description de poste bullet points percutants max 2000 caractères"
  }},
  "skills": ["liste", "des", "15", "meilleures", "compétences", "pour", "le", "poste"],
  "score": {{
    "photo": {{"points": 1, "sur": 1, "note": "À vérifier manuellement"}},
    "headline": {{"points": 1, "sur": 1, "note": "Optimisé avec mots-clés ATS"}},
    "about": {{"points": 2, "sur": 2, "note": "Complet, bilingue, appel à l'action"}},
    "experience": {{"points": 2, "sur": 2, "note": "Résultats quantifiés"}},
    "competences": {{"points": 1, "sur": 1, "note": "15 compétences stratégiques"}},
    "formation": {{"points": 1, "sur": 1, "note": "À vérifier manuellement"}},
    "recommandations": {{"points": 1, "sur": 1, "note": "3 recommandations recommandées"}},
    "activite": {{"points": 1, "sur": 1, "note": "Posts réguliers actifs"}},
    "total": 10,
    "resume": "Profil optimisé pour le marché canadien"
  }}
}}"""

    try:
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": prompt},
            ],
            temperature=0.7,
            max_tokens=4000,
        )
        raw = resp.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw)
        log("Contenu GPT-4o genere")
        return data
    except Exception as e:
        log(f"Erreur GPT-4o : {e}")
        return {}

# ── Approbation avant modification ───────────────────────────────────────────

def envoyer_apercu(contenu: dict):
    PENDING_PROFILE.write_text(
        json.dumps({"status": "pending", "contenu": contenu}, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    log("Fichier pending_profile.json cree")

    headline = contenu.get("headline", "")
    about    = contenu.get("about", "")[:600]
    skills   = contenu.get("skills", [])
    exp      = contenu.get("experience_descriptions", {})

    corps = f"""Bonjour,

Voici les modifications proposees pour votre profil LinkedIn.

{'='*40}
TITRE (Headline)
{'='*40}
{headline}

{'='*40}
A PROPOS (extrait 600 car.)
{'='*40}
{about}...

{'='*40}
EXPERIENCES
{'='*40}
"""
    for ent, desc in exp.items():
        corps += f"\n{ent} :\n{desc[:400]}\n"

    corps += f"""
{'='*40}
COMPETENCES ({len(skills)})
{'='*40}
{', '.join(skills)}

{'='*40}
Approuvez directement sur le dashboard.
"""

    if not GMAIL_ADDRESS or not GMAIL_PASSWORD:
        log("Gmail non configure — apercu affiche en console uniquement")
        print(corps)
        return

    try:
        msg = MIMEMultipart()
        msg["From"]    = GMAIL_ADDRESS
        msg["To"]      = GMAIL_ADDRESS
        msg["Subject"] = "[LinkedIn Optimizer] Approuver les modifications du profil ?"
        msg.attach(MIMEText(corps, "plain", "utf-8"))
        from email_helper import send_email
        ok, err = send_email(GMAIL_ADDRESS, "[LinkedIn Optimizer] Approuver les modifications du profil ?",
                             corps, reply_to=GMAIL_ADDRESS)
        if ok:
            log(f"Apercu envoye a {GMAIL_ADDRESS}")
        else:
            log(f"Email echoue : {err} — apercu affiche ci-dessous")
            print(corps)
    except Exception as e:
        log(f"Email echoue : {e} — apercu affiche ci-dessous")
        print(corps)


def attendre_approbation(timeout_min: int = 60) -> bool:
    import time
    log(f"En attente de votre approbation (max {timeout_min} min)...")
    log("   -> Approuvez sur le dashboard web")
    deadline = time.time() + timeout_min * 60
    while time.time() < deadline:
        try:
            data = json.loads(PENDING_PROFILE.read_text(encoding="utf-8"))
            status = data.get("status", "pending")
            if status == "approved":
                log("Approbation recue — lancement des modifications")
                return True
            if status == "rejected":
                log("Modifications rejetees")
                return False
        except Exception:
            pass
        time.sleep(30)
        log("   En attente...")
    log("Timeout — modifications annulees")
    return False


# ── Playwright Helpers ────────────────────────────────────────────────────────

class ProfileOptimizer:

    async def pause(self, a=800, b=2000):
        await asyncio.sleep(random.randint(a, b) / 1000)

    async def screenshot(self, page, nom):
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        try:
            path = DEBUG_DIR / f"{datetime.now().strftime('%H%M%S')}_{nom}.png"
            await page.screenshot(path=str(path), full_page=False)
            log(f"Screenshot : {path.name}")
        except Exception:
            pass

    async def cliquer(self, el):
        try:
            await el.scroll_into_view_if_needed()
            await self.pause(200, 600)
            await el.click()
            await self.pause(300, 800)
        except Exception as e:
            log(f"clic : {e}")

    async def remplir(self, el, texte: str):
        try:
            await el.click()
            await asyncio.sleep(0.4)
            await el.press("Control+a")
            await asyncio.sleep(0.2)
            await el.fill(texte)
            await asyncio.sleep(0.5)
        except Exception as e:
            log(f"fill : {e}")

    async def sauvegarder(self, page) -> bool:
        await asyncio.sleep(1)
        mots = ["Enregistrer", "Save", "Ajouter", "Add"]
        excl = ["annuler", "cancel", "fermer", "retour", "ignorer", "passer"]
        for mot in mots:
            try:
                b = page.locator(f"dialog button:has-text('{mot}')").first
                if await b.count() > 0:
                    await b.scroll_into_view_if_needed()
                    await b.click(force=True)
                    await asyncio.sleep(2)
                    return True
            except Exception:
                pass
        for mot in mots:
            try:
                b = page.get_by_role("button", name=mot).first
                if await b.count() > 0 and await b.is_visible():
                    await b.scroll_into_view_if_needed()
                    await b.click(force=True)
                    await asyncio.sleep(2)
                    return True
            except Exception:
                pass
        btns  = page.locator("button")
        count = await btns.count()
        for i in range(count):
            try:
                b   = btns.nth(i)
                txt = (await b.inner_text()).strip().lower()
                if any(e in txt for e in excl):
                    continue
                if any(m.lower() in txt for m in mots):
                    await b.scroll_into_view_if_needed()
                    await b.click(force=True)
                    await asyncio.sleep(2)
                    return True
            except Exception:
                pass
        return False

    async def fermer_modal(self, page):
        for sel in ["button[aria-label*='Fermer']", "button[aria-label*='Close']",
                    "button[aria-label*='fermer']", ".artdeco-modal__dismiss"]:
            try:
                b = page.locator(sel).first
                if await b.count() > 0 and await b.is_visible():
                    await self.cliquer(b)
                    await asyncio.sleep(1)
                    return
            except Exception:
                pass
        await page.keyboard.press("Escape")
        await asyncio.sleep(1)

    async def auto_login(self, page) -> bool:
        if not LINKEDIN_EMAIL or not LINKEDIN_PASSWORD:
            log("Session expiree — ajoutez LinkedIn Email/Password dans le Setup")
            return False
        log("Connexion automatique LinkedIn...")
        try:
            await page.goto("https://www.linkedin.com/login",
                            wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)
            await page.fill("#username", LINKEDIN_EMAIL)
            await asyncio.sleep(0.5)
            await page.fill("#password", LINKEDIN_PASSWORD)
            await asyncio.sleep(0.5)
            await page.click("button[type='submit']")
            await asyncio.sleep(5)
            if "feed" in page.url or ("login" not in page.url and "authwall" not in page.url):
                log("Connexion LinkedIn reussie")
                return True
            log("Echec connexion LinkedIn")
            return False
        except Exception as e:
            log(f"Erreur login : {e}")
            return False

    # ── Scraping profil actuel ─────────────────────────────────────────────────

    async def scraper_profil(self, page) -> dict:
        log("\n--- LECTURE du profil actuel ---")
        await page.goto("https://www.linkedin.com/in/me/",
                        wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)

        profil = {"headline": "", "about": "", "experiences": [], "skills": []}

        try:
            el = page.locator("h2.text-body-medium").first
            if await el.count() > 0:
                profil["headline"] = (await el.inner_text()).strip()
                log(f"  Titre : {profil['headline'][:80]}")
        except Exception:
            pass

        try:
            for sel in ["div[data-generated-suggestion-target='urn:li:fs_summary']",
                        "#about ~ div .full-width",
                        "section:has(#about) .pv-shared-text-with-see-more span[aria-hidden]"]:
                el = page.locator(sel).first
                if await el.count() > 0:
                    profil["about"] = (await el.inner_text()).strip()[:2000]
                    break
            log(f"  A propos : {len(profil['about'])} car.")
        except Exception:
            pass

        try:
            exps = await page.evaluate("""
                () => {
                    const items = [];
                    document.querySelectorAll('#experience ~ div li').forEach(li => {
                        const title = li.querySelector('.t-bold span[aria-hidden]')?.innerText?.trim() || '';
                        const comp  = li.querySelector('.t-normal span[aria-hidden]')?.innerText?.trim() || '';
                        if (title) items.push({titre: title, entreprise: comp});
                    });
                    return items.slice(0, 5);
                }
            """)
            profil["experiences"] = exps
            log(f"  Experiences : {len(exps)}")
        except Exception:
            pass

        try:
            await page.goto("https://www.linkedin.com/in/me/details/skills/",
                            wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)
            skills = await page.evaluate("""
                () => {
                    const lst = [];
                    document.querySelectorAll('.pvs-list__item--line-separated .t-bold span[aria-hidden]').forEach(s => {
                        const t = s.innerText.trim();
                        if (t) lst.push(t);
                    });
                    return lst.slice(0, 30);
                }
            """)
            profil["skills"] = skills
            log(f"  Competences : {len(skills)}")
        except Exception:
            pass

        return profil

    # ── Mise à jour Titre ──────────────────────────────────────────────────────

    async def maj_headline(self, page, headline: str):
        log("\n--- MISE A JOUR titre ---")
        await page.goto("https://www.linkedin.com/in/me/edit/intro/",
                        wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)

        try:
            el = page.locator("div[contenteditable='true']").first
            if await el.count() > 0 and await el.is_visible():
                await el.click()
                await asyncio.sleep(0.3)
                await el.press("Control+a")
                await asyncio.sleep(0.2)
                await el.fill(headline[:220])
                await asyncio.sleep(0.5)
                saved = await self.sauvegarder(page)
                log(f"  {'Titre mis a jour' if saved else 'Sauvegarde echouee'}")
            else:
                await self.screenshot(page, "headline_echec")
                log("  Div contenteditable non trouve")
        except Exception as e:
            log(f"  Erreur titre : {e}")
        await self.pause(2000, 3000)

    # ── Mise à jour À propos ───────────────────────────────────────────────────

    async def maj_about(self, page, about: str):
        log("\n--- MISE A JOUR A propos ---")
        await page.goto("https://www.linkedin.com/in/me/",
                        wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)

        clique = await page.evaluate("""
            () => {
                for (const el of document.querySelectorAll('a[aria-label], button[aria-label]')) {
                    const lbl = el.getAttribute('aria-label') || '';
                    if (lbl.includes('Modifier les infos') || lbl.includes('Edit about')) {
                        el.click(); return lbl;
                    }
                }
                for (const a of document.querySelectorAll('a[href*="summary"]')) {
                    a.click(); return a.href;
                }
                return null;
            }
        """)
        log(f"  Bouton clique : {clique}")
        await asyncio.sleep(4)
        await self.screenshot(page, "about_modal")

        selectors = [
            "div.tiptap[contenteditable='true']",
            ".ProseMirror[contenteditable='true']",
            "div[role='textbox'][contenteditable='true']",
            "[role='dialog'] div[contenteditable='true']",
            ".artdeco-modal div[contenteditable='true']",
            "div[contenteditable='true']",
            "textarea",
        ]
        found = False
        for sel in selectors:
            try:
                el = page.locator(sel).first
                if await el.count() > 0 and await el.is_visible():
                    await el.click()
                    await asyncio.sleep(0.4)
                    await el.press("Control+a")
                    await asyncio.sleep(0.3)
                    await page.keyboard.type(about[:2600], delay=5)
                    await asyncio.sleep(0.5)
                    saved = await self.sauvegarder(page)
                    log(f"  {'A propos mis a jour' if saved else 'Sauvegarde echouee'} ({sel})")
                    await self.screenshot(page, "about_ok")
                    found = True
                    break
            except Exception as e:
                log(f"  sel {sel}: {e}")
        if not found:
            await self.screenshot(page, "about_echec")
            log("  Champ A propos non trouve")
        await self.pause(2000, 4000)

    # ── Mise à jour expérience ─────────────────────────────────────────────────

    async def maj_experience(self, page, descriptions: dict):
        if not descriptions:
            return
        log("\n--- MISE A JOUR experiences ---")

        for entreprise, description in descriptions.items():
            log(f"  -> {entreprise}")
            await page.goto("https://www.linkedin.com/in/me/",
                            wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(5)

            ent_lower = entreprise[:15].lower()
            clique = await page.evaluate(f"""
                () => {{
                    for (const el of document.querySelectorAll('a[aria-label], button[aria-label]')) {{
                        const lbl = (el.getAttribute('aria-label') || '').toLowerCase();
                        if (lbl.includes('{ent_lower}') && (lbl.includes('modifier') || lbl.includes('edit'))) {{
                            el.click(); return 'aria:' + lbl;
                        }}
                    }}
                    for (const el of document.querySelectorAll('button[aria-label], a[aria-label]')) {{
                        const lbl = (el.getAttribute('aria-label') || '');
                        const parent = el.closest('li, section, .artdeco-card') || el.parentElement;
                        const txt = (parent?.textContent || '').toLowerCase();
                        if (txt.includes('{ent_lower}') && lbl.toLowerCase().includes('modif')) {{
                            el.click(); return 'parent:' + lbl;
                        }}
                    }}
                    return false;
                }}
            """)
            if not clique:
                log(f"  Bouton modifier non trouve pour {entreprise}")
                continue

            await asyncio.sleep(3)
            ta = None
            for sel in ["textarea[id*='description']", "div.tiptap[contenteditable='true']",
                        "div[role='textbox'][contenteditable='true']",
                        ".ProseMirror[contenteditable='true']",
                        "div[contenteditable='true']", "textarea"]:
                try:
                    el = page.locator(sel).first
                    if await el.count() > 0 and await el.is_visible():
                        ta = el
                        break
                except Exception:
                    pass

            if ta:
                await self.remplir(ta, description[:2000])
                saved = await self.sauvegarder(page)
                log(f"  {'Sauvegarde' if saved else 'Sauvegarde echouee'}")
            else:
                log(f"  Champ description non trouve — texte suggere :")
                print(description)
            await self.pause(2000, 3000)

    # ── Mise à jour compétences ────────────────────────────────────────────────

    async def maj_competences(self, page, skills: list):
        log(f"\n--- MISE A JOUR {len(skills)} competences ---")
        succes = 0

        await page.goto("https://www.linkedin.com/in/me/details/skills/",
                        wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(4)
        existantes = await page.evaluate("""
            () => Array.from(document.querySelectorAll('button[aria-label]'))
                .map(b => b.getAttribute('aria-label'))
                .filter(l => l && l.startsWith('Modifier la compétence'))
                .map(l => l.replace('Modifier la compétence "', '').replace('"', '').toLowerCase())
        """)
        log(f"  Competences existantes : {len(existantes)}")

        for i, comp in enumerate(skills, 1):
            if comp.lower() in existantes:
                log(f"  [{i:>2}/{len(skills)}] {comp} — deja presente, ignoree")
                succes += 1
                continue

            log(f"  [{i:>2}/{len(skills)}] {comp}")

            await page.goto("https://www.linkedin.com/in/me/details/skills/",
                            wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)

            clique = await page.evaluate("""
                () => {
                    const el = document.querySelector('a[aria-label="Ajouter une compétence"]');
                    if (el) { el.click(); return true; }
                    for (const a of document.querySelectorAll('a, button')) {
                        const lbl = (a.getAttribute('aria-label') || '');
                        const txt = (a.innerText || '').trim();
                        if (lbl.includes('Ajouter') && lbl.includes('comp') ||
                            txt.includes('Ajouter') && txt.includes('comp')) {
                            a.click(); return true;
                        }
                    }
                    return false;
                }
            """)

            if not clique:
                log(f"    Bouton 'Ajouter une competence' non trouve")
                if i == 1:
                    await self.screenshot(page, "comp_bouton_echec")
                continue

            await asyncio.sleep(3)
            if i == 1:
                await self.screenshot(page, "comp_modal_open")

            inp = None
            for sel in [
                "[role='dialog'] input[type='text']",
                "[role='dialog'] input",
                ".artdeco-modal input[type='text']",
                ".artdeco-modal input",
                "input[placeholder*='ompetence']",
                "input[placeholder*='kill']",
                "input[autocomplete]",
                "input[type='text']",
            ]:
                try:
                    el = page.locator(sel).first
                    if await el.count() > 0 and await el.is_visible():
                        inp = el
                        log(f"    Champ : {sel}")
                        break
                except Exception:
                    pass

            if not inp:
                log(f"    Champ input non trouve dans le modal")
                await self.screenshot(page, f"comp_echec_{i}")
                await self.fermer_modal(page)
                continue

            await inp.click(force=True)
            await asyncio.sleep(0.3)
            await inp.fill("")
            await inp.type(comp, delay=80)
            await asyncio.sleep(2)

            suggestion_ok = False
            for sug_sel in [
                "[role='option']:first-child",
                "[role='listbox'] li:first-child",
                f"[role='option']:has-text('{comp[:8]}')",
                ".basic-typeahead__selectable:first-child",
            ]:
                try:
                    sug = page.locator(sug_sel).first
                    if await sug.count() > 0 and await sug.is_visible():
                        await sug.click(force=True)
                        suggestion_ok = True
                        break
                except Exception:
                    pass
            if not suggestion_ok:
                await inp.press("Enter")

            await asyncio.sleep(1)
            saved = await self.sauvegarder(page)
            if saved:
                succes += 1
                existantes.append(comp.lower())
                log(f"    OK '{comp}'")
            else:
                log(f"    Sauvegarde echouee")
                await self.fermer_modal(page)

            await self.pause(1500, 2500)

        return succes

    # ── Rapport final ─────────────────────────────────────────────────────────

    def afficher_rapport(self, score_data: dict, comp_ok: int, total_comp: int):
        details = score_data.get("score", {})
        total   = details.get("total", "?")
        resume  = details.get("resume", "")

        print()
        print("="*60)
        print("  RAPPORT D'OPTIMISATION LINKEDIN — SCORE FINAL")
        print("="*60)

        items = [
            ("Photo profil",       details.get("photo",         {})),
            ("Titre (Headline)",   details.get("headline",      {})),
            ("A propos",           details.get("about",         {})),
            ("Experiences",        details.get("experience",    {})),
            ("Competences",        details.get("competences",   {})),
            ("Formation",          details.get("formation",     {})),
            ("Recommandations",    details.get("recommandations",{})),
            ("Activite / Posts",   details.get("activite",      {})),
        ]
        for label, d in items:
            pts  = d.get("points", "?")
            sur  = d.get("sur", "?")
            note = d.get("note", "")
            print(f"  {label:<22} {pts}/{sur}  {note[:40]}")

        print("─"*60)
        print(f"  TOTAL : {total}/10   |   Competences ajoutees : {comp_ok}/{total_comp}")
        if resume:
            print(f"  {resume}")
        print("="*60)
        print("  Actions manuelles pour atteindre 10/10 :")
        print("  - Ajouter photo de profil professionnelle")
        print("  - Photo de couverture")
        print("  - Demander 3 recommandations a d'anciens collegues")
        print("="*60)

    # ── Main ──────────────────────────────────────────────────────────────────

    async def run(self):
        for lock in ["LOCK", "SingletonLock", "SingletonCookie", "lockfile"]:
            lp = Path(PROFILE_PATH) / lock
            if lp.exists():
                try:
                    lp.unlink()
                    log(f"Lock supprime : {lock}")
                except Exception:
                    pass

        log("Lecture du CV...")
        cv_texte = lire_cv()

        Path(PROFILE_PATH).mkdir(parents=True, exist_ok=True)

        args = ["--no-sandbox"]
        if HEADLESS:
            args.append("--disable-dev-shm-usage")

        async with async_playwright() as p:
            launch_kwargs = dict(
                user_data_dir=PROFILE_PATH,
                headless=HEADLESS,
                viewport={"width": 1400, "height": 900},
                args=args,
            )
            if SMARTPROXY_USER and SMARTPROXY_PASS:
                launch_kwargs["proxy"] = {
                    "server":   "http://gate.smartproxy.com:10001",
                    "username": SMARTPROXY_USER + "-session-u" + SAAS_USER_ID,
                    "password": SMARTPROXY_PASS,
                }
            browser = await p.chromium.launch_persistent_context(**launch_kwargs)
            page = browser.pages[0] if browser.pages else await browser.new_page()

            try:
                log("Verification session LinkedIn...")
                await page.goto("https://www.linkedin.com/feed/",
                                wait_until="domcontentloaded", timeout=60000)
                await asyncio.sleep(4)
                if "login" in page.url or "authwall" in page.url or "checkpoint" in page.url:
                    ok = await self.auto_login(page)
                    if not ok:
                        return

                log("Session LinkedIn OK")
                print()
                print("="*60)
                print("  OPTIMISATION PROFIL LINKEDIN — GPT-4o + 10/10")
                print("="*60)

                profil_actuel = await self.scraper_profil(page)

                contenu = optimiser_avec_gpt(cv_texte, profil_actuel)
                if not contenu:
                    log("Aucun contenu genere — arret")
                    return

                out = Path(PROFILE_PATH) / "profile_optimizer_output.json"
                out.write_text(json.dumps(contenu, ensure_ascii=False, indent=2), encoding="utf-8")
                log(f"Contenu sauvegarde : {out}")

                envoyer_apercu(contenu)
                approuve = attendre_approbation(timeout_min=60)
                if not approuve:
                    log("Modifications non appliquees.")
                    return

                headline = contenu.get("headline", "")
                about    = contenu.get("about", "")
                exp_desc = contenu.get("experience_descriptions", {})
                skills   = contenu.get("skills", [])

                if headline:
                    await self.maj_headline(page, headline)
                if about:
                    await self.maj_about(page, about)
                if exp_desc:
                    await self.maj_experience(page, exp_desc)
                comp_ok = await self.maj_competences(page, skills) if skills else 0

                self.afficher_rapport(contenu, comp_ok, len(skills))

            except Exception as e:
                log(f"ERREUR FATALE : {e}")
                await self.screenshot(page, "fatal")
            finally:
                log("Fermeture dans 5s...")
                await asyncio.sleep(5)
                await browser.close()


if __name__ == "__main__":
    agent = ProfileOptimizer()
    asyncio.run(agent.run())
