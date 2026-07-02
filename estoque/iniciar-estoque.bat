@echo off
title Estoque - Botis da Eve
cd /d "%~dp0"
echo Iniciando o app Botis da Eve (site + estoque)...
echo O navegador vai abrir sozinho. Estoque fica no menu do site.
echo (Deixe esta janela aberta enquanto usa. Feche-a para encerrar.)
python app.py
pause
