# Shelfmark

> *shelfmark (n.)* — the call number a librarian writes on a book to give it
> its place on the shelf.

**Shelfmark** is a console tool that reads a document, works out its *title*
and *author*, and renames the file into something a human would recognise:

```
29623753.pdf                    ->  David Knickerbocker - Network Science with Python [2023].pdf
43b2956cd82bc62159778acf….pdf   ->  Артур Думчев - ПОМНИТЬ ВСЕ ПРАКТИЧЕСКОЕ РУКОВОДСТВО ПО РАЗВИТИЮ ПАМЯТИ [2013].pdf
345852.fb2                      ->  Штюрмер Ю. А. - Карманный справочник туриста.fb2
```

It works **fully offline** — no LLM, no external services. Just heuristics
over file metadata, the text layer, and OCR for scans.

## Supported formats

| Format | Metadata | Text | OCR |
|--------|----------|------|-----|
| PDF    | pdfinfo | pdftotext (poppler) | pdftoppm + tesseract |
| EPUB   | package.opf (dc:title, dc:creator, dc:date) | – | – |
| FB2    | title-info (book-title, author, date) | – | – |
| MOBI   | PalmDB + EXTH (title, author, date) | – | – |
| DJVU   | ANTa annotations (title, author) | djvutxt (djvulibre) | ddjvu + tesseract |
| DOCX   | docProps/core.xml | first paragraphs | – |

**Files without an extension** (hash-named downloads) are recognised by their
signature — magic bytes for PDF/DjVu/MOBI, the container structure for
EPUB/DOCX, the `FictionBook` root for FB2 — and the renamed file gets the
proper extension. The same works for files with a wrong or unknown extension.

## Requirements

* Python ≥ 3.10, standard library only;
* for PDF: `poppler-utils` (`pdfinfo`, `pdftotext`, `pdftoppm`);
* for scans (optional): `tesseract` with `rus+eng` language packs;
* for DjVu (optional): `djvulibre` tools (`djvutxt`, `ddjvu`) — without them
  DjVu text/OCR is unavailable (annotations ANTa are still read).

```bash
# Debian/Ubuntu
sudo apt install poppler-utils tesseract-ocr tesseract-ocr-rus tesseract-ocr-eng djvulibre-bin
```

## Install & run

```bash
# 1. straight from the source tree, no installation
cd shelfmark
python3 -m shelfmark --help

# 2. user install — the `shelfmark` command works from anywhere
pip install --user .
shelfmark --help

# 3. editable install for development (source edits apply immediately)
pip install --user -e .
```

After `pip install --user` the command lands in `~/.local/bin`
(make sure it is on your `PATH`). If you edit the project sources, either run
from the project folder or reinstall — the editable install (`-e`) picks up
changes without reinstalling.

## Usage

```bash
shelfmark book.pdf                   # show the plan (files are NOT touched)
shelfmark --apply book.pdf           # rename the file
shelfmark -r ~/Downloads             # plan for a whole folder, recursively
shelfmark --apply -r ~/Downloads     # rename everything in the folder
shelfmark --report plan.csv -r .     # save the plan as CSV
shelfmark --force-ocr book.pdf       # re-check a PDF whose text layer is broken
shelfmark --ai book.pdf              # let a vision LLM read the cover
shelfmark --title-from-text book.pdf # title = whole page text, fragments joined
shelfmark -n "{title}-{year}" book.pdf # custom name pattern
shelfmark -v book.pdf                # debug: title candidates, text snippet
```

### Options

| Option | Description |
|--------|-------------|
| `paths` | file(s) or folder(s) to process |
| `-a, --apply` | actually rename; **without this flag the tool only shows a plan (dry-run)** |
| `-r, --recursive` | walk folders recursively |
| `-n, --naming-template PATTERN` | name pattern with `{author}`, `{title}`, `{year}` placeholders; the extension is appended automatically (default: `{author} - {title} [{year}]`) |
| `--no-ocr` | never OCR scanned pages (faster) |
| `--force-ocr` | always OCR the leading pages and use that text instead of the built-in text layer (for PDFs with a broken encoding) |
| `--ocr-pages N` | how many leading pages to OCR (default: 2) |
| `--no-year` | do not append the year to file names |
| `--title-from-text` | build the title from the **whole** page text without special characters (title fragments are joined), instead of picking single candidate lines |
| `--title-pages N` | how many leading pages to take for `--title-from-text` (default: 1) |
| `--report CSV` | write a report: old name, new name, source, status |
| `-v, --verbose` | show title candidates and warnings |
| `-q, --quiet` | print only the summary |

### AI options (vision LLM, opt-in)

| Option | Description |
|--------|-------------|
| `--ai` | ask a vision LLM to read the cover; its answer outranks the heuristics |
| `--ai-url URL` | OpenAI-compatible endpoint (default `https://api.openai.com/v1`; Ollama: `http://localhost:11434/v1`) |
| `--ai-model MODEL` | model name (default `gpt-4o-mini`; Ollama: `moondream`, `llava`, `llama3.2-vision`) |
| `--ai-key KEY` | API key (or env `SHELFMARK_AI_KEY`; not needed for local Ollama) |
| `--ai-timeout SEC` | request timeout (default 60) |

Environment variables: `SHELFMARK_AI_URL`, `SHELFMARK_AI_MODEL`, `SHELFMARK_AI_KEY`.

The AI is used **only when `--ai` is passed**. Shelfmark renders the first page
to PNG, shows it to the model together with the heuristic candidates, and gets
back strict JSON `{"title", "author", "year"}`. If the model is unreachable or
answers oddly, the heuristic result is kept and a warning is printed.

```bash
# cloud (OpenAI, DeepSeek, GigaChat, YandexGPT, … — any compatible API)
export SHELFMARK_AI_KEY=sk-...
shelfmark --ai book.pdf

# local Ollama, fully offline
shelfmark --ai --ai-url http://localhost:11434/v1 --ai-model moondream book.pdf
```

## How the name is chosen

By default the name follows the pattern **`Author - Title [year].ext`**
(just `Title [year].ext` when no author is found). The pattern is
customizable: `--naming-template "{author} - {title}"`, `"{title}-{year}"`,
`"{year}_{title}"` — empty values are dropped together with their separators,
and the file extension is always appended automatically.

Sources are tried from most to least reliable:

1. **File metadata** — Title/Author/date. Junk values (`Microsoft Word - …`,
   `Layout 1`, `Pamyat_text 02.indd`, hashes, upload ids) are discarded;
2. **Text layer of the leading pages** — lines are scored by casing
   (ALL CAPS / Title Case), position on the page, length and punctuation.
   Service lines (ISBN, UDC, running heads, URLs), publisher imprints
   («Москва · Санкт-Петербург», «O'Reilly cities»), section headings
   («Table of Contents», «Preface») and name-like lines are rejected;
   subtitle lines are merged into the title;
3. **OCR of the leading pages** — when there is no text layer (a scan) or
   it is broken: mojibake from exotic font encodings, split words
   («W ICKED COOL», «SHELL SCRIP T S»);
4. **The original file name** — used when the other sources produced only a
   fragment («ВЕСЬ» of «Весь Linux…»), a cipher («М. МЦНМО, 2016»), a broken
   bibliographic line or a bad OCR guess. Names like `Author - Title`,
   `Title (Author)` and `03_Title_by_Author` are parsed apart.

Telling a short author name from a short title (both may be set in caps:
`АРТУР ДУМЧЕВ` vs `DARK MATTER`) is done with a compact dictionary of common
Russian/English first names and their transliterations
(`shelfmark/names.py`) — easy to extend.

Name lines in the forms «Surname F. M.», «F. M. Surname», «Surname, Name»
and «by Jane Smith» are recognised by pattern. ALL-CAPS names are normalised
(`АРТУР ДУМЧЕВ` → `Артур Думчев`), and service words («And Unix Systems»)
never count as a person's name.

## Safety

* **nothing is renamed by default** — the tool prints a plan first;
* name collisions are resolved with ` (2)`, ` (3)` suffixes;
* the file extension is preserved, forbidden characters become spaces;
* names are capped at 200 **bytes** (the FS limit is 255 bytes per path
  component, and Cyrillic takes 2 bytes per character), cut at a word
  boundary with `…`;
* the year is appended only when it was found in metadata or in the
  original file name.

## Tests

```bash
python3 -m unittest discover -s tests
```

128 tests: title/author heuristics, text cleaning, mojibake detection,
file-name building, file-name parsing, synthetic files for every supported
format, and rename scenarios.

## Project layout

```
shelfmark/
├── shelfmark/
│   ├── cli.py               # command line, plan output
│   ├── renamer.py           # rename planning and execution
│   ├── titlefinder.py       # heuristics: title and author from text
│   ├── names.py             # name dictionary: "author" vs "title"
│   ├── textclean.py         # string cleanup, mojibake detection
│   ├── naming.py            # file-name building, limits, collisions
│   ├── ocr.py               # OCR of leading pages (pdftoppm + tesseract)
│   ├── signature.py         # format detection by signature (extensionless files)
│   ├── ai.py                # vision LLM cover recognition (--ai, OpenAI-compatible)
│   ├── models.py            # DocumentInfo, Source, TextQuality
│   └── extractors/          # PDF, EPUB, FB2, MOBI, DJVU, DOCX
├── tests/
├── pyproject.toml
├── README.md                # this file
└── README.ru.md             # Russian documentation
```

## Author

**Sergei Korneev (AI coded)** — version 1.1.0 (`shelfmark --version`).
