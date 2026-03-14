#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
# BOT-AUTO-TRADE-KRAKEN — Automated installer for Ubuntu 24.04
# ──────────────────────────────────────────────────────────────
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/<owner>/BOT-AUTO-TRADE-KRAKEN/main/scripts/install-ubuntu.sh | sudo bash
#   — or —
#   sudo bash scripts/install-ubuntu.sh
#
# What this script does:
#   1. Install system dependencies (Docker, Docker Compose, Node.js 20, git, certbot)
#   2. Clone the repo (or use existing checkout)
#   3. Interactive .env configuration
#   4. Build the React frontend
#   5. Optional: provision Let's Encrypt SSL certificate
#   6. Launch Docker Compose stack
# ──────────────────────────────────────────────────────────────

set -euo pipefail

# ── Colors ────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERR]${NC}   $*"; exit 1; }

# ── Pre-flight checks ────────────────────────────────────────
[[ $EUID -eq 0 ]] || error "Ce script doit etre lance en root (sudo)."

source /etc/os-release 2>/dev/null || true
if [[ "${VERSION_ID:-}" != "24.04" && "${VERSION_ID:-}" != "24.10" ]]; then
    warn "Ce script est prevu pour Ubuntu 24.04 LTS. Version detectee: ${VERSION_ID:-inconnue}"
    read -rp "Continuer quand meme ? (y/N) " ans
    [[ "$ans" =~ ^[yY]$ ]] || exit 0
fi

# ── Configuration variables ───────────────────────────────────
INSTALL_DIR="/opt/kraken-bot"
REPO_URL="https://github.com/eme-data/BOT-AUTO-TRADE-KRAKEN.git"

echo ""
echo -e "${BOLD}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║   BOT-AUTO-TRADE-KRAKEN — Installation Ubuntu    ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════════════╝${NC}"
echo ""

# ── Step 1: System packages ──────────────────────────────────
info "Mise a jour des paquets systeme..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get upgrade -y -qq

info "Installation des dependances systeme..."
apt-get install -y -qq \
    apt-transport-https \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    git \
    ufw \
    fail2ban \
    htop \
    jq \
    unzip \
    software-properties-common

success "Dependances systeme installees."

# ── Step 2: Docker ────────────────────────────────────────────
if command -v docker &>/dev/null; then
    success "Docker deja installe: $(docker --version)"
else
    info "Installation de Docker..."
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg

    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    systemctl enable --now docker
    success "Docker installe: $(docker --version)"
fi

# Docker Compose (plugin)
if docker compose version &>/dev/null; then
    success "Docker Compose: $(docker compose version --short)"
else
    error "Docker Compose plugin non trouve. Verifiez l'installation Docker."
fi

# ── Step 3: Node.js 20 (pour build frontend) ─────────────────
if command -v node &>/dev/null && [[ "$(node -v)" == v20* || "$(node -v)" == v22* ]]; then
    success "Node.js deja installe: $(node -v)"
else
    info "Installation de Node.js 20 LTS..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
    apt-get install -y -qq nodejs
    success "Node.js installe: $(node -v)"
fi

# ── Step 4: Clone / update repo ──────────────────────────────
if [[ -d "$INSTALL_DIR/.git" ]]; then
    info "Depot existant detecte dans $INSTALL_DIR"
    cd "$INSTALL_DIR"
    git pull --ff-only || warn "git pull echoue — utilisation de la version locale"
else
    # Check if we're already in the repo
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    PARENT_DIR="$(dirname "$SCRIPT_DIR")"

    if [[ -f "$PARENT_DIR/docker-compose.yml" && -f "$PARENT_DIR/bot/main.py" ]]; then
        info "Installation depuis le depot local: $PARENT_DIR"
        if [[ "$PARENT_DIR" != "$INSTALL_DIR" ]]; then
            cp -r "$PARENT_DIR" "$INSTALL_DIR"
        fi
    else
        info "Clonage du depot..."
        git clone "$REPO_URL" "$INSTALL_DIR"
    fi
    cd "$INSTALL_DIR"
fi

success "Code source pret dans $INSTALL_DIR"

# ── Step 5: Interactive .env setup ────────────────────────────
if [[ -f "$INSTALL_DIR/.env" ]]; then
    warn "Fichier .env existant detecte."
    read -rp "Voulez-vous le reconfigurer ? (y/N) " ans
    CONFIGURE_ENV=false
    [[ "$ans" =~ ^[yY]$ ]] && CONFIGURE_ENV=true
else
    CONFIGURE_ENV=true
fi

if $CONFIGURE_ENV; then
    info "Configuration du fichier .env..."
    cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"

    echo ""
    echo -e "${BOLD}--- Configuration de la base de donnees ---${NC}"

    read -rp "Mot de passe PostgreSQL [krakenbot_secret]: " DB_PASS
    DB_PASS="${DB_PASS:-krakenbot_secret}"

    echo ""
    echo -e "${BOLD}--- Configuration du Dashboard ---${NC}"

    read -rp "Mot de passe admin du dashboard [admin]: " ADMIN_PASS
    ADMIN_PASS="${ADMIN_PASS:-admin}"

    # Generate random JWT secret
    JWT_SECRET=$(openssl rand -hex 32)

    # Generate random encryption key
    ENCRYPTION_KEY=$(openssl rand -hex 32)

    echo ""
    echo -e "${BOLD}--- Configuration SSL (optionnel) ---${NC}"

    read -rp "Nom de domaine pour HTTPS (laisser vide pour HTTP uniquement): " DOMAIN
    read -rp "Email pour Let's Encrypt (requis si domaine renseigne): " SSL_EMAIL

    # Apply to .env
    sed -i "s|POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=${DB_PASS}|" "$INSTALL_DIR/.env"
    sed -i "s|DATABASE_URL=.*|DATABASE_URL=postgresql+asyncpg://kraken:${DB_PASS}@timescaledb:5432/krakenbot|" "$INSTALL_DIR/.env"
    sed -i "s|ADMIN_PASSWORD=.*|ADMIN_PASSWORD=${ADMIN_PASS}|" "$INSTALL_DIR/.env"
    sed -i "s|JWT_SECRET=.*|JWT_SECRET=${JWT_SECRET}|" "$INSTALL_DIR/.env"
    sed -i "s|ENCRYPTION_KEY=.*|ENCRYPTION_KEY=${ENCRYPTION_KEY}|" "$INSTALL_DIR/.env"

    if [[ -n "$DOMAIN" ]]; then
        sed -i "s|DOMAIN=.*|DOMAIN=${DOMAIN}|" "$INSTALL_DIR/.env"
        sed -i "s|SSL_EMAIL=.*|SSL_EMAIL=${SSL_EMAIL}|" "$INSTALL_DIR/.env"
    fi

    # Secure the .env file
    chmod 600 "$INSTALL_DIR/.env"
    success "Fichier .env configure."
fi

# ── Step 6: Build frontend ───────────────────────────────────
info "Build du frontend React..."
cd "$INSTALL_DIR/dashboard/frontend"

npm install --silent 2>/dev/null
npm run build 2>/dev/null

success "Frontend compile."
cd "$INSTALL_DIR"

# ── Step 7: Firewall ─────────────────────────────────────────
info "Configuration du firewall (ufw)..."
ufw --force reset >/dev/null 2>&1
ufw default deny incoming >/dev/null 2>&1
ufw default allow outgoing >/dev/null 2>&1
ufw allow ssh >/dev/null 2>&1
ufw allow 80/tcp >/dev/null 2>&1
ufw allow 443/tcp >/dev/null 2>&1
ufw allow 3000/tcp comment "Grafana" >/dev/null 2>&1
ufw --force enable >/dev/null 2>&1
success "Firewall configure (SSH, HTTP, HTTPS, Grafana)."

# ── Step 8: Create systemd service ───────────────────────────
info "Creation du service systemd..."
cat > /etc/systemd/system/kraken-bot.service <<UNIT
[Unit]
Description=Kraken Auto-Trade Bot (Docker Compose)
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$INSTALL_DIR
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=120

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable kraken-bot.service
success "Service systemd kraken-bot.service cree et active au demarrage."

# ── Step 9: SSL certificate (optional) ───────────────────────
DOMAIN=$(grep "^DOMAIN=" "$INSTALL_DIR/.env" 2>/dev/null | cut -d'=' -f2 || true)
SSL_EMAIL=$(grep "^SSL_EMAIL=" "$INSTALL_DIR/.env" 2>/dev/null | cut -d'=' -f2 || true)

if [[ -n "$DOMAIN" && "$DOMAIN" != "bot.example.com" && -n "$SSL_EMAIL" ]]; then
    info "Provisionnement du certificat SSL pour $DOMAIN..."

    # Start only nginx with HTTP config for ACME challenge
    docker compose up -d timescaledb redis dashboard
    sleep 3

    # Run certbot via init-ssl script
    if [[ -f "$INSTALL_DIR/scripts/init-ssl.sh" ]]; then
        chmod +x "$INSTALL_DIR/scripts/init-ssl.sh"
        bash "$INSTALL_DIR/scripts/init-ssl.sh"
        success "Certificat SSL provisionne pour $DOMAIN"
    else
        warn "Script init-ssl.sh non trouve. Configuration SSL manuelle requise."
    fi
else
    info "Pas de domaine configure — demarrage en HTTP uniquement."
fi

# ── Step 10: Launch stack ─────────────────────────────────────
info "Demarrage de la stack Docker Compose..."
cd "$INSTALL_DIR"
docker compose up -d --build

# Wait for services to be healthy
info "Attente du demarrage des services..."
sleep 10

# Check service status
echo ""
echo -e "${BOLD}--- Etat des services ---${NC}"
docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"

# ── Step 11: Create log rotation ──────────────────────────────
cat > /etc/logrotate.d/kraken-bot <<LOGROTATE
/opt/kraken-bot/logs/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 root root
}
LOGROTATE

# ── Done ──────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║         Installation terminee avec succes !       ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════════════╝${NC}"
echo ""

# Determine access URL
if [[ -n "$DOMAIN" && "$DOMAIN" != "bot.example.com" ]]; then
    URL="https://$DOMAIN"
else
    IP=$(curl -4 -s ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')
    URL="http://$IP"
fi

echo -e "${GREEN}Dashboard:${NC}       $URL"
echo -e "${GREEN}Grafana:${NC}         $URL:3000  (admin / admin)"
echo -e "${GREEN}API Docs:${NC}        $URL/api/docs"
echo ""
echo -e "${CYAN}Commandes utiles:${NC}"
echo "  cd $INSTALL_DIR"
echo "  docker compose logs -f bot        # Logs du bot"
echo "  docker compose logs -f dashboard  # Logs du dashboard"
echo "  docker compose ps                 # Etat des services"
echo "  docker compose restart bot        # Redemarrer le bot"
echo "  systemctl status kraken-bot       # Status du service"
echo ""
echo -e "${YELLOW}Prochaines etapes:${NC}"
echo "  1. Connectez-vous au dashboard avec le mot de passe admin"
echo "  2. Renseignez vos identifiants API Kraken (mode DEMO recommande)"
echo "  3. Configurez vos parametres de risque"
echo "  4. Activez l'autopilot ou ajoutez des paires manuellement"
echo ""
echo -e "${YELLOW}Securite:${NC}"
echo "  - Changez le mot de passe Grafana par defaut"
echo "  - Le fichier .env est en permissions 600 (root uniquement)"
echo "  - fail2ban est installe pour proteger SSH"
echo ""
