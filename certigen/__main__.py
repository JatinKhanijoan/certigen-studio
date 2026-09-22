"""
Command-line interface for CertiGen
"""

import argparse
from .generator import CertificateGenerator
from .utils import find_coordinates


def main():
    parser = argparse.ArgumentParser(
        prog="certigen",
        description="Generate certificates by replacing placeholder text with names"
    )
    parser.add_argument("--template", "-t", required=True, help="Template image path")
    parser.add_argument("--excel", "-e", required=True, help="Excel/CSV file with names")
    parser.add_argument("--column", "-c", default="Name", help="Column name for names")
    parser.add_argument("--font", "-f", required=True, help="Font file path (.ttf)")
    parser.add_argument("--output", "-o", default="output", help="Output directory")
    parser.add_argument("--placeholder", "-p", default="John Doe", help="Placeholder text to find")
    parser.add_argument("--font-color", help="Font color as R,G,B (e.g., 0,0,0)")
    parser.add_argument("--bg-color", help="Background color as R,G,B")
    parser.add_argument("--position", help="Manual position as X,Y")
    parser.add_argument("--max-width", type=int, help="Max text width in pixels")
    parser.add_argument("--font-size", type=int, default=180, help="Base font size")
    parser.add_argument("--min-font-size", type=int, default=60, help="Minimum font size")
    parser.add_argument("--tesseract", help="Path to Tesseract executable")
    parser.add_argument("--zip", action="store_true", help="Create ZIP file")
    parser.add_argument("--pdf", action="store_true", help="Create PDF")
    parser.add_argument("--find-coords", action="store_true", help="Interactive coordinate finder")
    parser.add_argument("--quiet", "-q", action="store_true", help="Suppress output")
    
    args = parser.parse_args()
    
    if args.find_coords:
        find_coordinates(args.template)
        return
    
    font_color = tuple(map(int, args.font_color.split(','))) if args.font_color else None
    bg_color = tuple(map(int, args.bg_color.split(','))) if args.bg_color else None
    position = tuple(map(int, args.position.split(','))) if args.position else None
    
    generator = CertificateGenerator(
        template_path=args.template,
        excel_path=args.excel,
        name_column=args.column,
        font_path=args.font,
        output_dir=args.output,
        placeholder=args.placeholder,
        font_color=font_color,
        bg_color=bg_color,
        manual_position=position,
        max_text_width=args.max_width,
        base_font_size=args.font_size,
        min_font_size=args.min_font_size,
        tesseract_path=args.tesseract,
        verbose=not args.quiet,
    )
    
    generator.generate_all()
    
    if args.zip:
        generator.zip_certificates()
    if args.pdf:
        generator.export_as_pdf()


if __name__ == "__main__":
    main()
