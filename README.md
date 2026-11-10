# Rapport d'Itération 2 - Projet HELBIncognito

**Étudiant :** ALINIA Sacha
**Date :** 10 novembre 2026

## 1. Feedback reçu lors de l'itération précédente

//

## 2. État actuel du projet

- Nouvelle app `game` : modèles Game, GamePlayer, Round, RoundAlias, Message, Vote, Script
- Contraintes d'intégrité en base : un vote par joueur et par manche, pas d'auto-vote,
  pseudo unique par manche, pas de doublon de joueur dans une partie
- Enregistrement des modèles dans l'admin Django
- Page d'accueil : parties rejoignables triées par nombre de joueurs décroissant
- Formulaire « Nouvelle partie » (nom, description, manches, durée, cooldown,
  longueur max, joueurs minimum)
- Page de détail d'une partie et bouton « Rejoindre »
- Script `run.sh` fonctionnel sur la VM Ubuntu
- Diagramme entité-relation (image jointe)

## 3. Difficultés rencontrées

- Fusion d'historiques Git (conflits add/add) lors du premier push
- Remplacement de l'app `blog` du tutoriel par `game` (erreurs NoReverseMatch)
- Compatibilité avec Python 3.8 / Django 4.2 de la VM
- (Ajoute les tiennes)

## 4. Prochaines tâches

| Tâche | Estimation |
|---|---|
| Démarrage automatique de la partie + création des manches | à compléter |
| Pseudos aléatoires par manche | à compléter |
| Chat en temps réel + cooldown | à compléter |
| Votes et calcul du gagnant | à compléter |
| Agents IA et section Scripts | à compléter |
| Profil et graphiques d'activité | à compléter |
| Parties finies et récapitulatif | à compléter |