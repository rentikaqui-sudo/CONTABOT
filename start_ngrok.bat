@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo  ==========================================
echo   ContaBot Demo — URL Publica con ngrok
echo  ==========================================
echo.
echo  Iniciando servidor local...
start "ContaBot Servidor" python api/server.py
timeout /t 2 /nobreak >nul

echo  Generando URL publica...
echo  (Copie la URL https://XXXX.ngrok-free.app y enviela al contador)
echo.
python -c "
from pyngrok import ngrok
import time, webbrowser

tunnel = ngrok.connect(5000)
url = tunnel.public_url
print()
print('  ============================================')
print(f'  URL PUBLICA: {url}')
print(f'  Login:       {url}/login')
print('  ============================================')
print()
print('  Usuario   : contador')
print('  Contrasena: contabot2026')
print()
print('  Comparta esta URL por WhatsApp con el contador.')
print('  CTRL+C para cerrar.')
print()
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    ngrok.kill()
    print('  Sesion cerrada.')
"
pause
