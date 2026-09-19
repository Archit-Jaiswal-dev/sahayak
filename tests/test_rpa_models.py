from app.rpa.models import GrievancePayload, normalize_category


def test_normalize_devanagari_and_hinglish():
    assert normalize_category("पानी") == "pani"
    assert normalize_category("paani") == "pani"
    assert normalize_category("PANI") == "pani"
    assert normalize_category("बिजली") == "bijli"
    assert normalize_category("sadak") == "sadak"
    assert normalize_category("स्वच्छता") == "swachhata"
    assert normalize_category("सरकारी") == "sarkari"


def test_normalize_unknown():
    assert normalize_category("kuch aur") == "other"
    assert normalize_category("") == "other"
    assert normalize_category(None) == "other"


def test_payload_routing_from_ai_ministry():
    payload = GrievancePayload(
        category="pani",
        description="पानी की आपूर्ति ठीक नहीं है।",
        location="ग्राम नरायनपुर, सीतापुर",
        date="पिछले एक महीने से",
        name="राम कुमार",
        contact="9876543210",
        ministry="Drinking Water and Sanitation",
    )
    assert payload.category_key == "pani"
    assert payload.routed_ministry == "Drinking Water and Sanitation"


def test_payload_routing_nearest_matches_catalog():
    # Model wrote a paraphrase; routing must land on a real catalog label.
    payload = GrievancePayload(
        category="pani",
        description="x",
        location="y",
        date="z",
        name="n",
        contact="c",
        ministry="Ministry of Drinking Water",
    )
    assert payload.routed_ministry == "Drinking Water and Sanitation"


def test_payload_routing_unknown_falls_back():
    payload = GrievancePayload(
        category="kuch aur",
        description="x",
        location="y",
        date="z",
        name="n",
        contact="c",
    )
    assert payload.routed_ministry == "State Governments/Others"
    assert payload.routed_department == "State Governments/Others"
