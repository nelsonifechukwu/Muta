"""Voice turns must never erase the only visible terminal or queue state."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_failed_voice_turn_stays_visible_in_the_chat():
    source = (ROOT / "audio.js").read_text()
    branch = source.split('if (msg.reason === "voice-turn-failed")', 1)[1].split(
        'stopVoice(t("voice.unavailable"), "voice.unavailable")', 1
    )[0]

    assert 'assistant.fail(t("voice.answerFailed"), "voice.answerFailed")' in branch
    assert "assistant.finalize()" not in branch


def test_voice_queue_and_recovery_use_the_existing_assistant_placeholder():
    source = (ROOT / "audio.js").read_text()

    assert 'case "queued":' in source
    assert "assistant.showQueued(msg.queue_position || 1)" in source
    assert 'case "started":' in source
    assert "assistant.startQueued()" in source
    assert 'case "recovering":' in source
    assert "assistant.showRecovering()" in source


def test_unexpected_socket_close_keeps_an_empty_or_partial_reply_visibly_failed():
    source = (ROOT / "audio.js").read_text()

    assert 'stopVoice(t("voice.connectionFailed"), "voice.connectionFailed")' in source
    stop_voice = source.split("function stopVoice(toastText, failureKey = null)", 1)[1].split(
        "function barge()", 1
    )[0]
    assert "if (failureKey) assistant.fail(toastText || t(failureKey), failureKey)" in stop_voice
    assert "else assistant.finalize()" in stop_voice


def test_webkit_uses_a_direct_silent_script_processor_instead_of_a_prunable_gain_branch():
    source = (ROOT / "audio.js").read_text()

    assert "/AppleWebKit/i.test(navigator.userAgent)" in source
    assert "audioCtx.audioWorklet && !webKit" in source
    assert "captureNode.connect(audioCtx.destination)" in source
    assert "captureSink" not in source
    assert "outputChannelCount: [1]" in source
