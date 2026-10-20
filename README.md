<p align="center">
  <img src="assets/wave-server-mcp-logo.png" alt="Wave Server MCP Logo" width="190"/>
</p>

# 🐧 Wave Server MCP

> **Serveur MCP (Model Context Protocol) pour Android permettant de connecter vos agents IA sur ordinateur (Claude Desktop, Cursor, Antigravity, ChatGPT) à Wave Mobile Money via requêtes USSD directes et sans fil.**  
> Intègre nativement la posture et le skill de **Family Officer** pour protéger votre argent, sanctuariser l'épargne d'urgence et arbitrer chaque transfert.

---

## 🎯 Contexte & Objectif

Les modèles d'IA sur ordinateur (Claude Desktop, Cursor, Antigravity IDE, agents locaux) ne disposent d'aucun accès direct aux cartes SIM ni aux réseaux télécoms pour exécuter des requêtes USSD Mobile Money.

**Wave Server MCP** fait le pont sans fil entre votre PC et votre smartphone :
1. **Sur votre PC** : Vous échangez en langage naturel avec votre IA (ex: *« Quel est mon solde Wave ? »* ou *« Envoie 2 000 FCFA à maman »*).
2. **Sur votre téléphone Android** : Ce serveur MCP tourne dans Termux et écoute en Wi-Fi local.
3. **Exécution directe** : Le téléphone déclenche instantanément les requêtes USSD officielles (`*9113#`), lit les SMS et renvoie le résultat certifié à l'IA.

```text
┌────────────────────────────────────────────────────────┐
│     Interface IA sur Ordinateur (PC / Mac)             │
│        (Claude Desktop, Cursor, Antigravity IDE)       │
└───────────────────────────┬────────────────────────────┘
                            │ Protocole MCP (JSON-RPC 2.0)
                            │ Wi-Fi local / Hotspot (Port 8765)
┌───────────────────────────▼────────────────────────────┐
│         Serveur MCP Android (Termux en Wi-Fi)          │
│                serveur_mcp_telephone.py                │
│    + Skill & Doctrine de Family Officer Intégrés       │
└───────────────────────────┬────────────────────────────┘
                            │ Exécution native Android
                            │ (Modem Télécom & Termux:API)
┌───────────────────────────▼────────────────────────────┐
│             Requêtes USSD Wave & Système               │
│        *9113# (Solde) | *9113*1*...# (Transferts)      │
└────────────────────────────────────────────────────────┘
```

---

## 🏛️ Le Skill « Family Officer » Intégré

Wave Server MCP n'est pas un simple exécuteur aveugle : il implémente la **doctrine du Family Officer** (gestionnaire de patrimoine et protecteur financier personnel).

### Les 4 Piliers de Protection Financière :
1. **Sanctuaire d'Urgence Inviolable (25 000 FCFA)** : L'IA veille à préserver en permanence une réserve de sécurité minimale face aux imprévus de la vie.
2. **Arbitrage Préalable (`evaluer_impact_transfert_wave`)** : Avant tout transfert, le Family Officer calcule le solde résiduel, vérifie l'absence de risque pour les dépenses vitales et alerte l'utilisateur.
3. **Gestion Équilibrée de la Solidarité Familiale** : Aide l'utilisateur à soutenir ses proches (dépannages, tontines) sans fragiliser son propre équilibre financier.
4. **Bouclier Anti-Arnaque** : Vérifie l'authenticité des transactions par USSD infalsifiable et prévient les pièges de faux SMS Wave.

---

## 🛠️ Outils MCP Disponibles

| Nom de l'outil MCP | Description pour l'IA | Mécanisme USSD / Système |
|---|---|---|
| `consulter_solde_wave` | Consulte le solde Wave officiel en direct | Requête USSD `*9113#` ou dernier SMS certifié |
| `evaluer_impact_transfert_wave` | **Arbitrage Family Officer** : évalue l'impact du transfert sur la réserve d'urgence (25 000 FCFA) | Calcul budgétaire & modèle à 4 états |
| `transferer_argent_wave` | Envoie de l'argent Wave vers un numéro destinataire | Commande USSD `*9113*1*NUMERO*MONTANT*PIN#` |
| `lire_sms_wave` | Récupère et filtre les SMS de transaction reçus de Wave | Lecture directe des SMS Android (`termux-sms-list`) |
| `lire_notifications_wave` | Intercepte les notifications push actives de l'app Wave | Écouteur de notifications Android |
| `capturer_ecran_telephone` | Capture l'écran du smartphone en direct (PNG Base64) | Capture native Android (`screencap`) |
| `analyser_ui_telephone` | Inspecte l'arborescence UI des éléments Wave à l'écran | Dump d'accessibilité UI (`uiautomator dump`) |
| `lancer_application` | Ouvre l'application Wave (`com.wave.personal`) | Lanceur Intent Android |
| `statut_telephone` | Remonte l'état de la batterie, du Wi-Fi et de l'appareil | Sondes matérielles Termux |
| `reveiller_telephone` | Réveille l'écran et garde l'appareil actif | Wake-lock et keyevent Android |

---

## 📜 Prompts & Ressources MCP Intégrés

Le serveur MCP expose nativement les spécifications **Prompts** et **Resources** du Model Context Protocol :

- **Prompt MCP `family_officer_wave`** : Active instantanément la posture de protecteur financier dans votre client MCP.
- **Ressource `wave://family-officer/doctrine`** : Document de référence de la charte financière et des règles de gouvernance du Family Officer.
- **Agent Skill `skills/wave-family-officer/SKILL.md`** : Fichier SKILL.md autonome prêt pour Antigravity IDE, Cursor et Claude.

---

## ⚡ Exemples de Requêtes Utilisateur

- 💬 *« Quel est mon solde Wave actuel ? »*  
  ➔ L'IA appelle `consulter_solde_wave()`, interroge `*9113#` et répond :  
  *« Votre solde Wave certifié est de 48 500 FCFA. »*

- 💬 *« Envoie 10 000 FCFA au 0701020304 pour dépanner mon frère. »*  
  ➔ L'IA appelle `evaluer_impact_transfert_wave(10000, "0701020304")` et analyse :  
  *« ⚠️ Attention : après ce transfert de 10 000 FCFA (+ 100 FCFA de frais), votre solde ne sera plus que de 38 400 FCFA. Votre réserve d'urgence de 25 000 FCFA reste préservée. Confirmez-vous l'envoi vers le 0701020304 ? »*

---

## 🚀 Installation & Démarrage

### 1. Sur le smartphone Android (Termux)

1. Téléchargez et installez **[Termux](https://f-droid.org/fr/packages/com.termux/)** et **[Termux:API](https://f-droid.org/fr/packages/com.termux.api/)** depuis F-Droid.
2. Accordez les permissions à Termux:API (Appels / Téléphone, SMS, Notifications).
3. Exécutez dans Termux :

```bash
pkg update -y && pkg install -y git python termux-api
git clone https://github.com/issoufzousko-prog/wave-server-mcp.git
cd wave-server-mcp
chmod +x installer_mcp_termux.sh
./installer_mcp_termux.sh
```

Le serveur s'initialise et affiche son adresse IP (ex: `http://192.168.1.50:8765`).

---

## 💻 Configuration sur votre Ordinateur

### Claude Desktop (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "wave-family-officer": {
      "command": "python",
      "args": [
        "/chemin/absolu/vers/wave-server-mcp/pont_mcp_stdio_telephone.py"
      ],
      "env": {
        "IP_TELEPHONE": "192.168.1.50",
        "PORT_TELEPHONE": "8765",
        "WAVE_CODE_SECRET": "VOTRE_CODE_PIN"
      }
    }
  }
}
```

### Antigravity IDE / Cursor (`.agents/mcp_config.json`)

```json
{
  "mcpServers": {
    "wave-family-officer": {
      "command": "python",
      "args": [
        "c:/chemin/vers/wave-server-mcp/pont_mcp_stdio_telephone.py"
      ],
      "env": {
        "IP_TELEPHONE": "192.168.1.50",
        "PORT_TELEPHONE": "8765",
        "WAVE_CODE_SECRET": "VOTRE_CODE_PIN"
      }
    }
  }
}
```

---

## 🔒 Sécurité & Confidentialité

- **100 % Réseau Local** : Les communications s'effectuent exclusivement en Wi-Fi local sans aucun serveur tiers.
- **Zéro fuite de Code PIN** : Votre code secret Wave n'est stocké que dans votre fichier local `.env` et n'apparaît jamais en clair dans les logs ou échanges de l'IA.
- **Zéro dépendance externe sur Android** : Le serveur utilise uniquement la bibliothèque standard Python 3.

---

## 📄 Licence

Distribué sous licence [MIT](LICENSE).

---

<p align="center">
  <img src="assets/wave-server-mcp-logo.png" alt="Wave Server MCP Mascot" width="140"/>
</p>
