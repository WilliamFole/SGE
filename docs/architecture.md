Arquitetura do Sistema

Componentes principais
- app.py      — aplicação Flask; define rotas, filtros Jinja2 e lógica de UI.
- services.py — regras de negócio: movimentos, cálculos, validações e utilitários.
- database.py — esquema SQLite (SCHEMA), inicialização (init_db) e helpers.
- reports.py  — geração de PDF/Excel (reportlab, openpyxl) com cabeçalho da empresa.
- templates/  — ficheiros HTML (Jinja2) usados pela UI.
- static/     — CSS, JS e imagens.

Base de dados (resumo das tabelas principais)
- usuarios: id_usuario, nome, login, senha_hash, perfil, ativo, email, telefone
- categorias: id_categoria, nome, descricao, ativo
- produtos: id_produto, codigo, nome, id_categoria, unidade, qtd_por_unidade,
  preco_custo, preco_venda, estoque_minimo, estoque_maximo, validade, ativo
- estoque: id_produto (PK), saldo_atual, ultima_atualizacao
- movimentos: id_movimento, tipo (Entrada/Saida), id_produto, data_hora,
  quantidade (unidade base), quantidade_original, unidade_original, preco_unitario,
  valor_total, id_usuario, lucro, fornecedor/cliente, observacoes
- inventarios: registos de contagens físicas
- cotacoes / itens_cotacao: gerir propostas de venda
- auditoria: histórico de alterações (INSERT/UPDATE/DELETE/LOGIN/LOGOUT)

Padrões e decisões
- SQLite local (dados/estoque.db) facilita distribuição offline e empacotamento.
- Conversão de unidades: a app converte para unidade base ao registar movimentos
  (função converter_para_unidade_base em services.py).
- Custeio: por defeito usa média ponderada (configurável em Configurações).
- Exportação: relatórios gerados server-side em PDF (reportlab) ou Excel (openpyxl).

Onde procurar código relevante
- Schema e inicialização: [database.py](/d:/ALL/SGE/database.py)
- Regras de negócio: [services.py](/d:/ALL/SGE/services.py)
- Rotas e UI: [app.py](/d:/ALL/SGE/app.py)
- Relatórios: [reports.py](/d:/ALL/SGE/reports.py)

