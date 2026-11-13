# Mise en place de la veille emploi (une seule fois, environ 1 heure)

La veille tourne seule sur GitHub 3 fois par jour (résultats vers 7 h 30, 13 h 45 et 19 h, heure de Paris). Elle a besoin de quelques
clés, que **toi seul** colles dans GitHub. Ne les envoie à personne, pas même dans une conversation.

## 1. Accès Google (compte pro, 20 min)

1. Va sur https://console.cloud.google.com, connecté avec **ton adresse Gmail pro**, et crée un projet « veille-emploi ».
2. « API et services » > « Bibliothèque » : active **Google Drive API**, **Google Sheets API**, **Gmail API**.
3. « Écran de consentement OAuth » : type **Externe**, nom « Veille emploi », ton adresse pro en contact ; ajoute ton adresse pro dans
   « Utilisateurs test » ; enregistre.
4. Toujours sur l'écran de consentement : **« Publier l'application »** (statut « En production »). Sinon le jeton expire tous les 7 jours.
5. « Identifiants » > « Créer des identifiants » > « ID client OAuth » > type **Application de bureau**. Télécharge le fichier JSON.
6. Sur ton Mac, dans le Terminal :
   ```bash
   pip3 install google-auth-oauthlib
   ```
   ```bash
   python3 outils/obtenir_jeton.py ~/Downloads/client_secret_XXXX.json
   ```
   Choisis ton compte pro. Si Google affiche « application non validée » : « Paramètres avancés » > « Accéder à Veille emploi »
   (c'est ta propre application). Garde la ligne affichée entre les tirets : c'est le secret `GOOGLE_TOKEN`.

## 2. Apify (LinkedIn, 5 min)

Compte gratuit sur https://apify.com > « Settings » > « API & Integrations » > copie **Personal API token** : secret `APIFY_TOKEN`.
L'offre gratuite donne 5 $ de crédit par mois ; la veille s'arrête d'elle-même à 4,50 $.

## 3. Gemini (CV et lettres, 2 min)

https://aistudio.google.com/apikey > « Create API key » : secret `GEMINI_API_KEY`.

## 4. Facultatif (plus d'offres)

- France Travail : compte sur https://francetravail.io, crée une application, abonne-la à « API Offres d'emploi v2 » :
  secrets `FT_CLIENT_ID` et `FT_CLIENT_SECRET`.
- Adzuna : compte sur https://developer.adzuna.com : secrets `ADZUNA_APP_ID` et `ADZUNA_APP_KEY`.
- Mon V.I.E : sur mon-vie-via.businessfrance.fr, F12 > Réseau > filtre « search » > copie l'en-tête `X-API-KEY` : secret `VIE_API_KEY`.

## 5. Coller les clés dans GitHub

Dépôt `veille-emploi` > « Settings » > « Secrets and variables » > « Actions » > « New repository secret », une fois par clé :
`GOOGLE_TOKEN`, `APIFY_TOKEN`, `GEMINI_API_KEY`, `VEILLE_IDS` (fourni par Claude, avec ta propre adresse Gmail pro dans la clé « compte »), et les facultatifs ci-dessus.

## 6. Alertes LinkedIn (10 min)

Ouvre `docs/ALERTES_LINKEDIN.md` : pour chaque lien, ouvre-le connecté à LinkedIn, clique « Créer une alerte », fréquence
« Dès que possible » (sinon « Quotidienne »), réception **par e-mail**. La veille lit ces mails sans les marquer lus.

## 7. Lancer et vérifier

1. Dépôt > « Actions » > « Veille emploi » > si GitHub le demande, « I understand my workflows, go ahead and enable them ».
2. « Run workflow » > moment **matin** > « Run workflow ». Le premier passage dure environ 45 min à 1 h 15 (import de ton historique,
   offres des 7 derniers jours, au plus 40 CV + lettres).
3. Une fois la coche verte :
   - **Sheet « Veille emploi »** (Drive > Recherche emploi) : onglet **À postuler** (note, poste, entreprise, liens CV / lettre / dossier,
     brouillon, statut), **Toutes les offres**, **Sources** (combien d'offres par source, erreurs), **Entreprises** (sites carrières :
     tu peux y ajouter une ligne « Entreprise / Adresse » de page carrières, elle sera interrogée dès la veille suivante).
   - **Drive > Recherche emploi > Veille** : un dossier par offre (CV, lettre, Annonce_et_analyse.txt).
   - **Gmail > Brouillons** : une candidature prête (CV + lettre joints) pour chaque offre qui donne une adresse mail.
     Relis, puis clique « Envoyer » toi-même. Rien n'est jamais envoyé à un recruteur sans toi.
   - **Le mail récap** dans ta boîte : les 10 meilleures offres et les sources en erreur.
4. Ensuite tout est automatique : 06:47, 13:17 et 18:37 (heure de Paris, été comme hiver).

## Au quotidien

- Postuler : ouvre « À postuler », clique le lien de l'offre, joins le CV et la lettre du dossier (ou envoie le brouillon Gmail).
- Le statut se met à jour seul : **Envoyée** (dès que tu envoies le brouillon), **Réponse reçue**, **Relance prête** (brouillon de
  relance 7 jours après, dans le même fil, à envoyer toi-même), **Relancée**. Pour une candidature faite sur un site, écris
  « Envoyée » et la date dans la ligne.
- Une case « À relire » apparaît quand l'IA n'a pas pu tout écrire : la version de repli (moteur v12) est complète, mais relis-la.

## Si quelque chose ne va pas

- Coche rouge dans « Actions » : ouvre le passage, le message dit quoi faire (jeton d'un autre compte, moteur absent du Drive…).
- Jeton Google expiré (« invalid_grant ») : vérifie que l'application est « En production » (étape 1.4), refais l'étape 1.6 et
  remplace le secret `GOOGLE_TOKEN`.
- Une source en erreur dans l'onglet « Sources » n'arrête jamais les autres ; si elle reste en erreur plusieurs jours, dis-le à Claude.
- GitHub coupe les tâches planifiées d'un dépôt public après 60 jours sans activité : la veille du matin se réactive elle-même
  chaque jour. Si tu reçois quand même un mail GitHub « scheduled workflow disabled », clique « Enable workflow » dans « Actions ».
- Une offre qui fait planter la fabrication du CV est retentée aux 3 veilles suivantes, puis laissée de côté (le récap le dit).
