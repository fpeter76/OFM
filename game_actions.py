import logging

from playwright.sync_api import Page

import task_tactics_school


def run_once(page: Page, logger: logging.Logger) -> int:
    """Run each configured task once and return seconds until the next check."""
    return task_tactics_school.run_once(page, logger)
