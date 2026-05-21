import sys
sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
from dotenv import load_dotenv
load_dotenv()

import json
from openai import OpenAI
from playwright.async_api import async_playwright
import os, asyncio, random, requests, base64, re, imaplib, smtplib, time
import email as _email
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
from pathlib import Path

# ============================================================
# CONFIG
# ============================================================

client       = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
PROFILE_PATH = os.getenv("PROFILE_PATH", "chrome_profile")
HEADLESS     = os.getenv("DISPLAY", "") == ""

PHOTOS_DIR       = os.getenv("PHOTOS_DIR", "photos")
PHOTOS_UTILISEES = os.path.join(os.getenv("PHOTOS_DIR", "photos"), "photos_utilisees.txt")

GMAIL_ADDRESS     = os.getenv("GMAIL_ADDRESS")
GMAIL_PASSWORD    = os.getenv("GMAIL_APP_PASSWORD")
LINKEDIN_EMAIL    = os.getenv("LINKEDIN_EMAIL", "")
LINKEDIN_PASSWORD = os.getenv("LINKEDIN_PASSWORD", "")

TAG_NOM      = "Fredy Beukam"
TAG_LINKEDIN = "@Fredy Beukam"

# ============================================================
# THÈMES — génie civil et gestion de projet précis et humains
# ============================================================

THEMES = [
    (
        "la planification d'un chantier de construction : comment structurer les phases d'exécution, "
        "coordonner les sous-traitants et respecter l'échéancier malgré les imprévus du terrain",
        "construction site planning blueprint workers coordination Ottawa Canada"
    ),
    (
        "la gestion des risques en génie civil : identifier les aléas géotechniques, météorologiques "
        "et logistiques avant qu'ils ne deviennent des crises sur chantier",
        "civil engineering site risk assessment soil testing geotechnical Canada"
    ),
    (
        "l'importance du rapport de chantier quotidien : pourquoi documenter l'avancement, "
        "les ressources utilisées et les écarts par rapport au planning est indispensable",
        "construction site daily report supervisor workers documentation"
    ),
    (
        "la gestion budgétaire d'un projet de construction : contrôle des coûts, "
        "gestion des avenants et optimisation des ressources pour rester dans l'enveloppe",
        "construction project budget cost control financial planning documents"
    ),
    (
        "la coordination entre ingénieurs, techniciens, sous-traitants et client : "
        "comment les réunions de chantier hebdomadaires sauvent un projet de dérailler",
        "construction team meeting coordination engineers site Ottawa"
    ),
    (
        "AutoCAD et Civil 3D dans les projets d'infrastructure : comment ces outils transforment "
        "les plans 2D en modèles terrain exploitables pour les équipes sur le terrain",
        "AutoCAD Civil 3D infrastructure engineering drawing Canada"
    ),
    (
        "la gestion de l'eau et du drainage sur un chantier : une étape critique souvent "
        "sous-estimée qui peut bloquer tout l'avancement des travaux",
        "construction site drainage water management civil engineering"
    ),
    (
        "la certification PMP appliquée au terrain : comment les principes du PMI se traduisent "
        "concrètement dans la gestion d'un chantier de génie civil au Canada",
        "PMP project management professional construction Canada certification"
    ),
    (
        "la carte ASP Construction et la culture de sécurité sur les chantiers canadiens : "
        "pourquoi la prévention des accidents est aussi une responsabilité du gestionnaire de projet",
        "construction site safety workers helmets vests ASP Canada"
    ),
    (
        "le BIM et Revit dans la construction moderne : comment la maquette numérique réduit "
        "les conflits entre corps de métier et améliore la coordination avant même le premier coup de pelle",
        "BIM Revit 3D building model coordination architecture engineering"
    ),
    (
        "la gestion des délais en construction : techniques d'analyse du chemin critique (CPM) "
        "et comment MS Project aide à anticiper les retards avant qu'ils deviennent irréversibles",
        "MS Project construction schedule critical path Gantt chart"
    ),
    (
        "les infrastructures municipales à Ottawa-Gatineau : routes, égouts, aqueduc — "
        "les défis techniques et humains des projets publics d'envergure",
        "Ottawa municipal infrastructure roads utilities civil engineering workers"
    ),
]

# ============================================================
# LOGGER
# ============================================================

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

# ============================================================
# CHOISIR PHOTO
# ============================================================

def _charger_utilisees():
    p = Path(PHOTOS_UTILISEES)
    if not p.exists():
        return set()
    return set(l.strip() for l in p.read_text(encoding="utf-8").splitlines() if l.strip())

def _marquer_utilisee(nom):
    with open(PHOTOS_UTILISEES, "a", encoding="utf-8") as f:
        f.write(nom + "\n")

def choisir_photo(theme_fr, theme_en):
    photos_dir = Path(PHOTOS_DIR)
    photos_dir.mkdir(parents=True, exist_ok=True)

    extensions = [".jpg", ".jpeg", ".png", ".webp"]
    toutes = [
        f for f in photos_dir.iterdir()
        if f.suffix.lower() in extensions
        and not f.name.startswith("ai_generated")
    ]

    utilisees   = _charger_utilisees()
    disponibles = [f for f in toutes if f.name not in utilisees]

    if not disponibles and toutes:
        log("Toutes les photos deja publiees — reinitialisation du cycle")
        Path(PHOTOS_UTILISEES).write_text("", encoding="utf-8")
        disponibles = toutes

    if disponibles:
        mots = set(w for w in re.sub(r'[^a-z ]', '', theme_en.lower()).split() if len(w) > 3)
        scored = [(sum(1 for m in mots if m in f.stem.lower()), f) for f in disponibles]
        scored.sort(key=lambda x: x[0], reverse=True)
        meilleur_score, meilleure = scored[0]

        if meilleur_score > 0:
            photo = meilleure
            log(f"Photo adaptee au theme ({meilleur_score} mots) : {photo.name}")
        else:
            photo = random.choice(disponibles)
            log(f"Photo chantier selectionnee : {photo.name}")

        _marquer_utilisee(photo.name)
        return str(photo)

    log("Generation image IA adaptee au theme...")
    try:
        prompt = (
            f"Ultra-realistic professional documentary photograph: {theme_en}. "
            f"Main subject: a confident Black African-Canadian professional man, "
            f"white hard hat, high-visibility orange vest, leading work on a real "
            f"construction or civil engineering site in Ottawa, Canada. "
            f"Diverse coworkers visible in background, natural overcast daylight, "
            f"authentic jobsite: muddy ground, scaffolding or heavy equipment. "
            f"Canon EOS R5, 35mm lens, shallow depth of field, photojournalism style. "
            f"No text, no watermark, no logos. Warm natural tones. Unposed and raw."
        )
        response = client.images.generate(
            model="gpt-image-1",
            prompt=prompt,
            size="1024x1024",
            quality="high",
            n=1,
        )
        image_b64 = response.data[0].b64_json
        img_data  = base64.b64decode(image_b64)
        date_str  = datetime.now().strftime("%Y%m%d_%H%M%S")
        ai_path   = photos_dir / f"ai_{date_str}.png"
        with open(ai_path, "wb") as f:
            f.write(img_data)
        _marquer_utilisee(ai_path.name)
        log(f"Image IA generee : {ai_path.name}")
        return str(ai_path)
    except Exception as e:
        log(f"Generation image erreur : {e}")
        return None

# ============================================================
# GÉNÉRER POST
# ============================================================

def generer_post(theme_fr):
    user_name    = os.getenv("USER_NAME", "Patrice Arnold Sob Feukam")
    user_prof    = os.getenv("USER_PROFESSION", "technicien en génie civil et gestionnaire de projets de construction")
    prompt = f"""
Tu es {user_name}, {user_prof}.
Tu cherches activement un emploi en génie civil et gestion de projets à Ottawa-Gatineau.

Rédige un post LinkedIn professionnel sur ce thème précis :
{theme_fr}

RÈGLES STRICTES :
- Écris en français, ton humain et authentique, jamais corporatif
- Partage une vraie réflexion de terrain, une leçon apprise, un constat concret
- Utilise des détails techniques précis (chiffres, méthodes, outils réels)
- CHAQUE PHRASE ou idée doit être sur sa PROPRE LIGNE (retour à la ligne après chaque phrase)
- Ajoute UNE LIGNE VIDE entre chaque idée ou paragraphe — le texte doit être aéré et facile à lire sur mobile
- Maximum 5 idées distinctes, chacune sur sa propre ligne
- 1 emoji pertinent par idée clé (pas plus de 4 emojis au total), placé en début ou fin de ligne
- Ligne vide, puis 4-5 hashtags sur une seule ligne parmi : #Construction #GestionDeProjet #GénieCivil #Ottawa #Infrastructure #Chantier #BIM #Sécurité #PMP #Planification #GatineauOttawa
- Ligne vide, puis exactement : @Fredy Beukam
- NE JAMAIS dire que c'est généré par IA
- NE PAS utiliser de formules creuses comme "la clé du succès" ou "un outil indispensable"
- Retourne UNIQUEMENT le texte du post, rien d'autre
"""
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=400
    )
    return resp.choices[0].message.content.strip()

# ============================================================
# APPROBATION EMAIL AVANT PUBLICATION
# ============================================================

PENDING_POST = Path(os.path.join(PROFILE_PATH, "pending_post.json"))

def envoyer_approbation(post_text, image_path, theme_fr):
    data = {
        "status":       "pending",
        "text":         post_text,
        "image":        str(image_path) if image_path else "",
        "theme":        theme_fr,
        "generated_at": datetime.now().isoformat(),
    }
    PENDING_POST.parent.mkdir(parents=True, exist_ok=True)
    PENDING_POST.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    log("Post ecrit dans pending_post.json")

    try:
        msg = MIMEMultipart()
        msg["From"]    = GMAIL_ADDRESS
        msg["To"]      = GMAIL_ADDRESS
        msg["Subject"] = "[JOBAI] Post LinkedIn pret — approbation requise"
        corps = (
            "Bonjour,\n\n"
            "Un post LinkedIn est pret. Approuvez-le depuis le dashboard :\n"
            "-> Ouvrez l'app JobAI -> onglet LinkedIn Post\n\n"
            + "─" * 40 + "\n\n" + post_text + "\n\n" + "─" * 40 + "\n\n"
            "Votre bot LinkedIn"
        )
        msg.attach(MIMEText(corps, "plain", "utf-8"))
        if image_path and Path(image_path).exists():
            with open(image_path, "rb") as f:
                part = MIMEBase("image", "png")
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition",
                            f'attachment; filename="{Path(image_path).name}"')
            msg.attach(part)
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as srv:
            srv.login(GMAIL_ADDRESS, GMAIL_PASSWORD)
            srv.sendmail(GMAIL_ADDRESS, GMAIL_ADDRESS, msg.as_string())
        log(f"Notification email envoyee a {GMAIL_ADDRESS}")
    except Exception as e:
        log(f"Email notif : {str(e)[:60]}")

def attendre_ok(timeout_min=120):
    deadline = time.time() + timeout_min * 60
    log(f"En attente de votre approbation sur le dashboard (timeout {timeout_min}min)...")
    while time.time() < deadline:
        try:
            if PENDING_POST.exists():
                data = json.loads(PENDING_POST.read_text(encoding="utf-8"))
                if data.get("status") == "approved":
                    log("Approbation recue via dashboard — publication en cours...")
                    return True
                if data.get("status") == "rejected":
                    log("Post rejete via dashboard")
                    return False
        except Exception:
            pass
        time.sleep(30)
    log("Aucune reponse apres 2h — post annule")
    return False

# ============================================================
# AGENT LINKEDIN
# ============================================================

class LinkedInAgent:

    async def human_delay(self, context="normal"):
        ranges = {"fast": (500, 1200), "normal": (800, 2000), "slow": (1500, 4000)}
        a, b = ranges.get(context, (800, 2000))
        await asyncio.sleep(random.randint(a, b) / 1000)

    async def human_type(self, element, text):
        for char in text:
            await element.type(char)
            delay = random.randint(25, 120)
            if char in ".!?\n":
                delay += random.randint(150, 400)
            await asyncio.sleep(delay / 1000)

    async def debug(self, page, name):
        Path("debug").mkdir(parents=True, exist_ok=True)
        path = f"debug/{datetime.now().strftime('%Y%m%d_%H%M%S')}_{name}.png"
        try:
            await page.screenshot(path=path, full_page=True)
            log(f"Screenshot : {path}")
        except Exception:
            pass

    async def safe_click(self, el):
        try:
            await el.scroll_into_view_if_needed()
            await asyncio.sleep(0.5)
            await el.click(force=True)
        except Exception as e:
            log(f"safe_click : {e}")

    async def launch(self, p):
        log("Lancement navigateur")
        for lock_file in ["LOCK", "SingletonLock", "SingletonCookie", "lockfile"]:
            lp = Path(PROFILE_PATH) / lock_file
            if lp.exists():
                try:
                    lp.unlink()
                    log(f"Verrou supprime : {lock_file}")
                except Exception:
                    pass

        args = ["--start-maximized", "--no-sandbox"]
        if HEADLESS:
            args.append("--disable-dev-shm-usage")

        Path(PROFILE_PATH).mkdir(parents=True, exist_ok=True)
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=PROFILE_PATH,
            headless=HEADLESS,
            viewport={"width": 1400, "height": 900},
            args=args
        )
        page = browser.pages[0] if browser.pages else await browser.new_page()
        return browser, page

    async def auto_login(self, page):
        if not LINKEDIN_EMAIL or not LINKEDIN_PASSWORD:
            log("Session invalide — ajoutez LinkedIn Email/Password dans le Setup")
            return False
        log("Connexion automatique LinkedIn...")
        try:
            await page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded", timeout=30000)
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

    async def check_session(self, page):
        log("Session check")
        await page.goto("https://www.linkedin.com/feed/",
                        wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(6)
        url = page.url
        if "login" in url or "authwall" in url or "checkpoint" in url:
            return await self.auto_login(page)
        log("Session OK")
        return True

    async def wait_for_feed(self, page):
        log("Attente chargement feed LinkedIn...")
        for _ in range(20):
            if "/feed" in page.url:
                break
            await asyncio.sleep(1)

        selectors_feed = [
            ".share-box-feed-entry__trigger",
            "[aria-label='Commencer un post']",
            "[aria-label='Start a post']",
            ".feed-identity-module",
            ".scaffold-layout__main",
            "main",
            "#main-content",
        ]
        for sel in selectors_feed:
            try:
                await page.wait_for_selector(sel, timeout=8000)
                log(f"Feed detecte via : {sel}")
                return True
            except Exception:
                pass

        await asyncio.sleep(5)
        log("Feed charge par timeout — on continue")
        return True

    async def open_post_modal(self, page):
        log("Ouverture popup creation de post...")
        await self.wait_for_feed(page)
        await asyncio.sleep(3)

        selectors = [
            "[aria-label='Commencer un post']",
            "[aria-label='Start a post']",
            ".share-box-feed-entry__trigger",
            "[placeholder='Commencer un post']",
            "[placeholder='Start a post']",
            "button.share-box-feed-entry__trigger",
        ]
        for s in selectors:
            try:
                loc = page.locator(s).first
                if await loc.count() > 0 and await loc.is_visible():
                    await self.safe_click(loc)
                    await asyncio.sleep(3)
                    if await page.locator("div[role='textbox']").count() > 0:
                        log("Popup ouverte")
                        return True
            except Exception:
                pass

        try:
            clicked = await page.evaluate("""
                () => {
                    const kws = ['Commencer un post', 'Start a post', 'Créer un post'];
                    for (const el of document.querySelectorAll('div,span,button,p,input,textarea')) {
                        const t  = (el.textContent || '').trim();
                        const ph = el.getAttribute('placeholder') || '';
                        const al = el.getAttribute('aria-label') || '';
                        for (const kw of kws) {
                            if (t === kw || ph.includes(kw) || al.includes(kw)) {
                                el.click();
                                return kw;
                            }
                        }
                    }
                    return null;
                }
            """)
            if clicked:
                log(f"Bouton trouve via JS : '{clicked}'")
                await asyncio.sleep(3)
                if await page.locator("div[role='textbox']").count() > 0:
                    log("Popup ouverte via JS")
                    return True
        except Exception as e:
            log(f"JS fallback : {e}")

        await self.debug(page, "modal_fail")
        return False

    async def upload_image(self, page, image_path):
        if not image_path or not Path(image_path).exists():
            log("Pas d'image a uploader")
            return False

        log(f"Upload image : {Path(image_path).name}")
        photo_selectors = [
            "button[aria-label*='Photo']",
            "button[aria-label*='photo']",
            "button[aria-label*='média']",
            "button[aria-label*='Média']",
            "button[aria-label*='image']",
            "button[aria-label*='Image']",
            "button[aria-label*='Add a photo']",
        ]
        for sel in photo_selectors:
            try:
                btn = page.locator(sel).first
                if await btn.count() > 0 and await btn.is_visible():
                    await self.safe_click(btn)
                    await asyncio.sleep(2)
                    break
            except Exception:
                pass

        try:
            file_input = page.locator("input[type='file']").first
            await file_input.wait_for(state="attached", timeout=10000)
            await file_input.set_input_files(image_path)
            log("Image uploadee")
            await asyncio.sleep(5)
            return True
        except Exception as e:
            log(f"Upload image erreur : {e}")
            return False

    async def tagger_fredy(self, page, editor):
        try:
            log(f"Tentative de tag {TAG_NOM}...")
            await asyncio.sleep(2)
            suggestion_selectors = [
                "[data-view-name='type-ahead-result']",
                ".type-ahead-result",
                "li[id*='mention']",
                ".mentioning-dropdown li",
                "ul[role='listbox'] li",
                "[role='option']",
            ]
            for sel in suggestion_selectors:
                try:
                    suggestions = page.locator(sel)
                    count = await suggestions.count()
                    for i in range(count):
                        s = suggestions.nth(i)
                        txt = (await s.inner_text()).strip()
                        if "Fredy" in txt or "Beukam" in txt:
                            await s.click()
                            log(f"Tag {TAG_NOM} applique")
                            return True
                except Exception:
                    pass
            log("Tag en texte brut — acceptable")
            return True
        except Exception as e:
            log(f"Tag erreur : {e}")
            return False

    async def create_post(self, page, post_text, image_path):
        log("Chargement feed")
        await page.goto("https://www.linkedin.com/feed/",
                        wait_until="domcontentloaded", timeout=60000)

        opened = await self.open_post_modal(page)
        if not opened:
            await self.debug(page, "modal_not_opened")
            raise Exception("Impossible d'ouvrir le modal de post")

        await self.debug(page, "modal_opened")

        log("Attente editeur...")
        await page.wait_for_selector("div[role='textbox']", timeout=20000)
        editor = page.locator("div[role='textbox']").first
        await editor.click()
        await self.human_delay("fast")

        lines = post_text.split("\n")
        for line in lines:
            if "@Fredy" in line:
                await editor.type("@Fredy")
                await asyncio.sleep(2)
                await self.tagger_fredy(page, editor)
                reste = line.replace("@Fredy Beukam", "").replace("@Fredy", "").strip()
                if reste:
                    await self.human_type(editor, " " + reste)
            else:
                await self.human_type(editor, line)
            await editor.type("\n")
            await asyncio.sleep(0.1)

        log("Texte insere")
        await self.debug(page, "text_typed")

        if image_path:
            await self.upload_image(page, image_path)

        PUBLISH_LABELS = ["publier", "publish", "post"]
        NEXT_LABELS    = ["suivant", "next"]
        EXCLUDE        = ["republier", "repost", "commenter", "annuler",
                          "cancel", "retour", "back", "programmer", "schedule"]

        async def cliquer_bouton_bleu_principal():
            for label in ["Suivant", "Next", "Publier", "Publish", "Post"]:
                for sel in [f"button[aria-label='{label}']",
                            f"button[aria-label*='{label}']"]:
                    try:
                        b = page.locator(sel).first
                        if await b.count() > 0 and await b.is_visible():
                            return b, label
                    except Exception:
                        pass

            buttons = page.locator("button")
            count   = await buttons.count()
            for i in range(count):
                try:
                    b = buttons.nth(i)
                    if not await b.is_visible():
                        continue
                    t = (await b.inner_text()).strip()
                    if any(ex in t.lower() for ex in EXCLUDE):
                        continue
                    if t.lower() in PUBLISH_LABELS:
                        return b, t
                except Exception:
                    pass
            for i in range(count):
                try:
                    b = buttons.nth(i)
                    if not await b.is_visible():
                        continue
                    t = (await b.inner_text()).strip()
                    if any(ex in t.lower() for ex in EXCLUDE):
                        continue
                    if t.lower() in NEXT_LABELS:
                        return b, t
                except Exception:
                    pass

            for sel in ["button.artdeco-button--primary", ".share-actions__primary-action"]:
                try:
                    b = page.locator(sel).last
                    if await b.count() > 0 and await b.is_visible():
                        t = (await b.inner_text()).strip()
                        if not any(ex in t.lower() for ex in EXCLUDE):
                            return b, t
                except Exception:
                    pass

            return None, None

        publie = False
        for etape in range(1, 7):
            await asyncio.sleep(3)
            await self.debug(page, f"etape_{etape}")

            btn, label = await cliquer_bouton_bleu_principal()
            if not btn:
                log(f"Aucun bouton trouve etape {etape} — arret")
                break

            log(f"Clic '{label}' (etape {etape})")
            await self.safe_click(btn)

            if label and label.lower() in PUBLISH_LABELS:
                await asyncio.sleep(6)
                publie = True
                break

        if not publie:
            await self.debug(page, "publish_not_found")
            raise Exception("Bouton Publier introuvable apres toutes les etapes")

        await self.debug(page, "posted")
        log("POST PUBLIE !")

    async def run(self, post_text, image_path):
        async with async_playwright() as p:
            browser, page = await self.launch(p)
            try:
                ok = await self.check_session(page)
                if not ok:
                    return False
                await self.create_post(page, post_text, image_path)
                return True
            except Exception as e:
                log(f"ERREUR : {e}")
                await self.debug(page, "fatal")
                return False
            finally:
                log("Fermeture")
                await asyncio.sleep(3)
                await browser.close()

# ============================================================
# SAUVEGARDER LE POST
# ============================================================

def sauvegarder_post(post_text, image_path, succes):
    posts_dir = Path(PROFILE_PATH) / "posts_publies"
    posts_dir.mkdir(parents=True, exist_ok=True)
    date   = datetime.now().strftime("%Y%m%d_%H%M%S")
    statut = "OK" if succes else "ECHEC"
    path   = posts_dir / f"{date}_{statut}.txt"
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"Date   : {datetime.now().strftime('%d/%m/%Y %H:%M')}\n")
        f.write(f"Statut : {statut}\n")
        f.write(f"Image  : {image_path or 'Aucune'}\n")
        f.write("-" * 44 + "\n\n")
        f.write(post_text)
    log(f"Post sauvegarde : {path}")

# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    log("LinkedIn Agent demarre")
    print()

    theme_fr, theme_en = random.choice(THEMES)
    log(f"Theme : {theme_fr[:70]}...")
    print()

    image_path = choisir_photo(theme_fr, theme_en)

    log("Generation contenu GPT-4o...")
    try:
        post_text = generer_post(theme_fr)
        print()
        print("─" * 55)
        print(post_text)
        print("─" * 55)
        print()
    except Exception as e:
        log(f"Erreur generation : {e}")
        post_text = (
            "Sur un chantier, le planning n'est jamais fige.\n"
            "Ce qui fait la difference, c'est la capacite a recalibrer "
            "rapidement quand un sous-traitant accuse du retard.\n\n"
            "#Construction #GestionDeProjet #GenieCivil #Ottawa #Chantier\n\n"
            "@Fredy Beukam"
        )
        log("Utilisation du texte par defaut")

    try:
        envoyer_approbation(post_text, image_path, theme_fr)
    except Exception as e:
        log(f"Impossible d'envoyer l'approbation : {e}")
        sauvegarder_post(post_text, image_path, False)
        exit()

    approuve = attendre_ok(timeout_min=120)
    if not approuve:
        sauvegarder_post(post_text, image_path, False)
        exit()

    agent  = LinkedInAgent()
    succes = asyncio.run(agent.run(post_text, image_path))

    sauvegarder_post(post_text, image_path, succes)

    print()
    if succes:
        log("LinkedIn Agent termine avec succes !")
    else:
        log("LinkedIn Agent termine avec erreur")
