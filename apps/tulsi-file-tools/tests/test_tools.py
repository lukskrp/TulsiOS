from pathlib import Path

import pytest

from tulsi_file_tools import app, tools


def which(name):
    return f"/bin/{name}" if name in ("magick", "ffmpeg") else None


def test_output_names_never_overwrite():
    src = Path("/p/photo.JPG")
    taken = {Path("/p/photo (resized).jpg"), Path("/p/photo (resized 2).jpg")}
    out = tools.output_for(src, ".jpg", "resized", exists=lambda p: p in taken)
    assert out == Path("/p/photo (resized 3).jpg")
    # Converting to the same name as the source picks another.
    assert tools.output_for(Path("/p/a.png"), ".png", "", exists=lambda p: False) == Path("/p/a (2).png")
    assert tools.output_for(Path("/p/a.png"), ".jpg", "", exists=lambda p: False) == Path("/p/a.jpg")


def test_resize_and_convert_commands():
    job = tools.resize(Path("/p/x.png"), width=800, which=which, exists=lambda p: False)
    assert job.argv[-3:] == ["-resize", "800x>", "/p/x (resized).png"]
    job = tools.resize(Path("/p/x.png"), percent=50, which=which, exists=lambda p: False)
    assert "50%" in job.argv
    with pytest.raises(tools.ToolError):
        tools.resize(Path("/p/x.png"), which=which)
    with pytest.raises(tools.ToolError):
        tools.resize(Path("/p/x.png"), percent=150, which=which)
    job = tools.convert_image(Path("/p/x.png"), "jpg", which=which, exists=lambda p: False)
    assert "-flatten" in job.argv and job.output == Path("/p/x.jpg")
    job = tools.to_mp3(Path("/p/v.mp4"), which=which, exists=lambda p: False)
    assert job.argv[0] == "/bin/ffmpeg" and "-n" in job.argv and job.output == Path("/p/v.mp3")


def test_missing_programs_are_explained():
    with pytest.raises(tools.ToolError, match="LibreOffice"):
        tools.document_to_pdf(Path("/p/l.docx"), which=lambda n: None)
    with pytest.raises(tools.ToolError, match="magick"):
        tools.resize(Path("/p/x.png"), width=10, which=lambda n: None)


def test_a_batch_does_not_give_two_files_the_same_name(tmp_path, monkeypatch):
    monkeypatch.setattr(tools.shutil, "which", which)
    a = tmp_path / "a.png"
    b = tmp_path / "a.PNG.png"
    a.write_bytes(b"")
    b.write_bytes(b"")
    jobs = app.jobs_for("to-jpg", [a, a], None, None)
    assert [j.output.name for j in jobs] == ["a.jpg", "a (2).jpg"]


def test_run_really_converts_and_keeps_the_original(tmp_path):
    src = tmp_path / "notes.txt"
    src.write_text("hello")
    job = tools.Job([src], tmp_path / "notes (copy).txt", ["cp", str(src), str(tmp_path / "notes (copy).txt")])
    assert tools.run(job).read_text() == "hello"
    assert src.read_text() == "hello"
    bad = tools.Job([src], tmp_path / "never.txt", ["false"])
    with pytest.raises(tools.ToolError):
        tools.run(bad)
    assert not (tmp_path / "never.txt").exists()
