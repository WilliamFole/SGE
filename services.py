# -*- coding: utf-8 -*-
<<<<<<< HEAD
"""Módulo services: regras de negócio e utilitários do SGE."""
=======
"""Módulo services: regras de negócio e utilitários do SGE.

Este módulo agrupa funções reutilizáveis responsáveis por operações de
arredondamento, validações, geração e gestão de códigos de produto,
registro de entradas/saídas, cálculo de balancetes e relatórios, além de
mecanismos de segurança (tokens de recuperação, bloqueio de login) e
outras regras de negócio aplicadas pela aplicação.

As funções aqui são usadas por app.py e por outros módulos para garantir
coerência nas regras de negócio do sistema.
"""
>>>>>>> 64ec9886f1e598d60850f545ee865d1da75d06e9
import re
import secrets
import math
from datetime import datetime, timedelta
from database import get_conn, get_config, registrar_auditoria
<<<<<<< HEAD
from werkzeug.security import generate_password_hash, check_password_hash
=======
>>>>>>> 64ec9886f1e598d60850f545ee865d1da75d06e9

class RegraNegocioError(Exception):
    pass

<<<<<<< HEAD
UNIDADES_VALIDAS = ("Caixa", "Embalagem", "Unidade", "kg")
UNIDADES_DECIMAIS = ("kg",)


# ---------------------------------------------------------------------------
# Utilitários de arredondamento
# ---------------------------------------------------------------------------
def round5(valor, casas=2):
    try:
        casas = int(casas)
    except (TypeError, ValueError):
        casas = 2
    if valor is None:
        return 0.0 if casas > 0 else 0
    try:
        valor_float = float(valor)
    except (TypeError, ValueError):
        return 0.0 if casas > 0 else 0
    if not math.isfinite(valor_float):
        return 0.0 if casas > 0 else 0
    if casas <= 0:
        return int(round(valor_float + 1e-12))
    return round(valor_float + 1e-12, casas)


def ceil5(valor, casas=5):
    try:
        casas = int(casas)
    except (TypeError, ValueError):
        casas = 5
    if valor is None:
        return 0.0
    try:
        valor_float = float(valor)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(valor_float):
        return 0.0
    if casas <= 0:
        return int(math.ceil(valor_float - 1e-12))
=======
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

>>>>>>> 64ec9886f1e598d60850f545ee865d1da75d06e9
    fator = 10 ** casas
    return math.ceil(valor_float * fator - 1e-12) / fator


def arredondar_moeda(valor):
<<<<<<< HEAD
=======
    """Arredonda para 2 casas decimais (padrão monetário)."""
>>>>>>> 64ec9886f1e598d60850f545ee865d1da75d06e9
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
<<<<<<< HEAD
# Código de produto — SEQUENCIAL (fix 1.1)
# ---------------------------------------------------------------------------
def _proximo_numero_codigo(conn):
    """Devolve o próximo número inteiro disponível para um código PRD#####.
    considera TODOS os códigos provisórios (mesmo os já usados),
    porque a coluna `codigos_provisorios.codigo` é UNIQUE independentemente
    de `usado`. Ignorar os usados causaria IntegrityError ao reinserir o
    mesmo código.
    """
    try:
        m1 = conn.execute(
            "SELECT COALESCE(MAX(CAST(SUBSTR(codigo, 4) AS INTEGER)), 0) AS m "
            "FROM produtos WHERE codigo LIKE 'PRD%' "
            "AND CAST(SUBSTR(codigo, 4) AS INTEGER) > 0"
        ).fetchone()["m"] or 0
    except Exception:
        m1 = 0
    try:
        m2 = conn.execute(
            "SELECT COALESCE(MAX(CAST(SUBSTR(codigo, 4) AS INTEGER)), 0) AS m "
            "FROM codigos_provisorios WHERE codigo LIKE 'PRD%' "
            "AND CAST(SUBSTR(codigo, 4) AS INTEGER) > 0"
        ).fetchone()["m"] or 0
    except Exception:
        m2 = 0
    return max(int(m1), int(m2)) + 1

def gerar_codigo_produto(conn):
    """Gera o próximo código PRD##### sequencial (nunca aleatório).
    """
    proximo = _proximo_numero_codigo(conn)
    while True:
        codigo = f"PRD{proximo:05d}"
        existe = conn.execute(
            "SELECT 1 FROM produtos WHERE codigo=?", (codigo,)
        ).fetchone()
        existe_prov = conn.execute(
            "SELECT 1 FROM codigos_provisorios WHERE codigo=?", (codigo,)
        ).fetchone()   # ← sem AND usado=0
=======
# Código de produto
# ---------------------------------------------------------------------------
def gerar_codigo_produto(conn):
    row = conn.execute("SELECT COUNT(*) AS c FROM produtos").fetchone()
    proximo = row["c"] + 1
    while True:
        codigo = f"PRD{proximo:05d}"
        existe = conn.execute("SELECT 1 FROM produtos WHERE codigo=?", (codigo,)).fetchone()
        existe_prov = conn.execute("SELECT 1 FROM codigos_provisorios WHERE codigo=? AND usado=0", (codigo,)).fetchone()
>>>>>>> 64ec9886f1e598d60850f545ee865d1da75d06e9
        if not existe and not existe_prov:
            return codigo
        proximo += 1

<<<<<<< HEAD
def reservar_codigo_provisorio(conn, sessao_id):
    """Reserva um código provisório para a sessão.

    - Se a sessão já tem um código não usado, DEVOLVE-O (não gera outro).
    - Só cria um novo se não houver nenhum reservado.
    - Limpa órfãos antigos (>24h) antes de decidir.
    """
    # 1) Limpa órfãos antigos
    limite_limpeza = (datetime.now() - timedelta(minutes=1)).isoformat(timespec="seconds")
    try:
        conn.execute(
            "UPDATE codigos_provisorios SET usado=1 WHERE usado=0 AND data_criacao < ?",
            (limite_limpeza,),
        )
        conn.commit()
    except Exception:
        pass

    # 2) Reutiliza o código já reservado para esta sessão
    existente = conn.execute(
        "SELECT codigo FROM codigos_provisorios "
        "WHERE sessao_id = ? AND usado = 0 "
        "ORDER BY id_codigo DESC LIMIT 1",
        (sessao_id,),
    ).fetchone()
    if existente:
        return existente["codigo"]

    # 3) Só cria novo se não existir nenhum
    codigo = gerar_codigo_produto(conn)
    conn.execute(
        "INSERT INTO codigos_provisorios (codigo, sessao_id, usado, data_criacao) "
        "VALUES (?, ?, 0, ?)",
        (codigo, sessao_id, datetime.now().isoformat(timespec="seconds")),
    )
    conn.commit()
    return codigo
=======

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
>>>>>>> 64ec9886f1e598d60850f545ee865d1da75d06e9


def liberar_codigo_provisorio(conn, sessao_id, codigo=None):
    if codigo:
        conn.execute(
            "UPDATE codigos_provisorios SET usado=1 WHERE sessao_id=? AND codigo=?",
            (sessao_id, codigo),
        )
    else:
<<<<<<< HEAD
        conn.execute(
            "UPDATE codigos_provisorios SET usado=1 WHERE sessao_id=? AND usado=0", (sessao_id,)
        )
=======
        conn.execute("UPDATE codigos_provisorios SET usado=1 WHERE sessao_id=? AND usado=0", (sessao_id,))
>>>>>>> 64ec9886f1e598d60850f545ee865d1da75d06e9
    conn.commit()


def usar_codigo_provisorio(conn, sessao_id, codigo):
    conn.execute(
        "UPDATE codigos_provisorios SET usado=1 WHERE sessao_id=? AND codigo=?",
        (sessao_id, codigo),
    )
    conn.commit()


# ---------------------------------------------------------------------------
<<<<<<< HEAD
# Conversão de unidades
# ---------------------------------------------------------------------------
def converter_para_unidade_base(quantidade_original, qtd_por_unidade, unidade_original="Unidade"):
    """Converte para unidade base. Aceita decimais apenas para kg."""
    if unidade_original not in UNIDADES_VALIDAS:
        raise RegraNegocioError("Unidade inválida.")

    try:
        qtd_float = float(quantidade_original)
    except (TypeError, ValueError):
        raise RegraNegocioError("Quantidade inválida.")
    if not math.isfinite(qtd_float) or qtd_float <= 0:
        raise RegraNegocioError("Quantidade deve ser maior que zero.")

    if unidade_original in UNIDADES_DECIMAIS:
        return round(qtd_float, 3)

    if not qtd_float.is_integer():
        raise RegraNegocioError(
            f"Quantidade inválida para '{unidade_original}': deve ser um número inteiro."
        )
    qtd = int(qtd_float)

    if unidade_original == "Unidade":
        return qtd

    try:
        fator = int(qtd_por_unidade)
    except (TypeError, ValueError):
        raise RegraNegocioError("Quantidade por unidade inválida.")
    if fator <= 0:
        raise RegraNegocioError("Quantidade por unidade deve ser positiva.")
    return qtd * fator


def saldo_atual(conn, id_produto):
    """Devolve o saldo actual (sempre float — suporta kg)."""
    row = conn.execute("SELECT saldo_atual FROM estoque WHERE id_produto=?", (id_produto,)).fetchone()
    if not row:
        return 0.0
    try:
        return float(row["saldo_atual"] or 0)
    except (TypeError, ValueError):
        return 0.0
=======
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
>>>>>>> 64ec9886f1e598d60850f545ee865d1da75d06e9


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
<<<<<<< HEAD
# Código de segurança
# ---------------------------------------------------------------------------
=======
# Código de segurança para alteração de produto (com hash)
# ---------------------------------------------------------------------------
from werkzeug.security import generate_password_hash, check_password_hash

>>>>>>> 64ec9886f1e598d60850f545ee865d1da75d06e9
def validar_codigo_alteracao_produto(codigo_fornecido):
    codigo_cadastrado = get_config("codigo_alteracao_produto", "")
    if not codigo_cadastrado:
        return True
<<<<<<< HEAD
    try:
        return check_password_hash(codigo_cadastrado, codigo_fornecido or "")
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Registrar entrada (compra) — usa float (kg)
=======
    return check_password_hash(codigo_cadastrado, codigo_fornecido)


# ---------------------------------------------------------------------------
# Registrar entrada (compra)
>>>>>>> 64ec9886f1e598d60850f545ee865d1da75d06e9
# ---------------------------------------------------------------------------
def registrar_entrada(conn, id_produto, quantidade_original, unidade_original,
                       preco_unitario, id_usuario, nota_fiscal=None,
                       fornecedor=None, observacoes=None, data_hora=None,
                       ip_address=None):
    if not validar_produto_cadastrado(conn, id_produto):
        raise RegraNegocioError("Selecione um produto cadastrado e ativo.")
<<<<<<< HEAD
    if unidade_original not in UNIDADES_VALIDAS:
        raise RegraNegocioError("Unidade inválida.")
=======
>>>>>>> 64ec9886f1e598d60850f545ee865d1da75d06e9

    produto = conn.execute("SELECT * FROM produtos WHERE id_produto=?", (id_produto,)).fetchone()
    if not produto:
        raise RegraNegocioError("Produto não encontrado.")

<<<<<<< HEAD
    if produto["unidade"] in ("Unidade", "kg") and unidade_original != produto["unidade"]:
        raise RegraNegocioError(
            f"Este produto só pode ser movimentado em '{produto['unidade']}'."
        )

    qtd_base = converter_para_unidade_base(
        quantidade_original, produto["qtd_por_unidade"], unidade_original)
    if qtd_base <= 0:
        raise RegraNegocioError("Quantidade de entrada deve ser maior que zero.")

    try:
        preco_float = float(preco_unitario)
    except (TypeError, ValueError):
        raise RegraNegocioError("Preço unitário inválido.")
    if preco_float < 0:
        raise RegraNegocioError("Preço unitário não pode ser negativo.")

    # FIX: usar float (kg) em vez de int
    qtd_original_num = float(quantidade_original)
    valor_total = arredondar_moeda(qtd_original_num * preco_float)
    preco_unitario_base = arredondar_moeda(valor_total / qtd_base) if qtd_base else 0.0
=======
    qtd_base = converter_para_unidade_base(quantidade_original, produto["qtd_por_unidade"], unidade_original)
    if qtd_base <= 0:
        raise RegraNegocioError("Quantidade de entrada deve ser maior que zero.")

    fator = int(produto["qtd_por_unidade"]) if unidade_original in ("Caixa", "Embalagem") else 1
    preco_unitario_base = preco_unitario / fator if fator else preco_unitario
    preco_unitario_base = arredondar_moeda(preco_unitario_base)
>>>>>>> 64ec9886f1e598d60850f545ee865d1da75d06e9

    _garantir_linha_estoque(conn, id_produto)
    saldo = saldo_atual(conn, id_produto)

<<<<<<< HEAD
    # Cálculo do novo custo consoante o método configurado
    metodo = get_config("metodo_custeio", "media_ponderada")
    custo_atual = float(produto["preco_custo"] or 0)

    if metodo == "manual":
        # Custo FIXO: nunca altera automaticamente.
        # O utilizador gere o custo pela edição do produto.
        novo_custo = custo_atual
        atualizar_custo = False
    elif metodo == "media_ponderada" and (saldo + qtd_base) > 0:
        # Média ponderada móvel (contabilidade clássica)
        novo_custo = (saldo * custo_atual + valor_total) / (saldo + qtd_base)
        novo_custo = arredondar_moeda(novo_custo)
        atualizar_custo = True
    else:
        # "ultimo_preco" ou fallback — usa o preço da entrada actual
        novo_custo = preco_unitario_base
        atualizar_custo = True

=======
    metodo = get_config("metodo_custeio", "media_ponderada")
    custo_atual = produto["preco_custo"] or 0
    if metodo == "media_ponderada" and (saldo + qtd_base) > 0:
        novo_custo = ((saldo * custo_atual) + (qtd_base * preco_unitario_base)) / (saldo + qtd_base)
    else:
        novo_custo = preco_unitario_base
    novo_custo = arredondar_moeda(novo_custo)

    valor_total = arredondar_moeda(qtd_base * preco_unitario_base)
>>>>>>> 64ec9886f1e598d60850f545ee865d1da75d06e9
    data_hora = data_hora or datetime.now().isoformat(timespec="seconds")

    cur = conn.execute(
        """INSERT INTO movimentos
           (tipo, id_produto, data_hora, quantidade, quantidade_original, unidade_original,
            preco_unitario, valor_total, id_usuario, nota_fiscal, fornecedor, observacoes, lucro)
           VALUES ('Entrada',?,?,?,?,?,?,?,?,?,?,?,0)""",
<<<<<<< HEAD
        (id_produto, data_hora, qtd_base, qtd_original_num, unidade_original,
=======
        (id_produto, data_hora, qtd_base, int(quantidade_original), unidade_original,
>>>>>>> 64ec9886f1e598d60850f545ee865d1da75d06e9
         preco_unitario_base, valor_total, id_usuario, nota_fiscal,
         fornecedor or produto["fornecedor"], observacoes),
    )
    movimento_id = cur.lastrowid

    conn.execute(
        "UPDATE estoque SET saldo_atual = saldo_atual + ?, ultima_atualizacao=? WHERE id_produto=?",
        (qtd_base, data_hora, id_produto),
    )
<<<<<<< HEAD
    if atualizar_custo:
        conn.execute("UPDATE produtos SET preco_custo=? WHERE id_produto=?", (novo_custo, id_produto))
=======
    conn.execute("UPDATE produtos SET preco_custo=? WHERE id_produto=?", (novo_custo, id_produto))
>>>>>>> 64ec9886f1e598d60850f545ee865d1da75d06e9

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
<<<<<<< HEAD
    if unidade_original not in UNIDADES_VALIDAS:
        raise RegraNegocioError("Unidade inválida.")
=======
>>>>>>> 64ec9886f1e598d60850f545ee865d1da75d06e9

    produto = conn.execute("SELECT * FROM produtos WHERE id_produto=?", (id_produto,)).fetchone()
    if not produto:
        raise RegraNegocioError("Produto não encontrado.")

<<<<<<< HEAD
    if produto["unidade"] in ("Unidade", "kg") and unidade_original != produto["unidade"]:
        raise RegraNegocioError(
            f"Este produto só pode ser movimentado em '{produto['unidade']}'."
        )

    qtd_base = converter_para_unidade_base(
        quantidade_original, produto["qtd_por_unidade"], unidade_original)
    if qtd_base <= 0:
        raise RegraNegocioError("Quantidade de saída deve ser maior que zero.")

    try:
        preco_float = float(preco_unitario)
    except (TypeError, ValueError):
        raise RegraNegocioError("Preço unitário inválido.")
    if preco_float < 0:
        raise RegraNegocioError("Preço unitário não pode ser negativo.")

    qtd_original_num = float(quantidade_original)
    valor_total = arredondar_moeda(qtd_original_num * preco_float)
    preco_unitario_base = arredondar_moeda(valor_total / qtd_base) if qtd_base else 0.0
=======
    qtd_base = converter_para_unidade_base(quantidade_original, produto["qtd_por_unidade"], unidade_original)
    if qtd_base <= 0:
        raise RegraNegocioError("Quantidade de saída deve ser maior que zero.")

    fator = int(produto["qtd_por_unidade"]) if unidade_original in ("Caixa", "Embalagem") else 1
    preco_unitario_base = preco_unitario / fator if fator else preco_unitario
    preco_unitario_base = arredondar_moeda(preco_unitario_base)
>>>>>>> 64ec9886f1e598d60850f545ee865d1da75d06e9

    _garantir_linha_estoque(conn, id_produto)
    saldo = saldo_atual(conn, id_produto)

    permitir_negativo = get_config("permitir_estoque_negativo", "0") == "1"
<<<<<<< HEAD

    custo_medio = float(produto["preco_custo"] or 0)
    custo_total_venda = arredondar_moeda(custo_medio * qtd_base)
    lucro = arredondar_moeda(valor_total - custo_total_venda)

    data_hora = data_hora or datetime.now().isoformat(timespec="seconds")

    if permitir_negativo:
        conn.execute(
            "UPDATE estoque SET saldo_atual = saldo_atual - ?, ultima_atualizacao=? WHERE id_produto=?",
            (qtd_base, data_hora, id_produto),
        )
    else:
        cur_update = conn.execute(
            "UPDATE estoque SET saldo_atual = saldo_atual - ?, ultima_atualizacao=? "
            "WHERE id_produto=? AND saldo_atual >= ?",
            (qtd_base, data_hora, id_produto, qtd_base),
        )
        if cur_update.rowcount == 0:
            conn.rollback()
            raise RegraNegocioError(
                f"Estoque insuficiente. Saldo atual: {saldo}, solicitado: {qtd_base}."
            )

=======
    if not permitir_negativo and qtd_base > saldo + 1e-9:
        raise RegraNegocioError(f"Estoque insuficiente. Saldo atual: {saldo}, solicitado: {qtd_base}.")

    custo_medio = produto["preco_custo"] or 0
    lucro = arredondar_moeda((preco_unitario_base - custo_medio) * qtd_base)
    valor_total = arredondar_moeda(qtd_base * preco_unitario_base)
    data_hora = data_hora or datetime.now().isoformat(timespec="seconds")

>>>>>>> 64ec9886f1e598d60850f545ee865d1da75d06e9
    cur = conn.execute(
        """INSERT INTO movimentos
           (tipo, id_produto, data_hora, quantidade, quantidade_original, unidade_original,
            preco_unitario, valor_total, id_usuario, cliente, forma_pagamento, observacoes, lucro)
           VALUES ('Saida',?,?,?,?,?,?,?,?,?,?,?,?)""",
<<<<<<< HEAD
        (id_produto, data_hora, qtd_base, qtd_original_num, unidade_original,
=======
        (id_produto, data_hora, qtd_base, int(quantidade_original), unidade_original,
>>>>>>> 64ec9886f1e598d60850f545ee865d1da75d06e9
         preco_unitario_base, valor_total, id_usuario, cliente, forma_pagamento, observacoes, lucro),
    )
    movimento_id = cur.lastrowid

<<<<<<< HEAD
=======
    conn.execute(
        "UPDATE estoque SET saldo_atual = saldo_atual - ?, ultima_atualizacao=? WHERE id_produto=?",
        (qtd_base, data_hora, id_produto),
    )

>>>>>>> 64ec9886f1e598d60850f545ee865d1da75d06e9
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
<<<<<<< HEAD
# Situação do estoque / alertas
=======
# Situação do estoque
>>>>>>> 64ec9886f1e598d60850f545ee865d1da75d06e9
# ---------------------------------------------------------------------------
def situacao_estoque(saldo, minimo, maximo):
    if saldo < (minimo or 0):
        return "abaixo_minimo"
    if maximo and saldo > maximo:
        return "acima_maximo"
    return "normal"


<<<<<<< HEAD
=======
# ---------------------------------------------------------------------------
# Alertas
# ---------------------------------------------------------------------------
>>>>>>> 64ec9886f1e598d60850f545ee865d1da75d06e9
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
<<<<<<< HEAD
# Balancete — usa float (kg)
# ---------------------------------------------------------------------------
def calcular_balancete(conn, periodo, data_inicio, data_fim, id_categoria=None, id_produto=None):
    dt_ini = data_inicio + "T00:00:00"
    dt_fim = data_fim + "T23:59:59"

    sql_prod = """
        SELECT p.*, c.nome AS categoria_nome
        FROM produtos p
        LEFT JOIN categorias c ON c.id_categoria = p.id_categoria
        WHERE (
            p.ativo = 1
            OR EXISTS (
                SELECT 1 FROM movimentos m
                WHERE m.id_produto = p.id_produto
                  AND m.data_hora <= ?
            )
        )
    """
    params = [dt_fim]
    if id_categoria:
        sql_prod += " AND p.id_categoria = ?"
        params.append(id_categoria)
    if id_produto:
        sql_prod += " AND p.id_produto = ?"
=======
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
>>>>>>> 64ec9886f1e598d60850f545ee865d1da75d06e9
        params.append(id_produto)
    sql_prod += " ORDER BY p.nome"
    produtos = conn.execute(sql_prod, params).fetchall()

    linhas = []
<<<<<<< HEAD
    total_saldo_ini_qtd = 0.0
    total_entradas_qtd = 0.0
    total_saidas_qtd = 0.0
    total_saldo_fin_qtd = 0.0
    total_entradas_val = 0.0
    total_saidas_val = 0.0
    total_lucro = 0.0
    total_saldo_ini_valor_custo = 0.0
    total_saldo_ini_valor_venda = 0.0
    total_saldo_fin_valor_custo = 0.0
=======
    total_saldo_ini_qtd = 0
    total_entradas_qtd = 0
    total_saidas_qtd = 0
    total_saldo_fin_qtd = 0
    total_entradas_val = 0
    total_saidas_val = 0
    total_lucro = 0
>>>>>>> 64ec9886f1e598d60850f545ee865d1da75d06e9

    for p in produtos:
        idp = p["id_produto"]

<<<<<<< HEAD
        row_ini = conn.execute(
            """SELECT COALESCE(SUM(CASE WHEN tipo='Entrada' THEN quantidade ELSE -quantidade END),0) AS s
               FROM movimentos WHERE id_produto=? AND data_hora < ?""",
            (idp, dt_ini),
        ).fetchone()
        saldo_ini = round(float(row_ini["s"] or 0), 3)

        ent_q = conn.execute(
            """SELECT COALESCE(SUM(quantidade),0) AS s,
                      COALESCE(SUM(valor_total),0) AS v
               FROM movimentos
               WHERE id_produto=? AND tipo='Entrada' AND data_hora BETWEEN ? AND ?""",
            (idp, dt_ini, dt_fim),
        ).fetchone()
        sai_q = conn.execute(
            """SELECT COALESCE(SUM(quantidade),0) AS s,
                      COALESCE(SUM(valor_total),0) AS v,
                      COALESCE(SUM(lucro),0) AS l
               FROM movimentos
               WHERE id_produto=? AND tipo='Saida' AND data_hora BETWEEN ? AND ?""",
            (idp, dt_ini, dt_fim),
        ).fetchone()

        entradas_qtd = round(float(ent_q["s"] or 0), 3)
        entradas_val = arredondar_moeda(ent_q["v"])
        saidas_qtd = round(float(sai_q["s"] or 0), 3)
        saidas_val = arredondar_moeda(sai_q["v"])
        lucro = arredondar_moeda(sai_q["l"])
        saldo_fin = round(saldo_ini + entradas_qtd - saidas_qtd, 3)

        custo_atual = float(p["preco_custo"] or 0)
        venda_atual = float(p["preco_venda"] or 0)
        saldo_ini_valor_custo = arredondar_moeda(saldo_ini * custo_atual)
        saldo_ini_valor_venda = arredondar_moeda(saldo_ini * venda_atual)
        saldo_fin_valor_custo = arredondar_moeda(saldo_fin * custo_atual)
=======
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
>>>>>>> 64ec9886f1e598d60850f545ee865d1da75d06e9

        total_saldo_ini_qtd += saldo_ini
        total_entradas_qtd += entradas_qtd
        total_saidas_qtd += saidas_qtd
        total_saldo_fin_qtd += saldo_fin
        total_entradas_val += entradas_val
        total_saidas_val += saidas_val
        total_lucro += lucro
<<<<<<< HEAD
        total_saldo_ini_valor_custo += saldo_ini_valor_custo
        total_saldo_ini_valor_venda += saldo_ini_valor_venda
        total_saldo_fin_valor_custo += saldo_fin_valor_custo
=======
>>>>>>> 64ec9886f1e598d60850f545ee865d1da75d06e9

        linhas.append({
            "id_produto": idp,
            "codigo": p["codigo"],
            "produto": p["nome"],
            "categoria": p["categoria_nome"] or "—",
<<<<<<< HEAD
            "unidade": p["unidade"],
            "saldo_inicial": saldo_ini,
            "saldo_inicial_qtd": saldo_ini,
            "saldo_inicial_valor_custo": saldo_ini_valor_custo,
            "saldo_inicial_valor_venda": saldo_ini_valor_venda,
=======
            "saldo_inicial": saldo_ini,
            "saldo_inicial_qtd": saldo_ini,
            "saldo_inicial_valor_custo": 0,
            "saldo_inicial_valor_venda": 0,
>>>>>>> 64ec9886f1e598d60850f545ee865d1da75d06e9
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
<<<<<<< HEAD
            "saldo_final_valor_custo": saldo_fin_valor_custo,
=======
            "saldo_final_valor_custo": 0,
>>>>>>> 64ec9886f1e598d60850f545ee865d1da75d06e9
            "lucro": lucro,
            "debito": entradas_val,
            "credito": saidas_val,
            "nome_produto": p["nome"],
            "codigo_produto": p["codigo"],
        })

    totais = {
<<<<<<< HEAD
        "saldo_inicial": round(total_saldo_ini_qtd, 3),
        "saldo_inicial_qtd": round(total_saldo_ini_qtd, 3),
        "saldo_inicial_valor_custo": arredondar_moeda(total_saldo_ini_valor_custo),
        "saldo_inicial_valor_venda": arredondar_moeda(total_saldo_ini_valor_venda),
        "entradas_qtd": round(total_entradas_qtd, 3),
        "entradas_val": arredondar_moeda(total_entradas_val),
        "entradas_valor": arredondar_moeda(total_entradas_val),
        "entradas_valor_venda": arredondar_moeda(total_entradas_val),
        "saidas_qtd": round(total_saidas_qtd, 3),
        "saidas_val": arredondar_moeda(total_saidas_val),
        "saidas_valor": arredondar_moeda(total_saidas_val),
        "saidas_valor_venda": arredondar_moeda(total_saidas_val),
        "saldo_final": round(total_saldo_fin_qtd, 3),
        "saldo_final_qtd": round(total_saldo_fin_qtd, 3),
        "saldo_final_valor_custo": arredondar_moeda(total_saldo_fin_valor_custo),
        "lucro": arredondar_moeda(total_lucro),
=======
        "saldo_inicial": total_saldo_ini_qtd,
        "saldo_inicial_qtd": total_saldo_ini_qtd,
        "saldo_inicial_valor_custo": 0,
        "saldo_inicial_valor_venda": 0,
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
        "saldo_final_valor_custo": 0,
        "lucro": total_lucro,
>>>>>>> 64ec9886f1e598d60850f545ee865d1da75d06e9
    }
    return linhas, totais


def calcular_extrato_categoria(conn, id_categoria, data_inicio, data_fim):
<<<<<<< HEAD
    dt_ini = data_inicio + "T00:00:00"
    dt_fim = data_fim + "T23:59:59"
=======
    dt_ini = data_inicio + " 00:00:00"
    dt_fim = data_fim + " 23:59:59"
>>>>>>> 64ec9886f1e598d60850f545ee865d1da75d06e9

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
<<<<<<< HEAD
    saldo = 0.0
    entradas_acum = 0.0
    saidas_acum = 0.0
    for m in movs:
        sinal = 1 if m["tipo"] == "Entrada" else -1
        qtd = round(float(m["quantidade"] or 0), 3)
        saldo = round(saldo + sinal * qtd, 3)
        if m["tipo"] == "Entrada":
            entradas_acum += float(m["valor_total"] or 0)
        else:
            saidas_acum += float(m["valor_total"] or 0)
=======
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
>>>>>>> 64ec9886f1e598d60850f545ee865d1da75d06e9
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
<<<<<<< HEAD
    return linhas, saldo, arredondar_moeda(entradas_acum), arredondar_moeda(saidas_acum)


# ---------------------------------------------------------------------------
# Extrato por produto (cronológico)
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Extrato por produto (cronológico) — devolve qtd ORIGINAL e qtd BASE
# ---------------------------------------------------------------------------
def calcular_extrato_produto(conn, id_produto, data_inicio, data_fim):
    """Extrato cronológico de um produto.

    Cada linha devolve:
      - quantidade_original + unidade_original  (o que o utilizador registou)
      - quantidade_base                          (unidade avulsa, para o saldo)
      - saldo_acumulado                          (sempre em unidade base)

    Devolve (produto_dict, linhas, resumo) ou (None, [], {}).
    """
    produto = conn.execute(
        "SELECT * FROM produtos WHERE id_produto=?", (id_produto,)
    ).fetchone()
    if not produto:
        return None, [], {}

    dt_ini = (data_inicio or "1900-01-01") + "T00:00:00"
    dt_fim = (data_fim or "2999-12-31") + "T23:59:59"

    # Saldo antes do período (em unidade base)
    row_ini = conn.execute(
        """SELECT COALESCE(SUM(CASE WHEN tipo='Entrada' THEN quantidade ELSE -quantidade END),0) AS s
           FROM movimentos
           WHERE id_produto=? AND data_hora < ?""",
        (id_produto, dt_ini),
    ).fetchone()
    saldo_ini = round(float(row_ini["s"] or 0), 3)

    movs = conn.execute(
        """SELECT m.*, u.nome AS usuario_nome
           FROM movimentos m
           LEFT JOIN usuarios u ON u.id_usuario = m.id_usuario
           WHERE m.id_produto = ? AND m.data_hora BETWEEN ? AND ?
           ORDER BY m.data_hora ASC, m.id_movimento ASC""",
        (id_produto, dt_ini, dt_fim),
    ).fetchall()

    linhas = []
    saldo = saldo_ini
    tot_ent_qtd_orig = 0.0
    tot_ent_val = 0.0
    tot_sai_qtd_orig = 0.0
    tot_sai_val = 0.0
    tot_lucro = 0.0

    for m in movs:
        qtd_base = round(float(m["quantidade"] or 0), 3)
        qtd_orig = round(float(m["quantidade_original"] or 0), 3)
        sinal = 1 if m["tipo"] == "Entrada" else -1
        saldo = round(saldo + sinal * qtd_base, 3)

        valor = float(m["valor_total"] or 0)
        if m["tipo"] == "Entrada":
            tot_ent_qtd_orig += qtd_orig
            tot_ent_val += valor
        else:
            tot_sai_qtd_orig += qtd_orig
            tot_sai_val += valor
            tot_lucro += float(m["lucro"] or 0)

        linhas.append({
            "data_hora": m["data_hora"],
            "tipo": m["tipo"],
            "documento": m["nota_fiscal"] or "—",
            "quantidade_original": qtd_orig,
            "unidade_original": m["unidade_original"],
            "quantidade_base": qtd_base,
            "preco_unitario": arredondar_moeda(m["preco_unitario"]),
            "valor_total": arredondar_moeda(valor),
            "lucro": arredondar_moeda(m["lucro"] or 0),
            "saldo_acumulado": saldo,
            "terceiro": m["fornecedor"] or m["cliente"] or "—",
            "usuario": m["usuario_nome"] or "—",
        })

    resumo = {
        "qtd_comprada": round(tot_ent_qtd_orig, 3),
        "valor_comprado": arredondar_moeda(tot_ent_val),
        "qtd_vendida": round(tot_sai_qtd_orig, 3),
        "valor_vendido": arredondar_moeda(tot_sai_val),
        "lucro_periodo": arredondar_moeda(tot_lucro),
        "saldo_inicial": saldo_ini,
        "saldo_final": saldo,
        "n_movimentos": len(linhas),
    }

    return dict(produto), linhas, resumo

# ---------------------------------------------------------------------------
# Cotações
# ---------------------------------------------------------------------------
def gerar_numero_cotacao(conn):
=======
    return linhas, saldo, entradas_acum, saidas_acum


# ---------------------------------------------------------------------------
# Cotações
# ---------------------------------------------------------------------------
def gerar_numero_cotacao(conn):
    """Gera número sequencial para cotação (ex: COT-0001)."""
>>>>>>> 64ec9886f1e598d60850f545ee865d1da75d06e9
    row = conn.execute("SELECT COUNT(*) AS c FROM cotacoes").fetchone()
    prox = row["c"] + 1
    return f"COT-{prox:04d}"


<<<<<<< HEAD
def _calcular_total_itens(itens):
    total = 0.0
    for item in itens:
        qtd = int(item["quantidade"])
        preco = float(item["preco_unitario"])
        desconto = float(item.get("desconto_percentual", 0) or 0)
        total += qtd * preco * (1 - desconto / 100)
    return arredondar_moeda(total)


def criar_cotacao(conn, id_usuario, cliente_nome, cliente_email=None, cliente_telefone=None,
                  data_validade=None, observacoes=None, itens=None):
=======
def criar_cotacao(conn, id_usuario, cliente_nome, cliente_email=None, cliente_telefone=None,
                  data_validade=None, observacoes=None, itens=None):
    """
    itens: lista de dicionários com id_produto, quantidade, preco_unitario, desconto_percentual
    """
>>>>>>> 64ec9886f1e598d60850f545ee865d1da75d06e9
    if not itens:
        raise RegraNegocioError("A cotação deve ter pelo menos um item.")

    numero = gerar_numero_cotacao(conn)
    data_emissao = datetime.now().isoformat(timespec="seconds")
    if not data_validade:
        data_validade = (datetime.now() + timedelta(days=30)).isoformat(timespec="seconds")

<<<<<<< HEAD
    valor_total = _calcular_total_itens(itens)
=======
    valor_total = 0
    for item in itens:
        qtd = int(item["quantidade"])
        preco = arredondar_moeda(item["preco_unitario"])
        desconto = float(item.get("desconto_percentual", 0))
        subtotal = qtd * preco * (1 - desconto/100)
        valor_total += arredondar_moeda(subtotal)
>>>>>>> 64ec9886f1e598d60850f545ee865d1da75d06e9

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
<<<<<<< HEAD
        preco = float(item["preco_unitario"])
        desconto = float(item.get("desconto_percentual", 0) or 0)
        subtotal = arredondar_moeda(qtd * preco * (1 - desconto / 100))
=======
        preco = arredondar_moeda(item["preco_unitario"])
        desconto = float(item.get("desconto_percentual", 0))
        subtotal = qtd * preco * (1 - desconto/100)
>>>>>>> 64ec9886f1e598d60850f545ee865d1da75d06e9
        conn.execute(
            """INSERT INTO itens_cotacao
               (id_cotacao, id_produto, quantidade, preco_unitario, desconto_percentual, valor_total)
               VALUES (?,?,?,?,?,?)""",
<<<<<<< HEAD
            (id_cotacao, item["id_produto"], qtd, arredondar_moeda(preco),
             desconto, subtotal)
=======
            (id_cotacao, item["id_produto"], qtd, preco, desconto, arredondar_moeda(subtotal))
>>>>>>> 64ec9886f1e598d60850f545ee865d1da75d06e9
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


<<<<<<< HEAD
def atualizar_cotacao(conn, id_cotacao, id_usuario, cliente_nome,
                      cliente_email=None, cliente_telefone=None,
                      data_validade=None, observacoes=None, itens=None):
    cotacao = conn.execute("SELECT * FROM cotacoes WHERE id_cotacao=?", (id_cotacao,)).fetchone()
    if not cotacao:
        raise RegraNegocioError("Cotação não encontrada.")
    if cotacao["status"] != "Aberta":
        raise RegraNegocioError("Apenas cotações abertas podem ser editadas.")
    if not itens:
        raise RegraNegocioError("A cotação deve ter pelo menos um item.")

    valor_total = _calcular_total_itens(itens)

    conn.execute(
        """UPDATE cotacoes
           SET nome_cliente=?, email_cliente=?, telefone_cliente=?,
               data_validade=?, observacoes=?, valor_total=?
           WHERE id_cotacao=?""",
        (cliente_nome, cliente_email, cliente_telefone,
         data_validade, observacoes, valor_total, id_cotacao),
    )

    conn.execute("DELETE FROM itens_cotacao WHERE id_cotacao=?", (id_cotacao,))
    for item in itens:
        qtd = int(item["quantidade"])
        preco = float(item["preco_unitario"])
        desconto = float(item.get("desconto_percentual", 0) or 0)
        subtotal = arredondar_moeda(qtd * preco * (1 - desconto / 100))
        conn.execute(
            """INSERT INTO itens_cotacao
               (id_cotacao, id_produto, quantidade, preco_unitario, desconto_percentual, valor_total)
               VALUES (?,?,?,?,?,?)""",
            (id_cotacao, item["id_produto"], qtd, arredondar_moeda(preco),
             desconto, subtotal),
        )

    conn.commit()
    registrar_auditoria(conn, id_usuario, "cotacoes", id_cotacao, "UPDATE",
                        {"valor_total": cotacao["valor_total"]},
                        {"valor_total": valor_total, "n_itens": len(itens)},
                        None)
    return id_cotacao


=======
>>>>>>> 64ec9886f1e598d60850f545ee865d1da75d06e9
def atualizar_status_cotacao(conn, id_cotacao, novo_status, id_usuario):
    cotacao = conn.execute("SELECT * FROM cotacoes WHERE id_cotacao=?", (id_cotacao,)).fetchone()
    if not cotacao:
        raise RegraNegocioError("Cotação não encontrada.")
<<<<<<< HEAD
    if cotacao["status"] in ("Aprovada", "Rejeitada", "Convertida"):
=======
    if cotacao["status"] in ("Aprovada", "Rejeitada"):
>>>>>>> 64ec9886f1e598d60850f545ee865d1da75d06e9
        raise RegraNegocioError("Cotação já está finalizada.")
    conn.execute("UPDATE cotacoes SET status=? WHERE id_cotacao=?", (novo_status, id_cotacao))
    registrar_auditoria(conn, id_usuario, "cotacoes", id_cotacao, "UPDATE",
                        {"status": cotacao["status"]}, {"status": novo_status}, None)
    conn.commit()


def converter_cotacao_em_venda(conn, id_cotacao, id_usuario):
<<<<<<< HEAD
    res = obter_cotacao(conn, id_cotacao)
    if not res:
        raise RegraNegocioError("Cotação não encontrada.")
    cotacao, itens = res
    if cotacao["status"] != "Aprovada":
        raise RegraNegocioError("Apenas cotações aprovadas podem ser convertidas em venda.")

=======
    """Converte uma cotação aprovada em movimento de saída (venda)."""
    cotacao, itens = obter_cotacao(conn, id_cotacao)
    if not cotacao:
        raise RegraNegocioError("Cotação não encontrada.")
    if cotacao["status"] != "Aprovada":
        raise RegraNegocioError("Apenas cotações aprovadas podem ser convertidas em venda.")

    # Para cada item, registra uma saída
>>>>>>> 64ec9886f1e598d60850f545ee865d1da75d06e9
    for item in itens:
        registrar_saida(
            conn,
            id_produto=item["id_produto"],
            quantidade_original=item["quantidade"],
<<<<<<< HEAD
            unidade_original="Unidade",
=======
            unidade_original="Unidade",  # ou usar a unidade do produto
>>>>>>> 64ec9886f1e598d60850f545ee865d1da75d06e9
            preco_unitario=item["preco_unitario"],
            id_usuario=id_usuario,
            cliente=cotacao["nome_cliente"],
            observacoes=f"Venda gerada da cotação {cotacao['numero']}",
            ip_address=None
        )

<<<<<<< HEAD
    atualizar_status_cotacao(conn, id_cotacao, "Convertida", id_usuario)


# ---------------------------------------------------------------------------
# Reset / formatação da base de dados
# ---------------------------------------------------------------------------
NIVEIS_RESET = {
    "movimentos": "Apagar apenas movimentos (mantém catálogo e usuários)",
    "catalogo":   "Apagar movimentos + catálogo (mantém usuários e configurações)",
    "total":      "Reset total — volta ao estado de fábrica",
}


def _checkpoint_wal(conn):
    try:
        conn.execute("PRAGMA wal_checkpoint(FULL)")
    except Exception:
        pass


def fazer_backup_automatico(motivo="pre_reset"):
    import os
    import shutil
    from database import get_base_dir, DB_PATH
    try:
        backup_dir = os.path.join(get_base_dir(), "backups")
        os.makedirs(backup_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        destino = os.path.join(backup_dir, f"{motivo}_{ts}.db")
        c = get_conn()
        _checkpoint_wal(c)
        c.close()
        shutil.copy2(DB_PATH, destino)
        return destino
    except Exception:
        return None


def _reset_sequence(conn, tabelas):
    """Reinicia o auto-increment das tabelas indicadas."""
    try:
        placeholders = ",".join("?" * len(tabelas))
        conn.execute(f"DELETE FROM sqlite_sequence WHERE name IN ({placeholders})", tabelas)
    except Exception:
        pass


def _apagar_movimentos(conn):
    """Apaga movimentos, zerando saldo mas mantendo produtos."""
    conn.execute("DELETE FROM movimentos")
    conn.execute("DELETE FROM inventarios")
    conn.execute("DELETE FROM login_attempts")
    conn.execute("DELETE FROM auditoria")
    conn.execute("DELETE FROM itens_cotacao")
    conn.execute("DELETE FROM cotacoes")
    conn.execute("DELETE FROM codigos_provisorios")
    conn.execute("UPDATE estoque SET saldo_atual=0, ultima_atualizacao=?",
                 (datetime.now().isoformat(timespec="seconds"),))
    _reset_sequence(conn, ["movimentos", "inventarios", "login_attempts", "auditoria",
                            "itens_cotacao", "cotacoes", "codigos_provisorios"])


def _apagar_catalogo(conn):
    """Apaga produtos e categorias."""
    conn.execute("DELETE FROM itens_cotacao")
    conn.execute("DELETE FROM cotacoes")
    conn.execute("DELETE FROM movimentos")
    conn.execute("DELETE FROM inventarios")
    conn.execute("DELETE FROM estoque")
    conn.execute("DELETE FROM produtos")
    conn.execute("DELETE FROM categorias")
    conn.execute("DELETE FROM codigos_provisorios")
    conn.execute("DELETE FROM auditoria")
    conn.execute("DELETE FROM login_attempts")
    _reset_sequence(conn, ["produtos", "categorias", "itens_cotacao", "cotacoes",
                            "movimentos", "inventarios", "estoque", "codigos_provisorios",
                            "auditoria", "login_attempts"])


def _reset_total(conn):
    """Apaga tudo — reinicia para estado de fábrica."""
    from database import DEFAULT_CATEGORIAS, DEFAULT_CONFIG
    for tabela in ("itens_cotacao", "cotacoes", "movimentos", "inventarios",
                   "estoque", "produtos", "categorias", "codigos_provisorios",
                   "auditoria", "login_attempts", "usuarios", "configuracoes"):
        try:
            conn.execute(f"DELETE FROM {tabela}")
        except Exception:
            pass
    try:
        conn.execute("DELETE FROM sqlite_sequence")
    except Exception:
        pass

    conn.execute(
        "INSERT INTO usuarios (nome, login, senha_hash, perfil, ativo) VALUES (?,?,?,?,1)",
        ("Administrador", "admin", generate_password_hash("admin123"), "Admin"),
    )
    conn.executemany(
        "INSERT INTO categorias (nome, descricao, ativo) VALUES (?,?,1)",
        DEFAULT_CATEGORIAS,
    )
    for chave, valor in DEFAULT_CONFIG.items():
        conn.execute("INSERT INTO configuracoes (chave, valor) VALUES (?,?)", (chave, valor))


def formatar_base_dados(conn, nivel, id_usuario_admin, ip_address=None):
    if nivel not in NIVEIS_RESET:
        raise RegraNegocioError("Nível de reset inválido.")

    backup_path = fazer_backup_automatico(motivo=f"pre_reset_{nivel}")

    if nivel == "movimentos":
        _apagar_movimentos(conn)
    elif nivel == "catalogo":
        _apagar_catalogo(conn)
    elif nivel == "total":
        _reset_total(conn)
    else:
        raise RegraNegocioError("Nível desconhecido.")

    conn.commit()
    return {
        "nivel": nivel,
        "backup_path": backup_path,
        "mensagem": NIVEIS_RESET[nivel],
    }



# ---------------------------------------------------------------------------
# Vendas a Crédito / Contas a Receber / Recibos
# ---------------------------------------------------------------------------
def gerar_numero_recibo(conn):
    row = conn.execute("SELECT COUNT(*) AS c FROM recibos").fetchone()
    return f"REC-{row['c']+1:05d}"


def gerar_numero_fatura(conn):
    row = conn.execute("SELECT COUNT(*) AS c FROM contas_receber").fetchone()
    return f"FT-{datetime.now().year}-{row['c']+1:05d}"


def registrar_venda_credito(conn, itens, id_usuario, nome_cliente,
                             nif_cliente=None, endereco_cliente=None,
                             localidade_cliente=None, pais_cliente=None,
                             email_cliente=None, telefone_cliente=None,
                             data_vencimento=None, condicao_pagamento=None,
                             isento_iva=False, taxa_iva=None,
                             observacoes=None, data_venda=None,
                             ip_address=None):
    """Cria UMA fatura (conta_receber) com vários itens e devolve id_conta."""
    from database import registrar_auditoria, get_config

    if not itens:
        raise RegraNegocioError("A fatura deve ter pelo menos um item.")
    if not nome_cliente or not nome_cliente.strip():
        raise RegraNegocioError("Nome do cliente é obrigatório.")

    # Taxa efetiva
    if isento_iva:
        taxa_iva_efetiva = 0.0
    else:
        if taxa_iva is None:
            try:
                taxa_iva_efetiva = float(get_config("taxa_iva_padrao", "16"))
            except (TypeError, ValueError):
                taxa_iva_efetiva = 16.0
        else:
            taxa_iva_efetiva = float(taxa_iva)

    # 1) Registar cada item como saída individual
    movs_criados = []
    valor_total = 0.0
    data_emissao_final = data_venda
    for it in itens:
        registrar_saida(
            conn, id_produto=it["id_produto"],
            quantidade_original=it["quantidade"],
            unidade_original=it["unidade"],
            preco_unitario=it["preco_unitario"],
            id_usuario=id_usuario,
            cliente=nome_cliente,
            forma_pagamento="Credito",
            observacoes=observacoes,
            data_hora=data_venda,
            ip_address=ip_address,
        )
        mov = conn.execute(
            "SELECT id_movimento, id_produto, valor_total, data_hora, "
            "       quantidade, quantidade_original, unidade_original, preco_unitario "
            "FROM movimentos WHERE id_produto=? AND id_usuario=? "
            "ORDER BY id_movimento DESC LIMIT 1",
            (it["id_produto"], id_usuario),
        ).fetchone()
        movs_criados.append(dict(mov))
        valor_total += float(mov["valor_total"] or 0)
        data_emissao_final = mov["data_hora"]

    valor_total = arredondar_moeda(valor_total)
    data_emissao_final = data_emissao_final or datetime.now().isoformat(timespec="seconds")

    # 2) Gerar número de fatura sequencial
    numero_fatura = _proximo_numero_fatura(conn)

    # 3) Criar conta a receber
    cur = conn.execute(
        """INSERT INTO contas_receber
           (id_movimento, nome_cliente, nif_cliente, endereco_cliente,
            localidade_cliente, pais_cliente, email_cliente, telefone_cliente,
            valor_total, valor_pago, saldo, data_emissao, data_vencimento,
            status, observacoes, id_usuario, numero_fatura,
            isento_iva, taxa_iva, condicao_pagamento)
           VALUES (?,?,?,?,?,?,?,?,?,0,?,?,?, 'Aberta', ?,?,?,
                   ?,?,?)""",
        (movs_criados[0]["id_movimento"], nome_cliente, nif_cliente,
         endereco_cliente, localidade_cliente, pais_cliente,
         email_cliente, telefone_cliente,
         valor_total, valor_total, data_emissao_final, data_vencimento,
         observacoes, id_usuario, numero_fatura,
         1 if isento_iva else 0, taxa_iva_efetiva, condicao_pagamento),
    )
    id_conta = cur.lastrowid

    # 4) Guardar itens da fatura
    for m in movs_criados:
        conn.execute(
            """INSERT INTO contas_receber_itens
               (id_conta, id_movimento, id_produto, quantidade_original,
                unidade_original, quantidade_base, preco_unitario, valor_total)
               VALUES (?,?,?,?,?,?,?,?)""",
            (id_conta, m["id_movimento"], m["id_produto"],
             m["quantidade_original"], m["unidade_original"],
             m["quantidade"], m["preco_unitario"], m["valor_total"]),
        )

    conn.commit()
    registrar_auditoria(conn, id_usuario, "contas_receber", id_conta,
                        "INSERT", None,
                        {"cliente": nome_cliente, "valor": valor_total,
                         "numero_fatura": numero_fatura,
                         "n_itens": len(movs_criados)},
                        ip_address)
    return {"id_conta": id_conta, "valor": valor_total,
            "n_itens": len(movs_criados), "numero_fatura": numero_fatura}


def _proximo_numero_fatura(conn):
    """Gera 'FT 2026/00001' e incrementa o contador na config."""
    from database import get_config, set_config
    serie = get_config("serie_fatura", "FT") or "FT"
    ano = datetime.now().year
    try:
        num = int(get_config("proximo_num_fatura", "1"))
    except (TypeError, ValueError):
        num = 1
    numero = f"{serie} {ano}/{num:05d}"
    set_config("proximo_num_fatura", str(num + 1))
    return numero

def liquidar_conta(conn, id_conta, valor, forma_pagamento, id_usuario,
                    data_pagamento=None, observacoes=None, ip_address=None):
    from database import registrar_auditoria

    conta = conn.execute(
        "SELECT * FROM contas_receber WHERE id_conta=?", (id_conta,)
    ).fetchone()
    if not conta:
        raise RegraNegocioError("Conta a receber não encontrada.")
    if conta["status"] == "Cancelada":
        raise RegraNegocioError("Conta cancelada não pode ser liquidada.")
    if conta["status"] == "Liquidada":
        raise RegraNegocioError("Conta já está liquidada.")

    valor = round(float(valor or 0), 2)
    if valor <= 0:
        raise RegraNegocioError("Valor do pagamento deve ser positivo.")
    if valor > float(conta["saldo"]) + 0.001:
        raise RegraNegocioError(
            f"Valor excede o saldo devedor ({float(conta['saldo']):.2f})."
        )

    data_pagamento = data_pagamento or datetime.now().isoformat(timespec="seconds")
    numero = gerar_numero_recibo(conn)

    cur = conn.execute(
        """INSERT INTO recibos (numero, id_conta, valor, data_pagamento,
                                forma_pagamento, observacoes, id_usuario)
           VALUES (?,?,?,?,?,?,?)""",
        (numero, id_conta, valor, data_pagamento, forma_pagamento,
         observacoes, id_usuario),
    )
    id_recibo = cur.lastrowid

    novo_pago = round(float(conta["valor_pago"]) + valor, 2)
    novo_saldo = round(float(conta["valor_total"]) - novo_pago, 2)
    novo_status = "Liquidada" if novo_saldo <= 0.001 else "Parcial"

    conn.execute(
        "UPDATE contas_receber SET valor_pago=?, saldo=?, status=? WHERE id_conta=?",
        (novo_pago, novo_saldo, novo_status, id_conta),
    )
    conn.commit()
    registrar_auditoria(conn, id_usuario, "recibos", id_recibo, "INSERT",
                        None, {"numero": numero, "valor": valor},
                        ip_address)
    return {"id_recibo": id_recibo, "numero": numero,
            "novo_saldo": novo_saldo, "status": novo_status}


def obter_conta_receber(conn, id_conta):
    """Devolve (conta_dict, itens_list, recibos_list) ou None."""
    conta = conn.execute(
        "SELECT * FROM contas_receber WHERE id_conta=?", (id_conta,)
    ).fetchone()
    if not conta:
        return None

    itens = conn.execute(
        """SELECT cri.*, p.codigo AS produto_codigo, p.nome AS produto_nome
           FROM contas_receber_itens cri
           JOIN produtos p ON p.id_produto=cri.id_produto
           WHERE cri.id_conta=?
           ORDER BY cri.id_item""",
        (id_conta,)
    ).fetchall()

    # Fallback: faturas antigas sem itens → usa o movimento único
    if not itens and conta["id_movimento"]:
        mov = conn.execute(
            """SELECT m.*, p.codigo AS produto_codigo, p.nome AS produto_nome
               FROM movimentos m JOIN produtos p ON p.id_produto=m.id_produto
               WHERE m.id_movimento=?""",
            (conta["id_movimento"],)
        ).fetchone()
        if mov:
            itens = [{
                "id_conta": id_conta,
                "id_movimento": mov["id_movimento"],
                "id_produto": mov["id_produto"],
                "produto_codigo": mov["produto_codigo"],
                "produto_nome": mov["produto_nome"],
                "quantidade_original": mov["quantidade_original"],
                "unidade_original": mov["unidade_original"],
                "quantidade_base": mov["quantidade"],
                "preco_unitario": mov["preco_unitario"],
                "valor_total": mov["valor_total"],
            }]

    recibos = conn.execute(
        "SELECT * FROM recibos WHERE id_conta=? ORDER BY data_pagamento",
        (id_conta,)
    ).fetchall()

    return dict(conta), [dict(i) for i in itens], [dict(r) for r in recibos]


def cancelar_conta_receber(conn, id_conta, id_usuario, ip_address=None):
    """Cancela a fatura, REVERTE o stock dos produtos e apaga recibos/movimentos."""
    from database import registrar_auditoria

    conta = conn.execute(
        "SELECT * FROM contas_receber WHERE id_conta=?", (id_conta,)
    ).fetchone()
    if not conta:
        raise RegraNegocioError("Fatura não encontrada.")
    if conta["status"] == "Cancelada":
        raise RegraNegocioError("Fatura já está cancelada.")

    # 1) Descobrir os movimentos a reverter
    movs = conn.execute(
        "SELECT id_movimento FROM contas_receber_itens WHERE id_conta=?",
        (id_conta,)
    ).fetchall()
    ids_mov = [m["id_movimento"] for m in movs]
    if not ids_mov and conta["id_movimento"]:
        ids_mov = [conta["id_movimento"]]

    revertidos = 0
    for id_mov in ids_mov:
        mov = conn.execute(
            "SELECT id_movimento, id_produto, quantidade FROM movimentos WHERE id_movimento=?",
            (id_mov,)
        ).fetchone()
        if not mov:
            continue
        # Devolve ao estoque
        conn.execute(
            "UPDATE estoque SET saldo_atual = saldo_atual + ?, ultima_atualizacao=? "
            "WHERE id_produto=?",
            (mov["quantidade"],
             datetime.now().isoformat(timespec="seconds"),
             mov["id_produto"]),
        )
        conn.execute("DELETE FROM movimentos WHERE id_movimento=?", (id_mov,))
        revertidos += 1

    # 2) Apagar itens, recibos e a conta
    conn.execute("DELETE FROM contas_receber_itens WHERE id_conta=?", (id_conta,))
    conn.execute("DELETE FROM recibos WHERE id_conta=?", (id_conta,))
    conn.execute("DELETE FROM contas_receber WHERE id_conta=?", (id_conta,))
    conn.commit()

    registrar_auditoria(conn, id_usuario, "contas_receber", id_conta,
                        "DELETE", dict(conta),
                        {"acao": "CANCELAMENTO_COM_REVERSAO_STOCK",
                         "movimentos_revertidos": revertidos},
                        ip_address)
    return {"movimentos_revertidos": revertidos}


def obter_recibo(conn, id_recibo):
    r = conn.execute("SELECT * FROM recibos WHERE id_recibo=?", (id_recibo,)).fetchone()
    if not r:
        return None
    conta = conn.execute(
        "SELECT * FROM contas_receber WHERE id_conta=?", (r["id_conta"],)
    ).fetchone()
    return dict(r), (dict(conta) if conta else None)

def faturar_cotacao(conn, id_cotacao, id_usuario, ip_address=None,
                    data_vencimento=None, isento_iva=False, taxa_iva=None):
    """Converte uma cotação em fatura a crédito (conta_receber)."""
    from database import registrar_auditoria

    res = obter_cotacao(conn, id_cotacao)
    if not res:
        raise RegraNegocioError("Cotação não encontrada.")
    cotacao, itens_cot = res
    if cotacao["status"] == "Convertida":
        raise RegraNegocioError("Cotação já convertida em venda.")
    if cotacao["status"] in ("Rejeitada",):
        raise RegraNegocioError("Cotação rejeitada não pode ser faturada.")
    if not itens_cot:
        raise RegraNegocioError("Cotação sem itens.")

    # Converte cada item da cotação para formato do registrar_venda_credito
    itens = []
    for ic in itens_cot:
        itens.append({
            "id_produto": ic["id_produto"],
            "quantidade": float(ic["quantidade"]),
            "unidade": "Unidade",   # cotação usa unidade padrão
            "preco_unitario": float(ic["preco_unitario"]),
        })

    resultado = registrar_venda_credito(
        conn,
        itens=itens,
        id_usuario=id_usuario,
        nome_cliente=cotacao["nome_cliente"],
        nif_cliente=None,
        email_cliente=cotacao.get("email_cliente"),
        telefone_cliente=cotacao.get("telefone_cliente"),
        data_vencimento=data_vencimento,
        isento_iva=isento_iva,
        taxa_iva=taxa_iva,
        observacoes=f"Gerada da cotação {cotacao['numero']}",
        ip_address=ip_address,
    )

    # Marca cotação como Convertida
    conn.execute("UPDATE cotacoes SET status='Convertida' WHERE id_cotacao=?",
                 (id_cotacao,))
    conn.commit()
    registrar_auditoria(conn, id_usuario, "cotacoes", id_cotacao, "UPDATE",
                        {"status": cotacao["status"]},
                        {"status": "Convertida", "id_conta_gerada": resultado["id_conta"]},
                        ip_address)

    return resultado

# ===========================================================================
# AUDITORIA DE ESTOQUE
# ===========================================================================
def estoque_teorico(conn, id_produto, data_limite):
    """Estoque teórico até à data — usa fecho mensal quando disponível."""
    data_iso = (data_limite or "9999-12-31") + "T23:59:59"

    # Tenta usar o último fecho anterior à data
    fecho = conn.execute(
        """SELECT f.* FROM fechos_mensais f
           WHERE f.data_fecho < ?
           ORDER BY f.data_fecho DESC LIMIT 1""",
        (data_limite,),
    ).fetchone()

    if fecho:
        item = conn.execute(
            """SELECT quantidade FROM fechos_mensais_itens
               WHERE id_fecho=? AND id_produto=?""",
            (fecho["id_fecho"], id_produto),
        ).fetchone()
        base = float(item["quantidade"] if item else 0)
        ponto_partida = fecho["data_fecho"] + "T23:59:59"
    else:
        base = 0.0
        ponto_partida = "1900-01-01T00:00:00"

    mov = conn.execute(
        """SELECT COALESCE(SUM(
                CASE WHEN tipo='Entrada' THEN quantidade
                     WHEN tipo='Saida'   THEN -quantidade
                     ELSE 0 END), 0) AS s
           FROM movimentos
           WHERE id_produto=? AND data_hora > ? AND data_hora <= ?""",
        (id_produto, ponto_partida, data_iso),
    ).fetchone()
    return round(base + float(mov["s"] or 0), 3)

def justificar_divergencia(conn, id_divergencia, motivo, id_usuario,
                            observacao=None, ip_address=None):
    from database import registrar_auditoria
    div = conn.execute(
        "SELECT * FROM auditoria_divergencias WHERE id_divergencia=?",
        (id_divergencia,),
    ).fetchone()
    if not div:
        raise RegraNegocioError("Divergência não encontrada.")
    if div["estado"] == "ajustada":
        raise RegraNegocioError("Divergência já ajustada — não pode ser justificada.")

    conn.execute(
        """UPDATE auditoria_divergencias
           SET estado='justificada', causa=?, observacao=?, motivo_justificacao=?
           WHERE id_divergencia=?""",
        (motivo, observacao, motivo, id_divergencia),
    )
    conn.commit()
    registrar_auditoria(conn, id_usuario, "auditoria_divergencias",
                        id_divergencia, "UPDATE",
                        {"estado": div["estado"]},
                        {"estado": "justificada", "motivo": motivo},
                        ip_address)


def solicitar_recontagem(conn, id_divergencia, id_usuario, ip_address=None):
    from database import registrar_auditoria
    div = conn.execute(
        "SELECT * FROM auditoria_divergencias WHERE id_divergencia=?",
        (id_divergencia,),
    ).fetchone()
    if not div:
        raise RegraNegocioError("Divergência não encontrada.")
    agora = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        """UPDATE auditoria_divergencias
           SET recontagem_solicitada=1, recontagem_contador_id=?,
               recontagem_data=?, estado='pendente'
           WHERE id_divergencia=?""",
        (id_usuario, agora, id_divergencia),
    )
    conn.commit()
    registrar_auditoria(conn, id_usuario, "auditoria_divergencias",
                        id_divergencia, "UPDATE", None,
                        {"acao": "recontagem_solicitada"}, ip_address)


def marcar_aceite(conn, id_divergencia, id_usuario, ip_address=None):
    from database import registrar_auditoria
    conn.execute(
        "UPDATE auditoria_divergencias SET estado='aceita' WHERE id_divergencia=?",
        (id_divergencia,),
    )
    conn.commit()
    registrar_auditoria(conn, id_usuario, "auditoria_divergencias",
                        id_divergencia, "UPDATE", None,
                        {"estado": "aceita"}, ip_address)


def registrar_perda(conn, id_produto, quantidade, motivo, id_usuario,
                     observacao=None, data_hora=None, ip_address=None):
    """Registra uma perda de estoque (vencimento/quebra/furto/consumo)."""
    from database import registrar_auditoria

    motivos_validos = ("Vencimento", "Quebra", "Furto", "Consumo Interno", "Outro")
    if motivo not in motivos_validos:
        raise RegraNegocioError(f"Motivo inválido. Use: {', '.join(motivos_validos)}")

    produto = conn.execute(
        "SELECT * FROM produtos WHERE id_produto=?", (id_produto,)
    ).fetchone()
    if not produto:
        raise RegraNegocioError("Produto não encontrado.")

    qtd = float(quantidade or 0)
    if qtd <= 0:
        raise RegraNegocioError("Quantidade deve ser positiva.")

    saldo = saldo_atual(conn, id_produto)
    if qtd > saldo and get_config("permitir_estoque_negativo", "0") != "1":
        raise RegraNegocioError(
            f"Saldo insuficiente. Actual: {saldo}, solicitado: {qtd}."
        )

    data_hora = data_hora or datetime.now().isoformat(timespec="seconds")
    custo = float(produto["preco_custo"] or 0)
    valor_total = round(qtd * custo, 2)

    conn.execute(
        "UPDATE estoque SET saldo_atual = saldo_atual - ?, ultima_atualizacao=? "
        "WHERE id_produto=?",
        (qtd, data_hora, id_produto),
    )
    cur = conn.execute(
        """INSERT INTO movimentos
           (tipo, id_produto, data_hora, quantidade, quantidade_original,
            unidade_original, preco_unitario, valor_total, id_usuario,
            observacoes, lucro, subtipo)
           VALUES ('Saida',?,?,?,?,?,?,?,?,?,0,?)""",
        (id_produto, data_hora, qtd, qtd,
         produto["unidade"], custo, valor_total, id_usuario,
         f"Perda — {motivo}. {observacao or ''}".strip(),
         f"Perda_{motivo.replace(' ', '_')}"),
    )
    id_mov = cur.lastrowid
    conn.commit()
    registrar_auditoria(conn, id_usuario, "movimentos", id_mov, "INSERT",
                        None, {"tipo": "Perda", "motivo": motivo,
                               "id_produto": id_produto, "qtd": qtd},
                        ip_address)
    return id_mov

def abrir_auditoria(conn, data_inicio, data_fim, tipo, id_categoria,
                    responsavel_id, tolerancia_percentual=1.0,
                    tolerancia_valor_minimo=0.0, observacoes=None,
                    ip_address=None):
    from database import registrar_auditoria
    agora = datetime.now().isoformat(timespec="seconds")
    cur = conn.execute(
        """INSERT INTO auditorias
           (data_inicio, data_fim, data_abertura, tipo, id_categoria,
            responsavel_id, estado, tolerancia_percentual,
            tolerancia_valor_minimo, observacoes)
           VALUES (?,?,?,?,?,?, 'aberta', ?,?,?)""",
        (data_inicio, data_fim, agora, tipo, id_categoria,
         responsavel_id, float(tolerancia_percentual or 1.0),
         float(tolerancia_valor_minimo or 0), observacoes),
    )
    id_aud = cur.lastrowid
    conn.commit()
    registrar_auditoria(conn, responsavel_id, "auditorias", id_aud,
                        "INSERT", None,
                        {"data_inicio": data_inicio, "data_fim": data_fim,
                         "tipo": tipo}, ip_address)
    return id_aud


def produtos_da_auditoria(conn, id_auditoria):
    aud = conn.execute(
        "SELECT * FROM auditorias WHERE id_auditoria=?", (id_auditoria,)
    ).fetchone()
    if not aud:
        return []
    sql = """SELECT p.id_produto, p.codigo, p.nome, p.unidade,
                    p.preco_custo, c.nome AS categoria_nome,
                    COALESCE(e.saldo_atual, 0) AS saldo_atual
             FROM produtos p
             LEFT JOIN categorias c ON c.id_categoria=p.id_categoria
             LEFT JOIN estoque e   ON e.id_produto=p.id_produto
             WHERE p.ativo=1"""
    params = []
    if aud["tipo"] == "por_categoria" and aud["id_categoria"]:
        sql += " AND p.id_categoria=?"
        params.append(aud["id_categoria"])
    sql += " ORDER BY p.nome"
    return conn.execute(sql, params).fetchall()


def congelar_estoque_teorico(conn, id_auditoria, ip_address=None):
    """Cria linhas de divergência com o teórico congelado (contado=0)."""
    from database import registrar_auditoria
    aud = conn.execute(
        "SELECT * FROM auditorias WHERE id_auditoria=?", (id_auditoria,)
    ).fetchone()
    if not aud:
        raise RegraNegocioError("Auditoria não encontrada.")
    if aud["congelado_em"]:
        return

    produtos = produtos_da_auditoria(conn, id_auditoria)
    agora = datetime.now().isoformat(timespec="seconds")

    for p in produtos:
        teorico = estoque_teorico(conn, p["id_produto"], aud["data_fim"])
        custo = float(p["preco_custo"] or 0)
        conn.execute(
            """INSERT INTO auditoria_divergencias
               (id_auditoria, id_produto, estoque_teorico, estoque_contado,
                diferenca_qtd, custo_unitario, diferenca_valor, estado)
               VALUES (?,?,?,0,?,?,?, 'pendente')""",
            (id_auditoria, p["id_produto"], teorico,
             -teorico, custo, round(-teorico * custo, 2)),
        )

    conn.execute(
        "UPDATE auditorias SET congelado_em=?, estado='em_contagem' WHERE id_auditoria=?",
        (agora, id_auditoria),
    )
    conn.commit()
    registrar_auditoria(conn, aud["responsavel_id"], "auditorias", id_auditoria,
                        "UPDATE", {"estado": aud["estado"]},
                        {"estado": "em_contagem", "congelado_em": agora},
                        ip_address)


def registrar_contagem(conn, id_auditoria, id_produto, quantidade, id_usuario,
                       local=None, lote=None, validade=None, observacao=None,
                       contagem_cega=False, ip_address=None):
    from database import registrar_auditoria
    agora = datetime.now().isoformat(timespec="seconds")
    cur = conn.execute(
        """INSERT INTO auditoria_contagens
           (id_auditoria, id_produto, quantidade_contada, data_contagem,
            id_usuario_contador, local_prateleira, lote, validade,
            observacao, contagem_cega)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (id_auditoria, id_produto, float(quantidade), agora,
         id_usuario, local, lote, validade, observacao,
         1 if contagem_cega else 0),
    )
    id_contagem = cur.lastrowid

    div = conn.execute(
        "SELECT * FROM auditoria_divergencias WHERE id_auditoria=? AND id_produto=?",
        (id_auditoria, id_produto),
    ).fetchone()
    if div:
        teorico = float(div["estoque_teorico"] or 0)
        custo = float(div["custo_unitario"] or 0)
        dif_qtd = round(float(quantidade) - teorico, 3)
        dif_valor = round(dif_qtd * custo, 2)
        conn.execute(
            """UPDATE auditoria_divergencias
               SET estoque_contado=?, diferenca_qtd=?, diferenca_valor=?
               WHERE id_divergencia=?""",
            (float(quantidade), dif_qtd, dif_valor, div["id_divergencia"]),
        )
    conn.commit()
    registrar_auditoria(conn, id_usuario, "auditoria_contagens", id_contagem,
                        "INSERT", None,
                        {"id_auditoria": id_auditoria, "id_produto": id_produto,
                         "qtd": quantidade}, ip_address)
    return id_contagem


def divergencias_da_auditoria(conn, id_auditoria):
    return conn.execute(
        """SELECT d.*, p.codigo, p.nome, p.unidade, c.nome AS categoria_nome
           FROM auditoria_divergencias d
           JOIN produtos p ON p.id_produto=d.id_produto
           LEFT JOIN categorias c ON c.id_categoria=p.id_categoria
           WHERE d.id_auditoria=?
           ORDER BY ABS(d.diferenca_valor) DESC""",
        (id_auditoria,),
    ).fetchall()

# ---------------------------------------------------------------------------
# RELATÓRIOS DE AUDITORIA
# ---------------------------------------------------------------------------
def resumo_executivo(conn, id_auditoria):
    aud = obter_auditoria(conn, id_auditoria)
    if not aud:
        return None

    produtos = produtos_da_auditoria(conn, id_auditoria)
    valor_custo = 0.0
    valor_venda = 0.0
    for p in produtos:
        qtd = estoque_teorico(conn, p["id_produto"], aud["data_fim"])
        valor_custo += qtd * float(p["preco_custo"] or 0)
        valor_venda += qtd * float(p["preco_venda"] or 0)

    divs = divergencias_da_auditoria(conn, id_auditoria)
    div_qtd = sum(abs(float(d["diferenca_qtd"] or 0)) for d in divs)
    div_valor = sum(abs(float(d["diferenca_valor"] or 0)) for d in divs)
    div_pct = (div_valor / valor_custo * 100) if valor_custo else 0
    pendentes = [d for d in divs if d["estado"] == "pendente"]

    return {
        "aud": aud,
        "n_produtos": len(produtos),
        "valor_custo": round(valor_custo, 2),
        "valor_venda": round(valor_venda, 2),
        "div_qtd": round(div_qtd, 3),
        "div_valor": round(div_valor, 2),
        "div_percentual": round(div_pct, 2),
        "n_divergencias": len(divs),
        "n_pendentes": len(pendentes),
        "top_divergencias": divs[:10],
    }


def reconciliacao_periodo(conn, data_inicio, data_fim, id_categoria=None):
    sql = """SELECT p.id_produto, p.codigo, p.nome, p.unidade,
                    p.preco_custo, c.nome AS categoria_nome
             FROM produtos p
             LEFT JOIN categorias c ON c.id_categoria=p.id_categoria
             WHERE p.ativo=1"""
    params = []
    if id_categoria:
        sql += " AND p.id_categoria=?"
        params.append(id_categoria)
    sql += " ORDER BY p.nome"
    produtos = conn.execute(sql, params).fetchall()

    dt_ini = data_inicio + "T00:00:00"
    dt_fim = data_fim + "T23:59:59"

    linhas = []
    tot = {"ini": 0, "ent": 0, "sai": 0, "per": 0, "aj": 0, "teo": 0}
    for p in produtos:
        ini = estoque_teorico(conn, p["id_produto"], data_inicio + "T00:00:00"[:10])

        movs = conn.execute(
            """SELECT tipo, subtipo, COALESCE(SUM(quantidade),0) AS s,
                      COALESCE(SUM(valor_total),0) AS v
               FROM movimentos
               WHERE id_produto=? AND data_hora BETWEEN ? AND ?
               GROUP BY tipo, subtipo""",
            (p["id_produto"], dt_ini, dt_fim),
        ).fetchall()

        ent = sum(float(m["s"]) for m in movs if m["tipo"] == "Entrada"
                  and (m["subtipo"] or "") != "Ajuste_Inventario")
        sai = sum(float(m["s"]) for m in movs if m["tipo"] == "Saida"
                  and not (m["subtipo"] or "").startswith("Perda_")
                  and (m["subtipo"] or "") != "Ajuste_Inventario")
        per = sum(float(m["s"]) for m in movs if m["tipo"] == "Saida"
                  and (m["subtipo"] or "").startswith("Perda_"))
        aj_ent = sum(float(m["s"]) for m in movs if m["tipo"] == "Entrada"
                     and (m["subtipo"] or "") == "Ajuste_Inventario")
        aj_sai = sum(float(m["s"]) for m in movs if m["tipo"] == "Saida"
                     and (m["subtipo"] or "") == "Ajuste_Inventario")
        aj = aj_ent - aj_sai

        teo = round(ini + ent - sai - per + aj, 3)
        custo = float(p["preco_custo"] or 0)

        linhas.append({
            "codigo": p["codigo"], "nome": p["nome"],
            "categoria": p["categoria_nome"] or "—",
            "unidade": p["unidade"],
            "inicial": ini, "entradas": ent, "saidas": sai,
            "perdas": per, "ajustes": aj, "teorico": teo,
            "custo_unit": custo,
            "valor_teorico": round(teo * custo, 2),
        })
        tot["ini"] += ini; tot["ent"] += ent; tot["sai"] += sai
        tot["per"] += per; tot["aj"] += aj; tot["teo"] += teo

    return linhas, tot


def curva_abc(conn, id_auditoria=None):
    """Classifica produtos em A (80% valor), B (15%), C (5%)."""
    produtos = conn.execute(
        """SELECT p.id_produto, p.codigo, p.nome, p.unidade,
                  p.preco_custo, p.preco_venda, c.nome AS categoria_nome
           FROM produtos p LEFT JOIN categorias c ON c.id_categoria=p.id_categoria
           WHERE p.ativo=1"""
    ).fetchall()

    itens = []
    valor_total = 0.0
    for p in produtos:
        qtd = estoque_teorico(conn, p["id_produto"], datetime.now().date().isoformat())
        valor = round(qtd * float(p["preco_custo"] or 0), 2)
        valor_total += valor
        itens.append({
            "codigo": p["codigo"], "nome": p["nome"],
            "categoria": p["categoria_nome"] or "—",
            "qtd": qtd, "custo_unit": float(p["preco_custo"] or 0),
            "preco_venda": float(p["preco_venda"] or 0),
            "valor": valor,
        })

    itens.sort(key=lambda x: x["valor"], reverse=True)
    acum = 0.0
    for it in itens:
        acum += it["valor"]
        it["pct_acum"] = round(acum / valor_total * 100, 2) if valor_total else 0
        if it["pct_acum"] <= 80:
            it["classe"] = "A"
        elif it["pct_acum"] <= 95:
            it["classe"] = "B"
        else:
            it["classe"] = "C"

    return itens, valor_total


def perdas_e_validade(conn, dias_alerta=(30, 60, 90)):
    """Agrega perdas por motivo + produtos a vencer."""
    from datetime import timedelta
    motivos_rows = conn.execute(
        """SELECT subtipo, COUNT(*) AS n,
                  COALESCE(SUM(quantidade),0) AS qtd,
                  COALESCE(SUM(valor_total),0) AS valor
           FROM movimentos
           WHERE subtipo LIKE 'Perda_%'
           GROUP BY subtipo
           ORDER BY valor DESC"""
    ).fetchall()

    perdas = []
    for r in motivos_rows:
        motivo = (r["subtipo"] or "").replace("Perda_", "").replace("_", " ")
        perdas.append({
            "motivo": motivo, "n": r["n"],
            "qtd": float(r["qtd"] or 0),
            "valor": round(float(r["valor"] or 0), 2),
        })

    hoje = datetime.now().date()
    validade = []
    for dias in dias_alerta:
        limite = (hoje + timedelta(days=dias)).isoformat()
        rows = conn.execute(
            """SELECT p.codigo, p.nome, p.unidade, p.validade,
                      COALESCE(e.saldo_atual,0) AS saldo
               FROM produtos p LEFT JOIN estoque e ON e.id_produto=p.id_produto
               WHERE p.ativo=1 AND p.validade IS NOT NULL
                 AND p.validade <= ?
               ORDER BY p.validade""",
            (limite,),
        ).fetchall()
        for r in rows:
            try:
                venc = datetime.fromisoformat(r["validade"]).date()
                restantes = (venc - hoje).days
            except Exception:
                restantes = None
            validade.append({
                "codigo": r["codigo"], "nome": r["nome"],
                "unidade": r["unidade"], "validade": r["validade"],
                "saldo": float(r["saldo"] or 0),
                "dias_restantes": restantes,
                "limite_dias": dias,
            })

    # remove duplicados (mesmo produto pode aparecer em 30/60/90)
    vistos = set()
    validade_unicos = []
    for v in validade:
        if v["codigo"] in vistos: continue
        vistos.add(v["codigo"])
        validade_unicos.append(v)

    return perdas, validade_unicos


def excecoes(conn):
    """Deteta anomalias: estoque negativo, custo zero, ajustes sem justificação."""
    ex = []

    negativos = conn.execute(
        """SELECT p.codigo, p.nome, p.unidade, e.saldo_atual
           FROM estoque e JOIN produtos p ON p.id_produto=e.id_produto
           WHERE e.saldo_atual < 0 AND p.ativo=1"""
    ).fetchall()
    for r in negativos:
        ex.append({"tipo": "Estoque negativo", "produto": r["nome"],
                   "codigo": r["codigo"],
                   "detalhe": f"{float(r['saldo_atual']):.2f} {r['unidade']}"})

    custo_zero = conn.execute(
        """SELECT codigo, nome FROM produtos
           WHERE ativo=1 AND (preco_custo IS NULL OR preco_custo = 0)"""
    ).fetchall()
    for r in custo_zero:
        ex.append({"tipo": "Custo zerado", "produto": r["nome"],
                   "codigo": r["codigo"], "detalhe": "Sem custo definido"})

    sem_doc = conn.execute(
        """SELECT m.id_movimento, p.codigo, p.nome, m.data_hora, m.tipo
           FROM movimentos m JOIN produtos p ON p.id_produto=m.id_produto
           WHERE m.tipo='Entrada'
             AND (m.nota_fiscal IS NULL OR m.nota_fiscal='')
             AND COALESCE(m.subtipo,'') != 'Ajuste_Inventario'
           ORDER BY m.data_hora DESC LIMIT 50"""
    ).fetchall()
    for r in sem_doc:
        ex.append({"tipo": "Movimento sem documento", "produto": r["nome"],
                   "codigo": r["codigo"],
                   "detalhe": f"{r['tipo']} em {r['data_hora'][:10]} (#{r['id_movimento']})"})

    aj_sem_just = conn.execute(
        """SELECT a.id_ajuste, p.codigo, p.nome, a.quantidade_ajuste,
                  a.motivo, a.data_aprovacao
           FROM auditoria_ajustes a
           JOIN produtos p ON p.id_produto=a.id_produto
           WHERE (a.motivo IS NULL OR a.motivo='')"""
    ).fetchall()
    for r in aj_sem_just:
        ex.append({"tipo": "Ajuste sem justificação", "produto": r["nome"],
                   "codigo": r["codigo"],
                   "detalhe": f"{float(r['quantidade_ajuste']):.2f} em {r['data_aprovacao'][:10]}"})

    return ex

# ---------------------------------------------------------------------------
# FECHO MENSAL (otimização do cálculo de estoque teórico)
# ---------------------------------------------------------------------------
def obter_fecho_anterior(conn, data_limite):
    """Devolve o fecho mais recente cuja data_fecho < data_limite."""
    return conn.execute(
        """SELECT * FROM fechos_mensais
           WHERE data_fecho < ?
           ORDER BY data_fecho DESC LIMIT 1""",
        (data_limite,),
    ).fetchone()


def gerar_fecho_mensal(conn, ano, mes, id_usuario, ip_address=None,
                        sobrescrever=False):
    """Gera um snapshot do estoque no último instante do mês indicado."""
    from database import registrar_auditoria
    from calendar import monthrange

    if mes < 1 or mes > 12:
        raise RegraNegocioError("Mês inválido (1-12).")

    existente = conn.execute(
        "SELECT * FROM fechos_mensais WHERE ano=? AND mes=?",
        (ano, mes),
    ).fetchone()
    if existente and not sobrescrever:
        raise RegraNegocioError(
            f"Já existe fecho para {mes:02d}/{ano}. Marque 'sobrescrever' se quiser refazer."
        )

    ultimo_dia = monthrange(ano, mes)[1]
    data_fecho = f"{ano}-{mes:02d}-{ultimo_dia}"

    produtos = conn.execute(
        """SELECT p.id_produto, p.codigo, p.nome, p.unidade,
                  p.preco_custo, p.preco_venda
           FROM produtos p WHERE p.ativo=1"""
    ).fetchall()

    agora = datetime.now().isoformat(timespec="seconds")

    if existente:
        conn.execute("DELETE FROM fechos_mensais_itens WHERE id_fecho=?",
                     (existente["id_fecho"],))
        conn.execute("DELETE FROM fechos_mensais WHERE id_fecho=?",
                     (existente["id_fecho"],))

    cur = conn.execute(
        """INSERT INTO fechos_mensais
           (ano, mes, data_fecho, data_geracao, id_usuario, observacoes)
           VALUES (?,?,?,?,?,?)""",
        (ano, mes, data_fecho, agora, id_usuario,
         f"Fecho gerado manualmente"),
    )
    id_fecho = cur.lastrowid

    total_custo = 0.0
    total_venda = 0.0
    n_itens = 0

    for p in produtos:
        qtd = estoque_teorico(conn, p["id_produto"], data_fecho)
        custo = float(p["preco_custo"] or 0)
        venda = float(p["preco_venda"] or 0)
        vc = round(qtd * custo, 2)
        vv = round(qtd * venda, 2)
        total_custo += vc
        total_venda += vv
        n_itens += 1

        conn.execute(
            """INSERT INTO fechos_mensais_itens
               (id_fecho, id_produto, quantidade, custo_unitario,
                preco_venda, valor_custo, valor_venda)
               VALUES (?,?,?,?,?,?,?)""",
            (id_fecho, p["id_produto"], qtd, custo, venda, vc, vv),
        )

    conn.execute(
        """UPDATE fechos_mensais
           SET valor_total_custo=?, valor_total_venda=?, num_produtos=?
           WHERE id_fecho=?""",
        (round(total_custo, 2), round(total_venda, 2), n_itens, id_fecho),
    )
    conn.commit()
    registrar_auditoria(conn, id_usuario, "fechos_mensais", id_fecho,
                        "INSERT", None,
                        {"ano": ano, "mes": mes, "total_custo": total_custo},
                        ip_address)
    return {"id_fecho": id_fecho, "total_custo": round(total_custo, 2),
            "total_venda": round(total_venda, 2), "n_itens": n_itens,
            "data_fecho": data_fecho}


def listar_fechos(conn):
    return conn.execute(
        """SELECT f.*, u.nome AS usuario_nome
           FROM fechos_mensais f
           LEFT JOIN usuarios u ON u.id_usuario=f.id_usuario
           ORDER BY f.ano DESC, f.mes DESC"""
    ).fetchall()


def fechar_auditoria(conn, id_auditoria, id_usuario, ip_address=None):
    """Gera ajustes acima da tolerância, aplica no estoque e fecha."""
    from database import registrar_auditoria
    aud = conn.execute(
        "SELECT * FROM auditorias WHERE id_auditoria=?", (id_auditoria,)
    ).fetchone()
    if not aud:
        raise RegraNegocioError("Auditoria não encontrada.")
    if aud["estado"] == "fechada":
        raise RegraNegocioError("Auditoria já fechada.")

    agora = datetime.now().isoformat(timespec="seconds")
    tol_pct = float(aud["tolerancia_percentual"] or 1.0)
    tol_val = float(aud["tolerancia_valor_minimo"] or 0)

    divergencias = divergencias_da_auditoria(conn, id_auditoria)
    total_qtd = 0.0
    total_valor = 0.0
    ajustes_gerados = 0

    for d in divergencias:
        if d["estado"] in ("aceita", "justificada"):
            continue
        teorico = float(d["estoque_teorico"] or 0)
        contado = float(d["estoque_contado"] or 0)
        dif_qtd = float(d["diferenca_qtd"] or 0)
        dif_val = float(d["diferenca_valor"] or 0)
        total_qtd += abs(dif_qtd)
        total_valor += abs(dif_val)

        limite_qtd = abs(teorico) * (tol_pct / 100.0) if teorico else 0
        dentro_tol = (abs(dif_qtd) <= limite_qtd) and (abs(dif_val) <= tol_val)

        if dentro_tol or abs(dif_qtd) < 1e-9:
            conn.execute(
                "UPDATE auditoria_divergencias SET estado='aceita' WHERE id_divergencia=?",
                (d["id_divergencia"],),
            )
            continue

        ajuste_qtd = round(contado - teorico, 3)
        custo = float(d["custo_unitario"] or 0)

        cur = conn.execute(
            """INSERT INTO auditoria_ajustes
               (id_auditoria, id_produto, quantidade_ajuste, motivo,
                id_usuario_aprovador, data_aprovacao, observacao)
               VALUES (?,?,?,?,?,?,?)""",
            (id_auditoria, d["id_produto"], ajuste_qtd,
             d["causa"] or "Ajuste por auditoria", id_usuario, agora,
             d["observacao"]),
        )
        id_ajuste = cur.lastrowid

        tipo_mov = "Entrada" if ajuste_qtd > 0 else "Saida"
        qtd_mov = abs(ajuste_qtd)
        preco_ref = custo if custo > 0 else 0

        conn.execute(
            """INSERT INTO movimentos
               (tipo, id_produto, data_hora, quantidade, quantidade_original,
                unidade_original, preco_unitario, valor_total, id_usuario,
                observacoes, lucro, subtipo)
               VALUES (?,?,?,?,?,?,?,?,?,?,0,'Ajuste_Inventario')""",
            (tipo_mov, d["id_produto"], agora, qtd_mov, qtd_mov,
             "Unidade", preco_ref, round(qtd_mov * preco_ref, 2),
             id_usuario, f"Ajuste auditoria #{id_auditoria}"),
        )
        id_mov = conn.execute("SELECT last_insert_rowid() AS x").fetchone()["x"]

        sinal = 1 if ajuste_qtd > 0 else -1
        conn.execute(
            """UPDATE estoque SET saldo_atual = saldo_atual + ?,
                   ultima_atualizacao=? WHERE id_produto=?""",
            (sinal * qtd_mov, agora, d["id_produto"]),
        )

        conn.execute(
            """UPDATE auditoria_divergencias
               SET estado='ajustada', id_ajuste=? WHERE id_divergencia=?""",
            (id_ajuste, d["id_divergencia"]),
        )
        ajustes_gerados += 1

    conn.execute(
        """UPDATE auditorias
           SET estado='fechada', valor_div_qtd=?, valor_div_valor=?
           WHERE id_auditoria=?""",
        (round(total_qtd, 3), round(total_valor, 2), id_auditoria),
    )
    conn.commit()
    registrar_auditoria(conn, id_usuario, "auditorias", id_auditoria,
                        "UPDATE", {"estado": aud["estado"]},
                        {"estado": "fechada", "ajustes_gerados": ajustes_gerados,
                         "div_qtd": total_qtd, "div_valor": total_valor},
                        ip_address)
    return {"ajustes_gerados": ajustes_gerados,
            "div_qtd": round(total_qtd, 3),
            "div_valor": round(total_valor, 2)}


def obter_auditoria(conn, id_auditoria):
    aud = conn.execute(
        """SELECT a.*, u.nome AS responsavel_nome, c.nome AS categoria_nome
           FROM auditorias a
           LEFT JOIN usuarios u ON u.id_usuario=a.responsavel_id
           LEFT JOIN categorias c ON c.id_categoria=a.id_categoria
           WHERE a.id_auditoria=?""",
        (id_auditoria,),
    ).fetchone()
    return dict(aud) if aud else None
=======
    atualizar_status_cotacao(conn, id_cotacao, "Convertida", id_usuario)
>>>>>>> 64ec9886f1e598d60850f545ee865d1da75d06e9
