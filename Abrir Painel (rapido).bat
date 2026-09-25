@echo off
rem Duplo clique: abre o painel com os dados já gravados, sem baixar nada.
cd /d "%~dp0"
python abrir_painel.py --rapido
if errorlevel 1 pause
