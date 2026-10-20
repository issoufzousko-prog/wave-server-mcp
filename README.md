<p align="center">
  <img src="assets/wave-server-mcp-logo.png" alt="Wave Server MCP Logo" width="200"/>
</p>

# 🐧 Wave Server MCP

> **Serveur MCP (Model Context Protocol) Android sans fil pour Wave Mobile Money (Côte d'Ivoire & zone UEMOA)**  
> Contrôlez, automatisez et interrogez votre compte Wave directement depuis vos agents IA (Claude Desktop, Antigravity IDE, Cursor) via Wi-Fi — **sans câble USB ADB** et **sans fuite cloud**.

---

## 🌟 Points forts

- 📶 **100 % Sans Fil** : Plus besoin de câble USB ni de mode débogage ADB filaire permanent. Le smartphone tourne sur Termux et communique en Wi-Fi local ou Hotspot.
- 🪶 **Zéro Dépendance pip sur Android** : Le serveur utilise exclusivement la bibliothèque standard Python 3 et les commandes de `termux-api`.
- 🔌 **Protocole Officiel MCP JSON-RPC 2.0** : Outils (`tools`), ressources (`resources`) et prompts déclarés selon les spécifications Model Context Protocol.
- ⚡ **Pont STDIO Universel** : Relais bidirectionnel prêt pour Claude Desktop, Antigravity IDE, Cursor et tout client MCP stdio.
- 🔒 **Souverain & Sécurisé** : Aucune donnée bancaire ne transite par des serveurs tiers. Tout reste strictement sur votre réseau local.

---

## 🛠️ Outils MCP disponibles

| Outil MCP | Description | Mécanisme |
|---|---|---|
| `consulter_solde_wave` | Récupère le solde certifié Wave en temps réel | USSD natif `*9113#` ou capture OCR locale |
| `transferer_argent_wave` | Effectue un transfert d'argent sécurisé vers un destinataire | Automatisation USSD avec code secret |
| `lire_derniers_sms_wave` | Lit et filtre les SMS officiels reçus de Wave | API Termux SMS (`termux-sms-list`) |
| `lire_notifications_wave` | Intercepte les notifications push de l'application Wave | API Termux Notification |
| `capturer_ecran` | Capture l'écran de l'appareil Android en temps réel | `screencap` encodé en base64 |
| `obtenir_statut_telephone` | Retourne l'état de la batterie, du Wi-Fi et de l'appareil | Sondes matérielles Termux |
| `lancer_application_wave` | Ouvre l'application Wave au premier plan | Monkey runner Android |
| `vibrer_telephone` | Fait vibrer le téléphone (accusé de réception ou alerte) | Termux Vibrate API |

---

## 🏗️ Architecture du système

```
┌─────────────────────────────────┐        Wi-Fi Local         ┌─────────────────────────────────┐
│            Ordinateur           │ ◄────────────────────────► │        Smartphone Android       │
│                                 │                            │             (Termux)            │
│  ┌───────────────────────────┐  │                            │  ┌───────────────────────────┐  │
│  │   Agent IA                │  │                            │  │  serveur_mcp_             │  │
│  │   (Claude, Antigravity)   │  │   MCP JSON-RPC 2.0 HTTP    │  │  telephone.py             │  │
│  └─────────────┬─────────────┘  │   (port 8765)              │  │  (Serveur HTTP multithread│  │
│                │ stdio          │◄──────────────────────────►│  └─────────────┬─────────────┘  │
│  ┌─────────────▼─────────────┐  │                            │                │ Termux:API     │
│  │  pont_mcp_stdio_          │  │                            │  ┌─────────────▼─────────────┐  │
│  │  telephone.py             │  │                            │  │  Application Wave / USSD  │  │
│  └───────────────────────────┘  │                            │  │  SMS & Système Android    │  │
│                                 │                            │  └───────────────────────────┘  │
└─────────────────────────────────┘                            └─────────────────────────────────┘
```

---

## 🚀 Installation & Démarrage

### Étape 1 : Prérequis sur le smartphone Android

1. Installez **[Termux](https://f-droid.org/fr/packages/com.termux/)** depuis F-Droid (évitez la version obsolète du Play Store).
2. Installez **[Termux:API](https://f-droid.org/fr/packages/com.termux.api/)** depuis F-Droid.
3. Ouvrez les Paramètres Android → Applications → Termux:API et accordez les autorisations :
   - SMS (lecture)
   - Téléphone / Appels (USSD)
   - Notifications (accès)
   - Stockage

### Étape 2 : Lancer le serveur sur Termux (en 1 commande)

Ouvrez Termux sur votre téléphone et exécutez :

```bash
pkg update -y && pkg install -y git python termux-api
git clone https://github.com/issoufzousko-prog/wave-server-mcp.git
cd wave-server-mcp
chmod +x installer_mcp_termux.sh
./installer_mcp_termux.sh
```

Ou démarrez directement le serveur Python :

```bash
python serveur_mcp_telephone.py --port=8765
```

Le serveur s'initialise et affiche son adresse IP locale (ex: `http://192.168.1.50:8765`).

---

## 💻 Configuration côté PC / IDE

### Option A : Intégration Claude Desktop (`claude_desktop_config.json`)

Ajoutez cette configuration dans votre fichier `claude_desktop_config.json` :

```json
{
  "mcpServers": {
    "wave-telephone": {
      "command": "python",
      "args": [
        "/chemin/absolu/vers/wave-server-mcp/pont_mcp_stdio_telephone.py"
      ],
      "env": {
        "IP_TELEPHONE": "192.168.1.50",
        "PORT_TELEPHONE": "8765"
      }
    }
  }
}
```

### Option B : Intégration Antigravity IDE (`mcp_config.json`)

Dans votre fichier `.agents/mcp_config.json` :

```json
{
  "mcpServers": {
    "wave-android": {
      "command": "python",
      "args": [
        "c:/chemin/vers/wave-server-mcp/pont_mcp_stdio_telephone.py"
      ],
      "env": {
        "IP_TELEPHONE": "192.168.1.50",
        "PORT_TELEPHONE": "8765"
      }
    }
  }
}
```

---

## 🐍 Utilisation directe avec le client Python

Un client Python (`client_mcp.py`) est fourni pour interroger facilement le smartphone depuis n'importe quel script :

```python
from client_mcp import ServiceClientMcpTelephone

client = ServiceClientMcpTelephone()

# Tester la connexion
sante = client.verifier_sante()
print("Statut téléphone :", sante)

# Consulter le solde Wave via USSD
resultat_solde = client.executer_outil_mcp("consulter_solde_wave", {})
print("Solde Wave :", resultat_solde)

# Lire les 5 derniers SMS
sms = client.executer_outil_mcp("lire_derniers_sms_wave", {"limite": 5})
print("Derniers SMS :", sms)
```

---

## 🔒 Confidentialité & Sécurité

- Aucune clé d'API ni code secret n'est inclus par défaut dans ce dépôt.
- Les identifiants USSD (code PIN Wave) sont gérés exclusivement via votre fichier `.env` local.
- Les communications ont lieu à l'intérieur de votre réseau Wi-Fi local sans accès extérieur.

---

## 📄 Licence

Ce projet est sous licence [MIT](LICENSE) — Libre d'utilisation, de modification et d'intégration.

---

<p align="center">
  <img src="assets/wave-server-mcp-logo.png" alt="Wave Server MCP Mascot" width="150"/>
</p>
