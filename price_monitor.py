"""
Monitoraggio prezzi - Postre de COCO (Consum)
Usa Playwright per caricare la pagina JavaScript e leggere il prezzo reale.

Dipendenze:
    pip install playwright requests
    playwright install chromium

Uso manuale:
    python price_monitor.py
"""

import json
import logging
from pathlib import Path
from datetime import datetime, timezone

import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# ---------------------------------------------------------------------------
# CONFIGURAZIONE
# ---------------------------------------------------------------------------

PRODUCT_URL = "https://tienda.consum.es/es/p/postre-de-coco-natural/7401768"
PRODUCT_NAME = "Postre de COCO"

HISTORY_FILE = Path("price_history.json")

NTFY_TOPIC = "mio-canale-prezzi"
NTFY_URL = f"https://ntfy.sh/{NTFY_TOPIC}"

# ---------------------------------------------------------------------------
# LOGGING
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SCRAPING CON PLAYWRIGHT
# ---------------------------------------------------------------------------


def fetch_price() -> float:
    """
    Apre la pagina con un browser headless (Chromium) e legge il prezzo
    dal selettore CSS reale trovato nell'HTML del sito Consum.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        )

        log.info(f"Apro la pagina: {PRODUCT_URL}")
        page.goto(PRODUCT_URL, wait_until="networkidle", timeout=30000)

        # Attendi che il prezzo sia visibile (Angular impiega qualche secondo)
        selector = ".product-info-price__price"
        try:
            page.wait_for_selector(selector, timeout=15000)
        except PlaywrightTimeout:
            browser.close()
            raise ValueError(
                f"Timeout: il selettore '{selector}' non è apparso entro 15 secondi."
            )

        price_text = page.inner_text(selector)
        browser.close()

    log.info(f"Testo prezzo trovato: {price_text!r}")
    return _to_float(price_text)


def _to_float(value: str) -> float:
    """Converte '2,55 €' o '2.55' in float."""
    cleaned = "".join(c for c in value if c.isdigit() or c in ".,")
    if not cleaned:
        raise ValueError(f"Nessun numero trovato in: {value!r}")
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    else:
        cleaned = cleaned.replace(",", ".")
    return float(cleaned)


# ---------------------------------------------------------------------------
# STORIA DEI PREZZI
# ---------------------------------------------------------------------------


def load_history() -> dict:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            log.warning("File history corrotto, ne creo uno nuovo.")
    return {}


def save_history(history: dict) -> None:
    HISTORY_FILE.write_text(
        json.dumps(history, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# NOTIFICA NTFY
# ---------------------------------------------------------------------------


def send_ntfy_notification(current_price: float, previous_price: float) -> None:
    risparmio = previous_price - current_price
    percentuale = (risparmio / previous_price) * 100

    titolo = f"📉 Prezzo calato: {PRODUCT_NAME}"
    messaggio = (
        f"Il prezzo è sceso da €{previous_price:.2f} a €{current_price:.2f} "
        f"(risparmio: €{risparmio:.2f}, -{percentuale:.1f}%)\n"
        f"👉 {PRODUCT_URL}"
    )

    try:
        response = requests.post(
            NTFY_URL,
            data=messaggio.encode("utf-8"),
            headers={
                "Title": titolo,
                "Priority": "high",
                "Tags": "shopping,moneybag",
                "Click": PRODUCT_URL,
            },
            timeout=10,
        )
        response.raise_for_status()
        log.info(f"Notifica inviata a ntfy.sh/{NTFY_TOPIC}")
    except requests.RequestException as exc:
        log.error(f"Errore notifica ntfy: {exc}")


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------


def main() -> None:
    log.info(f"=== Avvio monitoraggio: {PRODUCT_NAME} ===")

    current_price = fetch_price()
    log.info(f"Prezzo rilevato: €{current_price:.2f}")

    history = load_history()
    product_key = "postre_coco"
    previous_price = history.get(product_key, {}).get("price")

    if previous_price is None:
        log.info(f"Primo rilevamento. Salvo €{current_price:.2f} come riferimento.")
    elif current_price < previous_price:
        log.info(f"Prezzo CALATO: €{previous_price:.2f} → €{current_price:.2f}. Invio notifica...")
        send_ntfy_notification(current_price, previous_price)
    elif current_price > previous_price:
        log.info(f"Prezzo aumentato: €{previous_price:.2f} → €{current_price:.2f}. Nessuna notifica.")
    else:
        log.info(f"Prezzo invariato: €{current_price:.2f}. Nessuna notifica.")

    history[product_key] = {
        "name": PRODUCT_NAME,
        "url": PRODUCT_URL,
        "price": current_price,
        "last_checked": datetime.now(timezone.utc).isoformat(),
    }
    save_history(history)
    log.info(f"Storia salvata in {HISTORY_FILE}")


if __name__ == "__main__":
    main()
