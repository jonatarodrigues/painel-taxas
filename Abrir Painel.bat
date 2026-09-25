@echo off
rem Duplo clique: atualiza os dados e abre o painel no navegador.
rem Para abrir sem atualizar, use "Abrir Painel (rapido).bat".
cd /d "%~dp0"
python abrir_painel.py %*
if errorlevel 1 pause
