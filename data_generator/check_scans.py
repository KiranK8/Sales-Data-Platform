"""Can Tesseract (German + English) read the scanned PDFs?  python -m data_generator.check_scans

Also proves that scans have NO text layer and the other PDFs do.
"""
import csv
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

import pdfplumber

from .config import INCOMING, TRUTH

DEFAULT_TESSERACT = Path("C:/Program Files/Tesseract-OCR/tesseract.exe")


def find_tesseract():
    return shutil.which("tesseract") or (str(DEFAULT_TESSERACT) if DEFAULT_TESSERACT.exists() else None)


def score(expected_lines, ocr_text):
    """Word recall (every expected word found), number recall (only words with digits) and text similarity."""
    expected = " ".join(expected_lines).split()
    found = Counter(ocr_text.split())
    def recall(words):
        left, hit = Counter(found), 0
        for word in words:
            if left[word] > 0:
                left[word] -= 1
                hit += 1
        return hit / len(words) if words else 1.0
    similarity = SequenceMatcher(None, " ".join(expected), " ".join(ocr_text.split())).ratio()
    return recall(expected), recall([w for w in expected if any(c.isdigit() for c in w)]), similarity


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    exe = find_tesseract()
    if not exe:
        sys.exit("Tesseract not found. Install it first (winget install --id UB-Mannheim.TesseractOCR -e).")

    expected = {}
    with open(TRUTH / "scans_expected_text.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            expected.setdefault(row["file"], []).append(row["text"])

    print("Text layer check (pdfplumber)")
    for path in sorted(INCOMING.glob("*.pdf")):
        with pdfplumber.open(path) as pdf:
            has_text = bool((pdf.pages[0].extract_text() or "").strip())
        scan = path.name in expected
        print(f"  {path.name:<28}{'text layer found' if has_text else 'NO text layer':<18}"
              f"{'OK' if has_text != scan else 'UNEXPECTED'}")

    print(f"\nOCR with Tesseract ({subprocess.run([exe, '--version'], capture_output=True, text=True).stdout.splitlines()[0]}), "
          "languages deu+eng")
    print(f"  {'scan':<28}{'words':>8}{'numbers':>9}{'similarity':>12}")
    with tempfile.TemporaryDirectory() as tmp:
        for name, lines in expected.items():
            with pdfplumber.open(INCOMING / name) as pdf:
                image = pdf.pages[0].to_image(resolution=200).original
            png = Path(tmp) / (Path(name).stem + ".png")
            image.save(png)
            ocr = subprocess.run([exe, str(png), "stdout", "-l", "deu+eng", "--psm", "6"],
                                 capture_output=True, text=True, encoding="utf-8").stdout
            words, numbers, similarity = score(lines, ocr)
            print(f"  {name:<28}{words:>8.0%}{numbers:>9.0%}{similarity:>12.0%}")
            if name == next(iter(expected)):
                print("  first lines read by OCR:", " | ".join(l for l in ocr.splitlines() if l.strip())[:230])


if __name__ == "__main__":
    main()
