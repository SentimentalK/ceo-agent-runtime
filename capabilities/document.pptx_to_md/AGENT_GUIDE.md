# document.pptx_to_md

Converts PPTX files to Markdown. It gets text, tables, chart text, speaker notes, and text in images (local OCR).

## Run

```bash
capabilities/document.pptx_to_md/run "<FILE_OR_DIR>" [-o <OUTPUT_FILE_OR_DIR>] [--no-ocr]
```

Other options: `--confidence <0-1>` (OCR threshold, default 0.55), `--no-dedup`, `--keep-footers`.

## Output

- With `-o`: the Markdown file, or `<name>.md` in the `-o` folder.
- Without `-o`: `output/<name>.md` next to the input file.

## Rules

1. If the command says that the Python environment is missing, run `capabilities/document.pptx_to_md/setup`.
2. If the exit code is not 0, read the `ERROR` lines in the output. Report them.
