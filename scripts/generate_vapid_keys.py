"""Generate VAPID key pair for Web Push notifications.

Usage:
    python scripts/generate_vapid_keys.py

Then add the output to your .env or docker-compose.yml environment.
"""

import base64
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())

# Private key in PEM format (for pywebpush)
priv_pem = private_key.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption(),
).decode().strip()

# Public key as URL-safe base64 (for browser PushManager)
pub_raw = private_key.public_key().public_bytes(
    serialization.Encoding.X962,
    serialization.PublicFormat.UncompressedPoint,
)
pub_b64 = base64.urlsafe_b64encode(pub_raw).rstrip(b"=").decode()

print("Add these to your docker-compose.yml or .env file:\n")
print(f"VAPID_PUBLIC_KEY={pub_b64}")
print(f"VAPID_PRIVATE_KEY={priv_pem}")
