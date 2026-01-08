#!/bin/bash
cd "$(dirname "$0")"
echo "Server: http://$(ipconfig getifaddr en0):8000"
python3 -m http.server 8000
