# -*- coding: utf-8 -*-
"""Aplicação principal (app.py) — pontos de entrada e rotas Flask."""
 
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
    """Gera uma chave de sessão na primeira execução e reutiliza nas seguintes."""
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


# ---------------------------------------------------------------------------
# Detecção de modo empacotado (PyInstaller)
# ---------------------------------------------------------------------------
def _resource_path(relative_path):
    """Retorna o caminho absoluto do recurso, tanto em dev como empacotado."""
    if getattr(sys, "frozen", False):
        # PyInstaller cria uma pasta temporária em sys._MEIPASS
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, relative_path)

app = Flask(
    __name__,
    template_folder=_resource_path("templates"),
    static_folder=_resource_path("static"),
    static_url_path="/static",
)
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
        if ',' in v_str and '.' in v_str:
            v_str = v_str.replace('.', '').replace(',', '.')
        elif ',' in v_str and '.' not in v_str:
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
    """Callback de encerramento: fecha conexões pendentes e força saída.

    No Windows (empacotado com PyInstaller) usamos os._exit(0) porque
    os.kill(pid, SIGTERM) não funciona de forma fiável nesse SO.
    """
    global _shutdown_requested
    if _shutdown_requested:
        return
    _shutdown_requested = True
    try:
        logging.shutdown()
    except Exception:
        pass
    try:
        if getattr(sys, "frozen", False):
            # Empacotado: força saída imediata (Windows-friendly)
            os._exit(0)
        else:
            # Em desenvolvimento: encerra o processo normalmente
            sys.exit(0)
    except Exception:
        try:
            os._exit(0)
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
        "hoje": datetime.now().date().isoformat(),
    }


def _formatar_numero_pt(value, decimals=2):
    """Formata um número no padrão pt-PT/pt-MZ: '.' para milhar, ',' para decimal."""
    try:
        decimals = int(decimals)
    except (TypeError, ValueError):
        decimals = 2
    try:
        val = float(value)
    except (TypeError, ValueError):
        val = 0.0
    # Guarda contra NaN/Inf (evita ValueError no format do Python)
    if not math.isfinite(val):
        val = 0.0
    formatted = f"{val:,.{decimals}f}"
    parts = formatted.split('.')
    integer_part = parts[0].replace(',', '.')
    decimal_part = parts[1] if len(parts) > 1 else '0' * decimals
    return f"{integer_part},{decimal_part}" if decimals else integer_part


@app.template_filter("format_num")
def format_num(value, decimals=2):
    """Formata números genéricos no padrão pt: 1.234,56."""
    return _formatar_numero_pt(value, decimals)


@app.template_filter("format_int")
def format_int(value):
    """Formata números como inteiros com separador de milhar (ex: 1.000)."""
    try:
        val = int(float(value))
    except (TypeError, ValueError):
        val = 0
    return _formatar_numero_pt(val, 0)


@app.template_filter("format_currency")
def format_currency(value, decimals=2):
    """Formata valores monetários (ex: 1.000,00)."""
    return _formatar_numero_pt(value, decimals)

@app.template_filter("format_qtd")
def format_qtd(value, unidade=None):
    """Formata quantidade: 3 decimais apenas para 'kg', senão inteiro."""
    unidade_norm = (str(unidade) if unidade is not None else "").strip().lower()
    if unidade_norm == "kg":
        return _formatar_numero_pt(value, 3)
    try:
        return _formatar_numero_pt(round(float(value or 0)), 0)
    except (TypeError, ValueError):
        return "0"


# ---------------------------------------------------------------------------
# Login / Logout / Recuperação de senha
# ---------------------------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
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
    """Passo 1: pede o login e gera token."""
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
    """Passo 2: valida o token e permite definir nova senha."""
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
@perfil_required("Admin", "Gerente")
def shutdown_app():
    """Endpoint chamado pelo botão 'Sair e encerrar'.

    Em modo janela (pywebview), fecha a janela — o `webview.start()`
    retorna e o `_encerrar_tudo()` corre em seguida no `finally`.

    Em modo browser (fallback), mata o processo directamente.
    """
    janela = app.config.get("_janela_webview")
    if janela is not None:
        try:
            # Fecha a janela do pywebview
            janela.destroy()
        except Exception:
            pass
        return jsonify({"ok": True})

    # Fallback (modo browser)
    t = threading.Timer(1.5, _encerrar_tudo)
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
# Produtos
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
    produto = conn.execute("SELECT * FROM produtos WHERE id_produto=? AND ativo=1", (id_produto,)).fetchone()
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

        # Categoria — tratamento robusto
        id_cat_raw = f.get("id_categoria", "").strip()
        if not id_cat_raw:
            flash("Selecione uma categoria válida.", "erro")
            conn.close()
            return redirect(url_for("produtos_list"))
        try:
            id_categoria = int(id_cat_raw)
        except (TypeError, ValueError):
            flash("Categoria inválida.", "erro")
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

        # Calcula estoque_maximo ANTES de montar o dict
        # (não é possível ter instruções dentro de dict(...))
        em_raw = (f.get("estoque_maximo") or "").strip()
        estoque_maximo = None
        if em_raw:
            try:
                _em = int(float(em_raw))
                estoque_maximo = _em if _em > 0 else None
            except (TypeError, ValueError):
                estoque_maximo = None

        dados = dict(
            codigo=codigo, nome=nome,
            id_categoria=id_categoria,
            unidade=unidade_val,
            qtd_por_unidade=qtd_por_unidade_raw,
            preco_custo=parse_ceil(f.get("preco_custo")),
            preco_venda=parse_ceil(f.get("preco_venda")),
            estoque_minimo=int(float(f.get("estoque_minimo") or 0)),
            estoque_maximo=estoque_maximo,
            validade=f.get("validade") or None,
            fornecedor=f.get("fornecedor", "").strip(),
            observacoes=f.get("observacoes", "").strip(),
        )

        antigos = None
        if modo == "editar":
            row = conn.execute(
                "SELECT * FROM produtos WHERE id_produto=?", (id_produto,)
            ).fetchone()
            if not row:
                flash("Produto não encontrado para atualização.", "erro")
                conn.close()
                return redirect(url_for("produtos_list"))
            antigos = dict(row)
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
    """Exclui o produto e TODOS os dados relacionados (cascata)."""
    conn = get_conn()
    try:
        antigos = conn.execute(
            "SELECT * FROM produtos WHERE id_produto=?", (id_produto,)
        ).fetchone()
        if not antigos:
            flash("Produto não encontrado.", "erro")
            conn.close()
            return redirect(url_for("produtos_list"))

        # Contadores para auditoria
        movimentos_removidos = conn.execute(
            "SELECT COUNT(*) c FROM movimentos WHERE id_produto=?", (id_produto,)
        ).fetchone()["c"]
        inventarios_removidos = conn.execute(
            "SELECT COUNT(*) c FROM inventarios WHERE id_produto=?", (id_produto,)
        ).fetchone()["c"]
        itens_cotacao_removidos = conn.execute(
            "SELECT COUNT(*) c FROM itens_cotacao WHERE id_produto=?", (id_produto,)
        ).fetchone()["c"]

        # Exclusão em cascata — ordem: tabelas dependentes primeiro
        conn.execute("DELETE FROM itens_cotacao WHERE id_produto=?", (id_produto,))
        conn.execute("DELETE FROM inventarios WHERE id_produto=?", (id_produto,))
        conn.execute("DELETE FROM movimentos WHERE id_produto=?", (id_produto,))
        conn.execute("DELETE FROM estoque WHERE id_produto=?", (id_produto,))
        conn.execute("DELETE FROM codigos_provisorios WHERE codigo=?", (antigos["codigo"],))
        conn.execute("DELETE FROM produtos WHERE id_produto=?", (id_produto,))

        registrar_auditoria(
            conn, session.get("user_id"), "produtos",
            id_produto, "DELETE",
            dict(antigos),
            {
                "acao": "EXCLUSAO_CASCATA",
                "movimentos_removidos": movimentos_removidos,
                "inventarios_removidos": inventarios_removidos,
                "itens_cotacao_removidos": itens_cotacao_removidos,
            },
            _client_ip()
        )
        conn.commit()
        flash(
            f"Produto '{antigos['nome']}' excluído permanentemente. "
            f"({movimentos_removidos} movimento(s), "
            f"{inventarios_removidos} inventário(s), "
            f"{itens_cotacao_removidos} item(ns) de cotação removidos).",
            "sucesso"
        )
    except Exception as e:
        conn.rollback()
        flash(f"Erro ao excluir produto: {e}", "erro")
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
# Inventário físico
# ---------------------------------------------------------------------------
@app.route("/estoque/inventario", methods=["GET", "POST"])
@login_required
def estoque_inventario():
    conn = get_conn()
    if request.method == "POST":
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

                # Feedback ao utilizador
        if invalid_entries:
            flash("As seguintes contagens foram ignoradas (produtos 'Unidade' "
                  "exigem valores inteiros): " + ", ".join(invalid_entries), "erro")

        # Exportação PDF (bloco independente de invalid_entries)
        if exportar and inventarios_inseridos:
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
                dif = int(r["diferenca"] or 0)
                alt = ""
                if r["valor_anterior"] is not None:
                    delta = int(r["contagem_fisica"] or 0) - int(r["valor_anterior"] or 0)
                    alt = f"(antes: {r['valor_anterior']} → Δ {delta:+d})"
                linhas.append([
                    r["codigo"], r["nome"],
                    int(r["saldo_registrado"] or 0),
                    int(r["contagem_fisica"] or 0),
                    dif,
                    alt,
                ])
            sub = f"Total de {len(linhas)} produtos contados em {datetime.now().strftime('%d/%m/%Y %H:%M')}"
            buf = reportmod.gerar_pdf("Relatório de Inventário Físico", colunas, linhas, subtitulo=sub)
            resp = make_response(buf.getvalue())
            resp.headers["Content-Type"] = "application/pdf"
            resp.headers["Content-Disposition"] = (
                f"attachment; filename=inventario_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")
            return resp

        if not invalid_entries:
            flash("Contagem de inventário registrada com sucesso.", "sucesso")
        conn.close()
        return redirect(url_for("estoque_inventario"))
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
# Movimentações
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
        sql += " AND m.data_hora >= ?"; params.append(data_ini + "T00:00:00")
    if data_fim:
        sql += " AND m.data_hora <= ?"; params.append(data_fim + "T23:59:59")
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
    args = dict(request.args)
    args["exportar"] = formato
    return redirect(url_for("movimentos_list", **args))

datetime.now()
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
            if unidade_val == "Unidade" and not float(quantidade_val).is_integer():
                flash("Quantidade inválida: produtos com unidade 'Unidade' devem ser números inteiros.", "erro")
                conn.close()
                return redirect(url_for("movimento_entrada"))
            data_str = request.form.get("data_entrada") or ""
            data_hora = (data_str + "T" + datetime.now().strftime("%H:%M:%S")) if data_str else None
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
                data_hora=data_hora,
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
        # Campos gerais da venda
        cliente = request.form.get("cliente") or None
        forma_pagamento = request.form.get("forma_pagamento") or None
        observacoes = request.form.get("observacoes") or None

        # Listas de itens (venda múltipla)
        ids_produto = request.form.getlist("id_produto[]")
        quantidades = request.form.getlist("quantidade[]")
        unidades = request.form.getlist("unidade_original[]")
        precos = request.form.getlist("preco_unitario[]")

        # Validação básica
        if not ids_produto or not any(ids_produto):
            flash("Adicione pelo menos um produto à venda.", "erro")
            conn.close()
            return redirect(url_for("movimento_saida"))

        erros = []
        sucessos = 0
        alertas_minimo = []

        for i, id_prod_str in enumerate(ids_produto):
            data_str = request.form.get("data_venda") or ""
            data_hora_venda = (data_str + "T" + datetime.now().strftime("%H:%M:%S")) if data_str else None
            if not id_prod_str:
                continue
            try:
                id_produto = int(id_prod_str)
                quantidade = float(quantidades[i] or 0)
                unidade = unidades[i] if i < len(unidades) else "Unidade"
                preco = float(precos[i] or 0)

                if quantidade <= 0:
                    erros.append(f"Item {i+1}: quantidade deve ser maior que zero.")
                    continue

                # Validar produto
                if not services.validar_produto_cadastrado(conn, id_produto):
                    erros.append(f"Item {i+1}: produto inválido ou inativo.")
                    continue

                # Validar inteiros para Unidade
                if unidade == "Unidade" and not quantidade.is_integer():
                    erros.append(f"Item {i+1}: produtos com unidade 'Unidade' devem ter quantidade inteira.")
                    continue

                resultado = services.registrar_saida(
                    conn,
                    id_produto=id_produto,
                    quantidade_original=quantidade,
                    unidade_original=unidade,
                    preco_unitario=preco,
                    id_usuario=session["user_id"],
                    cliente=cliente,
                    forma_pagamento=forma_pagamento,
                    observacoes=observacoes,
                    data_hora=data_hora_venda,
                    ip_address=_client_ip(),
                )
                sucessos += 1
                if resultado["alerta_minimo"]:
                    alertas_minimo.append(id_produto)

            except services.RegraNegocioError as e:
                erros.append(f"Item {i+1}: {str(e)}")
            except Exception as e:
                erros.append(f"Item {i+1}: {str(e)}")

        if erros:
            for e in erros:
                flash(e, "erro")
        if sucessos:
            flash(f"{sucessos} saída(s) registrada(s) com sucesso.", "sucesso")
        if alertas_minimo:
            flash("Atenção: alguns produtos ficaram abaixo do estoque mínimo.", "aviso")

        conn.close()
        return redirect(url_for("movimento_saida"))

    produtos = conn.execute("SELECT * FROM produtos WHERE ativo=1 ORDER BY nome").fetchall()
    conn.close()
    return render_template("movimento_form.html", tipo="Saida", produtos=produtos)

# ---------------------------------------------------------------------------
# Estoque atual
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
            val_c = float(p["saldo_atual"] or 0) * float(p["preco_custo"] or 0)
            val_v = float(p["saldo_atual"] or 0) * float(p["preco_venda"] or 0)
            linhas.append([
                p["codigo"], p["nome"], p["categoria_nome"] or "—", p["unidade"],
                int(p["saldo_atual"] or 0),
                int(p["estoque_minimo"] or 0),
                int(p["estoque_maximo"]) if p["estoque_maximo"] else None,
                float(p["preco_custo"] or 0),
                float(p["preco_venda"] or 0),
                val_c,
                val_v,
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

    valor_custo_total = 0
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
# Relatórios
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
            # Passa valores numéricos crus — reports.py formata (2 casas para valores)
            linhas.append([r["codigo"], r["nome"], r["categoria"] or "—",
                           int(r["saldo"] or 0),
                           float(r["preco_custo"] or 0),
                           float(r["preco_venda"] or 0), sit_label])
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
            sql += " AND m.data_hora <= ?"; params.append(data_fim + "T23:59:59")
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
                   int(r["quantidade"] or 0), r["unidade_original"],
                   float(r["preco_unitario"] or 0),
                   float(r["valor_total"] or 0), r["terceiro"]] for r in rows]
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
            sql += " AND m.data_hora <= ?"; params.append(data_fim + "T23:59:59")
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
            total = float(r["total"] or 0)
            lucro = float(r["lucro"] or 0)
            margem = (lucro / total * 100) if total else 0
            linhas.append([r["produto"], int(r["qtd"] or 0),
                           total, lucro,
                           f"{margem:.1f}%"])
        return "Relatório de Vendas", colunas, linhas

    if tipo_relatorio == "estoque_baixo":
        rows = services.produtos_abaixo_minimo(conn)
        colunas = ["Código", "Produto", "Saldo Atual", "Estoque Mínimo", "Déficit"]
        linhas = [[r["codigo"], r["nome"],
                   int(r["saldo_atual"] or 0),
                   int(r["estoque_minimo"] or 0),
                   int((r["estoque_minimo"] or 0) - (r["saldo_atual"] or 0))] for r in rows]
        return "Relatório de Produtos com Estoque Baixo", colunas, linhas

    if tipo_relatorio == "validade":
        rows = services.produtos_proximos_validade(conn)
        colunas = ["Código", "Produto", "Validade", "Saldo Atual", "Situação"]
        linhas = [[r["codigo"], r["nome"], r["validade"],
                   int(r["saldo_atual"] or 0),
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
                   float(r["preco_venda"] or 0),
                   int(r["saldo"] or 0)] for r in rows]
        return "Relatório de Preços de Venda", colunas, linhas

    if tipo_relatorio == "lucratividade":
        # CORRIGIDO: custo histórico real = valor_total - lucro (não usar preco_custo atual!)
        sql = """SELECT p.nome produto, SUM(m.quantidade) qtd, SUM(m.valor_total) receita,
                         SUM(m.valor_total) - SUM(m.lucro) AS custo_total,
                         SUM(m.lucro) lucro
                  FROM movimentos m JOIN produtos p ON p.id_produto=m.id_produto
                  WHERE m.tipo='Saida'"""
        params = []
        if data_ini:
            sql += " AND m.data_hora >= ?"; params.append(data_ini)
        if data_fim:
            sql += " AND m.data_hora <= ?"; params.append(data_fim + "T23:59:59")
        sql += " GROUP BY p.id_produto ORDER BY lucro DESC"
        rows = conn.execute(sql, params).fetchall()
        colunas = ["Produto", "Qtd. Vendida", "Receita (mzn)", "Custo (mzn)",
                   "Lucro Bruto (mzn)", "Margem (%)"]
        linhas = []
        for r in rows:
            receita = float(r["receita"] or 0)
            lucro = float(r["lucro"] or 0)
            custo = float(r["custo_total"] or 0)
            margem = (lucro / receita * 100) if receita else 0
            linhas.append([r["produto"], int(r["qtd"] or 0),
                           receita, custo, lucro, f"{margem:.1f}%"])
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
# Balancetes
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

    # --- Estado inicial (SEMPRE definido, para evitar UnboundLocalError) ---
    linhas = []
    totais = {}
    colunas = []
    titulo = ""
    subtitulo = ""
    saldo_acum_final = 0
    entradas_acum_final = 0
    saidas_acum_final = 0
    categoria_nome = ""
    extrato_produto_info = None
    extrato_produto_resumo = None

    todos_produtos = conn.execute(
        "SELECT id_produto, codigo, nome FROM produtos WHERE ativo=1 ORDER BY nome"
    ).fetchall()

    # ======================================================================
    # BLOCO 1: Determinar o tipo e construir linhas/totais/colunas/título
    # ======================================================================
    if tipo == "extrato_cat":
        # -------- Extrato por categoria --------
        if id_categoria:
            linhas_ext, saldo_acum_final, entradas_acum_final, saidas_acum_final = (
                services.calcular_extrato_categoria(conn, id_categoria, data_ini, data_fim)
            )
            linhas = linhas_ext
            cat = conn.execute(
                "SELECT nome FROM categorias WHERE id_categoria=?", (id_categoria,)
            ).fetchone()
            categoria_nome = cat["nome"] if cat else "—"
            titulo = f"Extrato de Categoria — {categoria_nome}"
            colunas = ["Data/Hora", "Tipo", "Código", "Produto", "Qtd.", "Unid.",
                       "Preço Unit.", "Valor Total", "Saldo Acumulado"]
            subtitulo = (
                f"Período: {data_ini} a {data_fim}  |  "
                f"Total Entradas: {entradas_acum_final:.2f}  |  "
                f"Total Saídas: {saidas_acum_final:.2f}  |  "
                f"Saldo Final: {saldo_acum_final:.2f}"
            )
            totais = {
                "subtotais": {
                    "qtd_entradas": services.round5(
                        sum(r["quantidade"] for r in linhas_ext if r["tipo"] == "Entrada")),
                    "qtd_saidas": services.round5(
                        sum(r["quantidade"] for r in linhas_ext if r["tipo"] == "Saida")),
                    "qtd_saldo": services.round5(saldo_acum_final),
                    "valor_entradas": services.round5(
                        sum(r["valor_total"] for r in linhas_ext if r["tipo"] == "Entrada")),
                    "valor_saidas": services.round5(
                        sum(r["valor_total"] for r in linhas_ext if r["tipo"] == "Saida")),
                    "valor_saldo": services.round5(
                        sum(r["valor_total"] for r in linhas_ext)),
                },
            }

    elif tipo == "extrato_prod":
        # -------- Extrato por produto --------
        if id_produto:
            produto_ext, linhas_ext, resumo_ext = services.calcular_extrato_produto(
                conn, id_produto, data_ini, data_fim
            )
            if produto_ext:
                linhas = linhas_ext
                extrato_produto_info = produto_ext
                extrato_produto_resumo = resumo_ext
                titulo = f"Extrato de Produto — {produto_ext['nome']}"
                # 11 colunas (bate com o template e com a exportação)
                colunas = ["Data/Hora", "Tipo", "Doc.",
                           "Qtd. Orig.", "Unid.", "Qtd. Base",
                           "Preço Unit.", "Valor Total", "Lucro",
                           "Saldo Acum. (un.)", "Forn./Cli."]
                subtitulo = (
                    f"Período: {data_ini} a {data_fim}  |  "
                    f"Comprado: {resumo_ext['qtd_comprada']} {produto_ext['unidade']} "
                    f"({services.round5(resumo_ext['valor_comprado']):.2f})  |  "
                    f"Vendido: {resumo_ext['qtd_vendida']} {produto_ext['unidade']} "
                    f"({services.round5(resumo_ext['valor_vendido']):.2f})  |  "
                    f"Saldo Final: {resumo_ext['saldo_final']} (unidade base)"
                )
                totais = {
                    "subtotais": {
                        "qtd_entradas": resumo_ext["qtd_comprada"],
                        "qtd_saidas": resumo_ext["qtd_vendida"],
                        "qtd_saldo": resumo_ext["saldo_final"],
                        "valor_entradas": resumo_ext["valor_comprado"],
                        "valor_saidas": resumo_ext["valor_vendido"],
                        "valor_saldo": resumo_ext["lucro_periodo"],
                    },
                }

    elif tipo == "extrato_geral":
        # -------- Extrato geral (todos os produtos) --------
        titulo = "Extrato Geral de Produtos"
        colunas = ["Código", "Produto", "Categoria",
                   "Saldo Inicial (Qtd)",
                   "Entradas (Qtd)", "Entradas (Valor)",
                   "Saídas (Qtd)", "Saídas (Valor)",
                   "Saldo Final (Qtd)", "Lucro Bruto"]
        linhas, totais = services.calcular_balancete(
            conn, "extrato_geral", data_ini, data_fim, id_categoria, id_produto)
        subtitulo = (
            f"Período: {data_ini} a {data_fim}  |  "
            f"{len(linhas)} produto(s)  |  "
            f"Saldo Inicial Total: {services.round5(totais.get('saldo_inicial_qtd', 0))}  |  "
            f"Entradas: {services.round5(totais.get('entradas_val', 0)):.2f}  |  "
            f"Saídas: {services.round5(totais.get('saidas_val', 0)):.2f}  |  "
            f"Saldo Final Total: {services.round5(totais.get('saldo_final_qtd', 0))}  |  "
            f"Lucro Total: {services.round5(totais.get('lucro', 0)):.2f}"
        )

    else:
        # -------- Balancete regular (mensal/trimestral/anual) --------
        periodo_label = {"mensal": "Mensal",
                         "trimestral": "Trimestral",
                         "anual": "Anual"}.get(tipo, "Personalizado")
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

    # ======================================================================
    # BLOCO 2: Categorias (SEMPRE — fora de qualquer if)
    # ======================================================================
    categorias = conn.execute(
        "SELECT * FROM categorias WHERE ativo=1 ORDER BY nome"
    ).fetchall()

    # ======================================================================
    # BLOCO 3: Exportação PDF/Excel
    # ======================================================================
    if exportar in ("pdf", "excel"):
        out_colunas = colunas
        out_linhas = []
        if tipo == "extrato_cat":
            for r in linhas:
                out_linhas.append([
                    r["data_hora"], r["tipo"], r["codigo"], r["produto"],
                    r["quantidade"], r["unidade"],
                    r["preco_unitario"], r["valor_total"], r["saldo_acumulado"],
                ])
        elif tipo == "extrato_prod":
            def _fmt_qtd_local(v, un):
                if (un or "").lower() == "kg":
                    return f"{float(v or 0):.3f}".replace(".", ",")
                return f"{int(round(float(v or 0)))}"
            for r in linhas:
                out_linhas.append([
                    r["data_hora"], r["tipo"], r["documento"],
                    _fmt_qtd_local(r["quantidade_original"], r["unidade_original"]),
                    r["unidade_original"],
                    _fmt_qtd_local(r["quantidade_base"], r["unidade_original"]),
                    r["preco_unitario"], r["valor_total"],
                    r["lucro"],
                    _fmt_qtd_local(r["saldo_acumulado"], r["unidade_original"]),
                    r["terceiro"],
                ])
        else:
            for r in linhas:
                out_linhas.append([
                    r["codigo"], r["produto"], r["categoria"],
                    r["saldo_inicial"], r["entradas_qtd"], r["entradas_val"],
                    r["saidas_qtd"], r["saidas_val"], r["saldo_final"], r["lucro"],
                ])
        conn.close()
        if exportar == "pdf":
            buf = reportmod.gerar_pdf(titulo, out_colunas, out_linhas, subtitulo=subtitulo)
            return send_file(
                buf, mimetype="application/pdf", as_attachment=True,
                download_name=f"{tipo}_{datetime.now():%Y%m%d_%H%M%S}.pdf"
            )
        else:
            buf = reportmod.gerar_excel(titulo, out_colunas, out_linhas)
            return send_file(
                buf,
                mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                as_attachment=True,
                download_name=f"{tipo}_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
            )

    # ======================================================================
    # BLOCO 4: Render
    # ======================================================================
    conn.close()
    return render_template(
        "balancetes.html",
        tipo=tipo, data_ini=data_ini, data_fim=data_fim,
        titulo=titulo, colunas=colunas, linhas=linhas,
        totais=totais, subtitulo=subtitulo,
        categorias=categorias,
        categoria_nome=categoria_nome,
        todos_produtos=todos_produtos,
        extrato_produto=extrato_produto_info,
        extrato_resumo=extrato_produto_resumo,
        filtros={"categoria_id": id_categoria, "id_produto": id_produto},
        extrato_sum={"saldo": saldo_acum_final,
                     "entradas": entradas_acum_final,
                     "saidas": saidas_acum_final},
    )

@app.route("/balancetes/imprimir-branco")
@login_required
def balancetes_imprimir_branco():
    """Folha de contagem física: nome do produto + qtd + data em branco."""
    conn = get_conn()
    id_categoria = request.args.get("categoria_id", type=int)
    id_produto = request.args.get("id_produto", type=int)

    sql = """SELECT p.codigo, p.nome, p.unidade,
                    c.nome AS categoria_nome
             FROM produtos p
             LEFT JOIN categorias c ON c.id_categoria=p.id_categoria
             WHERE p.ativo=1"""
    params = []
    if id_categoria:
        sql += " AND p.id_categoria=?"
        params.append(id_categoria)
    if id_produto:
        sql += " AND p.id_produto=?"
        params.append(id_produto)
    sql += " ORDER BY p.nome"

    produtos = conn.execute(sql, params).fetchall()
    conn.close()

    # Folha simples: 3 colunas — Produto | Quantidade | Data
    colunas = ["Produto", "Quantidade Contada", "Data"]

    linhas = []
    for p in produtos:
        # Nome + código/unidade numa única célula para caber mais na folha
        rotulo = f"{p['nome']}  ({p['codigo']})"
        linhas.append([rotulo, "", ""])

    sub = (f"Contagem física manual  |  {len(linhas)} produto(s)  |  "
           f"Emitido em {datetime.now()}")

    buf = reportmod.gerar_pdf(
        "Folha de Contagem — Preenchimento Manual",
        colunas,
        linhas,
        subtitulo=sub,
        landscape_mode=False,  # retrato é suficiente para 3 colunas
    )
    return send_file(
        buf, mimetype="application/pdf", as_attachment=True,
        download_name=f"folha_contagem_{datetime.now()}.pdf",
    )

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


# ---------------------------------------------------------------------------
# Cotações
# ---------------------------------------------------------------------------
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

@app.route("/cotacoes/<int:id_cotacao>/editar", methods=["GET"])
@perfil_required("Admin", "Gerente", "Operador")
def cotacao_editar(id_cotacao):
    """Mostra o formulário pré-preenchido para edição de uma cotação Aberta."""
    conn = get_conn()
    res = services.obter_cotacao(conn, id_cotacao)
    produtos = conn.execute(
        "SELECT * FROM produtos WHERE ativo=1 ORDER BY nome"
    ).fetchall()
    conn.close()
    if not res:
        abort(404)
    cotacao, itens = res
    if cotacao["status"] != "Aberta":
        flash("Apenas cotações com status 'Aberta' podem ser editadas.", "erro")
        return redirect(url_for("cotacao_detalhe", id_cotacao=id_cotacao))
    return render_template(
        "cotacao_form.html",
        produtos=produtos,
        cotacao=cotacao,
        itens=itens,
        validade_default=cotacao["data_validade"][:10],
    )


@app.route("/cotacoes/<int:id_cotacao>/atualizar", methods=["POST"])
@perfil_required("Admin", "Gerente", "Operador")
def cotacao_atualizar(id_cotacao):
    """Persiste alterações numa cotação existente (só se ainda estiver Aberta)."""
    cliente_nome = request.form.get("cliente_nome", "").strip()
    if not cliente_nome:
        flash("Nome do cliente é obrigatório.", "erro")
        return redirect(url_for("cotacao_editar", id_cotacao=id_cotacao))

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
                "desconto_percentual": float(descontos[i] or 0),
            })
    if not itens:
        flash("Adicione pelo menos um item.", "erro")
        return redirect(url_for("cotacao_editar", id_cotacao=id_cotacao))

    conn = get_conn()
    try:
        services.atualizar_cotacao(
            conn,
            id_cotacao=id_cotacao,
            id_usuario=session["user_id"],
            cliente_nome=cliente_nome,
            cliente_email=request.form.get("cliente_email") or None,
            cliente_telefone=request.form.get("cliente_telefone") or None,
            data_validade=request.form.get("data_validade") or None,
            observacoes=request.form.get("observacoes") or None,
            itens=itens,
        )
        flash("Cotação atualizada com sucesso.", "sucesso")
        conn.close()
        return redirect(url_for("cotacao_detalhe", id_cotacao=id_cotacao))
    except services.RegraNegocioError as e:
        flash(str(e), "erro")
    except Exception as e:
        flash(f"Erro ao atualizar cotação: {e}", "erro")
    conn.close()
    return redirect(url_for("cotacao_editar", id_cotacao=id_cotacao))

@app.route("/cotacoes/<int:id_cotacao>")
@login_required
def cotacao_detalhe(id_cotacao):
    conn = get_conn()
    res = services.obter_cotacao(conn, id_cotacao)
    conn.close()
    if not res:
        abort(404)
    cotacao, itens = res
    return render_template("cotacao_detalhe.html", cotacao=cotacao, itens=itens)


@app.route("/cotacoes/<int:id_cotacao>/exportar/<formato>")
@login_required
def cotacao_exportar(id_cotacao, formato):
    conn = get_conn()
    res = services.obter_cotacao(conn, id_cotacao)
    conn.close()
    if not res:
        abort(404)
    cotacao, itens = res
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


@app.route("/cotacoes/<int:id_cotacao>/faturar", methods=["POST"])
@perfil_required("Admin", "Gerente", "Operador")
def cotacao_faturar(id_cotacao):
    conn = get_conn()
    try:
        data_venc = request.form.get("data_vencimento") or None
        isento = request.form.get("isento_iva") == "1"
        try:
            taxa = float(request.form.get("taxa_iva") or 0)
        except (TypeError, ValueError):
            taxa = None
        res = services.faturar_cotacao(
            conn, id_cotacao, session["user_id"],
            ip_address=_client_ip(),
            data_vencimento=data_venc,
            isento_iva=isento,
            taxa_iva=taxa,
        )
        flash(f"Fatura {res['numero_fatura']} emitida a partir da cotação.", "sucesso")
        conn.close()
        return redirect(url_for("conta_receber_detalhe", id_conta=res["id_conta"]))
    except services.RegraNegocioError as e:
        flash(str(e), "erro")
    except Exception as e:
        flash(f"Erro: {e}", "erro")
    conn.close()
    return redirect(url_for("cotacao_detalhe", id_cotacao=id_cotacao))

# ---------------------------------------------------------------------------
# Vendas a Crédito / Contas a Receber / Recibos
# ---------------------------------------------------------------------------
@app.route("/vendas/credito", methods=["GET", "POST"])
@perfil_required("Admin", "Gerente", "Operador")
def venda_credito():
    conn = get_conn()
    if request.method == "POST":
        nome_cliente = request.form.get("cliente", "").strip()
        if not nome_cliente:
            flash("Nome do cliente é obrigatório.", "erro")
            conn.close()
            return redirect(url_for("venda_credito"))

        ids_produto = request.form.getlist("id_produto[]")
        quantidades = request.form.getlist("quantidade[]")
        unidades = request.form.getlist("unidade_original[]")
        precos = request.form.getlist("preco_unitario[]")

        itens = []
        for i, id_str in enumerate(ids_produto):
            if not id_str:
                continue
            try:
                itens.append({
                    "id_produto": int(id_str),
                    "quantidade": float(quantidades[i] or 0),
                    "unidade": unidades[i] if i < len(unidades) else "Unidade",
                    "preco_unitario": float(precos[i] or 0),
                })
            except (ValueError, IndexError):
                pass

        if not itens:
            flash("Adicione pelo menos um produto à fatura.", "erro")
            conn.close()
            return redirect(url_for("venda_credito"))

        data_venda = request.form.get("data_venda") or ""
        data_venda_iso = (data_venda + "T" + datetime.now().strftime("%H:%M:%S")) if data_venda else None
        data_venc = request.form.get("data_vencimento") or None

        isento = request.form.get("isento_iva") == "1"
        try:
            taxa = float(request.form.get("taxa_iva") or 0)
        except (TypeError, ValueError):
            taxa = None

        try:
            resultado = services.registrar_venda_credito(
                conn,
                itens=itens,
                id_usuario=session["user_id"],
                nome_cliente=nome_cliente,
                nif_cliente=request.form.get("cliente_nif") or None,
                endereco_cliente=request.form.get("cliente_endereco") or None,
                localidade_cliente=request.form.get("cliente_localidade") or None,
                pais_cliente=request.form.get("cliente_pais") or None,
                email_cliente=request.form.get("cliente_email") or None,
                telefone_cliente=request.form.get("cliente_telefone") or None,
                data_vencimento=data_venc,
                condicao_pagamento=request.form.get("condicao_pagamento") or None,
                isento_iva=isento,
                taxa_iva=taxa,
                observacoes=request.form.get("observacoes") or None,
                data_venda=data_venda_iso,
                ip_address=_client_ip(),
            )
            flash(
                f"Fatura {resultado['numero_fatura']} criada com "
                f"{resultado['n_itens']} produto(s) — total {resultado['valor']:.2f} "
                f"{get_config('moeda','MZN')}.",
                "sucesso"
            )
            conn.close()
            return redirect(url_for("conta_receber_detalhe", id_conta=resultado["id_conta"]))
        except services.RegraNegocioError as e:
            flash(str(e), "erro")
        except Exception as e:
            flash(f"Erro: {e}", "erro")

    produtos = conn.execute("SELECT * FROM produtos WHERE ativo=1 ORDER BY nome").fetchall()
    conn.close()
    return render_template("venda_credito_form.html", produtos=produtos)

@app.route("/contas-receber")
@login_required
def contas_receber_list():
    conn = get_conn()
    status = request.args.get("status", "")
    sql = "SELECT * FROM contas_receber"
    params = []
    if status:
        sql += " WHERE status=?"
        params.append(status)
    sql += " ORDER BY data_emissao DESC"
    contas = conn.execute(sql, params).fetchall()
    conn.close()
    return render_template("contas_receber.html", contas=contas, status_filtro=status)


@app.route("/contas-receber/<int:id_conta>")
@login_required
def conta_receber_detalhe(id_conta):
    conn = get_conn()
    res = services.obter_conta_receber(conn, id_conta)
    conn.close()
    if not res:
        abort(404)
    conta, itens, recibos = res
    return render_template("conta_receber_detalhe.html",
    conta=conta, itens=itens, recibos=recibos)

@app.route("/contas-receber/<int:id_conta>/liquidar", methods=["POST"])
@perfil_required("Admin", "Gerente", "Operador")
def conta_receber_liquidar(id_conta):
    conn = get_conn()
    try:
        valor = float(request.form.get("valor") or 0)
        forma = request.form.get("forma_pagamento") or "Dinheiro"
        data_pg = request.form.get("data_pagamento") or ""
        data_pg_iso = (data_pg + "T" + datetime.now().strftime("%H:%M:%S")) if data_pg else None
        res = services.liquidar_conta(
            conn, id_conta, valor, forma, session["user_id"],
            data_pagamento=data_pg_iso,
            observacoes=request.form.get("observacoes") or None,
            ip_address=_client_ip(),
        )
        flash(f"Recibo {res['numero']} emitido. Saldo restante: {res['novo_saldo']:.2f}.", "sucesso")
        conn.close()
        return redirect(url_for("conta_receber_detalhe", id_conta=id_conta))
    except services.RegraNegocioError as e:
        flash(str(e), "erro")
    except Exception as e:
        flash(f"Erro: {e}", "erro")
    conn.close()
    return redirect(url_for("conta_receber_detalhe", id_conta=id_conta))

@app.route("/contas-receber/<int:id_conta>/eliminar", methods=["POST"])
@perfil_required("Admin", "Gerente")
def conta_receber_eliminar(id_conta):
    conn = get_conn()
    try:
        res = services.cancelar_conta_receber(
            conn, id_conta, session["user_id"], _client_ip()
        )
        flash(
            f"Fatura eliminada. {res['movimentos_revertidos']} movimento(s) revertido(s) "
            f"e o stock foi reposto.",
            "sucesso"
        )
    except services.RegraNegocioError as e:
        flash(str(e), "erro")
    except Exception as e:
        flash(f"Erro: {e}", "erro")
    conn.close()
    return redirect(url_for("contas_receber_list"))


@app.route("/contas-receber/<int:id_conta>/fatura.pdf")
@login_required
def conta_receber_fatura_pdf(id_conta):
    conn = get_conn()
    res = services.obter_conta_receber(conn, id_conta)
    conn.close()
    if not res:
        abort(404)
    conta, itens, _recibos = res
    buf = reportmod.gerar_pdf_fatura(conta, itens=itens)
    nome_arq = (conta.get("numero_fatura") or f"FT-{id_conta:05d}").replace(" ", "_").replace("/", "-")
    return send_file(buf, mimetype="application/pdf", as_attachment=True,
                     download_name=f"{nome_arq}.pdf")

@app.route("/recibos/<int:id_recibo>.pdf")
@login_required
def recibo_pdf(id_recibo):
    conn = get_conn()
    res = services.obter_recibo(conn, id_recibo)
    conn.close()
    if not res:
        abort(404)
    recibo, conta = res
    buf = reportmod.gerar_pdf_recibo(recibo, conta)
    return send_file(buf, mimetype="application/pdf", as_attachment=True,
                     download_name=f"recibo_{recibo['numero']}.pdf")


# ---------------------------------------------------------------------------
# AUDITORIA DE ESTOQUE
# ---------------------------------------------------------------------------
@app.route("/auditorias")
@login_required
def auditorias_list():
    conn = get_conn()
    auditorias = conn.execute(
        """SELECT a.*, u.nome AS responsavel_nome
           FROM auditorias a
           LEFT JOIN usuarios u ON u.id_usuario=a.responsavel_id
           ORDER BY a.data_abertura DESC"""
    ).fetchall()
    conn.close()
    return render_template("auditorias_list.html", auditorias=auditorias)


@app.route("/auditorias/nova", methods=["GET", "POST"])
@perfil_required("Admin", "Gerente")
def auditoria_nova():
    conn = get_conn()
    if request.method == "POST":
        try:
            id_aud = services.abrir_auditoria(
                conn,
                data_inicio=request.form["data_inicio"],
                data_fim=request.form["data_fim"],
                tipo=request.form.get("tipo", "completa"),
                id_categoria=request.form.get("id_categoria", type=int),
                responsavel_id=session["user_id"],
                tolerancia_percentual=request.form.get("tolerancia_percentual", "1"),
                tolerancia_valor_minimo=request.form.get("tolerancia_valor_minimo", "0"),
                observacoes=request.form.get("observacoes"),
                ip_address=_client_ip(),
            )
            flash("Auditoria aberta. Próximo passo: congelar o estoque teórico.", "sucesso")
            conn.close()
            return redirect(url_for("auditoria_detalhe", id_auditoria=id_aud))
        except Exception as e:
            flash(f"Erro: {e}", "erro")
    categorias = conn.execute("SELECT * FROM categorias WHERE ativo=1 ORDER BY nome").fetchall()
    conn.close()
    return render_template("auditoria_form.html", categorias=categorias)


@app.route("/auditorias/<int:id_auditoria>")
@login_required
def auditoria_detalhe(id_auditoria):
    conn = get_conn()
    aud = services.obter_auditoria(conn, id_auditoria)
    if not aud:
        conn.close()
        abort(404)
    produtos = services.produtos_da_auditoria(conn, id_auditoria)
    divergencias = services.divergencias_da_auditoria(conn, id_auditoria)
    contagens = conn.execute(
        """SELECT c.*, p.codigo, p.nome, u.nome AS usuario_nome
           FROM auditoria_contagens c
           JOIN produtos p ON p.id_produto=c.id_produto
           LEFT JOIN usuarios u ON u.id_usuario=c.id_usuario_contador
           WHERE c.id_auditoria=?
           ORDER BY c.data_contagem DESC LIMIT 20""",
        (id_auditoria,),
    ).fetchall()
    conn.close()
    return render_template("auditoria_detalhe.html",
                           aud=aud, produtos=produtos,
                           divergencias=divergencias, contagens=contagens)


@app.route("/auditorias/<int:id_auditoria>/congelar", methods=["POST"])
@perfil_required("Admin", "Gerente")
def auditoria_congelar(id_auditoria):
    conn = get_conn()
    try:
        services.congelar_estoque_teorico(conn, id_auditoria, _client_ip())
        flash("Estoque teórico congelado. Inicie a contagem.", "sucesso")
    except services.RegraNegocioError as e:
        flash(str(e), "erro")
    conn.close()
    return redirect(url_for("auditoria_detalhe", id_auditoria=id_auditoria))


@app.route("/auditorias/<int:id_auditoria>/contar", methods=["POST"])
@perfil_required("Admin", "Gerente", "Operador")
def auditoria_contar(id_auditoria):
    conn = get_conn()
    try:
        id_produto = int(request.form["id_produto"])
        quantidade = float(request.form["quantidade"])
        services.registrar_contagem(
            conn, id_auditoria, id_produto, quantidade,
            id_usuario=session["user_id"],
            local=request.form.get("local"),
            lote=request.form.get("lote"),
            validade=request.form.get("validade"),
            observacao=request.form.get("observacao"),
            contagem_cega=request.form.get("contagem_cega") == "1",
            ip_address=_client_ip(),
        )
        flash("Contagem registada.", "sucesso")
    except services.RegraNegocioError as e:
        flash(str(e), "erro")
    except Exception as e:
        flash(f"Erro: {e}", "erro")
    conn.close()
    return redirect(url_for("auditoria_detalhe", id_auditoria=id_auditoria))


@app.route("/auditorias/<int:id_auditoria>/fechar", methods=["POST"])
@perfil_required("Admin", "Gerente")
def auditoria_fechar(id_auditoria):
    conn = get_conn()
    try:
        res = services.fechar_auditoria(conn, id_auditoria, session["user_id"], _client_ip())
        flash(
            f"Auditoria fechada. {res['ajustes_gerados']} ajuste(s). "
            f"Divergência: {res['div_qtd']} un. / {res['div_valor']:.2f} MZN.",
            "sucesso"
        )
    except services.RegraNegocioError as e:
        flash(str(e), "erro")
    conn.close()
    return redirect(url_for("auditoria_detalhe", id_auditoria=id_auditoria))


@app.route("/auditorias/<int:id_auditoria>/relatorio.pdf")
@login_required
def auditoria_relatorio_pdf(id_auditoria):
    conn = get_conn()
    aud = services.obter_auditoria(conn, id_auditoria)
    if not aud:
        conn.close()
        abort(404)
    divergencias = services.divergencias_da_auditoria(conn, id_auditoria)
    conn.close()

    colunas = ["Código", "Produto", "Categoria", "Unid.",
               "Teórico", "Contado", "Diferença", "Custo Unit.",
               "Diferença Valor", "Estado"]
    linhas = []
    for d in divergencias:
        u = (d["unidade"] or "").lower()
        def fqtd(v):
            return f"{float(v or 0):.3f}".replace(".", ",") if u == "kg" else f"{int(round(float(v or 0)))}"
        linhas.append([
            d["codigo"], d["nome"], d["categoria_nome"] or "—", d["unidade"],
            fqtd(d["estoque_teorico"]),
            fqtd(d["estoque_contado"]),
            fqtd(d["diferenca_qtd"]),
            f"{float(d['custo_unitario'] or 0):.2f}".replace(".", ","),
            f"{float(d['diferenca_valor'] or 0):.2f}".replace(".", ","),
            d["estado"],
        ])

    sub = (f"Período: {aud['data_inicio']} a {aud['data_fim']} | "
           f"Responsável: {aud['responsavel_nome'] or '—'} | "
           f"Estado: {aud['estado']}")
    buf = reportmod.gerar_pdf(
        f"Auditoria de Estoque #{id_auditoria}", colunas, linhas,
        subtitulo=sub, landscape_mode=True)
    return send_file(buf, mimetype="application/pdf", as_attachment=True,
                     download_name=f"auditoria_{id_auditoria}.pdf")


@app.route("/fechos-mensais", methods=["GET", "POST"])
@perfil_required("Admin", "Gerente")
def fechos_mensais_list():
    conn = get_conn()
    if request.method == "POST":
        try:
            ano = int(request.form["ano"])
            mes = int(request.form["mes"])
            sobrescrever = request.form.get("sobrescrever") == "1"
            res = services.gerar_fecho_mensal(
                conn, ano, mes, session["user_id"], _client_ip(),
                sobrescrever=sobrescrever)
            flash(
                f"Fecho {mes:02d}/{ano} gerado: {res['n_itens']} produtos, "
                f"custo total {res['total_custo']:.2f}.",
                "sucesso"
            )
        except services.RegraNegocioError as e:
            flash(str(e), "erro")
        except Exception as e:
            flash(f"Erro: {e}", "erro")
        conn.close()
        return redirect(url_for("fechos_mensais_list"))

    fechos = services.listar_fechos(conn)
    conn.close()
    return render_template("fechos_mensais.html",
                           fechos=fechos,
                           hoje=datetime.now().date().isoformat())

@app.route("/auditorias/divergencia/<int:id_div>/justificar", methods=["POST"])
@perfil_required("Admin", "Gerente")
def auditoria_justificar(id_div):
    conn = get_conn()
    try:
        services.justificar_divergencia(
            conn, id_div,
            motivo=request.form.get("motivo", "").strip() or "Sem motivo",
            id_usuario=session["user_id"],
            observacao=request.form.get("observacao"),
            ip_address=_client_ip(),
        )
        flash("Divergência justificada.", "sucesso")
    except services.RegraNegocioError as e:
        flash(str(e), "erro")
    conn.close()
    return redirect(request.referrer or url_for("auditorias_list"))


@app.route("/auditorias/divergencia/<int:id_div>/recontar", methods=["POST"])
@perfil_required("Admin", "Gerente")
def auditoria_recontar(id_div):
    conn = get_conn()
    try:
        services.solicitar_recontagem(conn, id_div, session["user_id"], _client_ip())
        flash("Recontagem solicitada.", "sucesso")
    except services.RegraNegocioError as e:
        flash(str(e), "erro")
    conn.close()
    return redirect(request.referrer or url_for("auditorias_list"))


@app.route("/auditorias/divergencia/<int:id_div>/aceitar", methods=["POST"])
@perfil_required("Admin", "Gerente")
def auditoria_aceitar(id_div):
    conn = get_conn()
    try:
        services.marcar_aceite(conn, id_div, session["user_id"], _client_ip())
        flash("Divergência marcada como aceite.", "sucesso")
    except services.RegraNegocioError as e:
        flash(str(e), "erro")
    conn.close()
    return redirect(request.referrer or url_for("auditorias_list"))


@app.route("/perdas", methods=["GET", "POST"])
@perfil_required("Admin", "Gerente", "Operador")
def perdas_list():
    conn = get_conn()
    if request.method == "POST":
        try:
            id_produto = int(request.form["id_produto"])
            quantidade = float(request.form["quantidade"])
            motivo = request.form.get("motivo", "Outro")
            data_str = request.form.get("data_perda") or ""
            data_hora = (data_str + "T" + datetime.now().strftime("%H:%M:%S")) if data_str else None
            services.registrar_perda(
                conn, id_produto, quantidade, motivo,
                id_usuario=session["user_id"],
                observacao=request.form.get("observacao"),
                data_hora=data_hora,
                ip_address=_client_ip(),
            )
            flash("Perda registada.", "sucesso")
        except services.RegraNegocioError as e:
            flash(str(e), "erro")
        except Exception as e:
            flash(f"Erro: {e}", "erro")
        conn.close()
        return redirect(url_for("perdas_list"))

    perdas = conn.execute(
        """SELECT m.*, p.codigo, p.nome, p.unidade, u.nome AS usuario_nome
           FROM movimentos m
           JOIN produtos p ON p.id_produto=m.id_produto
           LEFT JOIN usuarios u ON u.id_usuario=m.id_usuario
           WHERE m.subtipo LIKE 'Perda_%'
           ORDER BY m.data_hora DESC LIMIT 300"""
    ).fetchall()
    produtos = conn.execute(
        "SELECT * FROM produtos WHERE ativo=1 ORDER BY nome"
    ).fetchall()
    conn.close()
    return render_template("perdas.html", perdas=perdas, produtos=produtos,
                           hoje=datetime.now().date().isoformat())

@app.route("/fechos-mensais/<int:id_fecho>")
@perfil_required("Admin", "Gerente")
def fecho_detalhe(id_fecho):
    conn = get_conn()
    fecho = conn.execute(
        "SELECT * FROM fechos_mensais WHERE id_fecho=?", (id_fecho,)
    ).fetchone()
    if not fecho:
        conn.close()
        abort(404)
    itens = conn.execute(
        """SELECT i.*, p.codigo, p.nome, p.unidade
           FROM fechos_mensais_itens i
           JOIN produtos p ON p.id_produto=i.id_produto
           WHERE i.id_fecho=?
           ORDER BY p.nome""",
        (id_fecho,),
    ).fetchall()
    conn.close()
    return render_template("fecho_detalhe.html", fecho=fecho, itens=itens)

@app.route("/auditorias/<int:id_auditoria>/relatorios/<tipo>")
@login_required
def auditoria_relatorio(id_auditoria, tipo):
    conn = get_conn()
    aud = services.obter_auditoria(conn, id_auditoria)
    if not aud:
        conn.close()
        abort(404)

    contexto = {"aud": aud, "tipo": tipo, "titulo": "", "colunas": [], "linhas": []}

    if tipo == "resumo":
        dados = services.resumo_executivo(conn, id_auditoria)
        contexto.update(dados or {})
        contexto["titulo"] = f"Resumo Executivo — Auditoria #{id_auditoria}"

    elif tipo == "reconciliacao":
        linhas, tot = services.reconciliacao_periodo(
            conn, aud["data_inicio"], aud["data_fim"],
            aud.get("id_categoria"))
        contexto["linhas"] = linhas
        contexto["totais"] = tot
        contexto["titulo"] = f"Reconciliação — {aud['data_inicio']} a {aud['data_fim']}"

    elif tipo == "abc":
        itens, valor_total = services.curva_abc(conn, id_auditoria)
        contexto["itens"] = itens
        contexto["valor_total"] = valor_total
        contexto["titulo"] = "Curva ABC por Valor de Estoque"

    elif tipo == "perdas":
        perdas, validade = services.perdas_e_validade(conn)
        contexto["perdas"] = perdas
        contexto["validade"] = validade
        contexto["titulo"] = "Perdas e Validade"

    elif tipo == "excecoes":
        lista = services.excecoes(conn)
        contexto["excecoes"] = lista
        contexto["titulo"] = "Exceções"

    elif tipo == "detalhe":
        divs = services.divergencias_da_auditoria(conn, id_auditoria)
        contexto["divergencias"] = divs
        contexto["titulo"] = f"Detalhe por Produto — Auditoria #{id_auditoria}"

    conn.close()
    return render_template("auditoria_relatorios.html", **contexto)

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
            row = conn.execute(
                "SELECT * FROM usuarios WHERE id_usuario=?", (id_usuario,)
            ).fetchone()
            if not row:
                flash("Usuário não encontrado.", "erro")
                conn.close()
                return redirect(url_for("usuarios_list"))
            antigos = dict(row)
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
        row = conn.execute(
            "SELECT * FROM usuarios WHERE id_usuario=?", (id_usuario,)
        ).fetchone()
        if not row:
            flash("Usuário não encontrado.", "erro")
        else:
            antigos = dict(row)
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
# Configurações  ← ESTA É A FUNÇÃO QUE ESTAVA A FALTAR
# ---------------------------------------------------------------------------
@app.route("/configuracoes", methods=["GET", "POST"])
@perfil_required("Admin")
def configuracoes():
    if request.method == "POST":
        set_config("metodo_custeio", request.form.get("metodo_custeio", "media_ponderada"))
        set_config("dias_alerta_validade", request.form.get("dias_alerta_validade", "7"))
        set_config("margem_lucro_desejada", request.form.get("margem_lucro_desejada", "30"))
        set_config("permitir_estoque_negativo","1" if request.form.get("permitir_estoque_negativo") else "0")
        set_config("nome_empresa", (request.form.get("nome_empresa") or "").strip())
        set_config("moeda", (request.form.get("moeda") or "MZN").strip())
        set_config("estoque_minimo_padrao", request.form.get("estoque_minimo_padrao", "0"))
        set_config("backup_automatico","1" if request.form.get("backup_automatico") else "0")
        set_config("max_tentativas_login", request.form.get("max_tentativas_login", "5"))
        set_config("tempo_bloqueio_login_min", request.form.get("tempo_bloqueio_login_min", "5"))
        set_config("morada_empresa", (request.form.get("morada_empresa") or "").strip())
        set_config("nuit_empresa", (request.form.get("nuit_empresa") or "").strip())
        set_config("contacto_empresa", (request.form.get("contacto_empresa") or "").strip())
        set_config("email_empresa", (request.form.get("email_empresa") or "").strip())
        set_config("serie_fatura", (request.form.get("serie_fatura") or "FT").strip())
        set_config("proximo_num_fatura", request.form.get("proximo_num_fatura", "1").strip())
        set_config("tipo_documento", (request.form.get("tipo_documento") or "Factura").strip())
        set_config("condicoes_pagamento_padrao", (request.form.get("condicoes_pagamento_padrao") or "").strip())
        set_config("cambio_padrao", (request.form.get("cambio_padrao") or "0,00").strip())
        set_config("moeda_cambio", (request.form.get("moeda_cambio") or "USD").strip())
        set_config("taxa_iva_padrao", request.form.get("taxa_iva_padrao", "16").strip())
        set_config("regime_iva", (request.form.get("regime_iva") or "Regime Geral").strip())
        set_config("motivo_isencao_iva",(request.form.get("motivo_isencao_iva") or "").strip())
        set_config("texto_rodape_fatura", (request.form.get("texto_rodape_fatura") or "").strip())
        set_config("banco_nome", (request.form.get("banco_nome") or "").strip())
        set_config("iban_empresa", (request.form.get("iban_empresa") or "").strip())
        set_config("numero_conta", (request.form.get("numero_conta") or "").strip())
        set_config("nib_empresa", (request.form.get("nib_empresa") or "").strip())


        # Código de segurança para alterar produto — guardado como HASH
        codigo_seg_novo = (request.form.get("codigo_alteracao_produto") or "").strip()
        if codigo_seg_novo:
            set_config("codigo_alteracao_produto",
                       generate_password_hash(codigo_seg_novo))
        elif request.form.get("limpar_codigo_alteracao") == "1":
            set_config("codigo_alteracao_produto", "")

        # Upload do logo
        logo_arquivo = request.files.get("logo_arquivo")
        if logo_arquivo and logo_arquivo.filename:
            try:
                ext = logo_arquivo.filename.rsplit(".", 1)[-1].lower()
                if ext not in ("png", "jpg", "jpeg", "gif", "bmp", "webp"):
                    raise ValueError("Formato de imagem não suportado")
                pasta_img = os.path.join(get_base_dir(), "static", "img")
                os.makedirs(pasta_img, exist_ok=True)
                nome_seguro = f"logo_empresa.{ext}"
                caminho = os.path.join(pasta_img, nome_seguro)
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
        "max_tentativas_login": get_config("max_tentativas_login", "5"),
        "tempo_bloqueio_login_min": get_config("tempo_bloqueio_login_min", "5"),
        "primeira_instalacao": get_config("primeira_instalacao", "1"),
        "serie_fatura": get_config("serie_fatura", "FT"),
        "proximo_num_fatura": get_config("proximo_num_fatura", "1"),
        "tipo_documento": get_config("tipo_documento", "Factura"),
        "condicoes_pagamento_padrao": get_config("condicoes_pagamento_padrao", "30 dias"),
        "cambio_padrao": get_config("cambio_padrao", "0,00"),
        "moeda_cambio": get_config("moeda_cambio", "USD"),
        "taxa_iva_padrao": get_config("taxa_iva_padrao", "16"),
        "regime_iva": get_config("regime_iva", "Regime Geral"),
        "motivo_isencao_iva": get_config("motivo_isencao_iva", ""),
        "texto_rodape_fatura": get_config("texto_rodape_fatura", ""),
        "banco_nome": get_config("banco_nome", ""),
        "banco_logo": get_config("banco_logo", ""),
        "iban_empresa": get_config("iban_empresa", ""),
        "numero_conta": get_config("numero_conta", ""),
        "nib_empresa": get_config("nib_empresa", ""),
    }
    logo_url = None
    if config["logo_empresa"]:
        logo_url = url_for("static", filename=f"img/{config['logo_empresa']}")
    return render_template("configuracoes.html", config=config, logo_url=logo_url)


@app.route("/configuracoes/backup")
@perfil_required("Admin")
def configuracoes_backup():
    backup_dir = os.path.join(get_base_dir(), "backups")
    os.makedirs(backup_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(backup_dir, f"estoque_backup_{ts}.db")
    try:
        c = sqlite3.connect(DB_PATH)
        c.execute("PRAGMA wal_checkpoint(FULL)")
        c.close()
    except Exception:
        pass
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
    caminho_temp = os.path.join(
        pasta_upload,
        f"upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{nome_seguro}",
    )
    arquivo.save(caminho_temp)

    tabelas_esperadas = {"produtos", "usuarios", "movimentos", "estoque",
                         "categorias", "configuracoes"}
    try:
        # 1) Validação: o ficheiro é uma BD SQLite do SGE?
        conn = sqlite3.connect(caminho_temp)
        tabelas_existentes = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        conn.close()
        if not tabelas_esperadas.issubset(tabelas_existentes):
            raise sqlite3.Error("Schema incompatível com o SGE.")

        # 2) Checkpoint WAL da BD atual antes de mexer
        try:
            c = sqlite3.connect(DB_PATH)
            c.execute("PRAGMA wal_checkpoint(FULL)")
            c.close()
        except Exception:
            pass

        # 3) Guarda o atual como pré-restauro (rollback)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        pre_restore = os.path.join(get_base_dir(), "backups", f"pre_restore_{ts}.db")
        os.makedirs(os.path.dirname(pre_restore), exist_ok=True)
        if os.path.exists(DB_PATH):
            try:
                shutil.copy2(DB_PATH, pre_restore)
            except Exception:
                pass

        # 4) FIX CRÍTICO: remove WAL/SHM antigos ANTES de substituir a BD
        for sufixo in ("-wal", "-shm", "-journal"):
            f = DB_PATH + sufixo
            if os.path.exists(f):
                try:
                    os.remove(f)
                except OSError:
                    pass

        # 5) Substitui a BD
        shutil.copy2(caminho_temp, DB_PATH)

        # 6) Aplica migrações do schema atual (para backups antigos)
        try:
            init_db()
            migracao_ok = True
        except Exception as mig_err:
            migracao_ok = False
            logging.error(f"Falha ao migrar backup restaurado: {mig_err}")
            if os.path.exists(pre_restore):
                try:
                    shutil.copy2(pre_restore, DB_PATH)
                    init_db()
                except Exception:
                    pass

        if migracao_ok:
            flash(
                "Backup restaurado e migrado para o schema actual com sucesso. "
                "Recomenda-se reiniciar a aplicação.",
                "sucesso",
            )
        else:
            flash(
                "Backup restaurado, mas a migração falhou. "
                "O sistema reverteu para o estado anterior.",
                "erro",
            )
    except sqlite3.Error as e:
        flash(f"O arquivo selecionado não é um backup válido do sistema. ({e})", "erro")
    except Exception as e:
        flash(f"Erro ao restaurar backup: {e}", "erro")
    finally:
        if os.path.exists(caminho_temp):
            try:
                os.remove(caminho_temp)
            except OSError:
                pass

    return redirect(url_for("configuracoes"))


@app.route("/configuracoes/formatar", methods=["GET", "POST"])
@perfil_required("Admin")
def configuracoes_formatar():
    if request.method == "POST":
        nivel = request.form.get("nivel", "").strip()
        confirmacao = request.form.get("confirmacao", "").strip().upper()
        ciencia = request.form.get("ciencia") == "1"

        if nivel not in services.NIVEIS_RESET:
            flash("Selecione um nível de reset válido.", "erro")
            return redirect(url_for("configuracoes_formatar"))
        if confirmacao != "APAGAR":
            flash("Para confirmar, escreva exactamente APAGAR (maiúsculas).", "erro")
            return redirect(url_for("configuracoes_formatar"))
        if not ciencia:
            flash("Marque a caixa confirmando que compreende o impacto.", "erro")
            return redirect(url_for("configuracoes_formatar"))

        conn = get_conn()
        try:
            resultado = services.formatar_base_dados(
                conn,
                nivel=nivel,
                id_usuario_admin=session["user_id"],
                ip_address=_client_ip(),
            )
            conn.commit()
            conn.close()

            try:
                log_path = os.path.join(get_base_dir(), "reset_log.txt")
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(
                        f"[{datetime.now().isoformat(timespec='seconds')}] "
                        f"user_id={session.get('user_id')} nivel={nivel} "
                        f"backup={resultado.get('backup_path')} ip={_client_ip()}\n"
                    )
            except Exception:
                pass

            session.clear()

            flash(
                f"Reset concluído ({services.NIVEIS_RESET[nivel]}). "
                f"Backup automático guardado em backups/. "
                f"Volte a entrar com as credenciais padrão (admin/admin123) se escolheu reset total.",
                "sucesso"
            )
            return redirect(url_for("login"))
        except services.RegraNegocioError as e:
            flash(str(e), "erro")
            conn.close()
        except Exception as e:
            flash(f"Erro ao formatar base de dados: {e}", "erro")
            try:
                conn.close()
            except Exception:
                pass
        return redirect(url_for("configuracoes_formatar"))

    return render_template(
        "configuracoes_formatar.html",
        niveis=services.NIVEIS_RESET,
    )


# ---------------------------------------------------------------------------
# Inicialização
# ---------------------------------------------------------------------------
try:
    init_db()
except Exception as _e:
    logging.error(f"Falha ao inicializar a base de dados: {_e}")


def abrir_navegador():
    """Abre o browser padrão do sistema no endereço da aplicação."""
    try:
        webbrowser.open(f"http://127.0.0.1:{APP_PORT}/")
    except Exception as e:
        logging.error(f"Falha ao abrir o browser: {e}")


if __name__ == "__main__":
    if "--no-browser" not in sys.argv:
        threading.Timer(1.2, abrir_navegador).start()

    try:
        app.run(
            host="127.0.0.1",
            port=APP_PORT,
            debug=False,
            threaded=True,
            use_reloader=False,
        )
    finally:
        _encerrar_tudo()