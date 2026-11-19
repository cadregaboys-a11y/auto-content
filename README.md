# Niche Video Finder

Starter locale composto da un frontend Angular con Tailwind CSS, un'API Node.js e uno script Python basato su `yt-dlp`.

## Requisiti

- Node.js 20.19+ oppure 22.12+
- Python 3.10+

## Avvio

1. Installa le dipendenze Python: `python -m pip install -r requirements.txt`
2. Per il montaggio video installa anche: `python -m pip install -r requirements-video.txt`
3. Installa le dipendenze API: `cd backend; npm install`
4. Avvia l'API in un terminale: `npm run dev`
5. Installa le dipendenze Angular: `cd ../frontend; npm install`
6. Avvia il frontend in un altro terminale: `npm start`

Apri `http://localhost:4200`. Il proxy Angular inoltra le richieste `/api` al backend locale sulla porta 3000.

Su Windows, se il comando `python` non è disponibile, imposta `PYTHON_EXECUTABLE` con il percorso dell'interprete Python prima di avviare l'API. Il backend carica automaticamente `backend/.env` all'avvio (Node.js 20.19+ o 22.12+); le variabili d'ambiente già definite nel sistema hanno precedenza.

## Pipeline per gli Short

Installa FFmpeg e `ffprobe` e rendili disponibili nel `PATH`. Installa Ollama, avvialo su `http://127.0.0.1:11434` e scarica il modello visivo `ollama pull qwen2.5vl:3b` (modello selezionabile con `OLLAMA_VISION_MODEL`; host locale configurabile con `OLLAMA_HOST`). Configura `ELEVENLABS_API_KEY` e `ELEVENLABS_VOICE_ID` nell'ambiente del processo Node; il modello Whisper locale è selezionabile con `WHISPER_MODEL` (predefinito `base`). La UI invia `POST /api/video-jobs`, che cerca e scarica il primo risultato idoneo, poi avvia la pipeline. Lo stato si controlla con `GET /api/video-jobs/:id`, l'anteprima sorgente con `GET /api/video-jobs/:id/source`, l'anteprima montata con `GET /api/video-jobs/:id/preview` e il file finale con `GET /api/video-jobs/:id/download`. `POST /api/video-processing` resta disponibile per elaborare un video già scaricato.

Il job automatico richiede la conferma esplicita dei diritti prima di iniziare. Cerca un solo video alla volta, verificando i metadati completi della licenza; sono scaricati solo risultati che dichiarano Creative Commons Attribution. Durante ricerca e download, yt-dlp emette gli aggiornamenti di avanzamento. Dopo il download, la pipeline estrae fotogrammi chiave e li invia al modello Qwen in esecuzione su Ollama locale per descrivere scena, azioni, momenti e punto focale; integra questa analisi con il rilevamento locale del movimento. Il modello genera uno script in italiano con gancio iniziale, basato sulla scena e sulla trascrizione Whisper, con un limite di parole calibrato sulla durata disponibile. Se il parlato supera la durata sorgente, lo script viene accorciato e sintetizzato di nuovo. ElevenLabs genera la voce; Whisper ne allinea i timestamp parola per parola; FFmpeg seleziona i momenti migliori, centra ogni taglio sul punto focale, concatena segmenti per la durata effettiva del parlato e masterizza sottotitoli ASS dinamici. La UI consente di riprodurre sia la sorgente scaricata sia lo Short finito prima di scaricarlo. I fotogrammi sono inviati solo al modello configurato come locale e i file audio a ElevenLabs; non vengono inviati fotogrammi a ElevenLabs. I job sono in memoria e si perdono al riavvio del backend.

## Download e licenze

La ricerca seleziona esclusivamente video il cui campo licenza di YouTube dichiara una licenza Creative Commons Attribution; risultati senza licenza verificabile vengono ignorati. I file vengono salvati in `downloads/` (massimo 3 per richiesta). Verifica sempre i termini applicabili, i diritti e gli obblighi di attribuzione prima di usare o ridistribuire i contenuti. Questo starter non aggira restrizioni di accesso o protezioni tecniche.
