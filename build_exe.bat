@echo off
<<<<<<< HEAD
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
=======
REM ============================================================
REM  Script de build do SGE — Sistema de Gestão de Estoque
REM  Gera SGE.exe usando PyInstaller (compatível com todas as versões)
REM ============================================================

echo.
echo ============================================================
echo   SGE — Sistema de Gestao de Estoque
echo   Build: empacotar SGE.exe (PyInstaller)
echo ============================================================

echo.
echo === 1/6 Criando ambiente virtual (venv) ===
python -m venv venv
call venv\Scripts\activate.bat

echo.
echo === 2/6 Instalando dependencias ===
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install --upgrade pyinstaller

echo.
echo === 3/6 Limpando builds anteriores ===
if exist "dist" rmdir /s /q "dist"
if exist "build" rmdir /s /q "build"

echo.
echo === 4/6 Preparando icone (PNG -^> ICO) ===
if exist "static\img\iconsetup.ico" (
  echo Usando icone ja existente em static\img\iconsetup.ico
) else if exist "%USERPROFILE%\Downloads\sge.ico" (
  copy /Y "%USERPROFILE%\Downloads\sge.ico" "static\img\iconsetup.ico" >nul
  echo Icone copiado de Downloads\sge.ico
) else (
  echo AVISO: nao encontrei nenhum icone. O executavel sera gerado sem icone personalizado.
)

echo.
echo === 5/6 Compilando executavel com PyInstaller ===
if exist "SGE.spec" (
  echo Usando arquivo SGE.spec...
  python -m PyInstaller --noconfirm SGE.spec
) else (
  echo Usando parametros otimizados para maxima compatibilidade...
  python -m PyInstaller --noconfirm --onedir --windowed ^
    --name "SGE" ^
    --icon "static\img\iconsetup.ico" ^
    --add-data "templates;templates" ^
    --add-data "static;static" ^
    --add-data "dados;dados" ^
    --hidden-import "PIL._imaging" ^
    --hidden-import "PIL._imagingcms" ^
    --hidden-import "PIL._imagingmath" ^
    --hidden-import "openpyxl" ^
    --hidden-import "reportlab" ^
    --hidden-import "reportlab.pdfbase" ^
    --hidden-import "reportlab.pdfgen" ^
    --hidden-import "reportlab.platypus" ^
    --hidden-import "reportlab.lib" ^
    --hidden-import "reportlab.graphics" ^
    --collect-all "PIL" ^
    --collect-all "openpyxl" ^
    --collect-all "reportlab" ^
    --noupx ^
    app.py
)

echo.
echo === 6/6 Concluido! ===
echo O executavel foi gerado em: dist\SGE.exe
echo.
echo IMPORTANTE: Se ainda ocorrer erro de DLL, certifique-se de que o
echo Visual C++ Redistributable (2015-2022) esta instalado no sistema.
echo Descarregue de: https://aka.ms/vs/17/release/vc_redist.x64.exe
echo.
echo Proximo passo: abra o Inno Setup, carregue o arquivo installer.iss
echo e clique em "Compile" para gerar o instalador SGE.Setup.exe final.
echo O instalador sera gravado na pasta installer_output\ .
pause
>>>>>>> 64ec9886f1e598d60850f545ee865d1da75d06e9
