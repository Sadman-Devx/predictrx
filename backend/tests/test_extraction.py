"""Day 8: the prescription draft validator. Pure: no database, no model call (parse_model_output takes text)."""
import json

import pytest

from ai.extraction.prescription import MAX_DRAFTS, MAX_LEN, ExtractionError, parse_model_output


def reply(meds, **extra):
    return json.dumps({"is_prescription": True, "legibility": "clear", "medications": meds, **extra})


def test_plain_object_becomes_drafts():
    result = parse_model_output(reply([{"raw_text": "Tab. Napa 500mg", "brand_name": "Napa",
                                        "strength": "500 mg", "frequency": "1+0+1"}]))
    assert result.legibility == "clear"
    assert result.drafts == [{"raw_text": "Tab. Napa 500mg", "brand_name": "Napa", "strength": "500 mg",
                              "frequency": "1+0+1"}]


def test_fenced_json_is_accepted():
    text = "```json\n" + reply([{"raw_text": "Napa", "brand_name": "Napa"}]) + "\n```"
    assert len(parse_model_output(text).drafts) == 1


def test_chatter_around_the_object_is_ignored():
    text = 'Here you go: {"is_prescription": true, "medications": [{"brand_name": "Napa"}]} hope that helps'
    drafts = parse_model_output(text).drafts
    assert drafts[0]["raw_text"] == "Napa"  # raw_text falls back to the brand name


def test_bare_list_is_accepted():
    drafts = parse_model_output('[{"raw_text": "Napa 500", "brand_name": "Napa"}]').drafts
    assert drafts[0]["brand_name"] == "Napa"


def test_bangla_names_survive_untouched():
    drafts = parse_model_output(reply([{"raw_text": "ট্যাব. নাপা ৫০০", "brand_name": "নাপা"}])).drafts
    assert drafts[0]["brand_name"] == "নাপা"


@pytest.mark.parametrize("flag", [False, "false", "No"])
def test_not_a_prescription(flag):
    with pytest.raises(ExtractionError) as err:
        parse_model_output(json.dumps({"is_prescription": flag, "medications": []}))
    assert err.value.code == "not_a_prescription"


@pytest.mark.parametrize("text", ["I cannot read this image.", "{}", '{"medications": "Napa"}', "", "[1, 2"])
def test_garbage_is_invalid_model_output(text):
    with pytest.raises(ExtractionError) as err:
        parse_model_output(text)
    assert err.value.code == "invalid_model_output"


def test_empty_list_is_no_medications_found():
    with pytest.raises(ExtractionError) as err:
        parse_model_output(reply([]))
    assert err.value.code == "no_medications_found"


def test_heading_lines_are_not_medicines():
    result = parse_model_output(reply([{"raw_text": "Rx", "brand_name": "Rx"},
                                       {"raw_text": "Tab. Napa 500mg", "brand_name": "Napa"}]))
    assert [d["brand_name"] for d in result.drafts] == ["Napa"]
    with pytest.raises(ExtractionError):
        parse_model_output(reply([{"raw_text": "Advice:", "brand_name": ""}]))


def test_a_personal_data_line_is_dropped_not_stored():
    result = parse_model_output(reply([{"raw_text": "Name: Rahim Uddin", "brand_name": ""},
                                       {"raw_text": "Napa", "brand_name": "Napa"}]))
    assert [d["brand_name"] for d in result.drafts] == ["Napa"]
    assert result.redactions.get("NAME") == 1  # a count only, never the text


def test_personal_data_in_strength_is_blanked():
    result = parse_model_output(reply([{"raw_text": "Napa", "brand_name": "Napa", "strength": "01712345678"}]))
    assert result.drafts[0]["strength"] == ""
    assert result.redactions.get("PHONE") == 1


def test_identical_lines_are_kept_once():
    line = {"raw_text": "Napa 500", "brand_name": "Napa", "strength": "500 mg", "frequency": "1+1+1"}
    result = parse_model_output(reply([line, dict(line, brand_name="NAPA"), line]))
    assert len(result.drafts) == 1
    assert result.duplicates_removed == 2


def test_same_medicine_with_a_different_schedule_is_kept_twice():
    result = parse_model_output(reply([{"raw_text": "Napa", "brand_name": "Napa", "frequency": "1+0+0"},
                                       {"raw_text": "Napa", "brand_name": "Napa", "frequency": "0+0+1"}]))
    assert len(result.drafts) == 2


def test_fields_are_length_capped_and_control_characters_removed():
    result = parse_model_output(reply([{"brand_name": "A" * 300, "strength": "5\x00\x07 mg"}]))
    assert len(result.drafts[0]["brand_name"]) == MAX_LEN["brand_name"]
    assert result.drafts[0]["strength"] == "5 mg"


def test_too_many_lines_are_truncated_and_flagged():
    meds = [{"raw_text": f"Medx{i} 500", "brand_name": f"Medx{i}"} for i in range(MAX_DRAFTS + 5)]
    result = parse_model_output(reply(meds))
    assert len(result.drafts) == MAX_DRAFTS
    assert result.truncated is True


def test_unknown_legibility_value_becomes_unknown():
    result = parse_model_output(reply([{"brand_name": "Napa"}], legibility="excellent"))
    assert result.legibility == "unknown"