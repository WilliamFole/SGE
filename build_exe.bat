@echo off
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