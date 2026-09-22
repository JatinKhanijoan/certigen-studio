"""
Certificate Generator - Uses RapidOCR for placeholder detection
RapidOCR is lightweight (~15MB), works offline, no external dependencies.
Just: pip install rapidocr-onnxruntime
"""

from PIL import Image, ImageDraw, ImageFont
import pandas as pd
import numpy as np
import os
import zipfile
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from dataclasses import dataclass
from typing import Optional, Tuple, List
import re
from pathlib import Path

try:
    from rapidocr_onnxruntime import RapidOCR
    HAS_OCR = True
except ImportError:
    HAS_OCR = False

# Lazy load OCR engine
_ocr_engine = None

def get_ocr():
    global _ocr_engine
    if _ocr_engine is None and HAS_OCR:
        _ocr_engine = RapidOCR()
    return _ocr_engine


@dataclass
class TextRegion:
    """Detected text region with position and color info"""
    x: int  # center x
    y: int  # center y
    width: int  # max width for text
    height: int
    text_color: Tuple[int, int, int]
    bg_color: Tuple[int, int, int]
    detected_font_size: Optional[int] = None
    placeholder_box: Optional[Tuple[int, int, int, int]] = None  # (x1, y1, x2, y2)


class CertificateGenerator:
    def __init__(
        self,
        template_path: str,
        excel_path: str,
        name_column: str,
        font_path: str,
        output_dir: str = "output",
        placeholder: str = "John Doe",
        font_color: Optional[Tuple[int, int, int]] = None,
        bg_color: Optional[Tuple[int, int, int]] = None,
        base_font_size: int = 180,
        min_font_size: int = 60,
        manual_position: Optional[Tuple[int, int]] = None,
        max_text_width: Optional[int] = None,
    ):
        self.template_path = template_path
        self.excel_path = excel_path
        self.name_column = name_column
        self.font_path = font_path
        self.output_dir = output_dir
        self.placeholder = placeholder
        self.user_font_color = font_color
        self.user_bg_color = bg_color
        self.base_font_size = base_font_size
        self.min_font_size = min_font_size
        self.manual_position = manual_position
        self.max_text_width = max_text_width
        
        # Load template and names
        self.template = Image.open(template_path).convert("RGB")
        self.names = self._load_names()
        
        # Detect placeholder position and colors
        self.text_region = self._detect_placeholder()
        
        os.makedirs(output_dir, exist_ok=True)
        
        print(f"\n[Position] ({self.text_region.x}, {self.text_region.y})")
        print(f"[Text color] {self.text_region.text_color}")
        print(f"[Background] {self.text_region.bg_color}")
        print(f"[Max width] {self.text_region.width}px")
        print(f"[Font size] {self.text_region.detected_font_size or self.base_font_size}px")
        if self.text_region.placeholder_box:
            print(f"[Placeholder box] {self.text_region.placeholder_box}")
        print()

    def _load_names(self) -> List[str]:
        """Load names from Excel file"""
        df = pd.read_excel(self.excel_path)
        return [str(name).strip() for name in df[self.name_column] if pd.notna(name)]

    def _detect_placeholder(self) -> TextRegion:
        """
        Find placeholder using RapidOCR (lightweight, offline, no external deps).
        """
        img_array = np.array(self.template)
        height, width = img_array.shape[:2]
        
        # Defaults
        detected_x, detected_y = width // 2, height // 2
        detected_width = int(width * 0.6)
        detected_height = 100
        detected_font_size = None
        placeholder_box = None
        
        ocr = get_ocr()
        if ocr is not None and self.manual_position is None:
            try:
                print("Searching for placeholder with OCR...")
                
                # RapidOCR returns: (result, elapse)
                # result is list of [bbox, text, confidence]
                # bbox is [[x1,y1], [x2,y1], [x2,y2], [x1,y2]]
                result, _ = ocr(img_array)
                
                if result:
                    placeholder_words = self.placeholder.lower().split()
                    matching_boxes = []
                    
                    for item in result:
                        bbox, text, conf = item
                        text_lower = text.strip().lower()
                        
                        # Check if any placeholder word matches
                        for word in placeholder_words:
                            if word in text_lower or text_lower in word:
                                x1 = int(min(p[0] for p in bbox))
                                y1 = int(min(p[1] for p in bbox))
                                x2 = int(max(p[0] for p in bbox))
                                y2 = int(max(p[1] for p in bbox))
                                matching_boxes.append((x1, y1, x2, y2, text))
                                break
                    
                    if matching_boxes:
                        # Combine all matching boxes
                        x_min = min(b[0] for b in matching_boxes)
                        y_min = min(b[1] for b in matching_boxes)
                        x_max = max(b[2] for b in matching_boxes)
                        y_max = max(b[3] for b in matching_boxes)
                        
                        placeholder_box = (x_min, y_min, x_max, y_max)
                        detected_x = (x_min + x_max) // 2
                        detected_y = (y_min + y_max) // 2
                        detected_width = max(x_max - x_min, int(width * 0.4))
                        detected_height = y_max - y_min
                        
                        # Estimate font size
                        detected_font_size = self._estimate_font_size(
                            self.placeholder, x_max - x_min
                        )
                        
                        matched = [b[4] for b in matching_boxes]
                        print(f"Found '{self.placeholder}' -> {matched}")
                        print(f"   Box: ({x_min}, {y_min}) to ({x_max}, {y_max})")
                    else:
                        print(f"Placeholder '{self.placeholder}' not found, using center")
                else:
                    print("No text detected, using center")
                    
            except Exception as e:
                print(f"OCR failed: {e}")
        elif ocr is None and self.manual_position is None:
            print("rapidocr-onnxruntime not installed - using center")
            print("   Tip: pip install rapidocr-onnxruntime")
        
        if self.manual_position:
            detected_x, detected_y = self.manual_position
            print(f"Using manual position: ({detected_x}, {detected_y})")
        
        if self.max_text_width:
            detected_width = self.max_text_width
        
        # Get colors
        text_color, bg_color = self._extract_colors(
            detected_x, detected_y, detected_width, detected_height
        )
        
        if self.user_font_color:
            text_color = self.user_font_color
        if self.user_bg_color:
            bg_color = self.user_bg_color
        
        return TextRegion(
            x=detected_x, y=detected_y, width=detected_width, height=detected_height,
            text_color=text_color, bg_color=bg_color,
            detected_font_size=detected_font_size, placeholder_box=placeholder_box
        )

    def _estimate_font_size(self, text: str, target_width: int) -> int:
        """Estimate font size to match target width"""
        for size in range(20, 300, 2):
            font = ImageFont.truetype(self.font_path, size)
            bbox = font.getbbox(text)
            if bbox[2] - bbox[0] >= target_width:
                return size
        return 100

    def _extract_colors(self, cx: int, cy: int, w: int, h: int) -> Tuple[Tuple[int, int, int], Tuple[int, int, int]]:
        """Extract text and background colors from region"""
        img_array = np.array(self.template)
        img_h, img_w = img_array.shape[:2]
        
        x1 = max(0, cx - w // 2)
        x2 = min(img_w, cx + w // 2)
        y1 = max(0, cy - h)
        y2 = min(img_h, cy + h)
        
        region = img_array[y1:y2, x1:x2]
        pixels = region.reshape(-1, 3)
        unique_colors, counts = np.unique(pixels, axis=0, return_counts=True)
        sorted_idx = np.argsort(-counts)
        
        bg_color = tuple(int(x) for x in unique_colors[sorted_idx[0]])
        bg_array = np.array(bg_color)
        
        best_text_color = (0, 0, 0)
        best_dist = 0
        
        for idx in sorted_idx[:20]:
            color = unique_colors[idx]
            dist = np.sqrt(np.sum((color - bg_array) ** 2))
            if dist > best_dist and dist > 30:
                best_dist = dist
                best_text_color = tuple(int(x) for x in color)
        
        if best_dist < 30:
            brightness = sum(bg_color) / 3
            best_text_color = (0, 0, 0) if brightness > 128 else (255, 255, 255)
        
        return best_text_color, bg_color

    def _calculate_font_size(self, name: str, max_width: int) -> int:
        """Calculate font size to fit name within max width"""
        base = self.text_region.detected_font_size or self.base_font_size
        
        for size in range(base + 20, self.min_font_size - 1, -1):
            font = ImageFont.truetype(self.font_path, size)
            bbox = font.getbbox(name)
            if bbox[2] - bbox[0] <= max_width:
                return size
        return self.min_font_size

    def _generate_single(self, name: str, index: int) -> str:
        """Generate a single certificate"""
        img = self.template.copy()
        draw = ImageDraw.Draw(img)
        img_w, img_h = img.size
        
        font_size = self._calculate_font_size(name, self.text_region.width)
        font = ImageFont.truetype(self.font_path, font_size)
        
        bbox = draw.textbbox((0, 0), name, font=font, anchor="lt")
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        
        if self.text_region.placeholder_box:
            px1, py1, px2, py2 = self.text_region.placeholder_box
            start_x = px1
            center_y = (py1 + py2) // 2
        else:
            start_x = self.text_region.x - (text_w // 2)
            center_y = self.text_region.y
        
        # Clear placeholder area
        if self.text_region.placeholder_box:
            px1, py1, px2, py2 = self.text_region.placeholder_box
            draw.rectangle([px1 - 25, py1 - 25, px2 + 25, py2 + 25], fill=self.text_region.bg_color)
        
        # Clear new text area
        half_h = text_h // 2
        draw.rectangle(
            [max(0, start_x - 10), max(0, center_y - half_h - 10),
             min(img_w, start_x + text_w + 10), min(img_h, center_y + half_h + 10)],
            fill=self.text_region.bg_color
        )
        
        # Boundary check
        if start_x < 10:
            start_x = 10
        if start_x + text_w > img_w - 10:
            start_x = img_w - 10 - text_w
        
        draw.text((start_x, center_y), name, fill=self.text_region.text_color, font=font, anchor="lm")
        
        safe_name = re.sub(r'[^\w\s-]', '', name).replace(" ", "_")
        output_path = os.path.join(self.output_dir, f"{safe_name}_certificate.png")
        img.save(output_path, "PNG", quality=95)
        
        print(f"[{index}/{len(self.names)}] {safe_name}_certificate.png")
        return output_path

    def generate_all(self) -> List[str]:
        """Generate certificates for all names"""
        paths = []
        for idx, name in enumerate(self.names, 1):
            paths.append(self._generate_single(name, idx))
        print(f"\nGenerated {len(paths)} certificates in '{self.output_dir}'")
        return paths

    def export_as_pdf(self, output_name: str = "certificates.pdf") -> str:
        """Combine all PNGs to a single PDF"""
        png_files = sorted(Path(self.output_dir).glob("*_certificate.png"))
        if not png_files:
            raise ValueError("No certificates found. Run generate_all() first.")
        
        images = [Image.open(f).convert("RGB") for f in png_files]
        pdf_path = os.path.join(self.output_dir, output_name)
        images[0].save(pdf_path, "PDF", save_all=True, append_images=images[1:])
        print(f"PDF created: {pdf_path}")
        return pdf_path

    def zip_certificates(self, output_name: str = "certificates.zip") -> str:
        """Zip all certificates"""
        zip_path = os.path.join(self.output_dir, output_name)
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for f in Path(self.output_dir).glob("*_certificate.png"):
                zf.write(f, f.name)
        print(f"Zipped: {zip_path}")
        return zip_path



# ---- CLI ----
if __name__ == "__main__":
    generator = CertificateGenerator(
        template_path="examples/template.png",
        excel_path="examples/name.xlsx",
        name_column="Name",
        font_path="examples/OpenSans-VariableFont_wdth,wght.ttf",
        output_dir="output",
        placeholder="John Doe",
    )
    generator.generate_all()
