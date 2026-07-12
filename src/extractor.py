from __future__ import annotations

import os
from pathlib import Path

import pdfplumber
import pytesseract
from docx import Document
from PIL import Image


SUPPORTED_EXTENSIONS = {
	".pdf",
	".docx",
	".png",
	".jpg",
	".jpeg",
	".tif",
	".tiff",
	".bmp",
	".webp",
}


def _configure_tesseract_from_env() -> None:
	tesseract_cmd = os.getenv("TESSERACT_CMD", "").strip()
	if tesseract_cmd:
		pytesseract.pytesseract.tesseract_cmd = tesseract_cmd


def extract_text_from_pdf(file_path: str | Path) -> str:
	path = Path(file_path)
	texts: list[str] = []

	with pdfplumber.open(path) as pdf:
		for page in pdf.pages:
			page_text = (page.extract_text() or "").strip()
			if page_text:
				texts.append(page_text)

	return "\n\n".join(texts)


def extract_text_from_docx(file_path: str | Path) -> str:
	path = Path(file_path)
	document = Document(path)
	paragraphs = [paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip()]
	return "\n".join(paragraphs)


def extract_text_from_image(file_path: str | Path, lang: str = "eng") -> str:
	_configure_tesseract_from_env()

	path = Path(file_path)
	with Image.open(path) as image:
		return pytesseract.image_to_string(image, lang=lang).strip()


def extract_text(file_path: str | Path, ocr_lang: str = "eng") -> str:
	path = Path(file_path)
	extension = path.suffix.lower()

	if extension not in SUPPORTED_EXTENSIONS:
		raise ValueError(f"Type de fichier non supporte pour extraction: {path.suffix}")

	if extension == ".pdf":
		return extract_text_from_pdf(path)

	if extension == ".docx":
		return extract_text_from_docx(path)

	return extract_text_from_image(path, lang=ocr_lang)

