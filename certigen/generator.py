"""
Certificate Generator - Core module with OCR-based placeholder detection
Uses RapidOCR (lightweight, offline, no external dependencies)
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
    import cv2
except ImportError:
    cv2 = None

try:
    from rapidocr_onnxruntime import RapidOCR
    HAS_OCR = True
except ImportError:
    HAS_OCR = False

# Lazy load OCR engine
_ocr_engine = None

def _get_ocr():
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
    placeholder_found: bool = False
    anchor_line: Optional[Tuple[int, int, int, int]] = None  # underline (x1, y1, x2, y2)
    center_text: bool = False
    box_left: Optional[int] = None  # exact editor box origin (avoids odd-size rounding)
    box_top: Optional[int] = None
    text_align: str = "center"


class CertificateGenerator:
    """
    Generate certificates by replacing placeholder text with names from Excel/CSV.
    
    Features:
    - OCR-based automatic placeholder detection (using RapidOCR - no external deps)
    - Auto-detect font color and background color
    - Auto-resize text for long names
    - Export to PNG, PDF, or ZIP
    - Upload to S3 or Google Drive
    
    Example:
        >>> from certigen import CertificateGenerator
        >>> gen = CertificateGenerator(
        ...     template_path="template.png",
        ...     excel_path="names.xlsx",
        ...     name_column="Name",
        ...     font_path="arial.ttf",
        ...     placeholder="John Doe"
        ... )
        >>> gen.generate_all()
    """
    
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
        verbose: bool = True,
    ):
        """
        Initialize the certificate generator.
        
        Args:
            template_path: Path to certificate template image
            excel_path: Path to Excel/CSV file with names
            name_column: Column name containing the names
            font_path: Path to .ttf font file
            output_dir: Directory for generated certificates
            placeholder: Text to find and replace (e.g., "John Doe")
            font_color: RGB tuple for text color (auto-detected if None)
            bg_color: RGB tuple for background color (auto-detected if None)
            base_font_size: Starting font size for text
            min_font_size: Minimum font size for long names
            manual_position: (x, y) tuple to override OCR detection
            max_text_width: Maximum width for text in pixels
            verbose: Print progress messages
        """
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
        self.verbose = verbose
        
        # Load template and names
        self.template = Image.open(template_path).convert("RGB")
        self.names = self._load_names()
        
        # Detect placeholder position and colors
        self.text_region = self._detect_placeholder()
        
        os.makedirs(output_dir, exist_ok=True)
        
        if self.verbose:
            print(f"\n[Position] ({self.text_region.x}, {self.text_region.y})")
            print(f"[Text color] {self.text_region.text_color}")
            print(f"[Background] {self.text_region.bg_color}")
            print(f"[Max width] {self.text_region.width}px")
            print(f"[Font size] {self.text_region.detected_font_size or self.base_font_size}px")
            if self.text_region.placeholder_box:
                print(f"[Placeholder box] {self.text_region.placeholder_box}")
            print()

    def _load_names(self) -> List[str]:
        """Load names from Excel or CSV file"""
        path = Path(self.excel_path)
        if path.suffix.lower() == '.csv':
            df = pd.read_csv(self.excel_path)
        else:
            df = pd.read_excel(self.excel_path)
        return [str(name).strip() for name in df[self.name_column] if pd.notna(name)]

    def _detect_placeholder(self) -> TextRegion:
        """Use RapidOCR to find placeholder text position, with fallbacks"""
        img_array = np.array(self.template)
        height, width = img_array.shape[:2]
        
        detected_x, detected_y = width // 2, height // 2
        detected_width = int(width * 0.6)
        detected_height = 100
        color_x, color_y = detected_x, detected_y
        color_width, color_height = detected_width, detected_height
        detected_font_size = None
        placeholder_box = None
        placeholder_found = False
        anchor_line = None
        center_text = False
        
        ocr = _get_ocr()
        if ocr is not None and self.manual_position is None:
            try:
                if self.verbose:
                    print("Searching for placeholder with OCR...")
                
                # RapidOCR returns: (result, elapse)
                # result is list of [bbox, text, confidence]
                result, _ = ocr(img_array)
                
                if result:
                    placeholder_words = set(re.findall(r"\w+", self.placeholder.lower()))
                    matching_boxes = []
                    matched_placeholder_words = set()
                    
                    for item in result:
                        bbox, text, conf = item
                        text_lower = text.strip().lower()
                        detected_words = set(re.findall(r"\w+", text_lower))
                        matched_words = placeholder_words & detected_words
                        if matched_words:
                            x1 = int(min(p[0] for p in bbox))
                            y1 = int(min(p[1] for p in bbox))
                            x2 = int(max(p[0] for p in bbox))
                            y2 = int(max(p[1] for p in bbox))
                            matching_boxes.append((x1, y1, x2, y2, text))
                            matched_placeholder_words.update(matched_words)
                    
                    if matching_boxes and placeholder_words.issubset(matched_placeholder_words):
                        placeholder_found = True
                        x_min = min(b[0] for b in matching_boxes)
                        y_min = min(b[1] for b in matching_boxes)
                        x_max = max(b[2] for b in matching_boxes)
                        y_max = max(b[3] for b in matching_boxes)
                        
                        placeholder_box = (x_min, y_min, x_max, y_max)
                        detected_x = (x_min + x_max) // 2
                        detected_y = (y_min + y_max) // 2
                        detected_width = max(x_max - x_min, int(width * 0.4))
                        detected_height = y_max - y_min
                        color_x, color_y = detected_x, detected_y
                        color_width, color_height = detected_width, detected_height
                        
                        detected_font_size = self._estimate_font_size(
                            self.placeholder, x_max - x_min
                        )

                        # Keep a nearby underline as visual context, but do not
                        # automatically move the placement area: certificate
                        # layouts vary too much for that to be reliable. The web
                        # editor lets the user position its rectangle precisely.
                        anchor_line = self._find_underline(placeholder_box)
                        
                        if self.verbose:
                            matched = [b[4] for b in matching_boxes]
                            print(f"Found '{self.placeholder}' -> {matched}")
                            print(f"   Box: ({x_min}, {y_min}) to ({x_max}, {y_max})")
                    elif self.verbose:
                        print(f"Placeholder '{self.placeholder}' not found, using center")
                elif self.verbose:
                    print("No text detected, using center")
                    
            except Exception as e:
                if self.verbose:
                    print(f"OCR failed: {e}")
        elif ocr is None and self.manual_position is None:
            if self.verbose:
                print("rapidocr-onnxruntime not installed - using center")
                print("   Tip: pip install rapidocr-onnxruntime")
        
        if self.manual_position:
            detected_x, detected_y = self.manual_position
            color_x, color_y = detected_x, detected_y
            if self.verbose:
                print(f"Using manual position: ({detected_x}, {detected_y})")
        
        if self.max_text_width:
            detected_width = self.max_text_width
        
        text_color, bg_color = self._extract_colors(
            color_x, color_y, color_width, color_height
        )
        
        if self.user_font_color:
            text_color = self.user_font_color
        if self.user_bg_color:
            bg_color = self.user_bg_color
        
        return TextRegion(
            x=detected_x, y=detected_y, width=detected_width, height=detected_height,
            text_color=text_color, bg_color=bg_color,
            detected_font_size=detected_font_size, placeholder_box=placeholder_box,
            placeholder_found=placeholder_found, anchor_line=anchor_line,
            center_text=center_text,
        )

    def _find_underline(self, placeholder_box: Tuple[int, int, int, int]) -> Optional[Tuple[int, int, int, int]]:
        """Find a horizontal underline immediately below a detected placeholder.

        The search is deliberately local, preventing unrelated page dividers and
        signature lines elsewhere on a certificate from becoming text anchors.
        """
        if cv2 is None:
            return None

        x1, y1, x2, y2 = placeholder_box
        image = np.array(self.template)
        image_height, image_width = image.shape[:2]
        placeholder_width = max(1, x2 - x1)
        placeholder_height = max(1, y2 - y1)
        search_top = min(image_height, y2 + max(4, placeholder_height // 4))
        search_bottom = min(image_height, y2 + max(90, placeholder_height * 4))
        search_left = max(0, x1 - placeholder_width)
        search_right = min(image_width, x2 + placeholder_width)
        if search_bottom - search_top < 10 or search_right - search_left < 40:
            return None

        crop = image[search_top:search_bottom, search_left:search_right]
        grayscale = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
        edges = cv2.Canny(grayscale, 50, 150, apertureSize=3)
        lines = cv2.HoughLinesP(
            edges,
            rho=1,
            theta=np.pi / 180,
            threshold=max(18, placeholder_width // 5),
            minLineLength=max(40, placeholder_width // 2),
            maxLineGap=max(12, placeholder_width // 8),
        )
        if lines is None:
            return None

        placeholder_center = (x1 + x2) / 2
        candidates = []
        for raw_line in lines:
            lx1, ly1, lx2, ly2 = (int(value) for value in np.ravel(raw_line))
            length = abs(lx2 - lx1)
            vertical_delta = abs(ly2 - ly1)
            if vertical_delta > 3 or length < placeholder_width // 2:
                continue
            absolute_x1, absolute_x2 = sorted((search_left + lx1, search_left + lx2))
            absolute_y = search_top + (ly1 + ly2) // 2
            line_center = (absolute_x1 + absolute_x2) / 2
            # Prefer long, nearby lines centered under the placeholder.
            score = (length * 2) - abs(line_center - placeholder_center) - ((absolute_y - y2) * 0.35)
            candidates.append((score, absolute_x1, absolute_y, absolute_x2))

        if not candidates:
            return None
        _, line_x1, line_y, line_x2 = max(candidates, key=lambda item: item[0])
        return line_x1, line_y, line_x2, line_y

    def _estimate_font_size(self, text: str, target_width: int) -> int:
        """Estimate font size to match target width"""
        for size in range(20, 300, 2):
            try:
                font = ImageFont.truetype(self.font_path, size)
                bbox = font.getbbox(text)
                if bbox[2] - bbox[0] >= target_width:
                    return size
            except Exception:
                continue
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

    def _calculate_font_size(self, name: str, max_width: int, max_height: Optional[int] = None) -> int:
        """Calculate a font size that fits inside the placement box."""
        base_size = self.text_region.detected_font_size or self.base_font_size

        # The interactive editor allows deliberately small boxes. Respect that
        # geometry even when it requires going below the legacy min_font_size.
        for size in range(base_size, 0, -1):
            font = ImageFont.truetype(self.font_path, size)
            bbox = font.getbbox(name)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            if text_width <= max_width and (max_height is None or text_height <= max_height):
                return size
        return 1

    def render_certificate(self, name: str) -> Image.Image:
        """Render one certificate as an in-memory RGB image.

        This is useful for web applications that need to preview a certificate
        before deciding how it should be saved or packaged.
        """
        img = self.template.copy()
        draw = ImageDraw.Draw(img)
        img_width, img_height = img.size
        
        font_size = self._calculate_font_size(name, self.text_region.width, self.text_region.height)
        font = ImageFont.truetype(self.font_path, font_size)
        
        text_bbox = draw.textbbox((0, 0), name, font=font, anchor="lt")
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        
        if self.text_region.box_left is not None and self.text_region.box_top is not None:
            box_left = self.text_region.box_left
            box_top = self.text_region.box_top
            if self.text_region.text_align == "left":
                start_x = box_left
            elif self.text_region.text_align == "right":
                start_x = box_left + self.text_region.width - text_width
            else:
                start_x = box_left + (self.text_region.width - text_width) / 2
            center_y = box_top + self.text_region.height / 2
        elif self.text_region.center_text:
            start_x = self.text_region.x - (text_width // 2)
            center_y = self.text_region.y
        elif self.text_region.placeholder_box:
            px1, py1, px2, py2 = self.text_region.placeholder_box
            start_x = px1
            center_y = (py1 + py2) // 2
        else:
            start_x = self.text_region.x - (text_width // 2)
            center_y = self.text_region.y
        
        # Clear placeholder area
        if self.text_region.placeholder_box:
            px1, py1, px2, py2 = self.text_region.placeholder_box
            draw.rectangle([px1 - 25, py1 - 25, px2 + 25, py2 + 25], fill=self.text_region.bg_color)
        
        # Clear new text area
        half_h = text_height // 2
        draw.rectangle(
            [max(0, start_x - 10), max(0, center_y - half_h - 10),
             min(img_width, start_x + text_width + 10), min(img_height, center_y + half_h + 10)],
            fill=self.text_region.bg_color
        )
        
        # Boundary checks
        if start_x < 10:
            start_x = 10
        if start_x + text_width > img_width - 10:
            start_x = img_width - 10 - text_width
        
        draw.text((start_x, center_y), name, fill=self.text_region.text_color, font=font, anchor="lm")
        
        return img

    @staticmethod
    def save_certificate(image: Image.Image, output_path: str, output_format: str = "png") -> str:
        """Save a rendered certificate as PNG, JPEG, or a single-page PDF."""
        normalized_format = output_format.lower().replace("jpg", "jpeg")
        if normalized_format not in {"png", "jpeg", "pdf"}:
            raise ValueError("output_format must be PNG, JPEG, or PDF")

        if normalized_format == "jpeg":
            image.convert("RGB").save(output_path, "JPEG", quality=95, optimize=True)
        elif normalized_format == "pdf":
            image.convert("RGB").save(output_path, "PDF", resolution=150.0)
        else:
            image.save(output_path, "PNG", optimize=True)
        return output_path

    def _generate_single(self, name: str, index: int) -> str:
        """Generate a single PNG certificate using the legacy API."""
        img = self.render_certificate(name)

        safe_name = re.sub(r'[^\w\s-]', '', name).replace(" ", "_")
        output_path = os.path.join(self.output_dir, f"{safe_name}_certificate.png")
        self.save_certificate(img, output_path, "png")
        
        if self.verbose:
            print(f"[{index}/{len(self.names)}] {safe_name}_certificate.png")
        return output_path

    def generate_all(self) -> List[str]:
        """Generate certificates for all names"""
        paths = []
        for idx, name in enumerate(self.names, 1):
            paths.append(self._generate_single(name, idx))
        if self.verbose:
            print(f"\nGenerated {len(paths)} certificates in '{self.output_dir}'")
        return paths

    def export_as_pdf(self, output_name: str = "certificates.pdf") -> str:
        """Combine all certificates into a single PDF"""
        png_files = sorted(Path(self.output_dir).glob("*_certificate.png"))
        if not png_files:
            raise ValueError("No certificates found. Run generate_all() first.")
        
        images = [Image.open(f).convert("RGB") for f in png_files]
        pdf_path = os.path.join(self.output_dir, output_name)
        images[0].save(pdf_path, "PDF", save_all=True, append_images=images[1:])
        
        if self.verbose:
            print(f"PDF created: {pdf_path}")
        return pdf_path

    def zip_certificates(self, output_name: str = "certificates.zip") -> str:
        """Create ZIP archive of all certificates"""
        zip_path = os.path.join(self.output_dir, output_name)
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for file in Path(self.output_dir).glob("*_certificate.png"):
                zf.write(file, file.name)
        
        if self.verbose:
            print(f"Zipped: {zip_path}")
        return zip_path

    def email_certificates(
        self, smtp_server: str, smtp_port: int, sender_email: str,
        sender_password: str, recipient_emails: List[str],
        subject: str = "Your Certificate", body: str = "Please find your certificate attached."
    ):
        """Email certificates as ZIP attachment"""
        zip_path = self.zip_certificates()
        
        for recipient in recipient_emails:
            msg = MIMEMultipart()
            msg['From'], msg['To'], msg['Subject'] = sender_email, recipient, subject
            
            with open(zip_path, 'rb') as f:
                part = MIMEBase('application', 'zip')
                part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header('Content-Disposition', 'attachment; filename="certificates.zip"')
                msg.attach(part)
            
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()
                server.login(sender_email, sender_password)
                server.send_message(msg)
            
            if self.verbose:
                print(f"Sent to: {recipient}")

    def upload_to_s3(self, bucket: str, access_key: str, secret_key: str, 
                     region: str = "us-east-1", prefix: str = "certificates/"):
        """Upload certificates to AWS S3"""
        import boto3
        s3 = boto3.client('s3', aws_access_key_id=access_key, 
                          aws_secret_access_key=secret_key, region_name=region)
        
        for file in Path(self.output_dir).glob("*_certificate.png"):
            key = f"{prefix}{file.name}"
            s3.upload_file(str(file), bucket, key)
            if self.verbose:
                print(f"Uploaded: {key}")

    def upload_to_drive(self, credentials_path: str, folder_id: Optional[str] = None):
        """Upload certificates to Google Drive"""
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
        
        creds = service_account.Credentials.from_service_account_file(
            credentials_path, scopes=['https://www.googleapis.com/auth/drive.file']
        )
        service = build('drive', 'v3', credentials=creds)
        
        for file in Path(self.output_dir).glob("*_certificate.png"):
            metadata = {'name': file.name}
            if folder_id:
                metadata['parents'] = [folder_id]
            media = MediaFileUpload(str(file), mimetype='image/png')
            service.files().create(body=metadata, media_body=media).execute()
            if self.verbose:
                print(f"Uploaded: {file.name}")
