Guia de Utilização

Visão geral das secções principais da interface:

- Dashboard: visão geral com cards de valor (custo, venda, lucro), gráficos
  de entradas/saídas por período, produtos mais vendidos e alertas.

- Produtos: listar, filtrar, criar e editar produtos. Ao criar, o sistema
  gera um código provisório que é reservado durante a edição. Campos
  importantes: código, nome, categoria, unidade (Caixa/Embalagem/Unidade),
  preço de custo, preço de venda, estoque mínimo.

- Categorias: gerir categorias de produto (CRUD). Se uma categoria estiver
  em uso por produtos, é feita desativação lógica em vez de eliminação física.

- Movimentos: registrar Entradas (compras) e Saídas (vendas). Permite
  anexar nota fiscal, fornecedor/cliente, forma de pagamento e observações.
  Saídas verificam o saldo (a menos que "permitir_estoque_negativo" esteja ativo).

- Estoque: visualizar saldos atuais, exportar relatório PDF/Excel, filtrar
  por categoria e situação (abaixo mínimo / acima do máximo / normal).

- Inventário físico: interface para registar contagens manuais e exportar
  relatório de inventário; detecta diferenças e armazena histórico.

- Cotações: criar cotações, aprovar/rejeitar e converter cotações aprovadas
  em vendas (movimentos de saída).

- Relatórios: múltiplos relatórios configuráveis (movimentações, vendas,
  preços, validade, lucratividade, balancetes). Exportação em PDF e Excel.

- Utilizadores e Configurações: gerir perfis, permissões e opções do
  sistema (nome da empresa, moeda, método de custeio, alertas, backup).

Dicas rápidas
- Utilizar senhas fortes (a app exige mínimo 8 carateres, letra, número e símbolo).
- Para editar um produto com segurança, o administrador pode exigir um
  "código de alteração" (configuração) para prevenir alterações acidentais.
- Fazer backups antes de alterações em massa (Configurações → Backup).

Atalhos de exportação
- Em páginas de listagem existem parâmetros URL para exportar. Exemplo:
  /movimentos?exportar=pdf  → descarrega PDF com o filtro corrente.

Problemas de marcação/validação
- Produtos com unidade "Unidade" exigem quantidades inteiras nas saídas
  e inventário (validação imposta pelo servidor).

Credenciais iniciais
- admin / admin123  (trocar assim que possível)
