"""
CertiGen - Automatic Certificate Generator with OCR-based placeholder detection
"""

from .generator import CertificateGenerator, TextRegion
from .utils import find_coordinates

__version__ = "1.0.0"
__author__ = "Nakul Desai"
__email__ = "nakuldesai2006@gmail.com"

__all__ = ["CertificateGenerator", "TextRegion", "find_coordinates"]
