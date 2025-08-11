#!/usr/bin/env bash
set -e

# Cria config do Streamlit em runtime
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

# Sobe o app
streamlit run app.py
