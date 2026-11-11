from ocimum_assistant.markdown import to_pango


def test_inline_formatting_and_escaping():
    assert to_pango("Use **vlc** or `mpv` <now> & *later*") == (
        "Use <b>vlc</b> or <tt>mpv</tt> &lt;now&gt; &amp; <i>later</i>"
    )


def test_code_spans_keep_markdown_literal():
    assert to_pango("`a**b**`") == "<tt>a**b**</tt>"


def test_blocks():
    md = "# Plan\n- install `vlc`\n2. rebuild\n```\nservices.x = <1>;\n```"
    assert to_pango(md) == "<b>Plan</b>\n• install <tt>vlc</tt>\n2. rebuild\n<tt>services.x = &lt;1&gt;;</tt>"


def test_unbalanced_markers_stay_plain():
    assert to_pango("2 * 3 = 6 and a ** b") == "2 * 3 = 6 and a ** b"
