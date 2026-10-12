@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
title SGE — Build do Executável

REM ============================================================================
REM SGE — Script de build (Windows)
REM Gera um executável .exe com PyInstaller e prepara a pasta para o Inno Setup
REM ============================================================================

cd /d "%~dp0"

echo.
echo ============================================================
echo   SGE — SERIES  ^|  BUILD
echo ============================================================
echo.

REM ---------------------------------------------------------------------------
REM 1. Verificar Python
REM ---------------------------------------------------------------------------
where python >nul 2>nul
if errorlevel 1 (
    echo [ERRO] Python nao encontrado no PATH.
    echo        Instale o Python 3.10+ e adicione ao PATH.
    pause
    exit /b 1
)

python --version
echo.

REM ---------------------------------------------------------------------------
REM 2. Verificar / criar ambiente virtual
REM ---------------------------------------------------------------------------
if not exist ".venv\Scripts\python.exe" (
    echo [INFO] Ambiente virtual .venv nao encontrado. A criar...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERRO] Falha ao criar o ambiente virtual.
        pause
        exit /b 1
    )
)

set "PYTHON=.venv\Scripts\python.exe"
set "PIP=.venv\Scripts\pip.exe"

echo [INFO] A usar Python: %PYTHON%
echo.

REM ---------------------------------------------------------------------------
REM 3. Atualizar pip e instalar dependencias
REM ---------------------------------------------------------------------------
echo [INFO] A atualizar pip...
"%PYTHON%" -m pip install --upgrade pip >nul

echo [INFO] A instalar dependencias do requirements.txt...
if exist "requirements.txt" (
    "%PYTHON%" -m pip install -r requirements.txt
) else (
    echo [AVISO] requirements.txt nao encontrado. A instalar dependencias basicas...
)
if errorlevel 1 (
    echo [ERRO] Falha ao instalar dependencias.
    pause
    exit /b 1
)
echo.

REM ---------------------------------------------------------------------------
REM 4. Garantir PyInstaller instalado
REM ---------------------------------------------------------------------------
"%PYTHON%" -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo [INFO] PyInstaller nao encontrado. A instalar...
    "%PYTHON%" -m pip install pyinstaller
    if errorlevel 1 (
        echo [ERRO] Falha ao instalar PyInstaller.
        pause
        exit /b 1
    )
)

REM ---------------------------------------------------------------------------
REM 5. Limpar builds anteriores
REM ---------------------------------------------------------------------------
echo [INFO] A limpar pastas build/ e dist/ ...
if exist "build" rd /s /q "build"
if exist "dist"  rd /s /q "dist"
if exist "SGE.spec" del /q "SGE.spec"
echo.

REM ---------------------------------------------------------------------------
REM 6. Criar icone padrao (se nao existir)
REM ---------------------------------------------------------------------------
if not exist "static\img\app.ico" (
    echo [AVISO] static\img\icone.ico nao encontrado. O executavel usara o icone padrao.
    set "ICONE="
) else (
    set "ICONE=--icon=static\img\favicon.ico"
)

REM ---------------------------------------------------------------------------
REM 7. Correr PyInstaller
REM ---------------------------------------------------------------------------
echo [INFO] A compilar com PyInstaller...
echo.

"%PYTHON%" -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --name "SGE" ^
    --windowed ^
    --onedir ^
    %ICONE% ^
    --add-data "templates;templates" ^
    --add-data "static;static" ^
    --hidden-import "flask" ^
    --hidden-import "werkzeug" ^
    --hidden-import "werkzeug.security" ^
    --hidden-import "werkzeug.utils" ^
    --hidden-import "jinja2" ^
    --hidden-import "jinja2.ext" ^
    --hidden-import "openpyxl" ^
    --hidden-import "openpyxl.styles" ^
    --hidden-import "openpyxl.drawing.image" ^
    --hidden-import "reportlab" ^
    --hidden-import "reportlab.lib" ^
    --hidden-import "reportlab.lib.pagesizes" ^
    --hidden-import "reportlab.platypus" ^
    --hidden-import "reportlab.lib.styles" ^
    --hidden-import "reportlab.lib.enums" ^
    --hidden-import "reportlab.pdfbase" ^
    --hidden-import "reportlab.pdfbase.ttfonts" ^
    --hidden-import "reportlab.pdfbase.pdfmetrics" ^
    --hidden-import "PIL" ^
    --hidden-import "PIL._imaging" ^
    --hidden-import "sqlite3" ^
    --hidden-import "secrets" ^
    --hidden-import "uuid" ^
    --collect-all "reportlab" ^
    --collect-all "openpyxl" ^
    --collect-submodules "werkzeug" ^
    --collect-submodules "jinja2" ^
    app.py

if errorlevel 1 (
    echo.
    echo [ERRO] Falha ao compilar com PyInstaller.
    pause
    exit /b 1
)

echo.
echo [INFO] Compilacao concluida com sucesso.
echo.

REM ---------------------------------------------------------------------------
REM 8. Copiar dados iniciais (se existirem) para a pasta dist
REM ---------------------------------------------------------------------------
if exist "dados" (
    if not exist "dist\SGE\dados"   mkdir "dist\SGE\dados"
    if not exist "dist\SGE\backups" mkdir "dist\SGE\backups"
)

if exist "backups" (
    if not exist "dist\SGE\backups" mkdir "dist\SGE\backups"
    echo [INFO] Pasta 'backups' criada em dist\SGE\backups
)

REM ---------------------------------------------------------------------------
REM 9. Copiar README / LEIA-ME (se existirem)
REM ---------------------------------------------------------------------------
if exist "README.md"      copy /Y "README.md"      "dist\SGE\README.md" >nul
if exist "LEIA-ME.txt"    copy /Y "LEIA-ME.txt"    "dist\SGE\LEIA-ME.txt" >nul

REM ---------------------------------------------------------------------------
REM 10. Verificar se o Inno Setup esta instalado
REM ---------------------------------------------------------------------------
set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe"     set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"

if defined ISCC (
    echo.
    echo ============================================================
    echo   A criar instalador com Inno Setup...
    echo ============================================================
    "%ISCC%" installer.iss
    if errorlevel 1 (
        echo [AVISO] Falha ao criar o instalador. Verifique o installer.iss
    ) else (
        echo [INFO] Instalador criado com sucesso na pasta 'instalador\'
    )
) else (
    echo.
    echo [AVISO] Inno Setup 6 nao encontrado.
    echo         Instale de: https://jrsoftware.org/isdl.php
    echo         Depois, execute manualmente: installer.iss
)

REM ---------------------------------------------------------------------------
REM Fim
REM ---------------------------------------------------------------------------
echo.
echo ============================================================
echo   BUILD CONCLUIDO
echo ============================================================
echo.
echo   Executavel:  dist\SGE\SGE.exe
if exist "instalador" (
    echo   Instalador:  instalador\
)
echo.
pause
endlocal