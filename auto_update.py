#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
auto_update.py — 自包含网页更新器（可飞牧场）
在「定时任务沙箱」里运行，无需本地文件、无需云盘工具。
只需：能跑 Python + 能联网访问 GitHub。定时任务沙箱均具备。

工作流程（全自动，无人值守）：
  1. 从 GitHub 公开仓库下载最新 data.json（含上次保存的所有数据）
  2. 接收本次定时任务取数结果（命令行 JSON 或环境变量 UPDATE_JSON）
  3. 把取数结果合并进 data.json（覆盖行情字段 + 更新 lastUpdate）
  4. 内置生成逻辑 -> 生成单文件 index.html（含持仓/交易/选股池等全部）
  5. 用 GitHub API（token 参数）推送新的 data.json 和 index.html 回仓库
  6. GitHub Pages 自动重新部署，网页刷新

用法：
  python3 auto_update.py <github_token> [本次更新的JSON字符串]

  <本次更新的JSON> 可为空字符串。格式示例：
  '{"indices":[{"name":"上证指数","value":"3xxx","change":"+x.xx","direction":"up"}],
    "globalMarkets":[{"name":"纳斯达克","value":"x","change":"-x.xx","direction":"down"},
                     {"name":"富时A50","value":"x","change":"+x.xx","direction":"up"},
                     {"name":"伦敦金现","value":"x","change":"+x.xx","direction":"up"},
                     {"name":"布伦特原油","value":"x","change":"+x.xx","direction":"up"}],
    "hotSectorsToday":[...],"mainFlow":{...},"news":[...],"review":{...},
    "positions":[{"name":"铜陵有色","code":"000630","price":"x","cost":"x","pnl":"+x%","weight":"x%","sector":"...","strategy":"...","status":"..."}],
    "posSummary":{...},"fate":[{"h":"小标题","p":"正文"}],"lastUpdate":"2026-08-21 19:10 · 盘后复盘"}'

  token 也可通过环境变量 GITHUB_TOKEN 传入。
"""
import base64
import json
import math
import os
import sys
import urllib.request
import urllib.error

REPO_OWNER = "kele-1006"
REPO_NAME = "kefei-ranch-dashboard"
REPO = f"{REPO_OWNER}/{REPO_NAME}"
API = "https://api.github.com"
RAW = f"https://raw.githubusercontent.com/{REPO}/main"
BRANCH = "main"

DATA_FILE = "data.json"
HTML_FILE = "index.html"


# ---------------- GitHub HTTP ----------------
def http(method, url, token=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "kefei-auto-update")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"raw": raw}


def download_file(name):
    """从公开仓库下载文件内容。"""
    url = f"{RAW}/{name}"
    try:
        with urllib.request.urlopen(url, timeout=60) as resp:
            return resp.read().decode("utf-8")
    except Exception as e:
        print(f"⚠️ 下载 {name} 失败: {e}")
        return None


# ---------------- 数据加载 ----------------
def load_data():
    """优先 GitHub 上的 data.json，否则空模板。"""
    content = download_file(DATA_FILE)
    if content:
        try:
            return json.loads(content)
        except Exception as e:
            print(f"⚠️ 解析 data.json 失败: {e}")
    return {}


# ---------------- 生成逻辑（由 build_dashboard.py 提取） ----------------
def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def updown(direction):
    return "up" if direction == "up" else "down"


def fmt_change(c):
    c = str(c)
    return c if c.startswith(("-", "+")) else ("+" + c)


def build_html(d):
    hotspot = d.get("hotspot", {})
    stock = d.get("stock", {})
    journal = d.get("journal", {})
    review = d.get("review", {})
    fate = d.get("fate", [])
    lastUpdate = d.get("lastUpdate", "")

    indices = hotspot.get("indices", [])
    # 隔夜外盘：优先用 globalMarkets（纳斯达克+富时A50+伦敦金现+布伦特原油），兼容旧 usMarkets
    globalMarkets = hotspot.get("globalMarkets") or hotspot.get("usMarkets", [])
    news = hotspot.get("news", [])
    macro = hotspot.get("macro", [])
    margin = hotspot.get("marginBalance", {})
    mainflow = hotspot.get("mainFlow", {})
    hotToday = hotspot.get("hotSectorsToday", [])
    hot5d = hotspot.get("hotSectors5d", [])
    strategies = stock.get("strategies", [])
    poolFlow = stock.get("poolFlow", {})
    diagnosis = stock.get("diagnosis", [])
    sectorPriority = stock.get("sectorPriority", [])
    posSum = journal.get("positionSummary", {})
    positions = journal.get("positions", [])
    alerts = journal.get("alerts", [])
    riskRules = journal.get("riskRules", [])
    hist = journal.get("history", {})
    histStats = hist.get("stats", {})
    histList = hist.get("list", [])
    stratStats = histStats.get("strategyStats", {})
    reviewPoints = review.get("points", [])

    def weight_val(w):
        return float(str(w).replace("%", ""))

    def index_cards(items):
        out = []
        for it in items:
            ud = updown(it.get("direction", ""))
            disp = it.get("short") or it.get("name", "")
            kcode = it.get("kcode", "")
            bk = it.get("bk", "")
            attrs = (f' data-src="{esc(it.get("ksrc","tx"))}" data-code="{esc(kcode)}"'
                     f' data-ref="{esc(it.get("ref",""))}" data-name="{esc(it.get("name",""))}"'
                     + (f' data-bk="{esc(bk)}"' if bk else "")) if kcode else ""
            cls = "idx-card klk" if kcode else "idx-card"
            out.append(
                f'<div class="{cls}"{attrs}><div class="idx-name">{esc(disp)}</div>'
                f'<div class="idx-value {ud}">{esc(it.get("value",""))}</div>'
                f'<div class="idx-change {ud}"><span class="arr">{"▲" if ud=="up" else "▼"}</span>{fmt_change(it.get("change",""))}</div></div>')
        return "".join(out)

    def sector_bars(items, is_today):
        if not items:
            return ""
        max_c = max(it["change"] for it in items)
        bars = []
        for it in items:
            w = max(8, it["change"] / max_c * 100)
            pos = it["change"] >= 0
            kcode = it.get("kcode", "")
            bk = it.get("bk", "")
            attrs = (f' data-src="{esc(it.get("ksrc","tx"))}" data-code="{esc(kcode)}"'
                     f' data-ref="{esc(it.get("ref",""))}" data-name="{esc(it.get("name",""))}"'
                     + (f' data-bk="{esc(bk)}"' if bk else "")) if kcode else ""
            cls = "sector-row klk-row" if kcode else "sector-row"
            bars.append(
                f'<div class="{cls}"{attrs}><div class="sector-name">{esc(it.get("name",""))}</div>'
                f'<div class="sector-track"><div class="sector-fill {"pos" if pos else "neg"}" style="width:{w}%"></div></div>'
                f'<div class="sector-val {"pos" if pos else "neg"}">{it["change"]:+.2f}%</div>'
                f'<div class="sector-inflow">{esc(it.get("inflow",""))}</div></div>')
        return "".join(bars)

    def news_list(items):
        out = []
        sent_map = {"up": "利多", "down": "利空", "neutral": "中性"}
        sent_cls = {"up": "tag-up", "down": "tag-down", "neutral": "tag-neutral"}
        for it in items:
            s = it.get("sentiment", "neutral")
            phase = it.get("phase", "")
            phase_cls = "ph-hold" if phase == "持仓" else "ph-pre"
            title = esc(it.get("title", ""))
            link = it.get("url", "")
            if link:
                title = f'<a href="{esc(link)}" target="_blank">{title}<span class="ext-arrow">↗</span></a>'
            out.append(
                f'<div class="news-item"><div class="news-meta"><span class="time">{esc(it.get("time",""))}</span>'
                f'<span class="phase {phase_cls}">{esc(phase)}</span>'
                f'<span class="tag {sent_cls[s]}">{sent_map[s]}</span></div>'
                f'<div class="news-title">{title}</div>'
                f'<div class="news-rel">{esc(it.get("related",""))}</div></div>')
        return "".join(out)

    def macro_list(items):
        out = []
        type_map = {"up": "利多", "down": "利空", "neutral": "中性"}
        type_cls = {"up": "tag-up", "down": "tag-down", "neutral": "tag-neutral"}
        for it in items:
            t = it.get("type", "neutral")
            out.append(
                f'<div class="macro-item"><div class="macro-tag"><span class="tag {type_cls[t]}">{type_map[t]}</span>'
                f'<span class="macro-key">{esc(it.get("tag",""))}</span></div>'
                f'<div class="macro-text">{esc(it.get("text",""))}</div></div>')
        return "".join(out)

    def positions_rows(items):
        rows = []
        for p in items:
            ud = updown("up" if float(str(p.get("pnl","0")).replace("%","").replace("+","") or 0) >= 0 else "down")
            try:
                cost = float(p["cost"]); price = float(p["price"])
                pnl_num = (price/cost-1)*100 if cost else 0
            except Exception:
                pnl_num = 0
            ud = "up" if pnl_num >= 0 else "down"
            w = weight_val(p.get("weight", "0%"))
            rows.append(
                f'<tr><td><div class="p-name">{esc(p.get("name",""))}</div><div class="p-code">{esc(p.get("code",""))}</div></td>'
                f'<td><div class="p-sect">{esc(p.get("sector",""))}</div><div class="p-strat">{esc(p.get("strategy",""))}</div></td>'
                f'<td class="num">{esc(p.get("price",""))}</td><td class="num">{esc(p.get("cost",""))}</td>'
                f'<td class="num {ud}">{esc(p.get("pnl",""))}</td>'
                f'<td><div class="wbar"><div class="wfill" style="width:{min(100,w/25*100)}%"></div><span>{w:.0f}%</span></div></td>'
                f'<td><span class="p-status">{esc(p.get("status",""))}</span></td></tr>')
        return "".join(rows)

    def history_rows(items):
        # 全量历史（调用方已按 newest-first 传入）
        rows = []
        for p in items:
            try:
                rn = float(p.get("returnNum", 0))
            except Exception:
                rn = 0
            ud = "up" if rn >= 0 else "down"
            rows.append(
                f'<tr><td><div class="p-name">{esc(p.get("name",""))}</div><div class="p-code">{esc(p.get("code",""))}</div></td>'
                f'<td class="p-sect">{esc(p.get("sector",""))}</td>'
                f'<td class="num">{p.get("buyDate","")}</td><td class="num">{p.get("sellDate","")}</td>'
                f'<td class="num">{esc(p.get("buyPrice",""))} → {esc(p.get("sellPrice",""))}</td>'
                f'<td class="num {ud}">{esc(p.get("return",""))}</td>'
                f'<td><span class="tag-strat">{esc(p.get("strategy",""))}</span></td></tr>')
        return "".join(rows)

    def strat_cards(stats):
        out = []
        order = ["情绪流", "极点战法", "依依不舍", "骐骥一跃"]
        palette = {"情绪流": "#4f8cff", "极点战法": "#f5a623", "依依不舍": "#38d9c2", "骐骥一跃": "#a78bfa"}
        for s in order:
            if s not in stats:
                continue
            st = stats[s]
            wr = st.get("winRate", 0)
            col = palette.get(s, "#4f8cff")
            out.append(
                f'<div class="strat-card" style="--sc:{col}"><div class="strat-head"><span class="strat-name">{esc(s)}</span>'
                f'<span class="strat-trades">{st.get("trades",0)} 笔</span></div>'
                f'<div class="strat-nums"><span class="win">{st.get("wins",0)}胜</span><span class="loss">{st.get("losses",0)}负</span>'
                f'<span class="even">{st.get("evens",0)}平</span></div>'
                f'<div class="strat-bar"><div class="strat-fill" style="width:{wr}%;background:{col}"></div></div>'
                f'<div class="strat-wr" style="color:{col}">胜率 {wr}%</div></div>')
        return "".join(out)

    def pool_funnel(levels):
        total = sum(l["count"] for l in levels) if levels else 0
        bars = []
        for i, l in enumerate(levels):
            pct = l["count"]/total*100 if total else 0
            width = max(25, 100 - i*20)
            bars.append(
                f'<div class="funnel-row"><div class="funnel-label">{esc(l["name"])}</div>'
                f'<div class="funnel-track"><div class="funnel-fill" style="width:{width}%;background:{l["color"]}">'
                f'<span class="funnel-count">{l["count"]}</span></div></div>'
                f'<div class="funnel-pct">{pct:.0f}%</div></div>')
        return "".join(bars)

    def diag_cards(items):
        out = []
        for it in items:
            sc = it.get("score", 0)
            pool_cls = "diag-core" if it.get("pool") == "核心池" else "diag-watch"
            out.append(
                f'<div class="diag-card"><div class="diag-head"><div class="diag-name">{esc(it.get("name",""))} '
                f'<span class="diag-code">{esc(it.get("code",""))}</span></div><span class="diag-pool {pool_cls}">{esc(it.get("pool",""))}</span></div>'
                f'<div class="diag-score"><span class="score-num">{sc}</span><span class="score-total">/100</span></div>'
                f'<div class="score-track"><div class="score-fill" style="width:{sc}%"></div></div>'
                f'<div class="diag-strat"><span class="tag-strat">{esc(it.get("strategy",""))}</span></div>'
                f'<div class="diag-risk">⚠ {esc(it.get("risk",""))}</div></div>')
        return "".join(out)

    def priority_list(items):
        out = []
        pmap = {"高": "tag-up", "中": "tag-neutral", "低": "tag-down"}
        for it in items:
            pr = it.get("priority", "中")
            out.append(
                f'<div class="prio-item"><div class="prio-head"><span class="prio-name">{esc(it.get("name",""))}</span>'
                f'<span class="tag {pmap.get(pr,"tag-neutral")}">{esc(pr)}优先</span></div>'
                f'<div class="prio-reason">{esc(it.get("reason",""))}</div></div>')
        return "".join(out)

    def alerts_list(items):
        out = []
        for a in items:
            t = a.get("type", "")
            tone = "al-up" if ("加仓" in t or "🟢" in t) else "al-down" if ("🚨" in t or "止损" in t) else "al-mid"
            out.append(
                f'<div class="alert-item {tone}"><div class="alert-head"><span class="alert-type">{esc(t)}</span>'
                f'<span class="alert-name">{esc(a.get("name",""))}</span></div>'
                f'<div class="alert-detail">{esc(a.get("detail",""))}</div></div>')
        return "".join(out)

    def review_points(items):
        out = []
        tmap = {"up": "利多", "down": "利空", "neutral": "中性"}
        tcls = {"up": "tag-up", "down": "tag-down", "neutral": "tag-neutral"}
        for it in items:
            t = it.get("type", "neutral")
            out.append(
                f'<div class="rv-item"><span class="rv-dot {tcls[t]}"></span>'
                f'<span class="tag {tcls[t]}">{tmap[t]}</span>'
                f'<span class="rv-text">{esc(it.get("text",""))}</span></div>')
        return "".join(out)

    def fate_html(items):
        if not items:
            return '<div class="fate-empty">本期「缘起性空」内容整理中，敬请期待。</div>'
        out = []
        for i, it in enumerate(items, 1):
            if isinstance(it, dict):
                h = it.get("h", "")
                p = esc(it.get("p", "")).replace("\n", "<br>")
                out.append(
                    f'<div class="fate-block"><div class="fate-quote">❝</div>'
                    f'<div class="fate-h"><span class="fate-idx">{i:02d}</span>{esc(h)}</div>'
                    f'<div class="fate-p">{p}</div></div>')
            else:
                out.append(f'<div class="fate-block"><div class="fate-quote">❝</div><div class="fate-p">{esc(it)}</div></div>')
        return "".join(out)

    # 持仓环形图（SVG path arc 精确绘制，首尾强制闭合）
    try:
        pos_weights = [weight_val(p["weight"]) for p in positions]
    except Exception:
        pos_weights = []
    cash_weight = max(0, 100 - sum(pos_weights))
    segments = []
    colors = ["#4f8cff", "#38d9c2", "#f5a623", "#ff6b81", "#a78bfa", "#f472b6"]
    angle = 0.0
    for i, p in enumerate(positions):
        pct = weight_val(p["weight"])
        color = colors[i % len(colors)]
        segments.append({"name": p["name"], "pct": pct, "color": color, "start": angle, "end": angle + pct*3.6})
        angle += pct*3.6
    # 现金段强制延伸到 360°，保证环形闭合无缺口
    cash_seg = {"name": "现金", "pct": cash_weight, "color": "#2a2f45", "start": angle, "end": 360.0}
    r = 80

    def _pt(deg):
        rad = math.radians(deg)
        return 100 + r*math.sin(rad), 100 - r*math.cos(rad)

    donut_parts = []
    for s in segments + [cash_seg]:
        a, b = s["start"], s["end"]
        if b <= a + 0.01:
            continue
        b = min(b, 360.0)
        if a >= 359.99:
            continue
        x1, y1 = _pt(a)
        if (b - a) >= 359.9:
            # 整圆：拆两段半圆弧
            xm, ym = _pt(a + 180)
            x2, y2 = _pt(b)
            donut_parts.append(f'<path d="M {x1:.2f} {y1:.2f} A {r} {r} 0 1 1 {xm:.2f} {ym:.2f}" fill="none" stroke="{s["color"]}" stroke-width="20"/>')
            donut_parts.append(f'<path d="M {xm:.2f} {ym:.2f} A {r} {r} 0 1 1 {x2:.2f} {y2:.2f}" fill="none" stroke="{s["color"]}" stroke-width="20"/>')
        else:
            x2, y2 = _pt(b)
            large = 1 if (b - a) > 180 else 0
            donut_parts.append(f'<path d="M {x1:.2f} {y1:.2f} A {r} {r} 0 {large} 1 {x2:.2f} {y2:.2f}" fill="none" stroke="{s["color"]}" stroke-width="20"/>')
    donut_svg = ('<svg viewBox="0 0 200 200" class="donut">' + "".join(donut_parts) +
                 f'<text x="100" y="94" text-anchor="middle" class="donut-num">{esc(posSum.get("total","0"))}</text>'
                 f'<text x="100" y="116" text-anchor="middle" class="donut-label">总仓位</text></svg>')

    # 胜率环
    wr = histStats.get("winRate", 0)
    try:
        pct = float(str(wr).replace("%", ""))
    except Exception:
        pct = 0
    rr = 70; rc = 2*3.14159*rr; frac = pct/100
    pct_ring = (f'<svg viewBox="0 0 200 200" class="ring">'
                f'<circle cx="100" cy="100" r="{rr}" fill="none" stroke="#1d2440" stroke-width="16"/>'
                f'<circle cx="100" cy="100" r="{rr}" fill="none" stroke="url(#gg1)" stroke-width="16" stroke-linecap="round" stroke-dasharray="{frac*rc:.2f} {rc:.2f}" transform="rotate(-90 100 100)"/>'
                f'<text x="100" y="97" text-anchor="middle" class="ring-num">{pct:.1f}%</text>'
                f'<text x="100" y="118" text-anchor="middle" class="ring-label">胜率</text></svg>')

    def kpi_card(label, value, sub, tone=""):
        return f'<div class="kpi {tone}"><div class="kpi-label">{label}</div><div class="kpi-value">{value}</div><div class="kpi-sub">{sub}</div></div>'

    legend = "".join(
        f'<div class="legend-item"><div class="legend-l"><span class="legend-c" style="background:{s["color"]}"></span>{esc(s["name"])}</div><span class="legend-val">{s["pct"]:.0f}%</span></div>'
        for s in segments)
    legend += f'<div class="legend-item"><div class="legend-l"><span class="legend-c" style="background:{cash_seg["color"]}"></span>现金</div><span class="legend-val">{cash_seg["pct"]:.0f}%</span></div>'

    CSS = """
:root{--bg0:#070b16;--bg1:#0a1226;--bg2:#0d1833;--card:rgba(17,26,51,.72);--card2:rgba(23,35,66,.6);--line:rgba(90,130,255,.14);--line2:rgba(255,255,255,.06);--txt:#e9eefb;--txt2:#9aa6c9;--txt3:#6b7aa6;--up:#ff5470;--down:#2fd4a6;--accent:#4f8cff;--gold:#f5c451;--grad:linear-gradient(160deg,#4f8cff 0%,#8b5cf6 100%);--shadow:0 20px 60px rgba(0,0,0,.5)}
*{margin:0;padding:0;box-sizing:border-box}html{scroll-behavior:smooth}
body{font-family:"Inter","PingFang SC","HarmonyOS Sans SC","Microsoft YaHei",system-ui,sans-serif;color:var(--txt);background:radial-gradient(1200px 600px at 15% -10%,#12234d 0%,transparent 60%),radial-gradient(1000px 500px at 110% 10%,#1b1a3a 0%,transparent 55%),radial-gradient(800px 600px at 50% 120%,#0f1f4a 0%,transparent 60%),linear-gradient(160deg,var(--bg0) 0%,var(--bg1) 45%,var(--bg2) 100%);min-height:100vh;line-height:1.6;-webkit-font-smoothing:antialiased;overflow-x:hidden}
.wrap{position:relative;z-index:2;max-width:1280px;margin:0 auto;padding:28px 26px 60px}
.topbar{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:26px;gap:16px}
.brand{display:flex;align-items:center;gap:12px;min-width:0;flex:1}
.logo{width:46px;height:46px;border-radius:14px;background:linear-gradient(160deg,#ff5470 0%,#e8557d 55%,#8b5cf6 100%);display:flex;align-items:center;justify-content:center;font-size:25px;font-weight:800;color:#fff;text-shadow:0 2px 10px rgba(0,0,0,.35);flex-shrink:0;box-shadow:0 4px 16px rgba(232,85,125,.35)}
.brand-t{font-size:22px;font-weight:700;letter-spacing:.04em;line-height:1.25;white-space:nowrap}
.brand-cn{background:linear-gradient(110deg,#b9c7ee 0%,#b9c7ee 30%,#ffffff 42%,#ffffff 50%,#ffffff 58%,#b9c7ee 70%,#b9c7ee 100%);background-size:300% 100%;-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;animation:brandShine 6s linear infinite}
@keyframes brandShine{0%{background-position:150% 0}100%{background-position:0% 0}}
.brand-en{font-size:13.5px;color:var(--txt3);margin-left:8px;font-weight:600;letter-spacing:.03em;opacity:.85;white-space:nowrap}
.brand-s{font-size:12px;color:var(--txt3);margin-top:3px;letter-spacing:.12em}
.update{font-size:12px;color:var(--txt3);display:flex;align-items:center;gap:8px;flex-shrink:0;margin-top:6px;white-space:nowrap}
@media(max-width:640px){
.topbar{flex-direction:column;align-items:flex-start;margin-bottom:18px}
.brand{gap:11px;width:100%}
.logo{width:42px;height:42px;font-size:23px}
.brand-t{font-size:19px;display:flex;align-items:baseline;gap:6px;flex-wrap:wrap;white-space:nowrap}
.brand-en{font-size:12px;margin-left:0;opacity:.8}
.brand-s{font-size:11.5px}
.update{margin-top:6px;font-size:11px;white-space:normal;align-self:flex-start}
}
.dot{width:8px;height:8px;border-radius:50%;background:var(--down);box-shadow:0 0 10px var(--down)}
.nav{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:22px}
.nav-btn{padding:9px 18px;border-radius:11px;background:rgba(255,255,255,.04);border:1px solid var(--line2);color:var(--txt2);cursor:pointer;font-size:14px;font-family:inherit;white-space:nowrap}
.nav-btn.active{background:var(--grad);color:#fff;border-color:transparent;font-weight:500}
@media(max-width:640px){
.nav{gap:5px;margin-bottom:16px}
.nav-btn{padding:8px 13px;font-size:13px;border-radius:9px}
}
.section{display:none}.section.active{display:block}
.grid{display:grid;gap:18px}.g2{grid-template-columns:repeat(2,1fr)}.g3{grid-template-columns:repeat(3,1fr)}.g4{grid-template-columns:repeat(4,1fr)}.g-pos{grid-template-columns:1.1fr 1fr}.g-pos-wide{grid-template-columns:2.2fr 1fr}
@media(max-width:900px){.g2,.g3,.g4,.g-pos,.g-pos-wide{grid-template-columns:1fr}}
.card{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:22px;backdrop-filter:blur(18px);position:relative;overflow:hidden}
@media(max-width:640px){
.card{padding:16px;border-radius:14px}
.card-title{font-size:14px;margin-bottom:12px}
.wrap{padding:18px 14px 40px}
}
.card-title{font-size:15px;font-weight:600;color:var(--txt);margin-bottom:16px;display:flex;align-items:center;gap:9px}
.card-title::before{content:"";width:4px;height:16px;border-radius:3px;background:var(--grad)}
.card-title .sub{font-size:12px;color:var(--txt3);font-weight:400;margin-left:auto}
.kpi-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:18px}
@media(max-width:900px){.kpi-grid{grid-template-columns:repeat(2,1fr)}}
.kpi{background:linear-gradient(160deg,rgba(30,44,80,.85),rgba(18,28,55,.85));border:1px solid var(--line);border-radius:16px;padding:18px}
.kpi-label{font-size:12px;color:var(--txt2);margin-bottom:8px}.kpi-value{font-size:26px;font-weight:700}.kpi-sub{font-size:11.5px;color:var(--txt3);margin-top:5px}
.kpi.up .kpi-value{color:var(--up)}.kpi.down .kpi-value{color:var(--down)}
.idx-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}
@media(max-width:900px){.idx-grid{grid-template-columns:repeat(2,1fr)}}
.idx-card{background:rgba(255,255,255,.03);border:1px solid var(--line2);border-radius:14px;padding:16px;text-align:center}
.idx-name{font-size:12.5px;color:var(--txt2);margin-bottom:8px}.idx-value{font-size:20px;font-weight:600}.idx-change{font-size:13px;margin-top:5px}
.arr{font-size:10px;margin-right:3px}.up{color:var(--up)}.down{color:var(--down)}
table{width:100%;border-collapse:collapse;font-size:13px}th{text-align:left;color:var(--txt3);font-weight:500;font-size:12px;padding:10px 12px;border-bottom:1px solid var(--line)}td{padding:12px;border-bottom:1px solid var(--line2);vertical-align:middle}
.num{font-variant-numeric:tabular-nums}.bold{font-weight:700}.p-name{font-weight:600;white-space:nowrap}.p-code{font-size:11px;color:var(--txt3);white-space:nowrap}.p-sect{font-size:12px;color:var(--txt2);white-space:nowrap}.p-strat{font-size:11px;color:var(--txt3);white-space:nowrap}
.table-scroll{overflow-x:auto;-webkit-overflow-scrolling:touch;margin:0 -16px;padding:0 16px;scrollbar-width:none;-ms-overflow-style:none}.table-scroll::-webkit-scrollbar{display:none}.table-scroll table{width:100%;table-layout:auto}.pos-table,.hist-table{width:100%}.pos-table th,.pos-table td,.hist-table th,.hist-table td{white-space:nowrap}
@media(max-width:900px){.pos-table,.hist-table{width:auto;min-width:680px}.pos-table td,.pos-table th,.hist-table td,.hist-table th{padding:10px 8px}.p-name{font-size:13px}.p-sect,.p-strat{font-size:11px}}
.wbar{display:flex;align-items:center;gap:7px}.wfill{height:7px;border-radius:4px;background:var(--grad);max-width:60px}.p-status{font-size:11.5px;padding:4px 9px;border-radius:8px;background:rgba(79,140,255,.12)}
.tag-strat{font-size:11px;padding:3px 9px;border-radius:7px;background:rgba(245,196,81,.12);color:var(--gold)}
.tag{font-size:11px;padding:2.5px 8px;border-radius:7px;display:inline-block}.tag-up{background:rgba(255,84,112,.14);color:var(--up)}.tag-down{background:rgba(47,212,166,.14);color:var(--down)}.tag-neutral{background:rgba(154,166,201,.14);color:var(--txt2)}
.phase{font-size:11px;padding:2.5px 8px;border-radius:7px}.ph-pre{background:rgba(79,140,255,.14);color:#7ca7ff}.ph-hold{background:rgba(245,196,81,.14);color:var(--gold)}
.donut-wrap{display:flex;align-items:center;gap:24px;flex-wrap:wrap}.donut{width:180px;height:180px}.donut-num{fill:var(--txt);font-size:26px;font-weight:700}.donut-label{fill:var(--txt3);font-size:12px}
.legend{flex:1;min-width:160px}.legend-item{display:flex;align-items:center;justify-content:space-between;padding:7px 0;border-bottom:1px dashed var(--line2);font-size:13px}.legend-l{display:flex;align-items:center;gap:8px}.legend-c{width:10px;height:10px;border-radius:3px}.legend-val{color:var(--txt2)}
.ring{width:170px;height:170px}.ring-num{fill:var(--txt);font-size:28px;font-weight:700}.ring-label{fill:var(--txt3);font-size:12px}
.stats-side{display:flex;flex-direction:column;gap:12px;justify-content:center}.stat-line{display:flex;justify-content:space-between;font-size:13px;padding:8px 0;border-bottom:1px dashed var(--line2)}.stat-line .k{color:var(--txt2)}.stat-line .v{font-weight:600}.stat-line .v.good{color:var(--down)}.stat-line .v.bad{color:var(--up)}
.sector-row{display:grid;grid-template-columns:100px 1fr 70px 70px;align-items:center;gap:12px;padding:8px 0}.sector-name{font-size:13px}.sector-track{height:10px;border-radius:6px;background:rgba(255,255,255,.06);overflow:hidden}.sector-fill{height:100%}.sector-fill.pos{background:linear-gradient(90deg,#ff5470,#ff7d94)}.sector-fill.neg{background:linear-gradient(90deg,#2fd4a6,#2fe6c0)}.sector-val{font-size:12.5px;font-weight:600;text-align:right}.sector-inflow{font-size:11px;color:var(--txt3);text-align:right}
.news-item{padding:12px 0;border-bottom:1px solid var(--line2)}.news-meta{display:flex;gap:8px;align-items:center;margin-bottom:5px}.time{font-size:11.5px;color:var(--txt3)}.news-title{font-size:13.5px;line-height:1.55}.news-title a{color:var(--txt);text-decoration:none}.news-title a:hover{color:#7ca7ff}.news-rel{font-size:11.5px;color:var(--txt3);margin-top:4px}.ext-arrow{color:var(--accent);font-size:12px;font-weight:700;margin-left:4px;display:inline-block;transition:transform .2s;vertical-align:1px}.news-title a:hover .ext-arrow{transform:translate(2px,-2px)}
.macro-item{padding:11px 0;border-bottom:1px solid var(--line2)}.macro-tag{display:flex;gap:8px;align-items:center;margin-bottom:5px}.macro-key{font-size:12px;color:var(--accent)}.macro-text{font-size:13px;color:var(--txt2);line-height:1.6}
.flow-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:16px}.flow-card{background:rgba(255,255,255,.03);border:1px solid var(--line2);border-radius:14px;padding:16px}.flow-label{font-size:12px;color:var(--txt3);margin-bottom:6px}.flow-value{font-size:20px;font-weight:700}.flow-sub{font-size:11.5px;color:var(--txt3);margin-top:8px}.flow-sub2{font-size:12px;color:var(--txt2);margin-top:10px;white-space:nowrap}
.strat-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:14px}.strat-card{background:rgba(255,255,255,.03);border:1px solid var(--line2);border-radius:14px;padding:16px;border-top:3px solid var(--sc)}.strat-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}.strat-name{font-weight:600}.strat-trades{font-size:12px;color:var(--txt3)}.strat-nums{font-size:13px;margin-bottom:10px}.strat-nums .win{color:var(--up)}.strat-nums .loss{color:var(--down)}.strat-nums .even{color:var(--txt3)}.strat-nums span{margin-right:12px}.strat-bar{height:8px;border-radius:5px;background:rgba(255,255,255,.06);overflow:hidden}.strat-fill{height:100%}.strat-wr{font-size:13px;font-weight:600;margin-top:8px}
.funnel-row{display:grid;grid-template-columns:70px 1fr 46px;align-items:center;gap:12px;padding:7px 0}.funnel-label{font-size:13px}.funnel-track{height:34px;border-radius:9px;background:rgba(255,255,255,.04);overflow:hidden}.funnel-fill{height:100%;display:flex;align-items:center;padding-left:10px;position:relative}.funnel-count{font-size:12px;font-weight:600;color:#fff}.funnel-pct{font-size:12px;color:var(--txt2);text-align:right}.pool-note{font-size:12px;color:var(--txt3);margin-top:12px;line-height:1.7}.pool-note b{color:var(--gold)}
.diag-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}@media(max-width:900px){.diag-grid{grid-template-columns:1fr}}.diag-card{background:rgba(255,255,255,.03);border:1px solid var(--line2);border-radius:14px;padding:16px}.diag-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px}.diag-name{font-weight:600}.diag-code{font-size:11px;color:var(--txt3)}.diag-pool{font-size:11px;padding:3px 9px;border-radius:7px}.diag-core{background:rgba(245,196,81,.15);color:var(--gold)}.diag-watch{background:rgba(79,140,255,.14);color:#7ca7ff}.diag-score{display:flex;align-items:baseline;gap:4px;margin-bottom:6px}.score-num{font-size:32px;font-weight:700;color:var(--accent)}.score-total{font-size:13px;color:var(--txt3)}.score-track{height:7px;border-radius:4px;background:rgba(255,255,255,.06);overflow:hidden;margin-bottom:12px}.score-fill{height:100%;background:var(--grad)}.diag-strat{margin-bottom:8px}.diag-risk{font-size:12px;color:var(--txt3);line-height:1.5}
.prio-item{padding:12px 0;border-bottom:1px solid var(--line2)}.prio-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}.prio-name{font-weight:600}.prio-reason{font-size:12.5px;color:var(--txt2);line-height:1.65}
.alert-item{padding:13px 16px;border-radius:12px;margin-bottom:10px;background:rgba(255,255,255,.03);border:1px solid var(--line2)}.alert-head{display:flex;gap:10px;align-items:center;margin-bottom:5px}.alert-type{font-size:12px;font-weight:600}.alert-name{font-size:13px;font-weight:600}.alert-detail{font-size:12.5px;color:var(--txt2);line-height:1.6}.al-up .alert-type{color:var(--down)}.al-up{border-left:3px solid var(--down)}.al-down .alert-type{color:var(--up)}.al-down{border-left:3px solid var(--up)}.al-mid .alert-type{color:var(--gold)}.al-mid{border-left:3px solid var(--gold)}
.risk-list li{list-style:none;padding:9px 0;border-bottom:1px dashed var(--line2);font-size:13px;color:var(--txt2);display:flex;gap:10px;align-items:center}.risk-list li:last-child{border:none}.risk-list li::before{content:"✦";color:var(--gold);font-size:11px}
.rv-item{display:flex;gap:10px;align-items:flex-start;padding:11px 0;border-bottom:1px solid var(--line2)}.rv-dot{width:8px;height:8px;border-radius:50%;margin-top:6px;flex-shrink:0}.rv-text{font-size:13.5px;line-height:1.65;flex:1}.rv-item .tag{flex-shrink:0;margin-top:2px}
.hist-box{margin-top:2px}.hist-toggle{list-style:none;cursor:pointer;user-select:none;display:inline-flex;align-items:center;gap:8px;font-size:13px;color:var(--accent);padding:10px 0;font-weight:500}.hist-toggle::-webkit-details-marker{display:none}.hist-toggle::after{content:"▾";transition:transform .2s;font-size:12px}.hist-box[open] .hist-toggle::after{transform:rotate(180deg)}.hist-scroll{max-height:460px;overflow:auto;margin-top:6px;padding-right:4px;scrollbar-width:none;-ms-overflow-style:none}.hist-scroll::-webkit-scrollbar{display:none}
.fate-block{margin-bottom:26px;padding:20px 22px 22px;background:rgba(255,255,255,.025);border:1px solid var(--line2);border-radius:16px;position:relative;overflow:hidden}.fate-quote{position:absolute;top:10px;right:18px;font-size:38px;line-height:1;color:var(--gold);opacity:.18;font-family:Georgia,serif}.fate-h{font-size:15px;font-weight:600;color:var(--gold);margin-bottom:12px;display:flex;align-items:center;gap:10px;padding-left:12px;border-left:3px solid var(--gold);line-height:1.4}.fate-idx{font-size:11px;color:var(--txt3);font-weight:500;letter-spacing:.1em;opacity:.8}.fate-p{font-size:14px;color:var(--txt2);line-height:2;text-align:justify}.fate-p:last-child{margin-bottom:0}.fate-empty{font-size:13px;color:var(--txt3);line-height:1.8}
.sys-empty{padding:56px 20px;text-align:center}.sys-empty-icon{font-size:44px;line-height:1;margin-bottom:18px;opacity:.9}.sys-empty-title{font-size:16px;font-weight:600;color:var(--txt2);letter-spacing:.06em;margin-bottom:10px}.sys-empty-sub{font-size:12.5px;color:var(--txt3);letter-spacing:.04em}
@media(max-width:640px){.sys-empty{padding:40px 14px}.sys-empty-icon{font-size:36px;margin-bottom:14px}.sys-empty-title{font-size:14.5px}}
@media(max-width:640px){.fate-block{padding:16px 15px 16px;margin-bottom:16px;border-radius:13px}.fate-h{font-size:14px;margin-bottom:9px;gap:8px;padding-left:9px}.fate-p{font-size:13.5px;line-height:1.95}.fate-quote{font-size:30px;top:8px;right:13px}}
.footer{margin-top:40px;padding-top:20px;border-top:1px solid var(--line);font-size:12px;color:var(--txt3);text-align:center}.footer b{color:var(--gold)}.footer .ver{display:inline-block;margin-top:10px;padding:4px 14px;border-radius:20px;background:rgba(79,140,255,.12);color:#7ca7ff;font-size:11.5px;letter-spacing:.05em}
.rzrq-line{display:flex;align-items:baseline;gap:6px;margin-top:8px;font-size:11.5px;white-space:nowrap;flex-wrap:nowrap;overflow:hidden}.rzrq-k{color:var(--txt3);font-size:11px;flex-shrink:0}.rzrq-v{color:var(--txt2);font-weight:600;white-space:nowrap}.rzrq-c{margin-left:auto;font-weight:700;font-size:11px;flex-shrink:0;white-space:nowrap}.flow-sub2{font-size:12px;color:var(--txt2);margin-top:10px;white-space:nowrap}.flow-sub2 b{font-weight:700;color:var(--txt)}
.klk{cursor:pointer;position:relative;transition:border-color .2s,background .2s,transform .15s}.klk:hover{border-color:rgba(124,167,255,.45);background:rgba(79,140,255,.07)}.klk::after{content:"K";position:absolute;top:5px;right:7px;font-size:9px;font-weight:800;color:#7ca7ff;opacity:.55;background:rgba(79,140,255,.15);border-radius:4px;padding:1px 4px;line-height:1}.klk:hover::after{opacity:1;background:rgba(79,140,255,.25)}
.klk-row{cursor:pointer;transition:background .2s;border-radius:8px;padding-left:4px;padding-right:4px;margin-left:-4px;margin-right:-4px}.klk-row:hover{background:rgba(79,140,255,.08)}.klk-row:hover .sector-name::after{content:" 📈";font-size:10px;opacity:.7}
#kmask{display:none;position:fixed;inset:0;z-index:10000;background:rgba(4,8,18,.78);backdrop-filter:blur(6px);-webkit-backdrop-filter:blur(6px);align-items:center;justify-content:center;padding:20px}
#kmask.show{display:flex}
.kmodal{width:min(760px,96vw);max-height:92vh;overflow:auto;background:linear-gradient(165deg,#0e1730 0%,#0a1226 100%);border:1px solid rgba(90,130,255,.25);border-radius:18px;box-shadow:0 30px 80px rgba(0,0,0,.6);padding:20px 22px 16px;position:relative;animation:kpop .18s ease-out}
@keyframes kpop{from{opacity:0;transform:translateY(12px) scale(.98)}to{opacity:1;transform:none}}
.khead{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:6px}
.ktitle{font-size:16px;font-weight:700;color:var(--txt)}
.kref{font-size:11.5px;color:var(--txt3);margin-top:3px}.kref b{color:#7ca7ff;font-weight:500}
.kclose{background:rgba(255,255,255,.06);border:1px solid var(--line2);color:var(--txt2);width:30px;height:30px;border-radius:9px;cursor:pointer;font-size:15px;line-height:1;flex-shrink:0;transition:all .2s}.kclose:hover{background:rgba(255,84,112,.15);color:#ff5470;border-color:rgba(255,84,112,.35)}
.kbody{margin-top:6px}.kbody svg{display:block;width:100%;height:auto}
.kloading,.kfail{padding:70px 20px;text-align:center;color:var(--txt3);font-size:13.5px;letter-spacing:.05em}
.kfail{color:#ff8fa3}
.kspin{display:inline-block;width:26px;height:26px;border:3px solid rgba(124,167,255,.2);border-top-color:#7ca7ff;border-radius:50%;animation:krot .8s linear infinite;margin-bottom:14px}
@keyframes krot{to{transform:rotate(360deg)}}
@media(max-width:640px){.kmodal{padding:14px 12px 10px;border-radius:14px}.ktitle{font-size:15px}.rzrq-c{font-size:11.5px}}
"""

    # 自动检测服务端新数据并提示/刷新（解决浏览器缓存导致看不到更新的问题）
    auto_refresh_js = (
        "(function(){"
        "  function checkUpdate(){"
        "    fetch('data.json?_='+Date.now(),{cache:'no-store'}).then(function(r){return r.json();}).then(function(d){"
        "      var latest=d.lastUpdate||'';"
        "      if(latest && latest!==__CURRENT_UPDATE__){"
        "        var t=document.getElementById('update-toast');"
        "        if(t){t.style.display='block';t.onclick=function(){location.reload(true);};setTimeout(function(){location.reload(true);},4000);}"
        "      }"
        "    }).catch(function(e){});"
        "  }"
        "  checkUpdate();setInterval(checkUpdate,60000);"
        "})();"
    )

    # K线弹窗（点击指数/板块卡片 → 弹窗展示近60日日K，腾讯/新浪公开接口 JSONP，无跨域问题）
    KLINE_JS = r"""
(function(){
  var UP='#ff5470', DOWN='#2fd4a6', GRID='rgba(154,166,201,.14)', TXT='#6b7aa6';
  var EM_KLINE='https://push2his.eastmoney.com/api/qt/stock/kline/get?ut=fa5fd1943c7b386f172d6893dbfba10b&klt=101&fqt=1&lmt=60&end=20500101&fields1=f1,f2,f3&fields2=f51,f52,f53,f54,f55,f56,f57&secid=',
      EM_FFLOW='https://push2.eastmoney.com/api/qt/stock/fflow/daykline/get?ut=b2884a393a59ad64002292a3e90d46a5&lmt=25&klt=101&secid=1.000001&secid2=0.399001&fields1=f1,f2,f3,f7&fields2=f51,f52&cb=__CB__';
  var mask=document.createElement('div'); mask.id='kmask';
  mask.innerHTML='<div class="kmodal"><div class="khead"><div><div class="ktitle"></div><div class="kref"></div></div><button class="kclose" title="关闭">✕</button></div><div class="kbody"></div></div>';
  document.body.appendChild(mask);
  var mTitle=mask.querySelector('.ktitle'), mRef=mask.querySelector('.kref'), mBody=mask.querySelector('.kbody');
  function closeModal(){ mask.classList.remove('show'); document.body.style.overflow=''; }
  mask.addEventListener('click', function(e){ if(e.target===mask) closeModal(); });
  mask.querySelector('.kclose').addEventListener('click', closeModal);
  document.addEventListener('keydown', function(e){ if(e.key==='Escape') closeModal(); });

  function loadScript(url, vn, cb, timeout){
    var done=false, s=document.createElement('script');
    var timer=setTimeout(function(){ if(!done){ done=true; fin(); cb(null); } }, timeout||9000);
    function fin(){ clearTimeout(timer); try{ delete window[vn]; }catch(e){ window[vn]=undefined; } if(s.parentNode) s.parentNode.removeChild(s); }
    s.onload=function(){ if(done) return; done=true; var raw=window[vn]; fin(); cb(raw); };
    s.onerror=function(){ if(!done) return; done=true; fin(); cb(null); };
    s.src=url; document.head.appendChild(s);
  }
  function loadEM(url, cb, timeout){
    var fn='emcb'+Date.now()+Math.floor(Math.random()*1e5);
    var done=false, s=document.createElement('script');
    var timer=setTimeout(function(){ if(!done){ done=true; fin(); cb(null); } }, timeout||4000);
    function fin(){ clearTimeout(timer); try{ delete window[fn]; }catch(e){ window[fn]=undefined; } if(s.parentNode) s.parentNode.removeChild(s); }
    window[fn]=function(d){ if(done) return; done=true; fin(); cb(d); };
    s.onerror=function(){ if(!done) return; done=true; fin(); cb(null); };
    s.src=url.replace('__CB__', fn); document.head.appendChild(s);
  }
  function parseTx(raw, code){
    if(!raw || raw.code!==0 || !raw.data) return null;
    var node=raw.data[code]; if(!node) return null;
    var days=node.day || node.qfqday; if(!days || !days.length) return null;
    return days.slice(-60).map(function(a){ return {d:a[0],o:+a[1],c:+a[2],h:+a[3],l:+a[4],v:+a[5]||0}; });
  }
  function parseSina(raw){
    if(!raw || !raw.length) return null;
    return raw.slice(-60).map(function(a){ return {d:a.date,o:+a.open,c:+a.close,h:+a.high,l:+a.low,v:+a.volume||0}; });
  }
  function parseEM(raw){
    if(!raw || !raw.data || !raw.data.klines || !raw.data.klines.length) return null;
    return raw.data.klines.slice(-60).map(function(s){ var a=s.split(','); return {d:a[0],o:+a[1],c:+a[2],h:+a[3],l:+a[4],v:+a[5]||0}; });
  }

  function drawK(bars){
    var n=bars.length, W=680, H=400, padL=12, padR=58, top=44, kBot=288, volT=308, volB=384, bot=398;
    var iw=W-padL-padR, cw=iw/n, bw=Math.max(2, cw*0.62);
    var pmin=Infinity, pmax=-Infinity, vmax=0, i, b;
    for(i=0;i<n;i++){ b=bars[i]; if(b.l<pmin) pmin=b.l; if(b.h>pmax) pmax=b.h; if(b.v>vmax) vmax=b.v; }
    var padP=(pmax-pmin)*0.04||1; pmin-=padP; pmax+=padP;
    function Y(p){ return top+(pmax-p)/(pmax-pmin)*(kBot-top); }
    function ma(k){ var out=[]; for(i=0;i<n;i++){ if(i<k-1){ out.push(null); continue; } var s=0; for(var j=i-k+1;j<=i;j++) s+=bars[j].c; out.push(s/k); } return out; }
    var ma5=ma(5), ma10=ma(10);
    var last=bars[n-1].c, first=bars[0].c, chg=(last/first-1)*100, ccol=chg>=0?UP:DOWN;
    var g='';
    for(i=0;i<=4;i++){ var py=top+(kBot-top)*i/4, pv=pmax-(pmax-pmin)*i/4;
      g+='<line x1="'+padL+'" y1="'+py+'" x2="'+(W-padR)+'" y2="'+py+'" stroke="'+GRID+'" stroke-width="1"/>';
      g+='<text x="'+(W-padR+6)+'" y="'+(py+3.5)+'" fill="'+TXT+'" font-size="10.5" text-anchor="start">'+pv.toFixed(pv>1000?0:2)+'</text>';
    }
    for(i=0;i<n;i++){ b=bars[i]; var cx=padL+cw*(i+0.5), up=b.c>=b.o, col=up?UP:DOWN;
      g+='<line x1="'+cx+'" y1="'+Y(b.h)+'" x2="'+cx+'" y2="'+Y(b.l)+'" stroke="'+col+'" stroke-width="1"/>';
      var yo=Y(b.o), yc=Y(b.c), rh=Math.max(1,Math.abs(yc-yo));
      g+='<rect x="'+(cx-bw/2)+'" y="'+Math.min(yo,yc)+'" width="'+bw+'" height="'+rh+'" fill="'+col+'" fill-opacity="1"/>';
      var vh=vmax>0?b.v/vmax*(volB-volT):0;
      g+='<rect x="'+(cx-bw/2)+'" y="'+(volB-vh)+'" width="'+bw+'" height="'+Math.max(1,vh)+'" fill="'+col+'" fill-opacity="0.42"/>';
    }
    function maPath(arr, col){
      var d='', k;
      for(k=0;k<n;k++){ if(arr[k]==null) continue; var x=padL+cw*(k+0.5), y=Y(arr[k]); d+=(d?' L':'M')+x.toFixed(1)+' '+y.toFixed(1); }
      return d?'<path d="'+d+'" fill="none" stroke="'+col+'" stroke-width="1.3" stroke-opacity="0.9"/>':'';
    }
    g+=maPath(ma5,'#f5c451'); g+=maPath(ma10,'#a78bfa');
    g+='<text x="'+padL+'" y="'+(bot-2)+'" fill="'+TXT+'" font-size="10.5">'+bars[0].d+'</text>';
    g+='<text x="'+(W-padR)+'" y="'+(bot-2)+'" fill="'+TXT+'" font-size="10.5" text-anchor="end">'+bars[n-1].d+'</text>';
    g+='<text x="'+padL+'" y="'+(top-18)+'" fill="'+ccol+'" font-size="12.5" font-weight="700">近'+n+'日 '+(chg>=0?'+':'')+chg.toFixed(2)+'% · 最新 '+last+'</text>';
    g+='<text x="'+padL+'" y="'+(volT-6)+'" fill="'+TXT+'" font-size="9.5">成交量</text>';
    return '<svg viewBox="0 0 '+W+' '+H+'" preserveAspectRatio="xMidYMid meet"><rect x="0" y="0" width="'+W+'" height="'+H+'" fill="transparent"/>'+g+'</svg>';
  }

  function openModal(el){
    var name=el.getAttribute('data-name')||el.textContent.trim().slice(0,8);
    var code=el.getAttribute('data-code')||'';
    var src=el.getAttribute('data-src')||'tx';
    var ref=el.getAttribute('data-ref')||'';
    var bk=el.getAttribute('data-bk')||'';
    mTitle.textContent=name+' · 近60日K线';
    mRef.textContent='加载中…';
    mBody.innerHTML='<div class="kloading"><div class="kspin"></div><br>K线加载中…</div>';
    mask.classList.add('show'); document.body.style.overflow='hidden';
    function show(bars, srcTxt){
      if(bars){ mRef.innerHTML=srcTxt; mBody.innerHTML=drawK(bars); }
      else mBody.innerHTML='<div class="kfail">⚠ K线数据获取失败，请稍后重试</div>';
    }
    function tryTx(){
      var vn='kq'+Date.now()+Math.floor(Math.random()*1e5);
      loadScript('https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get?_var='+vn+'&param='+encodeURIComponent(code)+',day,,,60,qfq', vn, function(raw){
        show(parseTx(raw, code), (ref?('参考指数 <b>'+ref+'</b> · '):'')+'腾讯行情 · 仅供参考');
      });
    }
    function trySina(){
      var vn='kq'+Date.now()+Math.floor(Math.random()*1e5);
      loadScript('https://stock2.finance.sina.com.cn/futures/api/jsonp.php/var%20'+vn+'=/GlobalFuturesService.getGlobalFuturesDailyKLine?symbol='+encodeURIComponent(code), vn, function(raw){
        show(parseSina(raw), '新浪期货 · 仅供参考');
      });
    }
    if(bk){
      loadEM(EM_KLINE+encodeURIComponent('90.'+bk)+'&cb=__CB__', function(d){
        var bars=parseEM(d);
        if(bars) show(bars, '东方财富 · '+name+'板块K线 · 实时');
        else tryTx();
      });
    } else if(src==='sina'){ trySina(); } else { tryTx(); }
  }

  function loadMainFlow(){
    var e5=document.querySelector('.mf-d5'), e20=document.querySelector('.mf-d20');
    if(!e5 && !e20) return;
    loadEM(EM_FFLOW, function(d){
      if(!d || !d.data || !d.data.klines || d.data.klines.length<5) return;
      var arr=d.data.klines.map(function(s){ return parseFloat(s.split(',')[1])||0; });
      function set(el, v){ if(!el) return; el.textContent=(v>=0?'+':'')+(v/1e8).toFixed(1)+'亿'; el.style.color=v>=0?UP:DOWN; }
      set(e5, arr.slice(-5).reduce(function(a,b){return a+b;},0));
      if(arr.length>=20) set(e20, arr.slice(-20).reduce(function(a,b){return a+b;},0));
    }, 6000);
  }

  function bindK(){ document.querySelectorAll('.klk,.klk-row').forEach(function(el){ if(!el._kbound){ el._kbound=1; el.addEventListener('click', function(){ openModal(el); }); } }); }
  function onReady(fn){ if(document.readyState==='loading') document.addEventListener('DOMContentLoaded', fn); else fn(); }
  onReady(bindK); onReady(loadMainFlow);
})();
"""

    kpi_block = (
        '<div class="kpi-grid">'
        + kpi_card("总仓位", posSum.get("total", "0"), "现金 " + str(posSum.get("cash", "0")))
        + kpi_card("今日盈亏", posSum.get("dailyPnl", "0"), "当日账户净值变化", "up" if str(posSum.get("dailyPnl", "0")).startswith("+") else "down")
        + kpi_card("历史交易", str(histStats.get("totalTrades", 0)) + " 笔", "胜 " + str(histStats.get("wins", 0)) + " · 负 " + str(histStats.get("losses", 0)) + " · 平 " + str(histStats.get("evens", 0)))
        + kpi_card("交易胜率", str(histStats.get("winRate", 0)) + "%", "盈亏比 " + str(histStats.get("profitLossRatio", 0)))
        + '</div>'
    )

    html_doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<meta http-equiv="Pragma" content="no-cache">
<meta http-equiv="Expires" content="0">
<title>可飞牧场 · 投资工作台</title>
<style>{CSS}</style>
</head>
<body>
<div id="update-toast" style="display:none;position:fixed;top:0;left:0;right:0;z-index:9999;background:linear-gradient(90deg,#4f8cff,#8b5cf6);color:#fff;text-align:center;padding:11px;font-size:13px;cursor:pointer;box-shadow:0 4px 20px rgba(0,0,0,.4)">🔄 检测到云端已更新数据，点击此处或稍候自动刷新…</div>
<div class="wrap">
  <div class="topbar">
    <div class="brand"><div class="logo">涨</div><div><div class="brand-t"><span class="brand-cn">可飞牧场</span><span class="brand-en">CofiRanch</span></div><div class="brand-s">流水不争先 · 争的是滔滔不绝</div></div></div>
    <div class="update"><span class="dot"></span>{esc(lastUpdate)}</div>
  </div>
  <div class="nav">
    <button class="nav-btn active" data-tab="hotspot">● 市场热点</button>
    <button class="nav-btn" data-tab="stock">● 选股中心</button>
    <button class="nav-btn" data-tab="journal">● 持仓日志</button>
    <button class="nav-btn" data-tab="review">● 复盘笔记</button>
    <button class="nav-btn" data-tab="system">● 交易体系</button>
    <button class="nav-btn" data-tab="fate">● 缘起性空</button>
  </div>
  <div class="section active" id="hotspot">
    <div class="grid g-pos" style="margin-bottom:18px">
      <div class="card"><div class="card-title">A股指数 <span class="sub">今日收盘</span></div><div class="idx-grid">{index_cards(indices)}</div></div>
      <div class="card"><div class="card-title">隔夜外盘 <span class="sub">全球 · 期货/现货</span></div><div class="idx-grid">{index_cards(globalMarkets)}</div></div>
    </div>
    <div class="grid g2" style="margin-bottom:18px">
      <div class="card"><div class="card-title">今日热门板块 <span class="sub">涨跌幅</span></div>{sector_bars(hotToday, True)}</div>
      <div class="card"><div class="card-title">5日强势板块 <span class="sub">资金流入</span></div>{sector_bars(hot5d, False)}</div>
    </div>
    <div class="grid g3" style="margin-bottom:18px">
      <div class="card"><div class="card-title">两市资金</div><div class="flow-grid">
        <div class="flow-card">
          <div class="flow-label">两融余额</div>
          <div class="flow-value {updown(margin.get('direction',''))}">{esc(margin.get("balance",""))}</div>
          <div class="rzrq-line"><span class="rzrq-k">融资</span><span class="rzrq-v num">{esc(margin.get("rzBalance","—"))}</span><span class="rzrq-c num {updown(margin.get('rzDirection',''))}">{fmt_change(margin.get("rzChange",""))}</span></div>
          <div class="rzrq-line"><span class="rzrq-k">融券</span><span class="rzrq-v num">{esc(margin.get("rqBalance","—"))}</span><span class="rzrq-c num {updown(margin.get('rqDirection',''))}">{fmt_change(margin.get("rqChange",""))}</span></div>
          <div class="flow-sub">{esc(margin.get("date",""))}</div>
        </div>
        <div class="flow-card">
          <div class="flow-label">主力净流入</div>
          <div class="flow-value {updown(mainflow.get('direction',''))}">{esc(str(mainflow.get("value","")).replace("两市",""))}</div>
          <div class="flow-sub2">近5日 <b class="num mf-d5">{esc(mainflow.get("d5","—"))}</b> · 近20日 <b class="num mf-d20">{esc(mainflow.get("d20","—"))}</b></div>
          <div class="flow-sub">{esc(mainflow.get("date","今日"))}</div>
        </div>
      </div></div>
      <div class="card" style="grid-column:span 2"><div class="card-title">宏观要闻 <span class="sub">货币政策 · 海外</span></div>{macro_list(macro)}</div>
    </div>
    <div class="card"><div class="card-title">新闻快讯 <span class="sub">盘前 · 持仓相关</span></div>{news_list(news)}</div>
  </div>
  <div class="section" id="stock">
    <div class="grid g2" style="margin-bottom:18px">
      <div class="card"><div class="card-title">选股池漏斗 <span class="sub">海选 → 交易</span></div>{pool_funnel(poolFlow.get("levels", []))}
        <div class="pool-note"><b>🆕 新进：</b>{esc(poolFlow.get("newPromotion",""))}<br><b>🗑 淘汰：</b>{esc(poolFlow.get("newElimination",""))}</div></div>
      <div class="card"><div class="card-title">策略体系 <span class="sub">历史战绩</span></div><div class="strat-grid">{strat_cards(stratStats)}</div></div>
    </div>
    <div class="grid g2" style="margin-bottom:18px">
      <div class="card"><div class="card-title">候选池诊断 <span class="sub">评分</span></div><div class="diag-grid" style="grid-template-columns:1fr">{diag_cards(diagnosis)}</div></div>
      <div class="card"><div class="card-title">板块优先级 <span class="sub">轮动参考</span></div>{priority_list(sectorPriority)}</div>
    </div>
  </div>
  <div class="section" id="journal">
    {kpi_block}
    <div class="grid g-pos" style="margin-bottom:18px">
      <div class="card"><div class="card-title">持仓分布 <span class="sub">{len(positions)} 只 · 总仓位 {esc(posSum.get("total","0"))}</span></div>
        <div class="donut-wrap">{donut_svg}<div class="legend">{legend}</div></div></div>
      <div class="card"><div class="card-title">交易战绩 <span class="sub">历史胜率</span></div>
        <div style="display:flex;gap:24px;align-items:center;flex-wrap:wrap">
          <svg width="0" height="0"><defs><linearGradient id="gg1" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#ff5470"/><stop offset="1" stop-color="#f5c451"/></linearGradient></defs></svg>
          <div style="flex-shrink:0">{pct_ring}</div>
          <div class="stats-side">
            <div class="stat-line"><span class="k">总交易</span><span class="v">{histStats.get("totalTrades",0)} 笔</span></div>
            <div class="stat-line"><span class="k">平均盈利</span><span class="v good">+{histStats.get("avgWin",0)}%</span></div>
            <div class="stat-line"><span class="k">平均亏损</span><span class="v bad">{histStats.get("avgLoss",0)}%</span></div>
            <div class="stat-line"><span class="k">盈亏比</span><span class="v">{histStats.get("profitLossRatio",0)}</span></div>
          </div>
        </div></div>
    </div>
    <div class="grid g-pos-wide" style="margin-bottom:18px">
      <div class="card"><div class="card-title">当前持仓明细</div>
        <div class="table-scroll"><table class="pos-table"><thead><tr><th>名称</th><th>行业/战法</th><th>现价</th><th>成本</th><th>浮盈</th><th>仓位</th><th>状态</th></tr></thead>
        <tbody>{positions_rows(positions)}</tbody></table></div></div>
      <div class="card"><div class="card-title">操作预警</div>{alerts_list(alerts)}
        <div class="card-title" style="margin-top:20px">风险纪律</div><ul class="risk-list">{("".join(f'<li>{esc(r)}</li>' for r in riskRules))}</ul></div>
    </div>
    <div class="card"><div class="card-title">历史交易记录 <span class="sub">全部 {len(histList)} 笔 · 点击展开</span></div>
      <details class="hist-box">
        <summary class="hist-toggle">展开全部 {len(histList)} 笔历史持仓</summary>
        <div class="hist-scroll table-scroll"><table class="hist-table"><thead><tr><th>名称</th><th>板块</th><th>买入</th><th>卖出</th><th>成交价</th><th>收益</th><th>战法</th></tr></thead>
        <tbody>{history_rows(histList[::-1])}</tbody></table></div>
      </details>
    </div>
  </div>
  <div class="section" id="review">
    <div class="card" style="margin-bottom:18px"><div class="card-title">复盘概览 <span class="sub">{esc(review.get("date",""))}</span></div><div style="font-size:14px;color:var(--txt2);line-height:1.8">{esc(review.get("summary",""))}</div></div>
    <div class="card"><div class="card-title">要点归纳</div>{review_points(reviewPoints)}</div>
  </div>
  <div class="section" id="system">
    <div class="card"><div class="card-title">交易体系 <span class="sub">战法规则 · 建设中</span></div>
      <div class="sys-empty"><div class="sys-empty-icon">🏗️</div><div class="sys-empty-title">栏目建设中，敬请期待</div><div class="sys-empty-sub">规划：战法定义 · 买卖点规则 · 仓位管理 · 执行纪律</div></div>
    </div>
  </div>
  <div class="section" id="fate">
    <div class="card"><div class="card-title">缘起性空 <span class="sub">投资心法与纪律</span></div>{fate_html(fate)}</div>
  </div>
  <div class="footer"><b>可飞牧场 · 投资工作台</b> — 数据自动同步云端看板 · 仅供参考，不构成投资建议<br><span class="ver">V1.0体验版</span></div>
</div>
<script>
document.querySelectorAll('.nav-btn').forEach(function(b){{
  b.addEventListener('click',function(){{
    document.querySelectorAll('.nav-btn').forEach(function(x){{x.classList.remove('active')}});
    b.classList.add('active');
    document.querySelectorAll('.section').forEach(function(s){{s.classList.remove('active')}});
    document.getElementById(b.dataset.tab).classList.add('active');
    window.scrollTo({{top:0,behavior:'smooth'}});
  }});
}});
  var __CURRENT_UPDATE__ = {json.dumps(lastUpdate)};
  {auto_refresh_js}
  {KLINE_JS}
</script>
</body>
</html>
"""
    return html_doc


# ---------------- 合并更新 ----------------
def merge_update(d, update):
    """把本次取数结果合并进数据字典。"""
    if not update:
        return d
    if not d:
        d = {"hotspot": {}, "stock": {}, "journal": {}, "review": {}, "fate": [], "lastUpdate": ""}
    # 顶层字段
    for k in ("lastUpdate",):
        if k in update:
            d[k] = update[k]
    # hotspot 部分
    hotspot = d.setdefault("hotspot", {})
    hotspot_update = update.get("hotspot", update)
    for k in ("indices", "usMarkets", "globalMarkets", "news", "macro", "marginBalance", "mainFlow",
              "hotScoresToday", "hotSectorsToday", "hotScores5d", "hotSectors5d"):
        if k in hotspot_update:
            hotspot[k] = hotspot_update[k]
    # stock / journal / review / fate
    if "stock" in update:
        d["stock"] = update["stock"]
    if "journal" in update:
        d["journal"] = update["journal"]
    if "review" in update:
        d["review"] = update["review"]
    if "fate" in update:
        d["fate"] = update["fate"]
    return d


# ---------------- 推送 ----------------
def push_file(token, path, content_str, message):
    """用 GitHub API 推送单个文本文件。"""
    content_b64 = base64.b64encode(content_str.encode("utf-8")).decode()
    # 取当前 sha
    st, resp = http("GET", f"{API}/repos/{REPO}/contents/{path}?ref={BRANCH}", token)
    body = {"message": message, "content": content_b64, "branch": BRANCH}
    if st == 200:
        body["sha"] = resp.get("sha")
    st2, resp2 = http("PUT", f"{API}/repos/{REPO}/contents/{path}", token, body)
    if st2 in (200, 201):
        print(f"✅ 已推送 {path}")
        return True
    print(f"❌ 推送 {path} 失败: {st2} {json.dumps(resp2, ensure_ascii=False)[:200]}")
    return False


def main():
    token = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("GITHUB_TOKEN")
    if not token:
        print("❌ 缺少 GitHub Token")
        sys.exit(1)
    update_str = sys.argv[2] if len(sys.argv) > 2 else ""

    print(f"🔍 从 GitHub 下载最新 {DATA_FILE} ...")
    d = load_data()
    if not d:
        print("⚠️ 未拿到 data.json，使用空模板。后续请确保仓库有 data.json")

    if update_str:
        try:
            update = json.loads(update_str)
            d = merge_update(d, update)
            print(f"✅ 已合并本次更新数据")
        except Exception as e:
            print(f"⚠️ 更新数据 JSON 解析失败: {e}")

    print("🛠 生成 index.html ...")
    html = build_html(d)
    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✅ 已生成 {HTML_FILE} ({len(html)} 字节)")

    ok = True
    ok &= push_file(token, HTML_FILE, html, "auto-update dashboard")
    # 同时把合并后的 data.json 推回，作为下次基线
    ok &= push_file(token, DATA_FILE, json.dumps(d, ensure_ascii=False, indent=2), "auto-update data.json")

    if ok:
        print(f"\n🌐 网页已更新: https://{REPO_OWNER}.github.io/{REPO_NAME}/")
    else:
        print("\n⚠️ 部分推送失败，请检查 token 或仓库状态")
        sys.exit(1)


if __name__ == "__main__":
    main()
