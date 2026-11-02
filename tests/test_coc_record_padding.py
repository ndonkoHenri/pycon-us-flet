"""CoC's filled action obeys D-344 in every label state, including a pending send."""

import pytest

from pycon_us.ui.coc_review_dialog import Review, record_button


@pytest.mark.parametrize(
    "sending,maybe_sent", [(False, False), (False, True), (True, False)]
)
def test_record_action_reserves_space_around_wrapped_labels(
    sending: bool, maybe_sent: bool
) -> None:
    """Idle, retry and busy labels retain Material's full-size inset at large text."""
    button = record_button(
        Review("MOCK0002", "Grace Sample", sending=sending, maybe_sent=maybe_sent),
        lambda: None,
    )
    assert button.style is not None
    padding = button.style.padding
    assert padding is not None
    assert (padding.left, padding.right, padding.top, padding.bottom) == (24, 24, 8, 8)
    assert button.elevation == 0
