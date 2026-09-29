# -*- coding: utf-8 -*-
"""Aplicação principal (app.py) — pontos de entrada e rotas Flask.

Este ficheiro contém a instância Flask, os decorators de autenticação,
as rotas que expõem a interface web (dashboard, produtos, categorias,
movimentos, relatórios, cotações, inventário, utilizadores, configurações)
e integrações com os módulos de serviços, relatório e persistência.

Siga a documentação em /docs para instruções de instalação, empacotamento
e desenvolvimento.
"""
 
import atexit
import base64
import logging
import math
import os
import secrets
import shutil
import signal
import sqlite3
import sys
import threading
import time
import webbrowser
from datetime import datetime, timedelta
from functools import wraps
from uuid import uuid4

import traceback
from flask import (Flask, render_template, request, redirect, url_for,
                    session, flash, send_file, jsonify, abort, make_response)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from database import (init_db, get_conn, get_config, set_config,
                       get_base_dir, DB_PATH, get_company_info, registrar_auditoria)
import services
import reports as reportmod

APP_PORT = 5701
APP_NAME = "SGE"

def _get_or_create_secret_key():
    """Gera uma chave de sessão na primeira execução e reutiliza nas seguintes.

    A chave é guardada num ficheiro local (fora do controlo de versão) para
    que reiniciar a aplicação não invalide as sessões de todos os usuários.
    """
    key_path = os.path.join(get_base_dir(), ".secret_key")
    try:
        with open(key_path, "r") as f:
            key = f.read().strip()
            if key:
                return key
    except (FileNotFoundError, OSError):
        pass
    key = secrets.token_hex(32)
    try:
        with open(key_path, "w") as f:
            f.write(key)
    except OSError:
        pass
    return key


app = Flask(__name__)
app.secret_key = _get_or_create_secret_key()
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

logging.basicConfig(
    filename=os.path.join(get_base_dir(), "app_errors.log"),
    level=logging.ERROR,
    format="%(asctime)s %(levelname)s %(message)s",
)


def safe_parse_float(value, default=0.0):
    """Converte string para float de forma segura, aceitando vírgula como decimal"""
    if value is None or value == '':
        return default
    try:
        v_str = str(value).strip()
        # Se tiver vírgula como separador decimal
        if ',' in v_str and '.' in v_str:
            # Formato: 1.234,56
            v_str = v_str.replace('.', '').replace(',', '.')
        elif ',' in v_str and '.' not in v_str:
            # Formato: 1,23
            v_str = v_str.replace(',', '.')
        return float(v_str)
    except (TypeError, ValueError):
        return default


@app.errorhandler(Exception)
def handle_exception(e):
    traceback.print_exc()
    logging.error(traceback.format_exc())
    return (
        "<h1>Ocorreu um erro interno</h1>"
        "<p>Os detalhes foram registados. Tente novamente ou contacte o suporte "
        "técnico se o problema persistir.</p>"
        f'<p><a href="{url_for("dashboard")}">Voltar ao início</a></p>'
    ), 500

_shutdown_requested = False


# ---------------------------------------------------------------------------
# Encerramento limpo (garante que todos os processos terminem ao sair)
# ---------------------------------------------------------------------------
def _encerrar_tudo():
    """Callback de encerramento: fecha conexões pendentes e força saída."""
    global _shutdown_requested
    if _shutdown_requested:
        return
    _shutdown_requested = True
    try:
        if getattr(sys, "frozen", False):
            os.kill(os.getpid(), getattr(signal, "SIGTERM", 15))
    except Exception:
        pass


atexit.register(_encerrar_tudo)
try:
    signal.signal(signal.SIGINT, lambda s, f: (_encerrar_tudo(), sys.exit(0)))
    signal.signal(signal.SIGTERM, lambda s, f: (_encerrar_tudo(), sys.exit(0)))
except Exception:
    pass


def _client_ip():
    """Retorna o IP do cliente (seguro para localhost)."""
    try:
        return request.remote_addr or "127.0.0.1"
    except Exception:
        return "127.0.0.1"


# ---------------------------------------------------------------------------
# Autenticação e controle de acesso
# ---------------------------------------------------------------------------
def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def perfil_required(*perfis):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("login", next=request.path))
            if session.get("perfil") not in perfis:
                flash("Você não tem permissão para acessar essa área.", "erro")
                return redirect(url_for("dashboard"))
            return view(*args, **kwargs)
        return wrapped
    return decorator


@app.context_processor
def inject_globals():
    emp = get_company_info()
    primeira_install = get_config("primeira_instalacao", "1") == "1"
    empresa_nome = "" if primeira_install else emp.get("nome", "")
    return {
        "current_user": {
            "nome": session.get("nome"),
            "perfil": session.get("perfil"),
        },
        "empresa": {**emp, "nome": empresa_nome},
        "config": {"moeda": get_config("moeda", "MZN")},
        "ano_atual": datetime.now().year,
        "app_name": APP_NAME,
    }


def _formatar_numero_pt(value, decimals=2):
    """Formata um número no padrão pt-PT/pt-MZ: '.' para milhar, ',' para decimal."""
    decimals = int(decimals)
    try:
        val = float(value)
    except (TypeError, ValueError):
        val = 0.0
    # Python formata por omissão com ',' para milhar e '.' para decimal;
    # aqui trocamos para a convenção portuguesa.
    formatted = f"{val:,.{decimals}f}"
    parts = formatted.split('.')
    integer_part = parts[0].replace(',', '.')
    decimal_part = parts[1] if len(parts) > 1 else '0' * decimals
    return f"{integer_part},{decimal_part}" if decimals else integer_part


@app.template_filter("format_num")
def format_num(value, decimals=2):
    """Formata números genéricos no mesmo padrão usado em toda a aplicação (pt: 1.234,56)."""
    return _formatar_numero_pt(value, decimals)

@app.template_filter("format_int")
def format_int(value):
    """Formata números como inteiros com separador de milhar (ex: 1.000)"""
    try:
        val = int(float(value))
    except (TypeError, ValueError):
        val = 0
    return _formatar_numero_pt(val, 0)

@app.template_filter("format_currency")
def format_currency(value, decimals=2):
    """Formata valores monetários com separador de milhar e vírgula decimal (ex: 1.000,00)"""
    return _formatar_numero_pt(value, decimals)


# ---------------------------------------------------------------------------
# Login / Logout / Recuperação de senha
# ---------------------------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    # Autocomplete OFF → não guardar último utilizador
    if request.method == "POST":
        login_val = request.form.get("login", "").strip()
        senha = request.form.get("senha", "")

        conn = get_conn()
        bloqueado, rest_seg = services.login_bloqueado(conn, login_val)
        if bloqueado:
            mins = math.ceil(rest_seg / 60)
            flash(f"Conta temporariamente bloqueada. Tente novamente em {mins} minuto(s).", "erro")
            conn.close()
            return render_template(
                "login.html",
                bloqueio_info={"bloqueado": bloqueado, "segundos": rest_seg},
                autocomplete="off",
            )

        user = conn.execute(
            "SELECT * FROM usuarios WHERE login=? AND ativo=1", (login_val,)
        ).fetchone()

        sucesso = bool(user and check_password_hash(user["senha_hash"], senha))
        services.registrar_tentativa_login(conn, login_val, sucesso, _client_ip())

        if sucesso:
            registrar_auditoria(conn, user["id_usuario"], "usuarios",
                                user["id_usuario"], "LOGIN", None, None, _client_ip())
            conn.commit()
            conn.close()
            session["user_id"] = user["id_usuario"]
            session["nome"] = user["nome"]
            session["perfil"] = user["perfil"]
            session["_sid"] = str(uuid4())
            if get_config("primeira_instalacao", "1") == "1":
                set_config("primeira_instalacao", "0")
            return redirect(request.args.get("next") or url_for("dashboard"))
        else:
            bloq2, rest2 = services.login_bloqueado(conn, login_val)
            registrar_auditoria(conn, None, "usuarios", None, "LOGIN",
                                {"login": login_val, "sucesso": False}, None, _client_ip())
            conn.commit()
            conn.close()
            if bloq2:
                mins = math.ceil(rest2 / 60)
                flash(f"5 tentativas inválidas. Aguarde {mins} minuto(s).", "erro")
            else:
                flash("Login ou senha inválidos.", "erro")
            return render_template(
                "login.html",
                bloqueio_info={"bloqueado": bloq2, "segundos": rest2},
                autocomplete="off",
            )
    return render_template("login.html", autocomplete="off",
                           bloqueio_info=None)


@app.route("/recuperar-senha", methods=["GET", "POST"])
def recuperar_senha_inicio():
    """Passo 1: pede o login e gera token (exibe na tela, pq é desktop/offline)."""
    if request.method == "POST":
        login_val = request.form.get("login", "").strip()
        conn = get_conn()
        res = services.gerar_token_recuperacao(conn, login_val)
        conn.close()
        if res:
            token, user = res
            flash("Token gerado com sucesso.", "sucesso")
            return redirect(url_for("recuperar_senha_token", token=token))
        flash("Utilizador não encontrado ou inativo.", "erro")
    return render_template("recuperar_senha_passo1.html")


@app.route("/recuperar-senha/t/<token>", methods=["GET", "POST"])
def recuperar_senha_token(token):
    """Passo 2: valida o token e permite definir nova senha (com confirmação)."""
    conn = get_conn()
    user = services.validar_token_recuperacao(conn, token)
    if not user:
        flash("Token inválido ou expirado.", "erro")
        conn.close()
        return redirect(url_for("login"))
    if request.method == "POST":
        nova = request.form.get("nova_senha", "")
        conf = request.form.get("confirmar_senha", "")
        if not services.validar_senha(nova):
            flash("Senha fraca (mín. 8 car., letra, número e símbolo).", "erro")
        elif nova != conf:
            flash("A confirmação da senha não confere.", "erro")
        else:
            conn.execute(
                "UPDATE usuarios SET senha_hash=? WHERE id_usuario=?",
                (generate_password_hash(nova), user["id_usuario"]),
            )
            services.consumir_token_recuperacao(conn, user["id_usuario"])
            registrar_auditoria(conn, user["id_usuario"], "usuarios",
                                user["id_usuario"], "UPDATE",
                                {"senha": "RECUPERADA"}, {"senha": "ALTERADA"}, _client_ip())
            conn.commit()
            conn.close()
            flash("Senha redefinida com sucesso.", "sucesso")
            return redirect(url_for("login"))
    conn.close()
    return render_template("recuperar_senha_passo2.html", token=token,
                           usuario_nome=user["nome"], usuario_login=user["login"])


@app.route("/logout")
def logout():
    conn = get_conn()
    if "user_id" in session:
        registrar_auditoria(conn, session["user_id"], "usuarios",
                            session["user_id"], "LOGOUT", None, None, _client_ip())
        conn.commit()
    conn.close()
    session.clear()
    return redirect(url_for("login"))


@app.route("/api/shutdown", methods=["POST"])
@login_required
def shutdown_app():
    """Endpoint chamado pelo botão 'Sair e encerrar' (Admin/Gerente)."""
    t = threading.Timer(0.6, _encerrar_tudo)
    t.daemon = True
    t.start()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@app.route("/")
@login_required
def index():
    return redirect(url_for("dashboard"))


@app.route("/dashboard")
@login_required
def dashboard():
    conn = get_conn()
    categoria_id = request.args.get("categoria_id", type=int)
    periodo_dias = request.args.get("periodo", default=30, type=int)

    filtro_cat_sql = " AND p.id_categoria = ?" if categoria_id else ""
    params_cat = (categoria_id,) if categoria_id else ()

    total_produtos = conn.execute(
        f"SELECT COUNT(*) c FROM produtos p WHERE p.ativo=1{filtro_cat_sql}", params_cat
    ).fetchone()["c"]
    total_categorias = conn.execute("SELECT COUNT(*) c FROM categorias WHERE ativo=1").fetchone()["c"]

    valor_custo = conn.execute(
        f"""SELECT COALESCE(SUM(e.saldo_atual * p.preco_custo),0) v
            FROM produtos p JOIN estoque e ON e.id_produto=p.id_produto
            WHERE p.ativo=1{filtro_cat_sql}""", params_cat
    ).fetchone()["v"]
    valor_venda = conn.execute(
        f"""SELECT COALESCE(SUM(e.saldo_atual * p.preco_venda),0) v
            FROM produtos p JOIN estoque e ON e.id_produto=p.id_produto
            WHERE p.ativo=1{filtro_cat_sql}""", params_cat
    ).fetchone()["v"]

    inicio_mes = datetime.now().replace(day=1).strftime("%Y-%m-%d")
    lucro_mes = conn.execute(
        f"""SELECT COALESCE(SUM(m.lucro),0) v FROM movimentos m
            JOIN produtos p ON p.id_produto=m.id_produto
            WHERE m.tipo='Saida' AND m.data_hora >= ?{filtro_cat_sql}""",
        (inicio_mes,) + params_cat,
    ).fetchone()["v"]

    abaixo_minimo = services.produtos_abaixo_minimo(conn)
    proximos_venc = services.produtos_proximos_validade(conn)
    num_alertas = len(abaixo_minimo) + len(proximos_venc)

    desde = (datetime.now() - timedelta(days=periodo_dias)).strftime("%Y-%m-%d")
    mov_rows = conn.execute(
        f"""SELECT substr(m.data_hora,1,10) dia, m.tipo, SUM(m.quantidade) qtd
            FROM movimentos m JOIN produtos p ON p.id_produto = m.id_produto
            WHERE substr(m.data_hora,1,10) >= ?{filtro_cat_sql}
            GROUP BY dia, m.tipo ORDER BY dia""",
        (desde,) + params_cat,
    ).fetchall()
    dias_labels = sorted(set(r["dia"] for r in mov_rows))
    entradas_serie = []
    saidas_serie = []
    for d in dias_labels:
        entradas_serie.append(sum(r["qtd"] for r in mov_rows if r["dia"] == d and r["tipo"] == "Entrada"))
        saidas_serie.append(sum(r["qtd"] for r in mov_rows if r["dia"] == d and r["tipo"] == "Saida"))

    valores_rows = conn.execute(
        f"""SELECT substr(m.data_hora,1,10) dia, m.tipo, SUM(m.valor_total) total
            FROM movimentos m JOIN produtos p ON p.id_produto = m.id_produto
            WHERE substr(m.data_hora,1,10) >= ?{filtro_cat_sql}
            GROUP BY dia, m.tipo ORDER BY dia""",
        (desde,) + params_cat,
    ).fetchall()
    compras_serie = [sum(r["total"] for r in valores_rows if r["dia"] == d and r["tipo"] == "Entrada") for d in dias_labels]
    vendas_serie = [sum(r["total"] for r in valores_rows if r["dia"] == d and r["tipo"] == "Saida") for d in dias_labels]

    lucro_rows = conn.execute(
        f"""SELECT substr(m.data_hora,1,10) dia, SUM(m.lucro) lucro
            FROM movimentos m JOIN produtos p ON p.id_produto = m.id_produto
            WHERE m.tipo='Saida' AND substr(m.data_hora,1,10) >= ?{filtro_cat_sql}
            GROUP BY dia ORDER BY dia""",
        (desde,) + params_cat,
    ).fetchall()
    lucro_dict = {r["dia"]: r["lucro"] for r in lucro_rows}
    lucro_serie = [round(lucro_dict.get(d, 0), 2) for d in dias_labels]

    mais_vendidos = conn.execute(
        f"""SELECT p.nome, SUM(m.quantidade) total
            FROM movimentos m JOIN produtos p ON p.id_produto = m.id_produto
            WHERE m.tipo='Saida' AND substr(m.data_hora,1,10) >= ?{filtro_cat_sql}
            GROUP BY p.id_produto ORDER BY total DESC LIMIT 10""",
        (desde,) + params_cat,
    ).fetchall()

    sugestoes = services.sugestoes_precos(conn)
    categorias = conn.execute("SELECT * FROM categorias WHERE ativo=1 ORDER BY nome").fetchall()
    conn.close()

    return render_template(
        "dashboard.html",
        total_produtos=total_produtos, total_categorias=total_categorias,
        valor_custo=valor_custo, valor_venda=valor_venda, lucro_mes=lucro_mes,
        num_alertas=num_alertas, abaixo_minimo=abaixo_minimo[:8],
        proximos_venc=proximos_venc[:8],
        dias_labels=dias_labels, entradas_serie=entradas_serie, saidas_serie=saidas_serie,
        compras_serie=compras_serie, vendas_serie=vendas_serie, lucro_serie=lucro_serie,
        mais_vendidos=mais_vendidos, sugestoes=sugestoes[:8],
        categorias=categorias, categoria_id=categoria_id, periodo_dias=periodo_dias,
    )


# ---------------------------------------------------------------------------
# Categorias
# ---------------------------------------------------------------------------
@app.route("/categorias")
@login_required
def categorias_list():
    conn = get_conn()
    categorias = conn.execute("SELECT * FROM categorias ORDER BY nome").fetchall()
    conn.close()
    return render_template("categorias.html", categorias=categorias)


@app.route("/categorias/salvar", methods=["POST"])
@perfil_required("Admin", "Gerente")
def categorias_salvar():
    id_categoria = request.form.get("id_categoria")
    nome = request.form.get("nome", "").strip()
    descricao = request.form.get("descricao", "").strip()
    if not nome:
        flash("Informe o nome da categoria.", "erro")
        return redirect(url_for("categorias_list"))
    conn = get_conn()
    try:
        antigos = None
        if id_categoria:
            antigos = conn.execute(
                "SELECT * FROM categorias WHERE id_categoria=?", (id_categoria,)
            ).fetchone()
            conn.execute("UPDATE categorias SET nome=?, descricao=? WHERE id_categoria=?",
                         (nome, descricao, id_categoria))
            registrar_auditoria(conn, session.get("user_id"), "categorias",
                                int(id_categoria), "UPDATE",
                                dict(antigos) if antigos else None,
                                {"nome": nome, "descricao": descricao}, _client_ip())
        else:
            cur = conn.execute(
                "INSERT INTO categorias (nome, descricao, ativo) VALUES (?,?,1)",
                (nome, descricao))
            registrar_auditoria(conn, session.get("user_id"), "categorias",
                                cur.lastrowid, "INSERT", None,
                                {"nome": nome, "descricao": descricao}, _client_ip())
        conn.commit()
        flash("Categoria salva com sucesso.", "sucesso")
    except Exception as e:
        flash(f"Erro ao salvar categoria: {e}", "erro")
    conn.close()
    return redirect(url_for("categorias_list"))


@app.route("/categorias/<int:id_categoria>/excluir", methods=["POST"])
@perfil_required("Admin")
def categorias_excluir(id_categoria):
    conn = get_conn()
    antigos = conn.execute(
        "SELECT * FROM categorias WHERE id_categoria=?", (id_categoria,)
    ).fetchone()
    em_uso = conn.execute("SELECT COUNT(*) c FROM produtos WHERE id_categoria=?",
                          (id_categoria,)).fetchone()["c"]
    if em_uso:
        conn.execute("UPDATE categorias SET ativo=0 WHERE id_categoria=?", (id_categoria,))
        flash("Categoria em uso por produtos: foi desativada (exclusão lógica).", "info")
    else:
        conn.execute("DELETE FROM categorias WHERE id_categoria=?", (id_categoria,))
        flash("Categoria excluída.", "sucesso")
    registrar_auditoria(conn, session.get("user_id"), "categorias",
                        id_categoria, "DELETE",
                        dict(antigos) if antigos else None, {"ativo": 0 if em_uso else None},
                        _client_ip())
    conn.commit()
    conn.close()
    return redirect(url_for("categorias_list"))


# ---------------------------------------------------------------------------
# Produtos (atualizado: código automático, sem duplicados, 5 decimais,
#             código de segurança para editar, auditoria, reflete estoque)
# ---------------------------------------------------------------------------
@app.route("/produtos")
@login_required
def produtos_list():
    conn = get_conn()
    nome = request.args.get("nome", "").strip()
    categoria_id = request.args.get("categoria_id", type=int)
    codigo = request.args.get("codigo", "").strip()

    sql = """SELECT p.*, c.nome AS categoria_nome, COALESCE(e.saldo_atual,0) AS saldo_atual
              FROM produtos p LEFT JOIN categorias c ON c.id_categoria=p.id_categoria
              LEFT JOIN estoque e ON e.id_produto=p.id_produto
              WHERE p.ativo=1"""
    params = []
    if nome:
        sql += " AND p.nome LIKE ?"
        params.append(f"%{nome}%")
    if codigo:
        sql += " AND p.codigo LIKE ?"
        params.append(f"%{codigo}%")
    if categoria_id:
        sql += " AND p.id_categoria=?"
        params.append(categoria_id)
    sql += " ORDER BY p.nome"

    produtos = conn.execute(sql, params).fetchall()
    categorias = conn.execute("SELECT * FROM categorias WHERE ativo=1 ORDER BY nome").fetchall()
    conn.close()
    return render_template("produtos.html", produtos=produtos, categorias=categorias,
                           filtros={"nome": nome, "categoria_id": categoria_id, "codigo": codigo},
                           situacao=services.situacao_estoque)


@app.route("/produtos/novo")
@perfil_required("Admin", "Gerente")
def produtos_novo():
    if "_sid" not in session:
        session["_sid"] = str(uuid4())
    conn = get_conn()
    sessao_id = session["_sid"]
    codigo_provisorio = services.reservar_codigo_provisorio(conn, sessao_id)
    categorias = conn.execute("SELECT * FROM categorias WHERE ativo=1 ORDER BY nome").fetchall()
    conn.close()
    return render_template("produto_form.html", produto=None, categorias=categorias,
                           codigo_provisorio=codigo_provisorio, sessao_id=sessao_id,
                           modo="novo", necessita_codigo_seguranca=False)


@app.route("/api/produtos/codigo-provisorio")
@login_required
def api_codigo_provisorio():
    """Gera e reserva um novo código provisório (chamado via JS ao digitar o nome)."""
    if "_sid" not in session:
        session["_sid"] = str(uuid4())
    sessao_id = session["_sid"]
    conn = get_conn()
    codigo = services.reservar_codigo_provisorio(conn, sessao_id)
    conn.close()
    return jsonify({"codigo": codigo, "sessao_id": sessao_id})


@app.route("/produtos/<int:id_produto>/editar")
@perfil_required("Admin", "Gerente")
def produtos_editar(id_produto):
    conn = get_conn()
    produto = conn.execute("SELECT * FROM produtos WHERE id_produto=?", (id_produto,)).fetchone()
    categorias = conn.execute("SELECT * FROM categorias WHERE ativo=1 ORDER BY nome").fetchall()
    conn.close()
    if not produto:
        abort(404)
    codigo_seg = get_config("codigo_alteracao_produto", "")
    return render_template("produto_form.html", produto=produto, categorias=categorias,
                           modo="editar", necessita_codigo_seguranca=bool(codigo_seg))


@app.route("/produtos/salvar", methods=["POST"])
@perfil_required("Admin", "Gerente")
def produtos_salvar():
    f = request.form
    conn = get_conn()
    try:
        id_produto = f.get("id_produto")
        sessao_id = f.get("sessao_id") or session.get("_sid", "")
        modo = "editar" if id_produto else "novo"

        # Segurança: para EDITAR, exige código se Admin tiver definido um
        if modo == "editar":
            # Verifica se o código de segurança é exigido
            codigo_seg_config = get_config("codigo_alteracao_produto", "")
            if codigo_seg_config:
                codigo_seg_forn = f.get("codigo_seguranca", "")
                if not services.validar_codigo_alteracao_produto(codigo_seg_forn):
                    flash("Código de segurança inválido para alterar produto.", "erro")
                    conn.close()
                    return redirect(url_for("produtos_list"))

        # Nome do produto
        nome = f.get("nome", "").strip()
        if not nome:
            flash("Informe o nome do produto.", "erro")
            conn.close()
            return redirect(url_for("produtos_list"))

        # Duplicado de nome
        if services.produto_nome_existe(conn, nome,
                                        id_produto_excluir=int(id_produto) if id_produto else None):
            flash("Já existe um produto ativo com este nome (nomes duplicados não são permitidos).", "erro")
            conn.close()
            return redirect(url_for("produtos_list"))

        # Código
        if modo == "novo":
            codigo = (f.get("codigo", "") or "").strip()
            if not codigo:
                codigo = services.gerar_codigo_produto(conn)
            services.usar_codigo_provisorio(conn, sessao_id, codigo)
        else:
            codigo = f.get("codigo", "").strip()
            if not codigo:
                flash("Código do produto ausente.", "erro")
                conn.close()
                return redirect(url_for("produtos_list"))

        # Converte valores com 5 casas decimais (teto)
        def parse_ceil(v):
            if v is None or v == '':
                return 0.0
            try:
                v_str = str(v).strip()
                if ',' in v_str and '.' in v_str:
                    v_str = v_str.replace('.', '').replace(',', '.')
                elif ',' in v_str and '.' not in v_str:
                    v_str = v_str.replace(',', '.')
                return services.ceil5(float(v_str))
            except Exception:
                return 0.0

        unidade_val = f.get("unidade") or "Unidade"
        qtd_por_unidade_raw = int(f.get("qtd_por_unidade") or 1)
        if unidade_val == "Unidade":
            qtd_por_unidade_raw = 1

        dados = dict(
            codigo=codigo, nome=nome,
            id_categoria=f.get("id_categoria", type=int) or f.get("id_categoria"),
            unidade=unidade_val,
            qtd_por_unidade=qtd_por_unidade_raw,
            preco_custo=parse_ceil(f.get("preco_custo")),
            preco_venda=parse_ceil(f.get("preco_venda")),
            estoque_minimo=int(float(f.get("estoque_minimo") or 0)),
            estoque_maximo=(int(float(f.get("estoque_maximo"))) if f.get("estoque_maximo") else None),
            validade=f.get("validade") or None,
            fornecedor=f.get("fornecedor", "").strip(),
            observacoes=f.get("observacoes", "").strip(),
        )

        antigos = None
        if modo == "editar":
            antigos = dict(conn.execute(
                "SELECT * FROM produtos WHERE id_produto=?", (id_produto,)
            ).fetchone())
            conn.execute(
                """UPDATE produtos SET codigo=?, nome=?, id_categoria=?, unidade=?, qtd_por_unidade=?,
                   preco_custo=?, preco_venda=?, estoque_minimo=?, estoque_maximo=?, validade=?,
                   fornecedor=?, observacoes=? WHERE id_produto=?""",
                (dados["codigo"], dados["nome"], dados["id_categoria"], dados["unidade"],
                 dados["qtd_por_unidade"], dados["preco_custo"], dados["preco_venda"],
                 dados["estoque_minimo"], dados["estoque_maximo"], dados["validade"],
                 dados["fornecedor"], dados["observacoes"], id_produto),
            )
            alterados = services.atualizar_produto_refletir_estoque(
                conn, int(id_produto), antigos, dados)
            registrar_auditoria(conn, session.get("user_id"), "produtos",
                                int(id_produto), "UPDATE",
                                {**antigos, "campos_alterados": alterados} if antigos else None,
                                {**dados, "campos_alterados": alterados},
                                _client_ip())
            flash("Produto atualizado com sucesso (alterações refletidas no estoque).", "sucesso")
        else:
            cur = conn.execute(
                """INSERT INTO produtos (codigo, nome, id_categoria, unidade, qtd_por_unidade,
                   preco_custo, preco_venda, estoque_minimo, estoque_maximo, validade, fornecedor,
                   observacoes, ativo, data_cadastro) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1,?)""",
                (dados["codigo"], dados["nome"], dados["id_categoria"], dados["unidade"],
                 dados["qtd_por_unidade"], dados["preco_custo"], dados["preco_venda"],
                 dados["estoque_minimo"], dados["estoque_maximo"], dados["validade"],
                 dados["fornecedor"], dados["observacoes"],
                 datetime.now().isoformat(timespec="seconds")),
            )
            conn.execute(
                "INSERT INTO estoque (id_produto, saldo_atual, ultima_atualizacao) VALUES (?,0,?)",
                (cur.lastrowid, datetime.now().isoformat(timespec="seconds")))
            registrar_auditoria(conn, session.get("user_id"), "produtos",
                                cur.lastrowid, "INSERT", None, dados, _client_ip())
            flash("Produto cadastrado com sucesso.", "sucesso")
        conn.commit()
    except Exception as e:
        flash(f"Erro ao salvar produto: {e}", "erro")
    conn.close()
    return redirect(url_for("produtos_list"))


@app.route("/produtos/cancelar", methods=["POST"])
@perfil_required("Admin", "Gerente")
def produtos_cancelar():
    """Libera o código provisório da sessão (usuário cancelou o formulário)."""
    sessao_id = request.form.get("sessao_id") or session.get("_sid", "")
    codigo = request.form.get("codigo") or None
    conn = get_conn()
    services.liberar_codigo_provisorio(conn, sessao_id, codigo)
    conn.close()
    return redirect(url_for("produtos_list"))


@app.route("/produtos/<int:id_produto>/excluir", methods=["POST"])
@perfil_required("Admin")
def produtos_excluir(id_produto):
    conn = get_conn()
    antigos = conn.execute(
        "SELECT * FROM produtos WHERE id_produto=?", (id_produto,)
    ).fetchone()
    tem_mov = conn.execute("SELECT COUNT(*) c FROM movimentos WHERE id_produto=?",
                           (id_produto,)).fetchone()["c"]
    if tem_mov:
        conn.execute("UPDATE produtos SET ativo=0 WHERE id_produto=?", (id_produto,))
        flash("Produto possui movimentações: foi desativado (exclusão lógica).", "info")
    else:
        conn.execute("DELETE FROM estoque WHERE id_produto=?", (id_produto,))
        conn.execute("DELETE FROM produtos WHERE id_produto=?", (id_produto,))
        flash("Produto excluído.", "sucesso")
    registrar_auditoria(conn, session.get("user_id"), "produtos",
                        id_produto, "DELETE",
                        dict(antigos) if antigos else None,
                        {"ativo": 0 if tem_mov else None},
                        _client_ip())
    conn.commit()
    conn.close()
    return redirect(url_for("produtos_list"))


@app.route("/api/produtos/buscar")
@login_required
def api_produtos_buscar():
    termo = request.args.get("q", "").strip()
    conn = get_conn()
    rows = conn.execute(
        """SELECT p.id_produto, p.codigo, p.nome, p.unidade, p.qtd_por_unidade,
                  p.preco_custo, p.preco_venda, p.fornecedor, COALESCE(e.saldo_atual,0) saldo_atual
           FROM produtos p LEFT JOIN estoque e ON e.id_produto=p.id_produto
           WHERE p.ativo=1 AND (p.nome LIKE ? OR p.codigo LIKE ?) LIMIT 15""",
        (f"%{termo}%", f"%{termo}%"),
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


# ---------------------------------------------------------------------------
# Inventário físico (atualizado)
# ---------------------------------------------------------------------------
@app.route("/estoque/inventario", methods=["GET", "POST"])
@login_required
def estoque_inventario():
    conn = get_conn()
    if request.method == "POST":
        acao = request.form.get("acao_apos", "guardar")
        exportar = request.form.get("exportar_pdf", "0") == "1"

        inventarios_inseridos = []
        invalid_entries = []
        for key, value in request.form.items():
            if not key.startswith("contagem_"):
                continue
            id_produto = int(key.split("_", 1)[1])
            try:
                contagem = float(value or 0)
            except ValueError:
                continue
            # enforce integer counts for Unidade products
            prod = conn.execute("SELECT nome, unidade FROM produtos WHERE id_produto=?", (id_produto,)).fetchone()
            if prod and prod["unidade"] == "Unidade" and not float(contagem).is_integer():
                invalid_entries.append(prod["nome"] if prod and prod["nome"] else str(id_produto))
                continue
            saldo_registrado = conn.execute(
                "SELECT COALESCE(saldo_atual,0) AS saldo FROM estoque WHERE id_produto=?",
                (id_produto,),
            ).fetchone()
            saldo_registrado = saldo_registrado["saldo"] if saldo_registrado else 0
            diferenca = services.round5(contagem - saldo_registrado)

            # Se já tem inventário exportado, marca como "alterado após export"
            anterior = conn.execute(
                "SELECT MAX(id_inventario) AS ult FROM inventarios WHERE id_produto=? AND exportado=1",
                (id_produto,),
            ).fetchone()
            valor_anterior = None
            if anterior and anterior["ult"]:
                ult = conn.execute(
                    "SELECT contagem_fisica FROM inventarios WHERE id_inventario=?",
                    (anterior["ult"],),
                ).fetchone()
                if ult and abs(ult["contagem_fisica"] - contagem) > 1e-9:
                    valor_anterior = ult["contagem_fisica"]

            cur = conn.execute(
                "INSERT INTO inventarios (id_produto, contagem_fisica, saldo_registrado, diferenca, data_registro, exportado, valor_anterior) VALUES (?,?,?,?,?,?,?)",
                (id_produto, contagem, saldo_registrado, diferenca,
                 datetime.now().isoformat(timespec="seconds"),
                 1 if exportar else 0, valor_anterior),
            )
            inventarios_inseridos.append(cur.lastrowid)
        conn.commit()

        if exportar and inventarios_inseridos:
            # Auto-exporta PDF após a comparação
            linhas_inventario = conn.execute(
                """SELECT p.codigo, p.nome, i.saldo_registrado, i.contagem_fisica, i.diferenca, i.valor_anterior
                   FROM inventarios i JOIN produtos p ON p.id_produto=i.id_produto
                   WHERE i.id_inventario IN (%s) ORDER BY p.nome"""
                % ",".join("?" * len(inventarios_inseridos)),
                inventarios_inseridos,
            ).fetchall()
            conn.close()
            colunas = ["Código", "Produto", "Saldo Regist.", "Contagem Fís.", "Diferença", "Alterado"]
            linhas = []
            for r in linhas_inventario:
                dif = r["diferenca"]
                alt = ""
                if r["valor_anterior"] is not None:
                    delta = services.round5(r["contagem_fisica"] - r["valor_anterior"])
                    alt = f"(antes: {r['valor_anterior']} → Δ {delta:+})"
                linhas.append([
                    r["codigo"], r["nome"],
                    f"{r['saldo_registrado']:.5f}", f"{r['contagem_fisica']:.5f}",
                    f"{dif:+.5f}", alt,
                ])
            sub = f"Total de {len(linhas)} produtos contados em {datetime.now().strftime('%d/%m/%Y %H:%M')}"
            buf = reportmod.gerar_pdf("Relatório de Inventário Físico", colunas, linhas, subtitulo=sub)
            resp = make_response(buf.getvalue())
            resp.headers["Content-Type"] = "application/pdf"
            resp.headers["Content-Disposition"] = (
                f"attachment; filename=inventario_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")
            return resp
        flash("Contagem de inventário registrada com sucesso.", "sucesso")
        conn.close()
        return redirect(url_for("estoque_inventario"))

    # GET: a tela já envia os saldos, mas na VIEW eles ficam mascarados (via CSS + JS)
    # até o utilizador terminar a contagem (ao submeter).
    produtos_rows = conn.execute(
        """SELECT p.id_produto, p.codigo, p.nome, p.unidade, p.qtd_por_unidade,
                  COALESCE(e.saldo_atual,0) AS saldo_atual
           FROM produtos p LEFT JOIN estoque e ON e.id_produto=p.id_produto
           WHERE p.ativo=1 ORDER BY p.nome"""
    ).fetchall()

    produtos = []
    pos_export = set()
    for p in produtos_rows:
        pd = dict(p)
        # latest exported inventario -> valor_anterior
        ult = conn.execute(
            "SELECT valor_anterior FROM inventarios WHERE id_produto=? AND exportado=1 ORDER BY id_inventario DESC LIMIT 1",
            (pd["id_produto"],),
        ).fetchone()
        pd["valor_anterior"] = ult["valor_anterior"] if ult and "valor_anterior" in ult.keys() else None
        tem = conn.execute(
            "SELECT 1 FROM inventarios WHERE id_produto=? AND exportado=1 LIMIT 1",
            (pd["id_produto"],),
        ).fetchone()
        if tem:
            pos_export.add(pd["id_produto"])
        produtos.append(pd)
    conn.close()
    return render_template("inventario.html", produtos=produtos,
                           ids_exportados=pos_export)


# ---------------------------------------------------------------------------
# Movimentações (Entrada e Saída)  + exportações
# ---------------------------------------------------------------------------
@app.route("/movimentos")
@login_required
def movimentos_list():
    conn = get_conn()
    tipo = request.args.get("tipo", "")
    categoria_id = request.args.get("categoria_id", type=int)
    data_ini = request.args.get("data_ini", "")
    data_fim = request.args.get("data_fim", "")
    exportar = request.args.get("exportar", "")

    sql = """SELECT m.*, p.nome AS produto_nome, p.codigo AS produto_codigo,
                    u.nome AS usuario_nome, c.nome AS categoria_nome
              FROM movimentos m JOIN produtos p ON p.id_produto=m.id_produto
              LEFT JOIN usuarios u ON u.id_usuario=m.id_usuario
              LEFT JOIN categorias c ON c.id_categoria=p.id_categoria WHERE 1=1"""
    params = []
    if tipo in ("Entrada", "Saida"):
        sql += " AND m.tipo=?"; params.append(tipo)
    if categoria_id:
        sql += " AND p.id_categoria=?"; params.append(categoria_id)
    if data_ini:
        sql += " AND m.data_hora >= ?"; params.append(data_ini + " 00:00:00")
    if data_fim:
        sql += " AND m.data_hora <= ?"; params.append(data_fim + " 23:59:59")
    sql += " ORDER BY m.data_hora DESC LIMIT 500"
    movimentos = conn.execute(sql, params).fetchall()
    categorias = conn.execute("SELECT * FROM categorias WHERE ativo=1 ORDER BY nome").fetchall()

    if exportar in ("pdf", "excel"):
        colunas = ["Data/Hora", "Tipo", "Código", "Produto", "Categoria",
                   "Qtd. Orig.", "Unid.", "Qtd. Base", "Preço Unit.", "Total",
                   "Lucro", "Usuário", "Fornecedor/Cliente"]
        linhas = []
        for m in movimentos:
            linhas.append([
                m["data_hora"], m["tipo"], m["produto_codigo"], m["produto_nome"],
                m["categoria_nome"] or "—",
                m["quantidade_original"], m["unidade_original"], m["quantidade"],
                f"{services.round5(m['preco_unitario']):.5f}",
                f"{services.round5(m['valor_total']):.5f}",
                f"{services.round5(m['lucro']):.5f}",
                m["usuario_nome"] or "—",
                m["fornecedor"] or m["cliente"] or "—",
            ])
        sub = f"Filtros: tipo={tipo or 'Todos'}"
        conn.close()
        if exportar == "pdf":
            buf = reportmod.gerar_pdf("Relatório de Movimentações", colunas, linhas, subtitulo=sub)
            return send_file(buf, mimetype="application/pdf", as_attachment=True,
                             download_name=f"movimentacoes_{datetime.now():%Y%m%d_%H%M%S}.pdf")
        else:
            buf = reportmod.gerar_excel("Relatório de Movimentações", colunas, linhas)
            return send_file(buf, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             as_attachment=True,
                             download_name=f"movimentacoes_{datetime.now():%Y%m%d_%H%M%S}.xlsx")

    conn.close()
    return render_template("movimentos.html", movimentos=movimentos, tipo=tipo,
                           categorias=categorias,
                           filtros={"categoria_id": categoria_id,
                                    "data_ini": data_ini, "data_fim": data_fim})


@app.route("/movimentos/exportar/<formato>")
@login_required
def movimentos_exportar(formato):
    """Atalho de exportação (compatibilidade)."""
    if formato not in ("pdf", "excel"):
        abort(404)
    from flask import request as req2
    args = dict(req2.args)
    args["exportar"] = formato
    return movimentos_list()


@app.route("/movimentos/entrada", methods=["GET", "POST"])
@perfil_required("Admin", "Gerente", "Operador")
def movimento_entrada():
    conn = get_conn()
    if request.method == "POST":
        id_produto = request.form.get("id_produto", type=int)
        if not id_produto or not services.validar_produto_cadastrado(conn, id_produto):
            flash("Selecione um produto cadastrado e ativo antes de registrar a entrada.", "erro")
            conn.close()
            return redirect(url_for("movimento_entrada"))
        try:
            quantidade_val = float(request.form["quantidade"])
            unidade_val = request.form["unidade_original"]
            # Enforce integer quantities for Unidade
            if unidade_val == "Unidade" and not float(quantidade_val).is_integer():
                flash("Quantidade inválida: produtos com unidade 'Unidade' devem ser números inteiros.", "erro")
                conn.close()
                return redirect(url_for("movimento_entrada"))
            services.registrar_entrada(
                conn,
                id_produto=id_produto,
                quantidade_original=quantidade_val,
                unidade_original=unidade_val,
                preco_unitario=float(request.form["preco_unitario"]),
                id_usuario=session["user_id"],
                nota_fiscal=request.form.get("nota_fiscal") or None,
                fornecedor=request.form.get("fornecedor") or None,
                observacoes=request.form.get("observacoes") or None,
                ip_address=_client_ip(),
            )
            flash("Entrada registrada com sucesso.", "sucesso")
            conn.close()
            return redirect(url_for("movimento_entrada"))
        except services.RegraNegocioError as e:
            flash(str(e), "erro")
        except Exception as e:
            flash(f"Erro ao registrar entrada: {e}", "erro")
    produtos = conn.execute("SELECT * FROM produtos WHERE ativo=1 ORDER BY nome").fetchall()
    conn.close()
    return render_template("movimento_form.html", tipo="Entrada", produtos=produtos)


@app.route("/movimentos/saida", methods=["GET", "POST"])
@perfil_required("Admin", "Gerente", "Operador")
def movimento_saida():
    conn = get_conn()
    if request.method == "POST":
        id_produto = request.form.get("id_produto", type=int)
        if not id_produto or not services.validar_produto_cadastrado(conn, id_produto):
            flash("Selecione um produto cadastrado e ativo antes de registrar a saída.", "erro")
            conn.close()
            return redirect(url_for("movimento_saida"))
        try:
            quantidade_val = float(request.form["quantidade"])
            unidade_val = request.form["unidade_original"]
            if unidade_val == "Unidade" and not float(quantidade_val).is_integer():
                flash("Quantidade inválida: produtos com unidade 'Unidade' devem ser números inteiros.", "erro")
                conn.close()
                return redirect(url_for("movimento_saida"))
            resultado = services.registrar_saida(
                conn,
                id_produto=id_produto,
                quantidade_original=quantidade_val,
                unidade_original=unidade_val,
                preco_unitario=float(request.form["preco_unitario"]),
                id_usuario=session["user_id"],
                cliente=request.form.get("cliente") or None,
                forma_pagamento=request.form.get("forma_pagamento") or None,
                observacoes=request.form.get("observacoes") or None,
                ip_address=_client_ip(),
            )
            flash("Saída registrada com sucesso.", "sucesso")
            if resultado["alerta_minimo"]:
                flash("Atenção: o estoque deste produto ficou abaixo do mínimo!", "aviso")
            conn.close()
            return redirect(url_for("movimento_saida"))
        except services.RegraNegocioError as e:
            flash(str(e), "erro")
        except Exception as e:
            flash(f"Erro ao registrar saída: {e}", "erro")
    produtos = conn.execute("SELECT * FROM produtos WHERE ativo=1 ORDER BY nome").fetchall()
    conn.close()
    return render_template("movimento_form.html", tipo="Saida", produtos=produtos)


# ---------------------------------------------------------------------------
# Estoque atual (com exportação PDF/Excel)
# ---------------------------------------------------------------------------
@app.route("/estoque")
@login_required
def estoque_list():
    conn = get_conn()
    categoria_id = request.args.get("categoria_id", type=int)
    situacao_filtro = request.args.get("situacao", "")
    exportar = request.args.get("exportar", "")

    sql = """SELECT p.*, c.nome AS categoria_nome, COALESCE(e.saldo_atual,0) AS saldo_atual
              FROM produtos p LEFT JOIN categorias c ON c.id_categoria=p.id_categoria
              LEFT JOIN estoque e ON e.id_produto=p.id_produto WHERE p.ativo=1"""
    params = []
    if categoria_id:
        sql += " AND p.id_categoria=?"; params.append(categoria_id)
    sql += " ORDER BY p.nome"
    produtos_raw = conn.execute(sql, params).fetchall()

    linhas_processadas = []
    for p in produtos_raw:
        sit = services.situacao_estoque(p["saldo_atual"], p["estoque_minimo"], p["estoque_maximo"])
        if situacao_filtro and sit != situacao_filtro:
            continue
        linhas_processadas.append({**dict(p), "situacao": sit})

    categorias = conn.execute("SELECT * FROM categorias WHERE ativo=1 ORDER BY nome").fetchall()

    if exportar in ("pdf", "excel"):
        colunas = ["Código", "Produto", "Categoria", "Unid.",
                   "Saldo Atual", "Mínimo", "Máximo", "P. Custo", "P. Venda",
                   "Valor Estoque (Custo)", "Valor Estoque (Venda)", "Situação"]
        linhas = []
        sit_label = {"abaixo_minimo": "Abaixo do mínimo",
                     "acima_maximo": "Acima do máximo", "normal": "Normal"}
        for p in linhas_processadas:
            val_c = services.round5(p["saldo_atual"] * p["preco_custo"])
            val_v = services.round5(p["saldo_atual"] * p["preco_venda"])
            linhas.append([
                p["codigo"], p["nome"], p["categoria_nome"] or "—", p["unidade"],
                f"{services.round5(p['saldo_atual']):.5f}",
                p["estoque_minimo"], p["estoque_maximo"] or "—",
                f"{services.round5(p['preco_custo']):.5f}",
                f"{services.round5(p['preco_venda']):.5f}",
                f"{val_c:.5f}", f"{val_v:.5f}",
                sit_label.get(p["situacao"], p["situacao"]),
            ])
        sub = f"Filtros: categoria={categoria_id or 'Todas'} | situação={situacao_filtro or 'Todas'}"
        conn.close()
        if exportar == "pdf":
            buf = reportmod.gerar_pdf("Relatório de Estoque Atual", colunas, linhas, subtitulo=sub)
            return send_file(buf, mimetype="application/pdf", as_attachment=True,
                             download_name=f"estoque_{datetime.now():%Y%m%d_%H%M%S}.pdf")
        else:
            buf = reportmod.gerar_excel("Relatório de Estoque Atual", colunas, linhas)
            return send_file(buf, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             as_attachment=True,
                             download_name=f"estoque_{datetime.now():%Y%m%d_%H%M%S}.xlsx")

    # compute totals for template (valor_custo_total, valor_venda_total)
    valor_custo_total = 0
    valor_venda_total = 0
    for p in linhas_processadas:
        preco_custo = p.get('preco_custo') or 0
        preco_venda = p.get('preco_venda') or 0
        saldo = p.get('saldo_atual') or 0
        valor_custo_total += float(saldo) * float(preco_custo)
        valor_venda_total += float(saldo) * float(preco_venda)
    conn.close()
    return render_template("estoque.html", produtos=linhas_processadas, categorias=categorias,
                           categoria_id=categoria_id, situacao_filtro=situacao_filtro,
                           valor_custo_total=valor_custo_total, valor_venda_total=valor_venda_total)


# ---------------------------------------------------------------------------
# Relatórios existentes (mantém, com cabeçalho empresa automático via reports.py)
# ---------------------------------------------------------------------------
def _consulta_relatorio(conn, tipo_relatorio, args):
    categoria_id = args.get("categoria_id", type=int)
    id_produto = args.get("id_produto", type=int)
    fornecedor = args.get("fornecedor", "").strip()
    tipo_mov = args.get("tipo_mov", "")
    data_ini = args.get("data_ini", "")
    data_fim = args.get("data_fim", "")

    if tipo_relatorio == "estoque_atual":
        sql = """SELECT p.codigo, p.nome, c.nome categoria, COALESCE(e.saldo_atual,0) saldo,
                         p.preco_custo, p.preco_venda, p.estoque_minimo
                  FROM produtos p LEFT JOIN categorias c ON c.id_categoria=p.id_categoria
                  LEFT JOIN estoque e ON e.id_produto=p.id_produto WHERE p.ativo=1"""
        params = []
        if categoria_id:
            sql += " AND p.id_categoria=?"; params.append(categoria_id)
        if id_produto:
            sql += " AND p.id_produto=?"; params.append(id_produto)
        sql += " ORDER BY p.nome"
        rows = conn.execute(sql, params).fetchall()
        colunas = ["Código", "Produto", "Categoria", "Saldo", "Custo (mzn)", "Venda (mzn)", "Situação"]
        linhas = []
        for r in rows:
            sit = services.situacao_estoque(r["saldo"], r["estoque_minimo"], None)
            sit_label = {"abaixo_minimo": "Abaixo do mínimo",
                         "acima_maximo": "Acima do máximo",
                         "normal": "Normal"}[sit]
            linhas.append([r["codigo"], r["nome"], r["categoria"] or "—",
                           f"{services.round5(r['saldo']):.5f}",
                           f"{services.round5(r['preco_custo']):.5f}",
                           f"{services.round5(r['preco_venda']):.5f}", sit_label])
        return "Relatório de Estoque Atual", colunas, linhas

    if tipo_relatorio == "movimentacoes":
        sql = """SELECT m.data_hora, m.tipo, p.nome produto, m.quantidade, m.unidade_original,
                         m.preco_unitario, m.valor_total, COALESCE(m.fornecedor, m.cliente,'') terceiro
                  FROM movimentos m JOIN produtos p ON p.id_produto=m.id_produto
                  LEFT JOIN categorias c ON c.id_categoria=p.id_categoria WHERE 1=1"""
        params = []
        if data_ini:
            sql += " AND m.data_hora >= ?"; params.append(data_ini)
        if data_fim:
            sql += " AND m.data_hora <= ?"; params.append(data_fim + " 23:59:59")
        if categoria_id:
            sql += " AND p.id_categoria=?"; params.append(categoria_id)
        if id_produto:
            sql += " AND p.id_produto=?"; params.append(id_produto)
        if tipo_mov in ("Entrada", "Saida"):
            sql += " AND m.tipo=?"; params.append(tipo_mov)
        if fornecedor:
            sql += " AND m.fornecedor LIKE ?"; params.append(f"%{fornecedor}%")
        sql += " ORDER BY m.data_hora DESC"
        rows = conn.execute(sql, params).fetchall()
        colunas = ["Data/Hora", "Tipo", "Produto", "Qtd.", "Unid.",
                   "Preço Unit.", "Valor Total", "Fornecedor/Cliente"]
        linhas = [[r["data_hora"], r["tipo"], r["produto"],
                   f"{services.round5(r['quantidade']):.5f}", r["unidade_original"],
                   f"{services.round5(r['preco_unitario']):.5f}",
                   f"{services.round5(r['valor_total']):.5f}", r["terceiro"]] for r in rows]
        return "Relatório de Movimentações", colunas, linhas

    if tipo_relatorio == "vendas":
        sql = """SELECT p.nome produto, SUM(m.quantidade) qtd, SUM(m.valor_total) total,
                         SUM(m.lucro) lucro
                  FROM movimentos m JOIN produtos p ON p.id_produto=m.id_produto
                  WHERE m.tipo='Saida'"""
        params = []
        if data_ini:
            sql += " AND m.data_hora >= ?"; params.append(data_ini)
        if data_fim:
            sql += " AND m.data_hora <= ?"; params.append(data_fim + " 23:59:59")
        if categoria_id:
            sql += " AND p.id_categoria=?"; params.append(categoria_id)
        if id_produto:
            sql += " AND p.id_produto=?"; params.append(id_produto)
        sql += " GROUP BY p.id_produto ORDER BY total DESC"
        rows = conn.execute(sql, params).fetchall()
        colunas = ["Produto", "Qtd. Vendida", "Receita Total (mzn)",
                   "Lucro Bruto (mzn)", "Margem (%)"]
        linhas = []
        for r in rows:
            margem = (r["lucro"] / r["total"] * 100) if r["total"] else 0
            linhas.append([r["produto"], f"{services.round5(r['qtd']):.5f}",
                           f"{services.round5(r['total']):.5f}",
                           f"{services.round5(r['lucro']):.5f}", f"{margem:.1f}%"])
        return "Relatório de Vendas", colunas, linhas

    if tipo_relatorio == "estoque_baixo":
        rows = services.produtos_abaixo_minimo(conn)
        colunas = ["Código", "Produto", "Saldo Atual", "Estoque Mínimo", "Déficit"]
        linhas = [[r["codigo"], r["nome"],
                   f"{services.round5(r['saldo_atual']):.5f}",
                   r["estoque_minimo"],
                   f"{services.round5(r['estoque_minimo'] - r['saldo_atual']):.5f}"] for r in rows]
        return "Relatório de Produtos com Estoque Baixo", colunas, linhas

    if tipo_relatorio == "validade":
        rows = services.produtos_proximos_validade(conn)
        colunas = ["Código", "Produto", "Validade", "Saldo Atual", "Situação"]
        linhas = [[r["codigo"], r["nome"], r["validade"],
                   f"{services.round5(r['saldo_atual']):.5f}",
                   "VENCIDO" if r["vencido"] else "Próximo ao vencimento"] for r in rows]
        return "Relatório de Validade", colunas, linhas

    if tipo_relatorio == "precos_venda":
        rows = conn.execute(
            """SELECT p.codigo, p.nome, c.nome categoria, p.preco_custo, p.preco_venda,
                      COALESCE(e.saldo_atual,0) saldo
               FROM produtos p LEFT JOIN categorias c ON c.id_categoria=p.id_categoria
               LEFT JOIN estoque e ON e.id_produto=p.id_produto WHERE p.ativo=1 ORDER BY p.nome"""
        ).fetchall()
        colunas = ["Código", "Produto", "Categoria", "Preço Venda (mzn)", "Saldo Atual"]
        linhas = [[r["codigo"], r["nome"], r["categoria"] or "—",
                   f"{services.round5(r['preco_venda']):.5f}",
                   f"{services.round5(r['saldo']):.5f}"] for r in rows]
        return "Relatório de Preços de Venda", colunas, linhas

    if tipo_relatorio == "lucratividade":
        sql = """SELECT p.nome produto, SUM(m.quantidade) qtd, SUM(m.valor_total) receita,
                         SUM(m.quantidade * p.preco_custo) custo_total, SUM(m.lucro) lucro
                  FROM movimentos m JOIN produtos p ON p.id_produto=m.id_produto
                  WHERE m.tipo='Saida'"""
        params = []
        if data_ini:
            sql += " AND m.data_hora >= ?"; params.append(data_ini)
        if data_fim:
            sql += " AND m.data_hora <= ?"; params.append(data_fim + " 23:59:59")
        sql += " GROUP BY p.id_produto ORDER BY lucro DESC"
        rows = conn.execute(sql, params).fetchall()
        colunas = ["Produto", "Qtd. Vendida", "Receita (mzn)", "Custo (mzn)",
                   "Lucro Bruto (mzn)", "Margem (%)"]
        linhas = []
        for r in rows:
            margem = (r["lucro"] / r["receita"] * 100) if r["receita"] else 0
            linhas.append([r["produto"], f"{services.round5(r['qtd']):.5f}",
                           f"{services.round5(r['receita']):.5f}",
                           f"{services.round5(r['custo_total']):.5f}",
                           f"{services.round5(r['lucro']):.5f}", f"{margem:.1f}%"])
        return "Relatório de Lucratividade por Produto", colunas, linhas

    return "Relatório", [], []


@app.route("/relatorios")
@login_required
def relatorios():
    conn = get_conn()
    tipo_relatorio = request.args.get("tipo", "")
    titulo, colunas, linhas = ("", [], [])
    if tipo_relatorio:
        titulo, colunas, linhas = _consulta_relatorio(conn, tipo_relatorio, request.args)
    categorias = conn.execute("SELECT * FROM categorias WHERE ativo=1 ORDER BY nome").fetchall()
    conn.close()
    return render_template("relatorios.html", tipo_relatorio=tipo_relatorio, titulo=titulo,
                           colunas=colunas, linhas=linhas, categorias=categorias, args=request.args)


@app.route("/relatorios/exportar/<formato>")
@login_required
def relatorios_exportar(formato):
    conn = get_conn()
    tipo_relatorio = request.args.get("tipo", "")
    titulo, colunas, linhas = _consulta_relatorio(conn, tipo_relatorio, request.args)
    conn.close()
    if not colunas:
        flash("Selecione um relatório antes de exportar.", "erro")
        return redirect(url_for("relatorios"))

    if formato == "pdf":
        buf = reportmod.gerar_pdf(titulo, colunas, linhas)
        return send_file(buf, mimetype="application/pdf", as_attachment=True,
                         download_name=f"{tipo_relatorio}.pdf")
    if formato == "excel":
        buf = reportmod.gerar_excel(titulo, colunas, linhas)
        return send_file(buf, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                         as_attachment=True, download_name=f"{tipo_relatorio}.xlsx")
    abort(404)


# ---------------------------------------------------------------------------
# Balancetes (mensal / trimestral / anual) + Extratos de categoria
# ---------------------------------------------------------------------------
@app.route("/balancetes")
@login_required
def balancetes():
    conn = get_conn()
    tipo = request.args.get("tipo", "mensal")
    data_ini = request.args.get("data_ini", "")
    data_fim = request.args.get("data_fim", "")
    id_categoria = request.args.get("categoria_id", type=int)
    id_produto = request.args.get("id_produto", type=int)
    exportar = request.args.get("exportar", "")

    hoje = datetime.now().date()
    if tipo == "mensal" and not data_ini:
        data_ini = hoje.replace(day=1).isoformat()
    elif tipo == "trimestral" and not data_ini:
        q = (hoje.month - 1) // 3
        data_ini = hoje.replace(month=q * 3 + 1, day=1).isoformat()
    elif tipo == "anual" and not data_ini:
        data_ini = hoje.replace(month=1, day=1).isoformat()
    if not data_fim:
        data_fim = hoje.isoformat()

    linhas = []
    totais = {}
    colunas = []
    titulo = ""
    subtitulo = ""
    saldo_acum_final = 0
    entradas_acum_final = 0
    saidas_acum_final = 0

    # Buscar produtos para o filtro
    todos_produtos = conn.execute(
        "SELECT id_produto, codigo, nome FROM produtos WHERE ativo=1 ORDER BY nome"
    ).fetchall()

    if tipo == "extrato_cat":
        if id_categoria:
            linhas_ext, saldo_acum_final, entradas_acum_final, saidas_acum_final = (
                services.calcular_extrato_categoria(conn, id_categoria, data_ini, data_fim)
            )
            linhas = linhas_ext
            cat = conn.execute("SELECT nome FROM categorias WHERE id_categoria=?", (id_categoria,)).fetchone()
            cat_nome = cat["nome"] if cat else "—"
            titulo = f"Extrato de Categoria — {cat_nome}"
            colunas = ["Data/Hora", "Tipo", "Código", "Produto", "Qtd.", "Unid.",
                       "Preço Unit.", "Valor Total", "Saldo Acumulado"]
            subtitulo = (
                f"Período: {data_ini} a {data_fim}  |  "
                f"Total Entradas: {entradas_acum_final:.2f}  |  "
                f"Total Saídas: {saidas_acum_final:.2f}  |  "
                f"Saldo Final: {saldo_acum_final:.2f}"
            )
            totais = {
                "qtd_total": services.round5(sum(r["quantidade"] for r in linhas_ext)),
                "valor_total": services.round5(sum(r["valor_total"] for r in linhas_ext)),
                "saldo_acumulado_final": services.round5(saldo_acum_final),
                "subtotais": {
                    "qtd_entradas": services.round5(sum(r["quantidade"] for r in linhas_ext if r["tipo"] == "Entrada")),
                    "qtd_saidas": services.round5(sum(r["quantidade"] for r in linhas_ext if r["tipo"] == "Saida")),
                    "qtd_saldo": services.round5(saldo_acum_final),
                    "valor_entradas": services.round5(sum(r["valor_total"] for r in linhas_ext if r["tipo"] == "Entrada")),
                    "valor_saidas": services.round5(sum(r["valor_total"] for r in linhas_ext if r["tipo"] == "Saida")),
                    "valor_saldo": services.round5(sum(r["valor_total"] for r in linhas_ext)),
                },
            }
        else:
            linhas = []
            totais = {}
    else:
        periodo_label = {"mensal": "Mensal", "trimestral": "Trimestral", "anual": "Anual"}.get(tipo, "Personalizado")
        titulo = f"Balancete {periodo_label}"
        colunas = ["Código", "Produto", "Categoria",
                   "Saldo Inicial (Qtd)",
                   "Entradas (Qtd)", "Entradas (Valor)",
                   "Saídas (Qtd)", "Saídas (Valor)",
                   "Saldo Final (Qtd)", "Lucro Bruto"]
        linhas, totais = services.calcular_balancete(
            conn, tipo, data_ini, data_fim, id_categoria, id_produto)
        subtitulo = (
            f"Período: {data_ini} a {data_fim}  |  "
            f"Saldos Iniciais: {services.round5(totais.get('saldo_inicial', 0)):.2f}  |  "
            f"Entradas: {services.round5(totais.get('entradas_val', 0)):.2f}  |  "
            f"Saídas: {services.round5(totais.get('saidas_val', 0)):.2f}  |  "
            f"Saldos Finais: {services.round5(totais.get('saldo_final', 0)):.2f}  |  "
            f"Lucro Total: {services.round5(totais.get('lucro', 0)):.2f}"
        )

    categorias = conn.execute("SELECT * FROM categorias WHERE ativo=1 ORDER BY nome").fetchall()

    if exportar in ("pdf", "excel"):
        out_colunas = colunas
        out_linhas = []
        if tipo == "extrato_cat":
            for r in linhas:
                out_linhas.append([
                    r["data_hora"], r["tipo"], r["codigo"], r["produto"],
                    f"{services.round5(r['quantidade']):.2f}", r["unidade"],
                    f"{services.round5(r['preco_unitario']):.2f}",
                    f"{services.round5(r['valor_total']):.2f}",
                    f"{services.round5(r['saldo_acumulado']):.2f}",
                ])
        else:
            for r in linhas:
                out_linhas.append([
                    r["codigo"], r["produto"], r["categoria"],
                    f"{services.round5(r['saldo_inicial']):.2f}",
                    f"{services.round5(r['entradas_qtd']):.2f}",
                    f"{services.round5(r['entradas_val']):.2f}",
                    f"{services.round5(r['saidas_qtd']):.2f}",
                    f"{services.round5(r['saidas_val']):.2f}",
                    f"{services.round5(r['saldo_final']):.2f}",
                    f"{services.round5(r['lucro']):.2f}",
                ])
        conn.close()
        if exportar == "pdf":
            buf = reportmod.gerar_pdf(titulo, out_colunas, out_linhas, subtitulo=subtitulo)
            return send_file(buf, mimetype="application/pdf", as_attachment=True,
                             download_name=f"{tipo}_{datetime.now():%Y%m%d_%H%M%S}.pdf")
        else:
            buf = reportmod.gerar_excel(titulo, out_colunas, out_linhas)
            return send_file(buf, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             as_attachment=True, download_name=f"{tipo}_{datetime.now():%Y%m%d_%H%M%S}.xlsx")

    conn.close()
    return render_template("balancetes.html",
                           tipo=tipo, data_ini=data_ini, data_fim=data_fim,
                           titulo=titulo, colunas=colunas, linhas=linhas,
                           totais=totais, subtitulo=subtitulo,
                           categorias=categorias,
                           todos_produtos=todos_produtos,  # <-- CORREÇÃO: variável adicionada
                           filtros={"categoria_id": id_categoria, "id_produto": id_produto},
                           extrato_sum={"saldo": saldo_acum_final, "entradas": entradas_acum_final, "saidas": saidas_acum_final})


@app.route("/relatorios/precos")
@login_required
def relatorio_precos():
    conn = get_conn()
    exportar = request.args.get("exportar", "")
    colunas, linhas = reportmod.gerar_relatorio_precos(conn)
    if exportar == "pdf":
        buf = reportmod.gerar_pdf("Lista de Preços de Venda", colunas, linhas)
        return send_file(buf, mimetype="application/pdf", as_attachment=True,
                         download_name="precos_venda.pdf")
    elif exportar == "excel":
        buf = reportmod.gerar_excel("Lista de Preços de Venda", colunas, linhas)
        return send_file(buf, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                         as_attachment=True, download_name="precos_venda.xlsx")
    conn.close()
    return render_template("relatorio_precos.html", colunas=colunas, linhas=linhas)


@app.route("/cotacoes")
@login_required
def cotacoes_list():
    conn = get_conn()
    status = request.args.get("status", "")
    sql = "SELECT * FROM cotacoes"
    params = []
    if status:
        sql += " WHERE status=?"
        params.append(status)
    sql += " ORDER BY data_emissao DESC"
    cotacoes = conn.execute(sql, params).fetchall()
    conn.close()
    return render_template("cotacoes.html", cotacoes=cotacoes, status_filtro=status)


@app.route("/cotacoes/nova", methods=["GET", "POST"])
@perfil_required("Admin", "Gerente", "Operador")
def cotacao_nova():
    if request.method == "POST":
        cliente_nome = request.form.get("cliente_nome", "").strip()
        if not cliente_nome:
            flash("Nome do cliente é obrigatório.", "erro")
            return redirect(url_for("cotacao_nova"))
        itens = []
        ids_produto = request.form.getlist("id_produto[]")
        quantidades = request.form.getlist("quantidade[]")
        precos = request.form.getlist("preco_unitario[]")
        descontos = request.form.getlist("desconto[]")
        for i in range(len(ids_produto)):
            if ids_produto[i] and quantidades[i] and precos[i]:
                itens.append({
                    "id_produto": int(ids_produto[i]),
                    "quantidade": int(quantidades[i]),
                    "preco_unitario": float(precos[i]),
                    "desconto_percentual": float(descontos[i] or 0)
                })
        if not itens:
            flash("Adicione pelo menos um item.", "erro")
            return redirect(url_for("cotacao_nova"))
        try:
            conn = get_conn()
            id_cotacao = services.criar_cotacao(
                conn,
                id_usuario=session["user_id"],
                cliente_nome=cliente_nome,
                cliente_email=request.form.get("cliente_email"),
                cliente_telefone=request.form.get("cliente_telefone"),
                data_validade=request.form.get("data_validade"),
                observacoes=request.form.get("observacoes"),
                itens=itens,
            )
            conn.close()
            flash("Cotação criada com sucesso.", "sucesso")
            return redirect(url_for("cotacao_detalhe", id_cotacao=id_cotacao))
        except services.RegraNegocioError as e:
            flash(str(e), "erro")
        except Exception as e:
            flash(f"Erro ao criar cotação: {e}", "erro")
        return redirect(url_for("cotacao_nova"))

    conn = get_conn()
    produtos = conn.execute("SELECT * FROM produtos WHERE ativo=1 ORDER BY nome").fetchall()
    conn.close()
    validade_default = (datetime.now() + timedelta(days=30)).date().isoformat()
    return render_template("cotacao_form.html", produtos=produtos, validade_default=validade_default)


@app.route("/cotacoes/<int:id_cotacao>")
@login_required
def cotacao_detalhe(id_cotacao):
    conn = get_conn()
    cotacao, itens = services.obter_cotacao(conn, id_cotacao)
    conn.close()
    if not cotacao:
        abort(404)
    return render_template("cotacao_detalhe.html", cotacao=cotacao, itens=itens)


@app.route("/cotacoes/<int:id_cotacao>/exportar/<formato>")
@login_required
def cotacao_exportar(id_cotacao, formato):
    conn = get_conn()
    cotacao, itens = services.obter_cotacao(conn, id_cotacao)
    conn.close()
    if not cotacao:
        abort(404)
    if formato == "pdf":
        buf = reportmod.gerar_pdf_cotacao(cotacao, itens)
        return send_file(buf, mimetype="application/pdf", as_attachment=True,
                         download_name=f"cotacao_{cotacao['numero']}.pdf")
    elif formato == "excel":
        colunas = ["Código", "Produto", "Quantidade", "Preço Unit.", "Desc. %", "Subtotal"]
        linhas = []
        for item in itens:
            linhas.append([
                item["codigo"],
                item["produto_nome"],
                int(item["quantidade"]),
                services.arredondar_moeda(item["preco_unitario"]),
                f"{item['desconto_percentual']:.0f}%",
                services.arredondar_moeda(item["valor_total"]),
            ])
        buf = reportmod.gerar_excel(f"Cotação {cotacao['numero']}", colunas, linhas)
        return send_file(buf, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                         as_attachment=True, download_name=f"cotacao_{cotacao['numero']}.xlsx")
    abort(404)


@app.route("/cotacoes/<int:id_cotacao>/aprovar", methods=["POST"])
@perfil_required("Admin", "Gerente")
def cotacao_aprovar(id_cotacao):
    conn = get_conn()
    try:
        services.atualizar_status_cotacao(conn, id_cotacao, "Aprovada", session["user_id"])
        flash("Cotação aprovada.", "sucesso")
    except services.RegraNegocioError as e:
        flash(str(e), "erro")
    conn.close()
    return redirect(url_for("cotacao_detalhe", id_cotacao=id_cotacao))


@app.route("/cotacoes/<int:id_cotacao>/rejeitar", methods=["POST"])
@perfil_required("Admin", "Gerente")
def cotacao_rejeitar(id_cotacao):
    conn = get_conn()
    try:
        services.atualizar_status_cotacao(conn, id_cotacao, "Rejeitada", session["user_id"])
        flash("Cotação rejeitada.", "info")
    except services.RegraNegocioError as e:
        flash(str(e), "erro")
    conn.close()
    return redirect(url_for("cotacao_detalhe", id_cotacao=id_cotacao))


@app.route("/cotacoes/<int:id_cotacao>/converter", methods=["POST"])
@perfil_required("Admin", "Gerente")
def cotacao_converter(id_cotacao):
    conn = get_conn()
    try:
        services.converter_cotacao_em_venda(conn, id_cotacao, session["user_id"])
        flash("Cotação convertida em venda com sucesso.", "sucesso")
    except services.RegraNegocioError as e:
        flash(str(e), "erro")
    conn.close()
    return redirect(url_for("cotacao_detalhe", id_cotacao=id_cotacao))


# ---------------------------------------------------------------------------
# Segurança / perfil do usuário
# ---------------------------------------------------------------------------
@app.route("/perfil/senha", methods=["GET", "POST"])
@login_required
def trocar_senha():
    if request.method == "POST":
        senha_atual = request.form.get("senha_atual", "")
        nova_senha = request.form.get("nova_senha", "")
        confirmar_senha = request.form.get("confirmar_senha", "")

        conn = get_conn()
        usuario = conn.execute("SELECT * FROM usuarios WHERE id_usuario=?",
                               (session["user_id"],)).fetchone()
        if not usuario or not check_password_hash(usuario["senha_hash"], senha_atual):
            flash("A senha atual informada está incorreta.", "erro")
        elif not services.validar_senha(nova_senha):
            flash("A nova senha deve ter no mínimo 8 caracteres, incluir letra, número e símbolo.", "erro")
        elif nova_senha != confirmar_senha:
            flash("A confirmação da nova senha não confere.", "erro")
        else:
            conn.execute("UPDATE usuarios SET senha_hash=? WHERE id_usuario=?",
                         (generate_password_hash(nova_senha), session["user_id"]))
            registrar_auditoria(conn, session["user_id"], "usuarios",
                                session["user_id"], "UPDATE",
                                {"senha": "ALTERADA_PELO_USUARIO"}, None, _client_ip())
            conn.commit()
            flash("Sua senha foi alterada com sucesso.", "sucesso")
        conn.close()
    return render_template("trocar_senha.html")


# ---------------------------------------------------------------------------
# Usuários
# ---------------------------------------------------------------------------
@app.route("/usuarios")
@perfil_required("Admin")
def usuarios_list():
    conn = get_conn()
    usuarios = conn.execute("SELECT * FROM usuarios ORDER BY nome").fetchall()
    conn.close()
    return render_template("usuarios.html", usuarios=usuarios)


@app.route("/usuarios/salvar", methods=["POST"])
@perfil_required("Admin")
def usuarios_salvar():
    f = request.form
    conn = get_conn()
    try:
        id_usuario = f.get("id_usuario")
        senha = f.get("senha", "").strip()
        if id_usuario:
            antigos = dict(conn.execute(
                "SELECT * FROM usuarios WHERE id_usuario=?", (id_usuario,)
            ).fetchone())
            dados_novos = {"nome": f["nome"], "login": f["login"],
                           "perfil": f["perfil"],
                           "email": f.get("email", "").strip() or None,
                           "telefone": f.get("telefone", "").strip() or None}
            if senha:
                if not services.validar_senha(senha):
                    flash("A nova senha deve ter no mínimo 8 caracteres, incluir letra, número e símbolo.", "erro")
                    conn.close()
                    return redirect(url_for("usuarios_list"))
                conn.execute(
                    "UPDATE usuarios SET nome=?, login=?, perfil=?, senha_hash=?, email=?, telefone=? WHERE id_usuario=?",
                    (f["nome"], f["login"], f["perfil"], generate_password_hash(senha),
                     dados_novos["email"], dados_novos["telefone"], id_usuario))
                dados_novos["senha_hash"] = "***"
            else:
                conn.execute(
                    "UPDATE usuarios SET nome=?, login=?, perfil=?, email=?, telefone=? WHERE id_usuario=?",
                    (f["nome"], f["login"], f["perfil"],
                     dados_novos["email"], dados_novos["telefone"], id_usuario))
            registrar_auditoria(conn, session["user_id"], "usuarios",
                                int(id_usuario), "UPDATE", antigos, dados_novos, _client_ip())
            flash("Usuário atualizado.", "sucesso")
        else:
            if not senha or not services.validar_senha(senha):
                flash("Informe uma senha forte para o novo usuário.", "erro")
                conn.close()
                return redirect(url_for("usuarios_list"))
            dados_novos = {"nome": f["nome"], "login": f["login"],
                           "perfil": f["perfil"], "ativo": 1,
                           "email": f.get("email", "").strip() or None,
                           "telefone": f.get("telefone", "").strip() or None}
            cur = conn.execute(
                "INSERT INTO usuarios (nome, login, senha_hash, perfil, ativo, email, telefone) VALUES (?,?,?,?,1,?,?)",
                (f["nome"], f["login"], generate_password_hash(senha), f["perfil"],
                 dados_novos["email"], dados_novos["telefone"]))
            registrar_auditoria(conn, session["user_id"], "usuarios",
                                cur.lastrowid, "INSERT", None, dados_novos, _client_ip())
            flash("Usuário criado.", "sucesso")
        conn.commit()
    except Exception as e:
        flash(f"Erro ao salvar usuário: {e}", "erro")
    conn.close()
    return redirect(url_for("usuarios_list"))


@app.route("/usuarios/<int:id_usuario>/toggle", methods=["POST"])
@perfil_required("Admin")
def usuarios_toggle(id_usuario):
    conn = get_conn()
    if id_usuario == session["user_id"]:
        flash("Você não pode desativar seu próprio usuário.", "erro")
    else:
        antigos = dict(conn.execute(
            "SELECT * FROM usuarios WHERE id_usuario=?", (id_usuario,)
        ).fetchone())
        novo_ativo = 0 if antigos["ativo"] else 1
        conn.execute("UPDATE usuarios SET ativo = ? WHERE id_usuario=?", (novo_ativo, id_usuario,))
        registrar_auditoria(conn, session["user_id"], "usuarios",
                            id_usuario, "UPDATE", antigos, {"ativo": novo_ativo}, _client_ip())
        conn.commit()
        flash("Status do usuário atualizado.", "sucesso")
    conn.close()
    return redirect(url_for("usuarios_list"))


@app.route("/usuarios/<int:id_usuario>/excluir", methods=["POST"])
@perfil_required("Admin")
def usuarios_excluir(id_usuario):
    conn = get_conn()
    if id_usuario == session["user_id"]:
        flash("Você não pode excluir seu próprio usuário.", "erro")
    else:
        usuario = conn.execute("SELECT * FROM usuarios WHERE id_usuario=?", (id_usuario,)).fetchone()
        if not usuario:
            flash("Usuário não encontrado.", "erro")
        else:
            movimentos = conn.execute(
                "SELECT COUNT(*) c FROM movimentos WHERE id_usuario=?", (id_usuario,)
            ).fetchone()["c"]
            antigos = dict(usuario)
            if movimentos:
                conn.execute("UPDATE usuarios SET ativo=0 WHERE id_usuario=?", (id_usuario,))
                registrar_auditoria(conn, session["user_id"], "usuarios",
                                    id_usuario, "DELETE", antigos,
                                    {"ativo": 0, "motivo": "historico_movimentacoes"},
                                    _client_ip())
                flash("Usuário com histórico foi desativado em vez de excluído.", "info")
            else:
                conn.execute("DELETE FROM usuarios WHERE id_usuario=?", (id_usuario,))
                registrar_auditoria(conn, session["user_id"], "usuarios",
                                    id_usuario, "DELETE", antigos, None, _client_ip())
                flash("Usuário excluído com sucesso.", "sucesso")
            conn.commit()
    conn.close()
    return redirect(url_for("usuarios_list"))


# ---------------------------------------------------------------------------
# Configurações 
# ---------------------------------------------------------------------------
@app.route("/configuracoes", methods=["GET", "POST"])
@perfil_required("Admin")
def configuracoes():
    if request.method == "POST":
        set_config("metodo_custeio", request.form.get("metodo_custeio", "media_ponderada"))
        set_config("dias_alerta_validade", request.form.get("dias_alerta_validade", "7"))
        set_config("margem_lucro_desejada", request.form.get("margem_lucro_desejada", "30"))
        set_config("permitir_estoque_negativo",
                   "1" if request.form.get("permitir_estoque_negativo") else "0")
        set_config("nome_empresa", (request.form.get("nome_empresa") or "").strip())
        set_config("moeda", (request.form.get("moeda") or "MZN").strip())
        set_config("estoque_minimo_padrao", request.form.get("estoque_minimo_padrao", "0"))
        set_config("backup_automatico",
                   "1" if request.form.get("backup_automatico") else "0")

        set_config("morada_empresa", (request.form.get("morada_empresa") or "").strip())
        set_config("nuit_empresa", (request.form.get("nuit_empresa") or "").strip())
        set_config("contacto_empresa", (request.form.get("contacto_empresa") or "").strip())
        set_config("email_empresa", (request.form.get("email_empresa") or "").strip())

        # Código de segurança para alterar produto
        codigo_seg_novo = (request.form.get("codigo_alteracao_produto") or "").strip()
        if codigo_seg_novo:
            set_config("codigo_alteracao_produto", codigo_seg_novo)
        elif request.form.get("limpar_codigo_alteracao") == "1":
            set_config("codigo_alteracao_produto", "")

        # Upload do logo
        logo_arquivo = request.files.get("logo_arquivo")
        if logo_arquivo and logo_arquivo.filename:
            try:
                ext = logo_arquivo.filename.rsplit(".", 1)[-1].lower()
                if ext not in ("png", "jpg", "jpeg", "gif", "bmp", "webp"):
                    raise ValueError("Formato de imagem não suportado")
                os.makedirs(os.path.join(get_base_dir(), "static", "img"), exist_ok=True)
                nome_seguro = f"logo_empresa.{ext}"
                caminho = os.path.join(get_base_dir(), "static", "img", nome_seguro)
                logo_arquivo.save(caminho)
                set_config("logo_empresa", nome_seguro)
            except Exception as e:
                flash(f"Erro ao carregar logo: {e}", "erro")
        if request.form.get("remover_logo") == "1":
            set_config("logo_empresa", "")

        flash("Configurações salvas com sucesso.", "sucesso")
        return redirect(url_for("configuracoes"))

    config = {
        "metodo_custeio": get_config("metodo_custeio", "media_ponderada"),
        "dias_alerta_validade": get_config("dias_alerta_validade", "7"),
        "margem_lucro_desejada": get_config("margem_lucro_desejada", "30"),
        "permitir_estoque_negativo": get_config("permitir_estoque_negativo", "0"),
        "nome_empresa": get_config("nome_empresa", ""),
        "moeda": get_config("moeda", "MZN"),
        "estoque_minimo_padrao": get_config("estoque_minimo_padrao", "0"),
        "backup_automatico": get_config("backup_automatico", "0"),
        "morada_empresa": get_config("morada_empresa", ""),
        "nuit_empresa": get_config("nuit_empresa", ""),
        "contacto_empresa": get_config("contacto_empresa", ""),
        "email_empresa": get_config("email_empresa", ""),
        "logo_empresa": get_config("logo_empresa", ""),
        "codigo_alteracao_produto": get_config("codigo_alteracao_produto", ""),
        "primeira_instalacao": get_config("primeira_instalacao", "1"),
    }
    return render_template("configuracoes.html", config=config)


@app.route("/configuracoes/backup")
@perfil_required("Admin")
def configuracoes_backup():
    backup_dir = os.path.join(get_base_dir(), "backups")
    os.makedirs(backup_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(backup_dir, f"estoque_backup_{ts}.db")
    shutil.copy2(DB_PATH, backup_path)
    return send_file(backup_path, as_attachment=True, download_name=os.path.basename(backup_path))


@app.route("/configuracoes/restaurar", methods=["POST"])
@perfil_required("Admin")
def configuracoes_restaurar():
    if "arquivo_backup" not in request.files:
        flash("Selecione um arquivo de backup para restaurar.", "erro")
        return redirect(url_for("configuracoes"))

    arquivo = request.files["arquivo_backup"]
    if arquivo.filename == "":
        flash("Selecione um arquivo de backup para restaurar.", "erro")
        return redirect(url_for("configuracoes"))

    nome_seguro = secure_filename(arquivo.filename)
    pasta_upload = os.path.join(get_base_dir(), "backups")
    os.makedirs(pasta_upload, exist_ok=True)
    caminho_temp = os.path.join(pasta_upload,
                                 f"upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{nome_seguro}")
    arquivo.save(caminho_temp)

    tabelas_esperadas = {"produtos", "usuarios", "movimentos", "estoque",
                         "categorias", "configuracoes"}
    try:
        conn = sqlite3.connect(caminho_temp)
        tabelas_existentes = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        conn.close()
        if not tabelas_esperadas.issubset(tabelas_existentes):
            raise sqlite3.Error("Schema incompatível com o SGE.")
        shutil.copy2(caminho_temp, DB_PATH)
        flash("Backup restaurado com sucesso.", "sucesso")
    except sqlite3.Error:
        flash("O arquivo selecionado não é um backup válido do sistema.", "erro")
    finally:
        if os.path.exists(caminho_temp):
            os.remove(caminho_temp)

    return redirect(url_for("configuracoes"))


# ---------------------------------------------------------------------------
# Inicialização
# ---------------------------------------------------------------------------
def abrir_navegador():
    webbrowser.open(f"http://127.0.0.1:{APP_PORT}/")

if __name__ == "__main__":
    init_db()
    if "--no-browser" not in sys.argv:
        threading.Timer(1.2, abrir_navegador).start()
    try:
        app.run(host="127.0.0.1", port=APP_PORT, debug=False, threaded=True)
    finally:
        _encerrar_tudo()