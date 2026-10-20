#!/data/data/com.termux/files/usr/bin/bash
# ==============================================================================
# Script d'installation & de lancement de Wave Server MCP
# Serveur MCP Android sans fil pour Wave Mobile Money
# Compatible ChatGPT, Claude Desktop, Antigravity, Cursor
# ==============================================================================

set -e

echo "=========================================================="
echo " 🐧 WAVE SERVER MCP — INSTALLATION ANDROID (TERMUX)"
echo "=========================================================="

# 1. Paquets requis
echo "[1/4] Installation des paquets requis..."
pkg update -y
pkg install -y python termux-api curl git

# 2. Stockage partagé
echo "[2/4] Configuration du stockage partagé..."
termux-setup-storage || true

# 3. Récupération des fichiers si manquants
if [ ! -f "serveur_mcp_telephone.py" ]; then
    echo "[3/4] Téléchargement des scripts depuis GitHub..."
    curl -sSL "https://raw.githubusercontent.com/issoufzousko-prog/wave-server-mcp/main/serveur_mcp_telephone.py" -o serveur_mcp_telephone.py
    curl -sSL "https://raw.githubusercontent.com/issoufzousko-prog/wave-server-mcp/main/openapi.json" -o openapi.json
else
    echo "[3/4] Fichiers serveur_mcp_telephone.py et openapi.json prêts [OK]"
fi

# 4. Demander si activation tunnel public Cloudflare pour ChatGPT
echo ""
echo "----------------------------------------------------------"
echo " Voulez-vous activer le tunnel Cloudflare pour ChatGPT ? "
echo " (Permet à ChatGPT Cloud d'accéder au téléphone sans câble)"
echo "----------------------------------------------------------"
read -p "Activer Cloudflare Tunnel ? (o/n, défaut: o) : " REP_TUNNEL
REP_TUNNEL=${REP_TUNNEL:-o}

if [ "$REP_TUNNEL" = "o" ] || [ "$REP_TUNNEL" = "O" ]; then
    if ! command -v cloudflared &> /dev/null; then
        echo "[+] Installation de cloudflared..."
        pkg install -y cloudflared || true
    fi
    if command -v cloudflared &> /dev/null; then
        echo "[✓] Lancement de cloudflared tunnel en tâche de fond..."
        cloudflared tunnel --url http://localhost:8765 > tunnel.log 2>&1 &
        sleep 4
        URL_TUNNEL=$(grep -o 'https://[-a-zA-Z0-9.]*\.trycloudflare\.com' tunnel.log | head -n 1 || true)
        if [ -n "$URL_TUNNEL" ]; then
            echo ""
            echo "=========================================================="
            echo " 🌐 URL PUBLIQUE POUR CHATGPT & ACTIONS : $URL_TUNNEL"
            echo " 📄 URL Spécification OpenAPI : $URL_TUNNEL/openapi.json"
            echo "=========================================================="
            echo ""
        fi
    fi
fi

# 5. Démarrage du serveur
echo "[4/4] Démarrage du serveur Wave MCP sur le port 8765..."
python serveur_mcp_telephone.py --port=8765
