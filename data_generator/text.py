"""Small helpers that write numbers, dates and names the German (messy) way."""

_UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue"})


def translit(text):
    """Müller -> Mueller (what old systems without umlauts print)."""
    return text.translate(_UMLAUTS)


def de_number(value, decimals=2):
    """1200.5 -> '1.200,50' (dot for thousands, comma for decimals)."""
    text = f"{value:,.{decimals}f}"
    return text.replace(",", "#").replace(".", ",").replace("#", ".")


def de_decimal(value, decimals=2):
    """1200.5 -> '1200,50' (decimal comma, no thousands dot)."""
    return f"{value:.{decimals}f}".replace(".", ",")


def de_date(day):
    return day.strftime("%d.%m.%Y")


def iso_date(day):
    return day.strftime("%Y-%m-%d")


def de_percent(fraction):
    """0.18 -> '18 %'"""
    return f"{fraction * 100:.0f} %"


def de_percent_decimal(fraction):
    """0.18 -> '18,0 %'"""
    return f"{fraction * 100:.1f}".replace(".", ",") + " %"
