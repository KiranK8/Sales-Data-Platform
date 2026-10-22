"""STEP 3B: PDF price sheets: 10 with a text layer, 3 scanned (image only, OCR needed)."""
import csv
import os
import time
from pathlib import Path
from xml.sax.saxutils import escape

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .config import INCOMING, ISSUER, TRUTH, make_rng
from .docs_common import FIXED_STAMP, long_date, prices_by_period, same_dates
from .text import de_date, de_number, de_percent, iso_date
from .truth import CHARGE_ALIASES, PCT_CHARGES

FIXED_TIME = time.struct_time(FIXED_STAMP + (0, 0, 0))
TEXT_PDF_COUNT = 10
SCAN_SETTINGS = [(0.8, 8), (-1.2, 14), (1.6, 20)]   # (rotation in degrees, noise strength) per scan
MAX_SCAN_ROWS = 12
PAGE = (1654, 2339)                                  # A4 at 200 dpi
HEADERS = {"de": ("Strecke", "Preisart", "Preis"), "en": ("Lane", "Charge", "Price")}
FOOTER = "Alle Preise je Sendung, zuzüglich gesetzlicher MwSt."


def _validity(style, start, end):
    if style["date"] == "long":
        return f"Gültig ab {long_date(start)} bis {long_date(end)}"
    if style["date"] == "iso":
        return f"Valid from {iso_date(start)} to {iso_date(end)}"
    return f"Gültig vom {de_date(start)} bis {de_date(end)}"


def _make_sheet(truth, group, by_period, rng, style, english_numbers=False, max_rows=None):
    """The content of one price sheet: lines of text plus the prices it contains."""
    customer = rng.choice(truth.aliases_of(group[0].customer_id))
    rows, prices = [], []
    for period in group:
        lane = truth.lane(period.lane_id)
        for price in by_period[period.pid]:
            charge = rng.choice(CHARGE_ALIASES[price.charge_type])
            if price.charge_type in PCT_CHARGES:
                amount = de_percent(price.amount)
            elif english_numbers:
                amount = f"{price.amount:,.2f} EUR"        # PLANTED: 1,200.00 instead of 1.200,00
            else:
                amount = f"{de_number(price.amount)} EUR"
            rows.append((f"{lane['origin_city']} – {lane['dest_city']}", charge, amount))
            prices.append(price)
    if max_rows:
        rows, prices = rows[:max_rows], prices[:max_rows]
    return {
        "title": "Price sheet" if style["lang"] == "en" else "Preisblatt",
        "customer_line": f"Kunde: {customer}",
        "validity_line": _validity(style, group[0].start, group[0].end),
        "header": HEADERS[style["lang"]], "rows": rows, "prices": prices, "footer": FOOTER,
        "customer_id": group[0].customer_id,
    }


def expected_lines(spec):
    """The text a perfect reader would find on the page (used to judge the OCR quality)."""
    lines = [spec["title"], spec["customer_line"], spec["validity_line"], " ".join(spec["header"])]
    lines += [" ".join(row) for row in spec["rows"]]
    return lines + [spec["footer"]]


# ---------------------------------------------------------------- text PDFs (reportlab)
def _write_text_pdf(path, spec, font_size):
    styles = getSampleStyleSheet()
    body = styles["Normal"].clone("body", fontSize=font_size, leading=font_size * 1.4)
    doc = SimpleDocTemplate(str(path), pagesize=A4, invariant=1, title=spec["title"], author=ISSUER,
                            leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm)
    table = Table([list(spec["header"])] + [list(row) for row in spec["rows"]],
                  colWidths=[6.5 * cm, 5.5 * cm, 4.5 * cm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), font_size), ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ALIGN", (2, 1), (2, -1), "RIGHT")]))
    doc.build([Paragraph(escape(ISSUER), body), Paragraph(escape(spec["title"]), styles["Title"]),
               Paragraph(escape(spec["customer_line"]), body), Paragraph(escape(spec["validity_line"]), body),
               Spacer(1, 0.6 * cm), table, Spacer(1, 0.6 * cm), Paragraph(escape(spec["footer"]), body)])


# ---------------------------------------------------------------- scanned PDFs (Pillow)
def _font(size, bold=False):
    fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    for name in ("arialbd.ttf" if bold else "arial.ttf", "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(str(fonts / name) if (fonts / name).exists() else name, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def render_scan(spec, angle, noise, seed):
    """Draw the page as a picture, then make it look scanned: rotated, blurred, noisy."""
    img = Image.new("L", PAGE, 252)
    draw = ImageDraw.Draw(img)
    f_title, f_body, f_bold = _font(64, True), _font(38), _font(38, True)
    x0, right, row_h = 120, 1534, 66
    columns = [x0, x0 + 600, x0 + 1130]
    draw.text((x0, 140), spec["title"], font=f_title, fill=15)
    draw.text((x0, 260), spec["customer_line"], font=f_body, fill=15)
    draw.text((x0, 330), spec["validity_line"], font=f_body, fill=15)
    y = 440
    for cells, font, fill in [(spec["header"], f_bold, 215)] + [(row, f_body, 252) for row in spec["rows"]]:
        draw.rectangle([x0, y, right, y + row_h], fill=fill, outline=60, width=2)
        for x, text in zip(columns, cells):
            draw.text((x + 12, y + 12), text, font=font, fill=15)
        y += row_h
    draw.text((x0, y + 80), spec["footer"], font=f_body, fill=15)

    img = img.rotate(angle, resample=Image.BICUBIC, fillcolor=245).filter(ImageFilter.GaussianBlur(0.8))
    rs = np.random.RandomState(seed)
    pixels = np.asarray(img, dtype=np.float32) + rs.normal(0, noise, (PAGE[1], PAGE[0]))
    pixels += np.linspace(-6, 0, PAGE[1], dtype=np.float32)[:, None]          # uneven scanner light
    specks = rs.random_sample(pixels.shape) < 0.0006                         # dust and dots
    pixels[specks] = rs.choice([0, 255], size=int(specks.sum()))
    return Image.fromarray(np.clip(pixels, 0, 255).astype(np.uint8))


def build_pdf_files(truth, errors, doc_prices):
    rng = make_rng("pdf")
    by_period = prices_by_period(truth)
    ids = [c["customer_id"] for c in truth.customers]
    text_ids = sorted(rng.sample(ids, TEXT_PDF_COUNT))
    scan_ids = sorted(rng.sample([c for c in ids if c not in text_ids], len(SCAN_SETTINGS)))
    english_index = rng.randrange(TEXT_PDF_COUNT)

    summary = []
    for i, cid in enumerate(text_ids):
        period = rng.choice([p for p in truth.periods if p.customer_id == cid])
        style = {"lang": "en" if i % 3 == 2 else "de", "date": ["de", "long", "iso"][i % 3]}
        spec = _make_sheet(truth, same_dates(truth, period), by_period, rng, style, english_numbers=i == english_index)
        name = f"preisblatt_{cid}.pdf"
        _write_text_pdf(INCOMING / name, spec, font_size=[10, 9, 11][i % 3])
        doc_prices.extend((name, price.price_id) for price in spec["prices"])
        summary.append((name, len(spec["rows"])))
        if i == english_index:   # PLANTED
            errors.add("english_number_format", name, "price column", "EUR amounts written with a decimal point "
                       "(870.00, 1,200.00) instead of the German decimal comma (870,00, 1.200,00)")

    expected = []   # ground truth for OCR: the lines printed on each scan
    for cid, (angle, noise) in zip(scan_ids, SCAN_SETTINGS):
        candidates = [p for p in truth.periods if p.customer_id == cid]
        rng.shuffle(candidates)
        period = next((p for p in candidates if sum(len(by_period[q.pid]) for q in same_dates(truth, p)) <= MAX_SCAN_ROWS),
                      candidates[0])
        spec = _make_sheet(truth, same_dates(truth, period), by_period, rng, {"lang": "de", "date": "de"},
                           max_rows=MAX_SCAN_ROWS)
        name = f"preisblatt_scan_{cid}.pdf"
        # fixed creation/modification date: Pillow would otherwise stamp "now" and the file would change every run
        render_scan(spec, angle, noise, seed=cid).save(INCOMING / name, "PDF", resolution=200.0,
                                                       creationDate=FIXED_TIME, modDate=FIXED_TIME)
        doc_prices.extend((name, price.price_id) for price in spec["prices"])
        expected.extend([name, n, line] for n, line in enumerate(expected_lines(spec), 1))
        summary.append((name, len(spec["rows"])))
        errors.add("scanned_pdf_no_text", name, "page 1",
                   f"image-only page, rotated {angle}° with noise {noise}, no text layer: OCR needed")

    with open(TRUTH / "scans_expected_text.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["file", "line_no", "text"])
        writer.writerows(expected)
    return summary
