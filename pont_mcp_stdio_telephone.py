#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pont Stdio MCP pour Téléphone Android (Antigravity IDE / Claude Desktop).
Sert de relais standard entre l'IDE (sur stdin/stdout) et le serveur MCP sans fil
exécuté sur le smartphone Android (Termux) via Wi-Fi.

Permet à l'agent IA d'interagir directement avec le téléphone sans aucun câble USB.
Respecte strictement les 4 états anti-fallback et la convention de nommage en français.
"""

import sys
import os
import json
import urllib.request
import urllib.error
from typing import Dict, Any, Optional

FICHIER_CONFIG_MCP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config_mcp_telephone.json")


def charger_configuration() -> Dict[str, Any]:
    """Charge l'adresse IP et le port du téléphone depuis la configuration persistante."""
    if os.path.exists(FICHIER_CONFIG_MCP):
        try:
            with open(FICHIER_CONFIG_MCP, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"ip_telephone": None, "port_telephone": 8765, "nom_appareil": None}


def envoyer_requete_telephone(charge_mcp: Dict[str, Any], timeout: float = 12.0) -> Dict[str, Any]:
    """Transmet la requête JSON-RPC au serveur MCP tournant sur le smartphone Android."""
    config = charger_configuration()
    ip = config.get("ip_telephone")
    port = config.get("port_telephone", 8765)

    if not ip:
        return {
            "jsonrpc": "2.0",
            "id": charge_mcp.get("id"),
            "error": {
                "code": -32001,
                "message": (
                    "Aucun smartphone Android n'est configuré. Lancez 'python serveur_mcp_telephone.py --pc=<VOTRE_IP_PC>' "
                    "sur Termux pour l'enregistrer automatiquement, ou configurez son IP dans config_mcp_telephone.json."
                )
            }
        }

    url = f"http://{ip}:{port}/mcp"
    donnees_octets = json.dumps(charge_mcp, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=donnees_octets,
        headers={"Content-Type": "application/json; charset=utf-8"}
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as reponse:
            corps = reponse.read().decode("utf-8", errors="replace")
            return json.loads(corps)
    except urllib.error.URLError as e:
        return {
            "jsonrpc": "2.0",
            "id": charge_mcp.get("id"),
            "error": {
                "code": -32002,
                "message": f"Smartphone Android non joignable sur {url} ({str(e)}). Vérifiez la connexion Wi-Fi et que Termux est actif."
            }
        }
    except Exception as e:
        return {
            "jsonrpc": "2.0",
            "id": charge_mcp.get("id"),
            "error": {
                "code": -32000,
                "message": f"Erreur de communication avec le téléphone : {str(e)}"
            }
        }


def traiter_ligne(ligne: str) -> Optional[Dict[str, Any]]:
    """Traite un message JSON-RPC MCP reçu sur stdin."""
    ligne_nettoyee = ligne.strip()
    if not ligne_nettoyee:
        return None

    try:
        requete = json.loads(ligne_nettoyee)
    except json.JSONDecodeError:
        return {
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32700, "message": "JSON invalide."}
        }

    methode = requete.get("method")
    id_req = requete.get("id")

    # 1. INITIALIZE (Handshake immédiat pour ne pas bloquer l'IDE si le téléphone est temporairement en veille)
    if methode == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": id_req,
            "result": {
                "protocolVersion": "2024-11-05",
                "serverInfo": {
                    "name": "telephone-android-mcp-bridge",
                    "version": "2.0.0"
                },
                "capabilities": {
                    "tools": {"listChanged": False},
                    "resources": {"subscribe": False, "listChanged": False}
                }
            }
        }

    # 2. PING
    elif methode == "ping":
        return {"jsonrpc": "2.0", "id": id_req, "result": {}}

    # 3. NOTIFICATION NOTIFICATIONS/INITIALIZED (aucun id, ne pas répondre)
    elif methode == "notifications/initialized":
        return None

    # 4. Transmettre toutes les autres requêtes (tools/list, tools/call, resources/list) au téléphone
    return envoyer_requete_telephone(requete)


def main():
    """Boucle principale stdio conforme au protocole Model Context Protocol."""
    try:
        sys.stdin.reconfigure(encoding='utf-8', errors='replace')
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

    for ligne in sys.stdin:
        reponse = traiter_ligne(ligne)
        if reponse is not None:
            sys.stdout.write(json.dumps(reponse, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
