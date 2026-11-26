# ADR 0037: File actions in the file manager

Status: accepted (2026-11-26). Builds on ADR 0028 (agents see only what they are
given) and ADR 0032 (LocalSend).

## Context

People want to do small things with a file where they see it: ask what a file
is, send it to their phone, shrink a photo for email, turn a video into an MP3 or
a document into a PDF. On TulsiOS each needed a terminal or a separate app.

The Assistant could help, but its agent account sees none of the person's files
(ADR 0028), and giving it file access would be a large change in what agents may
do.

## Decision

New right-click actions in Nemo (Ocimum) and Ecco/Dolphin (SonicDE), from
`tulsi.fileActions` (`tulsi-file-tools`):

- **Explain with Assistant** (one text, PDF or office file):
  - `ocimum-assistant --explain FILE` runs as the person;
  - it reads the file's text (PDFs with pdftotext, office files with LibreOffice
    when installed), up to 40,000 characters, and asks about it in the chat, where
    the whole question can be seen;
  - the agent gets the text and nothing else: not the file, not its folder;
  - it refuses pictures and other binary files, and says why.
- **Send via LocalSend:** the selected files open in LocalSend, ready to send
  (LocalSend 1.18 takes files on its command line, also when it is already open).
- **Quick conversions,** each making **a new file beside the original**, never
  overwriting one ("photo (resized).jpg", then "photo (resized 2).jpg"):
  - Resize Images… (half size, 1920 or 1024 pixels wide, or a width; only ever
    smaller);
  - Convert to JPG / PNG, Combine into a PDF (ImageMagick);
  - Convert to MP3 (audio and video, ffmpeg);
  - Convert to PDF (documents, LibreOffice; shown only when it is installed).
  They are plain programs, not an agent: nothing to approve and nothing to log, and
  the original stays as it was.

**Not now:** an agent changing files itself. That needs file tools in tulsi-mcp
under Starah (a copy in the same folder, asked per change, logged, undone through
the trash) and gets its own ADR.

## Consequences

- Asking about a file shares its text with the Assistant's AI provider, as typing
  it would; the chat shows exactly what was sent.
- The Explain action hides itself when the Assistant isn't installed, and so do
  the LocalSend and document actions without LocalSend or LibreOffice (in Nemo;
  Dolphin shows them and the tool explains what's missing).
- dwm has no file manager, so it has no actions; `tulsi-file-tools` works from a
  terminal there too.
- `checks.file-actions` resizes and converts real files and checks the originals
  stay; the Assistant's unit tests cover reading, cutting and refusing files.
