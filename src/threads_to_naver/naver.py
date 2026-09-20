from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Self

from playwright.sync_api import (
    BrowserContext,
    Frame,
    Locator,
    Page,
    sync_playwright,
)
from playwright.sync_api import (
    TimeoutError as PlaywrightTimeoutError,
)

from .config import Config
from .models import ThreadPost

TITLE_SELECTORS = (
    ".se-documentTitle",
    ".se-title-text",
    '.se-title-text [contenteditable="true"]',
    '[contenteditable="true"][data-placeholder*="제목"]',
    'textarea[placeholder*="제목"]',
)
BODY_SELECTORS = (
    ".se-section-text .se-text-paragraph",
    '.se-component-content .se-text-paragraph[contenteditable="true"]',
    '.se-text-paragraph[contenteditable="true"]',
    '[contenteditable="true"][data-placeholder*="본문"]',
)
DRAFT_SELECTORS = (
    'button:has-text("임시저장")',
    '[role="button"]:has-text("임시저장")',
    'button:has-text("저장")',
    '[role="button"]:has-text("저장")',
)
IMAGE_BUTTON_SELECTORS = (
    'button[data-name="image"]',
    'button[aria-label*="사진"]',
    'button:has-text("사진")',
)


class NaverDraftWriter:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._playwright = None
        self._context: BrowserContext | None = None

    def __enter__(self) -> Self:
        self._playwright = sync_playwright().start()
        self._context = self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(self._config.profile_dir),
            headless=self._config.headless,
            viewport={"width": 1440, "height": 1000},
            locale="ko-KR",
        )
        return self

    def __exit__(self, *_: object) -> None:
        if self._context:
            self._context.close()
        if self._playwright:
            self._playwright.stop()

    def login(self) -> None:
        page = self._new_page()
        page.goto("https://nid.naver.com/nidlogin.login", wait_until="domcontentloaded")
        print("Log in to Naver in the opened browser. Credentials stay in the browser.")
        print("Waiting up to 10 minutes for the Naver login session...")
        for _ in range(600):
            cookie_names = {
                cookie["name"] for cookie in self._context.cookies("https://naver.com")
            }
            if "NID_AUT" in cookie_names or "NID_SES" in cookie_names:
                print("Naver login session detected and saved.")
                return
            page.wait_for_timeout(1_000)
        raise RuntimeError("Timed out waiting for Naver login.")

    def create_draft(self, post: ThreadPost, media_paths: Iterable[Path]) -> None:
        page = self._open_editor()
        page.wait_for_timeout(3_000)

        if "nidlogin" in page.url or "nid.naver.com" in page.url:
            raise RuntimeError("Naver login expired. Run `threads-to-naver login`.")

        title = _find_visible(page, TITLE_SELECTORS, "title editor")
        title.click()
        page.keyboard.press("ControlOrMeta+A")
        page.keyboard.press("Backspace")
        page.keyboard.insert_text(post.title)

        body = _find_visible(page, BODY_SELECTORS, "body editor")
        body.click()
        page.keyboard.press("ControlOrMeta+A")
        page.keyboard.press("Backspace")
        _insert_verbatim(page, post.text)

        paths = list(media_paths)
        if paths:
            self._upload_media(page, paths)

        draft_button = _find_safe_draft_button(page)
        draft_button.click()
        page.wait_for_timeout(5_000)
        self._save_artifact(page, post.id, "saved")

    def _upload_media(self, page: Page, paths: list[Path]) -> None:
        upload_button = _find_visible(
            page, IMAGE_BUTTON_SELECTORS, "image upload button"
        )
        for path in paths:
            with page.expect_file_chooser(timeout=10_000) as chooser_info:
                upload_button.click()
            chooser_info.value.set_files(str(path))
            page.wait_for_timeout(2_000)

    def _open_editor(self) -> Page:
        page = self._new_page()
        if self._config.naver_blog_id:
            write_url = self._config.naver_write_url.format(
                blog_id=self._config.naver_blog_id
            )
            page.goto(write_url, wait_until="domcontentloaded", timeout=60_000)
            return page

        page.goto(
            "https://www.naver.com/", wait_until="domcontentloaded", timeout=60_000
        )
        cookie_names = {
            cookie["name"] for cookie in self._context.cookies("https://naver.com")
        }
        if not ({"NID_AUT", "NID_SES"} & cookie_names):
            raise RuntimeError("Naver login expired. Run `threads-to-naver login`.")

        blog_tab = page.get_by_text("블로그", exact=True).filter(visible=True).first
        try:
            blog_tab.wait_for(state="visible", timeout=15_000)
        except PlaywrightTimeoutError as error:
            raise RuntimeError("Could not find the Naver Blog account menu.") from error
        blog_page = self._click_maybe_new_page(page, blog_tab)
        blog_page.wait_for_timeout(1_500)
        write_link = (
            blog_page.get_by_text("글쓰기", exact=True).filter(visible=True).first
        )
        try:
            write_link.wait_for(state="visible", timeout=15_000)
        except PlaywrightTimeoutError as error:
            raise RuntimeError("Could not find the Naver Blog write link.") from error
        return self._click_maybe_new_page(blog_page, write_link)

    def _click_maybe_new_page(self, source_page: Page, control: Locator) -> Page:
        try:
            with self._context.expect_page(timeout=10_000) as page_info:
                control.click()
            destination = page_info.value
            destination.wait_for_load_state("domcontentloaded")
            return destination
        except PlaywrightTimeoutError:
            source_page.wait_for_load_state("domcontentloaded")
            return source_page

    def _new_page(self) -> Page:
        if not self._context:
            raise RuntimeError("NaverDraftWriter must be used as a context manager.")
        return (
            self._context.pages[0] if self._context.pages else self._context.new_page()
        )

    def _save_artifact(self, page: Page, post_id: str, suffix: str) -> None:
        timestamp = datetime.now(self._config.timezone).strftime("%Y%m%d-%H%M%S")
        base = self._config.artifacts_dir / f"{timestamp}-{post_id}-{suffix}"
        page.screenshot(path=str(base.with_suffix(".png")), full_page=True)
        metadata = {"url": page.url, "title": page.title(), "post_id": post_id}
        base.with_suffix(".json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def _candidate_frames(page: Page) -> list[Page | Frame]:
    return [page, *page.frames]


def _find_visible(page: Page, selectors: tuple[str, ...], description: str) -> Locator:
    for frame in _candidate_frames(page):
        for selector in selectors:
            candidates = frame.locator(selector)
            for index in range(min(candidates.count(), 10)):
                candidate = candidates.nth(index)
                if candidate.is_visible():
                    return candidate
    raise RuntimeError(
        f"Could not find the Naver {description}. "
        "The editor may have changed; no publish control was clicked."
    )


def _insert_verbatim(page: Page, text: str) -> None:
    lines = text.split("\n")
    for index, line in enumerate(lines):
        if line:
            page.keyboard.insert_text(line)
        if index < len(lines) - 1:
            page.keyboard.press("Shift+Enter")


def _is_safe_draft_label(label: str) -> bool:
    compact = " ".join(label.split())
    if "발행" in compact:
        return False
    return compact == "임시저장" or compact == "저장" or compact.startswith("저장 |")


def _find_safe_draft_button(page: Page) -> Locator:
    for frame in _candidate_frames(page):
        for selector in DRAFT_SELECTORS:
            candidates = frame.locator(selector)
            for index in range(min(candidates.count(), 20)):
                candidate = candidates.nth(index)
                if not candidate.is_visible():
                    continue
                label = (
                    candidate.inner_text()
                    or candidate.get_attribute("aria-label")
                    or ""
                ).strip()
                box = candidate.bounding_box()
                if _is_safe_draft_label(label) and box and box["y"] < 180:
                    return candidate
    raise RuntimeError(
        "Could not identify a safe Naver temporary-save control. "
        "No publish control was clicked."
    )
