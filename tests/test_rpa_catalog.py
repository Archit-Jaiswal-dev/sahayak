from app.rpa import catalog


def test_catalog_loaded_from_real_capture():
    labels = catalog.ministries()
    assert len(labels) >= 75
    assert "Drinking Water and Sanitation" in labels
    assert "Power" in labels
    assert "Road Transport and Highways" in labels
    assert "State Governments/Others" in labels


def test_exact_match():
    assert catalog.nearest_ministry("Power") == "Power"
    assert catalog.is_valid_ministry("Power")


def test_substring_and_prefix_match():
    assert catalog.nearest_ministry("Ministry of Drinking Water") == (
        "Drinking Water and Sanitation"
    )
    assert catalog.nearest_ministry("Roads") == "Road Transport and Highways"


def test_unknown_returns_none():
    assert catalog.nearest_ministry("xyz nonsense") is None
    assert catalog.nearest_ministry("") is None
    assert catalog.nearest_ministry(None) is None