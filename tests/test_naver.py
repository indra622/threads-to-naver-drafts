from playwright.sync_api import sync_playwright

from threads_to_naver.naver import (
    _dismiss_restore_popup,
    _insert_verbatim,
    _is_safe_draft_label,
)


def test_safe_draft_labels() -> None:
    assert _is_safe_draft_label("임시저장") is True
    assert _is_safe_draft_label("저장") is True
    assert _is_safe_draft_label("저장 | 3") is True


def test_publish_labels_are_never_accepted() -> None:
    assert _is_safe_draft_label("발행") is False
    assert _is_safe_draft_label("저장 후 발행") is False
    assert _is_safe_draft_label("예약 발행") is False


def test_unrelated_save_controls_are_not_accepted() -> None:
    assert _is_safe_draft_label("설정 저장") is False
    assert _is_safe_draft_label("저장하기") is False


def test_visible_blog_control_is_selectable_when_account_copy_is_hidden() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(
            '<div id="account" style="display:none"><span>블로그</span></div>'
            '<a href="/blog"><span>블로그</span></a>'
        )
        control = page.get_by_text("블로그", exact=True).filter(visible=True).first
        assert control.is_visible()
        assert (
            control.evaluate("element => element.closest('a').getAttribute('href')")
            == "/blog"
        )
        browser.close()


def test_verbatim_insertion_preserves_text_and_blank_lines() -> None:
    source = "첫 줄\n\n둘째 줄 🙂\n끝"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content('<div id="body" contenteditable="true"></div>')
        body = page.locator("#body")
        body.click()
        _insert_verbatim(page, source)
        assert body.inner_text() == source
        browser.close()


def test_only_known_autosave_restore_popup_is_cancelled() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(
            '<div data-group="popupLayer">'
            "작성 중인 글이 있습니다. 어제 작성중이던 내용이 있습니다. "
            "이어서 작성하시겠습니까?"
            '<button onclick="this.parentElement.remove()">취소</button>'
            "<button>확인</button></div>"
        )
        assert _dismiss_restore_popup(page) is True
        assert page.locator('[data-group="popupLayer"]').count() == 0
        browser.close()


def test_unknown_popup_is_not_touched() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(
            '<div data-group="popupLayer">발행하시겠습니까?'
            '<button>취소</button><button>확인</button></div>'
        )
        assert _dismiss_restore_popup(page) is False
        assert page.locator('[data-group="popupLayer"]').is_visible()
        browser.close()
