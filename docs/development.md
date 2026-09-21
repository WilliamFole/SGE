Desenvolvimento e Testes

Executar em ambiente local
1. Criar e ativar um venv (recomendado):
   python -m venv venv
   venv\Scripts\Activate.ps1  # PowerShell

2. Instalar dependências:
   pip install -r requirements.txt

3. Inicializar a BD (opcional):
   python -c "from database import init_db; init_db()"

4. Executar a aplicação:
   python app.py

Testes
- O repositório inclui testes unitários em tests/. Para correr os testes:

  python -m unittest discover -s tests -v

- Exemplo de comando para um ficheiro específico:
  python -m unittest tests.test_services.ServicesRoundingTests.test_round5_rounds_money_to_two_decimals

Linter / formatação
- Não há configuração específica de linter no repositório. Recomenda-se
  usar flake8 e black se desejar uniformizar o estilo:

  pip install black flake8
  black .
  flake8 .

Debugging
- Executar app.py em modo directo permite ver exceções no console. A app
  também imprime stacktraces em / (handler global) para facilitar debug
  local (ver app.py @app.errorhandler(Exception)).

Contribuir
- Criar uma branch por feature/bugfix e submeter pull request com descrição
  e testes quando aplicável.

