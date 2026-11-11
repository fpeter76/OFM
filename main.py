#!/usr/bin/env python3

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

import game_actions
from login import LoginRequiredError, login, session_is_authenticated


BASE_DIR = Path(__file__).resolve().parent
LOGIN_RETRY_SECONDS = 10 * 60
TASK_RETRY_SECONDS = 30


def configure_logging() -> logging.Logger:
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler = RotatingFileHandler(
        BASE_DIR / "ofm.log",
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    logger = logging.getLogger("ofm")
    logger.setLevel(level)
    logger.handlers.clear()
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    logger.propagate = False
    return logger


def main() -> int:
    load_dotenv(BASE_DIR / ".env")
    logger = configure_logging()
    username = os.getenv("OFM_USERNAME", "").strip()
    password = os.getenv("OFM_PASSWORD", "")
    if not username or not password:
        logger.error(
            "Missing OFM_USERNAME or OFM_PASSWORD. Add them to the local .env file."
        )
        return 2

    logger.info("Starting the OFM assistant scheduler.")
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=False)
            try:
                page = browser.new_page()
                page.set_default_timeout(15_000)
                while True:
                    if not session_is_authenticated(page):
                        logger.info("Login screen detected; starting login.")
                        try:
                            login(page, logger, username, password)
                        except Exception:
                            logger.exception(
                                "Login failed; retrying in %d minutes.",
                                LOGIN_RETRY_SECONDS // 60,
                            )
                            page.wait_for_timeout(LOGIN_RETRY_SECONDS * 1_000)
                            continue

                    try:
                        delay_seconds = game_actions.run_once(page, logger)
                        page.wait_for_timeout(delay_seconds * 1_000)
                    except LoginRequiredError:
                        logger.warning("Session expired; login will be attempted again.")
                    except Exception:
                        logger.exception("Scheduled game task failed.")
                        if not session_is_authenticated(page):
                            logger.info("Login screen detected after task failure.")
                            continue
                        page.wait_for_timeout(TASK_RETRY_SECONDS * 1_000)
            finally:
                browser.close()
    except PlaywrightTimeoutError:
        logger.exception("The OFM assistant timed out outside its retry loop.")
        return 1
    except KeyboardInterrupt:
        logger.info("OFM assistant stopped by user.")
        return 0
    except Exception:
        logger.exception("The OFM assistant failed outside its retry loop.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
