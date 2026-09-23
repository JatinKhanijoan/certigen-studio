# CertiGen

CertiGen creates personalized certificates in batches from a certificate
template and a recipient list. Its Streamlit editor lets you position and style
recipient names on a clean template, preview the result, and export certificates
as PNG, JPEG, or PDF files. Python and command-line interfaces are also
available.

This repository extends the upstream CertiGen project with the Streamlit
editor and clean-template workflow while retaining its package and
command-line interfaces. Upstream project metadata, history, and licensing
are retained; see [Licensing and attribution](#licensing-and-attribution).

## Features

- Clean-template Streamlit editor with a live recipient name.
- Drag, resize, keyboard nudge, zoom, center snapping, undo, and redo.
- Exact left, top, width, and height controls in source-image pixels.
- Optional TTF or OTF font upload, font-size control, and text-color control.
- Production preview and ZIP generation from the same placement state.
- Python API and command-line workflow for templates that already contain a
  detectable placeholder.
- PNG, JPEG, PDF, and ZIP output.

## Streamlit app

### Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\run_webapp.ps1
```

The launcher uses the project virtual environment. The app entrypoint is
`webapp/app.py`.

Upload:

1. A PNG or JPEG certificate template without a sample name.
2. A CSV with either two columns (first and last name) or three columns
   (first, middle, and last name). The editor detects the column count and
   lets you map each name part to its column.

The editor uses the first recipient as the live sample. You can change the
sample recipient before exporting. The original template pixels are preserved;
the app draws the recipient name on top of them.

### Deploy on Streamlit Community Cloud

1. Push the repository to a GitHub account you control.
2. Open [Streamlit Community Cloud](https://share.streamlit.io/) and choose
   **New app**.
3. Select the repository, branch, and `webapp/app.py` as the entrypoint.
4. Deploy. Streamlit Cloud installs the dependencies listed in
   `requirements.txt`.

The repository includes `.python-version` with Python 3.11. The app does not
require secrets or API keys.

## Python package

Install the package from a checkout:

```bash
pip install .
```

The package API expects a template, a names file, a name column, and a font:

```python
from certigen import CertificateGenerator

generator = CertificateGenerator(
    template_path="template.png",
    excel_path="names.xlsx",
    name_column="Name",
    font_path="OpenSans-VariableFont_wdth,wght.ttf",
    placeholder="John Doe",
    output_dir="output",
)

generator.generate_all()
generator.export_as_pdf()
generator.zip_certificates()
```

The Python API can use OCR to locate the placeholder text. The Streamlit app
uses its clean-template placement workflow and does not require placeholder
text in the uploaded artwork.

## Command line

```bash
certigen -t template.png -e names.xlsx -f arial.ttf
certigen -t template.png -e names.xlsx -f arial.ttf -p "John Doe" --pdf --zip
certigen -t template.png --find-coords
```

## Input and output responsibilities

You are responsible for having permission to use every template image, font,
logo, photograph, name list, and other material you upload or redistribute.
Generated certificates inherit any restrictions attached to those materials.
CertiGen does not grant rights to third-party artwork, fonts, trademarks, or
personal data.

Do not commit recipient lists, credentials, private templates, or generated
certificates to a public repository. The Streamlit app processes uploads in its
runtime workspace and does not require a cloud storage account.

## Licensing and attribution

The upstream project's MIT License and copyright notice are in
[`LICENSE`](LICENSE). Keep that notice and license text with copies or
substantial portions of the source code. The MIT License permits modification
and redistribution subject to its conditions; it does not transfer authorship
or ownership of the original project.

Third-party materials are governed by their own terms:

- `examples/OpenSans-VariableFont_wdth,wght.ttf` is Open Sans, licensed under
  the [SIL Open Font License 1.1](https://scripts.sil.org/OFL). The font's
  embedded metadata identifies the Open Sans Project Authors and its source.
- Python dependencies listed in `requirements.txt` retain their respective
  copyright notices and licenses. Consult each installed distribution before
  redistributing a bundled environment.
- `examples/template.png` and `examples/name.xlsx` are demonstration assets.
  Verify their provenance and permissions before using or redistributing them.

The MIT license for the CertiGen source code does not relicense the Open Sans
font, dependencies, or example assets.

## Development

```powershell
.\.venv\Scripts\python.exe -m py_compile webapp\app.py webapp\selection_box.py certigen\generator.py
```

The local app can be started with `run_webapp.ps1`.
