"""
JobAI — Easy Apply Local Runner
================================
Lance ce script sur le PC de Nicole (pas sur Railway).
Il récupère les offres retenues depuis le serveur JobAI
et postule via Easy Apply LinkedIn avec le vrai Chrome.

Usage :
    python easy_apply_local.py

Prérequis :
    pip install playwright requests
    playwright install chromium
"""
import sys, json, asyncio, random, re, os, requests
from datetime import datetime
from playwright.async_api import async_playwright

# ─── CONFIGURATION ────────────────────────────────────────────────
SAAS_URL      = "https://jobai-pro-production.up.railway.app"
AGENT_SECRET  = "jobai-cli-secret-2026"
USER_ID       = 1          # ID de l'utilisateur Nicole
MAX_OFFRES    = 15         # Nombre max d'offres à traiter par session
HEADLESS      = False      # False = on voit le navigateur (recommandé)
# ──────────────────────────────────────────────────────────────────


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def get_config() -> dict:
    """Récupère la config depuis le serveur Railway."""
    try:
        r = requests.get(f"{SAAS_URL}/api/my-config",
                         headers={"X-User-Token": str(USER_ID)}, timeout=10)
        if r.status_code == 200:
            return r.json()
        log(f"Erreur config : {r.status_code}")
    except Exception as e:
        log(f"Erreur connexion serveur : {e}")
    return {}


def get_offres() -> list:
    """Récupère les offres retenues (score >= 65) depuis la DB Railway."""
    try:
        r = requests.get(f"{SAAS_URL}/api/candidatures",
                         headers={"X-User-Token": str(USER_ID)},
                         params={"statut": "retenu"}, timeout=10)
        if r.status_code == 200:
            data = r.json()
            offres = data.get("rows", [])
            log(f"{len(offres)} offres récupérées depuis le serveur")
            return offres
        log(f"Erreur offres : {r.status_code}")
    except Exception as e:
        log(f"Erreur récupération offres : {e}")
    return []


JS_TYPE_CANDIDATURE = """() => {
    const txt = document.body.innerText || '';
    const btns = Array.from(document.querySelectorAll('button')).map(b => (b.innerText||'').toLowerCase());
    if (btns.some(t => t.includes('easy apply') || t.includes('postuler facilement'))) return 'easy_apply';
    if (btns.some(t => t.includes('apply') || t.includes('postuler'))) return 'lien_externe';
    return 'inconnu';
}"""

JS_POSTULER = """() => {
    const btns = Array.from(document.querySelectorAll('button'));
    const btn = btns.find(b => {
        const t = (b.innerText||'').toLowerCase();
        return t.includes('easy apply') || t.includes('postuler facilement') ||
               t.includes('apply') || t.includes('postuler');
    });
    if (btn) { btn.click(); return btn.innerText.trim(); }
    return null;
}"""


async def easy_apply(page, offre: dict) -> str:
    """Tente Easy Apply sur une offre. Retourne le statut."""
    lien = offre.get("lien", "")
    if not lien:
        return "pas_de_lien"

    try:
        await page.goto(lien, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(random.uniform(2, 4))
        await page.wait_for_selector("button", timeout=5000)
    except Exception as e:
        return f"erreur_goto: {str(e)[:40]}"

    type_c = await page.evaluate(JS_TYPE_CANDIDATURE)
    log(f"  Type : {type_c}")

    if type_c != "easy_apply":
        return type_c

    clique = await page.evaluate(JS_POSTULER)
    if not clique:
        return "bouton_introuvable"

    log(f"  Cliqué : {clique}")
    await asyncio.sleep(4)

    EXCL   = ["republier","repost","annuler","cancel","retour","back","supprimer","dismiss","ignorer"]
    SUBMIT = ["envoyer la candidature","soumettre","submit","envoyer"]
    NEXT   = ["suivant","next","continuer","revoir","review"]
    publie = False

    for etape in range(1, 8):
        await asyncio.sleep(3)
        buttons = page.locator("button")
        cnt = await buttons.count()
        for j in range(cnt):
            try:
                b = buttons.nth(j)
                if not await b.is_visible():
                    continue
                t = (await b.inner_text()).strip().lower()
                if any(ex in t for ex in EXCL):
                    continue
                if any(lb in t for lb in SUBMIT):
                    log(f"  Soumis étape {etape} : '{t}'")
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
                if not await b.is_visible():
                    continue
                t = (await b.inner_text()).strip().lower()
                if any(ex in t for ex in EXCL):
                    continue
                if any(lb in t for lb in NEXT):
                    log(f"  Suivant étape {etape} : '{t}'")
                    await b.scroll_into_view_if_needed()
                    await b.click()
                    await asyncio.sleep(3)
                    suivant_clique = True
                    break
            except Exception:
                pass
        if not suivant_clique:
            break

    return "easy_apply_ok" if publie else "easy_apply_partiel"


async def run():
    print("=" * 55)
    print("  JobAI — Easy Apply Local Runner")
    print("=" * 55)

    # 1. Récupérer la config (cookies LinkedIn)
    cfg = get_config()
    if not cfg:
        log("ERREUR : impossible de récupérer la config depuis Railway")
        return

    cookies_json = cfg.get("linkedin_cookies_json", "")
    if not cookies_json:
        log("ERREUR : aucun cookie LinkedIn dans la config")
        log("→ Va dans Setup et colle tes cookies Cookie-Editor")
        return

    # 2. Récupérer les offres
    offres = get_offres()
    if not offres:
        log("Aucune offre à traiter. Lance d'abord l'Orchestrateur depuis le dashboard.")
        return

    # Filtrer : seulement les offres LinkedIn avec un lien
    li_offres = [o for o in offres if "linkedin.com" in o.get("lien","") and o.get("statut","") in ("retenu","")]
    li_offres = li_offres[:MAX_OFFRES]
    log(f"{len(li_offres)} offres LinkedIn à traiter")

    if not li_offres:
        log("Aucune offre LinkedIn retenue à traiter.")
        return

    # 3. Lancer le navigateur (VRAI Chrome, sans proxy)
    async with async_playwright() as p:
        log("Lancement du navigateur Chrome...")
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=os.path.join(os.path.expanduser("~"), ".jobai_chrome"),
            headless=HEADLESS,
            args=["--disable-blink-features=AutomationControlled"],
            locale="fr-CA",
            viewport={"width": 1280, "height": 800},
        )
        page = browser.pages[0] if browser.pages else await browser.new_page()

        # 4. Injecter les cookies LinkedIn
        try:
            raw = json.loads(cookies_json)
            pw_cookies = []
            for c in raw:
                ss = c.get("sameSite", "None")
                if ss not in ("Strict", "Lax", "None"):
                    ss = "None"
                if c.get("name") and c.get("value"):
                    pw_cookies.append({
                        "name": c["name"], "value": c["value"],
                        "domain": c.get("domain", ".linkedin.com"),
                        "path": c.get("path", "/"),
                        "secure": bool(c.get("secure", True)),
                        "httpOnly": bool(c.get("httpOnly", False)),
                        "sameSite": ss,
                        "expires": int(c.get("expirationDate", 2000000000)),
                    })
            await page.goto("https://www.linkedin.com/", wait_until="domcontentloaded", timeout=30000)
            await browser.add_cookies(pw_cookies)
            log(f"Cookies injectés : {len(pw_cookies)}")
        except Exception as e:
            log(f"Erreur cookies : {e}")

        # 5. Vérifier la session
        await page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)
        if "login" in page.url or "authwall" in page.url:
            log("Session LinkedIn invalide — rafraîchis les cookies dans le Setup")
            await browser.close()
            return
        log("Session LinkedIn active !")

        # 6. Easy Apply sur chaque offre
        stats = {"ok": 0, "partiel": 0, "echec": 0}
        for i, offre in enumerate(li_offres, 1):
            titre   = offre.get("titre", "")[:40]
            company = offre.get("entreprise", "")
            log(f"[{i}/{len(li_offres)}] {company} — {titre}")
            try:
                statut = await easy_apply(page, offre)
                if "ok" in statut:
                    stats["ok"] += 1
                    log(f"  ✅ Easy Apply réussi !")
                elif "partiel" in statut:
                    stats["partiel"] += 1
                    log(f"  ⚠️  Easy Apply partiel (vérifier manuellement)")
                else:
                    stats["echec"] += 1
                    log(f"  ❌ Échec : {statut}")
            except Exception as e:
                stats["echec"] += 1
                log(f"  ❌ Erreur : {str(e)[:60]}")
            await asyncio.sleep(random.uniform(3, 6))

        await browser.close()

    print("=" * 55)
    print(f"  RÉSULTAT : ✅{stats['ok']} réussis  ⚠️{stats['partiel']} partiels  ❌{stats['echec']} échecs")
    print("=" * 55)


if __name__ == "__main__":
    asyncio.run(run())
