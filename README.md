# HELBIncognito

Projet Django de Programmation Web II — HELB, BA2. Dernière mise à jour :
14 novembre 2026. Le socle comptes, authentification et présentation provient du
[tutoriel Django de Corey Schafer](https://github.com/CoreyMSchafer/code_snippets/tree/master/Django_Blog).
Les changements assistés par OpenAI Codex sont signalés dans le code.

## Fonctionnalités

- Parties Incognito paramétrables, joueurs et alias anonymes renouvelés à chaque
  manche ; démarrage automatique et clôture des manches par le serveur.
- Chat avec limite de longueur et cooldown ; vote obligatoire avec le premier
  message dès qu’un autre joueur est présent. Les égalités n’attribuent aucun point.
- Compte à rebours, vote courant, classement, historique et points par joueur
  pour chaque manche, avec distinction des joueurs arrivés plus tard.
- Profils publics avec graphique quotidien des parties jouées et gagnées. Les
  participations sont datées de l’arrivée et les victoires de la fin de partie ;
  seul le joueur ayant seul le meilleur score final est gagnant.
- Scripts privés réutilisables et agents Incognito configurables par leur joueur.
  Le choix de modèles dépend du fournisseur ; le prompt final est limité à
  2 000 caractères, script inclus.
- Modèle local CPU SmolLM2 et API Groq ; génération des décisions par un worker
  séparé, avec arrêt, invalidation des anciennes configurations et reprise après erreur.
- PokeClash : flux actualisé, envoi manuel autorisé et agent configurable avec
  exécution ponctuelle mise en file ou mode automatique. Les cooldowns sont partagés.

## Préparation et lancement

Python 3.10+ est requis. Les commandes suivantes ciblent Ubuntu ou WSL depuis le
dossier du projet. Les variables sont lues dans l’environnement du processus :
un fichier `.env` n’est **pas** chargé automatiquement.

**Limite actuelle d’installation :** `requirements.txt` est entièrement commenté.
Le point 1 sur les dépendances est hors périmètre de cette intervention ; le fichier
reste donc en l’état. Il faut reprendre ce point pour une installation neuve ;
les tests actuels utilisent un environnement virtuel existant qui contient déjà
Django et ses dépendances. `pip install -r requirements.txt` seul ne les installe donc pas.

Après préparation effective des dépendances :

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python manage.py migrate
```

Pour le modèle local, installer explicitement les dépendances CPU supplémentaires :

```bash
.venv/bin/python -m pip install -r requirements-local.txt
```

Les poids de `HuggingFaceTB/SmolLM2-135M-Instruct` sont téléchargés au premier appel
local explicite. La disponibilité mémoire, le réseau et le temps d’inférence
dépendent de la machine. Le modèle API utilise `GROQ_API_KEY` défini côté serveur.
Les identifiants disponibles figurent dans la liste de modèles du formulaire.

Définir les secrets dans le terminal de lancement, puis lancer le serveur et les
deux workers dans trois terminaux partageant ces variables :

```bash
export GROQ_API_KEY='YOUR_GROQ_KEY'
export HELBPLAYS_UID='YOUR_POKECLASH_UID'
export HELBPLAYS_KEY='YOUR_POKECLASH_KEY'
export HELBPLAYS_OWNER_USERNAME='YOUR_DJANGO_USERNAME'

.venv/bin/python manage.py runserver
# Deuxième terminal :
.venv/bin/python manage.py tick_games
# Troisième terminal :
.venv/bin/python manage.py run_agents
```

`tick_games` fait avancer les manches même sans navigateur connecté. `run_agents`
traite les agents activés et les exécutions PokeClash mises en file ; le simple
affichage d’une page ne déclenche pas de modèle. Pour Incognito, rejoindre une
partie puis enregistrer ses réglages dans **Your Incognito agent**. **Stop agent**
désactive le joueur et invalide une décision encore en cours. Les erreurs et la
dernière tentative sont visibles sur la page.

Le script `bash run.sh` effectue la préparation prévue, applique les migrations
puis démarre les deux workers et le serveur ; il dépend de la correction du point
sur `requirements.txt` pour fonctionner dans un environnement vierge.

Options utiles :

```bash
.venv/bin/python manage.py run_agents --dry-run
.venv/bin/python manage.py run_agents --once --incognito-only
.venv/bin/python manage.py tick_games --once
```

`--dry-run` donne uniquement le nombre d’agents Incognito éligibles, sans écriture,
appel modèle ni action PokeClash. Un passage `--once` normal peut réellement jouer
pour les agents activés ; `--incognito-only` exclut PokeClash.

Les clés ne doivent pas être placées dans les prompts ou scripts. Sans
`HELBPLAYS_OWNER_USERNAME`, le contrôle du compte externe revient aux comptes staff
actifs ; un propriétaire explicite permet un compte Django ordinaire. Voir le
[guide PokeClash](docs/pokeclash.md) pour les limites du flux et des envois.

## Vérification et documentation

```bash
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --check --dry-run
.venv/bin/python manage.py test game users helbplays agents
```

Les tests Django s’exécutent avec une base de test et simulent les transports
externes. Ils n’envoient aucun message PokeClash réel. La VM de cours et les appels
avec clés réelles restent à valider séparément.

Validation du 14 novembre 2026 dans l’environnement WSL existant : **65 tests
réussis** ; aucun changement détecté par `makemigrations --check --dry-run`.

- [Architecture et responsabilités](docs/architecture.md)
- [Rapport d’itération 2 conservé](docs/iterations/iteration-2.md)
- [Brouillon d’itération 3 — 14 novembre 2026](docs/iterations/iteration-3-2026-11-14.md)

Pour un déploiement hors développement, définir `DJANGO_DEBUG=0`,
`DJANGO_SECRET_KEY` et `DJANGO_ALLOWED_HOSTS`. `DJANGO_DB_PATH` permet d’isoler une
base SQLite. Le serveur Django intégré sert au développement ; la validation du
déploiement final reste à effectuer sur l’environnement de cours.
