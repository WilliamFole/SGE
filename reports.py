# -*- coding: utf-8 -*-
import io
import os
import re
import base64
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side, numbers
from openpyxl.drawing.image import Image as XLImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

from services import arredondar_moeda

BRAND_COLOR = colors.HexColor("#2F5233")
BRAND_COLOR_HEX = "2F5233"


def _caminho_logo_empresa():
    from database import get_config, get_base_dir
    logo_cfg = get_config("logo_empresa", "")
    if not logo_cfg:
        return None
    if logo_cfg.startswith("data:"):
        return None
    caminho = os.path.join(get_base_dir(), "static", "img", logo_cfg)
    if os.path.exists(caminho):
        return caminho
    caminho2 = os.path.join(get_base_dir(), logo_cfg)
    if os.path.exists(caminho2):
        return caminho2
    return None


def _logo_data_url_bytes():
    from database import get_config, get_base_dir
    logo_cfg = get_config("logo_empresa", "")
    if not logo_cfg:
        return None
    if logo_cfg.startswith("data:image") and ";base64," in logo_cfg:
        try:
            header, data = logo_cfg.split(",", 1)
            ext = "png" if "png" in header else "jpg"
            return base64.b64decode(data), ext
        except Exception:
            return None
    caminho = os.path.join(get_base_dir(), "static", "img", logo_cfg)
    if not os.path.exists(caminho):
        caminho = os.path.join(get_base_dir(), logo_cfg)
    if os.path.exists(caminho):
        ext = caminho.rsplit(".", 1)[-1].lower()
        with open(caminho, "rb") as f:
            return f.read(), ext
    return None


def _dados_empresa():
    from database import get_company_info
    return get_company_info()


def _cabecalho_empresa_texto():
    emp = _dados_empresa()
    linhas = []
    if emp.get("nome"):
        linhas.append(emp["nome"])
    morada_nuit_contacto = []
    if emp.get("morada"):
        morada_nuit_contacto.append(emp["morada"])
    if emp.get("nuit"):
        morada_nuit_contacto.append(f"NUIT: {emp['nuit']}")
    if emp.get("contacto"):
        morada_nuit_contacto.append(f"Tel.: {emp['contacto']}")
    if emp.get("email"):
        morada_nuit_contacto.append(emp["email"])
    if morada_nuit_contacto:
        linhas.append("  |  ".join(morada_nuit_contacto))
    return linhas


def formatar_moeda_br(valor):
    """Formata valor com duas casas decimais e separador de milhar (ex: 1.000,00)."""
    if valor is None:
        return "0,00"
    try:
        return f"{float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return "0,00"


def formatar_inteiro(valor):
    """Formata inteiro com separador de milhar (ex: 1.000)."""
    if valor is None:
        return "0"
    try:
        val = int(float(valor))
        return f"{val:,}".replace(",", ".")
    except (TypeError, ValueError):
        return "0"


def gerar_pdf(titulo, colunas, linhas, subtitulo=None, empresa_titulo=None, is_cotacao=False, landscape_mode=False):
    buf = io.BytesIO()
    # Detecta automaticamente se precisa de orientação horizontal
    # Baseado no número de colunas ou largura do conteúdo
    if not landscape_mode and not is_cotacao:
        # Força horizontal para cotações e relatórios com muitas colunas (> 6)
        landscape_mode = len(colunas) > 6 or any(len(str(c)) > 30 for c in colunas)
    pagesize = landscape(A4) if landscape_mode or is_cotacao else A4
    doc = SimpleDocTemplate(buf, pagesize=pagesize,
                             topMargin=1.2*cm, bottomMargin=1.2*cm,
                             leftMargin=1.2*cm, rightMargin=1.2*cm)
    
    styles = getSampleStyleSheet()
    style_titulo_empresa = ParagraphStyle(
        "EmpresaTitulo", parent=styles["Title"],
        fontSize=16, textColor=BRAND_COLOR, alignment=TA_CENTER, spaceAfter=2,
    )
    style_sub_empresa = ParagraphStyle(
        "EmpresaSub", parent=styles["Normal"],
        fontSize=9, textColor=colors.HexColor("#4B4B4B"),
        alignment=TA_CENTER, spaceAfter=2,
    )
    elementos = []

    # Logo
    logo_caminho = _caminho_logo_empresa()
    emp = _dados_empresa()
    img = ""
    if logo_caminho:
        try:
            img = RLImage(logo_caminho, width=3.2*cm, height=3.2*cm)
            img.hAlign = "CENTER"
        except Exception:
            img = ""
    else:
        logo_bytes = _logo_data_url_bytes()
        if logo_bytes:
            try:
                from io import BytesIO
                b, ext = logo_bytes
                bio = BytesIO(b)
                img = RLImage(bio, width=3.2*cm, height=3.2*cm)
                img.hAlign = "CENTER"
            except Exception:
                img = ""

    titulo_emp = empresa_titulo or emp.get("nome") or "SGE — Sistema de Gestão de Estoque"
    sub = _cabecalho_empresa_texto()[1:] if len(_cabecalho_empresa_texto()) > 1 else []
    col_esq = [img] if img else [Paragraph("◈", ParagraphStyle(
        "Mark", fontSize=32, textColor=colors.HexColor("#E8B33D"), alignment=TA_CENTER))]
    texto_centro = [Paragraph(titulo_emp, style_titulo_empresa)]
    for s in sub:
        texto_centro.append(Paragraph(s, style_sub_empresa))
    cabecalho_tabela = Table([[col_esq[0], texto_centro]],
                             colWidths=[4*cm, doc.width - 4.2*cm])
    cabecalho_tabela.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("ALIGN", (0,0), (-1,-1), "CENTER"),
    ]))
    elementos.append(cabecalho_tabela)
    elementos.append(Spacer(1, 0.2*cm))
    if emp.get("nome"):
        elementos.append(Paragraph(titulo, ParagraphStyle(
            "TituloRel", parent=styles["Heading2"], alignment=TA_CENTER,
            textColor=BRAND_COLOR, spaceAfter=2,
        )))
    else:
        elementos.append(Paragraph(titulo, styles["Title"]))
    if subtitulo:
        elementos.append(Paragraph(subtitulo, styles["Normal"]))
    elementos.append(Paragraph(
        f"Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')}", styles["Normal"]))
    elementos.append(Spacer(1, 0.5*cm))

    # Preparar dados com formatação
    dados_formatados = [colunas]
    for linha in linhas:
        linha_formatada = []
        for idx, val in enumerate(linha):
            col_nome = colunas[idx].lower()
            num_val = None
            if isinstance(val, (int, float)):
                num_val = float(val)
            elif isinstance(val, str):
                texto = val.strip().replace(' ', '')
                # Normaliza separadores decimais
                if ',' in texto and '.' in texto:
                    texto_norm = texto.replace('.', '').replace(',', '.')
                elif ',' in texto and '.' not in texto:
                    texto_norm = texto.replace(',', '.')
                else:
                    texto_norm = texto
                if re.fullmatch(r"-?\d+(?:\.\d+)?", texto_norm):
                    try:
                        num_val = float(texto_norm)
                    except Exception:
                        num_val = None
                else:
                    num_val = None
            else:
                num_val = None

            if num_val is not None:
                col_nome_lower = col_nome.lower()
                if any(p in col_nome_lower for p in ("preço", "preco", "valor", "total", "lucro", "custo", "venda", "receita")):
                    linha_formatada.append(formatar_moeda_br(num_val))
                elif any(p in col_nome_lower for p in ("qtd", "quantidade", "saldo", "estoque", "unid", "numero", "número", "unidade", "minimo", "maximo")):
                    linha_formatada.append(formatar_inteiro(num_val))
                else:
                    if abs(num_val - round(num_val)) < 1e-9:
                        linha_formatada.append(formatar_inteiro(num_val))
                    else:
                        linha_formatada.append(formatar_moeda_br(num_val))
            else:
                linha_formatada.append(str(val))
        dados_formatados.append(linha_formatada)

    tabela = Table(dados_formatados, repeatRows=1)
    tabela.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), BRAND_COLOR),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTSIZE", (0,0), (-1,-1), 8),
        ("FONTNAME", (0,0), (-1,-1), "Times-Roman"),
        ("FONTNAME", (0,0), (-1,0), "Times-Bold"),
        ("GRID", (0,0), (-1,-1), 0.4, colors.grey),
        ("ROWBACKGROUNDS", (0,1), (-1,-1),
         [colors.white, colors.HexColor("#F2F2F2")]),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("ALIGN", (0,0), (-1,-1), "LEFT"),
        ("ALIGN", (1,1), (-1,-1), "RIGHT"),  # números alinhados à direita
    ]))
    elementos.append(tabela)
    doc.build(elementos)
    buf.seek(0)
    return buf


def gerar_excel(titulo, colunas, linhas, empresa_titulo=None):
    wb = Workbook()
    ws = wb.active
    ws.title = titulo[:31] if titulo else "Relatorio"

    emp = _dados_empresa()
    nome_emp = empresa_titulo or emp.get("nome") or "SGE — Sistema de Gestão de Estoque"
    linha_atual = 1

    # Logo
    logo_info = _logo_data_url_bytes()
    if logo_info:
        try:
            import tempfile
            dados_bytes, ext = logo_info
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}")
            tmp.write(dados_bytes)
            tmp.close()
            img = XLImage(tmp.name)
            img.width = 80
            img.height = 80
            ws.add_image(img, "A1")
            linha_atual = 6
        except Exception:
            pass

    header_fill = PatternFill(start_color=BRAND_COLOR_HEX, end_color=BRAND_COLOR_HEX,
                              fill_type="solid")
    header_font = Font(name='Times New Roman', bold=True, color="FFFFFF", size=12)
    default_font = Font(name='Times New Roman', size=11)
    thin_border = Border(
        left=Side(style='thin', color='CCCCCC'),
        right=Side(style='thin', color='CCCCCC'),
        top=Side(style='thin', color='CCCCCC'),
        bottom=Side(style='thin', color='CCCCCC'),
    )

    ws.cell(row=linha_atual, column=1, value=nome_emp).font = Font(
        name='Times New Roman', bold=True, color=BRAND_COLOR_HEX, size=14)
    ws.merge_cells(start_row=linha_atual, start_column=1,
                   end_row=linha_atual, end_column=max(3, len(colunas)))
    linha_atual += 1

    sub_linhas = []
    if emp.get("morada"):
        sub_linhas.append(emp["morada"])
    if emp.get("nuit"):
        sub_linhas.append(f"NUIT: {emp['nuit']}")
    if emp.get("contacto"):
        sub_linhas.append(f"Tel.: {emp['contacto']}")
    if emp.get("email"):
        sub_linhas.append(emp["email"])
    if sub_linhas:
        ws.cell(row=linha_atual, column=1, value="  |  ".join(sub_linhas)).font = Font(
            size=10, color="555555")
        ws.merge_cells(start_row=linha_atual, start_column=1,
                       end_row=linha_atual, end_column=max(3, len(colunas)))
        linha_atual += 1

    ws.cell(row=linha_atual, column=1, value=titulo).font = Font(
        bold=True, color=BRAND_COLOR_HEX, size=12)
    ws.merge_cells(start_row=linha_atual, start_column=1,
                   end_row=linha_atual, end_column=max(3, len(colunas)))
    linha_atual += 1
    ws.cell(row=linha_atual, column=1,
            value=f"Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')}").font = Font(
        size=9, color="666666")
    linha_atual += 2

    header_row = linha_atual
    for i, col in enumerate(colunas, 1):
        c = ws.cell(row=header_row, column=i, value=col)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = header_fill
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = thin_border

    for idx, linha in enumerate(linhas, 1):
        for j, val in enumerate(linha, 1):
            c = ws.cell(row=header_row + idx, column=j, value=val)
            c.border = thin_border
            c.font = default_font
            if idx % 2 == 0:
                c.fill = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
            # Formatação condicional
            col_nome = colunas[j-1].lower()
            if any(p in col_nome for p in ("preço", "preco", "valor", "total", "lucro", "custo", "venda")):
                if isinstance(val, (int, float)):
                    c.number_format = '#,##0.00'
                    c.alignment = Alignment(horizontal="right")
            elif isinstance(val, (int, float)):
                c.number_format = '#,##0'
                c.alignment = Alignment(horizontal="right")

    for col_cells in ws.columns:
        largura = max((len(str(c.value)) if c.value is not None else 0) for c in col_cells) + 2
        first_cell = next((c for c in col_cells if hasattr(c, 'column_letter')), None)
        if first_cell is not None:
            ws.column_dimensions[first_cell.column_letter].width = min(largura, 50)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


# Função específica para relatório de preços
def gerar_relatorio_precos(conn):
    produtos = conn.execute(
        """SELECT p.codigo, p.nome, c.nome AS categoria, p.preco_venda
           FROM produtos p LEFT JOIN categorias c ON c.id_categoria=p.id_categoria
           WHERE p.ativo=1 ORDER BY p.nome"""
    ).fetchall()
    colunas = ["Código", "Produto", "Categoria", "Preço de Venda (MZN)"]
    linhas = []
    for p in produtos:
        linhas.append([p["codigo"], p["nome"], p["categoria"] or "—", arredondar_moeda(p["preco_venda"])])
    return colunas, linhas


# Função para gerar PDF de cotação
def gerar_pdf_cotacao(cotacao, itens, empresa_titulo=None):
    # Similar ao gerar_pdf, mas com dados específicos da cotação
    colunas = ["Código", "Produto", "Quantidade", "Preço Unit.", "Desc. %", "Subtotal"]
    linhas = []
    for item in itens:
        linhas.append([
            item["codigo"],
            item["produto_nome"],
            int(item["quantidade"]),
            arredondar_moeda(item["preco_unitario"]),
            f"{item['desconto_percentual']:.0f}%",
            arredondar_moeda(item["valor_total"])
        ])
    # Adicionar totais e informações do cliente
    subtitulo = (f"Cliente: {cotacao['nome_cliente']} | "
                 f"Validade: {cotacao['data_validade']} | "
                 f"Total: {formatar_moeda_br(cotacao['valor_total'])}")
    return gerar_pdf(f"Cotação {cotacao['numero']}", colunas, linhas,
                     subtitulo=subtitulo, empresa_titulo=empresa_titulo,
                     landscape_mode=True)