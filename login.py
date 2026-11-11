import re
import time
from logging import Logger

from playwright.sync_api import (
    Frame,
    Page,
    TimeoutError as PlaywrightTimeoutError,
)


SITE_URL = "https://en.onlinefootballmanager.com/"
LOGIN_TIMEOUT_MS = 90_000
CONSENT_TIMEOUT_MS = 8_000


class LoginRequiredError(RuntimeError):
    pass


def session_is_authenticated(page: Page) -> bool:
    logout_link = page.get_by_role("link", name="Logout", exact=True)
    return logout_link.count() > 0 and logout_link.first.is_visible()


def accept_cookie_prompt(
    page: Page, logger: Logger, wait_for_prompt: bool = False
) -> None:
    title = "Help us with your consent"

    def has_consent_prompt(frame: Frame) -> bool:
        return frame.get_by_text(title, exact=True).first.is_visible()

    if wait_for_prompt:
        deadline = time.monotonic() + CONSENT_TIMEOUT_MS / 1_000
        while time.monotonic() < deadline:
            if any(has_consent_prompt(frame) for frame in page.frames):
                break
            page.wait_for_timeout(250)

    accept_names = (
        re.compile(r"^accept$", re.IGNORECASE),
        re.compile(r"^accept\s+all(?:\s+cookies)?$", re.IGNORECASE),
        re.compile(r"^accept\s*&\s*close$", re.IGNORECASE),
        re.compile(r"^accept\s+and\s+close$", re.IGNORECASE),
    )
    accepted_count = 0
    for _ in range(6):
        clicked = False
        # Privacy Manager can leave an older iframe underneath a newer one.
        for frame in reversed(page.frames):
            if not has_consent_prompt(frame):
                continue
            for accept_name in accept_names:
                controls = (
                    frame.get_by_role("button", name=accept_name),
                    frame.get_by_role("link", name=accept_name),
                )
                for control_group in controls:
                    for index in range(control_group.count()):
                        control = control_group.nth(index)
                        if control.is_visible():
                            logger.info(
                                "Accepting the topmost visible cookie consent prompt."
                            )
                            control.evaluate("(element) => element.click()")
                            accepted_count += 1
                            clicked = True
                            break
                    if clicked:
                        break
                if clicked:
                    break
            if clicked:
                break
        if not clicked:
            break
        page.wait_for_timeout(500)

    remaining_prompt = any(has_consent_prompt(frame) for frame in page.frames)
    if remaining_prompt:
        logger.warning(
            "A consent prompt remains visible after %d Accept action(s); "
            "no further recognized Accept control was available.",
            accepted_count,
        )
    elif accepted_count:
        logger.info("Accepted %d cookie consent prompt(s).", accepted_count)
    elif not wait_for_prompt:
        logger.debug("No visible cookie consent prompt found.")


def login(page: Page, logger: Logger, username: str, password: str) -> None:
    username = username.strip()
    if not username or not password:
        raise ValueError("Both OFM username and password are required.")

    logger.info("Opening %s", SITE_URL)
    page.goto(SITE_URL, wait_until="domcontentloaded")
    accept_cookie_prompt(page, logger)

    logger.info("Opening the login dialog.")
    page.get_by_role("button", name="Login", exact=True).click()
    dialog = page.get_by_role("dialog", name="Log in or register")
    dialog.wait_for(state="visible")

    logger.info("Entering credentials from the local .env file.")
    dialog.get_by_role("textbox", name="User name or E-mail address").fill(username)
    dialog.get_by_role("textbox", name="Password").fill(password)

    logger.info("Submitting the login form.")
    dialog.get_by_role("button", name="Log in", exact=True).click()
    dialog.wait_for(state="hidden", timeout=LOGIN_TIMEOUT_MS)

    logger.info("Login dialog closed; checking for post-login consent prompts.")
    accept_cookie_prompt(page, logger, wait_for_prompt=True)

    logger.info("Waiting for the authenticated game page.")
    page.get_by_text("Logout", exact=True).wait_for(
        state="visible", timeout=LOGIN_TIMEOUT_MS
    )
    logger.info("Login successful; authenticated game page is ready.")
