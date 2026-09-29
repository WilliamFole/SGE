# -*- coding: utf-8 -*-
"""Módulo services: regras de negócio e utilitários do SGE.

Este módulo agrupa funções reutilizáveis responsáveis por operações de
arredondamento, validações, geração e gestão de códigos de produto,
registro de entradas/saídas, cálculo de balancetes e relatórios, além de
mecanismos de segurança (tokens de recuperação, bloqueio de login) e
outras regras de negócio aplicadas pela aplicação.

As funções aqui são usadas por app.py e por outros módulos para garantir
coerência nas regras de negócio do sistema.
"""
import re
import secrets
import math
from datetime import datetime, timedelta
from database import get_conn, get_config, registrar_auditoria

class RegraNegocioError(Exception):
    pass

UNIDADES_VALIDAS = ("Caixa", "Embalagem", "Unidade")

# ---------------------------------------------------------------------------
# Utilitários de arredondamento (apenas para valores monetários)
# ---------------------------------------------------------------------------
def round5(valor, casas=2):
    """Arredonda valores numéricos para casas decimais e preserva inteiros."""
    if valor is None:
        return 0 if casas == 0 else 0.0
    try:
        valor_float = float(valor)
    except (TypeError, ValueError):
        return 0 if casas == 0 else 0.0

    valor_arredondado = round(valor_float + 1e-12, casas)
    if casas == 0:
        return int(valor_arredondado)
    if abs(valor_arredondado - round(valor_arredondado)) < 1e-9:
        return int(valor_arredondado)
    return valor_arredondado


def ceil5(valor, casas=5):
    """Arredonda valores numéricos por excesso para até N casas decimais."""
    if valor is None:
        return 0 if casas == 0 else 0.0
    try:
        valor_float = float(valor)
    except (TypeError, ValueError):
        return 0 if casas == 0 else 0.0

    if casas == 0:
        return int(math.ceil(valor_float - 1e-12))

    fator = 10 ** casas
    return math.ceil(valor_float * fator - 1e-12) / fator


def arredondar_moeda(valor):
    """Arredonda para 2 casas decimais (padrão monetário)."""
    return round5(valor, 2)


# ---------------------------------------------------------------------------
# Validações
# ---------------------------------------------------------------------------
def validar_senha(senha):
    if not senha or len(senha) < 8:
        return False
    if not re.search(r"[A-Za-z]", senha):
        return False
    if not re.search(r"\d", senha):
        return False
    if not re.search(r"[^A-Za-z0-9]", senha):
        return False
    return True


def validar_produto_cadastrado(conn, id_produto):
    if id_produto is None:
        return False
    try:
        id_produto = int(id_produto)
    except (TypeError, ValueError):
        return False
    row = conn.execute("SELECT 1 FROM produtos WHERE id_produto=? AND ativo=1", (id_produto,)).fetchone()
    return bool(row)


def produto_nome_existe(conn, nome, id_produto_excluir=None):
    nome_norm = (nome or "").strip().lower()
    if not nome_norm:
        return False
    sql = "SELECT id_produto FROM produtos WHERE ativo=1 AND LOWER(nome)=?"
    params = [nome_norm]
    if id_produto_excluir:
        sql += " AND id_produto!=?"
        params.append(id_produto_excluir)
    row = conn.execute(sql, params).fetchone()
    return bool(row)


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------
def registrar_tentativa_login(conn, login, sucesso, ip_address=None):
    conn.execute(
        "INSERT INTO login_attempts (login, ip_address, data_hora, sucesso) VALUES (?,?,?,?)",
        (login, ip_address, datetime.now().isoformat(timespec="seconds"), 1 if sucesso else 0),
    )
    conn.commit()


def login_bloqueado(conn, login):
    max_tent = int(get_config("max_tentativas_login", "5"))
    bloqueio_min = int(get_config("tempo_bloqueio_login_min", "5"))
    desde = (datetime.now() - timedelta(minutes=bloqueio_min)).isoformat(timespec="seconds")
    falhas = conn.execute(
        "SELECT COUNT(*) c FROM login_attempts WHERE login=? AND sucesso=0 AND data_hora >= ?",
        (login, desde),
    ).fetchone()["c"]
    ultimas_falhas = conn.execute(
        "SELECT data_hora FROM login_attempts WHERE login=? AND sucesso=0 ORDER BY data_hora DESC LIMIT ?",
        (login, max_tent),
    ).fetchall()
    if falhas >= max_tent and len(ultimas_falhas) >= max_tent:
        ultima = ultimas_falhas[-1]["data_hora"]
        try:
            dt = datetime.fromisoformat(ultima)
        except Exception:
            dt = datetime.now()
        libera = dt + timedelta(minutes=bloqueio_min)
        restante = (libera - datetime.now()).total_seconds()
        if restante > 0:
            return True, int(restante)
    return False, 0


def gerar_token_recuperacao(conn, login):
    user = conn.execute("SELECT * FROM usuarios WHERE login=? AND ativo=1", (login,)).fetchone()
    if not user:
        return None
    token = secrets.token_urlsafe(32)
    expira = (datetime.now() + timedelta(hours=1)).isoformat(timespec="seconds")
    conn.execute(
        "UPDATE usuarios SET token_recuperacao=?, token_expira=? WHERE id_usuario=?",
        (token, expira, user["id_usuario"]),
    )
    conn.commit()
    return token, user


def validar_token_recuperacao(conn, token):
    if not token:
        return None
    user = conn.execute("SELECT * FROM usuarios WHERE token_recuperacao=? AND ativo=1", (token,)).fetchone()
    if not user:
        return None
    if not user["token_expira"]:
        return None
    try:
        expira = datetime.fromisoformat(user["token_expira"])
    except Exception:
        return None
    if expira < datetime.now():
        return None
    return user


def consumir_token_recuperacao(conn, id_usuario):
    conn.execute(
        "UPDATE usuarios SET token_recuperacao=NULL, token_expira=NULL WHERE id_usuario=?",
        (id_usuario,),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Código de produto
# ---------------------------------------------------------------------------
def gerar_codigo_produto(conn):
    row = conn.execute("SELECT COUNT(*) AS c FROM produtos").fetchone()
    proximo = row["c"] + 1
    while True:
        codigo = f"PRD{proximo:05d}"
        existe = conn.execute("SELECT 1 FROM produtos WHERE codigo=?", (codigo,)).fetchone()
        existe_prov = conn.execute("SELECT 1 FROM codigos_provisorios WHERE codigo=? AND usado=0", (codigo,)).fetchone()
        if not existe and not existe_prov:
            return codigo
        proximo += 1


def reservar_codigo_provisorio(conn, sessao_id):
    row = conn.execute("SELECT COUNT(*) AS c FROM produtos").fetchone()
    proximo = row["c"] + 1
    tentativas = 0
    while tentativas < 1000:
        tentativas += 1
        codigo = f"PRD{proximo:05d}"
        existe = conn.execute("SELECT 1 FROM produtos WHERE codigo=?", (codigo,)).fetchone()
        existe_prov = conn.execute("SELECT 1 FROM codigos_provisorios WHERE codigo=? AND usado=0", (codigo,)).fetchone()
        if not existe and not existe_prov:
            conn.execute(
                "INSERT INTO codigos_provisorios (codigo, sessao_id, usado, data_criacao) VALUES (?,?,0,?)",
                (codigo, sessao_id, datetime.now().isoformat(timespec="seconds")),
            )
            conn.commit()
            return codigo
        proximo += 1
    return f"PRD{int(datetime.now().timestamp()):05d}"


def liberar_codigo_provisorio(conn, sessao_id, codigo=None):
    if codigo:
        conn.execute(
            "UPDATE codigos_provisorios SET usado=1 WHERE sessao_id=? AND codigo=?",
            (sessao_id, codigo),
        )
    else:
        conn.execute("UPDATE codigos_provisorios SET usado=1 WHERE sessao_id=? AND usado=0", (sessao_id,))
    conn.commit()


def usar_codigo_provisorio(conn, sessao_id, codigo):
    conn.execute(
        "UPDATE codigos_provisorios SET usado=1 WHERE sessao_id=? AND codigo=?",
        (sessao_id, codigo),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Conversão de unidades (agora retorna inteiro)
# ---------------------------------------------------------------------------
def converter_para_unidade_base(quantidade_original, qtd_por_unidade, unidade_original="Unidade"):
    """Converte para unidade base (avulsa) e retorna um inteiro."""
    if unidade_original == "Unidade":
        return int(quantidade_original) * 1
    else:
        return int(quantidade_original) * int(qtd_por_unidade)


def saldo_atual(conn, id_produto):
    row = conn.execute("SELECT saldo_atual FROM estoque WHERE id_produto=?", (id_produto,)).fetchone()
    return int(row["saldo_atual"]) if row else 0


def _garantir_linha_estoque(conn, id_produto):
    row = conn.execute("SELECT 1 FROM estoque WHERE id_produto=?", (id_produto,)).fetchone()
    if not row:
        conn.execute(
            "INSERT INTO estoque (id_produto, saldo_atual, ultima_atualizacao) VALUES (?,0,?)",
            (id_produto, datetime.now().isoformat(timespec="seconds")),
        )


# ---------------------------------------------------------------------------
# Atualização de produto → refletir no estoque
# ---------------------------------------------------------------------------
def atualizar_produto_refletir_estoque(conn, id_produto, dados_antigos, dados_novos):
    _garantir_linha_estoque(conn, id_produto)
    agora = datetime.now().isoformat(timespec="seconds")
    campos_alterados = {}

    old_qpu = int(dados_antigos.get("qtd_por_unidade") or 1)
    new_qpu = int(dados_novos.get("qtd_por_unidade") or 1)
    new_unidade = dados_novos.get("unidade", "Unidade")
    if new_unidade == "Unidade":
        new_qpu = 1

    if old_qpu != new_qpu:
        campos_alterados["qtd_por_unidade"] = (old_qpu, new_qpu)

    for campo in ["preco_custo", "preco_venda", "estoque_minimo", "estoque_maximo"]:
        old_v = dados_antigos.get(campo)
        new_v = dados_novos.get(campo)
        if old_v != new_v:
            campos_alterados[campo] = (old_v, new_v)

    if "preco_custo" in campos_alterados:
        conn.execute("UPDATE estoque SET ultima_atualizacao=? WHERE id_produto=?", (agora, id_produto))
    return campos_alterados


# ---------------------------------------------------------------------------
# Código de segurança para alteração de produto (com hash)
# ---------------------------------------------------------------------------
from werkzeug.security import generate_password_hash, check_password_hash

def validar_codigo_alteracao_produto(codigo_fornecido):
    codigo_cadastrado = get_config("codigo_alteracao_produto", "")
    if not codigo_cadastrado:
        return True
    return check_password_hash(codigo_cadastrado, codigo_fornecido)


# ---------------------------------------------------------------------------
# Registrar entrada (compra)
# ---------------------------------------------------------------------------
def registrar_entrada(conn, id_produto, quantidade_original, unidade_original,
                       preco_unitario, id_usuario, nota_fiscal=None,
                       fornecedor=None, observacoes=None, data_hora=None,
                       ip_address=None):
    if not validar_produto_cadastrado(conn, id_produto):
        raise RegraNegocioError("Selecione um produto cadastrado e ativo.")
    if unidade_original not in UNIDADES_VALIDAS:
        raise RegraNegocioError("Unidade inválida.")

    produto = conn.execute("SELECT * FROM produtos WHERE id_produto=?", (id_produto,)).fetchone()
    if not produto:
        raise RegraNegocioError("Produto não encontrado.")

    qtd_base = converter_para_unidade_base(quantidade_original, produto["qtd_por_unidade"], unidade_original)
    if qtd_base <= 0:
        raise RegraNegocioError("Quantidade de entrada deve ser maior que zero.")

    fator = int(produto["qtd_por_unidade"]) if unidade_original in ("Caixa", "Embalagem") else 1
    preco_unitario_base = preco_unitario / fator if fator else preco_unitario
    preco_unitario_base = arredondar_moeda(preco_unitario_base)

    _garantir_linha_estoque(conn, id_produto)
    saldo = saldo_atual(conn, id_produto)

    metodo = get_config("metodo_custeio", "media_ponderada")
    custo_atual = produto["preco_custo"] or 0
    if metodo == "media_ponderada" and (saldo + qtd_base) > 0:
        novo_custo = ((saldo * custo_atual) + (qtd_base * preco_unitario_base)) / (saldo + qtd_base)
    else:
        novo_custo = preco_unitario_base
    novo_custo = arredondar_moeda(novo_custo)

    valor_total = arredondar_moeda(qtd_base * preco_unitario_base)
    data_hora = data_hora or datetime.now().isoformat(timespec="seconds")

    cur = conn.execute(
        """INSERT INTO movimentos
           (tipo, id_produto, data_hora, quantidade, quantidade_original, unidade_original,
            preco_unitario, valor_total, id_usuario, nota_fiscal, fornecedor, observacoes, lucro)
           VALUES ('Entrada',?,?,?,?,?,?,?,?,?,?,?,0)""",
        (id_produto, data_hora, qtd_base, int(quantidade_original), unidade_original,
         preco_unitario_base, valor_total, id_usuario, nota_fiscal,
         fornecedor or produto["fornecedor"], observacoes),
    )
    movimento_id = cur.lastrowid

    conn.execute(
        "UPDATE estoque SET saldo_atual = saldo_atual + ?, ultima_atualizacao=? WHERE id_produto=?",
        (qtd_base, data_hora, id_produto),
    )
    conn.execute("UPDATE produtos SET preco_custo=? WHERE id_produto=?", (novo_custo, id_produto))

    registrar_auditoria(conn, id_usuario, "movimentos", movimento_id, "INSERT",
                        None, {"tipo": "Entrada", "id_produto": id_produto,
                               "quantidade": qtd_base, "valor_total": valor_total},
                        ip_address)
    conn.commit()
    return qtd_base


# ---------------------------------------------------------------------------
# Registrar saída (venda)
# ---------------------------------------------------------------------------
def registrar_saida(conn, id_produto, quantidade_original, unidade_original,
                     preco_unitario, id_usuario, cliente=None, forma_pagamento=None,
                     observacoes=None, data_hora=None, ip_address=None):
    if not validar_produto_cadastrado(conn, id_produto):
        raise RegraNegocioError("Selecione um produto cadastrado e ativo.")
    if unidade_original not in UNIDADES_VALIDAS:
        raise RegraNegocioError("Unidade inválida.")

    produto = conn.execute("SELECT * FROM produtos WHERE id_produto=?", (id_produto,)).fetchone()
    if not produto:
        raise RegraNegocioError("Produto não encontrado.")

    qtd_base = converter_para_unidade_base(quantidade_original, produto["qtd_por_unidade"], unidade_original)
    if qtd_base <= 0:
        raise RegraNegocioError("Quantidade de saída deve ser maior que zero.")

    fator = int(produto["qtd_por_unidade"]) if unidade_original in ("Caixa", "Embalagem") else 1
    preco_unitario_base = preco_unitario / fator if fator else preco_unitario
    preco_unitario_base = arredondar_moeda(preco_unitario_base)

    _garantir_linha_estoque(conn, id_produto)
    saldo = saldo_atual(conn, id_produto)

    permitir_negativo = get_config("permitir_estoque_negativo", "0") == "1"
    if not permitir_negativo and qtd_base > saldo + 1e-9:
        raise RegraNegocioError(f"Estoque insuficiente. Saldo atual: {saldo}, solicitado: {qtd_base}.")

    custo_medio = produto["preco_custo"] or 0
    lucro = arredondar_moeda((preco_unitario_base - custo_medio) * qtd_base)
    valor_total = arredondar_moeda(qtd_base * preco_unitario_base)
    data_hora = data_hora or datetime.now().isoformat(timespec="seconds")

    cur = conn.execute(
        """INSERT INTO movimentos
           (tipo, id_produto, data_hora, quantidade, quantidade_original, unidade_original,
            preco_unitario, valor_total, id_usuario, cliente, forma_pagamento, observacoes, lucro)
           VALUES ('Saida',?,?,?,?,?,?,?,?,?,?,?,?)""",
        (id_produto, data_hora, qtd_base, int(quantidade_original), unidade_original,
         preco_unitario_base, valor_total, id_usuario, cliente, forma_pagamento, observacoes, lucro),
    )
    movimento_id = cur.lastrowid

    conn.execute(
        "UPDATE estoque SET saldo_atual = saldo_atual - ?, ultima_atualizacao=? WHERE id_produto=?",
        (qtd_base, data_hora, id_produto),
    )

    registrar_auditoria(conn, id_usuario, "movimentos", movimento_id, "INSERT",
                        None, {"tipo": "Saida", "id_produto": id_produto,
                               "quantidade": qtd_base, "valor_total": valor_total,
                               "lucro": lucro},
                        ip_address)
    conn.commit()

    novo_saldo = saldo - qtd_base
    alerta_minimo = novo_saldo < produto["estoque_minimo"]
    return {"qtd_base": qtd_base, "novo_saldo": novo_saldo, "alerta_minimo": alerta_minimo}


# ---------------------------------------------------------------------------
# Situação do estoque
# ---------------------------------------------------------------------------
def situacao_estoque(saldo, minimo, maximo):
    if saldo < (minimo or 0):
        return "abaixo_minimo"
    if maximo and saldo > maximo:
        return "acima_maximo"
    return "normal"


# ---------------------------------------------------------------------------
# Alertas
# ---------------------------------------------------------------------------
def produtos_proximos_validade(conn):
    dias = int(get_config("dias_alerta_validade", "7"))
    limite = (datetime.now() + timedelta(days=dias)).date().isoformat()
    hoje = datetime.now().date().isoformat()
    rows = conn.execute(
        """SELECT p.*, e.saldo_atual FROM produtos p
           LEFT JOIN estoque e ON e.id_produto = p.id_produto
           WHERE p.ativo=1 AND p.validade IS NOT NULL AND p.validade != ''
             AND p.validade <= ? ORDER BY p.validade ASC""",
        (limite,),
    ).fetchall()
    resultado = []
    for r in rows:
        resultado.append({**dict(r), "vencido": r["validade"] < hoje})
    return resultado


def produtos_abaixo_minimo(conn):
    rows = conn.execute(
        """SELECT p.*, COALESCE(e.saldo_atual,0) AS saldo_atual FROM produtos p
           LEFT JOIN estoque e ON e.id_produto = p.id_produto
           WHERE p.ativo=1 AND COALESCE(e.saldo_atual,0) < p.estoque_minimo
           ORDER BY (p.estoque_minimo - COALESCE(e.saldo_atual,0)) DESC"""
    ).fetchall()
    return [dict(r) for r in rows]


def sugestoes_precos(conn, dias=30):
    desde = (datetime.now() - timedelta(days=dias)).isoformat(timespec="seconds")
    vendas = conn.execute(
        """SELECT id_produto, SUM(quantidade) AS total_vendido
           FROM movimentos WHERE tipo='Saida' AND data_hora >= ?
           GROUP BY id_produto""",
        (desde,),
    ).fetchall()
    if not vendas:
        return []
    medias = {v["id_produto"]: v["total_vendido"] for v in vendas}
    media_geral = sum(medias.values()) / len(medias)

    sugestoes = []
    for id_produto, total in medias.items():
        produto = conn.execute("SELECT * FROM produtos WHERE id_produto=?", (id_produto,)).fetchone()
        if not produto or not produto["ativo"]:
            continue
        if total > media_geral * 1.2:
            sugestoes.append({
                "produto": dict(produto), "total_vendido": total,
                "tipo": "aumento", "percentual": 5,
                "preco_sugerido": arredondar_moeda(produto["preco_venda"] * 1.05),
            })
        elif total < media_geral * 0.5:
            sugestoes.append({
                "produto": dict(produto), "total_vendido": total,
                "tipo": "reducao", "percentual": 10,
                "preco_sugerido": arredondar_moeda(produto["preco_venda"] * 0.90),
            })
    return sugestoes


# ---------------------------------------------------------------------------
# Balancetes (com todas as chaves exigidas)
# ---------------------------------------------------------------------------
def calcular_balancete(conn, periodo, data_inicio, data_fim, id_categoria=None, id_produto=None):
    dt_ini = data_inicio + " 00:00:00"
    dt_fim = data_fim + " 23:59:59"

    sql_prod = """SELECT p.*, c.nome AS categoria_nome
                  FROM produtos p LEFT JOIN categorias c ON c.id_categoria=p.id_categoria
                  WHERE p.ativo=1"""
    params = []
    if id_categoria:
        sql_prod += " AND p.id_categoria=?"
        params.append(id_categoria)
    if id_produto:
        sql_prod += " AND p.id_produto=?"
        params.append(id_produto)
    sql_prod += " ORDER BY p.nome"
    produtos = conn.execute(sql_prod, params).fetchall()

    linhas = []
    total_saldo_ini_qtd = 0
    total_entradas_qtd = 0
    total_saidas_qtd = 0
    total_saldo_fin_qtd = 0
    total_entradas_val = 0
    total_saidas_val = 0
    total_lucro = 0
    total_saldo_ini_valor_custo = 0
    total_saldo_ini_valor_venda = 0
    total_saldo_fin_valor_custo = 0

    for p in produtos:
        idp = p["id_produto"]

        saldo_ini = 0
        rows_antes = conn.execute(
            """SELECT COALESCE(SUM(CASE WHEN tipo='Entrada' THEN quantidade ELSE -quantidade END),0) s
               FROM movimentos WHERE id_produto=? AND data_hora < ?""",
            (idp, dt_ini),
        ).fetchone()
        saldo_ini = int(rows_antes["s"])

        ent_q = conn.execute(
            "SELECT COALESCE(SUM(quantidade),0) s, COALESCE(SUM(valor_total),0) v FROM movimentos WHERE id_produto=? AND tipo='Entrada' AND data_hora BETWEEN ? AND ?",
            (idp, dt_ini, dt_fim),
        ).fetchone()
        sai_q = conn.execute(
            "SELECT COALESCE(SUM(quantidade),0) s, COALESCE(SUM(valor_total),0) v, COALESCE(SUM(lucro),0) l FROM movimentos WHERE id_produto=? AND tipo='Saida' AND data_hora BETWEEN ? AND ?",
            (idp, dt_ini, dt_fim),
        ).fetchone()

        entradas_qtd = int(ent_q["s"])
        entradas_val = arredondar_moeda(ent_q["v"])
        saidas_qtd = int(sai_q["s"])
        saidas_val = arredondar_moeda(sai_q["v"])
        lucro = arredondar_moeda(sai_q["l"])
        saldo_fin = int(saldo_ini + entradas_qtd - saidas_qtd)

        # Nota: não existe um livro-razão de custo histórico por movimento,
        # por isso os valores de abertura/fecho usam o custo e preço de venda
        # ATUAIS do produto como melhor aproximação disponível.
        custo_atual = p["preco_custo"] or 0
        venda_atual = p["preco_venda"] or 0
        saldo_ini_valor_custo = arredondar_moeda(saldo_ini * custo_atual)
        saldo_ini_valor_venda = arredondar_moeda(saldo_ini * venda_atual)
        saldo_fin_valor_custo = arredondar_moeda(saldo_fin * custo_atual)

        total_saldo_ini_qtd += saldo_ini
        total_entradas_qtd += entradas_qtd
        total_saidas_qtd += saidas_qtd
        total_saldo_fin_qtd += saldo_fin
        total_entradas_val += entradas_val
        total_saidas_val += saidas_val
        total_lucro += lucro
        total_saldo_ini_valor_custo += saldo_ini_valor_custo
        total_saldo_ini_valor_venda += saldo_ini_valor_venda
        total_saldo_fin_valor_custo += saldo_fin_valor_custo

        linhas.append({
            "id_produto": idp,
            "codigo": p["codigo"],
            "produto": p["nome"],
            "categoria": p["categoria_nome"] or "—",
            "saldo_inicial": saldo_ini,
            "saldo_inicial_qtd": saldo_ini,
            "saldo_inicial_valor_custo": saldo_ini_valor_custo,
            "saldo_inicial_valor_venda": saldo_ini_valor_venda,
            "entradas_qtd": entradas_qtd,
            "entradas_val": entradas_val,
            "entradas_valor": entradas_val,
            "entradas_valor_venda": entradas_val,
            "saidas_qtd": saidas_qtd,
            "saidas_val": saidas_val,
            "saidas_valor": saidas_val,
            "saidas_valor_venda": saidas_val,
            "saldo_final": saldo_fin,
            "saldo_final_qtd": saldo_fin,
            "saldo_final_valor_custo": saldo_fin_valor_custo,
            "lucro": lucro,
            "debito": entradas_val,
            "credito": saidas_val,
            "nome_produto": p["nome"],
            "codigo_produto": p["codigo"],
        })

    totais = {
        "saldo_inicial": total_saldo_ini_qtd,
        "saldo_inicial_qtd": total_saldo_ini_qtd,
        "saldo_inicial_valor_custo": total_saldo_ini_valor_custo,
        "saldo_inicial_valor_venda": total_saldo_ini_valor_venda,
        "entradas_qtd": total_entradas_qtd,
        "entradas_val": total_entradas_val,
        "entradas_valor": total_entradas_val,
        "entradas_valor_venda": total_entradas_val,
        "saidas_qtd": total_saidas_qtd,
        "saidas_val": total_saidas_val,
        "saidas_valor": total_saidas_val,
        "saidas_valor_venda": total_saidas_val,
        "saldo_final": total_saldo_fin_qtd,
        "saldo_final_qtd": total_saldo_fin_qtd,
        "saldo_final_valor_custo": total_saldo_fin_valor_custo,
        "lucro": total_lucro,
    }
    return linhas, totais


def calcular_extrato_categoria(conn, id_categoria, data_inicio, data_fim):
    dt_ini = data_inicio + " 00:00:00"
    dt_fim = data_fim + " 23:59:59"

    movs = conn.execute(
        """SELECT m.*, p.nome AS produto_nome, p.codigo AS produto_codigo,
                  c.nome AS categoria_nome
           FROM movimentos m JOIN produtos p ON p.id_produto=m.id_produto
           LEFT JOIN categorias c ON c.id_categoria=p.id_categoria
           WHERE p.id_categoria=? AND m.data_hora BETWEEN ? AND ?
           ORDER BY m.data_hora ASC, m.id_movimento ASC""",
        (id_categoria, dt_ini, dt_fim),
    ).fetchall()

    linhas = []
    saldo = 0
    entradas_acum = 0
    saidas_acum = 0
    for m in movs:
        sinal = 1 if m["tipo"] == "Entrada" else -1
        qtd = m["quantidade"]
        saldo += sinal * qtd
        if m["tipo"] == "Entrada":
            entradas_acum += m["valor_total"]
        else:
            saidas_acum += m["valor_total"]
        linhas.append({
            "data_hora": m["data_hora"],
            "tipo": m["tipo"],
            "codigo": m["produto_codigo"],
            "produto": m["produto_nome"],
            "quantidade": qtd,
            "unidade": m["unidade_original"],
            "preco_unitario": arredondar_moeda(m["preco_unitario"]),
            "valor_total": arredondar_moeda(m["valor_total"]),
            "saldo_acumulado": saldo,
            "entradas_acum_valor": arredondar_moeda(entradas_acum),
            "saidas_acum_valor": arredondar_moeda(saidas_acum),
        })
    return linhas, saldo, entradas_acum, saidas_acum


# ---------------------------------------------------------------------------
# Cotações
# ---------------------------------------------------------------------------
def gerar_numero_cotacao(conn):
    """Gera número sequencial para cotação (ex: COT-0001)."""
    row = conn.execute("SELECT COUNT(*) AS c FROM cotacoes").fetchone()
    prox = row["c"] + 1
    return f"COT-{prox:04d}"


def criar_cotacao(conn, id_usuario, cliente_nome, cliente_email=None, cliente_telefone=None,
                  data_validade=None, observacoes=None, itens=None):
    """
    itens: lista de dicionários com id_produto, quantidade, preco_unitario, desconto_percentual
    """
    if not itens:
        raise RegraNegocioError("A cotação deve ter pelo menos um item.")

    numero = gerar_numero_cotacao(conn)
    data_emissao = datetime.now().isoformat(timespec="seconds")
    if not data_validade:
        data_validade = (datetime.now() + timedelta(days=30)).isoformat(timespec="seconds")

    valor_total = 0
    for item in itens:
        qtd = int(item["quantidade"])
        preco = arredondar_moeda(item["preco_unitario"])
        desconto = float(item.get("desconto_percentual", 0))
        subtotal = qtd * preco * (1 - desconto/100)
        valor_total += arredondar_moeda(subtotal)

    cur = conn.execute(
        """INSERT INTO cotacoes
           (numero, id_cliente, nome_cliente, email_cliente, telefone_cliente,
            data_emissao, data_validade, observacoes, status, valor_total, id_usuario)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (numero, None, cliente_nome, cliente_email, cliente_telefone,
         data_emissao, data_validade, observacoes, "Aberta", valor_total, id_usuario)
    )
    id_cotacao = cur.lastrowid

    for item in itens:
        qtd = int(item["quantidade"])
        preco = arredondar_moeda(item["preco_unitario"])
        desconto = float(item.get("desconto_percentual", 0))
        subtotal = qtd * preco * (1 - desconto/100)
        conn.execute(
            """INSERT INTO itens_cotacao
               (id_cotacao, id_produto, quantidade, preco_unitario, desconto_percentual, valor_total)
               VALUES (?,?,?,?,?,?)""",
            (id_cotacao, item["id_produto"], qtd, preco, desconto, arredondar_moeda(subtotal))
        )

    conn.commit()
    registrar_auditoria(conn, id_usuario, "cotacoes", id_cotacao, "INSERT", None,
                        {"numero": numero, "cliente": cliente_nome, "valor_total": valor_total},
                        None)
    return id_cotacao


def obter_cotacao(conn, id_cotacao):
    cotacao = conn.execute("SELECT * FROM cotacoes WHERE id_cotacao=?", (id_cotacao,)).fetchone()
    if not cotacao:
        return None
    itens = conn.execute(
        """SELECT i.*, p.codigo, p.nome AS produto_nome
           FROM itens_cotacao i JOIN produtos p ON p.id_produto=i.id_produto
           WHERE i.id_cotacao=?""",
        (id_cotacao,)
    ).fetchall()
    return dict(cotacao), [dict(item) for item in itens]


def atualizar_status_cotacao(conn, id_cotacao, novo_status, id_usuario):
    cotacao = conn.execute("SELECT * FROM cotacoes WHERE id_cotacao=?", (id_cotacao,)).fetchone()
    if not cotacao:
        raise RegraNegocioError("Cotação não encontrada.")
    if cotacao["status"] in ("Aprovada", "Rejeitada"):
        raise RegraNegocioError("Cotação já está finalizada.")
    conn.execute("UPDATE cotacoes SET status=? WHERE id_cotacao=?", (novo_status, id_cotacao))
    registrar_auditoria(conn, id_usuario, "cotacoes", id_cotacao, "UPDATE",
                        {"status": cotacao["status"]}, {"status": novo_status}, None)
    conn.commit()


def converter_cotacao_em_venda(conn, id_cotacao, id_usuario):
    """Converte uma cotação aprovada em movimento de saída (venda)."""
    cotacao, itens = obter_cotacao(conn, id_cotacao)
    if not cotacao:
        raise RegraNegocioError("Cotação não encontrada.")
    if cotacao["status"] != "Aprovada":
        raise RegraNegocioError("Apenas cotações aprovadas podem ser convertidas em venda.")

    # Para cada item, registra uma saída
    for item in itens:
        registrar_saida(
            conn,
            id_produto=item["id_produto"],
            quantidade_original=item["quantidade"],
            unidade_original="Unidade",  # ou usar a unidade do produto
            preco_unitario=item["preco_unitario"],
            id_usuario=id_usuario,
            cliente=cotacao["nome_cliente"],
            observacoes=f"Venda gerada da cotação {cotacao['numero']}",
            ip_address=None
        )

    atualizar_status_cotacao(conn, id_cotacao, "Convertida", id_usuario)