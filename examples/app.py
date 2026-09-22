"""
Test file for certigen package
"""

from certigen import CertificateGenerator

# Create generator
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

# Optional: create PDF and ZIP
# gen.export_as_pdf()
# gen.zip_certificates()
