# Avertissement — portages Windows et macOS expérimentaux

**LES VERSIONS WINDOWS ET macOS NE SONT PAS TESTÉES SUR LEURS SYSTÈMES NATIFS.
Leur bon fonctionnement n’est pas garanti. Elles sont publiées comme préversions
expérimentales, pour évaluation uniquement.**

- **Windows 10/11 x64 :** l’exécutable et des tests logiciels ont été vérifiés
  sous Wine, sur Linux. Aucun essai sur un vrai PC Windows n’a été réalisé.
  L’USB, l’impression papier, les notifications Windows et le flash OpenFlow
  sur ce système restent non validés.
- **macOS Intel et Apple Silicon :** le kit a été préparé sous Linux, avec des
  tests simulés et une vérification des dépendances. Aucune compilation native
  ni exécution sur un Mac n’a été réalisée. Le kit ne contient pas de `.app`
  déjà compilé. L’interface Aqua, les notifications, l’USB, l’impression et
  le flash restent non validés sur macOS.

Les tests automatiques, les simulations et Wine ne remplacent pas une recette
sur les systèmes et les appareils réels. Aucun test de ces portages n’a envoyé
de travail d’impression ou de commande firmware à une imprimante.

OpenInk est fourni sans garantie de bon fonctionnement de ces portages.
Les niveaux d’encre restent estimatifs. **Un flash peut bloquer l’imprimante** :
conserver les sauvegardes et ne pas considérer les parcours Windows/macOS comme
validés pour une opération sur un appareil réel. Les confirmations de risque,
de connexion USB et la sauvegarde préalable restent obligatoires.

Cet avertissement concerne les portages Windows/macOS de cette préversion ;
les validations historiques de la version Ubuntu sont décrites séparément.

## English

**THE WINDOWS AND macOS PORTS HAVE NOT BEEN TESTED ON THEIR NATIVE OPERATING
SYSTEMS. They are experimental prereleases and their correct operation is not
guaranteed.** Windows software checks were performed under Wine on Linux only.
The macOS kit has neither been built natively nor run on a Mac, and includes
no compiled `.app`. Automated tests and simulations do not validate real USB,
printing, native notifications or OpenFlow flashing. Firmware flashing can
brick the printer. Keep backups and do not treat these ports as validated
for real-device firmware operations.

## Español

**LOS PORTES PARA WINDOWS Y macOS NO SE HAN PROBADO EN SUS SISTEMAS NATIVOS.
Son versiones preliminares experimentales y no se garantiza su funcionamiento.**
Las comprobaciones de Windows se realizaron únicamente con Wine sobre Linux.
El kit macOS no se ha compilado ni ejecutado en un Mac y no incluye una `.app`
compilada. Las pruebas automáticas y simulaciones no validan el USB, la impresión,
las notificaciones nativas ni la programación OpenFlow reales. El flasheo puede
bloquear la impresora. Conserva las copias de seguridad y no consideres estos
portes validados para programar el firmware de un dispositivo real.
