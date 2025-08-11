#!/usr/bin/env bash
set -e

# roda o streamlit sem usar config.toml
exec streamlit run app.py \
  --server.headless true \
  --server.address 0.0.0.0 \
  --server.port "$PORT" \
  --server.enableCORS false \
  --server.enableXsrfProtection false \
  --browser.gatherUsageStats false
