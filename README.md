# Serveur Minitel (Asterisk + modem V.23 logiciel)

```
Minitel ──RJ11── HT802v2 (192.168.1.56) ──SIP/RTP A-law── Asterisk (docker, host net)
                                                               │ AudioSocket 127.0.0.1:4040
                                                               ▼
                                                  modem V.23 Python (docker) ── services Minitel
PC softphone ──SIP── Asterisk        trunk SIP OVH ──SIP── Asterisk
```

* `asterisk/` : image Ubuntu 24.04 + Asterisk 20, config PJSIP/dialplan (`asterisk/etc`).
* `modem/` : modem V.23 (1200/75 bauds, 7E1) en numpy + serveur vidéotex (`minitel_modem/services.py`).
* `modem/tests/loopback.py` : test DSP hors ligne ; `modem/tests/sim_client.py` : faux Minitel à travers Asterisk.

## Lancer
    docker compose up -d --build
    docker logs -f minitel-modem          # connexions, porteuse Minitel, niveaux
    docker exec minitel-asterisk asterisk -rvvv

Les appels sont enregistrés en WAV dans `data/calls/` (`*-rx.wav` = ce que le Minitel émet, `*-tx.wav` = ce que
le serveur émet) pour déboguer.

## Réglages HT802v2 (FXS port 1)
* Primary SIP Server `192.168.1.10`, SIP User ID `minitel`, Registration **No** (ou Yes sans mot de passe).
* Offhook Auto-Dial : `3615` (touche Connexion/Fin = décroché → appel immédiat du serveur).
* Preferred Vocoder : PCMA uniquement ; Silence Suppression **No** ; Echo canceller (LEC) **No** ;
  Jitter buffer fixe ; Fax mode : pass-through / désactiver la détection de tonalités fax ; DTMF RFC2833.

## Numéros internes
| Depuis | Numéro | Effet |
|---|---|---|
| Minitel / PC | `3615` (n'importe quel `36xx`) | serveur Minitel (modem) |
| Minitel | `100` | sonne le softphone du PC |
| Minitel / PC | `0…` (ex. `0972101721` = MiniPavi) | sortie via OVH |
| PC | `101` | sonne la ligne Minitel (HT802) |
| PC | `600` | test d'écho |
| OVH (appel entrant) | – | serveur Minitel |

## Softphone PC
Compte SIP : serveur `192.168.1.10`, utilisateur `pc`, mot de passe = `PC_PASSWORD` du fichier `.env`.

## OVH
Renseigner `OVH_PASSWORD` dans `.env` puis `docker compose up -d`. L'IP publique est détectée automatiquement
(sinon `EXTERNAL_IP=`).
