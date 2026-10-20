"""
Service client pour le Pont Sans Fil MCP Téléphone (WaveGuard GPT).
Permet au backend FastAPI et à l'agent Jarvis de dialoguer avec le serveur MCP
tournant sur le smartphone Android (Termux) via Wi-Fi, sans fil physique ADB.

Respecte strictement le skill anti-fallback (4 états explicites : vide, chargement, succes, erreur)
et la convention de nommage en français.
"""

import os
import json
import socket
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
import httpx

logger = logging.getLogger("waveguard.mcp_telephone")

FICHIER_CONFIG_MCP = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "config_mcp_telephone.json"
)


class ServiceClientMcpTelephone:
    """Gestionnaire de liaison sans fil vers le serveur MCP hébergé sur le smartphone Android."""

    def __init__(self, fichier_config: Optional[str] = None):
        self.chemin_config = fichier_config or FICHIER_CONFIG_MCP
        self.config = self._charger_config()

    def _charger_config(self) -> Dict[str, Any]:
        """Charge la configuration locale du pont sans fil ou retourne une configuration vide."""
        if os.path.exists(self.chemin_config):
            try:
                with open(self.chemin_config, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Impossible de lire la configuration MCP : {e}")
        return {
            "ip_telephone": None,
            "port_telephone": 8765,
            "nom_appareil": None,
            "dernier_contact": None,
            "actif": False
        }

    def _sauvegarder_config(self) -> None:
        """Enregistre la configuration persistante."""
        try:
            with open(self.chemin_config, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Échec d'enregistrement de la configuration MCP : {e}")

    @staticmethod
    def detecter_ip_pc() -> str:
        """Détecte l'adresse IP locale du PC sur le réseau Wi-Fi/LAN."""
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        except Exception:
            ip = "127.0.0.1"
        finally:
            s.close()
        return ip

    def configurer_telephone(self, ip: str, port: int = 8765, nom: Optional[str] = None) -> Dict[str, Any]:
        """Définit manuellement ou via auto-découverte l'adresse du téléphone."""
        nettoye_ip = ip.strip()
        if ":" in nettoye_ip:
            parties = nettoye_ip.split(":")
            nettoye_ip = parties[0]
            try:
                port = int(parties[1])
            except ValueError:
                pass

        self.config["ip_telephone"] = nettoye_ip
        self.config["port_telephone"] = port
        if nom:
            self.config["nom_appareil"] = nom
        self.config["actif"] = True
        self._sauvegarder_config()
        return self.config

    def est_configure(self) -> bool:
        """Vérifie si une adresse IP est configurée."""
        return bool(self.config.get("ip_telephone") and self.config.get("port_telephone"))

    def obtenir_url_base(self) -> Optional[str]:
        """Retourne l'URL racine du serveur MCP Téléphone."""
        if not self.est_configure():
            return None
        return f"http://{self.config['ip_telephone']}:{self.config['port_telephone']}"

    # =========================================================================
    # ÉTATS CONFORMES ANTI-FALLBACK (vide, chargement, succes, erreur)
    # =========================================================================

    def obtenir_statut_pont(self) -> Dict[str, Any]:
        """
        Interroge le smartphone sans fil et modélise explicitement les 4 états :
        - vide : pas d'adresse IP renseignée
        - succes : smartphone en ligne, batterie reçue, MCP opérationnel
        - erreur : échec réseau ou délai dépassé
        """
        ip = self.config.get("ip_telephone")
        port = self.config.get("port_telephone", 8765)
        ip_pc = self.detecter_ip_pc()

        if not ip:
            return {
                "etat": "vide",
                "message": "Aucun smartphone configuré pour le pont sans fil MCP.",
                "ip_pc": ip_pc,
                "port_recommande": 8765,
                "commande_termux": f"curl -sO http://{ip_pc}:8000/api/v1/mcp-telephone/script-termux && python script-termux --pc={ip_pc}",
                "donnees": None
            }

        url_base = self.obtenir_url_base()
        try:
            with httpx.Client(timeout=3.5) as client:
                rep = client.get(f"{url_base}/sante")
                if rep.status_code == 200:
                    donnees_sante = rep.json()

                    # Obtenir les détails matériels
                    donnees_statut = {}
                    try:
                        rep_statut = client.get(f"{url_base}/api/statut")
                        if rep_statut.status_code == 200:
                            donnees_statut = rep_statut.json()
                    except Exception:
                        pass

                    self.config["dernier_contact"] = datetime.utcnow().isoformat()
                    self._sauvegarder_config()

                    return {
                        "etat": "succes",
                        "message": "Smartphone Android connecté sans fil via MCP !",
                        "ip_telephone": ip,
                        "port_telephone": port,
                        "ip_pc": ip_pc,
                        "dernier_contact": self.config["dernier_contact"],
                        "donnees": {
                            "serveur": donnees_sante.get("serveur"),
                            "version": donnees_sante.get("version"),
                            "batterie": donnees_statut.get("batterie"),
                            "reseau": donnees_statut.get("reseau"),
                            "nom_appareil": donnees_statut.get("nom_appareil", self.config.get("nom_appareil")),
                            "termux_api": donnees_statut.get("termux_api_disponible", False)
                        }
                    }
                else:
                    return {
                        "etat": "erreur",
                        "message": f"Le serveur du téléphone a retourné une erreur HTTP {rep.status_code}.",
                        "ip_telephone": ip,
                        "port_telephone": port,
                        "ip_pc": ip_pc,
                        "donnees": None
                    }
        except httpx.ConnectError:
            return {
                "etat": "erreur",
                "message": f"Connexion refusée sur {url_base}. Le serveur MCP est-il lancé sur le téléphone (Termux) ?",
                "ip_telephone": ip,
                "port_telephone": port,
                "ip_pc": ip_pc,
                "donnees": None
            }
        except httpx.TimeoutException:
            return {
                "etat": "erreur",
                "message": f"Délai d'attente dépassé vers {url_base}. Vérifiez que le téléphone et le PC sont sur le même réseau Wi-Fi.",
                "ip_telephone": ip,
                "port_telephone": port,
                "ip_pc": ip_pc,
                "donnees": None
            }
        except Exception as e:
            return {
                "etat": "erreur",
                "message": f"Erreur de communication avec le téléphone : {str(e)}",
                "ip_telephone": ip,
                "port_telephone": port,
                "ip_pc": ip_pc,
                "donnees": None
            }

    # =========================================================================
    # APPELS MCP JSON-RPC 2.0
    # =========================================================================

    def appeler_outil_mcp(self, nom_outil: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Exécute un outil via le protocole officiel MCP JSON-RPC 2.0 sur le téléphone.
        """
        if not self.est_configure():
            return {
                "etat": "erreur",
                "message": "Téléphone non configuré. Veuillez indiquer son IP.",
                "resultat": None
            }

        url_mcp = f"{self.obtenir_url_base()}/mcp"
        charge_mcp = {
            "jsonrpc": "2.0",
            "id": int(datetime.utcnow().timestamp()),
            "method": "tools/call",
            "params": {
                "name": nom_outil,
                "arguments": arguments or {}
            }
        }

        try:
            with httpx.Client(timeout=12.0) as client:
                rep = client.post(url_mcp, json=charge_mcp)
                if rep.status_code == 200:
                    donnees = rep.json()
                    if "error" in donnees:
                        return {
                            "etat": "erreur",
                            "message": donnees["error"].get("message", "Erreur RPC MCP"),
                            "code": donnees["error"].get("code"),
                            "resultat": None
                        }
                    resultat_mcp = donnees.get("result", {})
                    # Parsing standard du texte retourné par l'outil MCP
                    contenu_texte = ""
                    for bloc in resultat_mcp.get("content", []):
                        if bloc.get("type") == "text":
                            contenu_texte += bloc.get("text", "")

                    parsed_json = None
                    if contenu_texte:
                        try:
                            parsed_json = json.loads(contenu_texte)
                        except Exception:
                            parsed_json = contenu_texte

                    return {
                        "etat": "succes",
                        "outil": nom_outil,
                        "resultat": parsed_json
                    }
                else:
                    return {
                        "etat": "erreur",
                        "message": f"Code HTTP {rep.status_code} reçu de l'outil MCP.",
                        "resultat": None
                    }
        except Exception as e:
            return {
                "etat": "erreur",
                "message": f"Échec de l'appel d'outil MCP {nom_outil} : {str(e)}",
                "resultat": None
            }

    # =========================================================================
    # MÉTHODES MÉTIER SANS AUCUN CÂBLE USB ADB
    # =========================================================================

    def consulter_solde_sans_fil(self, code_ussd: Optional[str] = None, forcer_ussd: bool = False) -> Dict[str, Any]:
        """Demande au smartphone de retourner le solde Wave (par SMS récent ou USSD direct)."""
        args = {"forcer_ussd": forcer_ussd}
        if code_ussd:
            args["code_ussd"] = code_ussd
        return self.appeler_outil_mcp("consulter_solde_wave", args)

    def recuperer_sms_sans_fil(self, limite: int = 25) -> Dict[str, Any]:
        """Extrait les SMS de transactions Wave directement depuis le téléphone en Wi-Fi."""
        return self.appeler_outil_mcp("lire_sms_wave", {"limite": limite})

    def recuperer_notifications_sans_fil(self, limite: int = 20) -> Dict[str, Any]:
        """Extrait les notifications push Wave actives sans câble USB."""
        return self.appeler_outil_mcp("lire_notifications_wave", {"limite": limite})

    def capturer_ecran_sans_fil(self) -> Dict[str, Any]:
        """Prend une capture d'écran du smartphone en direct et retourne le PNG base64 sans ADB."""
        return self.appeler_outil_mcp("capturer_ecran_telephone", {})

    def analyser_ui_sans_fil(self) -> Dict[str, Any]:
        """Extrait et analyse l'arborescence UI complète des composants affichés à l'écran."""
        return self.appeler_outil_mcp("analyser_ui_telephone", {})

    def lancer_application_sans_fil(self, paquet: str = "com.wave.personal") -> Dict[str, Any]:
        """Lance une application (ex: Wave) au premier plan sans câble ADB."""
        return self.appeler_outil_mcp("lancer_application", {"paquet": paquet})

    def reveiller_telephone_sans_fil(self) -> Dict[str, Any]:
        """Réveille l'écran du smartphone et active le maintien en éveil."""
        return self.appeler_outil_mcp("reveiller_telephone", {})

    def simuler_clic_sans_fil(self, x: int, y: int) -> Dict[str, Any]:
        """Simule un appui tactile à des coordonnées (x, y) sans ADB."""
        return self.appeler_outil_mcp("simuler_clic", {"x": x, "y": y})

    def simuler_texte_sans_fil(self, texte: str) -> Dict[str, Any]:
        """Saisit du texte au clavier dans le champ actif du smartphone."""
        return self.appeler_outil_mcp("simuler_texte", {"texte": texte})

    def composer_ussd_sans_fil(self, code: str) -> Dict[str, Any]:
        """Compose un code USSD directement sur le téléphone."""
        return self.appeler_outil_mcp("composer_ussd_direct", {"code": code})

    def faire_vibrer_telephone(self, duree_ms: int = 350) -> Dict[str, Any]:
        """Alerte physique par vibration sur le smartphone."""
        return self.appeler_outil_mcp("vibrer_alerte", {"duree_ms": duree_ms})

    def parler_tts_sans_fil(self, texte: str, langue: str = "fr") -> Dict[str, Any]:
        """Prononce un message vocal via les haut-parleurs du smartphone."""
        return self.appeler_outil_mcp("parler_tts", {"texte": texte, "langue": langue})

    def gerer_presse_papier_sans_fil(self, texte: Optional[str] = None) -> Dict[str, Any]:
        """Lit ou modifie le presse-papier du smartphone sans câble."""
        return self.appeler_outil_mcp("presse_papier", {"texte": texte} if texte else {})

    def transferer_argent_wave_sans_fil(
        self,
        numero_destinataire: str,
        montant_fcfa: int,
        code_secret: Optional[str] = None,
        motif: str = "Transfert Wave"
    ) -> Dict[str, Any]:
        """Exécute un transfert d'argent Wave officiel sans fil via le serveur MCP sur le smartphone."""
        args = {
            "numero_destinataire": numero_destinataire,
            "montant_fcfa": montant_fcfa,
            "motif": motif
        }
        if code_secret:
            args["code_secret"] = code_secret
        return self.appeler_outil_mcp("transferer_argent_wave", args)


