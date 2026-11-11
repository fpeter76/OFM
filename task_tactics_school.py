import logging
import re
import time

from playwright.sync_api import Frame, Locator, Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from login import LoginRequiredError, session_is_authenticated


TASK_CHECK_INTERVAL_SECONDS = 30
TACTICS_SCHOOL_PATH = "/game/stadium/tactics"
TACTICS_SCHOOL_URL = f"https://en.onlinefootballmanager.com{TACTICS_SCHOOL_PATH}"
TACTICS_COUNTDOWN_SELECTOR = "#countdownTaktikschuleCardGenerator"
TACTICS_COLLECT_SELECTOR = "#play"
TACTICS_PICKUP_LABEL = re.compile(r"^Pick up\s+1\s+tactic card$", re.IGNORECASE)
_next_collect_attempt_at = 0.0


def _parse_countdown_seconds(text: str) -> int | None:
    text = text.strip()
    clock = re.search(r"(?<!\d)(\d{1,3}):(\d{2})(?::(\d{2}))?(?!\d)", text)
    if clock:
        first, second, third = clock.groups()
        if third is None:
            return int(first) * 60 + int(second)
        return int(first) * 3_600 + int(second) * 60 + int(third)

    units = {
        "hour": 3_600,
        "minute": 60,
        "second": 1,
    }
    total = 0
    matches = re.findall(
        r"(\d+)\s*(hours?|hrs?|h|minutes?|mins?|m|seconds?|secs?|s)\b",
        text,
        re.IGNORECASE,
    )
    for amount, unit in matches:
        unit = unit.lower()
        if unit.startswith(("h",)):
            multiplier = units["hour"]
        elif unit.startswith("m"):
            multiplier = units["minute"]
        else:
            multiplier = units["second"]
        total += int(amount) * multiplier
    return total if matches else None


def _visible_frame_with_selector(page: Page, selector: str) -> Frame | None:
    for frame in reversed(page.frames):
        locator = frame.locator(selector)
        if locator.count() > 0 and locator.first.is_visible():
            return frame
    return None


def _video_is_in_progress(page: Page) -> bool:
    return any(
        frame.locator(".enigma-watermark").count() > 0
        and frame.locator(".enigma-watermark").first.is_visible()
        for frame in page.frames
    )


def _find_pickup_control(page: Page) -> Locator | None:
    for frame in reversed(page.frames):
        controls = (
            frame.get_by_role("button", name=TACTICS_PICKUP_LABEL),
            frame.get_by_role("link", name=TACTICS_PICKUP_LABEL),
        )
        for control_group in controls:
            for index in range(control_group.count()):
                control = control_group.nth(index)
                if control.is_visible() and control.is_enabled():
                    return control

        text_matches = frame.get_by_text(TACTICS_PICKUP_LABEL)
        for index in range(text_matches.count()):
            text = text_matches.nth(index)
            if not text.is_visible():
                continue
            clickable = text.locator(
                "xpath=ancestor-or-self::*[self::button or self::a "
                "or @role='button' or contains(concat(' ', normalize-space(@class), "
                "' '), ' tooltip-button ')][1]"
            )
            if (
                clickable.count() > 0
                and clickable.first.is_visible()
                and clickable.first.is_enabled()
            ):
                return clickable.first
    return None


def _collect_pickup_control(
    page: Page, logger: logging.Logger, control: Locator
) -> None:
    global _next_collect_attempt_at

    now = time.monotonic()
    if now < _next_collect_attempt_at:
        return

    logger.info("Found 'Pick up 1 tactic card'; collecting it.")
    control.click()
    _next_collect_attempt_at = time.monotonic() + 60
    page.wait_for_timeout(1_000)
    logger.info("Clicked the Tactics school card collection control.")


def _open_tactics_school(page: Page, logger: logging.Logger) -> None:
    if TACTICS_SCHOOL_PATH in page.url:
        return

    logger.info("Opening Tactics school at %s.", TACTICS_SCHOOL_URL)
    try:
        page.goto(TACTICS_SCHOOL_URL, wait_until="domcontentloaded")
    except PlaywrightTimeoutError as error:
        raise RuntimeError(
            f"Timed out opening Tactics school at {TACTICS_SCHOOL_URL}. "
            f"Current URL: {page.url}"
        ) from error

    if not re.search(
        rf"{re.escape(TACTICS_SCHOOL_PATH)}/?(?:[?#].*)?$", page.url
    ):
        raise RuntimeError(
            f"Could not open Tactics school at {TACTICS_SCHOOL_URL}; "
            f"Current URL: {page.url}"
        )

    page.wait_for_timeout(1_000)
    logger.info("Tactics school page opened.")


def run_once(page: Page, logger: logging.Logger) -> int:
    global _next_collect_attempt_at

    if not session_is_authenticated(page):
        raise LoginRequiredError("The OFM login screen is visible.")

    _open_tactics_school(page, logger)

    if not session_is_authenticated(page):
        raise LoginRequiredError("The OFM session expired while opening Tactics school.")

    if _video_is_in_progress(page):
        logger.info(
            "Tactics school video is in progress; checking again in %d seconds.",
            TASK_CHECK_INTERVAL_SECONDS,
        )
        return TASK_CHECK_INTERVAL_SECONDS

    pickup_control = _find_pickup_control(page)
    if pickup_control is not None:
        _collect_pickup_control(page, logger, pickup_control)
        return TASK_CHECK_INTERVAL_SECONDS

    countdown_frame = _visible_frame_with_selector(
        page, TACTICS_COUNTDOWN_SELECTOR
    )
    collect_frame = _visible_frame_with_selector(page, TACTICS_COLLECT_SELECTOR)
    if countdown_frame is None:
        logger.warning(
            "Tactics school countdown %s is not visible; checking again in %d seconds.",
            TACTICS_COUNTDOWN_SELECTOR,
            TASK_CHECK_INTERVAL_SECONDS,
        )
        return TASK_CHECK_INTERVAL_SECONDS

    countdown_text = countdown_frame.locator(
        TACTICS_COUNTDOWN_SELECTOR
    ).inner_text().strip()
    remaining_seconds = _parse_countdown_seconds(countdown_text)
    if remaining_seconds is None:
        logger.warning(
            "Could not parse Tactics school countdown %r; checking again in %d seconds.",
            countdown_text,
            TASK_CHECK_INTERVAL_SECONDS,
        )
        return TASK_CHECK_INTERVAL_SECONDS

    if remaining_seconds > 0:
        logger.info(
            "Tactics school card is not ready; countdown %s (%d seconds).",
            countdown_text,
            remaining_seconds,
        )
        return min(TASK_CHECK_INTERVAL_SECONDS, remaining_seconds)

    if collect_frame is None:
        logger.warning(
            "Countdown reached zero, but the Tactics school collect button is not visible."
        )
        return TASK_CHECK_INTERVAL_SECONDS

    collect_button = collect_frame.locator(TACTICS_COLLECT_SELECTOR).first
    button_state = collect_button.evaluate(
        """element => ({
            className: element.className,
            disabled: element.disabled,
            hasClickHandler: typeof element.onclick === "function"
        })"""
    )
    disabled_classes = {"disabled", "grau"}
    classes = set(str(button_state["className"]).split())
    if (
        button_state["disabled"]
        or classes.intersection(disabled_classes)
        or not button_state["hasClickHandler"]
    ):
        logger.info(
            "Countdown reached zero, but the collect button is not ready; "
            "checking again in %d seconds.",
            TASK_CHECK_INTERVAL_SECONDS,
        )
        return TASK_CHECK_INTERVAL_SECONDS

    now = time.monotonic()
    if now < _next_collect_attempt_at:
        return min(
            TASK_CHECK_INTERVAL_SECONDS,
            max(1, int(_next_collect_attempt_at - now)),
        )

    logger.info("Tactics school timer reached zero; collecting the training card.")
    collect_button.click()
    _next_collect_attempt_at = time.monotonic() + 60
    page.wait_for_timeout(1_000)
    return TASK_CHECK_INTERVAL_SECONDS
