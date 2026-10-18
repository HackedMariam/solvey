import pytest

from so_pipeline.taxonomy import (ALL_SUBCATEGORIES, CATEGORY_TAXONOMY,
                                  LEGACY_SUBCATEGORY_ALIASES, RELEVANCE_PROFILES,
                                  SUBCATEGORY_SPECS, SUBCATEGORY_TO_CATEGORY,
                                  DIFFICULTY_LEVELS, TARGET_PER_CELL,
                                  all_specs_for, validate_subcategory)


def test_taxonomy_shape():
    assert len(CATEGORY_TAXONOMY) == 5
    for cat, subs in CATEGORY_TAXONOMY.items():
        assert len(subs) == 5, cat
    assert len(ALL_SUBCATEGORIES) == 25
    assert len(SUBCATEGORY_TO_CATEGORY) == 25


def test_required_subcategory_names_present():
    required = {
        "VPN authentication failure", "VPN connection failure", "Wi-Fi connectivity issue",
        "DNS/network configuration error", "Internet connection problem",
        "Wrong/expired password", "Account locked", "MFA/authentication failure",
        "Permission denied", "Access to restricted resource",
        "Cannot send email", "Cannot receive email", "Email authentication failure",
        "Mailbox/storage full", "Email client configuration problem",
        "Application won't launch", "Application crash", "Installation failure",
        "Application configuration error", "Software update failure",
        "Windows/system error", "Driver problem", "OS update failure",
        "System performance issue", "Hardware-related error",
    }
    assert set(ALL_SUBCATEGORIES) == required


def test_legacy_aliases_map_into_taxonomy():
    for legacy, target in LEGACY_SUBCATEGORY_ALIASES.items():
        assert target in SUBCATEGORY_TO_CATEGORY
        assert validate_subcategory(target)
        assert not validate_subcategory(legacy)


def test_every_subcategory_has_specs_and_profile():
    for sub in ALL_SUBCATEGORIES:
        assert all_specs_for(sub), f"no specs for {sub}"
        assert sub in RELEVANCE_PROFILES, f"no relevance profile for {sub}"
        assert sub in SUBCATEGORY_SPECS


def test_specs_have_valid_kinds_and_tag_budget():
    for sub, specs in SUBCATEGORY_SPECS.items():
        for spec in specs:
            assert spec.kind in ("q", "tagged")
            assert spec.sort in ("relevance", "votes", "creation", "activity")
            if spec.kind == "tagged":
                assert len(spec.value.split(";")) <= 5, f"too many tags in {sub}: {spec}"


def test_difficulty_levels_and_target():
    assert DIFFICULTY_LEVELS == ("easy", "medium", "hard")
    assert TARGET_PER_CELL == 20
    assert len(ALL_SUBCATEGORIES) * len(DIFFICULTY_LEVELS) == 75
