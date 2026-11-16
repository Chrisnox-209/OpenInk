# V2 : portée, contrôles et reprise

## Fonction réelle

La V2 historique modifie le comportement global des quatre couleurs sur une
XP-2200 IU05P2 compatible. Elle ne réécrit pas les puces et ne réalise pas de
reset physique sélectif. Les valeurs Epson à 100 % sont simulées ; le programme
maintient une estimation indépendante depuis les déclarations de remplissage.
Des cartouches physiquement sans puce n’ont pas été validées.

La sélection de couleurs ajuste seulement le registre local après vérification.
Sans encre ajoutée, l’estimation est conservée. Une V2 déjà installée ne demande
pas un nouveau flash pour chaque remplacement de cartouche.

## Ressources épinglées

| Élément | SHA-256 |
| --- | --- |
| Charge utile V2 décompressée | `413718a144f982fcae8d6e9c2a3adc82d0aafd99dbcb635105411c22f53348ef` |
| Manifeste V2 d’OpenInk 1.4 | `268d46f9ef07524c9a80ba2c7919e43ba89fed0988a3b706364949a44eb6a3a4` |

Version attendue : `06.58.IU05P2.FY22`. Le chargement vérifie taille et empreintes
hors ligne. Le programme refuse une image arbitraire ou une ressource altérée.
La V3 expérimentale et les outils de recherche ne sont pas distribués ici.

## Avant transfert

Le contrôleur impose l’USB normal `04b8:11b1`, l’identité attendue, une version
connue, les files vides et une sauvegarde complète avant écriture. L’utilisateur
doit confirmer le flash, accepter ses risques et confirmer une liaison USB
directe. Une couleur sans repère d’encre empêche le lancement tant qu’elle
n’est pas initialisée.

L’accès est exclusif, le suivi ordinaire est suspendu et une inhibition de
veille accompagne l’opération. Ne pas imprimer, fermer la session, couper
l’alimentation ou retirer l’USB tant que la fin n’est pas confirmée.

## Après transfert

Après un acquittement exact, le contrôleur observe les attributs USB en cache
système sans ouvrir le canal : nouvelle génération normale au port vérifié,
stable trois secondes, et au moins dix secondes après le commit. Si ce retour
est observé sous 90 secondes, le contrôle ciblé vérifie :

- les cinq secteurs modifiés, soit 327 680 octets ;
- les 192 Kio du secours, l’en-tête principal et la clé attendue ;
- les fenêtres de code RAM modifiées, la série, la version et le mode attendu.

Ce contrôle ne compare pas chaque octet non modifié. En cas d’acquittement
manquant, de retour USB incertain ou d’erreur, le résultat n’est pas déclaré
réussi : l’attente prudente jusqu’à quinze minutes et les conditions de
vérification complète s’appliquent. Un délai expiré ne signifie pas à lui seul
que l’imprimante est prête.

Après succès ciblé, la vérification complète reste disponible en lecture seule.
Le suivi ne reprend qu’après un résultat reconnu ; la calibration est appliquée
une seule fois et déduit les pages éventuellement imprimées dans l’intervalle.

## Incident ou interruption

Conserver `~/.local/share/inkora/firmware/` et sa sauvegarde avant transfert.
Suivre la vérification proposée, sans programmer une seconde fois par réflexe.
Le logiciel ne recommence jamais un upload ou un commit automatiquement après
une interruption. Une sauvegarde n’est pas une garantie de récupération.
Ce dépôt ne fournit pas d’outil de récupération Windows ou de procédure SPI.

## Limites

V2 a été imprimée et vérifiée sur l’appareil de développement. La nouvelle
reconnaissance anticipée du redémarrage reste validée sur transport simulé ;
la vérification ciblée a été exécutée en lecture seule sur une V2 réelle.
Ces résultats ne garantissent ni chaque imprimante ni chaque compatible.
Le suivi d’encre reste estimatif et ne remplace pas le contrôle de qualité.
