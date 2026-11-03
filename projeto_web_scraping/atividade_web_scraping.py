import os
import logging
from datetime import datetime, timedelta

import requests
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

#1. CONFIGURAÇÃO
plt.style.use("ggplot")
sns.set_theme(style="whitegrid")

PASTA_DADOS = "dados_cotacoes"
os.makedirs(PASTA_DADOS, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

MOEDAS = {
    "USD": "Dólar Americano",
    "EUR": "Euro",
    "GBP": "Libra Esterlina",
    "JPY": "Iene Japonês",
    "ARS": "Peso Argentino",
}

URL_BCB = (
    "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/"
    "CotacaoMoedaPeriodo(moeda=@moeda,dataInicial=@dataInicial,"
    "dataFinalCotacao=@dataFinalCotacao)"
)


def obter_periodo():
    """Retorna as datas no formato exigido pela API PTAX: MM-DD-AAAA."""
    fim = datetime.now()
    inicio = fim - timedelta(days=30)
    return inicio.strftime("%m-%d-%Y"), fim.strftime("%m-%d-%Y")


#2. COLETA DE DADOS

def consultar_moeda(codigo, nome, data_inicio, data_fim):
    """Consulta as cotações de uma moeda e devolve uma lista de registros."""
    logging.info("Consultando %s (%s)...", nome, codigo)

    parametros = {
        "@moeda": f"'{codigo}'",
        "@dataInicial": f"'{data_inicio}'",
        "@dataFinalCotacao": f"'{data_fim}'",
        "$top": 1000,
        "$format": "json",
    }

    try:
        resposta = requests.get(URL_BCB, params=parametros, timeout=30)
        resposta.raise_for_status()
        conteudo = resposta.json()
    except requests.RequestException as erro:
        logging.error("Falha na consulta de %s: %s", codigo, erro)
        return []
    except ValueError:
        logging.error("A API retornou uma resposta que não é JSON para %s.", codigo)
        return []

    registros = []
    for item in conteudo.get("value", []):
        registros.append({
            "data": item.get("dataHoraCotacao"),
            "cotacao_compra": item.get("cotacaoCompra"),
            "cotacao_venda": item.get("cotacaoVenda"),
        })

    logging.info("%s: %d cotação(ões) recebida(s).", codigo, len(registros))
    return registros


def coletar_dados():
    data_inicio, data_fim = obter_periodo()
    dados = {}

    logging.info("Período consultado: %s até %s", data_inicio, data_fim)

    for codigo, nome in MOEDAS.items():
        cotacoes = consultar_moeda(codigo, nome, data_inicio, data_fim)
        if cotacoes:
            df = pd.DataFrame(cotacoes)
            df["data"] = pd.to_datetime(df["data"], errors="coerce")
            df["cotacao_compra"] = pd.to_numeric(
                df["cotacao_compra"], errors="coerce"
            )
            df["cotacao_venda"] = pd.to_numeric(
                df["cotacao_venda"], errors="coerce"
            )
            df = df.dropna(subset=["data", "cotacao_compra", "cotacao_venda"])
            df = df.sort_values("data").drop_duplicates(subset=["data"])
            if not df.empty:
                dados[codigo] = {"nome": nome, "df": df}

    if not dados:
        raise RuntimeError(
            "Nenhuma cotação foi obtida. Verifique a conexão e tente novamente."
        )

    return dados


#3. PROCESSAMENTO E CSV

def salvar_csvs(dados):
    for codigo, info in dados.items():
        caminho = os.path.join(PASTA_DADOS, f"cotacao_{codigo}.csv")
        info["df"].to_csv(caminho, index=False, encoding="utf-8-sig")
        logging.info("CSV salvo: %s", caminho)


#4. VISUALIZAÇÃO DOS DADOS

def gerar_grafico_comparativo(dados):
    plt.figure(figsize=(14, 8))

    for codigo, info in dados.items():
        df = info["df"]
        plt.plot(
            df["data"], df["cotacao_venda"],
            marker="o", markersize=3,
            label=f'{info["nome"]} ({codigo})'
        )

    plt.title("Cotação de venda das moedas em relação ao Real - últimos 30 dias")
    plt.xlabel("Data")
    plt.ylabel("Cotação de venda (R$)")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()

    caminho = os.path.join(PASTA_DADOS, "grafico_todas_moedas.png")
    plt.savefig(caminho, dpi=300)
    plt.close()
    logging.info("Gráfico comparativo salvo: %s", caminho)


def gerar_graficos_individuais(dados):
    for codigo, info in dados.items():
        df = info["df"]
        plt.figure(figsize=(12, 6))
        plt.plot(df["data"], df["cotacao_compra"], label="Compra")
        plt.plot(df["data"], df["cotacao_venda"], label="Venda")

        plt.title(f'{info["nome"]} ({codigo}) em relação ao Real (R$)')
        plt.xlabel("Data")
        plt.ylabel("Cotação (R$)")
        plt.legend()
        plt.grid(True)
        plt.tight_layout()

        caminho = os.path.join(PASTA_DADOS, f"grafico_{codigo}.png")
        plt.savefig(caminho, dpi=300)
        plt.close()
        logging.info("Gráfico individual salvo: %s", caminho)


def calcular_variacoes(dados):
    resultados = []

    for codigo, info in dados.items():
        df = info["df"].sort_values("data")
        if len(df) < 2:
            continue

        primeiro = df.iloc[0]["cotacao_venda"]
        ultimo = df.iloc[-1]["cotacao_venda"]
        variacao = ((ultimo - primeiro) / primeiro) * 100

        resultados.append({
            "moeda": f'{info["nome"]} ({codigo})',
            "variacao_percentual": variacao,
        })

    return resultados

def gerar_grafico_variacao(resultados):
    if not resultados:
        logging.warning("Não há dados suficientes para o gráfico de variação.")
        return

    nomes = [item["moeda"] for item in resultados]
    valores = [item["variacao_percentual"] for item in resultados]
    plt.figure(figsize=(12, 7))
    barras = plt.bar(nomes, valores)
    plt.axhline(y=0, linewidth=1)
    plt.title("Variação percentual das moedas no período")
    plt.ylabel("Variação (%)")
    plt.xticks(rotation=15, ha="right")

    for barra, valor in zip(barras, valores):
        deslocamento = 3 if valor >= 0 else -12
        plt.annotate(
            f"{valor:.2f}%",
            (barra.get_x() + barra.get_width() / 2, valor),
            xytext=(0, deslocamento),
            textcoords="offset points",
            ha="center"
        )
    plt.tight_layout()
    caminho = os.path.join(PASTA_DADOS, "grafico_variacao_percentual.png")
    plt.savefig(caminho, dpi=300)
    plt.close()
    logging.info("Gráfico de variação salvo: %s", caminho)


#5. EXERCÍCIO ADICIONAL: CORRELAÇÃO

def gerar_analise_correlacao(dados):
    "Compara as séries de cotação de venda nas datas coincidentes."
    series = []

    for codigo, info in dados.items():
        serie = info["df"].set_index("data")["cotacao_venda"].rename(codigo)
        series.append(serie)

    if len(series) < 2:
        logging.warning("São necessárias pelo menos duas moedas para correlação.")
        return

    tabela = pd.concat(series, axis=1).sort_index()
    correlacao = tabela.corr(min_periods=2)

    caminho_csv = os.path.join(PASTA_DADOS, "matriz_correlacao.csv")
    correlacao.to_csv(caminho_csv, encoding="utf-8-sig")

    plt.figure(figsize=(9, 7))
    sns.heatmap(
        correlacao, annot=True, cmap="coolwarm",
        vmin=-1, vmax=1, center=0, fmt=".2f"
    )
    plt.title("Correlação entre as cotações de venda das moedas")
    plt.tight_layout()

    caminho_png = os.path.join(PASTA_DADOS, "grafico_correlacao.png")
    plt.savefig(caminho_png, dpi=300)
    plt.close()

    logging.info("Matriz de correlação salva: %s", caminho_csv)
    logging.info("Gráfico de correlação salvo: %s", caminho_png)


#6. RESUMO E RELATÓRIO
def gerar_resumo_e_relatorio(dados, variacoes):
    linhas = [
        "RELATÓRIO - COTAÇÕES DE MOEDAS EM RELAÇÃO AO REAL",
        f"Data da execução: {datetime.now():%d/%m/%Y %H:%M}",
        "Fonte: API PTAX do Banco Central do Brasil",
        "Período de consulta: últimos 30 dias",
        "",
        "RESUMO DOS DADOS",
    ]

    print("\nRESUMO DOS DADOS COLETADOS")
    print("=" * 55)
    for codigo, info in dados.items():
        df = info["df"]
        inicio = df["data"].min().strftime("%d/%m/%Y")
        fim = df["data"].max().strftime("%d/%m/%Y")
        minimo = df["cotacao_venda"].min()
        maximo = df["cotacao_venda"].max()
        media = df["cotacao_venda"].mean()

        texto = (
            f'{info["nome"]} ({codigo}) | Período: {inicio} a {fim} | '
            f'Mínima: R$ {minimo:.4f} | Máxima: R$ {maximo:.4f} | '
            f'Média: R$ {media:.4f}'
        )
        print(texto)
        linhas.append(texto)

    linhas.extend(["", "VARIAÇÃO PERCENTUAL NO PERÍODO"])
    for item in variacoes:
        texto = f'{item["moeda"]}: {item["variacao_percentual"]:+.2f}%'
        print(texto)
        linhas.append(texto)

    if variacoes:
        maior = max(variacoes, key=lambda x: x["variacao_percentual"])
        menor = min(variacoes, key=lambda x: x["variacao_percentual"])
        linhas.extend([
            "",
            "CONCLUSÃO AUTOMÁTICA (REVISAR ANTES DA ENTREGA)",
            (
                f'A maior variação positiva foi observada em {maior["moeda"]} '
                f'({maior["variacao_percentual"]:+.2f}%).'
            ),
            (
                f'A menor variação foi observada em {menor["moeda"]} '
                f'({menor["variacao_percentual"]:+.2f}%).'
            ),
            (
                "As variações representam a diferença entre a primeira e a última "
                "cotação de venda disponível no período consultado. Os resultados "
                "descrevem o intervalo analisado e não garantem tendências futuras."
            ),
            (
                "A matriz de correlação compara o comportamento conjunto das "
                "cotações nas datas coincidentes. Correlação não significa causalidade."
            ),
        ])
    caminho = os.path.join(PASTA_DADOS, "relatorio_resumo.txt")
    with open(caminho, "w", encoding="utf-8") as arquivo:
        arquivo.write("\n".join(linhas))

    logging.info("Relatório-resumo salvo: %s", caminho)


#EXECUÇÃO PRINCIPAL
def main():
    dados = coletar_dados()
    salvar_csvs(dados)

    gerar_grafico_comparativo(dados)
    gerar_graficos_individuais(dados)

    variacoes = calcular_variacoes(dados)
    gerar_grafico_variacao(variacoes)
    gerar_analise_correlacao(dados)
    gerar_resumo_e_relatorio(dados, variacoes)

    print(f"\nConcluído! Confira os arquivos na pasta '{PASTA_DADOS}'.")
if __name__ == "__main__":
    main()