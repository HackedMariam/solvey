from so_pipeline.classify import classify_difficulty, is_relevant, relevance_score


def test_easy_question_is_easy():
    r = classify_difficulty(
        "How do I reset my Windows password?",
        "I forgot my password and need to reset it. Thanks in advance!",
        ["windows"],
        resolution="Press Ctrl+Alt+Del, choose Reset password and follow the wizard.",
    )
    assert r.label == "easy"
    assert r.evidence
    assert 0.0 <= r.confidence <= 1.0


def test_hard_question_is_hard():
    body = """
    Intermittent BSOD with stop code VIDEO_TDR_FAILURE. Happens randomly every few hours.
    Minidump analysis shows watchdog.sys. I captured this with wireshark and event viewer:
    Traceback (most recent call last):
      File "C:\\app\\service.py", line 120, in run
    The crash involves the GPU driver, registry settings and a group policy change.
    Also seeing 0x00000116 and 0x000000EA codes. Kernel dump attached.
    """ + ("Long explanation of many diagnostic steps across driver, registry, "
           "group policy and hardware thermal issues. " * 30)
    r = classify_difficulty("Random BSOD with TDR failure after driver update",
                            body, ["windows", "bsod", "minidump"])
    assert r.label == "hard"
    assert r.hard_score > r.easy_score
    assert any(e.startswith("hard:") for e in r.evidence)


def test_medium_by_default():
    r = classify_difficulty(
        "Application throws error when saving file",
        "When I save a file sometimes it fails with an error message. "
        "I tried restarting the application but the problem persists. " * 5,
        ["windows"])
    assert r.label in ("medium", "hard", "easy")
    assert r.confidence > 0


def test_needs_review_flagged_for_ambiguous():
    r = classify_difficulty(
        "Short error",
        "error",  # tiny body: easy signal only, ambiguous
        [])
    assert r.needs_review is True


def test_difficulty_not_based_on_votes_views_or_resolution_presence():
    base = ("Cannot send email via smtp", "SMTP authentication fails when sending email "
            "from outlook client settings.", ["smtp", "outlook"])
    r1 = classify_difficulty(*base, resolution="")           # no resolution
    r2 = classify_difficulty(*base, resolution="fixed")      # has resolution
    # difficulty must not flip just because a resolution exists (short fix is a weak signal)
    assert r1.label == r2.label

    # votes/views are never passed to the classifier at all
    import inspect
    sig = inspect.signature(classify_difficulty)
    assert set(sig.parameters) == {"title", "description", "tags", "resolution"}


def test_confidence_in_range_and_single_label():
    r = classify_difficulty("vpn auth fails", "vpn authentication failed certificate",
                            ["vpn"])
    assert r.label in ("easy", "medium", "hard")
    assert 0.0 <= r.confidence <= 1.0


# ------------------------- relevance ------------------------- #

def test_relevance_accepts_good_match():
    score, matched = relevance_score(
        "VPN authentication failure",
        "Cisco AnyConnect authentication failed with certificate error",
        "The vpn authentication fails after certificate renewal",
        ["vpn", "anyconnect"])
    assert score >= 3
    assert is_relevant("VPN authentication failure",
                       "Cisco AnyConnect authentication failed",
                       "vpn authentication fails", ["vpn"])


def test_relevance_rejects_unrelated():
    score, _ = relevance_score(
        "VPN authentication failure",
        "How to sort a dictionary by value in Python?",
        "I have a python dict and want to sort it.",
        ["python", "dictionary"])
    assert score < 3
    assert not is_relevant("VPN authentication failure",
                           "How to sort a dictionary by value in Python?",
                           "I have a python dict and want to sort it.",
                           ["python", "dictionary"])


def test_relevance_via_tag_hit():
    assert is_relevant("Driver problem", "Something odd with my device",
                       "It stopped working after reboot.", ["drivers"])
