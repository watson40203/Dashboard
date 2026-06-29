#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dashboard de Pipeline e Previsibilidade (IM Incorporadora)
-----------------------------------------------------------
Segundo dashboard, separado do principal. Foco em gestão de pipeline:
pipeline ponderado, pacing do mês, win/loss rate, ciclo de venda,
forecast por vendedor e negócios parados.

Usa os MESMOS dados do RD Station CRM. Não depende do dashboard antigo
e não altera nada dele. Gera o arquivo: dashboard_pipeline.html
"""

import json
import os
import calendar
from datetime import datetime
from collections import defaultdict

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURAÇÃO (pode ser sobrescrita pelo arquivo config_pipeline.json)
# ─────────────────────────────────────────────────────────────────────────────

CONFIG_FILE = "config_pipeline.json"

# Meta de VGV por mês (padrão = mesma do dashboard principal)
DEFAULT_META_MENSAL = 2095240.14

# Peso/probabilidade de cada etapa (em %). A chave é uma "palavra-chave":
# se ela aparecer no nome da etapa do RD Station, o peso é aplicado.
# Assim funciona mesmo que o nome exato da etapa seja um pouco diferente.
DEFAULT_PESOS = {
    "lead": 5,
    "contato": 10,
    "agendamento": 20,
    "atendimento": 35,
    "visita": 35,
    "proposta": 45,
    "negocia": 55,
    "fecha": 100,
    "ganho": 100,
}

# Quantos dias sem movimentação para um negócio ser considerado "parado"
DIAS_PARADO = 14


def carregar_config():
    cfg = {"meta_vgv_mensal": DEFAULT_META_MENSAL, "pesos": dict(DEFAULT_PESOS), "dias_parado": DIAS_PARADO}
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                if data.get("meta_vgv_mensal"):
                    cfg["meta_vgv_mensal"] = float(data["meta_vgv_mensal"])
                if isinstance(data.get("pesos"), dict) and data["pesos"]:
                    cfg["pesos"] = {str(k).lower(): float(v) for k, v in data["pesos"].items()}
                if data.get("dias_parado"):
                    cfg["dias_parado"] = int(data["dias_parado"])
            print(f"Config carregada de {CONFIG_FILE}")
    except Exception as e:
        print(f"Config: usando padrão ({e})")
    return cfg


def peso_da_etapa(stage, pesos):
    s = (stage or "").lower()
    for kw, w in pesos.items():
        if kw in s:
            return w
    return 50  # padrão se a etapa não casar com nenhuma palavra-chave


def classificar(stage):
    s = (stage or "").lower()
    if "perdid" in s or "perda" in s:
        return "perdido"
    if "fecha" in s or "ganho" in s or "ganha" in s or "ganhamos" in s:
        return "ganho"
    return "aberto"


# ─────────────────────────────────────────────────────────────────────────────
# BUSCA NO RD STATION CRM
# ─────────────────────────────────────────────────────────────────────────────

def buscar_crm():
    import requests
    token = os.environ.get("TOKEN_CRM", "")
    if not token:
        print("AVISO: TOKEN_CRM nao configurado — dashboard sai vazio.")
        return []

    todas = []
    pagina = 1
    while True:
        url = f"https://crm.rdstation.com/api/v1/deals?token={token}&limit=200&page={pagina}"
        try:
            r = requests.get(url, timeout=20)
            if r.status_code != 200:
                print(f"Erro pagina {pagina}: HTTP {r.status_code}")
                break
            negs = r.json().get("deals", [])
            if not negs:
                break
            todas.extend(negs)
            print(f"Pipeline: pagina {pagina} — {len(negs)} negocios")
            if len(negs) < 200:
                break
            pagina += 1
        except Exception as e:
            print(f"Erro CRM pagina {pagina}: {e}")
            break

    deals = []
    for n in todas:
        try:
            stage = (n.get("deal_stage") or {}).get("name", "Sem etapa")
            valor = n.get("amount_total") or 0
            try:
                valor = float(valor)
            except Exception:
                valor = 0.0
            criado = str(n.get("created_at") or "")[:10]
            fechado = n.get("closed_at")
            fechado = str(fechado)[:10] if fechado else None
            atualizado = n.get("updated_at")
            atualizado = str(atualizado)[:10] if atualizado else None
            # motivo de perda (campo varia; tentamos os mais comuns)
            motivo = ""
            for campo in ("deal_lost_reason", "loss_reason", "lost_reason"):
                lr = n.get(campo)
                if isinstance(lr, dict) and lr.get("name"):
                    motivo = lr["name"]
                    break
                if isinstance(lr, str) and lr:
                    motivo = lr
                    break
            user = n.get("user") or {}
            resp = user.get("name", "Sem responsável") if isinstance(user, dict) else "Sem responsável"
            deals.append({
                "stage": stage,
                "value": valor,
                "created_at": criado,
                "closed_at": fechado,
                "updated_at": atualizado,
                "loss_reason": motivo,
                "user": resp or "Sem responsável",
            })
        except Exception as e:
            print(f"Erro processando negocio: {e}")
    return deals


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def R(v):
    """Formata em R$ no padrão brasileiro."""
    try:
        s = f"{float(v):,.2f}"
    except Exception:
        s = "0,00"
    return "R$ " + s.replace(",", "X").replace(".", ",").replace("X", ".")


def R0(v):
    try:
        return "R$ " + f"{round(float(v)):,}".replace(",", ".")
    except Exception:
        return "R$ 0"


def cor_pct(p):
    if p >= 100:
        return "var(--green)"
    if p >= 50:
        return "var(--yellow)"
    return "var(--red)"


def dias_desde(data_str):
    if not data_str:
        return None
    try:
        d = datetime.strptime(data_str, "%Y-%m-%d").date()
        return (datetime.now().date() - d).days
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# GERADOR DO HTML
# ─────────────────────────────────────────────────────────────────────────────

CSS = """
*{margin:0;padding:0;box-sizing:border-box}
:root{
  --bg:#f5f5f7;--card:#fff;--t:#1d1d1f;--t2:#6e6e73;--t3:#aeaeb2;--bd:#e3e3e6;
  --bl:#0071e3;--gr:#28cd41;--rd:#ff3b30;--or:#ff9500;--yellow:#ffcc00;--pu:#5e5ce6;
  --green:#28cd41;--red:#ff3b30;
}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:var(--bg);color:var(--t);-webkit-font-smoothing:antialiased;padding:24px 16px 60px}
.wrap{max-width:1180px;margin:0 auto}
.top{display:flex;align-items:center;gap:14px;margin-bottom:6px}
.logo{width:34px;height:34px;border-radius:8px;background:var(--bl);color:#fff;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:14px}
h1{font-size:26px;font-weight:700;letter-spacing:-.02em}
.sub{color:var(--t2);font-size:13px;margin-bottom:28px}
.sec{font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--t3);margin:34px 0 14px}
.grid{display:grid;gap:14px}
.g4{grid-template-columns:repeat(4,1fr)}
.g3{grid-template-columns:repeat(3,1fr)}
.g2{grid-template-columns:repeat(2,1fr)}
@media(max-width:900px){.g4,.g3{grid-template-columns:repeat(2,1fr)}}
@media(max-width:620px){.g4,.g3,.g2{grid-template-columns:1fr}}
.card{background:var(--card);border:1px solid var(--bd);border-radius:14px;padding:18px}
.k-lbl{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:var(--t3);margin-bottom:8px}
.k-val{font-size:25px;font-weight:700;letter-spacing:-.02em;line-height:1.1}
.k-sub{font-size:12px;color:var(--t2);margin-top:6px}
.hero{background:var(--bl);color:#fff;border:none}
.hero .k-lbl{color:rgba(255,255,255,.7)}
.hero .k-sub{color:rgba(255,255,255,.85)}
.bar{height:9px;background:#ededf0;border-radius:5px;overflow:hidden;margin:10px 0 6px}
.bar.dark{background:rgba(255,255,255,.25)}
.bar>div{height:100%;border-radius:5px;transition:width .4s}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--bd);border-radius:14px;overflow:hidden}
th,td{text-align:left;padding:12px 16px;font-size:13.5px;border-bottom:1px solid var(--bd)}
th{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:var(--t3);background:#fafafc}
tr:last-child td{border-bottom:none}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
.pill{display:inline-block;padding:3px 9px;border-radius:20px;font-size:11px;font-weight:700}
.minibar{height:7px;background:#ededf0;border-radius:4px;overflow:hidden;min-width:90px}
.minibar>div{height:100%}
.tag{font-size:11px;color:var(--t2)}
.empty{color:var(--t3);font-size:14px;padding:16px;background:var(--card);border:1px dashed var(--bd);border-radius:14px}
.note{font-size:12px;color:var(--t2);margin:6px 0 0}
.foot{margin-top:40px;font-size:11px;color:var(--t3);text-align:center}
"""


def gerar_dashboard(deals, cfg):
    pesos = cfg["pesos"]
    meta_mensal = cfg["meta_vgv_mensal"]
    limite_parado = cfg["dias_parado"]

    abertos = [d for d in deals if classificar(d["stage"]) == "aberto"]
    ganhos = [d for d in deals if classificar(d["stage"]) == "ganho"]
    perdidos = [d for d in deals if classificar(d["stage"]) == "perdido"]

    # ── Pipeline ponderado ────────────────────────────────────────────────
    pipe_total = sum(d["value"] for d in abertos)
    por_etapa = defaultdict(lambda: {"valor": 0.0, "pond": 0.0, "n": 0, "peso": 0})
    for d in abertos:
        w = peso_da_etapa(d["stage"], pesos)
        por_etapa[d["stage"]]["valor"] += d["value"]
        por_etapa[d["stage"]]["pond"] += d["value"] * w / 100.0
        por_etapa[d["stage"]]["n"] += 1
        por_etapa[d["stage"]]["peso"] = w
    pipe_pond = sum(v["pond"] for v in por_etapa.values())
    etapas_ord = sorted(por_etapa.items(), key=lambda kv: kv[1]["peso"])

    # ── Win / Loss ────────────────────────────────────────────────────────
    n_ganho, n_perda = len(ganhos), len(perdidos)
    win_rate = (n_ganho / (n_ganho + n_perda) * 100) if (n_ganho + n_perda) else 0
    valor_ganho_total = sum(d["value"] for d in ganhos)

    # ── Ciclo de venda médio ──────────────────────────────────────────────
    ciclos = []
    for d in ganhos:
        if d["created_at"] and d["closed_at"]:
            try:
                c = datetime.strptime(d["created_at"], "%Y-%m-%d").date()
                f = datetime.strptime(d["closed_at"], "%Y-%m-%d").date()
                if (f - c).days >= 0:
                    ciclos.append((f - c).days)
            except Exception:
                pass
    ciclo_medio = round(sum(ciclos) / len(ciclos)) if ciclos else 0

    # ── Pacing do mês ─────────────────────────────────────────────────────
    hoje = datetime.now()
    mes_tag = hoje.strftime("%Y-%m")
    dias_no_mes = calendar.monthrange(hoje.year, hoje.month)[1]
    dia_atual = hoje.day
    realizado_mes = sum(d["value"] for d in ganhos if (d["closed_at"] or "").startswith(mes_tag))
    pct_realizado = (realizado_mes / meta_mensal * 100) if meta_mensal else 0
    pct_tempo = dia_atual / dias_no_mes * 100
    esperado_hoje = meta_mensal * pct_tempo / 100
    no_ritmo = realizado_mes >= esperado_hoje

    # ── Forecast por vendedor ─────────────────────────────────────────────
    vend = defaultdict(lambda: {"pipe": 0.0, "pond": 0.0, "ganho": 0.0, "ng": 0, "na": 0})
    for d in deals:
        cl = classificar(d["stage"])
        if cl == "ganho":
            vend[d["user"]]["ganho"] += d["value"]
            vend[d["user"]]["ng"] += 1
        elif cl == "aberto":
            w = peso_da_etapa(d["stage"], pesos)
            vend[d["user"]]["pipe"] += d["value"]
            vend[d["user"]]["pond"] += d["value"] * w / 100.0
            vend[d["user"]]["na"] += 1
    vend_ord = sorted(vend.items(), key=lambda kv: kv[1]["pond"] + kv[1]["ganho"], reverse=True)

    # ── Motivos de perda ──────────────────────────────────────────────────
    motivos = defaultdict(lambda: {"n": 0, "valor": 0.0})
    for d in perdidos:
        m = d["loss_reason"] or "Não informado"
        motivos[m]["n"] += 1
        motivos[m]["valor"] += d["value"]
    motivos_ord = sorted(motivos.items(), key=lambda kv: kv[1]["n"], reverse=True)

    # ── Negócios parados ──────────────────────────────────────────────────
    parados = []
    for d in abertos:
        ref = d["updated_at"] or d["created_at"]
        dd = dias_desde(ref)
        if dd is not None and dd > limite_parado:
            parados.append({**d, "dias": dd})
    parados.sort(key=lambda d: d["value"], reverse=True)
    valor_parado = sum(d["value"] for d in parados)

    # ─────────────────────────────────────────────────────────────────────
    # MONTAGEM DO HTML
    # ─────────────────────────────────────────────────────────────────────
    agora = hoje.strftime("%d/%m/%Y às %H:%M")

    # Cartões de topo
    cobertura = (pipe_pond / meta_mensal * 100) if meta_mensal else 0
    topo = f"""
      <div class="card hero">
        <div class="k-lbl">Previsão de fechamento (pipeline ponderado)</div>
        <div class="k-val">{R(pipe_pond)}</div>
        <div class="bar dark"><div style="width:{min(cobertura,100):.0f}%;background:#fff"></div></div>
        <div class="k-sub">{cobertura:.0f}% da meta mensal ({R0(meta_mensal)}) — de {R(pipe_total)} em aberto</div>
      </div>
      <div class="card">
        <div class="k-lbl">Win Rate</div>
        <div class="k-val" style="color:{cor_pct(win_rate)}">{win_rate:.0f}%</div>
        <div class="k-sub">{n_ganho} ganhos / {n_perda} perdidos</div>
      </div>
      <div class="card">
        <div class="k-lbl">Ciclo de venda médio</div>
        <div class="k-val">{ciclo_medio} dias</div>
        <div class="k-sub">da criação até o fechamento ({len(ciclos)} negócios)</div>
      </div>
      <div class="card">
        <div class="k-lbl">Negócios em aberto</div>
        <div class="k-val">{len(abertos)}</div>
        <div class="k-sub">{R(pipe_total)} no total da esteira</div>
      </div>
    """

    # Pacing
    cor_pace = "var(--green)" if no_ritmo else ("var(--yellow)" if pct_realizado >= 50 else "var(--red)")
    status_txt = "No ritmo da meta" if no_ritmo else "Abaixo do ritmo"
    pacing = f"""
      <div class="card">
        <div class="k-lbl">Pacing — {MESES_PT[hoje.month-1]} (dia {dia_atual} de {dias_no_mes})</div>
        <div style="display:flex;align-items:baseline;gap:10px;flex-wrap:wrap">
          <div class="k-val">{R(realizado_mes)}</div>
          <div class="k-sub">realizado de {R0(meta_mensal)} de meta</div>
        </div>
        <div class="bar"><div style="width:{min(pct_realizado,100):.1f}%;background:{cor_pace}"></div></div>
        <div class="k-sub">
          <span class="pill" style="background:{cor_pace}1a;color:{cor_pace}">{status_txt}</span>
          &nbsp; Você está em <strong>{pct_realizado:.0f}%</strong> da meta e o mês está em <strong>{pct_tempo:.0f}%</strong>.
          No ritmo do calendário, o esperado hoje seria <strong>{R0(esperado_hoje)}</strong>.
        </div>
      </div>
    """

    # Tabela pipeline ponderado por etapa
    if etapas_ord:
        linhas = ""
        max_pond = max((v["pond"] for _, v in etapas_ord), default=1) or 1
        for etapa, v in etapas_ord:
            largura = v["pond"] / max_pond * 100
            linhas += f"""<tr>
              <td><strong>{etapa}</strong></td>
              <td class="num">{v['peso']:.0f}%</td>
              <td class="num">{v['n']}</td>
              <td class="num">{R(v['valor'])}</td>
              <td class="num" style="font-weight:700">{R(v['pond'])}</td>
              <td style="width:160px"><div class="minibar"><div style="width:{largura:.0f}%;background:var(--bl)"></div></div></td>
            </tr>"""
        tab_etapas = f"""<table>
          <thead><tr><th>Etapa</th><th class="num">Peso</th><th class="num">Qtd</th><th class="num">Valor bruto</th><th class="num">Ponderado</th><th>Peso visual</th></tr></thead>
          <tbody>{linhas}</tbody>
        </table>
        <p class="note">Ponderado = valor do negócio × probabilidade da etapa. É a previsão realista de fechamento. Ajuste os pesos no arquivo <strong>config_pipeline.json</strong>.</p>"""
    else:
        tab_etapas = '<div class="empty">Nenhum negócio em aberto no momento.</div>'

    # Forecast por vendedor
    if vend_ord:
        linhas = ""
        for nome, v in vend_ord:
            linhas += f"""<tr>
              <td><strong>{nome}</strong></td>
              <td class="num">{v['na']}</td>
              <td class="num">{R(v['pipe'])}</td>
              <td class="num" style="font-weight:700;color:var(--bl)">{R(v['pond'])}</td>
              <td class="num">{v['ng']}</td>
              <td class="num" style="color:var(--gr)">{R(v['ganho'])}</td>
            </tr>"""
        tab_vend = f"""<table>
          <thead><tr><th>Vendedor</th><th class="num">Abertos</th><th class="num">Pipeline</th><th class="num">Previsão</th><th class="num">Ganhos (qtd)</th><th class="num">Ganho R$</th></tr></thead>
          <tbody>{linhas}</tbody>
        </table>"""
    else:
        tab_vend = '<div class="empty">Sem dados de vendedores.</div>'

    # Motivos de perda
    if motivos_ord:
        linhas = ""
        tot_perda = sum(m["n"] for _, m in motivos_ord) or 1
        for motivo, m in motivos_ord:
            pct = m["n"] / tot_perda * 100
            linhas += f"""<tr>
              <td>{motivo}</td>
              <td class="num">{m['n']}</td>
              <td class="num">{pct:.0f}%</td>
              <td class="num">{R(m['valor'])}</td>
            </tr>"""
        tab_perda = f"""<table>
          <thead><tr><th>Motivo da perda</th><th class="num">Qtd</th><th class="num">%</th><th class="num">Valor perdido</th></tr></thead>
          <tbody>{linhas}</tbody>
        </table>
        <p class="note">Os motivos só aparecem se forem preenchidos no RD Station — é a higiene de CRM que o João Olivério recomenda.</p>"""
    else:
        tab_perda = '<div class="empty">Nenhum negócio perdido registrado (ou sem motivo preenchido).</div>'

    # Negócios parados
    if parados:
        linhas = ""
        for d in parados[:25]:
            cor_d = "var(--rd)" if d["dias"] > 30 else "var(--or)"
            linhas += f"""<tr>
              <td>{d['stage']}</td>
              <td>{d['user']}</td>
              <td class="num">{R(d['value'])}</td>
              <td class="num"><span style="color:{cor_d};font-weight:700">{d['dias']} dias</span></td>
            </tr>"""
        extra = f'<p class="note">Mostrando os 25 maiores de {len(parados)} negócios parados.</p>' if len(parados) > 25 else ""
        tab_parados = f"""<table>
          <thead><tr><th>Etapa</th><th>Vendedor</th><th class="num">Valor</th><th class="num">Parado há</th></tr></thead>
          <tbody>{linhas}</tbody>
        </table>{extra}"""
    else:
        tab_parados = '<div class="empty">Nenhum negócio parado há mais de ' + str(limite_parado) + ' dias. Pipeline saudável!</div>'

    html = f"""<!DOCTYPE html>
<html lang="pt-br">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pipeline & Previsibilidade — IM Incorporadora</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
  <div class="top">
    <div class="logo">IM</div>
    <h1>Pipeline & Previsibilidade</h1>
  </div>
  <div class="sub">Dados do RD Station CRM — atualizado em {agora}</div>

  <div class="sec">Visão geral</div>
  <div class="grid g4">{topo}</div>

  <div class="sec">Ritmo do mês (pacing)</div>
  <div class="grid">{pacing}</div>

  <div class="sec">Pipeline ponderado por etapa</div>
  {tab_etapas}

  <div class="sec">Previsão por vendedor</div>
  {tab_vend}

  <div class="grid g2" style="margin-top:8px">
    <div>
      <div class="sec" style="margin-top:18px">Motivos de perda</div>
      {tab_perda}
    </div>
    <div>
      <div class="sec" style="margin-top:18px">Total ganho no período</div>
      <div class="card">
        <div class="k-lbl">Receita ganha (negócios fechados)</div>
        <div class="k-val" style="color:var(--gr)">{R(valor_ganho_total)}</div>
        <div class="k-sub">{n_ganho} negócios ganhos · valor em risco parado: {R(valor_parado)}</div>
      </div>
    </div>
  </div>

  <div class="sec">Negócios parados (sem movimentação há +{limite_parado} dias)</div>
  {tab_parados}

  <div class="foot">Dashboard de pipeline · gerado automaticamente · IM Incorporadora</div>
</div>
</body>
</html>"""

    with open("dashboard_pipeline.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"OK: dashboard_pipeline.html gerado ({len(html)} bytes)")
    return html


MESES_PT = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
            "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cfg = carregar_config()
    deals = buscar_crm()
    print(f"Total de negocios: {len(deals)}")
    gerar_dashboard(deals, cfg)
    print("Concluido!")
