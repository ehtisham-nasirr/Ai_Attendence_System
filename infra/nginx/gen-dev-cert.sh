#!/bin/sh
# Self-signed certificate for dev/staging only. Production uses the organisation's CA (docs/runbook.md).
set -eu
dir="$(dirname "$0")/certs"
name="${1:-facetrack.example.local}"
openssl req -x509 -newkey rsa:3072 -sha256 -days 365 -nodes \
  -keyout "$dir/privkey.pem" -out "$dir/fullchain.pem" \
  -subj "/CN=$name" -addext "subjectAltName=DNS:$name,DNS:localhost,IP:127.0.0.1"
chmod 600 "$dir/privkey.pem"
echo "wrote $dir/fullchain.pem and $dir/privkey.pem for $name"
