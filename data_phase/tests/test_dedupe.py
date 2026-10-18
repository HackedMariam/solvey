from so_pipeline.dedupe import DedupeRegistry


def make(qid, url, title):
    return str(qid), url, title


def test_duplicate_id_rejected():
    reg = DedupeRegistry()
    reg.add(*make(1, "https://stackoverflow.com/questions/1/a-title-here", "A title here"))
    hit = reg.check(*make(1, "https://stackoverflow.com/questions/1/a-title-here", "A title here"))
    assert hit is not None
    assert hit.reason == "duplicate_id"
    assert hit.existing_id == "1"


def test_duplicate_url_rejected():
    reg = DedupeRegistry()
    reg.add(*make(1, "https://stackoverflow.com/questions/1/some-long-title", "Some long title"))
    hit = reg.check(*make(999, "https://stackoverflow.com/questions/1/other-slug",
                          "Completely different wording"))
    assert hit is not None
    assert hit.reason == "duplicate_url"
    assert hit.existing_id == "1"


def test_normalized_title_duplicate():
    reg = DedupeRegistry()
    reg.add(*make(1, "https://stackoverflow.com/questions/1/x",
                  "VPN fails after Windows 10 update!!"))
    hit = reg.check(*make(2, "https://stackoverflow.com/questions/2/y",
                          "vpn fails after windows 10 update"))
    assert hit is not None
    assert hit.reason == "duplicate_title"


def test_near_duplicate_title():
    reg = DedupeRegistry()
    reg.add(*make(1, "https://stackoverflow.com/questions/1/x",
                  "Cannot connect to office VPN from home network"))
    hit = reg.check(*make(2, "https://stackoverflow.com/questions/2/y",
                          "Cannot connect to office VPN from my home network"))
    assert hit is not None
    assert hit.reason == "near_duplicate_title"


def test_distinct_issues_not_merged():
    """Generic shared error text must NOT merge different issues."""
    reg = DedupeRegistry()
    reg.add(*make(1, "https://stackoverflow.com/questions/1/x",
                  "SQL syntax error near FROM clause in report query"))
    hit = reg.check(*make(2, "https://stackoverflow.com/questions/2/y",
                          "SQL connection error when opening database file"))
    assert hit is None


def test_short_titles_skip_near_dup():
    reg = DedupeRegistry()
    reg.add(*make(1, "https://stackoverflow.com/questions/1/x", "VPN error"))
    hit = reg.check(*make(2, "https://stackoverflow.com/questions/2/y", "Wifi error"))
    assert hit is None
