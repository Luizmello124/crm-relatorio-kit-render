#!/usr/bin/env bash
set -e

# Cria config do Streamlit
mkdir -p ~/.streamlit
cat > ~/.streamlit/config.toml << 'EOF'
[server]
headless = true
address = "0.0.0.0"
port = $PORT
enableCORS = false
enableXsrfProtection = false

[browser]
gatherUsageStats = false

[theme]
base = "light"
EOF

# Inicia o Streamlit na porta correta
streamlit run app.py --server.port=$PORT --server.address=0.0.0.0
