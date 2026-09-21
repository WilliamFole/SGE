# -*- coding: utf-8 -*-
"""Módulo database: definição do schema SQLite e funções de acesso.

Contém a definição do esquema (SCHEMA), inicialização do banco de dados
(init_db), utilitários para obter/definir configurações, e abstrações de
conexão com o ficheiro de base de dados embutido. Usado como camada de
persistência pelo restante da aplicação.
"""
import sqlite3
import os
import sys
from datetime import datetime
from werkzeug.security import generate_password_hash

def get_base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

DB_PATH = os.path.join(get_base_dir(), "dados", "estoque.db")

def get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

SCHEMA = """
CREATE TABLE IF NOT EXISTS categorias (
    id_categoria INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL UNIQUE,
    descricao TEXT,
    ativo INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS usuarios (
    id_usuario INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    login TEXT NOT NULL UNIQUE,
    senha_hash TEXT NOT NULL,
    perfil TEXT NOT NULL CHECK (perfil IN ('Admin','Gerente','Operador')),
    ativo INTEGER NOT NULL DEFAULT 1,
    email TEXT,
    telefone TEXT,
    token_recuperacao TEXT,
    token_expira TEXT
);

CREATE TABLE IF NOT EXISTS produtos (
    id_produto INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT NOT NULL UNIQUE,
    nome TEXT NOT NULL,
    id_categoria INTEGER NOT NULL,
    unidade TEXT NOT NULL CHECK (unidade IN ('Caixa','Embalagem','Unidade')),
    qtd_por_unidade INTEGER NOT NULL DEFAULT 1,
    preco_custo REAL NOT NULL DEFAULT 0,
    preco_venda REAL NOT NULL DEFAULT 0,
    estoque_minimo INTEGER NOT NULL DEFAULT 0,
    estoque_maximo INTEGER,
    validade TEXT,
    fornecedor TEXT,
    observacoes TEXT,
    ativo INTEGER NOT NULL DEFAULT 1,
    data_cadastro TEXT NOT NULL,
    FOREIGN KEY (id_categoria) REFERENCES categorias(id_categoria)
);

CREATE TABLE IF NOT EXISTS movimentos (
    id_movimento INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo TEXT NOT NULL CHECK (tipo IN ('Entrada','Saida')),
    id_produto INTEGER NOT NULL,
    data_hora TEXT NOT NULL,
    quantidade INTEGER NOT NULL,             -- quantidade na unidade base (inteira)
    quantidade_original INTEGER NOT NULL,    -- quantidade na unidade original (inteira)
    unidade_original TEXT NOT NULL,
    preco_unitario REAL NOT NULL,
    valor_total REAL NOT NULL,
    id_usuario INTEGER,
    nota_fiscal TEXT,
    fornecedor TEXT,
    cliente TEXT,
    forma_pagamento TEXT,
    observacoes TEXT,
    lucro REAL DEFAULT 0,
    FOREIGN KEY (id_produto) REFERENCES produtos(id_produto),
    FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario)
);

CREATE TABLE IF NOT EXISTS estoque (
    id_produto INTEGER PRIMARY KEY,
    saldo_atual INTEGER NOT NULL DEFAULT 0,   -- quantidade inteira
    ultima_atualizacao TEXT,
    FOREIGN KEY (id_produto) REFERENCES produtos(id_produto)
);

CREATE TABLE IF NOT EXISTS configuracoes (
    id_config INTEGER PRIMARY KEY AUTOINCREMENT,
    chave TEXT NOT NULL UNIQUE,
    valor TEXT
);

CREATE TABLE IF NOT EXISTS inventarios (
    id_inventario INTEGER PRIMARY KEY AUTOINCREMENT,
    id_produto INTEGER NOT NULL,
    contagem_fisica INTEGER NOT NULL DEFAULT 0,
    saldo_registrado INTEGER NOT NULL DEFAULT 0,
    diferenca INTEGER NOT NULL DEFAULT 0,
    data_registro TEXT NOT NULL,
    exportado INTEGER DEFAULT 0,
    valor_anterior INTEGER,
    FOREIGN KEY (id_produto) REFERENCES produtos(id_produto)
);

CREATE TABLE IF NOT EXISTS login_attempts (
    id_tentativa INTEGER PRIMARY KEY AUTOINCREMENT,
    login TEXT NOT NULL,
    ip_address TEXT,
    data_hora TEXT NOT NULL,
    sucesso INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS auditoria (
    id_auditoria INTEGER PRIMARY KEY AUTOINCREMENT,
    id_usuario INTEGER,
    tabela TEXT NOT NULL,
    id_registro INTEGER,
    acao TEXT NOT NULL CHECK (acao IN ('INSERT','UPDATE','DELETE','LOGIN','LOGOUT')),
    dados_anteriores TEXT,
    dados_novos TEXT,
    data_hora TEXT NOT NULL,
    ip_address TEXT
);

CREATE TABLE IF NOT EXISTS codigos_provisorios (
    id_codigo INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT NOT NULL UNIQUE,
    sessao_id TEXT,
    usado INTEGER NOT NULL DEFAULT 0,
    data_criacao TEXT NOT NULL
);

-- Tabelas para cotações
CREATE TABLE IF NOT EXISTS cotacoes (
    id_cotacao INTEGER PRIMARY KEY AUTOINCREMENT,
    numero TEXT NOT NULL UNIQUE,
    id_cliente INTEGER,
    nome_cliente TEXT NOT NULL,
    email_cliente TEXT,
    telefone_cliente TEXT,
    data_emissao TEXT NOT NULL,
    data_validade TEXT NOT NULL,
    observacoes TEXT,
    status TEXT DEFAULT 'Aberta',
    valor_total REAL NOT NULL,
    id_usuario INTEGER NOT NULL,
    FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario)
);

CREATE TABLE IF NOT EXISTS itens_cotacao (
    id_item INTEGER PRIMARY KEY AUTOINCREMENT,
    id_cotacao INTEGER NOT NULL,
    id_produto INTEGER NOT NULL,
    quantidade INTEGER NOT NULL,
    preco_unitario REAL NOT NULL,
    desconto_percentual REAL DEFAULT 0,
    valor_total REAL NOT NULL,
    FOREIGN KEY (id_cotacao) REFERENCES cotacoes(id_cotacao) ON DELETE CASCADE,
    FOREIGN KEY (id_produto) REFERENCES produtos(id_produto)
);

-- Índices
CREATE INDEX IF NOT EXISTS idx_mov_data ON movimentos(data_hora);
CREATE INDEX IF NOT EXISTS idx_mov_prod ON movimentos(id_produto);
CREATE INDEX IF NOT EXISTS idx_aud_data ON auditoria(data_hora);
CREATE INDEX IF NOT EXISTS idx_login_att ON login_attempts(login, data_hora);
CREATE INDEX IF NOT EXISTS idx_cotacoes_data ON cotacoes(data_emissao);
CREATE INDEX IF NOT EXISTS idx_cotacoes_status ON cotacoes(status);
"""

DEFAULT_CONFIG = {
    "metodo_custeio": "media_ponderada",
    "dias_alerta_validade": "7",
    "margem_lucro_desejada": "30",
    "permitir_estoque_negativo": "0",
    "nome_empresa": "",
    "moeda": "MZN",
    "estoque_minimo_padrao": "0",
    "backup_automatico": "0",
    "logo_empresa": "",
    "morada_empresa": "",
    "nuit_empresa": "",
    "contacto_empresa": "",
    "email_empresa": "",
    "codigo_alteracao_produto": "",
    "max_tentativas_login": "5",
    "tempo_bloqueio_login_min": "5",
    "primeira_instalacao": "1",
}

DEFAULT_CATEGORIAS = [
    ("Alimentos", "Produtos alimentícios em geral"),
    ("Bebidas", "Bebidas em geral"),
    ("Limpeza", "Produtos de limpeza e higiene"),
    ("Diversos", "Outros produtos"),
]

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.executescript(SCHEMA)

    # Atualiza colunas existentes se necessário (migrações)
    cur.execute("PRAGMA table_info(usuarios)")
    cols = [c[1] for c in cur.fetchall()]
    for col in ["email", "telefone", "token_recuperacao", "token_expira"]:
        if col not in cols:
            cur.execute(f"ALTER TABLE usuarios ADD COLUMN {col} TEXT")

    cur.execute("PRAGMA table_info(inventarios)")
    cols = [c[1] for c in cur.fetchall()]
    for col, tipo in [("exportado", "INTEGER DEFAULT 0"), ("valor_anterior", "INTEGER")]:
        if col not in cols:
            cur.execute(f"ALTER TABLE inventarios ADD COLUMN {col} {tipo}")

    # Ajustar tipos de colunas se necessário (ex: quantidade para INTEGER)
    # (Na prática, para SQLite, alterar tipo é complicado; recomenda-se recriar a tabela.
    # Para este exemplo, assumimos que as tabelas já foram criadas com os tipos corretos.)

    cur.execute("SELECT COUNT(*) AS c FROM usuarios")
    if cur.fetchone()["c"] == 0:
        cur.execute(
            "INSERT INTO usuarios (nome, login, senha_hash, perfil, ativo) VALUES (?,?,?,?,1)",
            ("Administrador", "admin", generate_password_hash("admin123"), "Admin"),
        )

    cur.execute("SELECT COUNT(*) AS c FROM categorias")
    if cur.fetchone()["c"] == 0:
        cur.executemany(
            "INSERT INTO categorias (nome, descricao, ativo) VALUES (?,?,1)",
            DEFAULT_CATEGORIAS,
        )

    for chave, valor in DEFAULT_CONFIG.items():
        cur.execute("SELECT COUNT(*) AS c FROM configuracoes WHERE chave=?", (chave,))
        if cur.fetchone()["c"] == 0:
            cur.execute(
                "INSERT INTO configuracoes (chave, valor) VALUES (?,?)", (chave, valor)
            )

    conn.commit()
    conn.close()

def get_config(chave, default=None):
    conn = get_conn()
    row = conn.execute("SELECT valor FROM configuracoes WHERE chave=?", (chave,)).fetchone()
    conn.close()
    return row["valor"] if row else default

def set_config(chave, valor):
    conn = get_conn()
    conn.execute(
        "INSERT INTO configuracoes (chave, valor) VALUES (?,?) "
        "ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor",
        (chave, valor),
    )
    conn.commit()
    conn.close()

def get_company_info():
    return {
        "nome": get_config("nome_empresa", ""),
        "logo": get_config("logo_empresa", ""),
        "morada": get_config("morada_empresa", ""),
        "nuit": get_config("nuit_empresa", ""),
        "contacto": get_config("contacto_empresa", ""),
        "email": get_config("email_empresa", ""),
        "moeda": get_config("moeda", "MZN"),
    }

def registrar_auditoria(conn, id_usuario, tabela, id_registro, acao, dados_anteriores=None, dados_novos=None, ip_address=None):
    import json
    conn.execute(
        """INSERT INTO auditoria
           (id_usuario, tabela, id_registro, acao, dados_anteriores, dados_novos, data_hora, ip_address)
           VALUES (?,?,?,?,?,?,?,?)""",
        (id_usuario, tabela, id_registro, acao,
         json.dumps(dados_anteriores, ensure_ascii=False) if dados_anteriores is not None else None,
         json.dumps(dados_novos, ensure_ascii=False) if dados_novos is not None else None,
         datetime.now().isoformat(timespec="seconds"), ip_address),
    )