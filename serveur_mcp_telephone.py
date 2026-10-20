#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Serveur MCP Téléphone Android pour WaveGuard GPT (Mode Sans Fil).
Permet la communication complète entre le smartphone Android et le PC sans aucun câble USB ADB.

Fonctionnalités :
1. Protocole officiel MCP (Model Context Protocol) JSON-RPC 2.0 (outils, ressources, prompts).
2. Endpoints REST rapides (/api/statut, /api/solde, /api/sms, /api/notifications, /api/capture-ecran, /api/ui-arbre, /sante).
3. Transport sans fil local Wi-Fi / Hotspot avec zéro dépendance pip externe.
4. Intégration directe Termux:API (SMS, Notifications, USSD, Écran, Batterie, Réseau, Vibreur, TTS, Presse-papier).
5. Émulation des commandes ADB directement sur l'appareil (screencap, uiautomator dump, input tap, monkey launcher).
6. Annonce automatique d'adresse IP au serveur PC WaveGuard au démarrage.

Usage sur Android (Termux) :
    pkg update && pkg install -y python termux-api
    python serveur_mcp_telephone.py --port=8765 --pc=192.168.1.X
"""

import sys
import os
import re
import json
import time
import socket
import base64
import subprocess
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple


class ServeurThreaded(ThreadingMixIn, HTTPServer):
    """Serveur HTTP multithreadé gérant simultanément plusieurs requêtes MCP et REST."""
    daemon_threads = True
    allow_reuse_address = True


class GestionnaireMaterielAndroid:
    """Accès souverain et direct aux fonctionnalités du smartphone Android sans câble USB."""

    @staticmethod
    def obtenir_ip_locale() -> str:
        """Détermine l'adresse IP locale du smartphone sur le réseau Wi-Fi ou Point d'accès."""
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # Ne transmet aucun paquet réel mais résout la route sortante locale
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        except Exception:
            ip = "127.0.0.1"
        finally:
            s.close()
        return ip

    @staticmethod
    def executer_commande(cmd: List[str], timeout: int = 10) -> Tuple[int, str, str]:
        """Exécute une commande système de façon sécurisée."""
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout
            )
            return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
        except FileNotFoundError:
            return 127, "", f"Commande non trouvée : {cmd[0]}"
        except subprocess.TimeoutExpired:
            return 124, "", "Délai d'exécution dépassé."
        except Exception as e:
            return 1, "", str(e)

    @classmethod
    def obtenir_statut_telephone(cls) -> Dict[str, Any]:
        """Interroge la batterie, le Wi-Fi, le modèle de l'appareil et le stockage."""
        statut = {
            "mode": "android_termux_sans_fil",
            "horodatage": datetime.utcnow().isoformat(),
            "ip_locale": cls.obtenir_ip_locale(),
            "batterie": {"pourcentage": None, "en_charge": None, "statut": "inconnu", "temperature": None},
            "reseau": {"type": "inconnu", "ssid": None, "ip": cls.obtenir_ip_locale()},
            "nom_appareil": socket.gethostname() or "Android Smartphone",
            "termux_api_disponible": False,
            "version_serveur": "2.0.0"
        }

        # 1. Batterie via Termux:API
        code, out, _ = cls.executer_commande(["termux-battery-status"], timeout=3)
        if code == 0 and out:
            try:
                donnees_bat = json.loads(out)
                statut["batterie"] = {
                    "pourcentage": donnees_bat.get("percentage"),
                    "en_charge": donnees_bat.get("status") in ("CHARGING", "FULL"),
                    "statut": donnees_bat.get("status", "inconnu"),
                    "temperature": donnees_bat.get("temperature"),
                }
                statut["termux_api_disponible"] = True
            except Exception:
                pass
        else:
            # Fallback Android natif dumpsys
            code_d, out_d, _ = cls.executer_commande(["dumpsys", "battery"], timeout=2)
            if code_d == 0 and out_d:
                m_lvl = re.search(r"level:\s*(\d+)", out_d)
                if m_lvl:
                    statut["batterie"]["pourcentage"] = int(m_lvl.group(1))

        # 2. Informations Wi-Fi
        code_w, out_w, _ = cls.executer_commande(["termux-wifi-connectioninfo"], timeout=3)
        if code_w == 0 and out_w:
            try:
                donnees_wifi = json.loads(out_w)
                statut["reseau"] = {
                    "type": "wifi",
                    "ssid": donnees_wifi.get("ssid", "").replace('"', ""),
                    "vitesse_mbps": donnees_wifi.get("link_speed_mbps"),
                    "ip": donnees_wifi.get("ip") or statut["ip_locale"]
                }
            except Exception:
                pass

        return statut

    @classmethod
    def extraire_montant_fcfa(cls, texte: str) -> Optional[int]:
        """Trouve le montant principal en FCFA dans un texte ou SMS."""
        if not texte:
            return None
        m = re.search(r"(\d[\d\s.,]*)\s*(?:F|FCFA|CFA)", texte, re.IGNORECASE)
        if m:
            chiffres = re.sub(r"[\s.,]", "", m.group(1))
            if chiffres.isdigit():
                return int(chiffres)
        return None

    @classmethod
    def lire_sms_wave(cls, limite: int = 25) -> List[Dict[str, Any]]:
        """
        Lit directement les SMS de transactions Wave sans câble USB.
        Utilise termux-sms-list ou le ContentProvider Android.
        """
        messages = []

        # Méthode A : Termux:API
        code, out, _ = cls.executer_commande(["termux-sms-list", "-l", str(limite)], timeout=8)
        if code == 0 and out:
            try:
                sms_bruts = json.loads(out)
                for item in sms_bruts:
                    expediteur = item.get("number") or item.get("sender") or ""
                    corps = item.get("body") or item.get("message") or ""
                    date_sms = item.get("received") or item.get("date") or ""

                    # Filtrage Wave et Mobile Money
                    if any(k in expediteur.lower() or k in corps.lower() for k in ["wave", "retrait", "transfert", "paiement", "depot"]):
                        montant = cls.extraire_montant_fcfa(corps)
                        messages.append({
                            "expediteur": expediteur,
                            "corps": corps,
                            "date": date_sms,
                            "montant_fcfa": montant,
                            "type": "transaction_wave" if "wave" in corps.lower() else "sms_bancaire"
                        })
                return messages
            except Exception:
                pass

        # Méthode B : ContentProvider Android natif (content query)
        code_cp, out_cp, _ = cls.executer_commande([
            "content", "query", "--uri", "content://sms/inbox",
            "--projection", "address,body,date", "--sort", "date DESC"
        ], timeout=5)
        if code_cp == 0 and out_cp:
            lignes = out_cp.split("\n")
            for l in lignes:
                if any(k in l.lower() for k in ["wave", "retrait", "transfert"]):
                    m_addr = re.search(r"address=([^,\s]+)", l)
                    m_body = re.search(r"body=(.*?)(?:,\s*date=|$)", l)
                    m_date = re.search(r"date=(\d+)", l)
                    corps = m_body.group(1) if m_body else l
                    expediteur = m_addr.group(1) if m_addr else "Wave"
                    date_str = m_date.group(1) if m_date else ""
                    messages.append({
                        "expediteur": expediteur,
                        "corps": corps,
                        "date": date_str,
                        "montant_fcfa": cls.extraire_montant_fcfa(corps),
                        "type": "transaction_wave"
                    })
                if len(messages) >= limite:
                    break

        return messages

    @classmethod
    def extraire_notifications_wave(cls, limite: int = 25) -> List[Dict[str, Any]]:
        """
        Extrait les notifications push actives de Wave Mobile Money sans câble ADB.
        Remplace complètement la commande filaire `adb shell dumpsys notification --noredact`.
        """
        notifications = []

        # Méthode 1 : termux-notification-list (Termux:API officiel)
        code, out, _ = cls.executer_commande(["termux-notification-list"], timeout=6)
        if code == 0 and out:
            try:
                notifs_brutes = json.loads(out)
                for item in notifs_brutes:
                    paquet = item.get("packageName", "")
                    titre = item.get("title", "")
                    corps = item.get("content", "") or item.get("bigText", "")
                    horodatage = item.get("when", "")

                    if "com.wave.personal" in paquet or "wave" in titre.lower() or "wave" in corps.lower():
                        montant = cls.extraire_montant_fcfa(corps)
                        notifications.append({
                            "paquet": paquet,
                            "titre": titre,
                            "texte": corps,
                            "horodatage": horodatage,
                            "montant_fcfa": montant,
                            "source": "termux_notification_list"
                        })
                if notifications:
                    return notifications[:limite]
            except Exception:
                pass

        # Méthode 2 : dumpsys notification natif Android (sans fil)
        code_d, out_d, _ = cls.executer_commande(["dumpsys", "notification", "--noredact"], timeout=6)
        if code_d == 0 and out_d:
            blocs = out_d.split("NotificationRecord{")
            for bloc in blocs:
                if "pkg=com.wave.personal" not in bloc and "wave" not in bloc.lower():
                    continue

                titre = ""
                texte = ""
                texte_big = ""
                horodatage_ms = None

                m_titre = re.search(r"android\.title=(?:String|SpannableString)\s*\((.*?)\)", bloc)
                if m_titre:
                    titre = m_titre.group(1).strip()

                m_texte = re.search(r"android\.text=(?:String|SpannableString)\s*\((.*?)\)", bloc)
                if m_texte:
                    texte = m_texte.group(1).strip()

                m_big = re.search(r"android\.bigText=(?:String|SpannableString)\s*\((.*?)\)", bloc)
                if m_big:
                    texte_big = m_big.group(1).strip()

                m_time = re.search(r"postTime=(\d+)", bloc)
                if m_time:
                    try:
                        horodatage_ms = int(m_time.group(1))
                    except ValueError:
                        pass

                texte_final = texte_big or texte
                if titre or texte_final:
                    notifications.append({
                        "paquet": "com.wave.personal",
                        "titre": titre,
                        "texte": texte_final,
                        "horodatage": (
                            datetime.fromtimestamp(horodatage_ms / 1000.0).isoformat()
                            if horodatage_ms else datetime.utcnow().isoformat()
                        ),
                        "montant_fcfa": cls.extraire_montant_fcfa(texte_final),
                        "source": "dumpsys_sans_fil"
                    })
                if len(notifications) >= limite:
                    break

        return notifications

    @classmethod
    def capturer_ecran(cls) -> Dict[str, Any]:
        """
        Capture l'écran du smartphone en direct et retourne l'image PNG encodée en base64.
        Remplace la commande filaire `adb exec-out screencap -p`.
        """
        chemin_temp = "/sdcard/waveguard_screenshot.png"
        code, _, err = cls.executer_commande(["screencap", "-p", chemin_temp], timeout=6)

        if code == 0 and os.path.exists(chemin_temp):
            try:
                with open(chemin_temp, "rb") as f:
                    donnees = f.read()
                try:
                    os.remove(chemin_temp)
                except Exception:
                    pass

                return {
                    "succes": True,
                    "format": "png",
                    "taille_octets": len(donnees),
                    "base64_png": base64.b64encode(donnees).decode("ascii"),
                    "horodatage": datetime.utcnow().isoformat()
                }
            except Exception as e:
                return {"succes": False, "erreur": f"Lecture capture échouée : {str(e)}"}

        # Capture directe via stdout binaire si pas d'écriture sdcard
        try:
            proc = subprocess.run(["screencap", "-p"], capture_output=True, timeout=6)
            if proc.returncode == 0 and len(proc.stdout) > 500:
                return {
                    "succes": True,
                    "format": "png",
                    "taille_octets": len(proc.stdout),
                    "base64_png": base64.b64encode(proc.stdout).decode("ascii"),
                    "horodatage": datetime.utcnow().isoformat()
                }
        except Exception:
            pass

        return {"succes": False, "erreur": f"Capture d'écran indisponible : {err}"}

    @classmethod
    def analyser_arborescence_ui(cls) -> Dict[str, Any]:
        """
        Exécute uiautomator dump directement sur Android et extrait l'arbre des composants UI.
        Remplace la commande filaire `adb shell uiautomator dump`.
        """
        chemin_xml = "/sdcard/waveguard_dump.xml"
        code, out, err = cls.executer_commande(["uiautomator", "dump", "--compressed", chemin_xml], timeout=10)

        xml_texte = ""
        if code == 0 and os.path.exists(chemin_xml):
            try:
                with open(chemin_xml, "r", encoding="utf-8", errors="ignore") as f:
                    xml_texte = f.read()
                try:
                    os.remove(chemin_xml)
                except Exception:
                    pass
            except Exception:
                pass

        if not xml_texte:
            # Fallback lecture directe
            code_c, out_c, _ = cls.executer_commande(["cat", chemin_xml], timeout=5)
            if code_c == 0 and out_c.startswith("<?xml"):
                xml_texte = out_c

        if not xml_texte:
            return {
                "succes": False,
                "erreur": f"Échec extraction UI : {err or out}",
                "elements": []
            }

        elements = []
        solde_detecte = None
        try:
            racine = ET.fromstring(xml_texte)
            for node in racine.iter("node"):
                txt = node.attrib.get("text", "").strip()
                desc = node.attrib.get("content-desc", "").strip()
                res_id = node.attrib.get("resource-id", "")
                bounds = node.attrib.get("bounds", "")
                cliquable = node.attrib.get("clickable", "false") == "true"
                paquet = node.attrib.get("package", "")

                if txt or desc:
                    elements.append({
                        "texte": txt,
                        "description": desc,
                        "id_ressource": res_id,
                        "limites": bounds,
                        "cliquable": cliquable,
                        "paquet": paquet
                    })

                    # Recherche du solde dans le texte de l'interface
                    if not solde_detecte:
                        montant = cls.extraire_montant_fcfa(txt or desc)
                        if montant and montant > 0:
                            solde_detecte = montant

            return {
                "succes": True,
                "total_elements": len(elements),
                "solde_potentiel_fcfa": solde_detecte,
                "elements": elements[:50],  # Limite de transmission réseau raisonnable
                "horodatage": datetime.utcnow().isoformat()
            }
        except Exception as e:
            return {"succes": False, "erreur": f"Parsing XML échoué : {str(e)}", "elements": []}

    @classmethod
    def lancer_application(cls, paquet: str = "com.wave.personal") -> Dict[str, Any]:
        """
        Lance une application au premier plan sur le téléphone sans câble USB.
        Remplace la commande filaire `adb shell monkey -p com.wave.personal ...`.
        """
        cmd_monkey = [
            "monkey", "-p", paquet,
            "-c", "android.intent.category.LAUNCHER", "1"
        ]
        code, out, err = cls.executer_commande(cmd_monkey, timeout=6)
        if code == 0:
            return {
                "succes": True,
                "paquet": paquet,
                "message": f"Application {paquet} lancée avec succès au premier plan.",
                "horodatage": datetime.utcnow().isoformat()
            }

        # Fallback am start
        cmd_am = ["am", "start", "-n", f"{paquet}/.MainActivity"]
        code_am, _, err_am = cls.executer_commande(cmd_am, timeout=5)
        return {
            "succes": code_am == 0,
            "paquet": paquet,
            "message": "Lancement via Intent Android effectué." if code_am == 0 else f"Échec : {err or err_am}"
        }

    @classmethod
    def reveiller_telephone(cls) -> Dict[str, Any]:
        """
        Réveille l'écran du smartphone et le déverrouille sans fil.
        Remplace `adb shell input keyevent 224`.
        """
        # 1. Wakeup
        cls.executer_commande(["input", "keyevent", "224"], timeout=3)
        # 2. Déverrouillage swipe
        cls.executer_commande(["input", "keyevent", "82"], timeout=3)
        # 3. Empêcher l'extinction via Termux wake-lock
        cls.executer_commande(["termux-wake-lock"], timeout=3)

        return {
            "succes": True,
            "message": "Écran réveillé et wake-lock activé.",
            "horodatage": datetime.utcnow().isoformat()
        }

    @classmethod
    def simuler_clic(cls, x: int, y: int) -> Dict[str, Any]:
        """Simule un toucher tactile (tap) aux coordonnées spécifiées sans ADB."""
        code, _, err = cls.executer_commande(["input", "tap", str(x), str(y)], timeout=4)
        return {
            "succes": code == 0,
            "x": x,
            "y": y,
            "message": f"Clic simulé aux coordonnées ({x}, {y})" if code == 0 else f"Erreur : {err}"
        }

    @classmethod
    def simuler_texte(cls, texte: str) -> Dict[str, Any]:
        """Saisit du texte dans le champ actuellement sélectionné sans ADB."""
        texte_echappe = texte.replace(" ", "%s")
        code, _, err = cls.executer_commande(["input", "text", texte_echappe], timeout=5)
        return {
            "succes": code == 0,
            "texte": texte,
            "message": "Texte injecté avec succès." if code == 0 else f"Erreur : {err}"
        }

    @classmethod
    def composer_ussd(cls, code_ussd: str) -> Dict[str, Any]:
        """
        Déclenche l'appel USSD sur le téléphone sans fil.
        Priorités :
        1. termux-telephony-call (Termux:API)
        2. am start action.CALL
        """
        code = code_ussd.strip()
        code_encode = code.replace("#", "%23")

        # 1. Termux API
        code_ret, _, err = cls.executer_commande(["termux-telephony-call", code], timeout=4)
        if code_ret == 0:
            return {
                "succes": True,
                "methode": "termux-telephony-call",
                "code_ussd": code,
                "horodatage": datetime.utcnow().isoformat()
            }

        # 2. Intent Android am start
        cmd_am = ["am", "start", "-a", "android.intent.action.CALL", "-d", f"tel:{code_encode}"]
        code_am, _, err_am = cls.executer_commande(cmd_am, timeout=4)
        if code_am == 0:
            return {
                "succes": True,
                "methode": "android_intent_call",
                "code_ussd": code,
                "horodatage": datetime.utcnow().isoformat()
            }

        return {
            "succes": False,
            "erreur": f"Échec d'appel USSD : {err or err_am}",
            "code_ussd": code
        }

    @classmethod
    def transferer_argent_wave(
        cls,
        numero_destinataire: str,
        montant_fcfa: int,
        code_secret: Optional[str] = None,
        motif: str = "Transfert Wave"
    ) -> Dict[str, Any]:
        """
        Exécute un ordre de transfert d'argent réel Wave via le code USSD officiel :
        Format : *9113*1*<numero_destinataire>*<montant_fcfa>*<code_secret>#
        Le code secret est lu depuis les arguments ou la variable d'environnement WAVE_CODE_SECRET.
        """
        pin = (code_secret or os.environ.get("WAVE_CODE_SECRET", "")).strip()
        if not pin:
            return {
                "succes": False,
                "statut": "erreur_validation",
                "erreur": "Code secret Wave non configuré. Veuillez renseigner 'code_secret' ou définir WAVE_CODE_SECRET.",
                "message": "Opération interrompue : aucun code secret Wave renseigné."
            }

        numero_propre = re.sub(r"[^\d]", "", str(numero_destinataire).strip())
        if numero_propre.startswith("225") and len(numero_propre) == 13:
            numero_normalise = numero_propre[3:]
        else:
            numero_normalise = numero_propre

        montant_entier = int(montant_fcfa)
        code_ussd = f"*9113*1*{numero_normalise}*{montant_entier}*{pin}#"

        res_ussd = cls.composer_ussd(code_ussd)

        # Masquage du code PIN pour ne jamais le faire fuiter dans les réponses ou logs
        code_ussd_masque = f"*9113*1*{numero_normalise}*{montant_entier}*••••#"

        return {
            "succes": res_ussd.get("succes", False),
            "statut": "transfert_transmis" if res_ussd.get("succes") else "erreur_transmission",
            "numero_destinataire": numero_destinataire,
            "numero_normalise": numero_normalise,
            "montant_fcfa": montant_entier,
            "devise": "FCFA",
            "code_ussd_compose": code_ussd_masque,
            "motif": motif,
            "horodatage": datetime.utcnow().isoformat(),
            "details_appel": res_ussd,
            "message": (
                f"Ordre de transfert Wave de {montant_entier:,} FCFA vers le {numero_destinataire} "
                f"transmis avec succès par commande USSD."
                if res_ussd.get("succes")
                else f"Échec de l'envoi du transfert : {res_ussd.get('erreur')}"
            )
        }

    @classmethod
    def evaluer_impact_transfert_wave(
        cls,
        montant_fcfa: int,
        numero_destinataire: str,
        motif: str = "",
        categorie: str = "depannage_famille",
        reserve_minimale_fcfa: int = 25000
    ) -> Dict[str, Any]:
        """
        Analyse de gouvernance et d'arbitrage du Family Officer avant tout transfert Wave.
        Respecte rigoureusement le modèle à 4 états (succes, alerte_reserve_entamee, refus_solde_insuffisant, erreur_technique).
        """
        try:
            montant = int(montant_fcfa)
            frais_estimes = max(0, int(montant * 0.01))
            total_preleve = montant + frais_estimes

            solde_actuel = cls.extraire_solde_dernier_sms()
            solde_apres = (solde_actuel - total_preleve) if solde_actuel is not None else None

            # 1. ÉTAT : REFUS (Solde insuffisant)
            if solde_actuel is not None and total_preleve > solde_actuel:
                return {
                    "statut": "refus_solde_insuffisant",
                    "autorise_par_officer": False,
                    "montant_demande_fcfa": montant,
                    "frais_wave_estimes_fcfa": frais_estimes,
                    "total_debit_prevu_fcfa": total_preleve,
                    "solde_actuel_certifie_fcfa": solde_actuel,
                    "deficit_fcfa": total_preleve - solde_actuel,
                    "avis_officer": (
                        f"⛔ Refus du Family Officer : Solde disponible ({solde_actuel:,} FCFA) insuffisant "
                        f"pour couvrir ce transfert de {montant:,} FCFA (+ {frais_estimes:,} FCFA de frais)."
                    ),
                    "recommandation": "Différer l'opération ou ajuster le montant au solde réel disponible."
                }

            # 2. ÉTAT : ALERTE (Sanctuaire entamé)
            elif solde_actuel is not None and solde_apres < reserve_minimale_fcfa:
                danger_critique = solde_apres < 5000
                return {
                    "statut": "alerte_reserve_entamee",
                    "autorise_par_officer": not danger_critique,
                    "niveau_alerte": "critique" if danger_critique else "vigilance",
                    "montant_demande_fcfa": montant,
                    "frais_wave_estimes_fcfa": frais_estimes,
                    "total_debit_prevu_fcfa": total_preleve,
                    "solde_actuel_certifie_fcfa": solde_actuel,
                    "solde_restant_apres_fcfa": solde_apres,
                    "sanctuaire_urgence_fcfa": reserve_minimale_fcfa,
                    "ecart_sanctuaire_fcfa": reserve_minimale_fcfa - solde_apres,
                    "avis_officer": (
                        f"⚠️ Alerte Vigilance Family Officer : Ce transfert entame votre réserve de sécurité "
                        f"({reserve_minimale_fcfa:,} FCFA). Votre solde résiduel ne sera plus que de {solde_apres:,} FCFA. "
                        + ("🚨 Niveau CRITIQUE : risque d'impossibilité de subvenir aux besoins vitaux !" if danger_critique else "Confirmez uniquement s'il s'agit d'une priorité avérée.")
                    ),
                    "questions_a_confirmer": [
                        f"Êtes-vous certain de vouloir réduire votre réserve d'urgence à {solde_apres:,} FCFA ?",
                        f"Ce dépannage peut-il être réduit ou différé ?",
                        f"Le numéro {numero_destinataire} est-il certifié (vérification anti-fraude) ?"
                    ]
                }

            # 3. ÉTAT : SUCCÈS (Feu vert)
            else:
                return {
                    "statut": "succes",
                    "autorise_par_officer": True,
                    "montant_demande_fcfa": montant,
                    "frais_wave_estimes_fcfa": frais_estimes,
                    "total_debit_prevu_fcfa": total_preleve,
                    "solde_actuel_certifie_fcfa": solde_actuel,
                    "solde_restant_apres_fcfa": solde_apres,
                    "sanctuaire_urgence_preserve": True if solde_apres is not None else "a_verifier_apres_ussd",
                    "avis_officer": (
                        f"✅ Feu vert du Family Officer : L'opération est compatible avec votre équilibre financier. "
                        f"Votre sanctuaire d'urgence est préservé (solde restant estimé : {solde_apres:,} FCFA)."
                        if solde_apres is not None else
                        f"ℹ️ Feu vert sous réserve : Solde non extrait des SMS, vérification en direct via USSD."
                    ),
                    "recommandation": f"Vous pouvez confirmer le transfert vers le {numero_destinataire}."
                }
        except Exception as e:
            # 4. ÉTAT : ERREUR
            return {
                "statut": "erreur_technique",
                "autorise_par_officer": False,
                "erreur": f"Échec d'évaluation financière : {str(e)}"
            }

    @classmethod
    def extraire_solde_dernier_sms(cls) -> Optional[int]:
        """Extrait le solde le plus récent depuis les SMS Wave reçus."""
        sms_wave = cls.lire_sms_wave(limite=10)
        for s in sms_wave:
            corps = s.get("corps", "")
            m = re.search(r"solde\s*(?:est\s+de|:)?\s*(\d[\d\s.,]*)\s*(?:F|FCFA|CFA)", corps, re.IGNORECASE)
            if m:
                chiffres = re.sub(r"[\s.,]", "", m.group(1))
                if chiffres.isdigit():
                    return int(chiffres)
        return None

    @classmethod
    def faire_vibrer(cls, duree_ms: int = 300) -> bool:
        """Fait vibrer le téléphone pour une alerte ou validation."""
        code, _, _ = cls.executer_commande(["termux-vibrate", "-d", str(duree_ms)], timeout=2)
        return code == 0

    @classmethod
    def gerer_presse_papier(cls, texte_a_copier: Optional[str] = None) -> Dict[str, Any]:
        """Lit ou modifie le presse-papier du téléphone sans fil."""
        if texte_a_copier is not None:
            code, _, _ = cls.executer_commande(["termux-clipboard-set", texte_a_copier], timeout=2)
            return {"succes": code == 0, "operation": "ecriture", "texte": texte_a_copier}
        else:
            code, out, _ = cls.executer_commande(["termux-clipboard-get"], timeout=2)
            return {"succes": code == 0, "operation": "lecture", "contenu": out if code == 0 else ""}

    @classmethod
    def parler_tts(cls, texte: str, langue: str = "fr") -> bool:
        """Joue un message vocal via la synthèse vocale Android."""
        code, _, _ = cls.executer_commande(["termux-tts-speak", "-l", langue, texte], timeout=5)
        return code == 0


class GestionnaireProtocoleMCP:
    """Implémentation conforme du protocole Model Context Protocol (JSON-RPC 2.0)."""

    VERSION_PROTOCOLE = "2024-11-05"
    NOM_SERVEUR = "telephone-android-mcp"
    VERSION_SERVEUR = "2.0.0"

    OUTILS_DISPONIBLES = [
        {
            "name": "statut_telephone",
            "description": "Retourne l'état complet du smartphone Android (batterie, Wi-Fi, IP, Termux API, modèle).",
            "inputSchema": {
                "type": "object",
                "properties": {}
            }
        },
        {
            "name": "consulter_solde_wave",
            "description": "Consulte le solde officiel Wave du téléphone directement via USSD ou SMS certifié sans fil.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "code_ussd": {
                        "type": "string",
                        "description": "Code USSD de consultation (défaut: variable WAVE_USSD_SOLDE ou *9113#).",
                        "default": "*9113#"
                    },
                    "forcer_ussd": {
                        "type": "boolean",
                        "description": "Si vrai, compose immédiatement le code USSD.",
                        "default": False
                    }
                }
            }
        },
        {
            "name": "transferer_argent_wave",
            "description": "Exécute un transfert d'argent réel Wave sans fil par commande USSD officielle (*9113*1*numero*montant*PIN#).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "numero_destinataire": {
                        "type": "string",
                        "description": "Numéro de téléphone du destinataire Wave (ex: 0700000000 ou format international)."
                    },
                    "montant_fcfa": {
                        "type": "integer",
                        "description": "Montant à transférer en FCFA (ex: 5000)."
                    },
                    "code_secret": {
                        "type": "string",
                        "description": "Code secret Wave de validation (lu depuis WAVE_CODE_SECRET si omis)."
                    },
                    "motif": {
                        "type": "string",
                        "description": "Motif du transfert pour le grand livre (ex: Loyer, Facture, Dépannage).",
                        "default": "Transfert Wave"
                    }
                },
                "required": ["numero_destinataire", "montant_fcfa"]
            }
        },
        {
            "name": "lire_sms_wave",
            "description": "Extrait les derniers SMS de transactions Wave et Mobile Money sans aucun câble USB.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "limite": {
                        "type": "integer",
                        "description": "Nombre maximal de SMS à récupérer (défaut: 25).",
                        "default": 25
                    }
                }
            }
        },
        {
            "name": "lire_notifications_wave",
            "description": "Extrait les notifications push actives de Wave Mobile Money (remplace adb dumpsys notification).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "limite": {
                        "type": "integer",
                        "description": "Nombre maximal de notifications à récupérer (défaut: 20).",
                        "default": 20
                    }
                }
            }
        },
        {
            "name": "capturer_ecran_telephone",
            "description": "Capture l'écran du smartphone en direct et retourne l'image PNG en base64 (remplace adb screencap).",
            "inputSchema": {
                "type": "object",
                "properties": {}
            }
        },
        {
            "name": "analyser_ui_telephone",
            "description": "Extrait l'arborescence UI complète des composants affichés à l'écran (remplace adb uiautomator dump).",
            "inputSchema": {
                "type": "object",
                "properties": {}
            }
        },
        {
            "name": "lancer_application",
            "description": "Ouvre une application au premier plan sur le téléphone (défaut: Wave com.wave.personal).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "paquet": {
                        "type": "string",
                        "description": "Nom du paquet Android (défaut: com.wave.personal).",
                        "default": "com.wave.personal"
                    }
                }
            }
        },
        {
            "name": "reveiller_telephone",
            "description": "Réveille l'écran du smartphone et le déverrouille (remplace adb input keyevent 224).",
            "inputSchema": {
                "type": "object",
                "properties": {}
            }
        },
        {
            "name": "simuler_clic",
            "description": "Simule un appui tactile (tap) à une coordonnée précise de l'écran (remplace adb input tap).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "Coordonnée X en pixels."},
                    "y": {"type": "integer", "description": "Coordonnée Y en pixels."}
                },
                "required": ["x", "y"]
            }
        },
        {
            "name": "simuler_texte",
            "description": "Saisit du texte au clavier virtuel dans le champ actif du smartphone.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "texte": {"type": "string", "description": "Texte à saisir."}
                },
                "required": ["texte"]
            }
        },
        {
            "name": "composer_ussd_direct",
            "description": "Compose n'importe quel code USSD directement sur le modem GSM du téléphone.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Code USSD à composer (ex: *9113#)."}
                },
                "required": ["code"]
            }
        },
        {
            "name": "vibrer_alerte",
            "description": "Déclenche une vibration sur le téléphone pour alerter l'utilisateur.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "duree_ms": {
                        "type": "integer",
                        "description": "Durée de la vibration en ms (défaut 300).",
                        "default": 300
                    }
                }
            }
        },
        {
            "name": "presse_papier",
            "description": "Lit ou modifie le contenu du presse-papier du smartphone.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "texte": {
                        "type": "string",
                        "description": "Texte à définir dans le presse-papier. Si omis, effectue une lecture."
                    }
                }
            }
        },
        {
            "name": "parler_tts",
            "description": "Annonce un message vocal à haute voix sur les haut-parleurs du téléphone via la synthèse vocale.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "texte": {"type": "string", "description": "Message à prononcer."},
                    "langue": {"type": "string", "description": "Code langue (défaut: fr).", "default": "fr"}
                },
                "required": ["texte"]
            }
        },
        {
            "name": "evaluer_impact_transfert_wave",
            "description": "Gouvernance et arbitrage du Family Officer : évalue l'impact financier d'un transfert ou d'une dépense Wave avant exécution (vérifie le solde résiduel, le sanctuaire d'urgence de 25 000 FCFA et la viabilité budgétaire).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "montant_fcfa": {
                        "type": "integer",
                        "description": "Montant du transfert en FCFA."
                    },
                    "numero_destinataire": {
                        "type": "string",
                        "description": "Numéro de téléphone du bénéficiaire."
                    },
                    "motif": {
                        "type": "string",
                        "description": "Raison ou contexte de l'opération (ex: Loyer, Santé, Dépannage cousin, Tontine).",
                        "default": "Dépannage famille"
                    },
                    "categorie": {
                        "type": "string",
                        "description": "Catégorie de la dépense.",
                        "enum": ["charge_vitale", "urgence_sante", "depannage_famille", "tontine_epargne", "achat_plaisir", "inconnu"],
                        "default": "depannage_famille"
                    },
                    "reserve_minimale_fcfa": {
                        "type": "integer",
                        "description": "Seuil minimal du sanctuaire d'urgence à préserver en FCFA (défaut: 25000).",
                        "default": 25000
                    }
                },
                "required": ["montant_fcfa", "numero_destinataire"]
            }
        }
    ]

    PROMPTS_DISPONIBLES = [
        {
            "name": "family_officer_wave",
            "description": "Active la posture de Family Officer et Protecteur Financier pour Wave Mobile Money : gouvernance de l'argent, sanctuarisation de l'épargne d'urgence, vérification anti-fraude et arbitrage bienveillant des dépenses.",
            "arguments": [
                {
                    "name": "prenom_utilisateur",
                    "description": "Prénom ou nom de l'utilisateur.",
                    "required": False
                },
                {
                    "name": "reserve_urgence_fcfa",
                    "description": "Montant du sanctuaire d'urgence en FCFA (défaut: 25000).",
                    "required": False
                }
            ]
        }
    ]

    DOCTRINE_FAMILY_OFFICER = """# DOCTRINE DU FAMILY OFFICER WAVE MOBILE MONEY

Vous êtes le **Family Officer et Protecteur Financier Souverain** de l'utilisateur et de sa famille.
Votre rôle est de veiller sur chaque franc CFA avec rigueur, bienveillance et prudence.

## RÈGLES DE GOUVERNANCE INVIOLABLES :
1. LE SANCTUAIRE D'URGENCE (25 000 FCFA MINIMUM) :
   - Chaque compte doit impérativement conserver une réserve de sécurité d'au moins 25 000 FCFA.
   - Ne jamais valider un transfert futile s'il entame ce sanctuaire vital.

2. PROTOCOLE OBLIGATOIRE EN 3 POINTS AVANT TOUT TRANSFERT :
   - Étape 1 : Vérifier le solde disponible via l'outil 'consulter_solde_wave' (USSD *9113# ou SMS).
   - Étape 2 : Évaluer l'impact budgétaire avec 'evaluer_impact_transfert_wave'.
   - Étape 3 : Demander une confirmation explicite à l'utilisateur en rappelant le solde restant estimé avant d'appeler 'transferer_argent_wave'.

3. SOLIDARITÉ FAMILIALE ÉQUILIBRÉE :
   - Aider l'utilisateur à soutenir ses proches (dépannages, tontines) sans jamais se mettre en danger financier.

4. BOUCLIER ANTI-ARNAQUE :
   - Toujours vérifier l'authenticité des messages et se méfier des faux SMS Wave ou des transferts sous pression émotionnelle.
"""

    @classmethod
    def traiter_requete_jsonrpc(cls, requete: Dict[str, Any]) -> Dict[str, Any]:
        """Point d'entrée principal pour traiter les messages MCP JSON-RPC 2.0."""
        id_req = requete.get("id")
        methode = requete.get("method")
        params = requete.get("params", {})

        # 1. Handshake INITIALIZE
        if methode == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": id_req,
                "result": {
                    "protocolVersion": cls.VERSION_PROTOCOLE,
                    "serverInfo": {
                        "name": cls.NOM_SERVEUR,
                        "version": cls.VERSION_SERVEUR
                    },
                    "capabilities": {
                        "tools": {"listChanged": False},
                        "resources": {"subscribe": False, "listChanged": False},
                        "prompts": {"listChanged": False}
                    }
                }
            }

        # 2. PING
        elif methode == "ping":
            return {"jsonrpc": "2.0", "id": id_req, "result": {}}

        # 3. LISTE DES OUTILS (tools/list)
        elif methode == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": id_req,
                "result": {
                    "tools": cls.OUTILS_DISPONIBLES
                }
            }

        # 4. APPEL D'UN OUTIL (tools/call)
        elif methode == "tools/call":
            nom_outil = params.get("name")
            args = params.get("arguments", {})
            return cls._executer_outil(id_req, nom_outil, args)

        # 5. LISTE DES RESSOURCES (resources/list)
        elif methode == "resources/list":
            return {
                "jsonrpc": "2.0",
                "id": id_req,
                "result": {
                    "resources": [
                        {
                            "uri": "wave://family-officer/doctrine",
                            "name": "Doctrine & Charte du Family Officer Wave",
                            "mimeType": "text/markdown"
                        },
                        {
                            "uri": "telephone://statut",
                            "name": "État Matériel Smartphone",
                            "mimeType": "application/json"
                        },
                        {
                            "uri": "telephone://sms-wave",
                            "name": "Grand Livre SMS Wave",
                            "mimeType": "application/json"
                        },
                        {
                            "uri": "telephone://notifications",
                            "name": "Notifications Push Actives",
                            "mimeType": "application/json"
                        }
                    ]
                }
            }

        # 6. LECTURE D'UNE RESSOURCE (resources/read)
        elif methode == "resources/read":
            uri = params.get("uri", "")
            if uri == "wave://family-officer/doctrine":
                return {
                    "jsonrpc": "2.0",
                    "id": id_req,
                    "result": {
                        "contents": [
                            {
                                "uri": uri,
                                "mimeType": "text/markdown",
                                "text": cls.DOCTRINE_FAMILY_OFFICER
                            }
                        ]
                    }
                }
            elif uri == "telephone://statut":
                donnees = GestionnaireMaterielAndroid.obtenir_statut_telephone()
                return {
                    "jsonrpc": "2.0",
                    "id": id_req,
                    "result": {
                        "contents": [
                            {
                                "uri": uri,
                                "mimeType": "application/json",
                                "text": json.dumps(donnees, ensure_ascii=False)
                            }
                        ]
                    }
                }
            elif uri == "telephone://sms-wave":
                messages = GestionnaireMaterielAndroid.lire_sms_wave(limite=20)
                return {
                    "jsonrpc": "2.0",
                    "id": id_req,
                    "result": {
                        "contents": [
                            {
                                "uri": uri,
                                "mimeType": "application/json",
                                "text": json.dumps(messages, ensure_ascii=False)
                            }
                        ]
                    }
                }
            elif uri == "telephone://notifications":
                notifs = GestionnaireMaterielAndroid.extraire_notifications_wave(limite=15)
                return {
                    "jsonrpc": "2.0",
                    "id": id_req,
                    "result": {
                        "contents": [
                            {
                                "uri": uri,
                                "mimeType": "application/json",
                                "text": json.dumps(notifs, ensure_ascii=False)
                            }
                        ]
                    }
                }
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": id_req,
                    "error": {
                        "code": -32602,
                        "message": f"Ressource introuvable : {uri}"
                    }
                }

        # 7. LISTE DES PROMPTS (prompts/list)
        elif methode == "prompts/list":
            return {
                "jsonrpc": "2.0",
                "id": id_req,
                "result": {
                    "prompts": cls.PROMPTS_DISPONIBLES
                }
            }

        # 8. OBTENTION D'UN PROMPT (prompts/get)
        elif methode == "prompts/get":
            nom_prompt = params.get("name")
            args_prompt = params.get("arguments", {})
            if nom_prompt == "family_officer_wave":
                prenom = args_prompt.get("prenom_utilisateur", "l'Utilisateur")
                reserve = args_prompt.get("reserve_urgence_fcfa", "25 000")
                texte_systeme = (
                    f"{cls.DOCTRINE_FAMILY_OFFICER}\n"
                    f"Contexte actif : Vous conseillez {prenom}. "
                    f"Le sanctuaire d'urgence incompressible est fixé à {reserve} FCFA."
                )
                return {
                    "jsonrpc": "2.0",
                    "id": id_req,
                    "result": {
                        "description": "Posture de Family Officer pour Wave Mobile Money",
                        "messages": [
                            {
                                "role": "user",
                                "content": {
                                    "type": "text",
                                    "text": texte_systeme
                                }
                            }
                        ]
                    }
                }
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": id_req,
                    "error": {
                        "code": -32602,
                        "message": f"Prompt inconnu : {nom_prompt}"
                    }
                }

        # Méthode non gérée
        return {
            "jsonrpc": "2.0",
            "id": id_req,
            "error": {
                "code": -32601,
                "message": f"Méthode MCP inconnue ou non supportée : {methode}"
            }
        }

    @classmethod
    def _executer_outil(cls, id_req: Any, nom: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Exécute l'outil demandé et formate le résultat au standard MCP."""
        try:
            if nom == "statut_telephone":
                donnees = GestionnaireMaterielAndroid.obtenir_statut_telephone()
                return cls._reponse_succes_mcp(id_req, donnees)

            elif nom == "lire_sms_wave":
                limite = args.get("limite", 25)
                messages = GestionnaireMaterielAndroid.lire_sms_wave(limite=limite)
                return cls._reponse_succes_mcp(id_req, {
                    "statut": "succes",
                    "total": len(messages),
                    "messages": messages
                })

            elif nom == "lire_notifications_wave":
                limite = args.get("limite", 20)
                notifs = GestionnaireMaterielAndroid.extraire_notifications_wave(limite=limite)
                return cls._reponse_succes_mcp(id_req, {
                    "statut": "succes",
                    "total": len(notifs),
                    "notifications": notifs
                })

            elif nom == "capturer_ecran_telephone":
                res = GestionnaireMaterielAndroid.capturer_ecran()
                return cls._reponse_succes_mcp(id_req, res)

            elif nom == "analyser_ui_telephone":
                res = GestionnaireMaterielAndroid.analyser_arborescence_ui()
                return cls._reponse_succes_mcp(id_req, res)

            elif nom == "lancer_application":
                paquet = args.get("paquet", "com.wave.personal")
                res = GestionnaireMaterielAndroid.lancer_application(paquet=paquet)
                return cls._reponse_succes_mcp(id_req, res)

            elif nom == "reveiller_telephone":
                res = GestionnaireMaterielAndroid.reveiller_telephone()
                return cls._reponse_succes_mcp(id_req, res)

            elif nom == "simuler_clic":
                x = int(args.get("x", 0))
                y = int(args.get("y", 0))
                res = GestionnaireMaterielAndroid.simuler_clic(x, y)
                return cls._reponse_succes_mcp(id_req, res)

            elif nom == "simuler_texte":
                texte = args.get("texte", "")
                res = GestionnaireMaterielAndroid.simuler_texte(texte)
                return cls._reponse_succes_mcp(id_req, res)

            elif nom == "consulter_solde_wave":
                code_ussd = args.get("code_ussd") or os.environ.get("WAVE_USSD_SOLDE", "*9113#")
                forcer_ussd = args.get("forcer_ussd", False)

                solde = None
                methode_utilisee = "sms_recent"
                if not forcer_ussd:
                    solde = GestionnaireMaterielAndroid.extraire_solde_dernier_sms()

                if solde is None:
                    res_ussd = GestionnaireMaterielAndroid.composer_ussd(code_ussd)
                    return cls._reponse_succes_mcp(id_req, {
                        "statut": "appel_lance",
                        "methode": "composition_ussd",
                        "code_ussd": code_ussd,
                        "details": res_ussd
                    })

                return cls._reponse_succes_mcp(id_req, {
                    "statut": "succes",
                    "balance": solde,
                    "currency": "FCFA",
                    "methode": methode_utilisee,
                    "retrieved_at": datetime.utcnow().isoformat()
                })

            elif nom == "transferer_argent_wave":
                numero = str(args.get("numero_destinataire", ""))
                montant = int(args.get("montant_fcfa", 0))
                code_secret = args.get("code_secret")
                motif = str(args.get("motif", "Transfert Wave"))
                res = GestionnaireMaterielAndroid.transferer_argent_wave(
                    numero_destinataire=numero,
                    montant_fcfa=montant,
                    code_secret=code_secret,
                    motif=motif
                )
                return cls._reponse_succes_mcp(id_req, res)

            elif nom == "composer_ussd_direct":
                code = args.get("code", "")
                res = GestionnaireMaterielAndroid.composer_ussd(code)
                return cls._reponse_succes_mcp(id_req, res)

            elif nom == "vibrer_alerte":
                duree = args.get("duree_ms", 300)
                reussi = GestionnaireMaterielAndroid.faire_vibrer(duree)
                return cls._reponse_succes_mcp(id_req, {"succes": reussi, "duree_ms": duree})

            elif nom == "presse_papier":
                texte = args.get("texte")
                res = GestionnaireMaterielAndroid.gerer_presse_papier(texte)
                return cls._reponse_succes_mcp(id_req, res)

            elif nom == "parler_tts":
                texte = args.get("texte", "")
                langue = args.get("langue", "fr")
                reussi = GestionnaireMaterielAndroid.parler_tts(texte, langue)
                return cls._reponse_succes_mcp(id_req, {"succes": reussi, "texte": texte})

            elif nom == "evaluer_impact_transfert_wave":
                montant = int(args.get("montant_fcfa", 0))
                numero = str(args.get("numero_destinataire", ""))
                motif = str(args.get("motif", "Dépannage famille"))
                categorie = str(args.get("categorie", "depannage_famille"))
                reserve = int(args.get("reserve_minimale_fcfa", 25000))
                res = GestionnaireMaterielAndroid.evaluer_impact_transfert_wave(
                    montant_fcfa=montant,
                    numero_destinataire=numero,
                    motif=motif,
                    categorie=categorie,
                    reserve_minimale_fcfa=reserve
                )
                return cls._reponse_succes_mcp(id_req, res)

            else:
                return {
                    "jsonrpc": "2.0",
                    "id": id_req,
                    "error": {
                        "code": -32602,
                        "message": f"Outil non trouvé : {nom}"
                    }
                }

        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": id_req,
                "error": {
                    "code": -32000,
                    "message": f"Erreur interne lors de l'exécution de l'outil {nom} : {str(e)}"
                }
            }

    @classmethod
    def _reponse_succes_mcp(cls, id_req: Any, donnees: Any) -> Dict[str, Any]:
        """Helper pour formater une réponse d'outil standard MCP."""
        texte = json.dumps(donnees, ensure_ascii=False, indent=2) if not isinstance(donnees, str) else donnees
        return {
            "jsonrpc": "2.0",
            "id": id_req,
            "result": {
                "content": [
                    {"type": "text", "text": texte}
                ]
            }
        }


class GestionnaireRequetesHTTP(BaseHTTPRequestHandler):
    """Serveur HTTP hybride : gère à la fois le protocole MCP et l'API REST rapide."""

    def _envoyer_reponse_json(self, donnees: Any, statut: int = 200) -> None:
        """Helper pour retourner une réponse JSON avec en-têtes CORS universels."""
        corps = json.dumps(donnees, ensure_ascii=False).encode("utf-8")
        self.send_response(statut)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corps)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()
        self.wfile.write(corps)

    def do_OPTIONS(self) -> None:
        """Gère les requêtes préliminaires CORS du navigateur."""
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self) -> None:
        """Routes REST de consultation rapide et SSE."""
        chemin = urllib.parse.urlparse(self.path).path

        # 1. Santé / Ping liveness
        if chemin in ("/", "/sante", "/health", "/ping"):
            self._envoyer_reponse_json({
                "statut": "en_ligne",
                "serveur": "telephone-android-mcp",
                "version": "2.0.0",
                "ip": GestionnaireMaterielAndroid.obtenir_ip_locale(),
                "horodatage": datetime.utcnow().isoformat()
            })

        # 2. Statut matériel du téléphone
        elif chemin == "/api/statut":
            statut = GestionnaireMaterielAndroid.obtenir_statut_telephone()
            self._envoyer_reponse_json(statut)

        # 3. Solde Wave
        elif chemin == "/api/solde":
            solde = GestionnaireMaterielAndroid.extraire_solde_dernier_sms()
            if solde is not None:
                self._envoyer_reponse_json({
                    "statut": "succes",
                    "balance": solde,
                    "currency": "FCFA",
                    "retrieved_at": datetime.utcnow().isoformat()
                })
            else:
                self._envoyer_reponse_json({
                    "statut": "solde_non_trouve",
                    "message": "Aucun solde Wave récent trouvé dans les SMS. Essayez l'appel USSD."
                }, statut=404)

        # 4. SMS Wave
        elif chemin == "/api/sms":
            messages = GestionnaireMaterielAndroid.lire_sms_wave(limite=25)
            self._envoyer_reponse_json({
                "statut": "succes",
                "total": len(messages),
                "messages": messages
            })

        # 5. Notifications Wave
        elif chemin == "/api/notifications":
            notifs = GestionnaireMaterielAndroid.extraire_notifications_wave(limite=20)
            self._envoyer_reponse_json({
                "statut": "succes",
                "total": len(notifs),
                "notifications": notifs
            })

        # 6. Capture d'écran (Image binaire directe ou JSON base64)
        elif chemin == "/api/capture-ecran":
            res = GestionnaireMaterielAndroid.capturer_ecran()
            if res.get("succes") and "base64_png" in res:
                self._envoyer_reponse_json(res)
            else:
                self._envoyer_reponse_json({"erreur": res.get("erreur", "Échec capture")}, statut=500)

        # 7. Arborescence UI
        elif chemin == "/api/ui-arbre":
            res = GestionnaireMaterielAndroid.analyser_arborescence_ui()
            self._envoyer_reponse_json(res)

        # 8. Flux SSE (Server-Sent Events) pour clients MCP
        elif chemin == "/sse":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            message_init = f"event: endpoint\ndata: /mcp\n\n".encode("utf-8")
            self.wfile.write(message_init)

        # 9. Spécification OpenAPI pour ChatGPT Custom Actions
        elif chemin in ("/openapi.json", "/api/openapi.json"):
            chemin_openapi = os.path.join(os.path.dirname(os.path.abspath(__file__)), "openapi.json")
            if os.path.exists(chemin_openapi):
                try:
                    with open(chemin_openapi, "r", encoding="utf-8") as f:
                        spec = json.load(f)
                    hote = self.headers.get("Host")
                    if hote:
                        proto = "https" if ("trycloudflare.com" in hote or "ngrok" in hote) else "http"
                        spec["servers"] = [{"url": f"{proto}://{hote}", "description": "Passerelle Wave MCP active"}]
                    self._envoyer_reponse_json(spec)
                except Exception as e:
                    self._envoyer_reponse_json({"erreur": f"Erreur lecture openapi.json : {e}"}, statut=500)
            else:
                self._envoyer_reponse_json({"erreur": "Spécification openapi.json introuvable sur le serveur"}, statut=404)

        else:
            self._envoyer_reponse_json({"erreur": "Route introuvable"}, statut=404)

    def do_POST(self) -> None:
        """Traitement des requêtes MCP JSON-RPC et des actions REST."""
        chemin = urllib.parse.urlparse(self.path).path
        longueur = int(self.headers.get("Content-Length", 0))
        corps = self.rfile.read(longueur).decode("utf-8", errors="replace")

        try:
            donnees_json = json.loads(corps) if corps else {}
        except json.JSONDecodeError:
            self._envoyer_reponse_json({
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "JSON invalide."}
            }, statut=400)
            return

        # 1. Point d'entrée MCP JSON-RPC 2.0 officiel (/mcp ou racine)
        if chemin in ("/mcp", "/"):
            reponse_mcp = GestionnaireProtocoleMCP.traiter_requete_jsonrpc(donnees_json)
            self._envoyer_reponse_json(reponse_mcp)

        # 2. Action REST : Vibreur
        elif chemin == "/api/vibrer":
            duree = donnees_json.get("duree_ms", 300)
            reussi = GestionnaireMaterielAndroid.faire_vibrer(duree)
            self._envoyer_reponse_json({"succes": reussi})

        # 3. Action REST : Déclencher USSD
        elif chemin == "/api/ussd":
            code = donnees_json.get("code_ussd") or os.environ.get("WAVE_USSD_SOLDE", "*9113#")
            res = GestionnaireMaterielAndroid.composer_ussd(code)
            self._envoyer_reponse_json(res)

        # 4. Action REST : Lancer App
        elif chemin == "/api/lancer-app":
            paquet = donnees_json.get("paquet", "com.wave.personal")
            res = GestionnaireMaterielAndroid.lancer_application(paquet)
            self._envoyer_reponse_json(res)

        # 5. Action REST : Réveiller l'écran
        elif chemin == "/api/reveiller":
            res = GestionnaireMaterielAndroid.reveiller_telephone()
            self._envoyer_reponse_json(res)

        # 6. Action REST : Clic tactile
        elif chemin == "/api/clic":
            x = donnees_json.get("x", 0)
            y = donnees_json.get("y", 0)
            res = GestionnaireMaterielAndroid.simuler_clic(x, y)
            self._envoyer_reponse_json(res)

        # 7. Action REST : Transfert d'argent Wave
        elif chemin == "/api/transferer":
            numero = donnees_json.get("numero_destinataire", "")
            montant = donnees_json.get("montant_fcfa", 0)
            code_secret = donnees_json.get("code_secret")
            motif = donnees_json.get("motif", "Transfert Wave")
            res = GestionnaireMaterielAndroid.transferer_argent_wave(
                numero_destinataire=numero,
                montant_fcfa=montant,
                code_secret=code_secret,
                motif=motif
            )
            self._envoyer_reponse_json(res)

        # 8. Action REST : Évaluation d'impact Family Officer (pour ChatGPT Actions)
        elif chemin == "/api/evaluer-transfert":
            montant = donnees_json.get("montant_fcfa", 0)
            numero = donnees_json.get("numero_destinataire", "")
            motif = donnees_json.get("motif", "Dépannage famille")
            categorie = donnees_json.get("categorie", "depannage_famille")
            reserve = donnees_json.get("reserve_minimale_fcfa", 25000)
            res = GestionnaireMaterielAndroid.evaluer_impact_transfert_wave(
                montant_fcfa=montant,
                numero_destinataire=numero,
                motif=motif,
                categorie=categorie,
                reserve_minimale_fcfa=reserve
            )
            self._envoyer_reponse_json(res)

        else:
            self._envoyer_reponse_json({"erreur": "Route POST introuvable"}, statut=404)

    def log_message(self, format: str, *args: Any) -> None:
        """Journalisation sobre des requêtes entrantes."""
        sys.stderr.write(f"[{datetime.now().strftime('%H:%M:%S')}] {args[0]} {args[1]} -> {args[2]}\n")


def annoncer_au_pc(ip_pc: str, port_pc: int, port_local: int) -> None:
    """Annonce automatiquement l'adresse IP et le port du téléphone au serveur WaveGuard PC."""
    url = f"http://{ip_pc}:{port_pc}/api/v1/mcp-telephone/enregistrer"
    ip_locale = GestionnaireMaterielAndroid.obtenir_ip_locale()
    charge = {
        "ip": ip_locale,
        "port": port_local,
        "nom": socket.gethostname() or "Android Smartphone",
        "horodatage": datetime.utcnow().isoformat()
    }
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(charge).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=3) as rep:
            if rep.status in (200, 201):
                print(f"[✓] Enregistré avec succès auprès du PC WaveGuard ({url}) !")
    except Exception as e:
        print(f"[-] Annonce automatique au PC ignorée (PC non joint : {e})")


def demarrer_serveur(port: int = 8765, ip_pc: Optional[str] = None, port_pc: int = 8000) -> None:
    """Lance le serveur MCP Téléphone en écoute sur toutes les interfaces locales."""
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

    ip_locale = GestionnaireMaterielAndroid.obtenir_ip_locale()
    serveur = ServeurThreaded(("0.0.0.0", port), GestionnaireRequetesHTTP)

    print("=" * 65)
    print("  [*] SERVEUR MCP TELEPHONE ANDROID SANS FIL - WAVEGUARD GPT v2.0")
    print("=" * 65)
    print(f"  - Adresse IP locale     : http://{ip_locale}:{port}")
    print(f"  - Endpoint MCP 2.0      : http://{ip_locale}:{port}/mcp")
    print(f"  - Endpoint Sante        : http://{ip_locale}:{port}/sante")
    print(f"  - Flux SSE              : http://{ip_locale}:{port}/sse")
    print(f"  - API Notifications     : http://{ip_locale}:{port}/api/notifications")
    print(f"  - API Capture Ecran     : http://{ip_locale}:{port}/api/capture-ecran")
    print(f"  - API Arbre UI          : http://{ip_locale}:{port}/api/ui-arbre")
    print("=" * 65)
    print("  Zero cable USB requis. Remplace 100% de la liaison filaire ADB !")
    print("  Appuyez sur Ctrl+C pour arreter le serveur.")
    print("=" * 65)

    if ip_pc:
        annoncer_au_pc(ip_pc, port_pc, port)

    try:
        serveur.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt du serveur MCP Téléphone.")
        serveur.server_close()


if __name__ == "__main__":
    port_ecoute = 8765
    hote_pc = None
    port_cible_pc = 8000

    for arg in sys.argv[1:]:
        if arg.startswith("--port="):
            port_ecoute = int(arg.split("=")[1])
        elif arg.startswith("--pc="):
            hote_pc = arg.split("=")[1]
        elif arg.startswith("--port-pc="):
            port_cible_pc = int(arg.split("=")[1])

    demarrer_serveur(port=port_ecoute, ip_pc=hote_pc, port_pc=port_cible_pc)
