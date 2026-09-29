Instalação e Empacotamento

Requisitos
- Python 3.8+ (recomendado 3.10 ou 3.11)
- pip
- No Windows: Inno Setup (opcional, para gerar instalador .exe)

Instalação a partir do código-fonte
1. Criar e ativar um ambiente virtual (recomendado):
   python -m venv venv
   venv\Scripts\Activate.ps1   # PowerShell
   venv\Scripts\activate.bat    # CMD

2. Instalar dependências:
   pip install -r requirements.txt

3. Inicializar base de dados (opcional — é criada automaticamente na 1ª execução):
   python -c "from database import init_db; init_db()"

4. Executar a aplicação:
   python app.py

Construir um executável Windows (standalone)
-------------------------------------------
O repositório inclui um script para automatizar a geração do executável
no Windows: build_exe.bat. O processo instala dependências numa venv, usa
pyinstaller e gera um .exe em dist\EstoqueMercearia.exe.

Passos rápidos (num PC Windows):
1. Abrir um terminal na pasta do projeto.
2. Executar build_exe.bat (duplo-clique ou via terminal).
3. Encontrar o exe em dist\EstoqueMercearia.exe

Gerar instalador (Inno Setup)
-----------------------------
1. Instalar Inno Setup: https://jrsoftware.org/isdl.php
2. Abrir installer.iss no Inno Setup e compilar (F9).
3. O instalador (Setup_EstoqueMercearia.exe) será gerado em installer_output\

Notas sobre o banco de dados
- Ficheiro DB: dados\estoque.db (criado na primeira execução)
- Faça backups periódicos da pasta dados/ — o projeto inclui operações de
  backup/restauração na interface (Configurações).

Executar como aplicação «desktop» (sem instalar Python)
- Execute o ficheiro gerado em dist\EstoqueMercearia.exe ou use o
  instalador gerado pelo Inno Setup.

Problemas comuns
- Erros de dependências: assegurar Python na PATH e que o venv está ativo
- Permissões: ao instalar em "Arquivos de Programas", alguns ficheiros
  podem requerer permissões elevadas. O instalador procura lidar com isto.
