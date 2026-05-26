@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo  ==========================================
echo   ContaBot Demo — Distribuidora ABC S.A.S.
echo  ==========================================
echo.
echo  Iniciando servidor...
echo  Abriendo http://localhost:5000
echo.
start "" "http://localhost:5000"
python api/server.py
pause
