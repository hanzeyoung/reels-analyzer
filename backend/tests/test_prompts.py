import pytest

from app.prompts import load_prompt


@pytest.mark.parametrize("name", ["vision_shot", "guide_writer"])
def test_load_prompt_parses_system_and_user(name: str):
    template = load_prompt(name)
    assert template.system.strip() != ""
    assert template.user_template.strip() != ""
    assert "```" not in template.system
    assert "```" not in template.user_template


def test_vision_shot_user_template_has_expected_placeholders():
    template = load_prompt("vision_shot")
    assert "{cut_count}" in template.user_template
    assert "{caption}" in template.user_template


def test_guide_writer_user_template_has_confidence_placeholder():
    template = load_prompt("guide_writer")
    assert "{confidence}" in template.user_template


def test_load_prompt_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        load_prompt("does_not_exist")
