"""Verifies the repository has every file/folder the Dockerfile copies. Run: python check_layout.py"""
import re, sys, os
need = ["Dockerfile", "render.yaml", "requirements.txt", "gridmind/core.py", "gridmind/store.py", "gridmind/__init__.py",
        "api/main.py", "frontend/package.json", "frontend/index.html", "frontend/src/App.tsx", "frontend/src/main.tsx",
        "tests/test_core.py", ".github/workflows/ci.yml"]
missing = [p for p in need if not os.path.exists(p)]
for line in open("Dockerfile"):
    m = re.match(r"COPY\s+(?!--from)(\S+)\s+\S+", line)
    if m and not os.path.exists(m.group(1).rstrip("/")): missing.append(f"{m.group(1)} (needed by Dockerfile)")
if missing:
    print("MISSING:", *sorted(set(missing)), sep="\n  "); sys.exit(1)
print("Layout OK: all files the Dockerfile needs are present.")
