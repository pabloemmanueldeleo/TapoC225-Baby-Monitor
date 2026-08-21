@echo off
title Tapo C225 AI Baby Monitor
cd /d "%~dp0"
echo Iniciando Monitor de Bebe Tapo C225...
uv run main.py
if errorlevel 1 (
    echo.
    echo ----------------------------------------------------
    echo [ERROR] Hubo un problema al iniciar la aplicacion.
    echo Asegurate de tener 'uv' instalado y tu archivo .env configurado.
    echo ----------------------------------------------------
    pause
)
