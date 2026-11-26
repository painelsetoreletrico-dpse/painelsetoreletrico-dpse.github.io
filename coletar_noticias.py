# -*- coding: utf-8 -*-
"""Coleta manchetes recentes sobre clima severo e falta de energia e grava noticias.json.

Roda no GitHub (Actions) a cada 30 minutos. Usa só a biblioteca padrão do Python.
Fontes: busca do Google Notícias (que reúne g1, CNN Brasil, Metrópoles, UOL, Folha,
Agência Brasil, jornais regionais etc.) e os feeds RSS de alguns portais gerais.
Guarda só título, fonte, data e link (o texto das matérias não é copiado).
"""
import email.utils
import html
import json
import os
import re
import sys
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

SAIDA = "noticias.json"
DIAS = 7                 # janela máxima guardada (a página prioriza as últimas 48 h)
MAXIMO = 60
UA = "Mozilla/5.0 (compatible; painel-setor-eletrico/1.0; +https://github.com)"
SITE_ANTERIOR = os.environ.get("SITE_URL", "").rstrip("/")   # reaproveita a lista anterior se tudo falhar

BUSCAS = [   # Google Notícias, últimas 48 h, em português do Brasil
    '(temporal OR vendaval OR tempestade OR "chuva forte" OR granizo OR ciclone) (energia OR "sem luz" OR "falta de energia")',
    '("falta de energia" OR "sem energia" OR "sem luz" OR "queda de energia") (chuva OR temporal OR vento OR tempestade)',
    '("chuva forte" OR temporal OR ventania OR vendaval OR granizo OR alagamento) (cidade OR estado OR capital OR moradores OR bairros)',
    '(previsão OR alerta OR aviso) (chuva OR temporal OR tempestade OR ventania OR "frente fria" OR "onda de calor") (Inmet OR "Defesa Civil" OR Climatempo OR MetSul)',
    '(ciclone OR "frente fria" OR "massa de ar" OR "onda de calor") (previsão OR estados OR região)',
]
FEEDS = {   # portais gerais (o que não falar de clima é descartado pelo filtro)
    "g1": "https://g1.globo.com/rss/g1/",
    "CNN Brasil": "https://www.cnnbrasil.com.br/feed/",
    "Metrópoles": "https://www.metropoles.com/feed",
    "Agência Brasil": "https://agenciabrasil.ebc.com.br/rss/ultimasnoticias/feed.xml",
}

def sem_acento(t):
    return "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")

# o que não é tempo/clima, mesmo usando as mesmas palavras
EXCLUIR = (r"tempestade (solar|geomagnetic)|vento solar|erupc\w* solar|clima espacial|chuva de (gols|meteoros|estrelas|criticas|dinheiro|votos|likes|prata|ouro|bala|tiros|pedidos)"
           r"|tempestade perfeita|tempestade (politica|de ideias)|apagao (do|da|no|na|dos) (time|equipe|defesa|ataque|jogo|clube|selecao|goleiro)"
           r"|clima (de|entre|tenso|politico|eleitoral|organizacional)|previsao do (horoscopo|signo)|horoscopo")
TEMPO = (r"chuva|chuvas|chuvoso|temporal|temporais|tempestade|vendaval|ventania|rajada|granizo|ciclone|tornado|alagamento|alagad|enchente"
         r"|inundac|frente fria|onda de calor|calor extremo|massa de ar|raios\b|descargas? atmosferic|deslizamento|nevoeiro|geada|neve\b"
         r"|frio intenso|baixa umidade|estiagem|seca\b|tempo (instavel|severo|seco)|calor\b|previsao do tempo")
FORTE = (r"chuva (forte|intensa|volumosa|torrencial|de granizo|extrema)|chuvas? (fortes|intensas|volumosas)|temporal|temporais|tempestade|vendaval"
         r"|ventania|rajada|granizo|ciclone|tornado|alagamento|alagad|enchente|inundac|frente fria|onda de calor|calor extremo|deslizamento"
         r"|alerta|aviso|previsao|inmet|defesa civil|desabrig|desalojad|emergencia|calamidade|tempo (instavel|severo)|acumulado|milimetros|\bmm\b"
         r"|calor (forte|intenso|extremo)|\d+ ?(°|graus)")
FALTA = r"falta de (energia|luz)|sem (energia|luz)|queda de energia|apagao|interrupc\w* (de|no) (energia|fornecimento)|fornecimento de energia|religad|restabelec|desligamento"
DISTRIB = r"enel|light\b|cemig|copel|ceee|equatorial|energisa|neoenergia|coelba|cosern|celpe|cpfl|rge\b|celesc|edp\b|amazonas energia|elektro|distribuidora"
ALERTA = r"\binmet\b|defesa civil|alerta|aviso (amarelo|laranja|vermelho|meteorologico|de)"
LOCAL = r"\bcidade|\bestado|\bcapital|\bbairro|moradores|litoral|interior|regiao (sul|sudeste|norte|nordeste|centro|metropolitana|serrana)|\bsul\b|sudeste|nordeste|centro-oeste|\bnorte\b"
ESTADOS = [("rio grande do sul", "RS"), ("rio grande do norte", "RN"), ("mato grosso do sul", "MS"), ("mato grosso", "MT"),
    ("santa catarina", "SC"), ("sao paulo", "SP"), ("rio de janeiro", "RJ"), ("minas gerais", "MG"), ("espirito santo", "ES"),
    ("parana", "PR"), ("goias", "GO"), ("distrito federal", "DF"), ("brasilia", "DF"), ("bahia", "BA"), ("sergipe", "SE"),
    ("alagoas", "AL"), ("pernambuco", "PE"), ("paraiba", "PB"), ("ceara", "CE"), ("piaui", "PI"), ("maranhao", "MA"),
    ("tocantins", "TO"), ("amapa", "AP"), ("roraima", "RR"), ("rondonia", "RO"), ("acre", "AC"), ("amazonas", "AM"),
    ("porto alegre", "RS"), ("florianopolis", "SC"), ("curitiba", "PR"), ("belo horizonte", "MG"),
    ("salvador", "BA"), ("recife", "PE"), ("fortaleza", "CE"), ("manaus", "AM"), ("belem", "PA"),
    ("goiania", "GO"), ("campo grande", "MS"), ("cuiaba", "MT"), ("baixada fluminense", "RJ"), ("grande sp", "SP"),
    ("sao luis", "MA"), ("teresina", "PI"), ("natal", "RN"), ("joao pessoa", "PB"), ("maceio", "AL"), ("aracaju", "SE"),
    ("palmas", "TO"), ("porto velho", "RO"), ("rio branco", "AC"), ("boa vista", "RR"), ("macapa", "AP"), ("campinas", "SP"),
    ("santos", "SP"), ("niteroi", "RJ"), ("petropolis", "RJ"), ("joinville", "SC"), ("blumenau", "SC"), ("londrina", "PR"),
    ("caxias do sul", "RS"), ("pelotas", "RS"), ("uberlandia", "MG"), ("juiz de fora", "MG"), ("feira de santana", "BA"), ("serra gaucha", "RS")]

def baixar(url, tempo=30):
    pedido = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml, application/xml, */*"})
    with urllib.request.urlopen(pedido, timeout=tempo) as r:
        return r.read()

def data_rss(texto):
    try:
        d = email.utils.parsedate_to_datetime(texto)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None

def classificar(titulo):
    """Devolve (tipo, uf, prioridade) ou None.
    prioridade 3 = falta de energia ligada a tempo/rede; 2 = tempo severo/previsão com lugar ou alerta;
    1 = clima em geral (vai só para a lista completa)."""
    t = sem_acento(titulo)
    if re.search(EXCLUIR, t):
        return None
    tempo, forte, falta = re.search(TEMPO, t), re.search(FORTE, t), re.search(FALTA, t)
    distrib, energia_palavra = re.search(DISTRIB, t), re.search(r"energia|eletric", t)
    uf = next((sigla for nome, sigla in ESTADOS if re.search(r"\b" + nome, t)), None)
    if not uf:   # sigla escrita no título ("no RS", "em SP")
        m = re.search(r"\b(AC|AL|AP|AM|BA|CE|DF|ES|GO|MA|MT|MS|MG|PA|PB|PR|PE|PI|RJ|RN|RS|RO|RR|SC|SP|SE|TO)\b", titulo)
        uf = m.group(1) if m else None
    if falta and (tempo or distrib or energia_palavra):
        return "energia", uf, 3
    if not tempo:
        return None
    tipo = "alerta" if re.search(ALERTA, t) else "clima"
    if uf or (forte and (re.search(LOCAL, t) or tipo == "alerta")):   # tempo num lugar, ou alerta/tempo severo regional
        return tipo, uf, 2
    return tipo, uf, 1

def itens_rss(conteudo, fonte_padrao=None):
    raiz = ET.fromstring(conteudo)
    for it in raiz.iter("item"):
        titulo = html.unescape((it.findtext("title") or "").strip())
        link = (it.findtext("link") or "").strip()
        data = data_rss(it.findtext("pubDate") or "")
        fonte = fonte_padrao
        src = it.find("source")
        if src is not None and (src.text or "").strip():
            fonte = src.text.strip()
            sufixo = " - " + fonte
            if titulo.endswith(sufixo):
                titulo = titulo[: -len(sufixo)].strip()
        if titulo and link and data:
            yield {"titulo": titulo, "fonte": fonte or "Notícias", "url": link, "data": data}

def chave(titulo):
    return re.sub(r"[^a-z0-9 ]", "", sem_acento(titulo))[:70]

def coletar():
    agora = datetime.now(timezone.utc)
    limite = agora - timedelta(days=DIAS)
    brutos, falhas = [], []
    for q in BUSCAS:
        url = ("https://news.google.com/rss/search?q=" + urllib.parse.quote(q + " when:2d")
               + "&hl=pt-BR&gl=BR&ceid=BR:pt-419")
        try:
            brutos += list(itens_rss(baixar(url)))
        except Exception as erro:
            falhas.append(f"busca '{q[:30]}…': {erro}")
    for nome, url in FEEDS.items():
        try:
            brutos += list(itens_rss(baixar(url), nome))
        except Exception as erro:
            falhas.append(f"{nome}: {erro}")
    vistos, itens = set(), []
    for n in sorted(brutos, key=lambda x: x["data"], reverse=True):
        if n["data"] < limite or n["data"] > agora + timedelta(hours=1):
            continue
        k = chave(n["titulo"])
        if k in vistos:
            continue
        c = classificar(n["titulo"])
        if not c:
            continue
        vistos.add(k)
        n["tipo"], n["uf"], n["prioridade"] = c
        n["data"] = n["data"].astimezone(timezone(timedelta(hours=-3))).isoformat(timespec="minutes")
        itens.append(n)
        if len(itens) >= MAXIMO:
            break
    return itens, falhas

def main():
    itens, falhas = coletar()
    for f in falhas:
        print("aviso:", f, file=sys.stderr)
    if not itens and SITE_ANTERIOR:   # tudo falhou: mantém a lista publicada antes
        try:
            anterior = json.loads(baixar(SITE_ANTERIOR + "/noticias.json"))
            anterior["mantida_da_execucao_anterior"] = True
            json.dump(anterior, open(SAIDA, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            print("nenhuma notícia nova coletada; mantida a lista anterior")
            return
        except Exception:
            pass
    saida = {"atualizado_em": datetime.now(timezone(timedelta(hours=-3))).isoformat(timespec="minutes"), "itens": itens}
    json.dump(saida, open(SAIDA, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{len(itens)} notícias gravadas em {SAIDA}")

if __name__ == "__main__":
    main()
