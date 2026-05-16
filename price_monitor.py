"""
Monitoraggio prezzi - Postre de COCO (Consum)
Invia una notifica via ntfy.sh quando il prezzo scende rispetto all'ultimo rilevato.

Dipendenze:
    pip install requests beautifulsoup4 lxml

Uso manuale:
    python price_monitor.py
"""

import json
import logging
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# CONFIGURAZIONE
# ---------------------------------------------------------------------------

PRODUCT_URL = "https://tienda.consum.es/es/p/postre-de-coco-natural/7401768"
PRODUCT_NAME = "Postre de COCO"

# File dove viene salvata la storia dei prezzi
HISTORY_FILE = Path("price_history.json")

# Canale ntfy.sh — cambialo con il tuo canale segreto
NTFY_TOPIC = "mio-canale-prezzi"
NTFY_URL = f"https://ntfy.sh/{NTFY_TOPIC}"

# Tentativi in caso di errore di rete prima di rinunciare
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 10

# Header HTTP per simulare un browser reale ed evitare blocchi
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-ES,es;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

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
# FUNZIONI PRINCIPALI
# ---------------------------------------------------------------------------


def fetch_page(url: str) -> str:
    """
    Scarica il codice HTML della pagina prodotto.
    Riprova fino a MAX_RETRIES volte in caso di errore di rete.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            log.info(f"Tentativo {attempt}/{MAX_RETRIES}: scarico {url}")
            response = requests.get(url, headers=HEADERS, timeout=20)
            response.raise_for_status()
            return response.text
        except requests.RequestException as exc:
            log.warning(f"Errore di rete (tentativo {attempt}): {exc}")
            if attempt < MAX_RETRIES:
                log.info(f"Riprovo tra {RETRY_DELAY_SECONDS} secondi...")
                time.sleep(RETRY_DELAY_SECONDS)
    raise RuntimeError(f"Impossibile scaricare la pagina dopo {MAX_RETRIES} tentativi.")


def parse_price(html: str) -> float:
    """
    Estrae il prezzo dalla pagina HTML di Consum.
    Prova più selettori in ordine di priorità per resistere a piccoli
    cambiamenti nel markup del sito.
    """
    soup = BeautifulSoup(html, "lxml")

    # --- Strategia 1: meta tag Open Graph / schema.org (il più stabile) ---
    # Consum spesso include <meta property="product:price:amount" content="2.55">
    for meta_name in (
        "product:price:amount",
        "og:price:amount",
    ):
        tag = soup.find("meta", property=meta_name)
        if tag and tag.get("content"):
            return _to_float(tag["content"])

    # --- Strategia 2: JSON-LD strutturato (schema.org/Product) ---
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            # Può essere un oggetto o una lista
            items = data if isinstance(data, list) else [data]
            for item in items:
                if item.get("@type") in ("Product", "Offer"):
                    price = (
                        item.get("offers", {}).get("price")
                        or item.get("price")
                    )
                    if price is not None:
                        return _to_float(str(price))
        except (json.JSONDecodeError, AttributeError):
            continue

    # --- Strategia 3: selettori CSS comuni nei siti di e-commerce spagnoli ---
    css_selectors = [
        "[class*='price--current']",
        "[class*='current-price']",
        "[class*='precio']",
        "[itemprop='price']",
        ".price__value",
        ".price",
    ]
    for selector in css_selectors:
        tag = soup.select_one(selector)
        if tag:
            # Prova prima l'attributo content (itemprop), poi il testo
            value = tag.get("content") or tag.get_text(strip=True)
            if value:
                price = _to_float(value)
                if price > 0:
                    return price

    raise ValueError(
        "Impossibile trovare il prezzo nella pagina. "
        "Il sito potrebbe aver cambiato il markup."
    )


def _to_float(value: str) -> float:
    """
    Converte una stringa come '2,55 €' o '2.55' in float.
    Gestisce sia il formato italiano/spagnolo (virgola decimale) sia quello anglosassone.
    """
    # Rimuove tutto tranne cifre, punti e virgole
    cleaned = "".join(c for c in value if c.isdigit() or c in ".,")
    if not cleaned:
        raise ValueError(f"Nessun numero trovato in: {value!r}")
    # Se ci sono sia punto che virgola, il separatore decimale è l'ultimo
    if "," in cleaned and "." in cleaned:
        # Es. "1.299,99" → 1299.99
        cleaned = cleaned.replace(".", "").replace(",", ".")
    else:
        # Es. "2,55" → 2.55
        cleaned = cleaned.replace(",", ".")
    return float(cleaned)


# ---------------------------------------------------------------------------
# STORIA DEI PREZZI
# ---------------------------------------------------------------------------


def load_history() -> dict:
    """Carica il file JSON con la storia dei prezzi (crea il file se non esiste)."""
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            log.warning("File history corrotto, ne creo uno nuovo.")
    return {}


def save_history(history: dict) -> None:
    """Salva la storia dei prezzi nel file JSON."""
    HISTORY_FILE.write_text(
        json.dumps(history, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# NOTIFICA NTFY
# ---------------------------------------------------------------------------


def send_ntfy_notification(current_price: float, previous_price: float) -> None:
    """
    Invia una notifica push tramite ntfy.sh.
    Il canale è quello configurato in NTFY_TOPIC.
    """
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
        log.info(f"Notifica inviata con successo a ntfy.sh/{NTFY_TOPIC}")
    except requests.RequestException as exc:
        log.error(f"Errore nell'invio della notifica ntfy: {exc}")


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------


def main() -> None:
    log.info(f"=== Avvio monitoraggio: {PRODUCT_NAME} ===")

    # 1. Scarica la pagina
    html = fetch_page(PRODUCT_URL)

    # 2. Estrai il prezzo
    current_price = parse_price(html)
    log.info(f"Prezzo rilevato: €{current_price:.2f}")

    # 3. Carica la storia e confronta
    history = load_history()
    product_key = "postre_coco"
    previous_price = history.get(product_key, {}).get("price")

    if previous_price is None:
        log.info(
            f"Nessun prezzo precedente trovato. "
            f"Salvo €{current_price:.2f} come riferimento iniziale."
        )
    elif current_price < previous_price:
        log.info(
            f"Prezzo CALATO: €{previous_price:.2f} → €{current_price:.2f}. "
            "Invio notifica..."
        )
        send_ntfy_notification(current_price, previous_price)
    elif current_price > previous_price:
        log.info(
            f"Prezzo aumentato: €{previous_price:.2f} → €{current_price:.2f}. "
            "Nessuna notifica."
        )
    else:
        log.info(f"Prezzo invariato: €{current_price:.2f}. Nessuna notifica.")

    # 4. Aggiorna la storia
    from datetime import datetime, timezone

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
