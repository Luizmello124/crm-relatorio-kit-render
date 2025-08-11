#!/usr/bin/env bash
set -e

# Cria config do Streamlit (sem a linha de 'port')
mkdir -p ~/.streamlit
cat > ~/.streamlit/config.toml <<EOF
[server]
headless = true
address = "0.0.0.0"
enableCORS = false
enableXsrfProtection = false

[browser]
gatherUsageStats = false

[theme]
base = "light"
EOF

# Inicia na porta que o Render fornece
exec streamlit run app.py --server.port "$PORT" --server.address 0.0.0.0

