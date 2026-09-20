from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Self
from urllib.parse import parse_qs, urlsplit

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
VIDEO_BUTTON_SELECTORS = (
    'button[data-name="video"]',
    'button[aria-label*="동영상"]',
    'button:has-text("동영상")',
)
VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".webm"}
SAFE_DRAFT_COUNT_LIMIT = 98


@dataclass(frozen=True)
class TempDraft:
    log_no: str


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
        page = self._prepare_editor()
        draft_count = _current_draft_count(page)
        if draft_count is not None and draft_count >= SAFE_DRAFT_COUNT_LIMIT:
            raise RuntimeError(
                f"Naver has {draft_count} temporary drafts. "
                "Review or publish some drafts before resuming; no new draft was created."
            )
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
            self._upload_media(page, paths, post.title)
        self._append_configured_footer(page)

        draft_button = _find_safe_draft_button(page)
        draft_button.click()
        page.wait_for_timeout(5_000)
        self._save_artifact(page, post.id, "saved")

    def list_temp_drafts(self) -> list[TempDraft]:
        page = self._prepare_editor()
        drafts, _ = self._open_temp_draft_list(page)
        return drafts

    def append_footer_to_temp_draft(
        self,
        log_no: str,
        footer_url: str,
        footer_image_path: Path,
        *,
        save_artifact: bool = False,
    ) -> bool:
        page = self._prepare_editor()
        self._load_temp_draft(page, log_no)
        footer_text_exists = footer_url in _editor_body_text(page)
        footer_link_exists = _footer_link_count(page, footer_url) > 0
        if footer_text_exists and footer_link_exists:
            return False
        if footer_text_exists:
            _make_text_link(page, footer_url)
            draft_button = _find_safe_draft_button(page)
            draft_button.click()
            page.wait_for_timeout(5_000)
            if _footer_link_count(page, footer_url) == 0:
                raise RuntimeError(
                    f"Naver draft {log_no} did not retain the clickable footer link."
                )
            if save_artifact:
                self._save_artifact(page, log_no, "footer-saved")
            return True

        before_images = _visible_image_count(page)
        self._append_footer(page, footer_url, footer_image_path)
        draft_button = _find_safe_draft_button(page)
        draft_button.click()
        page.wait_for_timeout(5_000)

        if footer_url not in _editor_body_text(page):
            raise RuntimeError(
                f"Naver draft {log_no} did not retain the configured footer URL."
            )
        if _footer_link_count(page, footer_url) == 0:
            raise RuntimeError(
                f"Naver draft {log_no} did not retain the clickable footer link."
            )
        if _visible_image_count(page) <= before_images:
            raise RuntimeError(
                f"Naver draft {log_no} did not retain the configured footer image."
            )
        if save_artifact:
            self._save_artifact(page, log_no, "footer-saved")
        return True

    def _upload_media(self, page: Page, paths: list[Path], post_title: str) -> None:
        for path in paths:
            is_video = path.suffix.lower() in VIDEO_SUFFIXES
            if is_video:
                _upload_video(page, path, post_title)
                continue
            upload_button = _find_visible(
                page,
                IMAGE_BUTTON_SELECTORS,
                "image upload button",
            )
            with page.expect_file_chooser(timeout=10_000) as chooser_info:
                upload_button.click()
            chooser_info.value.set_files(str(path))
            page.wait_for_timeout(2_000)

    def _append_configured_footer(self, page: Page) -> None:
        if not self._config.footer_url and self._config.footer_image_path is None:
            return
        if not self._config.footer_url or self._config.footer_image_path is None:
            raise RuntimeError(
                "Configure both footer_url and footer_image_path, or leave both empty."
            )
        self._append_footer(
            page,
            self._config.footer_url,
            self._config.footer_image_path,
        )

    def _append_footer(
        self, page: Page, footer_url: str, footer_image_path: Path
    ) -> None:
        if not footer_image_path.is_file():
            raise FileNotFoundError(f"Missing footer image: {footer_image_path}")
        paragraph = _find_last_visible_text_paragraph(page)
        if _editor_text_body_text(page).strip():
            if _paragraph_is_in_list(paragraph):
                _insert_text_link_after_list(page, paragraph, footer_url)
            else:
                _place_caret_at_end(paragraph)
                page.keyboard.press("Shift+Enter")
                page.keyboard.press("Shift+Enter")
                _insert_text_link_at_cursor(page, footer_url)
        else:
            paragraph.click()
            page.keyboard.insert_text(".")
            page.keyboard.press("Backspace")
            _insert_text_link_at_cursor(page, footer_url)
        paragraph = _find_paragraph_containing(page, footer_url)
        _place_caret_at_end(paragraph)
        page.keyboard.press("Shift+Enter")
        self._upload_media(page, [footer_image_path], "footer")

    def _prepare_editor(self) -> Page:
        page = self._open_editor()
        page.wait_for_timeout(3_000)
        if "nidlogin" in page.url or "nid.naver.com" in page.url:
            raise RuntimeError("Naver login expired. Run `threads-to-naver login`.")
        _dismiss_restore_popup(page)
        return page

    def _open_temp_draft_list(
        self, page: Page
    ) -> tuple[list[TempDraft], Locator]:
        count_button = _find_visible(
            page,
            ('button[aria-label^="임시저장된 글 보기"]',),
            "temporary-draft list button",
        )
        with page.expect_response(
            lambda response: urlsplit(response.url).path.endswith(
                "/TempPostList.naver"
            ),
            timeout=15_000,
        ) as response_info:
            count_button.click()
        result = response_info.value.json().get("result", {})
        drafts = [
            TempDraft(log_no=str(item["logNo"]))
            for item in result.get("tempPostList", [])
        ]
        buttons = _find_temp_draft_buttons(page, len(drafts))
        if buttons is None:
            raise RuntimeError(
                "Naver temporary-draft list did not match its visible controls."
            )
        return drafts, buttons

    def _load_temp_draft(self, page: Page, log_no: str) -> None:
        drafts, buttons = self._open_temp_draft_list(page)
        try:
            index = next(
                index for index, draft in enumerate(drafts) if draft.log_no == log_no
            )
        except StopIteration as error:
            raise RuntimeError(f"Naver temporary draft {log_no} no longer exists.") from error

        with page.expect_response(
            lambda response: _is_temp_draft_read_response(response.url, log_no),
            timeout=15_000,
        ):
            buttons.nth(index).click()
        page.wait_for_timeout(2_000)
        _find_visible(page, TITLE_SELECTORS, "loaded temporary-draft title")

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


def _wait_for_visible(
    page: Page,
    selectors: tuple[str, ...],
    description: str,
    *,
    timeout_ms: int = 5_000,
) -> Locator:
    attempts = max(1, timeout_ms // 100)
    for _ in range(attempts):
        try:
            return _find_visible(page, selectors, description)
        except RuntimeError:
            page.wait_for_timeout(100)
    return _find_visible(page, selectors, description)


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


def _dismiss_restore_popup(page: Page) -> bool:
    """Discard only Naver's known autosave-restore prompt, never other dialogs."""
    for frame in _candidate_frames(page):
        popups = frame.locator('[data-group="popupLayer"]')
        for index in range(min(popups.count(), 20)):
            popup = popups.nth(index)
            if not popup.is_visible():
                continue
            label = " ".join((popup.inner_text() or "").split())
            if not (
                label.startswith("작성 중인 글이 있습니다.")
                and "이어서 작성하시겠습니까?" in label
            ):
                continue
            cancel = popup.get_by_role("button", name="취소", exact=True)
            if cancel.count() == 1 and cancel.is_visible():
                cancel.click()
                popup.wait_for(state="hidden", timeout=10_000)
                return True
    return False


def _current_draft_count(page: Page) -> int | None:
    for frame in _candidate_frames(page):
        controls = frame.locator('button[aria-label^="임시저장된 글 보기"]')
        for index in range(min(controls.count(), 10)):
            control = controls.nth(index)
            if not control.is_visible():
                continue
            label = control.get_attribute("aria-label") or ""
            match = re.search(r"(\d+)개", label)
            if match:
                return int(match.group(1))
    return None


def _find_temp_draft_buttons(page: Page, expected_count: int) -> Locator | None:
    for frame in _candidate_frames(page):
        buttons = frame.locator('button[data-click-area="tpb*s.tlist"]')
        if buttons.count() == expected_count:
            return buttons
    return None


def _is_temp_draft_read_response(url: str, log_no: str) -> bool:
    parsed = urlsplit(url)
    return parsed.path.endswith("/RabbitTempPostRead.naver") and (
        parse_qs(parsed.query).get("logNo") == [log_no]
    )


def _editor_body_text(page: Page) -> str:
    parts: list[str] = []
    for frame in _candidate_frames(page):
        components = frame.locator(".se-component-content")
        for index in range(min(components.count(), 100)):
            component = components.nth(index)
            if component.is_visible():
                parts.append(component.inner_text() or "")
    return "\n".join(parts)


def _editor_text_body_text(page: Page) -> str:
    parts: list[str] = []
    for frame in _candidate_frames(page):
        sections = frame.locator(".se-section-text")
        for index in range(min(sections.count(), 100)):
            section = sections.nth(index)
            if section.is_visible():
                parts.append(section.inner_text() or "")
    return "\n".join(parts)


def _find_paragraph_containing(page: Page, text: str) -> Locator:
    match: Locator | None = None
    for frame in _candidate_frames(page):
        paragraphs = frame.locator(".se-text-paragraph")
        for index in range(min(paragraphs.count(), 500)):
            paragraph = paragraphs.nth(index)
            if paragraph.is_visible() and text in (paragraph.inner_text() or ""):
                match = paragraph
    if match is None:
        raise RuntimeError("Could not find the inserted Naver footer text.")
    return match


def _make_text_link(page: Page, url: str) -> None:
    paragraph = _find_paragraph_containing(page, url)
    paragraph.click()
    page.keyboard.press("End")
    for _ in url:
        page.keyboard.press("Shift+ArrowLeft")

    toolbar_button = _wait_for_visible(
        page,
        ('button[data-name="text-link"]',),
        "text-link toolbar button",
    )
    toolbar_button.click()
    url_input = _wait_for_visible(
        page,
        ('input[placeholder="URL을 입력하세요."]',),
        "text-link URL input",
    )
    url_input.fill(url)
    apply_button = _wait_for_visible(
        page,
        ("button.se-custom-layer-link-apply-button",),
        "text-link apply button",
    )
    apply_button.click()
    page.wait_for_timeout(500)
    if _footer_link_count(page, url) == 0:
        raise RuntimeError("Naver did not create a clickable footer link.")


def _insert_text_link_at_cursor(page: Page, url: str) -> None:
    toolbar_button = _wait_for_visible(
        page,
        ('button[data-name="text-link"]',),
        "text-link toolbar button",
    )
    toolbar_button.click()
    url_input = _wait_for_visible(
        page,
        ('input[placeholder="URL을 입력하세요."]',),
        "text-link URL input",
    )
    url_input.fill(url)
    apply_button = _wait_for_visible(
        page,
        ("button.se-custom-layer-link-apply-button",),
        "text-link apply button",
    )
    apply_button.click()
    page.wait_for_timeout(500)
    if _footer_link_count(page, url) == 0:
        raise RuntimeError("Naver did not insert a clickable footer link.")


def _footer_link_count(page: Page, url: str) -> int:
    count = 0
    for frame in _candidate_frames(page):
        links = frame.locator(".se-component-content a, .se-component-content .se-link")
        for index in range(min(links.count(), 500)):
            link = links.nth(index)
            target = link.get_attribute("href") or link.get_attribute("data-href")
            if target == url:
                count += 1
    return count


def _find_last_visible_text_paragraph(page: Page) -> Locator:
    visible: list[Locator] = []
    for frame in _candidate_frames(page):
        paragraphs = frame.locator(".se-section-text .se-text-paragraph")
        for index in range(min(paragraphs.count(), 500)):
            paragraph = paragraphs.nth(index)
            if paragraph.is_visible():
                visible.append(paragraph)
    if not visible:
        raise RuntimeError("Could not find the end of the Naver draft body.")
    return next(
        (
            paragraph
            for paragraph in reversed(visible)
            if (paragraph.inner_text() or "").strip()
        ),
        visible[-1],
    )


def _place_caret_at_end(paragraph: Locator) -> None:
    paragraph.scroll_into_view_if_needed()
    paragraph.click()
    paragraph.evaluate(
        """
        element => {
          const range = element.ownerDocument.createRange();
          range.selectNodeContents(element);
          range.collapse(false);
          const selection = element.ownerDocument.getSelection();
          selection.removeAllRanges();
          selection.addRange(range);
        }
        """
    )


def _paragraph_is_in_list(paragraph: Locator) -> bool:
    return paragraph.locator("xpath=ancestor::li").count() > 0


def _click_at_visual_text_end(paragraph: Locator) -> None:
    nodes = paragraph.locator("span.__se-node")
    for index in range(nodes.count() - 1, -1, -1):
        node = nodes.nth(index)
        if not node.is_visible():
            continue
        box = node.bounding_box()
        if box is None:
            continue
        node.click(
            position={
                "x": max(1, box["width"] - 1),
                "y": max(1, box["height"] / 2),
            }
        )
        return
    raise RuntimeError("Could not focus the end of the Naver list item.")


def _insert_text_link_after_list(page: Page, paragraph: Locator, url: str) -> None:
    original_text = paragraph.inner_text() or ""
    section = paragraph.locator("xpath=ancestor::div[contains(@class,'se-section-text')]")
    _click_at_visual_text_end(paragraph)
    page.keyboard.press("Enter")
    page.wait_for_timeout(300)
    page.keyboard.press("Enter")

    tail: Locator | None = None
    for _ in range(50):
        candidate = section.locator(".se-text-paragraph").last
        if (
            candidate.count() == 1
            and candidate.is_visible()
            and not _paragraph_is_in_list(candidate)
        ):
            tail = candidate
            break
        page.wait_for_timeout(100)
    if tail is None:
        raise RuntimeError("Could not exit the Naver list before appending the footer.")
    if (paragraph.inner_text() or "") != original_text:
        raise RuntimeError(
            "The Naver list item changed while positioning the footer; no draft was saved."
        )

    tail.click()
    page.keyboard.insert_text(".")
    page.keyboard.press("Backspace")
    _insert_text_link_at_cursor(page, url)


def _visible_image_count(page: Page) -> int:
    count = 0
    for frame in _candidate_frames(page):
        images = frame.locator(".se-component-content img")
        count += sum(
            images.nth(index).is_visible()
            for index in range(min(images.count(), 500))
        )
    return count


def _upload_video(page: Page, path: Path, title: str) -> None:
    toolbar_button = _find_visible(page, VIDEO_BUTTON_SELECTORS, "video upload button")
    toolbar_button.click()
    popup = _find_visible(page, (".se-popup-video-upload",), "video upload dialog")
    local_upload = popup.locator(".nvu_local").first
    try:
        local_upload.wait_for(state="visible", timeout=10_000)
    except PlaywrightTimeoutError as error:
        raise RuntimeError(
            "Could not find Naver's local video upload control."
        ) from error

    with page.expect_file_chooser(timeout=10_000) as chooser_info:
        local_upload.click()
    chooser_info.value.set_files(str(path))

    title_input = popup.get_by_placeholder("제목을 입력하세요. (최대 40자, 필수)")
    title_input.wait_for(state="visible", timeout=10_000)
    title_input.fill(title[:40])
    popup.get_by_text("업로드 완료", exact=True).wait_for(
        state="visible", timeout=120_000
    )
    done = popup.get_by_role("button", name="완료", exact=True)
    done.click()
    popup.wait_for(state="hidden", timeout=30_000)
