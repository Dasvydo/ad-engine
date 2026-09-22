# md_to_pdf

Renders a repo markdown doc to a typeset A4 PDF.

```bash
python tools/md_to_pdf.py docs/META-ADS-CHEATSHEET.md -o build/cheatsheet.pdf \
  --footer "DoviLoop - Meta Ads cheat sheet"
```

**The markdown is canonical.** The PDF is derived and is not committed
(`build/` is gitignored). Edit the markdown, rebuild, re-send.

Build instructions deliberately live here and not inside the documents
themselves: a note like this at the foot of a three-page cheat sheet spills onto
a fourth, nearly empty page, and it is addressed to whoever maintains the repo
rather than to whoever reads the sheet.

Supported markdown: headings, pipe tables (a `| | |` header makes a headless
layout table), bullets, `- [ ]` checkboxes, numbered lists, fenced code,
blockquotes and `⚠` lines (both render as callouts), `---` rules, `**bold**`,
`*italic*` and `` `code` ``. A table whose header contains **Bad** and **Good**
gets those columns colour-coded.

Requires `reportlab` and the DejaVu fonts in `/usr/share/fonts/truetype/dejavu`.
Tests: `tests/test_md_to_pdf.py`.
