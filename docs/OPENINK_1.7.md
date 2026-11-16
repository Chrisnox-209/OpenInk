# OpenInk 1.7.0 : apparence et démarrage discret

## Réglages

- Un encart **Apparence** distinct de la connexion regroupe la langue et les
  boutons **Clair / Sombre**. Les choix sont appliqués et enregistrés immédiatement.
- Le thème sombre utilise des gris anthracite inspirés de Discord, avec des
  panneaux distincts, du texte clair et des accents violets. Il couvre les cinq
  vues, les champs, les menus et les dialogues, y compris l’avertissement OpenFlow.
- Un interrupteur **Lancer minimisé à la connexion** remplace la case de démarrage.
  Il est utilisable à la souris, avec Espace ou Entrée et conserve la préférence.
- Le bouton **? bleu** ouvre une explication du suivi en arrière-plan.

Le démarrage désactivé n’arrête pas le suivi de la session actuelle. Au prochain
login, OpenInk ne sera pas lancé automatiquement ; l’utilisateur pourra l’ouvrir
manuellement. Avec l’option activée, l’icône et l’agent démarrent sans fenêtre.

L’historique continu et les alertes nécessitent une session et un agent actifs.
Au retour d’une période sans lecture, les compteurs peuvent retrouver le total
des pages, sans recréer les heures exactes des impressions. L’ordinateur éteint
ne reçoit aucune notification. L’aide donne ces explications dans les trois langues.

## Données et matériel

Le thème ne change que la présentation. Les compteurs, les niveaux, les profils
et les historiques sont conservés. Le firmware et son manifeste sont inchangés :
cette mise à jour n’exige aucun nouveau flash. Les PDF de test restent adaptés au
papier blanc et ne dépendent pas du thème de la fenêtre.

## Validation

117 tests hors ligne couvrent notamment la conservation des données et des
préférences, les entrées invalides, le contraste des textes sombres et les
régressions existantes. Les cinq vues et les contrôles sont vérifiés dans les
deux thèmes et les trois langues, avec une base en mémoire et sans accès matériel.
Les captures publiques utilisent des valeurs fictives.

Aucun flash ni travail d’impression réel n’est effectué pour cette mise à jour.
