#!/usr/bin/env bash
set -euo pipefail
python3 -c 'import json; d=json.load(open("config/projects.json")); assert d["projects"]; print("OK: project registry")'
