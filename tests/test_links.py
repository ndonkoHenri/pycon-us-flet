"""Tests for the link rule (INFO-14, ux.md §4.7): ``ui.links`` and ``core.links``.

What a target is and how it opens, Copy for phone numbers, addresses and any other
text (``copy_text()``, D-263), and how a failure is said and logged. The helpers run
with a fake page bound as Flet binds a session's page and the in-memory launcher and
clipboard (``tests/link_rule.py``); feed texts' links are tested in
``test_links_feed.py``, the rows that use them in ``test_rows.py``.
"""

import logging

import flet as ft
import pytest

from pycon_us.services import Services
from pycon_us.ui import links
from pycon_us.ui.links import (
    LinkKind,
    contact_of,
    copy_contact,
    copy_text,
    external,
    link_kind,
    open_link,
)
from tests import link_rule
from tests.fake_page import FakePage, android_device
from tests.link_rule import (
    ADDRESS,
    EMAIL,
    HOTLINE,
    PROFILE,
    WEB,
    clipboard,
    launcher,
    said,
)

svc, page = link_rule.svc, link_rule.page


# ------------------------------------------------------------------ the rule


@pytest.mark.parametrize(
    ("target", "app", "kind"),
    [
        ("/more/speakers", False, LinkKind.PAGE),
        ("/schedule/session/42", False, LinkKind.PAGE),
        (WEB, False, LinkKind.WEB),
        ("http://example.org/page", False, LinkKind.WEB),
        ("HTTPS://Example.org/", False, LinkKind.WEB),  # schemes ignore case
        (PROFILE, True, LinkKind.APP),
        ("https://maps.apple.com/?q=Long+Beach+Convention+Center", True, LinkKind.APP),
        ("geo:33.7637,-118.1888", False, LinkKind.APP),  # a map always opens its app
        ("geo:33.7637,-118.1888", True, LinkKind.APP),
        (HOTLINE, False, LinkKind.PHONE),
        (EMAIL, False, LinkKind.EMAIL),
        ("MAILTO:a@b.org", False, LinkKind.EMAIL),
    ],
)
def test_the_link_rule_tells_pages_web_pages_apps_and_contacts_apart(
    target: str, app: bool, kind: LinkKind
) -> None:
    """The link rule tells app pages, web pages, other apps, phones and emails apart.

    A scheme's case does not matter, and a map always opens in its app.
    """
    assert link_kind(target, app=app) is kind


@pytest.mark.parametrize(
    ("kind", "mode"),
    [
        # the attendee stays in context
        (LinkKind.WEB, ft.LaunchMode.IN_APP_BROWSER_VIEW),
        (LinkKind.APP, ft.LaunchMode.EXTERNAL_APPLICATION),
        (LinkKind.PHONE, ft.LaunchMode.EXTERNAL_APPLICATION),
        (LinkKind.EMAIL, ft.LaunchMode.EXTERNAL_APPLICATION),
    ],
)
def test_each_external_kind_opens_in_its_launch_mode(
    kind: LinkKind, mode: ft.LaunchMode
) -> None:
    """Web pages open in the in-app browser; app, phone and email links externally."""
    assert links.LAUNCH_MODES[kind] is mode


def test_a_page_has_no_launch_mode_since_it_is_pushed() -> None:
    """An app page has no launch mode: it is pushed, not launched."""
    assert LinkKind.PAGE not in links.LAUNCH_MODES


@pytest.mark.parametrize(
    "target",
    [
        "javascript:alert(1)",
        "file:///etc/hosts",
        "more/speakers",
        "",
        "sms:+15555550100",
    ],
)
def test_a_target_the_app_does_not_open_is_refused(target: str) -> None:
    """The link rule refuses a javascript, file, sms, relative or empty target."""
    with pytest.raises(ValueError, match="not a link the app opens"):
        link_kind(target)


@pytest.mark.parametrize("target", ["/more/speakers", HOTLINE, EMAIL])
def test_only_a_web_address_can_be_marked_as_another_app_s(target: str) -> None:
    """Marking a page, a phone or an email as another app's raises ValueError.

    The flag never does nothing silently: a page, a phone or an email has one way to
    open.
    """
    with pytest.raises(ValueError, match="only a web address opens in another app"):
        link_kind(target, app=True)


@pytest.mark.parametrize(
    ("target", "copied"),
    [
        (HOTLINE, "+1-562-662-4082"),
        ("tel:+1%20562%20662%204082", "+1 562 662 4082"),
        (EMAIL, ADDRESS),  # without the query
    ],
)
def test_copy_takes_the_number_or_the_address_alone(target: str, copied: str) -> None:
    """Copy takes the decoded phone number, or the email address without its query."""
    assert contact_of(target) == copied


# ------------------------------------------------------------------ opening


async def test_open_link_pushes_a_page_as_a_markdown_link_would(
    page: FakePage, svc: Services
) -> None:
    """Opening an app page pushes its route and launches nothing."""
    await open_link(svc, "/more/sprints")
    assert page.navigated == ["/more/sprints"]
    assert launcher(svc).launched == []


async def test_open_link_launches_a_web_page_in_the_in_app_browser(
    page: FakePage, svc: Services
) -> None:
    """Opening a web page launches it in the in-app browser view."""
    await open_link(svc, WEB)
    assert launcher(svc).launched == [(WEB, ft.LaunchMode.IN_APP_BROWSER_VIEW)]


async def test_a_link_the_platform_cannot_open_says_so_and_logs_no_address(
    page: FakePage, svc: Services, caplog: pytest.LogCaptureFixture
) -> None:
    """A link no app opens says so, and logs the error's class but not the address.

    The error is what Android's url_launcher reports, through Flet, when no app takes
    the intent: it carries the address.
    """
    launcher(svc).error = RuntimeError(
        f"PlatformException(ACTIVITY_NOT_FOUND, No Activity found to handle intent "
        f"{{ {EMAIL} }}, null, null)"
    )
    with caplog.at_level(logging.WARNING):
        await open_link(svc, EMAIL)
    assert said(page) == ["Couldn't open the link"]
    assert [r.getMessage() for r in caplog.records] == [
        "Could not open the email link: RuntimeError"
    ]
    assert ADDRESS not in caplog.text  # nor in a traceback (D-72)


# ------------------------------------------------------------------ copying


@pytest.mark.parametrize(
    ("target", "copied", "message"),
    [
        (HOTLINE, "+1-562-662-4082", "Phone number copied"),
        (EMAIL, ADDRESS, "Email address copied"),
    ],
)
async def test_a_copy_puts_the_contact_on_the_clipboard_and_says_so(
    page: FakePage, svc: Services, target: str, copied: str, message: str
) -> None:
    """A copy puts the number or the address on the clipboard and says which it was."""
    await copy_contact(svc, target)
    assert clipboard(svc).value == copied
    assert said(page) == [message]


@pytest.mark.parametrize(
    ("sdk", "messages"), [(32, ["Email address copied"]), (33, []), (36, [])]
)
async def test_android_13_and_later_confirm_a_copy_themselves(
    page: FakePage, svc: Services, sdk: int, messages: list[str]
) -> None:
    """On Android 13 and later the system confirms a copy, so the app says nothing.

    On Android 12 and earlier the app still says it was copied.
    """
    page.platform = ft.PagePlatform.ANDROID
    page.device = android_device(sdk)
    await copy_contact(svc, EMAIL)
    assert clipboard(svc).value == ADDRESS
    assert said(page) == messages  # no SnackBar over the system's own overlay


async def test_a_copy_is_confirmed_when_the_android_version_cannot_be_read(
    page: FakePage, svc: Services
) -> None:
    """On Android, a copy is confirmed when the device's SDK version cannot be read."""
    page.platform = ft.PagePlatform.ANDROID
    page.device_error = TimeoutError()
    await copy_contact(svc, EMAIL)
    assert said(page) == ["Email address copied"]


@pytest.mark.parametrize(
    ("target", "message"),
    [
        (HOTLINE, "Couldn't copy the phone number"),
        (EMAIL, "Couldn't copy the email address"),
    ],
)
async def test_a_copy_that_fails_says_what_was_not_copied_and_logs_no_address(
    page: FakePage,
    svc: Services,
    caplog: pytest.LogCaptureFixture,
    target: str,
    message: str,
) -> None:
    """A failed copy says what was not copied and logs that, never the contact."""
    page.platform = ft.PagePlatform.ANDROID  # a failure is said on every platform
    page.device = android_device(34)
    # What Flet raises when the Flutter side does not answer: the call's arguments.
    clipboard(svc).error = TimeoutError(
        f"Timeout waiting for invokeMethod set({{'data': '{contact_of(target)}'}}) call"
    )
    with caplog.at_level(logging.WARNING):
        await copy_contact(svc, target)
    assert said(page) == [message]
    assert contact_of(target) not in caplog.text
    assert [r.getMessage() for r in caplog.records] == [f"{message}: TimeoutError"]


PASSWORD = "pyconLB2026"
COPIED = "Password copied"
FAILED = "Couldn't copy the password"


async def test_a_text_copy_puts_the_text_on_the_clipboard_and_says_so(
    page: FakePage, svc: Services
) -> None:
    """``copy_text()`` copies the text as given and confirms it once, in its words."""
    await copy_text(svc, PASSWORD, COPIED, FAILED)
    assert clipboard(svc).value == PASSWORD
    assert said(page) == [COPIED]


@pytest.mark.parametrize(("sdk", "messages"), [(32, [COPIED]), (33, []), (36, [])])
async def test_a_text_copy_leaves_the_confirmation_to_android_13_and_later(
    page: FakePage, svc: Services, sdk: int, messages: list[str]
) -> None:
    """On Android 13 and later only the system's overlay confirms a copy (ux.md §4.7).

    Android 12 and earlier get the app's SnackBar, as iOS does.
    """
    page.platform = ft.PagePlatform.ANDROID
    page.device = android_device(sdk)
    await copy_text(svc, PASSWORD, COPIED, FAILED)
    assert clipboard(svc).value == PASSWORD
    assert said(page) == messages


@pytest.mark.parametrize(
    ("platform", "sdk"), [(ft.PagePlatform.IOS, None), (ft.PagePlatform.ANDROID, 34)]
)
async def test_a_failed_text_copy_says_so_and_logs_no_value(
    page: FakePage,
    svc: Services,
    caplog: pytest.LogCaptureFixture,
    platform: ft.PagePlatform,
    sdk: int | None,
) -> None:
    """A failed copy says so on every platform; the log names it, never the value."""
    page.platform = platform
    page.device = android_device(sdk) if sdk else None
    # What Flet raises when the Flutter side does not answer: the call's arguments.
    clipboard(svc).error = TimeoutError(
        f"Timeout waiting for invokeMethod set({{'data': '{PASSWORD}'}}) call"
    )
    with caplog.at_level(logging.WARNING):
        await copy_text(svc, PASSWORD, COPIED, FAILED)
    assert clipboard(svc).value != PASSWORD
    assert said(page) == [FAILED]  # never "copied", even where the system confirms
    assert PASSWORD not in caplog.text  # D-72
    assert [r.getMessage() for r in caplog.records] == [f"{FAILED}: TimeoutError"]


async def test_only_phone_and_email_links_copy(page: FakePage, svc: Services) -> None:
    """Copying a web address raises ValueError: only phones and emails copy."""
    with pytest.raises(ValueError, match="only phone and email"):
        await copy_contact(svc, WEB)


def test_an_external_button_s_node_says_whether_it_is_disabled() -> None:
    """F42: the merged node takes the button's state, as ``named()``'s does (D-214)."""
    for disabled in (True, False):
        button = ft.FilledTonalButton("Propose one", disabled=disabled)
        merged = external("open_spaces.propose", button)
        assert isinstance(merged, ft.MergeSemantics)
        node = merged.content
        assert isinstance(node, ft.Semantics) and node.link
        assert node.disabled is disabled
