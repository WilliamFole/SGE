Guidelines de Docstrings e Exemplos (pt-PT)

Objetivo
Fornecer regras simples para escrever docstrings úteis e consistentes no
projeto SGE. As docstrings ajudam a documentação automática e a leitura
rápida do comportamento das funções.

Formato recomendado
- Padrão: triple-quoted string imediatamente após a definição do módulo,
  função, classe ou método.
- Idioma: Português (pt-PT) para documentação dirigida a utilizadores/administradores.

Estrutura (função)
1. Linha de resumo curta (imperativa).
2. Linha em branco.
3. Descrição mais detalhada (quando necessário).
4. Parâmetros (Args:), Valor de retorno (Returns:) e Excepções (Raises:).

Exemplo
def calcular_iva(valor, taxa=0.17):
    """Calcula o IVA aplicado a um valor.

    Args:
        valor (float): valor base sobre o qual calcular o IVA.
        taxa (float): percentagem de IVA (ex: 0.17 = 17%).

    Returns:
        float: montante do IVA arredondado a 2 casas decimais.

    Raises:
        TypeError: se 'valor' não for numérico.
    """

Pequenas regras
- Manter a primeira linha curta (<72 carateres).
- Usar frases completas e claras.
- Documentar efeitos laterais relevantes (ex: atualiza BD, altera ficheiros).

Ferramentas úteis
- Sphinx / pydoc para gerar documentação automática a partir das docstrings.
- flake8-docstrings para validar presença de docstrings em funções públicas.

