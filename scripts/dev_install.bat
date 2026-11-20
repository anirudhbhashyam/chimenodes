@echo off
where py >nul 2>nul && (py -3 "%~dp0dev_install.py" %* & exit /b %ERRORLEVEL%)
python "%~dp0dev_install.py" %*
