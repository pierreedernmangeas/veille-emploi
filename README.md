# Veille emploi

Veille d'offres d'emploi automatique (achats, supply chain : France, Europe, V.I.E, graduate programmes), 3 fois par jour sur GitHub Actions.

- **Collecte** : LinkedIn (Apify, JobSpy, mails d'alerte), Indeed, HelloWork, Welcome to the Jungle, APEC, Cadremploi, Jobijoba,
  France Travail et Adzuna (si clés), Mon V.I.E, et environ 150 sites carrières d'entreprises.
- **Tri** : dédoublonnage entre sources et entre veilles, filtres (stage, senior, langue, zone, expérience), note sur 10.
- **Candidatures** : CV et lettre en PDF pour les meilleures offres (rédaction IA contrôlée, sinon moteur sans IA), brouillons
  Gmail quand l'annonce donne une adresse, relance en brouillon à J+7. Rien n'est jamais envoyé à un recruteur automatiquement.
- **Suivi** : Google Sheet « Veille emploi » et mail récapitulatif.

Le moteur de CV (données personnelles) n'est pas dans ce dépôt : il est téléchargé depuis Google Drive à chaque veille.
Mise en place : [docs/MISE_EN_PLACE.md](docs/MISE_EN_PLACE.md). Réglages : `config.yaml` et `recherches.yaml`.

Essai local (sources réelles, Google factice) : `python -m veille.principal --moment matin --essai`.
