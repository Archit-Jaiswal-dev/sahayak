from app.prompts import _language_note, _language_rule, build_system_prompt


def test_language_note_hindi_default():
    assert "HINDI" in _language_note("hi")
    assert "HINDI" in _language_note("")


def test_language_note_english():
    assert "ENGLISH" in _language_note("en")


def test_language_rule_hindi_forces_devanagari():
    rule = _language_rule("hi")
    assert "Respond ONLY in HINDI" in rule
    assert "Devanagari" in rule
    assert "ENGLISH" not in rule


def test_language_rule_english_forces_english():
    rule = _language_rule("en")
    assert "Respond ONLY in ENGLISH" in rule
    assert "HINDI" not in rule


def test_build_system_prompt_default_is_hindi():
    prompt = build_system_prompt({})
    assert "Respond ONLY in HINDI" in prompt
    assert "Devanagari" in prompt
    assert "Respond ONLY in ENGLISH" not in prompt


def test_build_system_prompt_english():
    prompt = build_system_prompt({}, language="en")
    assert "Respond ONLY in ENGLISH" in prompt
    assert "Respond ONLY in HINDI" not in prompt


def test_build_system_prompt_contains_fields_and_ministries():
    prompt = build_system_prompt({})
    assert "Fields you must collect" in prompt
    assert "Available CPGRAMS ministries" in prompt
    assert "STAY ON TOPIC" in prompt