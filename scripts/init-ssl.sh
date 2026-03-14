#!/usr/bin/env bash
# ──────────────────────────────────────────────────────
# SSL Certificate Setup Script
# Run this ONCE on first deployment to get Let's Encrypt certs.
# ──────────────────────────────────────────────────────
set -euo pipefail

# Load env
if [ -f .env ]; then
    source .env
fi

DOMAIN="${DOMAIN:-bot.example.com}"
EMAIL="${CERT_EMAIL:-admin@example.com}"

echo "=== SSL Certificate Setup ==="
echo "Domain: $DOMAIN"
echo "Email:  $EMAIL"
echo ""

# Step 1: Start with HTTP-only nginx config
echo "[1/3] Starting services with HTTP-only config..."
cp nginx/nginx-init.conf nginx/nginx-active.conf
docker compose up -d timescaledb redis dashboard nginx

echo "[2/3] Requesting Let's Encrypt certificate..."
docker compose run --rm certbot certonly \
    --webroot \
    --webroot-path=/var/www/certbot \
    --email "$EMAIL" \
    --agree-tos \
    --no-eff-email \
    -d "$DOMAIN"

echo "[3/3] Switching to HTTPS config..."
# Replace domain placeholder in nginx.conf
sed "s/\${DOMAIN:-localhost}/$DOMAIN/g" nginx/nginx.conf > nginx/nginx-active.conf
docker compose restart nginx

echo ""
echo "=== SSL Setup Complete ==="
echo "Dashboard available at: https://$DOMAIN"
echo ""
echo "Certificates will auto-renew via the certbot container."
