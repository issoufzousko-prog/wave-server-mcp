#!/data/data/com.termux/files/usr/bin/bash
# ==============================================================================
# Script d'installation & de lancement de Wave Server MCP
# Serveur MCP Android sans fil pour Wave Mobile Money
# ==============================================================================

set -e

echo "=========================================================="
echo " 🐧 WAVE SERVER MCP — INSTALLATION ANDROID (TERMUX)"
echo "=========================================================="

# 1. Vérification et installation des paquets requis
echo "[1/4] Installation des paquets requis (Python + Termux:API)..."
pkg update -y
pkg install -y python termux-api curl git

# 2. Configuration du stockage partagé
echo "[2/4] Vérification de l'accès au stockage..."
termux-setup-storage || true

# 3. Récupération ou mise à jour du script si non présent
if [ ! -f "serveur_mcp_telephone.py" ]; then
    echo "[3/4] Téléchargement de serveur_mcp_telephone.py depuis GitHub..."
    curl -sSL "https://raw.githubusercontent.com/issoufzousko-prog/wave-server-mcp/main/serveur_mcp_telephone.py" -o serveur_mcp_telephone.py
else
    echo "[3/4] Fichier serveur_mcp_telephone.py détecté localement [OK]"
fi

# 4. Paramétrage IP PC facultatif
IP_PC="${1:-}"

echo "[✓] Serveur MCP prêt !"

# 5. Démarrage du serveur
echo "[4/4] Démarrage du serveur sur le port 8765..."
if [ -n "$IP_PC" ]; then
    python serveur_mcp_telephone.py --port=8765 --pc="$IP_PC"
else
    python serveur_mcp_telephone.py --port=8765
fi
