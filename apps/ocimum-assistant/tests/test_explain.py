import pytest

from ocimum_assistant import explain


def test_text_file_becomes_a_fenced_question(tmp_path):
    f = tmp_path / "notes.md"
    f.write_text("# Plan\nUse ``` fences.\n")
    q = explain.question_for(f)
    assert "“notes.md”" in q and "Don't change anything" in q
    # The fence is longer than any backtick run in the file.
    assert "\n````\n# Plan\nUse ``` fences.\n````" in q
    assert str(tmp_path) not in q  # the text, not where it lives


def test_long_text_is_cut_and_says_so(tmp_path):
    f = tmp_path / "log.txt"
    f.write_text("z" * (explain.MAX_CHARS + 10))
    q = explain.question_for(f)
    assert "first 40,000 characters" in q
    assert q.count("z") == explain.MAX_CHARS


def test_binary_and_empty_files_are_refused(tmp_path):
    b = tmp_path / "photo.jpg"
    b.write_bytes(b"\xff\xd8\xff\x00\x01binary")
    with pytest.raises(explain.CannotExplain, match="isn't text"):
        explain.question_for(b)
    e = tmp_path / "empty.txt"
    e.write_text("  \n")
    with pytest.raises(explain.CannotExplain, match="no text"):
        explain.question_for(e)
    with pytest.raises(explain.CannotExplain, match="not a file"):
        explain.question_for(tmp_path)


def test_office_files_need_libreoffice(tmp_path):
    d = tmp_path / "letter.docx"
    d.write_bytes(b"PK\x03\x04")
    with pytest.raises(explain.CannotExplain, match="LibreOffice"):
        explain.extract(d, which=lambda _p: None)


def test_utf8_cut_at_the_sniff_boundary_is_still_text():
    data = b"a" * 8191 + "é".encode()
    assert explain._is_text(data)
