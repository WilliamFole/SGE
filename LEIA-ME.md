# Sistema de Controle de Estoque para Mercearia

Sistema completo de gestão de estoque desenvolvido conforme a documentação
fornecida (RF01–RF08, RNF01–RNF07, RN01–RN08), incluindo dashboard
gerencial, relatórios com exportação PDF/Excel, controle de acesso por
perfil e regras de negócio de estoque (conversão de unidades, custeio por
média ponderada, alertas de mínimo/validade, etc.).

Tecnologia: Python + Flask + SQLite (banco de dados embutido, sem precisar
instalar MySQL/PostgreSQL). A aplicação roda um servidor local e abre
automaticamente no navegador padrão — funciona como um programa desktop
comum, 100% offline.

---
## 1. Testar rapidamente (sem instalar nada, se já tiver Python)

```
pip install -r requirements.txt
python app.py
```

O navegador abre sozinho em `http://127.0.0.1:5701`.

**Login inicial:** `admin` / `admin123` — troque a senha em *Usuários* assim
que possível.

---
## 2. Gerar o instalador Windows (.exe clicável)

Como não tenho acesso à internet neste ambiente de desenvolvimento, não
consigo compilar o `.exe` aqui. O processo abaixo é rápido (~5 minutos) e
só precisa ser feito uma vez, num PC Windows com internet:

### Passo 1 — Instalar o Python (se ainda não tiver)
Baixe em https://www.python.org/downloads/ (marque a opção **"Add Python
to PATH"** durante a instalação).

### Passo 2 — Gerar o executável
1. Copie toda a pasta `estoque_app` para o PC Windows.
2. (Opcional) Se quiser um ícone personalizado, coloque o arquivo
   `sgosIcon.png` (ou já convertido, `sgosIcon.ico`) na sua pasta
   `Downloads`. O script detecta e converte automaticamente.
3. Dê duplo-clique em **`build_exe.bat`** (ou execute-o num terminal).
4. Aguarde — ele cria um ambiente virtual, instala as dependências,
   prepara o ícone e gera o executável em `dist\EstoqueMercearia.exe`.

Nesse ponto, `EstoqueMercearia.exe` já é um programa Windows funcional que
pode ser copiado e executado em qualquer PC Windows, sem precisar instalar
Python. Se só precisar disso (sem instalador), já está pronto.

### Passo 3 — Gerar o instalador clicável (Setup.exe)
1. Baixe e instale o **Inno Setup** (gratuito):
   https://jrsoftware.org/isdl.php
2. Abra o arquivo **`installer.iss`** com o Inno Setup.
3. Clique em **Build → Compile** (ou aperte F9 / Ctrl+F9).
4. O instalador final aparece em `installer_output\Setup_EstoqueMercearia.exe`.

Esse `Setup_EstoqueMercearia.exe` é o instalador clicável: ao rodar, cria
atalho no Menu Iniciar e (opcionalmente) na Área de Trabalho, e inclui
desinstalador automático. Pode ser distribuído/copiado para qualquer PC
Windows.

> **Nota:** o banco de dados (`dados\estoque.db`) é criado automaticamente
> na primeira execução, na mesma pasta onde o programa foi instalado. O
> script do instalador já concede permissão de escrita para utilizadores
> comuns, mesmo instalando em "Arquivos de Programas".

---
## 3. Estrutura do projeto

```
estoque_app/
├── app.py              # Rotas Flask e ponto de entrada
├── database.py         # Schema SQLite e conexão
├── services.py         # Regras de negócio (RN01–RN08)
├── reports.py          # Geração de PDF/Excel
├── templates/           # Telas (HTML/Jinja2)
├── static/css/style.css # Estilo visual
├── static/js/app.js     # Gráficos do dashboard (SVG, sem libs externas)
├── requirements.txt
├── build_exe.bat        # Gera o .exe (rodar no Windows)
├── installer.iss        # Script do Inno Setup (gera o Setup.exe)
└── LEIA-ME.md
```

---
## 4. Perfis de utilizador (RNF03)

| Perfil    | Permissões |
|-----------|------------|
| Admin     | Acesso total: produtos, categorias, usuários, configurações, exclusão física |
| Gerente   | Produtos (CRUD, sem exclusão física), entradas/saídas, relatórios, dashboard |
| Operador  | Entradas/saídas, consulta de estoque, dashboard (leitura), relatórios básicos |

Crie novos utilizadores em **Usuários** (menu lateral, apenas Admin).

---
## 5. Principais funcionalidades implementadas

- Cadastro de categorias e produtos, com unidade (Caixa/Embalagem/Unidade)
  e conversão automática para unidade avulsa em todas as entradas/saídas.
- Entradas (compras) e saídas (vendas), com custeio por média ponderada
  móvel (configurável) e bloqueio de estoque negativo.
- Dashboard com cards, gráficos de entradas/saídas, compras x vendas,
  lucro diário, produtos mais vendidos, alertas de estoque mínimo e
  validade, e sugestões automáticas de ajuste de preço.
- Relatórios (estoque atual, movimentações, vendas, estoque baixo,
  validade, lucratividade) com filtros, impressão e exportação para PDF
  e Excel.
- Inventário físico: compare a contagem manual com o saldo do sistema e
  registe as diferenças encontradas.
- Configurações gerais (nome da empresa, moeda, método de custeio, dias
  de alerta de validade, margem de lucro desejada, estoque mínimo padrão,
  permitir estoque negativo).
- Backup e restauração do banco de dados diretamente pela tela de
  Configurações (Admin).
- Troca de senha pelo próprio utilizador, com exigência de senha forte
  (mínimo 8 caracteres, letra, número e símbolo).
- Gestão de usuários com exclusão real (quando sem histórico) ou
  desativação automática (quando já possui movimentações).

---
## 6. Suporte

Qualquer ajuste (novos campos, regras adicionais, relatórios extra, etc.)
pode ser feito diretamente no código-fonte — a estrutura foi organizada
em módulos (`database.py`, `services.py`, `reports.py`, `app.py`) para
facilitar a manutenção, conforme RNF05.

Documentação completa
- A documentação completa do projeto foi adicionada à pasta `docs/`.
  Consulte [docs/index.md](/d:/ALL/SGE/docs/index.md) para o índice e
  os tópicos detalhados (instalação, utilização, API, arquitectura e
  desenvolvimento). Todos os ficheiros da pasta docs/ estão em Português (pt-PT).


