from pathlib import Path

from playwright.sync_api import sync_playwright

from threads_to_naver.naver import (
    _current_draft_count,
    _dismiss_restore_popup,
    _editor_text_body_text,
    _find_last_visible_text_paragraph,
    _insert_text_link_at_cursor,
    _insert_verbatim,
    _is_safe_draft_label,
    _make_text_link,
    _paragraph_is_in_list,
    _upload_video,
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


def test_video_upload_uses_nested_uploader_and_required_title(
    tmp_path: Path,
) -> None:
    video = tmp_path / "sample.mp4"
    video.write_bytes(b"not-a-real-video")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(
            '<button data-name="video" '
            "onclick=\"document.querySelector('.se-popup-video-upload').style.display='block';"
            "setTimeout(() => document.querySelector('.nvu_local').style.display='block', 100)\">"
            "동영상</button>"
            '<div class="se-popup-video-upload" style="display:none">'
            '<button class="nvu_local" style="display:none" '
            'onclick="document.querySelector(\'#file\').click()">동영상 추가</button>'
            '<input id="file" type="file" style="display:none" '
            "onchange=\"document.querySelector('#status').textContent='업로드 완료'\">"
            '<input placeholder="제목을 입력하세요. (최대 40자, 필수)">'
            '<span id="status">업로드 진행중</span>'
            '<button onclick="this.parentElement.remove()">완료</button>'
            "</div>"
        )

        _upload_video(page, video, "가" * 50)

        assert page.locator(".se-popup-video-upload").count() == 0
        browser.close()


def test_current_draft_count_uses_accessible_label() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(
            '<button aria-label="임시저장된 글 보기, 98개">98</button>'
        )
        assert _current_draft_count(page) == 98
        browser.close()


def test_footer_url_is_converted_to_clickable_link() -> None:
    url = "https://naver.me/example"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(
            '<div class="se-component-content" contenteditable="true">'
            f'<p class="se-text-paragraph"><span>{url}</span></p></div>'
            '<button data-name="text-link" '
            "onclick=\"window.savedRange=getSelection().getRangeAt(0).cloneRange();"
            "document.querySelector('#link-box').style.display='block'\">링크</button>"
            '<div id="link-box" style="display:none">'
            '<input placeholder="URL을 입력하세요.">'
            '<button class="se-custom-layer-link-apply-button" '
            "onclick=\"const s=getSelection();s.removeAllRanges();"
            "s.addRange(window.savedRange);document.execCommand('createLink',false,"
            "document.querySelector('#link-box input').value)\">적용</button></div>"
        )

        _make_text_link(page, url)

        assert page.locator(f'a[href="{url}"]').count() == 1
        browser.close()


def test_clickable_link_can_be_inserted_at_empty_cursor() -> None:
    url = "https://naver.me/example"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(
            '<div class="se-component-content" contenteditable="true">'
            '<p id="target" class="se-text-paragraph"><br></p></div>'
            '<button data-name="text-link" style="display:none" '
            "onclick=\"window.savedRange=getSelection().getRangeAt(0).cloneRange();"
            "document.querySelector('#link-box').style.display='block'\">링크</button>"
            '<div id="link-box" style="display:none">'
            '<input placeholder="URL을 입력하세요.">'
            '<button class="se-custom-layer-link-apply-button" '
            "onclick=\"const input=document.querySelector('#link-box input');"
            "const span=document.createElement('span');span.className='se-link';"
            "span.dataset.href=input.value;span.textContent=input.value;"
            "window.savedRange.insertNode(span)\">적용</button></div>"
            '<script>setTimeout(() => {'
            'document.querySelector(\'button[data-name="text-link"]\')'
            '.style.display="block";'
            '}, 100);</script>'
        )
        page.locator("#target").click()

        _insert_text_link_at_cursor(page, url)

        assert page.locator(f'.se-link[data-href="{url}"]').count() == 1
        browser.close()


def test_footer_uses_last_nonempty_body_paragraph() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(
            '<div class="se-documentTitle"><p class="se-text-paragraph">제목</p></div>'
            '<div class="se-section-text">'
            '<p class="se-text-paragraph">본문 끝</p>'
            '<p class="se-text-paragraph"></p></div>'
        )

        paragraph = _find_last_visible_text_paragraph(page)

        assert paragraph.inner_text() == "본문 끝"
        browser.close()


def test_empty_text_body_ignores_title_and_video_metadata() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(
            '<div class="se-documentTitle">제목</div>'
            '<div class="se-video">영상 제목</div>'
            '<div class="se-section-text"><p class="se-text-paragraph"></p></div>'
        )

        assert _editor_text_body_text(page).strip() == ""
        browser.close()


def test_list_paragraph_is_detected() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(
            '<ul><li><p id="list-item" class="se-text-paragraph">항목</p></li></ul>'
            '<p id="normal" class="se-text-paragraph">문단</p>'
        )

        assert _paragraph_is_in_list(page.locator("#list-item")) is True
        assert _paragraph_is_in_list(page.locator("#normal")) is False
        browser.close()
