# Rapport d'Itération 1 - Projet HELBIncognito

**Nom du projet :** HELBIncognito
**Module / Cours :** Projet Web II
**Étudiant(s) :** ALINIA Sacha
**Date :** 2 novembre 2026

---

## 1. Feedback reçu lors de l'itération précédente

* **Remarques principales  :**
  * /
* **Actions correctives entreprises :**
  * /

---

## 2. État actuel du projet (Fonctionnalités implémentées)

Le projet **HELBIncognito** est développé sous le framework **Django**. L'architecture globale est opérationnelle et s'articule autour des composants suivants :

### 2.1 Architecture & Infrastructure

* **Configuration initiale de Django (`HELBIncognito/`) :** Paramétrage des réglages principaux, gestion des variables globales et routage principal de l'application.
* **Base de données (`db.sqlite3`) :** Modélisation relationnelle configurée et premières migrations exécutées avec succès.

### 2.2 Applications & Fonctionnalités d'ores et déjà développées

#### A. Gestion des utilisateurs (`users/`)

* [X] **Création de compte / Inscription :** Formulaire de création de compte utilisateur.
* [X] **Authentification & Connexion :** Système de login/logout sécurisé fourni par Django.
* [X] **Gestion des profils :** Gestion des informations utilisateur et droits d'accès.
* [X] **Page Administrateur :** Gestion globale en mode admin.

#### B. Publications (`blog/`)

* [X] **Publication de billets / messages :** Création et affichage des publications.
* [X] **Lecture des fils d'actualité / posts :** Vue d'ensemble des posts publiés.

---

## 3. Difficultés rencontrées

Pendant le développement de cette itération, j'ai fait face à plusieurs défis techniques et organisationnels :

1. **Prise en main des bases de Django :**
   Il a été difficile au départ d'assimiler les concepts fondamentaux du framework Django (architecture MVT, gestion des requêtes, ORM, etc.) et de comprendre comment connecter proprement les différentes briques du projet.
2. **Suivi et compréhension des tutoriels (Corey Schafer) :**
   La formation s'est appuyée sur la série de cours vidéo de Corey Schafer. Il n'était pas toujours évident de saisir l'ensemble des détails techniques de chaque vidéo, ce qui a demandé d'être extrêmement attentif, de faire des pauses fréquentes et de retravailler soigneusement les concepts pour pouvoir les appliquer à mon propre projet.

---

## 4. Prochaines tâches à réaliser

Voici la feuille de route pour les prochaines itérations :

| Tâche / Fonctionnalité                   | Description                                                          | Application / Module |
| :----------------------------------------- | :------------------------------------------------------------------- | :------------------- |
| **Posts**                            | Permettre d'interagir et réagir anonymement sur chaque publication. | `blog`             |
| **Amélioration UI/UX**              | Refonte de l'interface graphique et responsive design.               | Templates / CSS      |
| **Tests unitaires & d'intégration** | Écriture des tests pour les vues et les formulaires clés.          | `tests.py`         |
