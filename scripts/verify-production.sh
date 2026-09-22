#!/usr/bin/env sh
set -eu
: "${RSS_CORE_URL:?Set RSS_CORE_URL}"
: "${RSS_CORE_API_TOKEN:?Set RSS_CORE_API_TOKEN}"
python3 scripts/production_verify.py
