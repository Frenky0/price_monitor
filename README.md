# 🥥 Monitoraggio prezzo — Postre de COCO (Consum)

Invia una notifica push tramite **ntfy.sh** ogni volta che il prezzo del prodotto scende.

---

## Struttura del progetto

```
├── price_monitor.py              # Script principale
├── price_history.json            # Creato automaticamente al primo run
└── .github/
    └── workflows/
        └── price-check.yml       # Workflow GitHub Actions (ogni 6 ore)
```

---

## Setup rapido (GitHub Actions — gratuito, nessun server)

### 1. Installa ntfy sul telefono
- Android: [Play Store](https://play.google.com/store/apps/details?id=io.heckel.ntfy)
- iOS: [App Store](https://apps.apple.com/app/ntfy/id1625396347)
- Apri l'app → **Subscribe to topic** → inserisci `mio-canale-prezzi`
  *(o il nome che hai scelto in `NTFY_TOPIC`)*

### 2. Crea il repository su GitHub
```bash
git init
git add price_monitor.py .github/
git commit -m "first commit"
git branch -M main
git remote add origin https://github.com/TUO_UTENTE/TUO_REPO.git
git push -u origin main
```

### 3. Abilita i permessi di scrittura per Actions
Vai su **Repo → Settings → Actions → General → Workflow permissions**
e seleziona **"Read and write permissions"**.

### 4. (Opzionale) Test manuale
Vai su **Actions → Controlla prezzo Postre de COCO → Run workflow**.

---

## Uso locale

```bash
pip install requests beautifulsoup4 lxml
python price_monitor.py
```

---

## Personalizzazioni comuni

| Cosa cambiare | Dove |
|---|---|
| Canale ntfy | `NTFY_TOPIC` in `price_monitor.py` |
| URL / nome prodotto | `PRODUCT_URL`, `PRODUCT_NAME` |
| Frequenza controllo | `cron` in `price-check.yml` |
| Max tentativi rete | `MAX_RETRIES` |

---

## Come funziona

1. Lo script scarica la pagina prodotto di Consum
2. Estrae il prezzo con 3 strategie di parsing (meta tag, JSON-LD, selettori CSS)
3. Confronta con il prezzo salvato in `price_history.json`
4. Se il prezzo è calato → invia notifica push via ntfy.sh
5. Aggiorna `price_history.json` e GitHub Actions fa commit del file aggiornato

Il file `price_history.json` viene salvato nel repository ad ogni run, così il prezzo precedente è sempre disponibile al run successivo.
