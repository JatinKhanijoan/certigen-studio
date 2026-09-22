# Certigen Examples

Test files for the certigen package.

## Files

- `template.png` - Sample certificate template with "John Doe" placeholder
- `name.xlsx` - Excel file with sample names
- `OpenSans-VariableFont_wdth,wght.ttf` - Font file
- `app.py` - Example usage script

## Quick Start

1. Install the package:
```bash
pip install certigen
```

No additional setup needed! OCR works out of the box.

2. Run from this directory:
```bash
cd examples
python app.py
```

3. Check the `output/` folder for generated certificates.

## Example Code

```python
from certigen import CertificateGenerator

gen = CertificateGenerator(
    template_path="template.png",
    excel_path="name.xlsx",
    name_column="Name",
    font_path="OpenSans-VariableFont_wdth,wght.ttf",
    placeholder="John Doe",
    output_dir="output"
)

# Generate all certificates
gen.generate_all()

# Optional exports
gen.export_as_pdf()
gen.zip_certificates()
```

## Parameters

| Parameter | Description |
|-----------|-------------|
| `template_path` | Path to certificate template image |
| `excel_path` | Path to Excel/CSV file with names |
| `name_column` | Column name containing the names |
| `font_path` | Path to .ttf font file |
| `placeholder` | Text to find and replace (e.g., "John Doe") |
| `output_dir` | Directory for generated certificates |
| `font_color` | Optional RGB tuple for text color (auto-detected) |
| `bg_color` | Optional RGB tuple for background (auto-detected) |
| `manual_position` | Optional (x, y) to override OCR detection |
| `base_font_size` | Starting font size (default: 180) |
| `min_font_size` | Minimum font size for long names (default: 60) |

## Notes

- OCR automatically detects the placeholder position and text color
- If OCR fails, use `manual_position=(x, y)` to specify coordinates
- Long names are automatically scaled down to fit
