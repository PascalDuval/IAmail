# Mail IA Agent (Gmail, local-first)

Ce projet Python indexe des emails Gmail et leurs pieces jointes pour permettre des recherches en langage naturel, en gardant les donnees en local.

Etat actuel:
- setup du projet
- connexion IMAP Gmail
- commande CLI `index` pour afficher les 10 derniers mails de INBOX

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
- tableau des derniers mails avec date, expediteur et objet

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
