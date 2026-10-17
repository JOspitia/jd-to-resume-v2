"""
backend.adapters.linkedin.playwright_auth_adapter
==================================================

Drives a headless Chromium via Playwright to log into LinkedIn with
``LINKEDIN_EMAIL`` + ``LINKEDIN_PASSWORD`` and scrape the rendered
profile DOM. Returns a Markdown blob with name / headline / location /
about / experience / education / skills / certifications / languages.

This is the highest-quality path (full profile data) but:
    * Violates LinkedIn's Terms of Service.
    * Triggers CAPTCHA / 2FA on accounts that don't bypass it.
    * Breaks whenever LinkedIn changes its DOM structure.

So the service falls back to the public scraper when this path fails.
"""

from __future__ import annotations

import os
import time

from playwright.sync_api import sync_playwright


_JS_EXTRACTOR = """
() => {
    const getText = (el) => el ? el.innerText.trim() : '';
    const getAll = (sel) => Array.from(document.querySelectorAll(sel)).map(e => e.innerText.trim()).filter(Boolean);

    const name = getText(document.querySelector('h1'));
    const headline = getText(document.querySelector('.text-body-medium.break-words'));
    const location = getText(document.querySelector('.text-body-small.inline.t-black--light.break-words'));

    const aboutSection = document.querySelector('#about ~ div .visually-hidden, section[data-section="about"] .display-flex.ph5 span');
    const about = aboutSection ? aboutSection.innerText.trim() : '';

    const expContainer = document.querySelector('#experience');
    let experiences = [];
    if (expContainer) {
        const expParent = expContainer.closest('section') || expContainer.parentElement?.parentElement?.parentElement;
        if (expParent) {
            const items = expParent.querySelectorAll('li.artdeco-list__item');
            items.forEach(item => {
                const lines = item.innerText.split('\\n').map(l => l.trim()).filter(Boolean);
                experiences.push(lines.join(' | '));
            });
        }
    }

    const eduContainer = document.querySelector('#education');
    let education = [];
    if (eduContainer) {
        const eduParent = eduContainer.closest('section') || eduContainer.parentElement?.parentElement?.parentElement;
        if (eduParent) {
            const items = eduParent.querySelectorAll('li.artdeco-list__item');
            items.forEach(item => {
                const lines = item.innerText.split('\\n').map(l => l.trim()).filter(Boolean);
                education.push(lines.join(' | '));
            });
        }
    }

    const skillsContainer = document.querySelector('#skills');
    let skills = [];
    if (skillsContainer) {
        const skillsParent = skillsContainer.closest('section') || skillsContainer.parentElement?.parentElement?.parentElement;
        if (skillsParent) {
            const items = skillsParent.querySelectorAll('li .t-bold span, li .mr1 span');
            items.forEach(item => skills.push(item.innerText.trim()));
        }
    }
    if (skills.length === 0) {
        document.querySelectorAll('[data-field="skill_card_skill_topic"]').forEach(el => skills.push(el.innerText.trim()));
    }

    const certContainer = document.querySelector('#licenses_and_certifications, #certifications');
    let certifications = [];
    if (certContainer) {
        const certParent = certContainer.closest('section') || certContainer.parentElement?.parentElement?.parentElement;
        if (certParent) {
            const items = certParent.querySelectorAll('li.artdeco-list__item');
            items.forEach(item => {
                const lines = item.innerText.split('\\n').map(l => l.trim()).filter(Boolean);
                certifications.push(lines.join(' | '));
            });
        }
    }

    const langContainer = document.querySelector('#languages');
    let languages = [];
    if (langContainer) {
        const langParent = langContainer.closest('section') || langContainer.parentElement?.parentElement?.parentElement;
        if (langParent) {
            const items = langParent.querySelectorAll('li.artdeco-list__item');
            items.forEach(item => languages.push(item.innerText.trim()));
        }
    }

    return { name, headline, location, about, experiences, education, skills, certifications, languages };
}
"""


def _fmt_section(title: str, items: list[str]) -> str:
    if not items:
        return ""
    body = "\n".join(f"  - {i}" for i in items if i)
    return f"### {title}\n{body}\n" if body.strip() else ""


def _run_playwright_scrape(url: str, li_email: str, li_password: str) -> str:
    """Open a headless Chromium, log in, navigate to ``url``, scrape the
    profile sections, return Markdown. Empty string on any failure.

    Synchronous — the service wraps it in ``asyncio.to_thread``.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                )
            )
            page = context.new_page()
            print("[LINKEDIN EXTRACTOR] Iniciando sesión en LinkedIn...")
            page.goto(
                "https://www.linkedin.com/login",
                wait_until="domcontentloaded",
                timeout=25000,
            )
            time.sleep(2)

            # Multiple selector strategies (LinkedIn A/B tests the login UI).
            username_sel = "#username, input[name='session_key'], input[autocomplete='username']"
            password_sel = "#password, input[name='session_password'], input[autocomplete='current-password']"
            submit_sel = "button[type='submit'], .btn__primary--large"

            page.wait_for_selector(username_sel, timeout=8000)
            page.fill(username_sel, li_email)
            time.sleep(0.8)
            page.fill(password_sel, li_password)
            time.sleep(0.5)
            page.click(submit_sel)

            try:
                page.wait_for_url(
                    lambda u: any(
                        marker in u
                        for marker in ("feed", "mynetwork", "/in/", "checkpoint", "challenge")
                    ),
                    timeout=25000,
                )
            except Exception:
                page.wait_for_load_state("networkidle", timeout=20000)
            time.sleep(2)

            current_url = page.url
            print(f"[LINKEDIN EXTRACTOR] URL post-login: {current_url}")

            if any(marker in current_url for marker in ("checkpoint", "challenge", "security")):
                print("[LINKEDIN EXTRACTOR WARN] LinkedIn pidió verificación adicional (CAPTCHA/2FA). Abortando.")
                return ""

            if "login" in current_url or "authwall" in current_url:
                print(f"[LINKEDIN EXTRACTOR ERROR] Login falló. URL: {current_url}")
                return ""

            print("[LINKEDIN EXTRACTOR] ✅ Sesión iniciada correctamente.")
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            time.sleep(3)

            # Scroll to load lazy sections.
            for _ in range(6):
                page.keyboard.press("End")
                time.sleep(1.2)

            data = page.evaluate(_JS_EXTRACTOR)

            parts = ["# Perfil LinkedIn Extraído"]
            if data.get("name"):
                parts.append(f"**Nombre:** {data['name']}")
            if data.get("headline"):
                parts.append(f"**Titular:** {data['headline']}")
            if data.get("location"):
                parts.append(f"**Ubicación:** {data['location']}")
            if data.get("about"):
                parts.append(f"\n### Resumen / Acerca de\n{data['about']}\n")
            parts.append(_fmt_section("Experiencia Laboral", data.get("experiences", [])))
            parts.append(_fmt_section("Educación", data.get("education", [])))
            parts.append(_fmt_section("Habilidades", data.get("skills", [])))
            parts.append(_fmt_section("Certificaciones y Licencias", data.get("certifications", [])))
            parts.append(_fmt_section("Idiomas", data.get("languages", [])))
            result = "\n".join(p for p in parts if p)
            print(
                f"[LINKEDIN EXTRACTOR] ✅ Secciones: exp={len(data.get('experiences',[]))}, "
                f"skills={len(data.get('skills',[]))}, certs={len(data.get('certifications',[]))}"
            )
            return result

        except Exception as scrape_err:
            print(f"[LINKEDIN EXTRACTOR ERROR] Error durante scraping autenticado: {scrape_err}")
            return ""
        finally:
            browser.close()


class PlaywrightAuthAdapter:
    """Adapter that drives headless Chromium to scrape an authenticated profile."""

    strategy_name = "playwright_auth"

    def __init__(self) -> None:
        email = os.getenv("LINKEDIN_EMAIL", "").strip()
        password = os.getenv("LINKEDIN_PASSWORD", "").strip()
        if not email or not password:
            raise ValueError(
                "PlaywrightAuthAdapter requires LINKEDIN_EMAIL + LINKEDIN_PASSWORD."
            )
        self._email = email
        self._password = password

    def scrape(self, linkedin_url: str) -> str:
        return _run_playwright_scrape(linkedin_url, self._email, self._password)


__all__ = ["PlaywrightAuthAdapter"]