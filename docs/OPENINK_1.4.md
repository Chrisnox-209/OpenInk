# OpenInk 1.4.0-beta1 : modifications et validation

Version préparée le 16 novembre 2026. Première version du dépôt Linux autonome,
issue de l’application Inkora. Aucun comportement du firmware n’est modifié
pour le passage à OpenInk.

## Interface

- Nom, lanceur et notifications OpenInk ; chemins et alias Inkora conservés.
- Logo CMJN vectoriel original, icônes jusqu’à 1024 px et page A4 vectorielle.
- Jauges et progression mesurable en pourcentage.
- Choix d’un moniteur, taille initiale d’environ 58 % de sa surface, minimum
  d’environ 46 % ; textes et contrôles adaptés à la taille.
- Dialogues défilants avec actions accessibles ; correction de la prise de
  focus Tk avant visibilité et des références à une fenêtre détruite.

## Impression et firmware

La page de test exige une sélection de file et un clic explicite. Une seule
copie est envoyée ; ni file par défaut implicite, ni suppression de travaux,
ni renvoi automatique. La démo ne consulte pas CUPS et n’imprime rien.

Le flash garde l’image V2 historique inchangée. Acceptation des risques et
confirmation USB sont obligatoires. Le contrôle ciblé permet de terminer
après un retour normal confirmé ; le repli prudent et la sauvegarde préalable
restent en place. Une vérification complète reste accessible après succès.

## Vérifications réalisées

| Contrôle | Résultat et limites |
| --- | --- |
| Tests unitaires | 90 tests hors ligne : consommation, réserve, migration, agent, IPC, dialogues, impression simulée et contrôleur firmware |
| Interface | Cinq vues et formulaires contrôlés en démo, sans accès matériel ; minimum mesuré à 46,24 % d’un moniteur 5120 × 2880 |
| V2 historique | Installation et vérification complète réussies avec la bêta précédente sur l’appareil de développement |
| Contrôle ciblé réel | Lecture seule de la V2 installée : 32,26 secondes ; état prêt et mode attendu |
| Nouveau retour USB anticipé | Validé avec horloge et transport simulés ; pas de nouveau flash réel pour cette branche |
| Image | Comparaison hors ligne : toutes les différences attendues du programme principal restent dans les cinq secteurs couverts |
| Page de test | Une page A4, couleurs et disposition contrôlées ; les tests de soumission CUPS utilisent des doublures |
| Ubuntu | Paquet construit, extrait, inspecté et lancé en démo ; construction autonome vérifiée depuis le dépôt |

Les fichiers de preuve privés, identités de l’appareil, captures utilisateur
et sauvegardes ne sont pas publiés dans ce dépôt. Aucun flash ou travail
d’impression réel n’est envoyé par la suite de tests.

## Construction du dépôt autonome

Les scripts ne dépendent plus de l’arborescence de recherche d’origine. Le
générateur graphique utilise la racine du dépôt et l’archive sources inclut
les notices et la documentation courante. Le firmware fourni et tous les
modules exécutés par l’application restent ceux d’OpenInk 1.4 préparé.

## Références techniques

- [Options CUPS](https://www.cups.org/doc/options.html) : soumission PDF, file,
  nombre de copies et options explicites.
- [Support Epson XP-2200](https://www.epson.eu/en_EU/support/sc/epson-expression-home-xp-2200/s/s2530) :
  précautions et liaison USB pour la récupération firmware.
- [Epson Software Updater](https://epson.com/Support/wa00603a) : attendre la fin
  de la mise à jour et ne pas couper l’alimentation pendant l’opération.

Les instructions Epson ne valident pas à elles seules la branche de détection
anticipée de ce contrôleur ; ses conditions et limites sont décrites dans
[PERIMETRE_V2.md](PERIMETRE_V2.md).
