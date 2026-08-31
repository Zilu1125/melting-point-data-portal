@echo off
title Melting Point Experimental Data Portal
cd /d "%~dp0"

echo Starting Melting Point Experimental Data Portal...
echo.
echo Keep this window open while the portal is running.
echo Press Ctrl+C to stop the portal.
echo.

start "" cmd /c "timeout /t 2 /nobreak >nul & start http://localhost:8501"

python -m streamlit run portal_mvp.py --server.headless true

echo.
echo Portal stopped.
pause
