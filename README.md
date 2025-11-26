# MTG Scan System

![MTG Scan Logo](https://img.shields.io/badge/MTG%20Scan-Scan%20Sort%20Done-00D084?style=for-the-badge)

Un sistema completo di scansione e catalogazione per Magic: The Gathering con riconoscimento AI, ordinamento intelligente e tracking prezzi in tempo reale.

## 🎯 Funzionalità Principali

### 📷 Scansione e Riconoscimento
- **Riconoscimento automatico** delle carte tramite AI e computer vision
- **Batch scanning** per processare multiple carte contemporaneamente
- **Preprocessing avanzato** delle immagini (crop, rotate, enhance)
- **Confidence scoring** per valutare l'accuratezza del riconoscimento
- Supporto per **foil cards** e diverse lingue

### 🗂️ Catalogazione Digitale
- **Database completo** con tutte le informazioni delle carte
- Integrazione con **Scryfall API** per dati accurati
- **Collezioni personalizzate** per organizzare le carte
- **Ricerca e filtri** avanzati
- **Export dei dati** in vari formati

### 🔄 Sistema di Ordinamento
- **6 criteri di ordinamento**:
  - Alfabetico (1°, 2°, 3° lettera)
  - Set/Espansione
  - Colore (WUBRG + multicolor + colorless)
  - Tipo di carta
  - Rarità
  - Prezzo (5 tier)
- **Configurazione bins** personalizzabile (2-20 bins)
- **Preview** prima di applicare l'ordinamento
- **Salvataggio configurazioni** per riutilizzo

### 💰 Tracking Prezzi
- Integrazione con **Scryfall API** per prezzi accurati (EUR e USD)
- **Aggiornamento automatico** dei prezzi ogni 6 ore
- **Storico prezzi** per tracking nel tempo
- **Trend di prezzo** con indicatori ↑↓→
- **Calcolo valore collezione** con breakdown per tier
- **5 tier di prezzo**: Bulk, Low, Medium, High, Premium

### 🌐 Portale Web
- **Dashboard** con statistiche in tempo reale
- **Scanner interface** con drag & drop
- **Card library** con grid view
- **Sorting controls** interattivi
- **Import tools** per popolare il database
- **Real-time updates** via WebSocket

## 🚀 Installazione

### Prerequisiti
- Python 3.8+
- pip

### Setup

1. **Installa le dipendenze**:
```bash
cd C:\Users\Utente\Desktop\SCANNER
pip install -r requirements.txt
```

2. **Inizializza il database**:
```bash
python database.py
```

3. **Avvia il server**:
```bash
python app.py
```

4. **Apri il browser**:
```
http://localhost:5000
```

## 📖 Guida all'Uso

### 1. Importare Carte nel Database

Prima di poter riconoscere le carte, devi popolare il database:

**Opzione A - Import Singola Carta**:
1. Vai su "Import Cards"
2. Seleziona il TCG
3. Inserisci il nome della carta
4. Clicca "Import Card"

**Opzione B - Import Set Completo (MTG)**:
1. Vai su "Import Cards"
2. Inserisci il codice del set (es: MID, VOW, NEO)
3. Clicca "Import Entire Set"
4. Attendi il completamento (può richiedere alcuni minuti)

### 2. Scansionare Carte

1. Vai su "Scanner"
2. Seleziona il TCG
3. Scegli la modalità (Single/Batch)
4. Carica le immagini delle carte (drag & drop o click)
5. Clicca "Start Scanning"
6. Visualizza i risultati con confidence score

### 3. Visualizzare la Collezione

1. Vai su "Card Library"
2. Usa i filtri per TCG e rarità
3. Cerca carte specifiche
4. Visualizza dettagli e statistiche

### 4. Ordinare le Carte

1. Vai su "Sorting"
2. Seleziona il criterio di ordinamento
3. Configura il numero di bins
4. Clicca "Preview Sorting" per vedere l'anteprima
5. Clicca "Apply Sorting" per applicare
6. Le carte vengono assegnate ai bins

### 5. Monitorare i Prezzi

1. I prezzi vengono aggiornati automaticamente
2. Visualizza il valore totale nella Dashboard
3. Vedi il breakdown per price tier
4. Storico prezzi disponibile per ogni carta

## 🏗️ Architettura del Sistema

### Backend (Python)
```
app.py                  # Flask application principale
database.py             # SQLAlchemy models e DB setup
card_recognition.py     # Engine di riconoscimento AI
sorting_engine.py       # Algoritmi di ordinamento
price_tracker.py        # Sistema di tracking prezzi
api_integrations.py     # Client per API esterne
config.py              # Configurazione
```

### Frontend (Web Portal)
```
static/
  ├── index.html       # Dashboard
  ├── scanner.html     # Interfaccia scanner
  ├── library.html     # Libreria carte
  ├── sorting.html     # Configurazione sorting
  ├── import.html      # Import carte
  ├── styles.css       # Design system
  └── app.js          # JavaScript + WebSocket
```

### Database Schema
- **cards**: Master database di tutte le carte conosciute
- **scanned_cards**: Istanze delle carte scansionate
- **collections**: Collezioni personalizzate
- **price_history**: Storico prezzi
- **sorting_configs**: Configurazioni di ordinamento salvate

## 🔧 API Endpoints

### Scanning
- `POST /api/scan/upload` - Upload e riconosci singola carta
- `POST /api/scan/batch` - Batch scan multiple carte

### Cards
- `GET /api/cards/search` - Cerca carte nel database
- `POST /api/cards/import` - Importa carta da API
- `POST /api/cards/bulk-import` - Import set completo

### Collection
- `GET /api/collection` - Ottieni collezione
- `GET /api/collection/stats` - Statistiche collezione

### Sorting
- `POST /api/sort/preview` - Anteprima ordinamento
- `POST /api/sort/apply` - Applica ordinamento

### Prices
- `POST /api/prices/update` - Aggiorna prezzi
- `GET /api/prices/history/<card_id>` - Storico prezzi
- `GET /api/prices/trend/<card_id>` - Trend prezzi
- `GET /api/prices/trending` - Carte in trend

## 🎨 Tecnologie Utilizzate

- **Backend**: Flask, SQLAlchemy, Flask-SocketIO
- **Computer Vision**: OpenCV, Pillow
- **Image Hashing**: imagehash
- **APIs**: Scryfall (per dati e prezzi MTG)
- **Frontend**: HTML5, CSS3, JavaScript (Vanilla)
- **Real-time**: Socket.IO
- **Database**: SQLite

## 📊 Supporto Magic: The Gathering

- ✅ Riconoscimento completo tramite OCR + Scryfall API
- ✅ Tutti i set disponibili
- ✅ Prezzi in tempo reale (EUR e USD)
- ✅ Trend prezzi con indicatori visuali
- ✅ Sorting per colore WUBRG, tipo, rarità, set, prezzo

## 🔒 Note sulla Sicurezza

- Cambia `SECRET_KEY` in produzione
- Usa HTTPS per deployment
- Limita dimensione upload (default 16MB)
- Rate limiting sulle API esterne implementato

## 🐛 Troubleshooting

### Il riconoscimento non funziona
- Assicurati di aver importato le carte nel database
- Verifica che le immagini siano di buona qualità
- Prova a inserire manualmente il nome della carta

### Errori di import
- Verifica la connessione internet
- Controlla che il codice set sia corretto
- Le API esterne potrebbero avere rate limits

### Database locked
- Chiudi tutte le connessioni al database
- Riavvia il server

## 📝 Licenza

Questo progetto è stato creato per scopi educativi e dimostrativi.

## 🙏 Credits

- **Scryfall API** per i dati e prezzi Magic: The Gathering

---

**MTG Scan** - Scan. Sort. Done. ⚡
