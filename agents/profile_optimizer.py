"""
LinkedIn Profile Optimizer — GPT-4o powered
Reads CV → scrapes current profile → generates optimized content → applies changes → scores 10/10
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
PROFILE_PATH     = os.getenv("PROFILE_PATH", fos.getenv("PROFILE_PATH", "chrome_profile"))
OPENAI_KEY       = os.getenv("OPENAI_API_KEY", "")
CV_PATH          = os.getenv("CV_PATH", os.getenv("CV_PATH", "cv.pdf"))
GMAIL_ADDRESS    = os.getenv("GMAIL_ADDRESS", os.getenv("USER_EMAIL", ""))
GMAIL_PASSWORD   = os.getenv("GMAIL_APP_PASSWORD", "")
USER_NAME        = os.getenv("USER_NAME", "")
USER_PROFESSION  = os.getenv("USER_PROFESSION", "")

# Fichier pending isolé par utilisateur
_data_dir        = Path(f"C:/ai_linkedin_bot/user_data/{USER_ID}")
_data_dir.mkdir(parents=True, exist_ok=True)
PENDING_PROFILE  = _data_dir / "pending_profile.json"
DEBUG_DIR        = Path("debug_profile")

client = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None

# ── Logger ────────────────────────────────────────────────────────────────────

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

# ── CV Reader ─────────────────────────────────────────────────────────────────

def lire_cv() -> str:
    path = Path(CV_PATH)
    if not path.exists():
        log(f"⚠️  CV non trouvé : {CV_PATH}")
        return ""
    if PdfReader is None:
        log("⚠️  pypdf non installé — pip install pypdf")
        return ""
    try:
        reader = PdfReader(str(path))
        texte = "\n".join(p.extract_text() or "" for p in reader.pages)
        log(f"✅ CV lu : {len(texte)} caractères, {len(reader.pages)} pages")
        return texte[:8000]
    except Exception as e:
        log(f"⚠️  Erreur lecture CV : {e}")
        return ""

# ── GPT-4o Optimizer ──────────────────────────────────────────────────────────

def optimiser_avec_gpt(cv_texte: str, profil_actuel: dict) -> dict:
    if not client:
        log("❌ Clé OpenAI manquante — impossible d'optimiser")
        return {}

    log("🤖 Envoi à GPT-4o pour optimisation...")

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
    "resume": "Profil optimisé pour le marché canadien génie civil Ottawa"
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
        # Nettoyer si GPT met du markdown
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw)
        log("✅ Contenu GPT-4o généré")
        return data
    except Exception as e:
        log(f"❌ Erreur GPT-4o : {e}")
        return {}

# ── Approbation avant modification ───────────────────────────────────────────

def envoyer_apercu(contenu: dict):
    """Écrit le fichier pending + envoie email avec aperçu complet."""
    PENDING_PROFILE.write_text(
        json.dumps({"status": "pending", "contenu": contenu}, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    log("📋 Fichier pending_profile.json créé")

    headline = contenu.get("headline", "")
    about    = contenu.get("about", "")[:600]
    skills   = contenu.get("skills", [])
    exp      = contenu.get("experience_descriptions", {})

    corps = f"""Bonjour Patrice,

Voici les modifications proposées pour ton profil LinkedIn.

═══════════════════════════════════════
TITRE (Headline)
═══════════════════════════════════════
{headline}

═══════════════════════════════════════
À PROPOS (extrait 600 car.)
═══════════════════════════════════════
{about}...

═══════════════════════════════════════
EXPÉRIENCES
═══════════════════════════════════════
"""
    for ent, desc in exp.items():
        corps += f"\n{ent} :\n{desc[:400]}\n"

    corps += f"""
═══════════════════════════════════════
COMPÉTENCES ({len(skills)})
═══════════════════════════════════════
{', '.join(skills)}

═══════════════════════════════════════
POUR APPROUVER : réponds OK à cet email
POUR REJETER   : réponds NON
═══════════════════════════════════════

Ou approuve directement sur le dashboard.
"""

    if not GMAIL_ADDRESS or not GMAIL_PASSWORD:
        log("⚠️  Gmail non configuré — aperçu affiché en console uniquement")
        print(corps)
        return

    try:
        msg = MIMEMultipart()
        msg["From"]    = GMAIL_ADDRESS
        msg["To"]      = GMAIL_ADDRESS
        msg["Subject"] = "🔵 [LinkedIn Optimizer] Approuver les modifications du profil ?"
        msg.attach(MIMEText(corps, "plain", "utf-8"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as srv:
            srv.login(GMAIL_ADDRESS, GMAIL_PASSWORD)
            srv.sendmail(GMAIL_ADDRESS, GMAIL_ADDRESS, msg.as_bytes())
        log(f"📧 Aperçu envoyé à {GMAIL_ADDRESS}")
    except Exception as e:
        log(f"⚠️  Email échoué : {e} — aperçu affiché ci-dessous")
        print(corps)


def attendre_approbation(timeout_min: int = 60) -> bool:
    """Attend que pending_profile.json passe à 'approved' ou 'rejected'."""
    import time
    log(f"⏳ En attente de ton approbation (max {timeout_min} min)...")
    log("   -> Approuve sur le dashboard web OU mets status='approved' dans pending_profile.json")
    deadline = time.time() + timeout_min * 60
    while time.time() < deadline:
        try:
            data = json.loads(PENDING_PROFILE.read_text(encoding="utf-8"))
            status = data.get("status", "pending")
            if status == "approved":
                log("✅ Approbation recue — lancement des modifications")
                return True
            if status == "rejected":
                log("❌ Modifications rejetees")
                return False
        except Exception:
            pass
        time.sleep(30)
        log("   ⏳ Toujours en attente...")
    log("⏰ Timeout — modifications annulees")
    return False


# ── Playwright Helpers ────────────────────────────────────────────────────────

class ProfileOptimizer:

    async def pause(self, a=800, b=2000):
        await asyncio.sleep(random.randint(a, b) / 1000)

    async def screenshot(self, page, nom):
        DEBUG_DIR.mkdir(exist_ok=True)
        try:
            path = DEBUG_DIR / f"{datetime.now().strftime('%H%M%S')}_{nom}.png"
            await page.screenshot(path=str(path), full_page=False)
            log(f"  📸 {path.name}")
        except Exception:
            pass

    async def cliquer(self, el):
        try:
            await el.scroll_into_view_if_needed()
            await self.pause(200, 600)
            await el.click()
            await self.pause(300, 800)
        except Exception as e:
            log(f"  ⚠️  clic : {e}")

    async def remplir(self, el, texte: str):
        try:
            await el.click()
            await asyncio.sleep(0.4)
            await el.press("Control+a")
            await asyncio.sleep(0.2)
            await el.fill(texte)
            await asyncio.sleep(0.5)
        except Exception as e:
            log(f"  ⚠️  fill : {e}")

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

    # ── Scraping profil actuel ─────────────────────────────────────────────────

    async def scraper_profil(self, page) -> dict:
        log("\n━━━ LECTURE du profil actuel ━━━")
        await page.goto("https://www.linkedin.com/in/me/",
                        wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)

        profil = {"headline": "", "about": "", "experiences": [], "skills": []}

        # Titre
        try:
            el = page.locator("h2.text-body-medium").first
            if await el.count() > 0:
                profil["headline"] = (await el.inner_text()).strip()
                log(f"  Titre : {profil['headline'][:80]}")
        except Exception:
            pass

        # À propos
        try:
            for sel in ["div[data-generated-suggestion-target='urn:li:fs_summary']",
                        "#about ~ div .full-width",
                        "section:has(#about) .pv-shared-text-with-see-more span[aria-hidden]"]:
                el = page.locator(sel).first
                if await el.count() > 0:
                    profil["about"] = (await el.inner_text()).strip()[:2000]
                    break
            log(f"  À propos : {len(profil['about'])} car.")
        except Exception:
            pass

        # Expériences (titres + entreprises)
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
            log(f"  Expériences : {len(exps)}")
        except Exception:
            pass

        # Compétences
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
            log(f"  Compétences : {len(skills)}")
        except Exception:
            pass

        return profil

    # ── Mise à jour Titre ──────────────────────────────────────────────────────

    async def maj_headline(self, page, headline: str):
        log("\n━━━ MISE À JOUR titre ━━━")
        await page.goto("https://www.linkedin.com/in/me/edit/intro/",
                        wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)

        # Le titre LinkedIn est un <div contenteditable="true"> — pas un <input>
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
                log(f"  {'✅ Titre mis à jour' if saved else '⚠️ Sauvegarde échouée'}")
            else:
                await self.screenshot(page, "headline_echec")
                log("  ❌ Div contenteditable non trouvé")
        except Exception as e:
            log(f"  ❌ Erreur titre : {e}")
        await self.pause(2000, 3000)

    # ── Mise à jour À propos ───────────────────────────────────────────────────

    async def maj_about(self, page, about: str):
        log("\n━━━ MISE À JOUR À propos ━━━")
        # Aller sur la page profil et cliquer "Modifier les infos"
        await page.goto("https://www.linkedin.com/in/me/",
                        wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)

        # Cliquer le bouton "Modifier les infos" (ouvre un modal)
        clique = await page.evaluate("""
            () => {
                for (const el of document.querySelectorAll('a[aria-label], button[aria-label]')) {
                    const lbl = el.getAttribute('aria-label') || '';
                    if (lbl.includes('Modifier les infos') || lbl.includes('Edit about')) {
                        el.click(); return lbl;
                    }
                }
                // Fallback: chercher par href
                for (const a of document.querySelectorAll('a[href*="summary"]')) {
                    a.click(); return a.href;
                }
                return null;
            }
        """)
        log(f"  Bouton cliqué : {clique}")
        await asyncio.sleep(4)
        await self.screenshot(page, "about_modal")

        # L'éditeur TipTap / ProseMirror s'ouvre dans un dialog
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
                    # Tout sélectionner et remplacer
                    await el.press("Control+a")
                    await asyncio.sleep(0.3)
                    await page.keyboard.type(about[:2600], delay=5)
                    await asyncio.sleep(0.5)
                    saved = await self.sauvegarder(page)
                    log(f"  {'✅ À propos mis à jour' if saved else '⚠️ Sauvegarde échouée'} ({sel})")
                    await self.screenshot(page, "about_ok")
                    found = True
                    break
            except Exception as e:
                log(f"  ⚠️ sel {sel}: {e}")
        if not found:
            await self.screenshot(page, "about_echec")
            log("  ❌ Champ À propos non trouvé")
        await self.pause(2000, 4000)

    # ── Mise à jour expérience ─────────────────────────────────────────────────

    async def maj_experience(self, page, descriptions: dict):
        if not descriptions:
            return
        log("\n━━━ MISE À JOUR expériences ━━━")

        for entreprise, description in descriptions.items():
            log(f"  → {entreprise}")
            await page.goto("https://www.linkedin.com/in/me/",
                            wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(5)

            clique = await page.evaluate(f"""
                () => {{
                    // Chercher via aria-label contenant le nom de l'entreprise
                    for (const el of document.querySelectorAll('a[aria-label], button[aria-label]')) {{
                        const lbl = (el.getAttribute('aria-label') || '').toLowerCase();
                        if (lbl.includes('{entreprise[:15].lower()}') && (lbl.includes('modifier') || lbl.includes('edit'))) {{
                            el.click(); return 'aria:' + lbl;
                        }}
                    }}
                    // Chercher via texte parent
                    for (const el of document.querySelectorAll('button[aria-label], a[aria-label]')) {{
                        const lbl = (el.getAttribute('aria-label') || '');
                        const parent = el.closest('li, section, .artdeco-card') || el.parentElement;
                        const txt = (parent?.textContent || '').toLowerCase();
                        if (txt.includes('{entreprise[:15].lower()}') && lbl.toLowerCase().includes('modif')) {{
                            el.click(); return 'parent:' + lbl;
                        }}
                    }}
                    // Chercher via href experience
                    for (const a of document.querySelectorAll('a[href*=\"experience\"][href*=\"edit\"]')) {{
                        const parent = a.closest('li, section') || a.parentElement;
                        const txt = (parent?.textContent || '').toLowerCase();
                        if (txt.includes('{entreprise[:15].lower()}')) {{
                            a.click(); return 'href:' + a.href;
                        }}
                    }}
                    return false;
                }}
            """)
            if not clique:
                log(f"  ⚠️  Bouton modifier non trouvé pour {entreprise}")
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
                log(f"  {'✅ Sauvegardé' if saved else '⚠️ Sauvegarde échouée'}")
            else:
                log(f"  ❌ Champ description non trouvé — texte suggéré :")
                print(description)
            await self.pause(2000, 3000)

    # ── Mise à jour compétences ────────────────────────────────────────────────

    async def maj_competences(self, page, skills: list):
        log(f"\n━━━ MISE À JOUR {len(skills)} compétences ━━━")
        succes = 0

        # Récupérer compétences déjà présentes pour éviter les doublons
        await page.goto("https://www.linkedin.com/in/me/details/skills/",
                        wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(4)
        existantes = await page.evaluate("""
            () => Array.from(document.querySelectorAll('button[aria-label]'))
                .map(b => b.getAttribute('aria-label'))
                .filter(l => l && l.startsWith('Modifier la compétence'))
                .map(l => l.replace('Modifier la compétence "', '').replace('"', '').toLowerCase())
        """)
        log(f"  Compétences existantes : {len(existantes)}")

        for i, comp in enumerate(skills, 1):
            # Ignorer si déjà présente
            if comp.lower() in existantes:
                log(f"  [{i:>2}/{len(skills)}] {comp} — déjà présente, ignorée")
                succes += 1
                continue

            log(f"  [{i:>2}/{len(skills)}] {comp}")

            # Naviguer vers la page détails compétences
            await page.goto("https://www.linkedin.com/in/me/details/skills/",
                            wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)

            # Cliquer le lien "Ajouter une compétence" (c'est un <a>, pas un <button>)
            clique = await page.evaluate("""
                () => {
                    const el = document.querySelector('a[aria-label="Ajouter une compétence"]');
                    if (el) { el.click(); return true; }
                    // fallback texte
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
                log(f"    ❌ Bouton 'Ajouter une compétence' non trouvé")
                if i == 1:
                    await self.screenshot(page, "comp_bouton_echec")
                continue

            await asyncio.sleep(3)
            if i == 1:
                await self.screenshot(page, "comp_modal_open")

            # Chercher le champ input dans le modal
            inp = None
            for sel in [
                "[role='dialog'] input[type='text']",
                "[role='dialog'] input",
                ".artdeco-modal input[type='text']",
                ".artdeco-modal input",
                "input[placeholder*='ompétence']",
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
                log(f"    ❌ Champ input non trouvé dans le modal")
                await self.screenshot(page, f"comp_echec_{i}")
                await self.fermer_modal(page)
                continue

            await inp.click(force=True)
            await asyncio.sleep(0.3)
            await inp.fill("")
            await inp.type(comp, delay=80)
            await asyncio.sleep(2)

            # Sélectionner la première suggestion
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
                log(f"    ✅ '{comp}'")
            else:
                log(f"    ⚠️  Sauvegarde échouée")
                await self.fermer_modal(page)

            await self.pause(1500, 2500)

        return succes

    # ── Rapport final ─────────────────────────────────────────────────────────

    def afficher_rapport(self, score_data: dict, comp_ok: int, total_comp: int):
        details = score_data.get("score", {})
        total   = details.get("total", "?")
        resume  = details.get("resume", "")

        print()
        print("╔══════════════════════════════════════════════════════════╗")
        print("║      RAPPORT D'OPTIMISATION LINKEDIN — SCORE FINAL       ║")
        print("╠══════════════════════════════════════════════════════════╣")

        items = [
            ("📸 Photo profil",       details.get("photo",         {})),
            ("📝 Titre (Headline)",    details.get("headline",      {})),
            ("📖 À propos",            details.get("about",         {})),
            ("💼 Expériences",         details.get("experience",    {})),
            ("🎯 Compétences",         details.get("competences",   {})),
            ("🎓 Formation",           details.get("formation",     {})),
            ("⭐ Recommandations",     details.get("recommandations",{})),
            ("📢 Activité / Posts",    details.get("activite",      {})),
        ]
        for label, d in items:
            pts  = d.get("points", "?")
            sur  = d.get("sur", "?")
            note = d.get("note", "")
            print(f"║  {label:<22} {pts}/{sur}  {note[:32]:<32} ║")

        print("╠══════════════════════════════════════════════════════════╣")
        print(f"║  TOTAL                   {total}/10                          ║")
        print(f"║  Compétences ajoutées    {comp_ok}/{total_comp}                            ║")
        print("╠══════════════════════════════════════════════════════════╣")
        if resume:
            for i in range(0, len(resume), 56):
                print(f"║  {resume[i:i+56]:<56} ║")
        print("╠══════════════════════════════════════════════════════════╣")
        print("║  Actions manuelles pour atteindre 10/10 :               ║")
        print("║  • Ajouter photo de profil professionnelle              ║")
        print("║  • Photo de couverture (chantier Ottawa)                ║")
        print("║  • Demander 3 recommandations à d'anciens collègues     ║")
        print("╚══════════════════════════════════════════════════════════╝")

    # ── Main ──────────────────────────────────────────────────────────────────

    async def run(self):
        # Supprimer lock files Chrome
        for lock in ["LOCK", "SingletonLock", "SingletonCookie", "lockfile"]:
            lp = Path(PROFILE_PATH) / lock
            if lp.exists():
                try:
                    lp.unlink()
                    log(f"🗑️  Lock supprimé : {lock}")
                except Exception:
                    pass

        # 1. Lire le CV
        log("📄 Lecture du CV...")
        cv_texte = lire_cv()

        async with async_playwright() as p:
            browser = await p.chromium.launch_persistent_context(
                user_data_dir=PROFILE_PATH,
                channel="chrome",
                headless=False,
                viewport={"width": 1400, "height": 900},
                args=["--start-maximized"],
            )
            page = browser.pages[0] if browser.pages else await browser.new_page()

            try:
                # 2. Vérifier session
                log("🔐 Vérification session LinkedIn...")
                await page.goto("https://www.linkedin.com/feed/",
                                wait_until="domcontentloaded", timeout=60000)
                await asyncio.sleep(4)
                if "login" in page.url or "authwall" in page.url:
                    log("❌ Session expirée — lancez login_once.py")
                    return

                log("✅ Session LinkedIn OK")
                print()
                print("╔══════════════════════════════════════════════════════════╗")
                print("║   🤖 OPTIMISATION PROFIL LINKEDIN — GPT-4o + 10/10      ║")
                print("╚══════════════════════════════════════════════════════════╝")

                # 3. Scraper profil actuel
                profil_actuel = await self.scraper_profil(page)

                # 4. GPT-4o génère le contenu optimisé
                contenu = optimiser_avec_gpt(cv_texte, profil_actuel)
                if not contenu:
                    log("❌ Aucun contenu généré — arrêt")
                    return

                # Sauvegarder le contenu généré
                out = Path("C:/ai_linkedin_bot/logs/profile_optimizer_output.json")
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(json.dumps(contenu, ensure_ascii=False, indent=2), encoding="utf-8")
                log(f"💾 Contenu sauvegardé : {out}")

                # 4b. Envoyer aperçu et attendre approbation
                envoyer_apercu(contenu)
                approuve = attendre_approbation(timeout_min=60)
                if not approuve:
                    log("🛑 Modifications non appliquées.")
                    return

                # 5. Appliquer les changements
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

                # 6. Rapport final
                self.afficher_rapport(contenu, comp_ok, len(skills))

            except Exception as e:
                log(f"❌ ERREUR FATALE : {e}")
                await self.screenshot(page, "fatal")
            finally:
                log("🔚 Fermeture dans 5s...")
                await asyncio.sleep(5)
                await browser.close()


if __name__ == "__main__":
    agent = ProfileOptimizer()
    asyncio.run(agent.run())
