#!/usr/bin/env python3
"""
YTLoader - YouTube Downloader
Run with: python run.py
Then open http://localhost:5000
"""
import subprocess, sys, os

def check_deps():
    missing = []
    for pkg in ['flask','yt_dlp']:
        try: __import__(pkg)
        except ImportError: missing.append(pkg.replace('_','-'))
    if missing:
        print(f"Installing: {', '.join(missing)}")
        subprocess.check_call([sys.executable,'-m','pip','install']+missing)

if __name__ == '__main__':
    check_deps()
    os.chdir(os.path.dirname(__file__) or '.')
    from app import app
    print("\n" + "═"*50)
    print("  YTLoader - YouTube Downloader")
    print("  Open: http://localhost:5000")
    print("═"*50 + "\n")
    app.run(host='0.0.0.0', port=5000, threaded=True)
