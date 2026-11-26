"""tulsi-file-tools ACTION [--width N | --percent N] [--no-window] FILE...

The file manager's quick actions (ADR 0037): resize images, convert images, images
to one PDF, audio or video to MP3, documents to PDF. Each makes a new file beside
the original. With a window (the default) it shows progress and the result;
"resize" without a size asks for one first.
"""

from __future__ import annotations

import argparse
import sys
import threading
from pathlib import Path

from . import tools

ACTIONS = ("resize", "to-jpg", "to-png", "to-webp", "images-to-pdf", "to-mp3", "doc-to-pdf")
TITLES = {
    "resize": "Resizing images",
    "to-jpg": "Converting to JPG",
    "to-png": "Converting to PNG",
    "to-webp": "Converting to WebP",
    "images-to-pdf": "Making a PDF",
    "to-mp3": "Converting to MP3",
    "doc-to-pdf": "Converting to PDF",
}


def jobs_for(action: str, files: list[Path], width: int | None, percent: int | None) -> list[tools.Job]:
    if action == "images-to-pdf":
        return [tools.images_to_pdf(files)]
    jobs = []
    made: set[Path] = set()

    def free(p: Path) -> bool:  # names already taken by this batch count as used
        return p.exists() or p in made

    for f in files:
        if action == "resize":
            job = tools.resize(f, width, percent, exists=free)
        elif action.startswith("to-") and action[3:] in tools.IMAGE_FORMATS:
            job = tools.convert_image(f, action[3:], exists=free)
        elif action == "to-mp3":
            job = tools.to_mp3(f, exists=free)
        else:
            job = tools.document_to_pdf(f, exists=free)
        made.add(job.output)
        jobs.append(job)
    return jobs


def run_jobs(jobs: list[tools.Job], progress=lambda i, job: None) -> tuple[list[Path], list[str]]:
    done, errors = [], []
    for i, job in enumerate(jobs):
        progress(i, job)
        try:
            done.append(tools.run(job))
        except tools.ToolError as e:
            errors.append(f"{job.source[0].name}: {e}")
    return done, errors


def _ask_size(parent=None) -> tuple[int | None, int | None] | None:
    from gi.repository import Gtk

    dialog = Gtk.Dialog(title="Resize Images", transient_for=parent, modal=True)
    dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Resize", Gtk.ResponseType.OK)
    dialog.set_default_response(Gtk.ResponseType.OK)
    box = dialog.get_content_area()
    box.set_spacing(6)
    box.set_border_width(12)
    label = Gtk.Label(label="New copies are made next to the originals; they stay as they are.",
                      xalign=0, wrap=True)
    box.pack_start(label, False, False, 0)
    half = Gtk.RadioButton.new_with_label(None, "Half the size")
    full_hd = Gtk.RadioButton.new_with_label_from_widget(half, "1920 pixels wide (Full HD)")
    small = Gtk.RadioButton.new_with_label_from_widget(half, "1024 pixels wide (for email)")
    custom = Gtk.RadioButton.new_with_label_from_widget(half, "Width in pixels:")
    spin = Gtk.SpinButton.new_with_range(16, 20000, 16)
    spin.set_value(800)
    row = Gtk.Box(spacing=6)
    row.pack_start(custom, False, False, 0)
    row.pack_start(spin, False, False, 0)
    for w in (half, full_hd, small):
        box.pack_start(w, False, False, 0)
    box.pack_start(row, False, False, 0)
    dialog.show_all()
    response = dialog.run()
    choice = None
    if response == Gtk.ResponseType.OK:
        if half.get_active():
            choice = (None, 50)
        elif full_hd.get_active():
            choice = (1920, None)
        elif small.get_active():
            choice = (1024, None)
        else:
            choice = (spin.get_value_as_int(), None)
    dialog.destroy()
    return choice


def _window(action: str, jobs: list[tools.Job]) -> int:
    from gi.repository import GLib, Gtk

    win = Gtk.Window(title=TITLES[action], default_width=420)
    win.set_position(Gtk.WindowPosition.CENTER)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=16)
    status = Gtk.Label(xalign=0, wrap=True)
    bar = Gtk.ProgressBar()
    box.pack_start(status, False, False, 0)
    box.pack_start(bar, False, False, 0)
    close = Gtk.Button(label="Close", halign=Gtk.Align.END, sensitive=False)
    close.connect("clicked", lambda _b: win.destroy())
    box.pack_end(close, False, False, 0)
    win.add(box)
    win.connect("destroy", lambda _w: Gtk.main_quit())
    win.show_all()
    result = {"code": 0}

    def progress(i: int, job: tools.Job) -> None:
        def show() -> bool:
            status.set_text(f"{job.source[0].name} → {job.output.name}")
            bar.set_fraction(i / len(jobs))
            return False
        GLib.idle_add(show)

    def finished(done: list[Path], errors: list[str]) -> bool:
        bar.set_fraction(1.0)
        lines = []
        if done:
            names = ", ".join(p.name for p in done[:5]) + ("…" if len(done) > 5 else "")
            lines.append(f"Made {len(done)} new file{'s' if len(done) != 1 else ''}: {names}")
        if errors:
            result["code"] = 1
            lines.append("Could not convert:\n" + "\n".join(errors))
        status.set_text("\n\n".join(lines))
        close.set_sensitive(True)
        close.grab_focus()
        return False

    def work() -> None:
        done, errors = run_jobs(jobs, progress)
        GLib.idle_add(finished, done, errors)

    threading.Thread(target=work, daemon=True).start()
    Gtk.main()
    return result["code"]


def _show_error(message: str) -> None:
    from gi.repository import Gtk

    dialog = Gtk.MessageDialog(message_type=Gtk.MessageType.ERROR, buttons=Gtk.ButtonsType.CLOSE,
                               text="Can't do that")
    dialog.format_secondary_text(message)
    dialog.run()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tulsi-file-tools", description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=ACTIONS)
    parser.add_argument("files", nargs="+", type=Path)
    size = parser.add_mutually_exclusive_group()
    size.add_argument("--width", type=int)
    size.add_argument("--percent", type=int)
    parser.add_argument("--no-window", action="store_true", help="print instead of showing a window")
    args = parser.parse_args(argv)

    window = not args.no_window
    if window:
        import gi

        gi.require_version("Gtk", "3.0")
    width, percent = args.width, args.percent
    if args.action == "resize" and width is None and percent is None:
        if not window:
            parser.error("resize needs --width or --percent")
        chosen = _ask_size()
        if chosen is None:
            return 1
        width, percent = chosen
    try:
        jobs = jobs_for(args.action, [f.resolve() for f in args.files], width, percent)
    except tools.ToolError as e:
        if window:
            _show_error(str(e))
        else:
            print(f"tulsi-file-tools: {e}", file=sys.stderr)
        return 1
    if window:
        return _window(args.action, jobs)
    done, errors = run_jobs(jobs)
    for p in done:
        print(p)
    for e in errors:
        print(f"tulsi-file-tools: {e}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
