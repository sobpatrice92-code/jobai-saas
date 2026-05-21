@echo off
title JobAI Local Runner
color 0A
echo.
echo  ================================================
echo    JobAI Local Runner - IP Residentielle
echo    LinkedIn sans blocage - Resultats sur Railway
echo  ================================================
echo.

cd /d "%~dp0"

python local_runner.py orchestrateur

echo.
echo  Appuyez sur une touche pour fermer...
pause > nul
