import csv
from html import escape
import io
import sqlite3
import streamlit as st
from contextlib import contextmanager
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

DB_NAME = Path(__file__).resolve().with_name("gastos_pessoais.db")
CATEGORIAS = ["Alimentação", "Moradia", "Transporte", "Saúde", "Lazer", "Salário", "Outros"]
TIPOS = ["Despesa", "Receita"]


class BancoDeDados:
    def __init__(self, caminho=DB_NAME):
        self.caminho = caminho

    @contextmanager
    def conectar(self):
        conexao = sqlite3.connect(self.caminho)
        conexao.row_factory = sqlite3.Row
        try:
            with conexao:
                yield conexao
        finally:
            conexao.close()

    def inicializar(self):
        with self.conectar() as conexao:
            conexao.execute(
                """
                CREATE TABLE IF NOT EXISTS transacoes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    descricao TEXT NOT NULL,
                    valor REAL NOT NULL,
                    tipo TEXT NOT NULL,
                    categoria TEXT NOT NULL,
                    data TEXT NOT NULL DEFAULT ''
                )
                """
            )
            colunas = {linha["name"] for linha in conexao.execute("PRAGMA table_info(transacoes)")}
            if "data" not in colunas:
                conexao.execute("ALTER TABLE transacoes ADD COLUMN data TEXT NOT NULL DEFAULT ''")

    def adicionar(self, descricao, valor, tipo, categoria, data_transacao):
        with self.conectar() as conexao:
            conexao.execute(
                "INSERT INTO transacoes (descricao, valor, tipo, categoria, data) VALUES (?, ?, ?, ?, ?)",
                (descricao, float(valor), tipo, categoria, data_transacao),
            )

    def listar(self, tipo="Todos", categoria="Todas", busca=""):
        consulta = "SELECT id, descricao, valor, tipo, categoria, data FROM transacoes WHERE 1 = 1"
        parametros = []
        if tipo != "Todos":
            consulta += " AND tipo = ?"
            parametros.append(tipo)
        if categoria != "Todas":
            consulta += " AND categoria = ?"
            parametros.append(categoria)
        if busca:
            consulta += " AND descricao LIKE ?"
            parametros.append(f"%{busca}%")
        consulta += " ORDER BY CASE WHEN data = '' THEN 1 ELSE 0 END, data DESC, id DESC"
        with self.conectar() as conexao:
            return conexao.execute(consulta, parametros).fetchall()

    def totais(self):
        receitas = Decimal("0.00")
        despesas = Decimal("0.00")
        with self.conectar() as conexao:
            registros = conexao.execute("SELECT valor, tipo FROM transacoes").fetchall()
        for registro in registros:
            valor = Decimal(str(registro["valor"]))
            if registro["tipo"] == "Receita":
                receitas += valor
            else:
                despesas += valor
        return receitas, despesas

    def excluir(self, id_transacao):
        with self.conectar() as conexao:
            conexao.execute("DELETE FROM transacoes WHERE id = ?", (id_transacao,))


@st.cache_resource
def obter_banco():
    banco = BancoDeDados()
    banco.inicializar()
    return banco


def formatar_moeda(valor):
    texto = f"{valor:,.2f}"
    return "R$ " + texto.replace(",", "X").replace(".", ",").replace("X", ".")


def interpretar_valor(texto):
    texto = texto.strip().replace("R$", "").replace(" ", "")
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        valor = Decimal(texto).quantize(Decimal("0.01"))
    except InvalidOperation as erro:
        raise ValueError from erro
    if not valor.is_finite() or valor <= 0:
        raise ValueError
    return valor


def criar_csv(registros):
    buffer = io.StringIO(newline="")
    escritor = csv.writer(buffer, delimiter=";")
    escritor.writerow(("Data", "Descrição", "Categoria", "Tipo", "Valor (R$)"))
    for registro in registros:
        escritor.writerow(
            (
                registro["data"],
                registro["descricao"],
                registro["categoria"],
                registro["tipo"],
                formatar_moeda(Decimal(str(registro["valor"]))),
            )
        )
    return "\ufeff" + buffer.getvalue()


def renderizar_app():
    st.set_page_config(page_title="Meu Controle Financeiro", page_icon="💳", layout="wide")
    st.markdown(
        """
        <style>
        :root {
            --forest: #174b3a;
            --leaf: #267454;
            --coral: #b94f45;
            --ink: #20342c;
            --muted: #68766f;
            --paper: #f3f6f2;
        }
        .stApp { background: var(--paper); color: var(--ink); }
        .block-container { max-width: 1180px; padding-top: 2rem; padding-bottom: 3rem; }
        h1, h2, h3 { color: var(--forest); }
        h1 { font-size: 2rem !important; }
        [data-testid="stMetric"] {
            background: #fff;
            border: 1px solid #dfe7df;
            border-left: 4px solid var(--leaf);
            padding: 1rem 1.2rem;
            border-radius: 6px;
        }
        [data-testid="stMetricLabel"] { color: var(--muted); }
        [data-testid="stMetricValue"] { color: var(--forest); }
            .history-table-wrap { overflow-x: auto; border: 1px solid #dfe7df; border-radius: 6px; background: #fff; }
            table.history-table { width: 100%; border-collapse: collapse; font-size: .92rem; }
            table.history-table th { background: #e8eee8; color: var(--forest); text-align: left; font-weight: 600; }
            table.history-table th, table.history-table td { padding: .7rem .85rem; border-bottom: 1px solid #e8eee8; }
            table.history-table tr:last-child td { border-bottom: 0; }
            table.history-table td:nth-child(1), table.history-table td:nth-child(2),
            table.history-table td:nth-child(5), table.history-table td:nth-child(6) { white-space: nowrap; }
        div.stButton > button[kind="primary"] {
            background: var(--forest);
            border-color: var(--forest);
        }
        div.stButton > button[kind="primary"]:hover {
            background: var(--leaf);
            border-color: var(--leaf);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    banco = obter_banco()
    st.title("Meu Controle Financeiro")
    st.caption("Registre suas movimentações e acompanhe o saldo em um só lugar.")

    with st.expander("Nova transação", expanded=True):
        with st.form("formulario_transacao", clear_on_submit=True):
            descricao_col, valor_col, categoria_col, tipo_col, data_col = st.columns([2.2, 1, 1.3, 1, 1.2])
            descricao = descricao_col.text_input("Descrição", placeholder="Ex.: compras do mês")
            valor_texto = valor_col.text_input("Valor (R$)", placeholder="0,00")
            categoria = categoria_col.selectbox("Categoria", CATEGORIAS)
            tipo = tipo_col.selectbox("Tipo", TIPOS)
            data_transacao = data_col.date_input("Data", value=date.today(), format="DD/MM/YYYY")
            enviado = st.form_submit_button("Adicionar transação", type="primary", use_container_width=True)

        if enviado:
            if not descricao.strip():
                st.error("Informe a descrição da transação.")
            else:
                try:
                    valor = interpretar_valor(valor_texto)
                except ValueError:
                    st.error("Informe um valor maior que zero, por exemplo 125,90.")
                else:
                    try:
                        banco.adicionar(descricao.strip(), valor, tipo, categoria, data_transacao.isoformat())
                    except sqlite3.Error as erro:
                        st.error(f"Não foi possível salvar a transação: {erro}")
                    else:
                        st.success("Transação adicionada.")
                        st.rerun()

    receitas, despesas = banco.totais()
    saldo = receitas - despesas
    receita_col, despesa_col, saldo_col = st.columns(3)
    receita_col.metric("Receitas", formatar_moeda(receitas))
    despesa_col.metric("Despesas", formatar_moeda(despesas))
    saldo_col.metric("Saldo", formatar_moeda(saldo), delta="Positivo" if saldo >= 0 else "Negativo")

    st.subheader("Histórico")
    busca_col, tipo_col, categoria_col = st.columns([2, 1, 1.3])
    busca = busca_col.text_input("Buscar descrição", placeholder="Digite para pesquisar")
    filtro_tipo = tipo_col.selectbox("Filtrar por tipo", ["Todos", *TIPOS])
    filtro_categoria = categoria_col.selectbox("Filtrar por categoria", ["Todas", *CATEGORIAS])
    registros = banco.listar(tipo=filtro_tipo, categoria=filtro_categoria, busca=busca.strip())
    st.caption(f"{len(registros)} transação(ões)")
    if registros:
        cabecalhos = ("ID", "Data", "Descrição", "Categoria", "Tipo", "Valor (R$)")
        linhas_html = []
        for registro in registros:
            valores = (
                registro["id"], registro["data"] or "Sem data", registro["descricao"],
                registro["categoria"], registro["tipo"],
                formatar_moeda(Decimal(str(registro["valor"]))),
            )
            celulas = "".join(f"<td>{escape(str(valor))}</td>" for valor in valores)
            linhas_html.append(f"<tr>{celulas}</tr>")
        cabecalho_html = "".join(f"<th>{escape(coluna)}</th>" for coluna in cabecalhos)
        tabela_html = (
            '<div class="history-table-wrap"><table class="history-table">'
            f"<thead><tr>{cabecalho_html}</tr></thead>"
            f"<tbody>{''.join(linhas_html)}</tbody></table></div>"
        )
        st.markdown(tabela_html, unsafe_allow_html=True)
        st.download_button(
            "Exportar CSV",
            data=criar_csv(registros),
            file_name="transacoes.csv",
            mime="text/csv",
        )

        st.divider()
        st.markdown("**Excluir transação**")
        opcoes = {registro["id"]: registro for registro in registros}
        id_selecionado = st.selectbox(
            "Selecione um registro",
            options=list(opcoes),
            format_func=lambda id_registro: (
                f'{opcoes[id_registro]["data"]} · {opcoes[id_registro]["descricao"]} · '
                f'{formatar_moeda(Decimal(str(opcoes[id_registro]["valor"])))}'
            ),
            label_visibility="collapsed",
        )
        confirmar = st.checkbox("Confirmo a exclusão desta transação")
        if st.button("Excluir selecionada", disabled=not confirmar):
            banco.excluir(id_selecionado)
            st.success("Transação excluída.")
            st.rerun()
    else:
        st.info("Nenhuma transação encontrada para esses filtros.")


renderizar_app()
