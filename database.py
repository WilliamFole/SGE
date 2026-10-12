# -*- coding: utf-8 -*-
<<<<<<< HEAD
"""Módulo database: definição do schema SQLite e funções de acesso."""
=======
"""Módulo database: definição do schema SQLite e funções de acesso.

Contém a definição do esquema (SCHEMA), inicialização do banco de dados
(init_db), utilitários para obter/definir configurações, e abstrações de
conexão com o ficheiro de base de dados embutido. Usado como camada de
persistência pelo restante da aplicação.
"""
>>>>>>> 64ec9886f1e598d60850f545ee865d1da75d06e9
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
<<<<<<< HEAD
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # WAL: melhora a concorrência em ambientes multi-request (desktop)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
    except sqlite3.OperationalError:
        # Alguns sistemas de ficheiros não suportam WAL — ignora
        pass
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA synchronous = NORMAL")
=======
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
>>>>>>> 64ec9886f1e598d60850f545ee865d1da75d06e9
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
<<<<<<< HEAD
    quantidade INTEGER NOT NULL,
    quantidade_original INTEGER NOT NULL,
=======
    quantidade INTEGER NOT NULL,             -- quantidade na unidade base (inteira)
    quantidade_original INTEGER NOT NULL,    -- quantidade na unidade original (inteira)
>>>>>>> 64ec9886f1e598d60850f545ee865d1da75d06e9
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
<<<<<<< HEAD
    saldo_atual INTEGER NOT NULL DEFAULT 0,
=======
    saldo_atual INTEGER NOT NULL DEFAULT 0,   -- quantidade inteira
>>>>>>> 64ec9886f1e598d60850f545ee865d1da75d06e9
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

<<<<<<< HEAD
=======
-- Tabelas para cotações
>>>>>>> 64ec9886f1e598d60850f545ee865d1da75d06e9
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

<<<<<<< HEAD
CREATE INDEX IF NOT EXISTS idx_cotacoes_status ON cotacoes(status);

CREATE TABLE IF NOT EXISTS contas_receber (
    id_conta INTEGER PRIMARY KEY AUTOINCREMENT,
    id_movimento INTEGER,
    nome_cliente TEXT NOT NULL,
    email_cliente TEXT,
    telefone_cliente TEXT,
    valor_total REAL NOT NULL,
    valor_pago REAL NOT NULL DEFAULT 0,
    saldo REAL NOT NULL,
    data_emissao TEXT NOT NULL,
    data_vencimento TEXT,
    status TEXT NOT NULL DEFAULT 'Aberta'
        CHECK (status IN ('Aberta','Parcial','Liquidada','Cancelada')),
    observacoes TEXT,
    id_usuario INTEGER,
    FOREIGN KEY (id_movimento) REFERENCES movimentos(id_movimento),
    FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario)
);

CREATE TABLE IF NOT EXISTS recibos (
    id_recibo INTEGER PRIMARY KEY AUTOINCREMENT,
    numero TEXT NOT NULL UNIQUE,
    id_conta INTEGER NOT NULL,
    valor REAL NOT NULL,
    data_pagamento TEXT NOT NULL,
    forma_pagamento TEXT,
    observacoes TEXT,
    id_usuario INTEGER,
    FOREIGN KEY (id_conta) REFERENCES contas_receber(id_conta),
    FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario)
);

CREATE TABLE IF NOT EXISTS contas_receber_itens (
    id_item INTEGER PRIMARY KEY AUTOINCREMENT,
    id_conta INTEGER NOT NULL,
    id_movimento INTEGER NOT NULL,
    id_produto INTEGER NOT NULL,
    quantidade_original REAL NOT NULL,
    unidade_original TEXT NOT NULL,
    quantidade_base REAL NOT NULL,
    preco_unitario REAL NOT NULL,
    valor_total REAL NOT NULL,
    FOREIGN KEY (id_conta) REFERENCES contas_receber(id_conta) ON DELETE CASCADE,
    FOREIGN KEY (id_movimento) REFERENCES movimentos(id_movimento),
    FOREIGN KEY (id_produto) REFERENCES produtos(id_produto)
);
    CREATE TABLE IF NOT EXISTS auditorias (
    id_auditoria INTEGER PRIMARY KEY AUTOINCREMENT,
    data_inicio TEXT NOT NULL,
    data_fim TEXT NOT NULL,
    data_abertura TEXT NOT NULL,
    tipo TEXT NOT NULL DEFAULT 'completa'
        CHECK (tipo IN ('completa','por_categoria','por_amostragem')),
    id_categoria INTEGER,
    responsavel_id INTEGER NOT NULL,
    estado TEXT NOT NULL DEFAULT 'aberta'
        CHECK (estado IN ('aberta','em_contagem','em_revisao','fechada')),
    congelado_em TEXT,
    tolerancia_percentual REAL DEFAULT 1.0,
    tolerancia_valor_minimo REAL DEFAULT 0,
    observacoes TEXT,
    valor_div_qtd REAL DEFAULT 0,
    valor_div_valor REAL DEFAULT 0,
    FOREIGN KEY (responsavel_id) REFERENCES usuarios(id_usuario),
    FOREIGN KEY (id_categoria) REFERENCES categorias(id_categoria)
);

CREATE TABLE IF NOT EXISTS auditoria_contagens (
    id_contagem INTEGER PRIMARY KEY AUTOINCREMENT,
    id_auditoria INTEGER NOT NULL,
    id_produto INTEGER NOT NULL,
    quantidade_contada REAL NOT NULL,
    data_contagem TEXT NOT NULL,
    id_usuario_contador INTEGER,
    local_prateleira TEXT,
    lote TEXT,
    validade TEXT,
    observacao TEXT,
    contagem_cega INTEGER DEFAULT 0,
    FOREIGN KEY (id_auditoria) REFERENCES auditorias(id_auditoria) ON DELETE CASCADE,
    FOREIGN KEY (id_produto) REFERENCES produtos(id_produto),
    FOREIGN KEY (id_usuario_contador) REFERENCES usuarios(id_usuario)
);

CREATE TABLE IF NOT EXISTS auditoria_divergencias (
    id_divergencia INTEGER PRIMARY KEY AUTOINCREMENT,
    id_auditoria INTEGER NOT NULL,
    id_produto INTEGER NOT NULL,
    estoque_teorico REAL NOT NULL DEFAULT 0,
    estoque_contado REAL NOT NULL DEFAULT 0,
    diferenca_qtd REAL NOT NULL DEFAULT 0,
    custo_unitario REAL NOT NULL DEFAULT 0,
    diferenca_valor REAL NOT NULL DEFAULT 0,
    causa TEXT,
    estado TEXT NOT NULL DEFAULT 'pendente'
        CHECK (estado IN ('pendente','justificada','ajustada','aceita')),
    observacao TEXT,
    id_ajuste INTEGER,
    FOREIGN KEY (id_auditoria) REFERENCES auditorias(id_auditoria) ON DELETE CASCADE,
    FOREIGN KEY (id_produto) REFERENCES produtos(id_produto)
);

CREATE TABLE IF NOT EXISTS auditoria_ajustes (
    id_ajuste INTEGER PRIMARY KEY AUTOINCREMENT,
    id_auditoria INTEGER NOT NULL,
    id_produto INTEGER NOT NULL,
    quantidade_ajuste REAL NOT NULL,
    motivo TEXT,
    id_usuario_aprovador INTEGER,
    data_aprovacao TEXT,
    id_movimento_gerado INTEGER,
    observacao TEXT,
    FOREIGN KEY (id_auditoria) REFERENCES auditorias(id_auditoria) ON DELETE CASCADE,
    FOREIGN KEY (id_produto) REFERENCES produtos(id_produto),
    FOREIGN KEY (id_usuario_aprovador) REFERENCES usuarios(id_usuario)
);
CREATE TABLE IF NOT EXISTS fechos_mensais (
    id_fecho INTEGER PRIMARY KEY AUTOINCREMENT,
    ano INTEGER NOT NULL,
    mes INTEGER NOT NULL,
    data_fecho TEXT NOT NULL,
    data_geracao TEXT NOT NULL,
    valor_total_custo REAL NOT NULL DEFAULT 0,
    valor_total_venda REAL NOT NULL DEFAULT 0,
    num_produtos INTEGER NOT NULL DEFAULT 0,
    id_usuario INTEGER,
    observacoes TEXT,
    UNIQUE(ano, mes),
    FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario)
);

CREATE TABLE IF NOT EXISTS fechos_mensais_itens (
    id_item INTEGER PRIMARY KEY AUTOINCREMENT,
    id_fecho INTEGER NOT NULL,
    id_produto INTEGER NOT NULL,
    quantidade REAL NOT NULL DEFAULT 0,
    custo_unitario REAL NOT NULL DEFAULT 0,
    preco_venda REAL NOT NULL DEFAULT 0,
    valor_custo REAL NOT NULL DEFAULT 0,
    valor_venda REAL NOT NULL DEFAULT 0,
    FOREIGN KEY (id_fecho) REFERENCES fechos_mensais(id_fecho) ON DELETE CASCADE,
    FOREIGN KEY (id_produto) REFERENCES produtos(id_produto)
);

CREATE INDEX IF NOT EXISTS idx_fecho_ano_mes ON fechos_mensais(ano, mes);
CREATE INDEX IF NOT EXISTS idx_fechoitens_fecho ON fechos_mensais_itens(id_fecho);

CREATE INDEX IF NOT EXISTS idx_aud_estado ON auditorias(estado);
CREATE INDEX IF NOT EXISTS idx_aud_data ON auditorias(data_inicio, data_fim);
CREATE INDEX IF NOT EXISTS idx_audcont_aud ON auditoria_contagens(id_auditoria);
CREATE INDEX IF NOT EXISTS idx_auddiv_aud ON auditoria_divergencias(id_auditoria);
CREATE INDEX IF NOT EXISTS idx_cri_conta ON contas_receber_itens(id_conta);

CREATE INDEX IF NOT EXISTS idx_cr_status ON contas_receber(status);
CREATE INDEX IF NOT EXISTS idx_cr_venc ON contas_receber(data_vencimento);
CREATE INDEX IF NOT EXISTS idx_rec_conta ON recibos(id_conta);
=======
-- Índices
>>>>>>> 64ec9886f1e598d60850f545ee865d1da75d06e9
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
<<<<<<< HEAD
    # ---- Fatura ----
    "serie_fatura": "FT",
    "proximo_num_fatura": "1",
    "tipo_documento": "Factura",
    "condicoes_pagamento_padrao": "30 dias",
    "cambio_padrao": "0,00",
    "moeda_cambio": "USD",
    "taxa_iva_padrao": "16",
    "regime_iva": "Regime Geral",
    "motivo_isencao_iva": "IVA — Regime de não isenção",
    "texto_rodape_fatura": (
        "Os bens e/ou serviços foram colocados à disposição do adquirente "
        "na data de emissão deste documento, de acordo com o regime legal aplicável."
    ),
    "banco_nome": "",
    "banco_logo": "",
    "iban_empresa": "",
    "numero_conta": "",
    "nib_empresa": "",
}
=======
}

>>>>>>> 64ec9886f1e598d60850f545ee865d1da75d06e9
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

<<<<<<< HEAD
    # Migração: colunas de usuarios
=======
    # Atualiza colunas existentes se necessário (migrações)
>>>>>>> 64ec9886f1e598d60850f545ee865d1da75d06e9
    cur.execute("PRAGMA table_info(usuarios)")
    cols = [c[1] for c in cur.fetchall()]
    for col in ["email", "telefone", "token_recuperacao", "token_expira"]:
        if col not in cols:
            cur.execute(f"ALTER TABLE usuarios ADD COLUMN {col} TEXT")

<<<<<<< HEAD
    # Migração: colunas de inventarios
=======
>>>>>>> 64ec9886f1e598d60850f545ee865d1da75d06e9
    cur.execute("PRAGMA table_info(inventarios)")
    cols = [c[1] for c in cur.fetchall()]
    for col, tipo in [("exportado", "INTEGER DEFAULT 0"), ("valor_anterior", "INTEGER")]:
        if col not in cols:
            cur.execute(f"ALTER TABLE inventarios ADD COLUMN {col} {tipo}")

<<<<<<< HEAD
    conn.commit()  # FIX: commit antes de PRAGMA foreign_keys

    # Migração: colunas de movimentos (data_vencimento, tipo_pagamento)
    cur.execute("PRAGMA table_info(movimentos)")
    cols_mov = [c[1] for c in cur.fetchall()]
    if "data_vencimento" not in cols_mov:
        cur.execute("ALTER TABLE movimentos ADD COLUMN data_vencimento TEXT")
    if "subtipo" not in cols_mov:
        cur.execute("ALTER TABLE movimentos ADD COLUMN subtipo TEXT")
    if "tipo_pagamento" not in cols_mov:
        cur.execute("ALTER TABLE movimentos ADD COLUMN tipo_pagamento TEXT DEFAULT 'Vista'")
        # Garante tabela contas_receber_itens para instalações antigas
    try:
        cur.execute("SELECT 1 FROM contas_receber_itens LIMIT 1")
    except Exception:
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS contas_receber_itens (
                id_item INTEGER PRIMARY KEY AUTOINCREMENT,
                id_conta INTEGER NOT NULL,
                id_movimento INTEGER NOT NULL,
                id_produto INTEGER NOT NULL,
                quantidade_original REAL NOT NULL,
                unidade_original TEXT NOT NULL,
                quantidade_base REAL NOT NULL,
                preco_unitario REAL NOT NULL,
                valor_total REAL NOT NULL
            );
        """)
        
        # Migração: colunas de auditoria_divergencias
    try:
        cur.execute("PRAGMA table_info(auditoria_divergencias)")
        cols_ad = [c[1] for c in cur.fetchall()]
        novas_ad = [
            ("motivo_justificacao", "TEXT"),
            ("recontagem_solicitada", "INTEGER DEFAULT 0"),
            ("recontagem_contador_id", "INTEGER"),
            ("recontagem_data", "TEXT"),
        ]
        for col, tipo in novas_ad:
            if col not in cols_ad:
                cur.execute(f"ALTER TABLE auditoria_divergencias ADD COLUMN {col} {tipo}")
    except Exception:
        pass
    # Migração: remover CHECK constraint de 'unidade' (permite 'kg')
    cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='produtos'")
    row_sql = cur.fetchone()
    if row_sql and "CHECK (unidade" in (row_sql[0] or ""):
        conn.execute("PRAGMA foreign_keys=OFF")
        cur.executescript("""
            CREATE TABLE produtos_new (
                id_produto INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo TEXT NOT NULL UNIQUE,
                nome TEXT NOT NULL,
                id_categoria INTEGER NOT NULL,
                unidade TEXT NOT NULL,
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
            INSERT INTO produtos_new
                SELECT id_produto, codigo, nome, id_categoria, unidade,
                       qtd_por_unidade, preco_custo, preco_venda,
                       estoque_minimo, estoque_maximo, validade,
                       fornecedor, observacoes, ativo, data_cadastro
                FROM produtos;
            DROP TABLE produtos;
            ALTER TABLE produtos_new RENAME TO produtos;
        """)
        conn.execute("PRAGMA foreign_keys=ON")
        conn.commit()

        # Migração: novas colunas em contas_receber
    cur.execute("PRAGMA table_info(contas_receber)")
    cols_cr = [c[1] for c in cur.fetchall()]
    novas_cr = [
        ("numero_fatura",    "TEXT"),
        ("nif_cliente",      "TEXT"),
        ("endereco_cliente", "TEXT"),
        ("localidade_cliente", "TEXT"),
        ("pais_cliente",     "TEXT"),
        ("isento_iva",       "INTEGER DEFAULT 0"),
        ("taxa_iva",         "REAL DEFAULT 16"),
        ("condicao_pagamento", "TEXT"),
    ]
    for col, tipo in novas_cr:
        if col not in cols_cr:
            cur.execute(f"ALTER TABLE contas_receber ADD COLUMN {col} {tipo}")

    # Cria utilizador admin se não existir
=======
    # Ajustar tipos de colunas se necessário (ex: quantidade para INTEGER)
    # (Na prática, para SQLite, alterar tipo é complicado; recomenda-se recriar a tabela.
    # Para este exemplo, assumimos que as tabelas já foram criadas com os tipos corretos.)

>>>>>>> 64ec9886f1e598d60850f545ee865d1da75d06e9
    cur.execute("SELECT COUNT(*) AS c FROM usuarios")
    if cur.fetchone()["c"] == 0:
        cur.execute(
            "INSERT INTO usuarios (nome, login, senha_hash, perfil, ativo) VALUES (?,?,?,?,1)",
            ("Administrador", "admin", generate_password_hash("admin123"), "Admin"),
        )

<<<<<<< HEAD
    # Cria categorias padrão
=======
>>>>>>> 64ec9886f1e598d60850f545ee865d1da75d06e9
    cur.execute("SELECT COUNT(*) AS c FROM categorias")
    if cur.fetchone()["c"] == 0:
        cur.executemany(
            "INSERT INTO categorias (nome, descricao, ativo) VALUES (?,?,1)",
            DEFAULT_CATEGORIAS,
        )

<<<<<<< HEAD
    # Configurações padrão
    for chave, valor in DEFAULT_CONFIG.items():
        cur.execute("SELECT COUNT(*) AS c FROM configuracoes WHERE chave=?", (chave,))
        if cur.fetchone()["c"] == 0:
            cur.execute("INSERT INTO configuracoes (chave, valor) VALUES (?,?)", (chave, valor))

    conn.commit()
    conn.close()
    
=======
    for chave, valor in DEFAULT_CONFIG.items():
        cur.execute("SELECT COUNT(*) AS c FROM configuracoes WHERE chave=?", (chave,))
        if cur.fetchone()["c"] == 0:
            cur.execute(
                "INSERT INTO configuracoes (chave, valor) VALUES (?,?)", (chave, valor)
            )

    conn.commit()
    conn.close()

>>>>>>> 64ec9886f1e598d60850f545ee865d1da75d06e9
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
<<<<<<< HEAD
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
        "iban": get_config("iban_empresa", ""),
        "numero_conta": get_config("numero_conta", ""),
        "nib": get_config("nib_empresa", ""),
=======
>>>>>>> 64ec9886f1e598d60850f545ee865d1da75d06e9
    }

def registrar_auditoria(conn, id_usuario, tabela, id_registro, acao, dados_anteriores=None, dados_novos=None, ip_address=None):
    import json
    conn.execute(
        """INSERT INTO auditoria
           (id_usuario, tabela, id_registro, acao, dados_anteriores, dados_novos, data_hora, ip_address)
           VALUES (?,?,?,?,?,?,?,?)""",
        (id_usuario, tabela, id_registro, acao,
<<<<<<< HEAD
         json.dumps(dados_anteriores, ensure_ascii=False, default=str) if dados_anteriores is not None else None,
         json.dumps(dados_novos, ensure_ascii=False, default=str) if dados_novos is not None else None,
=======
         json.dumps(dados_anteriores, ensure_ascii=False) if dados_anteriores is not None else None,
         json.dumps(dados_novos, ensure_ascii=False) if dados_novos is not None else None,
>>>>>>> 64ec9886f1e598d60850f545ee865d1da75d06e9
         datetime.now().isoformat(timespec="seconds"), ip_address),
    )