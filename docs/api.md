Referência de API (endpoints importantes)

Autenticação: a aplicação usa sessão Flask. As chamadas API esperam que o
utilizador esteja autenticado (login via UI). Abaixo estão endpoints
úteis para integração ou automação local.

GET /api/produtos/buscar?q=TERMO
- Descrição: procura produtos por nome ou código (máx. 15 resultados).
- Autenticação: sim (cookie de sessão)
- Resposta: JSON array de objetos com campos: id_produto, codigo, nome,
  unidade, qtd_por_unidade, preco_custo, preco_venda, fornecedor, saldo_atual

GET /api/produtos/codigo-provisorio
- Descrição: gera e reserva um código provisório para a sessão atual.
- Autenticação: sim
- Resposta: {"codigo": "PRD00001", "sessao_id": "..."}

POST /api/shutdown
- Descrição: encerra a aplicação (usado pelo botão "Sair e encerrar").
- Autenticação: sim (qualquer utilizador autenticado pode chamar, mas a UI
  oferece o botão apenas para Admin/Gerente)
- Resposta: {"ok": true}

Exportações por URL (GET com query string)
- /movimentos?exportar=pdf ou =excel
- /estoque?exportar=pdf ou =excel
- /relatorios/exportar/<formato>?tipo=movimentacoes  (formato = pdf|excel)

Notas de integração
- Como a app é pensada para uso local/desktop, a autenticação baseia-se em
  sessão/cookies. Para chamadas automáticas, primeiro autenticar via UI ou
  simular login para obter cookie de sessão.
- O endpoint /api/shutdown destina-se a encerrar o processo localmente —
  tomar cuidado em integrações automáticas.

Exemplo (curl) — procurar produtos (executar após login e obter cookie):

curl -b cookiefile "http://127.0.0.1:5701/api/produtos/buscar?q=arroz"

