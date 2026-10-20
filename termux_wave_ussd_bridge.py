#!/usr/bin/env python3
"""
Pont USSD Wave pour Termux / Debian proot sur Android (wave-assistant).
S'exécute directement sur le téléphone dans l'environnement Python de l'utilisateur :
(venv) root@localhost:~/wave-assistant# python termux_wave_ussd_bridge.py

Fournit :
1. Une commande CLI autonome : python termux_wave_ussd_bridge.py --solde
2. Un endpoint HTTP local contrôlé (ex: Flask port 5001) consommable par l'agent IA.

Autorisations Android nécessaires :
- android.permission.CALL_PHONE (accordée à Termux ou via ADB)
- Accès stockage partagé /sdcard/ (termux-setup-storage)
"""

import os
import re
import sys
import time
import json
import subprocess
from datetime import datetime
from typing import Dict, Any, Optional, Tuple


class TermuxWaveUssdBridge:
    """Pont local d'exécution et d'extraction USSD pour Termux et Android natif."""

    def __init__(self, code_ussd_par_defaut: Optional[str] = None):
        code_env = os.environ.get("WAVE_CODE_SECRET")
        if code_ussd_par_defaut:
            self.code_ussd = code_ussd_par_defaut
        elif code_env:
            self.code_ussd = f"*9113*0*{code_env}#"
        else:
            self.code_ussd = "*9113#"
        # ffmpeg est utilise pour la capture non-bloquante (pas de uiautomator)
        self.chemin_ffmpeg = os.environ.get("FFMPEG_PATH", "ffmpeg")

    def declencher_appel(self, code_ussd: Optional[str] = None) -> bool:
        """Lance l'intention d'appel CALL_PHONE sur Android."""
        code = (code_ussd or self.code_ussd).strip()
        code_encode = code.replace("#", "%23")

        # Plusieurs méthodes d'appel selon l'environnement d'exécution (ADB, Termux, proot)
        commandes_testees = [
            ["am", "start", "-a", "android.intent.action.CALL", "-d", f"tel:{code_encode}"],
            ["termux-telephony-call", code],
            ["su", "-c", f"am start -a android.intent.action.CALL -d 'tel:{code_encode}'"]
        ]

        for cmd in commandes_testees:
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=5)
                if proc.returncode == 0:
                    return True
            except FileNotFoundError:
                continue
            except Exception:
                continue

        return False

    def fermer_dialogue(self) -> None:
        """Ferme la fenêtre modale MMI pour ne pas perturber l'écran."""
        try:
            subprocess.run(["input", "keyevent", "4"], capture_output=True, timeout=2)
        except Exception:
            pass

    def _capture_frame_ffmpeg(self) -> Optional[bytes]:
        """
        Capture un frame de l'ecran Android via le pipeline :
          adb exec-out screenrecord --output-format=h264 --time-limit=2 - | ffmpeg -i pipe:0 -vframes 1 -f image2pipe -vcodec png pipe:1

        Non-bloquant : le telephone reste totalement utilisable pendant la capture.
        Retourne les bytes PNG ou None en cas d'echec.
        """
        cmd_sr = ["adb", "exec-out", "screenrecord", "--output-format=h264", "--time-limit=2", "-"]
        cmd_ff = [self.chemin_ffmpeg, "-loglevel", "error", "-i", "pipe:0",
                  "-vframes", "1", "-f", "image2pipe", "-vcodec", "png", "pipe:1"]
        try:
            p_sr = subprocess.Popen(cmd_sr, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            p_ff = subprocess.Popen(cmd_ff, stdin=p_sr.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if p_sr.stdout:
                p_sr.stdout.close()
            png_bytes, _ = p_ff.communicate(timeout=12)
            p_sr.wait(timeout=5)
            return png_bytes if png_bytes and len(png_bytes) > 100 else None
        except Exception:
            return None

    def _ocr_depuis_frame(self, png_bytes: bytes) -> Optional[str]:
        """
        Lance pytesseract sur un frame PNG (en memoire) pour extraire le texte.
        Retourne le texte reconnu ou None si les bibliotheques ne sont pas disponibles.
        """
        try:
            import io
            from PIL import Image
            import pytesseract
            img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
            larg, haut = img.size
            zone = img.crop((int(larg * 0.05), int(haut * 0.08), int(larg * 0.95), int(haut * 0.45)))
            config = r"--oem 3 --psm 6"
            return pytesseract.image_to_string(zone, config=config, lang="fra")
        except Exception:
            return None

    def capturer_texte_mmi(self, timeout_secondes: float = 15.0) -> Tuple[Optional[str], Optional[str]]:
        """
        Attend que le dialogue USSD soit visible, puis capture l'ecran via ffmpeg
        (pipeline non-bloquant) et extrait le texte par OCR.

        L'utilisateur peut continuer a utiliser son telephone pendant toute l'attente.
        """
        debut = time.time()

        while (time.time() - debut) < timeout_secondes:
            # Verifier si le dialogue USSD est au premier plan (lecture seule)
            dialogue_actif = False
            try:
                res = subprocess.run(
                    ["adb", "shell", "dumpsys", "window", "windows"],
                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=4
                )
                dialogue_actif = "MMIDialogActivity" in res.stdout or "com.android.phone" in res.stdout
            except Exception:
                pass

            if dialogue_actif:
                png = self._capture_frame_ffmpeg()
                if png:
                    texte = self._ocr_depuis_frame(png)
                    if texte:
                        t_low = texte.lower()
                        en_attente = any(w in t_low for w in [
                            "execution du code ussd", "code ussd en cours",
                            "veuillez patienter", "en cours"
                        ]) and "solde" not in t_low

                        if not en_attente and "solde" in t_low:
                            return texte.strip(), "source:ffmpeg_ocr"

            time.sleep(1.0)

        return None, "Delai d'attente USSD expire (ffmpeg non-bloquant)."

    def parser_solde(self, texte: str) -> Optional[int]:
        """Extrait le montant du solde en FCFA."""
        if not texte:
            return None
        match = re.search(
            r"solde\s*(?:wave)?\s*(?:est\s+de|est)?\s*:?\s*(\d[\d\s.,]*)\s*(?:F|FCFA|CFA)?",
            texte,
            re.IGNORECASE
        )
        if match:
            chiffres = re.sub(r"[\s.,]", "", match.group(1))
            if chiffres.isdigit():
                return int(chiffres)
        return None

    def get_wave_balance(self, code_ussd: Optional[str] = None) -> Dict[str, Any]:
        """Exécute et retourne le format de données structuré exigé par l'agent IA."""
        horodatage = datetime.utcnow().isoformat()
        code = code_ussd or self.code_ussd

        # 1. Déclencher
        if not self.declencher_appel(code):
            return {
                "balance": None,
                "currency": "FCFA",
                "retrieved_at": horodatage,
                "status": "BALANCE_UNAVAILABLE",
                "error_message": "Échec d'exécution de l'intention d'appel USSD sur Android."
            }

        # 2. Capturer la réponse du réseau (délai de 15s adapté au réseau mobile)
        texte_reponse, _ = self.capturer_texte_mmi(timeout_secondes=15.0)

        # 3. Fermer le dialogue
        self.fermer_dialogue()

        if not texte_reponse:
            return {
                "balance": None,
                "currency": "FCFA",
                "retrieved_at": horodatage,
                "status": "BALANCE_UNAVAILABLE",
                "error_message": "Aucune réponse USSD reçue du réseau cellulaire."
            }

        # 4. Extraire
        solde = self.parser_solde(texte_reponse)
        if solde is None:
            return {
                "balance": None,
                "currency": "FCFA",
                "retrieved_at": horodatage,
                "status": "BALANCE_UNAVAILABLE",
                "raw_response": texte_reponse,
                "error_message": "Le solde n'a pas pu être identifié dans la réponse réseau."
            }

        return {
            "balance": solde,
            "currency": "FCFA",
            "retrieved_at": horodatage,
            "status": "success",
            "raw_response": texte_reponse,
            "code_ussd": code
        }


def lancer_serveur_flask(port: int = 5001):
    """Serveur Flask minimal pour intégration directe dans wave-assistant."""
    try:
        from flask import Flask, jsonify, request
    except ImportError:
        print("Flask n'est pas installé. Installez-le avec : pip install flask")
        return

    app = Flask(__name__)
    bridge = TermuxWaveUssdBridge()

    @app.route("/api/wave/balance", methods=["GET", "POST"])
    def endpoint_solde():
        code = None
        if request.is_json:
            code = request.json.get("code_ussd")
        elif request.args.get("code_ussd"):
            code = request.args.get("code_ussd")
        resultat = bridge.get_wave_balance(code)
        return jsonify(resultat)

    print(f"[*] Serveur USSD Termux démarré sur http://127.0.0.1:{port}")
    app.run(host="127.0.0.1", port=port, debug=False)


if __name__ == "__main__":
    bridge = TermuxWaveUssdBridge()
    if "--serveur" in sys.argv:
        port = 5001
        for arg in sys.argv:
            if arg.startswith("--port="):
                port = int(arg.split("=")[1])
        lancer_serveur_flask(port=port)
    else:
        print("[*] Exécution de la consultation USSD Wave en direct...")
        res = bridge.get_wave_balance()
        print(json.dumps(res, indent=2, ensure_ascii=False))
