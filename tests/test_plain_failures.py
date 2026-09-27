"""F15 (out-of-box journey R1): a model call that brings no answer is explained in plain words, with what to try."""
import pytest

from runesmith.app.planner import why_no_answer


@pytest.mark.parametrize('raw,plain', [
    ('every route failed - nvidia:moonshotai/kimi-k3 timeout', 'did not answer in time'),
    ('nvidia capacity reached; no alternative route available', 'busy or at its free limit'),
    ('auth_failed: Milliner token unavailable', 'refused the key or token'),
    ('Remote outcome unresolved; retrieve the saved job, do not resubmit.', 'will not send it twice'),
    ('something new', 'the model did not answer'),
])
def test_a_missing_answer_is_explained_in_plain_words_and_keeps_the_gateway_words(raw, plain):
    text = why_no_answer(RuntimeError(raw))
    assert plain in text and raw[:40] in text
