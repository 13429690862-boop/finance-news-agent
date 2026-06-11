from pathlib import Path


def test_requirements_utf8_exact_lines():
    text = Path("requirements.txt").read_text(encoding="utf-8")
    assert text.strip().splitlines() == ["httpx", "PyYAML", "pytest", "pydantic", "openai"]
