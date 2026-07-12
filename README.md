# Mail IA Agent (Gmail, local-first)

Ce projet Python indexe des emails Gmail et leurs pieces jointes pour permettre des recherches en langage naturel, en gardant les donnees en local.

Etat actuel:
- setup du projet
- connexion IMAP Gmail
- commande CLI `index` pour afficher les 10 derniers mails de INBOX
- round 2: affichage de la taille du corps texte et du nombre de pieces jointes

## 1) Cloner le projet depuis GitHub

```bash
git clone https://github.com/PascalDuval/IAmail.git
cd IAmail
```

## 2) Creer un environnement Python

Windows (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

## 3) Installer les dependances

```bash
pip install -r requirements.txt
```

## 4) Configurer Gmail via mot de passe d'application

1. Activez la validation en 2 etapes du compte Google.
2. Generez un mot de passe d'application Gmail.
3. Activez IMAP dans Gmail (Parametres > Transfert et POP/IMAP).
4. Copiez `.env.example` vers `.env` puis renseignez vos valeurs.

Exemple:

```env
GMAIL_ADDRESS=votre_mail@gmail.com
GMAIL_APP_PASSWORD=votre_mot_de_passe_application
IMAP_HOST=imap.gmail.com
IMAP_PORT=993
IMAP_SSL=true
IMAP_SSL_VERIFY=true
IMAP_FOLDER=INBOX
```

Variables prises en charge:
- `GMAIL_ADDRESS`: adresse Gmail
- `GMAIL_APP_PASSWORD`: mot de passe d'application Google
- `IMAP_HOST`: serveur IMAP (Gmail: `imap.gmail.com`)
- `IMAP_PORT`: port IMAP (Gmail SSL: `993`)
- `IMAP_SSL`: `true` ou `false`
- `IMAP_SSL_VERIFY`: `true` ou `false` (laisser `true` sauf diagnostic local)
- `IMAP_FOLDER`: dossier a lire (par defaut `INBOX`)

Important:
- ne committez jamais `.env`
- ne partagez jamais votre mot de passe d'application

## 5) Verifier la connexion IMAP

```bash
python -m src.cli index
```

Sortie attendue:
- tableau des derniers mails avec date, expediteur, taille de corps texte, nombre de pieces jointes, objet

Exemple valide (Round 1):

```text
┌──────────────────┬───────────────────────────────────────────────────────────┬─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ Date             │ Expediteur                                                │ Objet                                                                                                                   │
├──────────────────┼───────────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ 2026-07-12 11:34 │ Google <no-reply@accounts.google.com>                     │ Alerte de securite                                                                                                      │
│ 2026-07-12 11:17 │ Leader <noreply@communities.kajabimail.com>               │ Leader is live on SAATM Virtual Academy | July 12                                                                       │
│ 2026-07-12 11:01 │ Agone <editions@agone.org>                                │ Un 14 juillet, il y a 237 ans [LettrInfo 26-XXI]                                                                        │
│ 2026-07-12 10:50 │ Votre alerte Cadremploi <offres@alertes.cadremploi.fr>    │ 1 offre a ne rater sous aucun pretexte                                                                                  │
│ 2026-07-12 10:43 │ Alertes Google Scholar <scholaralerts-noreply@google.com> │ Nietzsche - de nouveaux resultats sont disponibles                                                                      │
│ 2026-07-12 10:43 │ Alertes Google Scholar <scholaralerts-noreply@google.com> │ "stanley cavell" - de nouveaux resultats sont disponibles                                                               │
│ 2026-07-12 10:15 │ Indeed <donotreply@match.indeed.com>                      │ Chef de Projet Supervision Transport Supervision Aide a l'Exploitation (SAE) MAV - F/H (D&I/TSI) - RATP EPIC          │
│ 2026-07-12 10:01 │ Indeed <donotreply@match.indeed.com>                      │ Responsable maitrise d'oeuvre outillage, telemaintenance et supervision pour le Grand Paris - F/H (DSI/TSI) - RATP EPIC │
│ 2026-07-12 09:49 │ Alertes LinkedIn Jobs <jobalerts-noreply@linkedin.com>    │ Blockchain / Cryptocurrency Project Lead [Full Stack and AWS] chez OREBiT                                               │
│ 2026-07-12 09:49 │ Alertes LinkedIn Jobs <jobalerts-noreply@linkedin.com>    │ Alternant(e) REDACTEUR ET CREATEUR DE CONTENUS VIDEOS chez Cite internationale universitaire de Paris                  │
└──────────────────┴───────────────────────────────────────────────────────────┴─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

Round 2 (etape 2 de la roadmap):
- `index` recupere aussi le corps texte (parties `text/plain`) et les pieces jointes de base
- la table affiche maintenant deux colonnes supplementaires:
	- `Corps (car)` = taille en caracteres du corps texte extrait
	- `PJ` = nombre de pieces jointes detectees

Commande de test Round 2 (20 derniers mails):

```bash
python.exe -m src.cli index --limit 20
```

## 5.b) Tester l'etape 3 (extraction PDF / DOCX / OCR)

Commande de test:

```bash
python.exe tests/run_extractor_examples.py
```

Ce script:
- genere des fichiers exemples dans `tests/samples`
- verifie extraction texte DOCX
- verifie extraction texte PDF
- verifie OCR image (ou affiche `SKIP` si Tesseract n'est pas installe/configure)

Exemple de sortie Round 2:

```text
┌──────────────────┬───────────────────────────────────────────────────────────┬─────────────┬────┬─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ Date             │ Expediteur                                                │ Corps (car) │ PJ │ Objet                                                                                                                       │
├──────────────────┼───────────────────────────────────────────────────────────┼─────────────┼────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ 2026-07-12 11:34 │ Google <no-reply@accounts.google.com>                     │         809 │  0 │ Alerte de securite                                                                                                          │
│ 2026-07-12 11:17 │ Leader <noreply@communities.kajabimail.com>               │        3167 │  0 │ Leader is live on SAATM Virtual Academy | July 12                                                                           │
│ 2026-07-12 11:01 │ Agone <editions@agone.org>                                │       11809 │  0 │ Un 14 juillet, il y a 237 ans [LettrInfo 26-XXI]                                                                            │
│ 2026-07-12 10:50 │ Votre alerte Cadremploi <offres@alertes.cadremploi.fr>    │           0 │  0 │ 1 offre a ne rater sous aucun pretexte                                                                                      │
│ 2026-07-12 10:43 │ Alertes Google Scholar <scholaralerts-noreply@google.com> │           0 │  0 │ Nietzsche - de nouveaux resultats sont disponibles                                                                          │
│ 2026-07-12 10:43 │ Alertes Google Scholar <scholaralerts-noreply@google.com> │           0 │  0 │ "stanley cavell" - de nouveaux resultats sont disponibles                                                                   │
│ 2026-07-12 10:15 │ Indeed <donotreply@match.indeed.com>                      │        7877 │  0 │ Chef de Projet Supervision Transport Supervision Aide a l'Exploitation (SAE) MAV - F/H (D&I/TSI) - RATP EPIC                │
│ 2026-07-12 10:01 │ Indeed <donotreply@match.indeed.com>                      │        8051 │  0 │ Responsable maitrise d'oeuvre outillage, telemaintenance et supervision pour le Grand Paris - F/H (DSI/TSI) - RATP EPIC     │
│ 2026-07-12 09:49 │ Alertes LinkedIn Jobs <jobalerts-noreply@linkedin.com>    │       10065 │  0 │ Blockchain / Cryptocurrency Project Lead [Full Stack and AWS] chez OREBiT                                                   │
│ 2026-07-12 09:49 │ Alertes LinkedIn Jobs <jobalerts-noreply@linkedin.com>    │        5227 │  0 │ Alternant(e) REDACTEUR ET CREATEUR DE CONTENUS VIDEOS chez Cite internationale universitaire de Paris                       │
│ 2026-07-12 09:49 │ Alertes LinkedIn Jobs <jobalerts-noreply@linkedin.com>    │        9877 │  0 │ CNIL recrute a Ville de Paris                                                                                               │
│ 2026-07-12 09:49 │ Alertes LinkedIn Jobs <jobalerts-noreply@linkedin.com>    │        9975 │  0 │ Artificial Intelligence Engineer chez Reply                                                                                 │
│ 2026-07-12 09:49 │ Alertes LinkedIn Jobs <jobalerts-noreply@linkedin.com>    │       10030 │  0 │ Artificial Intelligence Engineer chez Reply                                                                                 │
│ 2026-07-12 09:46 │ Archana sur Facebook <friendupdates@facebookmail.com>     │         853 │  0 │ Pour vous : votre ami(e) Archana Pandey a partage la publication de Rishibha Tiwari                                         │
│ 2026-07-12 09:42 │ Indeed <donotreply@match.indeed.com>                      │        7684 │  0 │ Responsable des Systemes d'Information H/F - remplacement - GROUPE ESRA                                                     │
│ 2026-07-12 09:36 │ Indeed <donotreply@match.indeed.com>                      │        7432 │  0 │ Conseil en Reglementation ESP/ESPN F/H - EDF                                                                                │
│ 2026-07-12 09:30 │ AOC (Analyse Opinion Critique) <contact@aoc.media>        │        1408 │  0 │ 6 mois pour 1EUR, plus que quelques jours...                                                                                │
│ 2026-07-12 09:05 │ Philosophie magazine <infolettres@redaction.philomag.com> │       16353 │  0 │ Marine Le Pen hors surveillance, la regle d'or du football et le cerveau de Putnam... La semaine de "Philosophie magazine" │
│ 2026-07-12 08:06 │ Indeed <donotreply@match.indeed.com>                      │        7449 │  0 │ Chef de Projet CVC - Macro-Lot - H/F - NEO2 Consultant                                                                      │
│ 2026-07-12 07:49 │ Alertes LinkedIn Jobs <jobalerts-noreply@linkedin.com>    │        9867 │  0 │ CNIL recrute a France                                                                                                       │
└──────────────────┴───────────────────────────────────────────────────────────┴─────────────┴────┴─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

## 6) Arborescence

```text
.
├── README.md
├── requirements.txt
├── .env.example
├── .gitignore
├── config/
│   └── settings.yaml
├── src/
│   ├── __init__.py
│   ├── mail_connector.py
│   ├── extractor.py
│   ├── indexer.py
│   ├── structured_store.py
│   ├── llm.py
│   ├── query_engine.py
│   ├── actions.py
│   └── cli.py
├── app_streamlit.py
├── data/
└── tests/
```

## 7) Confidentialite et donnees sensibles

Le projet manipule potentiellement des donnees personnelles (emails, finances, documents). L'objectif est un fonctionnement local-first (modele local via Ollama), sans envoi externe des contenus mail.
