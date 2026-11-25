"""Completion: nixd's suggestions, and the guide's snippets (ADR 0019)."""

from __future__ import annotations

import re

import gi

gi.require_version("GtkSource", "4")
from gi.repository import GObject, GtkSource  # noqa: E402

from .text import indent_snippet, typed_prefix  # noqa: E402

MAX_ITEMS = 200
SNIPPET_INFO = "From the guide: "



class NixCompletion(GObject.Object, GtkSource.CompletionProvider):
    """`window` gives `lsp_ready()`, `request_completion(view, line, char16, cb)`,
    `guide` and `log`."""

    def __init__(self, window):
        super().__init__()
        self.window = window

    def do_get_name(self) -> str:
        return "Nix"

    def do_get_priority(self) -> int:
        return 10

    def do_get_activation(self):
        return GtkSource.CompletionActivation.INTERACTIVE | GtkSource.CompletionActivation.USER_REQUESTED

    def do_get_interactive_delay(self) -> int:
        return 300

    def _iter(self, context):
        got = context.get_iter()
        return got[1] if isinstance(got, tuple) else got

    def do_match(self, context) -> bool:
        it = self._iter(context)
        if context.get_activation() == GtkSource.CompletionActivation.USER_REQUESTED:
            return True
        start = it.copy()
        start.set_line_offset(0)
        before = start.get_text(it)
        # As you type: after two letters of a name, or right after a dot.
        return len(typed_prefix(before)) >= 2 or before.endswith(".")

    def do_populate(self, context) -> None:
        it = self._iter(context)
        start = it.copy()
        start.set_line_offset(0)
        before = start.get_text(it)
        prefix = typed_prefix(before)
        snippets = []
        for key, entry in self.window.guide.snippets(prefix):
            item = GtkSource.CompletionItem()
            item.set_label(f"{key} {{ … }}")
            item.set_text(entry.snippet)
            item.set_info(f"{SNIPPET_INFO}{entry.title}")
            snippets.append(item)

        if not self.window.lsp_ready():
            context.add_proposals(self, snippets, True)
            return

        cancelled = {"yes": False}
        context.connect("cancelled", lambda _c: cancelled.update(yes=True))

        def got(items: list[dict]) -> None:
            if cancelled["yes"]:
                return
            props = list(snippets)
            for i in items:
                if prefix and not i["label"].startswith(prefix):
                    continue
                item = GtkSource.CompletionItem()
                item.set_label(i["label"])
                item.set_text(i["text"])
                info = "\n\n".join(x for x in (i["detail"], i["doc"]) if x)
                if info:
                    item.set_info(info)
                props.append(item)
                if len(props) >= MAX_ITEMS:
                    break
            names = [p.get_label() for p in props[:60]]
            self.window.log(f"completion: {len(props)} items for {prefix!r}: {', '.join(names)}")
            try:
                context.add_proposals(self, props, True)
            except Exception:  # noqa: BLE001 - the popup closed meanwhile
                pass

        self.window.request_completion(it.get_line(), before, got)

    def do_activate_proposal(self, proposal, it) -> bool:
        buffer = it.get_buffer()
        start = it.copy()
        start.set_line_offset(0)
        before = start.get_text(it)
        prefix = typed_prefix(before)
        begin = it.copy()
        begin.backward_chars(len(prefix))
        text = proposal.get_text() or proposal.get_label()
        if (proposal.get_info() or "").startswith(SNIPPET_INFO):
            indent = re.match(r"\s*", before).group(0)
            text = indent_snippet(text, indent)
        buffer.begin_user_action()
        buffer.delete(begin, it)
        buffer.insert(begin, text)
        buffer.end_user_action()
        return True
