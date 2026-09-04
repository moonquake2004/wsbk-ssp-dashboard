#!/usr/bin/env python3
"""
WSBK 2026 WorldSSP 单文件 HTML 看板构建器
读取 data.json -> 计算衍生统计 -> 内联数据生成 index.html
布局: 桌面宽屏双栏 (适配 1440×932 等高分辨率), iOS 暗色风格
"""
import json, os, html
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = json.load(open(os.path.join(HERE, "data.json"), encoding="utf-8"))

SEASON = DATA["season"]
ROUNDS = DATA["rounds"]            # dict: AUS -> {...}
ROUND_ORDER = DATA["round_order"]  # list: [AUS, POR, ...]
RIDERS = DATA["riders"]            # dict: id -> {...}
RACES = DATA["races"]              # list of {round, race, date, results[]}
STANDINGS = DATA["standings"]      # 官方车手积分榜
STANDINGS_MFR = DATA.get("manufacturer_standings", [])  # 厂商积分榜
CIRCUITS = DATA.get("circuits", {})  # 赛道信息

# 加载历史缓存 (历年冠军+最快圈)
# 注意: API 原始 fl_ms 是 MMSSmmm 格式，需要解码
def _decode_hist_time(v):
    if v is None: return None
    try:
        s = str(int(v))
    except: return None
    if len(s) < 4: return int(s)
    ms = int(s[-3:]); secs = int(s[-5:-3]); mins = int(s[:-5]) if len(s) > 5 else 0
    return mins * 60000 + secs * 1000 + ms

HISTORY = {}
hist_path = os.path.join(HERE, "history_cache.json")
if os.path.exists(hist_path):
    try:
        raw_hist = json.load(open(hist_path, encoding="utf-8"))
        # 解码所有 fl_ms
        for cid, years in raw_hist.items():
            for yr, races in years.items():
                for race in races:
                    if 'fl_ms' in race:
                        race['fl_ms'] = _decode_hist_time(race['fl_ms'])
        HISTORY = raw_hist
    except: pass

POINTS_SCALE = [25, 20, 16, 13, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1]  # SSP 前15名积分

# ---------- 衍生统计计算 ----------
def race_key(race):
    return f"{race['round']}_{race['race']}"

rider_stats = {}
for rid in RIDERS:
    rider_stats[rid] = {
        "id": rid, "races_started": 0, "finishes": [],
        "podiums": 0, "wins": 0, "p2": 0, "p3": 0,
        "poles_fl": 0, "dnf": 0, "best_finish": 99,
        "total_time_ms": 0, "calc_points": 0,
        "fl_total_ms": 0, "fl_count": 0, "fastest_fl_ms": 99999999,
    }

for race in RACES:
    rk = race_key(race)
    for res in race["results"]:
        rid = res["rider_id"]
        if rid not in rider_stats: continue
        s = rider_stats[rid]
        pos = res.get("pos"); status = res.get("status", ""); fl = res.get("fastest_lap_ms")
        s["races_started"] += 1
        s["finishes"].append({
            "round": race["round"], "race": race["race"], "rk": rk,
            "pos": pos, "status": status, "fastest_lap_ms": fl,
            "time_ms": res.get("time_ms"), "date": race.get("date", ""),
        })
        if pos is not None:
            if pos == 1: s["wins"] += 1; s["podiums"] += 1
            elif pos == 2: s["p2"] += 1; s["podiums"] += 1
            elif pos == 3: s["p3"] += 1; s["podiums"] += 1
            if 1 <= pos <= 15: s["calc_points"] += POINTS_SCALE[pos-1]
            if pos < s["best_finish"]: s["best_finish"] = pos
        if res.get("fastest_lap_pos") == 1: s["poles_fl"] += 1
        if fl:
            s["fl_total_ms"] += fl; s["fl_count"] += 1
            if fl < s["fastest_fl_ms"]: s["fastest_fl_ms"] = fl
        if status not in ("Classified",): s["dnf"] += 1
        if res.get("time_ms") and status == "Classified": s["total_time_ms"] += res["time_ms"]

for rid, s in rider_stats.items():
    ok = [f["pos"] for f in s["finishes"] if f["status"] == "Classified" and f["pos"]]
    s["avg_pos"] = round(sum(ok)/len(ok), 2) if ok else 0
    s["finishes_ok"] = len(ok)
    s["avg_fl_ms"] = round(s["fl_total_ms"]/s["fl_count"], 0) if s["fl_count"] else 0

official_pts = {st["rider_id"]: st.get("points", 0) for st in STANDINGS if st.get("rider_id")}
for rid, ri in RIDERS.items():
    ri["points"] = official_pts.get(rid, 0)
    ri.update(rider_stats.get(rid, {}))

race_fastest = {}
for race in RACES:
    fl_list = [(r["fastest_lap_ms"], r) for r in race["results"] if r.get("fastest_lap_ms")]
    if fl_list:
        fl_list.sort(key=lambda x: x[0])
        race_fastest[race_key(race)] = fl_list[0]

# ---------- 国旗 ----------
FLAGS = {
    "ESP":"🇪🇸","FRA":"🇫🇷","GBR":"🇬🇧","GER":"🇩🇪","ITA":"🇮🇹","AUS":"🇦🇺",
    "USA":"🇺🇸","JPN":"🇯🇵","TUR":"🇹🇷","NED":"🇳🇱","POR":"🇵🇹","CZE":"🇨🇿",
    "SUI":"🇨🇭","AUT":"🇦🇹","BEL":"🇧🇪","IRL":"🇮🇪","BRA":"🇧🇷","ARG":"🇦🇷",
    "THA":"🇹🇭","INA":"🇮🇩","MAL":"🇲🇾","CAN":"🇨🇦","RSA":"🇿🇦","SWE":"🇸🇪",
    "NOR":"🇳🇴","FIN":"🇫🇮","DEN":"🇩🇰","POL":"🇵🇱","HUN":"🇭🇺","CRO":"🇭🇷",
    "SVN":"🇸🇮","SVK":"🇸🇰","EST":"🇪🇪","LAT":"🇱🇻","LTU":"🇱🇹","BUL":"🇧🇬",
    "ROU":"🇷🇴","GRE":"🇬🇷","UKR":"🇺🇦","RUS":"🇷🇺","CHN":"🇨🇳","HKG":"🇭🇰",
    "TPE":"🇹🇼","KOR":"🇰🇷","UAE":"🇦🇪","KSA":"🇸🇦","QAT":"🇶🇦",
}

# ---------- 构建输出数据 ----------
riders_sorted = sorted(RIDERS.values(), key=lambda r: r.get("points", 0), reverse=True)
front_riders = [{
    "id": ri["id"], "num": ri.get("number"), "name": ri.get("full_name",""),
    "country": ri.get("country",""),
    "team": ri.get("team",""), "motorcycle": ri.get("motorcycle",""),
    "points": ri.get("points",0), "calc_pts": ri.get("calc_points",0),
    "starts": ri.get("races_started",0), "wins": ri.get("wins",0),
    "podiums": ri.get("podiums",0), "p2": ri.get("p2",0), "p3": ri.get("p3",0),
    "fl": ri.get("poles_fl",0), "dnf": ri.get("dnf",0),
    "best": ri.get("best_finish",99) if ri.get("best_finish",99)!=99 else 0,
    "avg_pos": ri.get("avg_pos",0), "finishes_ok": ri.get("finishes_ok",0),
    "fastest_fl": ri.get("fastest_fl_ms",0) if ri.get("fastest_fl_ms",99999999)!=99999999 else 0,
    "per_race": {f["rk"]: {"pos": f["pos"], "status": f["status"]} for f in ri.get("finishes",[])},
} for ri in riders_sorted]

front_races = []
for race in RACES:
    rd = ROUNDS.get(race["round"], {})
    fl = race_fastest.get(race_key(race))
    first_time = race["results"][0].get("time_ms") if race["results"] else None
    front_races.append({
        "rk": race_key(race), "round": race["round"],
        "round_name": rd.get("name",""), "circuit": rd.get("circuit",""),
        "country": rd.get("country",""), "date": race.get("date",""), "race": race["race"],
        "fastest_lap_ms": fl[0] if fl else 0,
        "fastest_lap_rider": RIDERS.get(fl[1]["rider_id"],{}).get("full_name","") if fl else "",
        "results": [{
            "pos": r.get("pos"), "num": r.get("number"),
            "name": RIDERS.get(r["rider_id"],{}).get("full_name","?"),
            "country": RIDERS.get(r["rider_id"],{}).get("country",""),
            "id": r["rider_id"], "team": r.get("team",""),
            "motorcycle": r.get("motorcycle",""),
            "laps": r.get("laps"), "status": r.get("status"),
            "time_ms": r.get("time_ms"),
            "gap_ms": (r.get("time_ms") or 0) - first_time if r.get("time_ms") and first_time else None,
            "fl_ms": r.get("fastest_lap_ms"), "fl_pos": r.get("fastest_lap_pos"),
        } for r in race["results"]],
    })

front_manufacturers = [{
    "pos": m.get("pos"), "name": m.get("name",""),
    "manufacturer_id": m.get("manufacturer_id",""),
    "points": m.get("points",0),
} for m in STANDINGS_MFR]

front_data = {
    "season": SEASON, "generated": DATA.get("generated_at",""),
    "round_order": ROUND_ORDER,
    "rounds": {k: {"name": v["name"], "circuit": v["circuit"], "country": v["country"],
                    "date": v["start_date"], "end_date": v["end_date"],
                    "status": v["status"], "circuit_id": v.get("circuit_id",""),
                    "sequence_order": v.get("sequence_order",0)}
               for k,v in ROUNDS.items()},
    "riders": front_riders, "races": front_races,
    "manufacturers": front_manufacturers,
    "circuits": {cid: {"name": c.get("name",""), "locality": c.get("locality",""),
                        "country": c.get("country",""), "length_m": c.get("length_m",0)}
                 for cid, c in CIRCUITS.items()},
    "history": HISTORY,
    "total_riders": len(RIDERS), "total_races": len(RACES), "total_rounds_done": len(ROUND_ORDER),
}

DATA_JSON = json.dumps(front_data, ensure_ascii=False, separators=(",",":"))

# ---------- HTML 模板 (桌面宽屏双栏) ----------
HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>WorldSSP 2026 · 成绩统计</title>
<style>
  :root {
    --bg: #000000;
    --bg-soft: #0a0a0c;
    --card: #1c1c1e;
    --card-2: #2c2c2e;
    --sep: #38383a;
    --label: #ffffff;
    --sec: #98989d;
    --sec2: #636366;
    --accent: #ff9f0a;
    --gold: #ffd60a;
    --silver: #d4d4d8;
    --bronze: #cd7f32;
    --danger: #ff453a;
    --green: #30d158;
    --blue: #0a84ff;
    --ssp: #006600;
    --ssp-bright: #34c759;
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text",
                 "Helvetica Neue", "PingFang SC", "Microsoft YaHei", sans-serif;
  }
  /* 制造商品牌色 chip */
  .moto-chip { display:inline-block; font-size:10px; font-weight:700; padding:1px 6px; border-radius:4px; letter-spacing:0.2px; white-space:nowrap; line-height:1.4; vertical-align:middle; }
  .mc-ducati     { background:rgba(226,0,26,0.18);  color:#ff5470; border:0.5px solid rgba(226,0,26,0.45); }
  .mc-yamaha     { background:rgba(0,53,160,0.22);  color:#5b9eff; border:0.5px solid rgba(0,120,255,0.5); }
  .mc-triumph    { background:rgba(154,156,158,0.18); color:#d0d3d6; border:0.5px solid rgba(200,16,46,0.45); }
  .mc-kawasaki   { background:rgba(105,190,40,0.18); color:#8de04a; border:0.5px solid rgba(105,190,40,0.45); }
  .mc-honda      { background:rgba(204,0,0,0.18);   color:#ff6b6b; border:0.5px solid rgba(204,0,0,0.45); }
  .mc-qj         { background:rgba(0,150,136,0.20); color:#4fd1c5; border:0.5px solid rgba(0,200,180,0.45); }
  .mc-zxmoto     { background:rgba(255,107,0,0.20); color:#ff9248; border:0.5px solid rgba(255,107,0,0.5); }
  .mc-mvagusta   { background:rgba(201,48,166,0.20); color:#e074d8; border:0.5px solid rgba(220,70,200,0.5); }
  .mc-default    { background:rgba(142,142,147,0.16); color:var(--sec2); border:0.5px solid var(--sep); }
  /* 热力图用小圆点: 取制造商色实心填充 */
  .moto-dot { display:inline-block; width:6px; height:6px; border-radius:50%; margin-right:4px; vertical-align:middle; }
  .moto-dot.mc-ducati     { background:#ff5470; }
  .moto-dot.mc-yamaha     { background:#5b9eff; }
  .moto-dot.mc-triumph    { background:#d0d3d6; }
  .moto-dot.mc-kawasaki   { background:#8de04a; }
  .moto-dot.mc-honda      { background:#ff6b6b; }
  .moto-dot.mc-qj         { background:#4fd1c5; }
  .moto-dot.mc-zxmoto     { background:#ff9248; }
  .moto-dot.mc-mvagusta   { background:#e074d8; }
  .moto-dot.mc-default    { background:var(--sec2); }
  * { margin:0; padding:0; box-sizing:border-box; }
  html { background:var(--bg); }
  body { background:var(--bg); color:var(--label); -webkit-font-smoothing:antialiased; font-size:14px; line-height:1.4; overflow:hidden; }

  /* ===== 整体双栏布局 ===== */
  .app { display:grid; grid-template-columns:300px 1fr; height:100vh; width:100vw; }

  /* ===== 左侧栏 ===== */
  .sidebar { background:var(--bg-soft); border-right:0.5px solid var(--sep); display:flex; flex-direction:column; overflow:hidden; }
  .sb-header { padding:18px 20px 14px; border-bottom:0.5px solid var(--sep); }
  .brand { display:flex; align-items:center; gap:8px; margin-bottom:4px; }
  .ssp-badge { background:linear-gradient(135deg,#0a8a0a,#006600); color:#fff; font-size:10px; font-weight:700; padding:3px 7px; border-radius:5px; letter-spacing:0.5px; }
  .sb-header h1 { font-size:16px; font-weight:700; letter-spacing:-0.3px; }
  .sb-header .sub { font-size:11px; color:var(--sec); margin-top:3px; }

  /* 概览统计 */
  .sb-stats { display:grid; grid-template-columns:repeat(3,1fr); gap:6px; padding:14px 20px; border-bottom:0.5px solid var(--sep); }
  .sb-stat { text-align:center; }
  .sb-stat .v { font-size:20px; font-weight:700; color:var(--accent); letter-spacing:-0.5px; }
  .sb-stat .l { font-size:9px; color:var(--sec); text-transform:uppercase; letter-spacing:0.3px; margin-top:1px; }

  /* 导航 */
  .sb-nav { flex:1; overflow-y:auto; padding:10px 12px; }
  .sb-nav::-webkit-scrollbar { width:6px; }
  .sb-nav::-webkit-scrollbar-thumb { background:var(--sep); border-radius:3px; }
  .nav-label { font-size:10px; font-weight:700; color:var(--sec2); text-transform:uppercase; letter-spacing:1px; padding:10px 8px 6px; }
  .nav-item { display:flex; align-items:center; gap:10px; padding:8px 10px; border-radius:8px; cursor:pointer; color:var(--sec); font-size:13px; font-weight:500; transition:all .15s; }
  .nav-item:hover { background:var(--card); color:var(--label); }
  .nav-item.active { background:var(--card-2); color:var(--label); }
  .nav-item .ico { width:18px; text-align:center; font-size:14px; }
  .nav-item.active .ico { color:var(--accent); }
  .nav-divider { height:0.5px; background:var(--sep); margin:8px 8px; }
  .round-item { display:flex; align-items:center; gap:10px; padding:7px 10px; border-radius:8px; cursor:pointer; color:var(--sec); font-size:12px; transition:all .15s; }
  .round-item:hover { background:var(--card); color:var(--label); }
  .round-item.active { background:rgba(0,102,0,0.25); color:var(--ssp-bright); }
  .round-item .rn { font-size:10px; color:var(--sec2); width:14px; }
  .round-item.active .rn { color:var(--ssp-bright); }
  .round-item .nm { flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .round-item .dt { font-size:9px; color:var(--sec2); }

  .sb-footer { padding:10px 20px; border-top:0.5px solid var(--sep); font-size:9px; color:var(--sec2); line-height:1.6; }

  /* ===== 主区域 ===== */
  .main { overflow-y:auto; position:relative; }
  .main::-webkit-scrollbar { width:8px; }
  .main::-webkit-scrollbar-thumb { background:var(--sep); border-radius:4px; }
  .main-inner { padding:24px 28px 40px; max-width:1500px; }

  .page-title { display:flex; align-items:baseline; gap:12px; margin-bottom:4px; }
  .page-title h2 { font-size:24px; font-weight:700; letter-spacing:-0.5px; }
  .page-title .cnt { font-size:13px; color:var(--sec); }
  .page-desc { font-size:12px; color:var(--sec); margin-bottom:20px; }

  /* 概览英雄区 */
  .hero-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-bottom:20px; }
  .hero-card { background:var(--card); border-radius:14px; padding:16px 18px; border:0.5px solid var(--sep); }
  .hero-card.lead { background:linear-gradient(135deg,#1a1a1c,#262629); grid-column:span 2; display:flex; align-items:center; gap:14px; }
  .hero-card .crown { font-size:30px; }
  .hero-card .ti { font-size:10px; font-weight:700; letter-spacing:1px; text-transform:uppercase; }
  .hero-card .ti.gold { color:var(--gold); }
  .hero-card .ti.blue { color:var(--blue); }
  .hero-card .ti.green { color:var(--ssp-bright); }
  .hero-card .nm { font-size:17px; font-weight:700; margin-top:3px; }
  .hero-card .mt { font-size:11px; color:var(--sec); margin-top:2px; }
  .hero-card .big-v { font-size:30px; font-weight:800; color:var(--accent); letter-spacing:-1px; line-height:1; }
  .hero-card .big-u { font-size:11px; color:var(--sec); }
  .hero-card .big-l { font-size:10px; color:var(--sec); text-transform:uppercase; letter-spacing:0.5px; margin-top:6px; }

  /* 通用卡片 */
  .card { background:var(--card); border-radius:14px; overflow:hidden; border:0.5px solid var(--sep); }
  .card-hd { padding:14px 18px 10px; display:flex; align-items:center; justify-content:space-between; border-bottom:0.5px solid var(--sep); }
  .card-hd h3 { font-size:14px; font-weight:600; }
  .card-hd .meta { font-size:11px; color:var(--sec); }

  /* 双栏容器 */
  .cols-2 { display:grid; grid-template-columns:1fr 1fr; gap:16px; }

  /* 表格通用 */
  .tbl { width:100%; }
  .tbl-row { display:grid; align-items:center; gap:6px; padding:8px 18px; border-bottom:0.5px solid var(--sep); transition:background .12s; cursor:pointer; }
  .tbl-row:last-child { border-bottom:none; }
  .tbl-row:hover { background:var(--card-2); }
  .tbl-row.head { cursor:default; font-size:10px; font-weight:600; color:var(--sec2); text-transform:uppercase; letter-spacing:0.5px; padding:7px 18px; background:var(--card-2); }
  .tbl-row.head:hover { background:var(--card-2); }

  /* 积分榜行 */
  .sb-row { grid-template-columns:34px 36px 1fr 60px 60px 60px; }
  .pos { font-weight:700; text-align:center; color:var(--sec); font-size:14px; }
  .pos.p1 { color:var(--gold); } .pos.p2 { color:var(--silver); } .pos.p3 { color:var(--bronze); }
  .num-badge { background:var(--card-2); color:#fff; font-size:11px; font-weight:700; height:22px; border-radius:5px; display:flex; align-items:center; justify-content:center; }
  .rdr-name { font-size:13px; font-weight:500; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .rdr-name .fl { margin-right:3px; }
  .rdr-sub { font-size:10px; color:var(--sec); margin-top:1px; }
  .rdr-sub .w { color:var(--accent); font-weight:600; }
  .col-num { text-align:right; font-variant-numeric:tabular-nums; font-size:13px; }
  .col-num.accent { color:var(--accent); font-weight:700; }
  .col-num.muted { color:var(--sec); font-size:12px; }

  /* 比赛结果表 */
  .race-row { grid-template-columns:38px 34px 150px 1fr 40px 85px 75px 22px 78px; }
  /* 比赛结果-车队/赛车列: 两行布局, 车队在上赛车在下 */
  .tm-col { min-width:0; overflow:hidden; }
  .tm-cell { display:flex; flex-direction:column; gap:2px; }
  .tm-team { font-size:11px; color:var(--sec2); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .tm-moto { line-height:1.6; }
  /* 制造商积分榜 */
  .mfr-list { display:flex; flex-direction:column; gap:8px; padding:4px 0; }
  .mfr-row { display:grid; grid-template-columns:32px 1fr 70px; align-items:center; gap:12px; padding:8px 4px; border-bottom:0.5px solid var(--sep); }
  .mfr-row:last-child { border-bottom:none; }
  .mfr-rank { text-align:center; font-weight:700; font-size:14px; color:var(--sec2); width:26px; height:26px; line-height:26px; border-radius:6px; background:rgba(142,142,147,0.12); }
  .mfr-rank.p1 { background:rgba(255,204,0,0.18); color:#ffd60a; }
  .mfr-rank.p2 { background:rgba(142,142,147,0.22); color:#d1d1d6; }
  .mfr-rank.p3 { background:rgba(199,135,75,0.22); color:#e0a875; }
  .mfr-info { min-width:0; }
  .mfr-name { display:flex; align-items:center; gap:8px; margin-bottom:5px; }
  .mfr-cn { font-size:11px; color:var(--sec2); }
  .mfr-bar-bg { height:8px; background:rgba(58,58,60,0.6); border-radius:4px; overflow:hidden; }
  .mfr-bar { height:100%; border-radius:4px; transition:width 0.6s ease; }
  .mfr-bar.mc-ducati { background:#ff5470; }
  .mfr-bar.mc-yamaha { background:#5b9eff; }
  .mfr-bar.mc-triumph { background:#d0d3d6; }
  .mfr-bar.mc-kawasaki { background:#8de04a; }
  .mfr-bar.mc-honda { background:#ff6b6b; }
  .mfr-bar.mc-qj { background:#4fd1c5; }
  .mfr-bar.mc-zxmoto { background:#ff9248; }
  .mfr-bar.mc-mvagusta { background:#e074d8; }
  .mfr-bar.mc-default { background:var(--sec2); }
  .mfr-pts { text-align:right; font-weight:700; font-size:18px; color:var(--accent); font-variant-numeric:tabular-nums; }

  /* 状态圆点 (分站列表用) */
  .status-dot { display:inline-block; width:7px; height:7px; border-radius:50%; margin-right:6px; vertical-align:middle; flex-shrink:0; }
  .status-dot.finished { background:var(--ssp-bright); box-shadow:0 0 4px rgba(48,209,88,0.4); }
  .status-dot.live { background:var(--accent); box-shadow:0 0 4px rgba(255,159,10,0.4); }
  .status-dot.upcoming { background:var(--sec2); box-shadow:0 0 3px rgba(99,99,102,0.3); }

  /* 分站详情页 */
  .rd-header { display:flex; align-items:center; gap:14px; margin-bottom:6px; }
  .rd-header h2 { font-size:24px; font-weight:700; letter-spacing:-0.5px; }
  .rd-status-badge { font-size:10px; font-weight:700; padding:3px 8px; border-radius:6px; letter-spacing:0.5px; text-transform:uppercase; }
  .rd-status-badge.finished { background:rgba(48,209,88,0.18); color:var(--ssp-bright); }
  .rd-status-badge.live { background:rgba(255,159,10,0.18); color:var(--accent); }
  .rd-status-badge.upcoming { background:rgba(99,99,102,0.18); color:var(--sec); }
  .rd-date { font-size:12px; color:var(--sec); margin-bottom:18px; }
  .rd-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:10px; margin-bottom:18px; }
  .rd-grid .card { padding:14px 16px; }
  .rd-grid .card .big-label { font-size:9px; color:var(--sec2); text-transform:uppercase; letter-spacing:0.5px; margin-bottom:4px; }
  .rd-grid .card .big-val { font-size:16px; font-weight:700; }
  .rd-grid .card .big-sub { font-size:11px; color:var(--sec); margin-top:2px; }

  /* 历史冠军表 */
  .hist-row { display:grid; grid-template-columns:50px 1fr 1fr; align-items:center; gap:8px; padding:7px 14px; border-bottom:0.5px solid var(--sep); font-size:12px; }
  .hist-row:last-child { border-bottom:none; }
  .hist-row.head { font-size:10px; color:var(--sec2); text-transform:uppercase; letter-spacing:0.5px; background:var(--card-2); padding:6px 14px; }
  .hist-year { font-weight:700; color:var(--sec); }
  .hist-race { color:var(--label); }
  .hist-fl { font-size:11px; color:var(--sec2); }
  .hist-empty { color:var(--sec2); font-size:12px; padding:20px; text-align:center; }

  /* 预设赛道纪录行 */
  .rd-record { display:flex; align-items:center; gap:10px; }
  .rd-record .rec-label { font-size:9px; color:var(--sec2); text-transform:uppercase; }
  .rd-record .rec-val { font-size:14px; font-weight:700; color:var(--accent); }
  .race-meta-bar { background:var(--card); border-radius:14px; padding:14px 18px; margin-bottom:14px; border:0.5px solid var(--sep); display:flex; justify-content:space-between; align-items:center; gap:20px; }
  .race-meta-bar .lf { display:flex; align-items:center; gap:12px; }
  .race-meta-bar .rt { display:flex; align-items:center; gap:8px; }
  .race-tab-btn { padding:7px 16px; background:var(--card-2); color:var(--sec); border:none; border-radius:8px; font-size:12px; font-weight:600; cursor:pointer; transition:all .15s; }
  .race-tab-btn.active { background:var(--ssp); color:#fff; }
  .race-tab-btn:hover:not(.active) { color:var(--label); }
  .fl-badge { display:inline-flex; align-items:center; gap:4px; background:rgba(255,159,10,0.15); color:var(--accent); padding:3px 8px; border-radius:6px; font-size:11px; font-weight:600; }
  .gap-cell { text-align:right; font-size:11px; color:var(--sec); font-variant-numeric:tabular-nums; }
  .fl-cell { text-align:right; font-size:11px; font-variant-numeric:tabular-nums; color:var(--sec); }
  .fl-cell.best { color:var(--accent); font-weight:700; }

  /* 热力图 */
  .heatmap-card { background:var(--card); border-radius:14px; border:0.5px solid var(--sep); overflow:hidden; }
  .heatmap-wrap { padding:8px 18px 18px; overflow-x:auto; }
  .heatmap { display:grid; gap:3px; font-size:11px; min-width:760px; }
  .hm-head { display:grid; gap:3px; grid-template-columns:170px repeat(var(--ncol), minmax(0,1fr)); margin-bottom:6px; }
  .hm-hd-grp { text-align:center; font-size:10px; color:var(--sec); font-weight:600; padding:4px 0; border-bottom:0.5px solid var(--sep); }
  .hm-body-row { display:grid; gap:3px; grid-template-columns:170px repeat(var(--ncol), minmax(0,1fr)); align-items:center; }
  .hm-body-row:hover .hm-lbl { color:var(--accent); }
  .hm-lbl { font-size:11px; color:var(--label); padding:5px 8px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; cursor:pointer; }
  .hm-lbl:hover { text-decoration:underline; }
  .hm-cell { text-align:center; padding:5px 0; border-radius:4px; font-weight:700; font-size:11px; color:#fff; cursor:pointer; transition:transform .1s; }
  .hm-cell:hover { transform:scale(1.15); }
  .hm-cell.p1 { background:var(--gold); color:#000; }
  .hm-cell.p2 { background:var(--silver); color:#000; }
  .hm-cell.p3 { background:var(--bronze); }
  .hm-cell.p4t6 { background:#0a8a0a; }
  .hm-cell.p7t10 { background:#3a6b3a; }
  .hm-cell.p11p { background:#2c2c2e; color:var(--sec); }
  .hm-cell.dnf { background:#5c1f1c; color:var(--danger); }
  .hm-cell.empty { background:#111113; color:var(--sec2); }
  .legend { display:flex; gap:14px; flex-wrap:wrap; padding:10px 18px; font-size:10px; color:var(--sec); border-top:0.5px solid var(--sep); }
  .legend span { display:inline-flex; align-items:center; gap:4px; }
  .legend i { width:10px; height:10px; border-radius:2px; display:inline-block; }

  /* 车手详情抽屉 */
  .drawer { position:fixed; inset:0; z-index:100; visibility:hidden; opacity:0; transition:opacity .25s; }
  .drawer.open { visibility:visible; opacity:1; }
  .drawer-mask { position:absolute; inset:0; background:rgba(0,0,0,0.6); backdrop-filter:blur(4px); }
  .drawer-panel { position:absolute; right:0; top:0; bottom:0; width:min(560px, 92vw); background:var(--card); border-left:0.5px solid var(--sep); overflow-y:auto; transform:translateX(100%); transition:transform .3s cubic-bezier(0.2,0.8,0.2,1); }
  .drawer.open .drawer-panel { transform:translateX(0); }
  .dr-close { position:absolute; top:14px; right:18px; background:var(--card-2); color:var(--sec); border:none; width:30px; height:30px; border-radius:50%; font-size:16px; cursor:pointer; z-index:2; }
  .dr-close:hover { background:var(--sep); color:#fff; }
  .dr-header { padding:24px 28px 18px; border-bottom:0.5px solid var(--sep); background:linear-gradient(135deg,#1a1a1c,#262629); }
  .dr-header .nb { font-size:13px; color:var(--accent); font-weight:700; }
  .dr-header .nm { font-size:26px; font-weight:800; margin-top:2px; letter-spacing:-0.5px; }
  .dr-header .ct { font-size:13px; color:var(--sec); margin-top:2px; }
  .dr-stats { display:grid; grid-template-columns:repeat(4,1fr); gap:1px; background:var(--sep); margin:18px 28px; border-radius:12px; overflow:hidden; }
  .dr-stat { background:var(--card-2); padding:14px 4px; text-align:center; }
  .dr-stat .v { font-size:20px; font-weight:800; }
  .dr-stat .v.gold { color:var(--gold); } .dr-stat .v.accent { color:var(--accent); }
  .dr-stat .l { font-size:10px; color:var(--sec); margin-top:2px; text-transform:uppercase; letter-spacing:0.3px; }
  .dr-section-t { font-size:11px; font-weight:700; color:var(--sec); margin:20px 28px 10px; text-transform:uppercase; letter-spacing:0.8px; }
  .pr-grid { display:grid; grid-template-columns:1fr 1fr; gap:8px; padding:0 28px 28px; }
  .pr-row { display:grid; grid-template-columns:1fr 40px 1fr; align-items:center; gap:6px; padding:9px 12px; background:var(--card-2); border-radius:10px; }
  .pr-row .rnd { font-size:12px; font-weight:500; }
  .pr-row .rc { font-size:9px; color:var(--sec2); }
  .pr-row .pp { text-align:center; font-weight:800; font-size:14px; }
  .pr-row .pp.p1 { color:var(--gold); } .pr-row .pp.p2 { color:var(--silver); } .pr-row .pp.p3 { color:var(--bronze); } .pr-row .pp.dnf { color:var(--danger); font-size:10px; }
  .pr-row .ft { text-align:right; font-size:10px; color:var(--sec); font-variant-numeric:tabular-nums; }
  .pr-row .ft.best { color:var(--accent); font-weight:700; }

  .empty-note { color:var(--sec); font-size:13px; padding:40px 20px; text-align:center; }
</style>
</head>
<body>
<div class="app">
  <!-- ===== 左侧栏 ===== -->
  <aside class="sidebar">
    <div class="sb-header">
      <div class="brand"><span class="ssp-badge">WORLDSUPERSPORT</span></div>
      <h1>2026 成绩统计</h1>
      <div class="sub" id="subInfo"></div>
    </div>
    <div class="sb-stats">
      <div class="sb-stat"><div class="v" id="svRounds">0</div><div class="l">分站</div></div>
      <div class="sb-stat"><div class="v" id="svRaces">0</div><div class="l">场次</div></div>
      <div class="sb-stat"><div class="v" id="svRiders">0</div><div class="l">车手</div></div>
    </div>
    <nav class="sb-nav" id="sbNav">
      <div class="nav-label">视图</div>
      <div class="nav-item active" data-view="overview"><span class="ico">◉</span>概览</div>
      <div class="nav-item" data-view="standings"><span class="ico">🏆</span>积分榜</div>
      <div class="nav-item" data-view="races"><span class="ico">🏁</span>比赛成绩</div>
      <div class="nav-item" data-view="heatmap"><span class="ico">▦</span>赛季全景</div>
      <div class="nav-divider"></div>
      <div class="nav-label">分站</div>
      <div id="roundList"></div>
    </nav>
    <div class="sb-footer" id="sbFooter"></div>
  </aside>

  <!-- ===== 主区域 ===== -->
  <main class="main">
    <div class="main-inner" id="content"></div>
  </main>
</div>

<!-- 车手详情抽屉 -->
<div class="drawer" id="drawer">
  <div class="drawer-mask" onclick="closeDrawer()"></div>
  <div class="drawer-panel" id="drawerPanel"></div>
</div>

<script>
const D = __DATA__;
const FLAGS = __FLAGS__;
const RACE_LABELS = {RC1:'Race 1', RC2:'Race 2'};

function fmtLap(ms){ if(!ms) return '—'; ms=Math.round(ms); const m=Math.floor(ms/60000), s=Math.floor((ms%60000)/1000), x=ms%1000; return m+':'+String(s).padStart(2,'0')+'.'+String(x).padStart(3,'0'); }
function fmtGap(ms){ if(ms==null) return '—'; if(ms<=0) return '—'; const s=ms/1000; if(s<60) return '+'+s.toFixed(3); const m=Math.floor(s/60); return '+'+m+':'+(s%60).toFixed(1); }
// 格式化总完赛时间 (如 32:15.456 或 1:02:15.456)
function fmtTime(ms){
  if(ms==null||ms<=0) return '—';
  ms=Math.round(ms);
  const totSec=Math.floor(ms/1000), mm=Math.floor(totSec/60), ss=totSec%60, x=ms%1000;
  const hh=Math.floor(mm/60);
  const secStr = String(ss).padStart(2,'0')+'.'+String(x).padStart(3,'0');
  if(hh>0) return hh+':'+String(mm%60).padStart(2,'0')+':'+secStr;
  return mm+':'+secStr;
}
function flag(cc){ return FLAGS[cc] || '🏁'; }
function escH(s){ return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
// 制造商品牌色 chip：根据摩托车型号返回高亮 HTML
function motChip(motorcycle){
  if(!motorcycle) return '';
  return `<span class="moto-chip ${motCls(motorcycle)}">${escH(motorcycle)}</span>`;
}
// 返回制造商色 CSS class
function motCls(motorcycle){
  if(!motorcycle) return 'mc-default';
  const m = motorcycle.toLowerCase();
  if(m.includes('ducati')) return 'mc-ducati';
  if(m.includes('yamaha')) return 'mc-yamaha';
  if(m.includes('triumph')) return 'mc-triumph';
  if(m.includes('kawasaki')||m.includes('zx-6')||m.includes('ninja')) return 'mc-kawasaki';
  if(m.includes('honda')) return 'mc-honda';
  if(m.includes('qj motor')||m.includes('qjmoto')) return 'mc-qj';
  if(m.includes('zxmoto')) return 'mc-zxmoto';
  if(m.includes('mv agusta')) return 'mc-mvagusta';
  return 'mc-default';
}
// 制造商品牌色圆点 (热力图用, 不占空间)
function motDot(motorcycle){
  if(!motorcycle) return '';
  return `<span class="moto-dot ${motCls(motorcycle)}" title="${escH(motorcycle)}"></span>`;
}

const rounds = D.round_order.map(k => ({k, ...D.rounds[k]}));
const racesByRound = {};
D.races.forEach(r => { (racesByRound[r.round] = racesByRound[r.round] || []).push(r); });

let curView='overview', curRound=D.round_order[0], curRaceTab='RC1';

// 侧栏分站列表
function renderSidebar(){
  document.getElementById('svRounds').textContent = D.total_rounds_done;
  document.getElementById('svRaces').textContent = D.total_races;
  document.getElementById('svRiders').textContent = D.total_riders;
  const gen = D.generated ? new Date(D.generated) : new Date();
  document.getElementById('subInfo').textContent = `${D.total_rounds_done}站 · ${D.total_races}场 · ${D.total_riders}车手`;
  document.getElementById('sbFooter').innerHTML = 'WorldSBK 官方数据<br>更新于 ' + gen.toLocaleDateString('zh-CN');
  let h='';
  rounds.forEach((rd,i)=>{
    const dotClass = rd.status==='FINISHED'?'finished':rd.status==='LIVE'?'live':'upcoming';
    const isActive = rd.k===curRound && (curView==='races'||curView==='roundDetail');
    h += `<div class="round-item ${isActive?'active':''}" onclick="goRound('${rd.k}')">
      <span class="status-dot ${dotClass}"></span><span class="nm">${flag(rd.country)} ${rd.k}</span><span class="dt">${rd.date||''}</span></div>`;
  });
  document.getElementById('roundList').innerHTML = h;
  document.querySelectorAll('.nav-item').forEach(n=>{
    n.classList.toggle('active', n.dataset.view===curView);
  });
}

function render(){
  renderSidebar();
  const c=document.getElementById('content');
  if(curView==='overview') c.innerHTML=viewOverview();
  else if(curView==='standings') c.innerHTML=viewStandings();
  else if(curView==='races') c.innerHTML=viewRaces();
  else if(curView==='roundDetail') c.innerHTML=viewRoundDetail();
  else if(curView==='heatmap') c.innerHTML=viewHeatmap();
}

// ===== 概览 =====
function viewOverview(){
  const leader=D.riders[0];
  const topFl=[...D.riders].filter(r=>r.fastest_fl).sort((a,b)=>a.fastest_fl-b.fastest_fl)[0]||{};
  const mostWins=[...D.riders].sort((a,b)=>b.wins-a.wins)[0];
  let html=`<div class="page-title"><h2>赛季概览</h2><span class="cnt">2026 WorldSSP</span></div>
    <div class="page-desc">世界超级摩托车锦标赛 · 超级运动组（600cc）· 已完赛 ${D.total_rounds_done} 个分站</div>`;
  // 英雄卡
  html+=`<div class="hero-grid">
    <div class="hero-card lead">
      <div class="crown">👑</div>
      <div style="flex:1"><div class="ti gold">积分领跑</div>
        <div class="nm">${flag(leader.country)} #${leader.num} ${leader.name}</div>
        <div class="mt">${leader.team?`<span style="color:var(--sec2)">${escH(leader.team)}</span>`:''}${leader.team&&leader.motorcycle?' · ':''}${motChip(leader.motorcycle)}</div>
        <div class="mt">${leader.wins}胜 · ${leader.podiums}领奖台 · 平均完赛P${leader.avg_pos||'—'}</div></div>
      <div style="text-align:right"><div style="font-size:30px;font-weight:800;color:var(--accent)">${leader.points}</div><div style="font-size:11px;color:var(--sec)">PTS</div></div>
    </div>
    <div class="hero-card">
      <div class="ti blue">⚡赛季最快圈</div>
      <div class="nm" style="font-size:14px;margin-top:6px">${topFl.name?flag(topFl.country)+' '+topFl.name:'—'}</div>
      <div class="mt">${topFl.team?`<span style="color:var(--sec2)">${escH(topFl.team)}</span>`:''}${topFl.team&&topFl.motorcycle?' · ':''}${motChip(topFl.motorcycle)}</div>
      <div class="mt">${fmtLap(topFl.fastest_fl)}</div>
    </div>
    <div class="hero-card">
      <div class="ti green">🏆最多胜场</div>
      <div class="nm" style="font-size:14px;margin-top:6px">${flag(mostWins.country)} ${mostWins.name}</div>
      <div class="mt">${mostWins.team?`<span style="color:var(--sec2)">${escH(mostWins.team)}</span>`:''}${mostWins.team&&mostWins.motorcycle?' · ':''}${motChip(mostWins.motorcycle)}</div>
      <div class="mt">${mostWins.wins} 场胜利</div>
    </div>
  </div>`;

  // 双栏：左=分站冠军一览，右=积分TOP10
  html+=`<div class="cols-2" style="margin-top:8px">`;
  // 左：分站冠军
  html+=`<div class="card"><div class="card-hd"><h3>分站冠军</h3><span class="meta">每场 Race 1 冠军</span></div>`;
  rounds.forEach((rd,i)=>{
    const r1=racesByRound[rd.k]?.find(r=>r.race==='RC1');
    const w=r1?.results.find(x=>x.pos===1);
    html+=`<div class="tbl-row sb-row" style="grid-template-columns:30px 1fr 1fr" onclick="goRace('${rd.k}')">
      <div style="color:var(--sec);font-size:11px;text-align:center">${i+1}</div>
      <div><div class="rdr-name">${flag(rd.country)} ${rd.name}</div><div class="rdr-sub">${rd.date||''}</div></div>
      <div style="text-align:right">${w?`<div style="font-weight:600;font-size:12px">${flag(w.country)} ${w.name}</div><div class="rdr-sub">${w.team?`<span style="color:var(--sec2)">${escH(w.team)}</span>`:''}${w.team&&w.motorcycle?' · ':''}${motChip(w.motorcycle)}<br>最快圈 ${fmtLap(r1.fastest_lap_ms)}</div>`:'<span style="color:var(--sec2)">未进行</span>'}</div>
    </div>`;
  });
  html+=`</div>`;

  // 右：积分TOP10
  html+=`<div class="card"><div class="card-hd"><h3>积分榜 TOP 10</h3><span class="meta">官方积分</span></div>`;
  D.riders.slice(0,10).forEach((r,i)=>{
    const pk=i<3?('p'+(i+1)):'';
    const teamTxt = r.team ? `<span style="color:var(--sec2)">${escH(r.team)}</span>` : '';
    const sep = teamTxt && r.motorcycle ? ' · ' : '';
    html+=`<div class="tbl-row sb-row" onclick="openRider('${r.id}')">
      <div class="pos ${pk}">${i+1}</div>
      <div class="num-badge">${r.num||'-'}</div>
      <div><div class="rdr-name"><span class="fl">${flag(r.country)}</span>${r.name}</div><div class="rdr-sub">${(teamTxt||r.motorcycle)?(teamTxt+sep+motChip(r.motorcycle)+' · '):''}<span class="w">${r.wins}胜</span> · ${r.podiums}台 · ${r.fl}⚡</div></div>
      <div class="col-num muted">${r.starts}</div>
      <div class="col-num muted">${r.wins}</div>
      <div class="col-num accent">${r.points}</div>
    </div>`;
  });
  html+=`<div class="tbl-row head sb-row" style="margin-top:0"><div></div><div></div><div></div><div class="col-num" style="font-size:9px">出场</div><div class="col-num" style="font-size:9px">胜</div><div class="col-num" style="font-size:9px">积分</div></div>`;
  html+=`</div></div>`;
  return html;
}

// ===== 积分榜 =====
function viewStandings(){
  let html=`<div class="page-title"><h2>车手积分榜</h2><span class="cnt">${D.riders.length} 位车手</span></div>
    <div class="page-desc">官方年度积分 · WorldSSP 2026 · 前 15 名完赛获分 (25-20-16-13-11-10-9-8-7-6-5-4-3-2-1)</div>`;
  html+=`<div class="card"><div class="card-hd"><h3>完整排名</h3><span class="meta">点击车手查看详情</span></div>`;
  html+=`<div class="tbl-row head sb-row"><div>名次</div><div>#</div><div>车手</div><div class="col-num">出场</div><div class="col-num">胜/台</div><div class="col-num">积分</div></div>`;
  D.riders.forEach((r,i)=>{
    const pk=i<3?('p'+(i+1)):'';
    const teamMoto = r.team ? `<span style="color:var(--sec2)">${escH(r.team)}</span>` : '';
    const motoChip = motChip(r.motorcycle);
    const sep = teamMoto && motoChip ? ' · ' : '';
    html+=`<div class="tbl-row sb-row" onclick="openRider('${r.id}')">
      <div class="pos ${pk}">${i+1}</div>
      <div class="num-badge">${r.num||'-'}</div>
      <div><div class="rdr-name"><span class="fl">${flag(r.country)}</span>${r.name}</div>
        <div class="rdr-sub">${teamMoto||motoChip?(teamMoto+sep+motoChip+' · '):''}<span class="w">${r.wins}胜</span> · ${r.podiums}领奖台 · ${r.fl}最快圈 · ${r.dnf}退赛</div></div>
      <div class="col-num muted">${r.starts}</div>
      <div class="col-num muted">${r.wins}/${r.podiums}</div>
      <div class="col-num accent">${r.points}</div>
    </div>`;
  });
  html+=`</div>`;

  // ===== 厂商积分榜 =====
  if(D.manufacturers && D.manufacturers.length){
    const mfs = D.manufacturers;
    const maxPts = Math.max(...mfs.map(m=>m.points||0), 1);
    html+=`<div class="card"><div class="card-hd"><h3>🏆 制造商积分榜</h3><span class="meta">官方厂商年度积分</span></div>`;
    html+=`<div class="mfr-list">`;
    mfs.forEach((m,i)=>{
      const pct = Math.round((m.points/maxPts)*100);
      const pk = i<3?('p'+(i+1)):'';
      // 制造商中文名映射
      const cnNames = {'Yamaha':'雅马哈','Ducati':'杜卡迪','ZXMOTO':'张雪机车','Triumph':'凯旋','Kawasaki':'川崎','Honda':'本田','MV Agusta':'奥古斯塔','QJ Motor':'钱江','QJMOTOR':'钱江'};
      html+=`<div class="mfr-row">
        <div class="mfr-rank ${pk}">${m.pos||i+1}</div>
        <div class="mfr-info">
          <div class="mfr-name">${motChip(m.name)}<span class="mfr-cn">${cnNames[m.name]||''}</span></div>
          <div class="mfr-bar-bg"><div class="mfr-bar ${motCls(m.name)}" style="width:${pct}%"></div></div>
        </div>
        <div class="mfr-pts">${m.points}</div>
      </div>`;
    });
    html+=`</div></div>`;
  }
  return html;
}
function viewRaces(){
  const rd=D.rounds[curRound];
  const rcs=racesByRound[curRound]||[];
  const cur=rcs.find(r=>r.race===curRaceTab)||rcs[0];
  let html=`<div class="page-title"><h2>比赛成绩</h2><span class="cnt">${flag(rd.country)} ${rd.name}</span></div>
    <div class="page-desc">${rd.circuit} · ${rd.country}</div>`;
  if(!cur) return html+'<div class="empty-note">该分站暂无比赛数据</div>';

  html+=`<div class="race-meta-bar">
    <div class="lf"><div><div style="font-size:11px;color:var(--sec)">${rd.name} · ${cur.date}</div>
      <div style="font-size:13px;color:var(--sec);margin-top:2px">${cur.results.length} 位车手参赛</div></div></div>
    <div class="rt">`;
  ['RC1','RC2'].forEach(rt=>{
    if(rcs.find(r=>r.race===rt)) html+=`<button class="race-tab-btn ${rt===cur.race?'active':''}" onclick="setRaceTab('${rt}')">${RACE_LABELS[rt]}</button>`;
  });
  html+=`</div></div>`;

  // 最快圈横条
  html+=`<div class="card" style="margin-bottom:14px;padding:12px 18px;display:flex;justify-content:space-between;align-items:center">
    <div><div style="font-size:10px;color:var(--sec);text-transform:uppercase;letter-spacing:0.5px">全场最快圈</div>
      <div style="font-size:15px;font-weight:600;margin-top:3px">${cur.fastest_lap_rider?flag('')+' '+cur.fastest_lap_rider:'—'}</div></div>
    <div class="fl-badge">⚡ ${fmtLap(cur.fastest_lap_ms)}</div>
  </div>`;

  html+=`<div class="card"><div class="tbl-row head race-row"><div>名次</div><div>#</div><div>车手</div><div>车队 / 赛车</div><div class="col-num">圈数</div><div class="col-num">完赛时间</div><div class="gap-cell">差距</div><div></div><div class="fl-cell">最快圈</div></div>`;
  cur.results.forEach(r=>{
    const pos=r.pos;
    const pk = pos===1?'p1':pos===2?'p2':pos===3?'p3':(r.status!=='Classified'&&pos>20?'dnf':'');
    const posTxt = (r.status!=='Classified'&&pos>20) ? r.status.substr(0,3).toUpperCase() : pos;
    const isFl = r.fl_pos===1;
    const teamLine = r.team ? `<div class="tm-team">${escH(r.team)}</div>` : '';
    const motoLine = r.motorcycle ? `<div class="tm-moto">${motChip(r.motorcycle)}</div>` : '';
    const teamCell = (teamLine||motoLine) ? `<div class="tm-cell">${teamLine}${motoLine}</div>` : '<span style="color:var(--sec2)">—</span>';
    const notClassified = r.status!=='Classified'&&pos>20;
    html+=`<div class="tbl-row race-row" onclick="openRider('${r.id}')">
      <div class="pos ${pk}">${posTxt}</div>
      <div class="num-badge">${r.num||'-'}</div>
      <div><div class="rdr-name"><span class="fl">${flag(r.country)}</span>${r.name}</div></div>
      <div class="tm-col">${teamCell}</div>
      <div class="col-num muted">${r.laps||'—'}</div>
      <div class="col-num">${notClassified?'—':fmtTime(r.time_ms)}</div>
      <div class="gap-cell">${fmtGap(r.gap_ms)}</div>
      <div>${isFl?'<span style="color:var(--accent)">⚡</span>':''}</div>
      <div class="fl-cell ${isFl?'best':''}">${fmtLap(r.fl_ms)}</div>
    </div>`;
  });
  html+=`</div>`;
  return html;
}

// ===== 分站详情 =====
function viewRoundDetail(){
  const rd = D.rounds[curRound];
  if(!rd) return '<div class="empty-note">分站数据不可用</div>';
  
  const cir = D.circuits ? D.circuits[rd.circuit_id||''] : null;
  const hist = D.history ? D.history[rd.circuit_id||''] : null;
  const rcs = racesByRound[curRound]||[];
  const statusLabel = rd.status==='FINISHED'?'已完赛':(rd.status==='LIVE'?'进行中':'未开始');
  const statusClass = rd.status==='FINISHED'?'finished':(rd.status==='LIVE'?'live':'upcoming');
  
  let html=`<div class="page-title"><h2>${rd.name||curRound}</h2><span class="cnt">${flag(rd.country)} ${rd.circuit||''}</span></div>
    <div class="rd-header">
      <div class="rd-status-badge ${statusClass}">${statusLabel}</div>
    </div>
    <div class="rd-date">${rd.date||''}${(rd.end_date&&rd.end_date!==rd.date)?' ~ '+rd.end_date:''}</div>`;
  
  if(cir){
    const lenKm = cir.length_m ? (cir.length_m/1000).toFixed(3)+' km' : '—';
    html+=`<div class="rd-grid">
      <div class="card"><div class="big-label">赛道长度</div><div class="big-val">${lenKm}</div><div class="big-sub">${cir.name||''}</div></div>
      <div class="card"><div class="big-label">地点</div><div class="big-val">${cir.locality||'—'}</div><div class="big-sub">${flag(cir.country||rd.country)} ${cir.country||rd.country||''}</div></div>
      <div class="card"><div class="big-label">比赛状态</div><div class="big-val">${rcs.length?rcs.length+' 场':'—'}</div><div class="big-sub">${rcs.length?'已完赛':'数据待更新'}</div></div>
    </div>`;
  } else {
    html+=`<div class="rd-grid">
      <div class="card"><div class="big-label">赛道</div><div class="big-val">${rd.circuit||'—'}</div></div>
      <div class="card"><div class="big-label">国家</div><div class="big-val">${flag(rd.country)} ${rd.country||''}</div></div>
      <div class="card"><div class="big-label">比赛状态</div><div class="big-val">${rcs.length?rcs.length+' 场':'—'}</div></div>
    </div>`;
  }
  
  // 历年冠军
  if(hist){
    const years = Object.keys(hist).sort().reverse();
    if(years.length){
      html+=`<div class="card" style="margin-bottom:18px">
        <div class="card-hd"><h3>🏆 历年冠军</h3><span class="meta">${cir?cir.name+' 赛道':''}</span></div>`;
      html+=`<div class="hist-row head"><div>年份</div><div>Race 1 冠军 / 赛车</div><div>Race 2 冠军 / 赛车</div></div>`;
      years.forEach(yr => {
        const races = hist[yr];
        const r1 = races.find(r=>r.race==='RC1')||{};
        const r2 = races.find(r=>r.race==='RC2')||{};
        const fl1 = r1.fl_ms ? fmtLap(r1.fl_ms) : '';
        const fl2 = r2.fl_ms ? fmtLap(r2.fl_ms) : '';
        const fl1r = r1.fl_rider ? ' ('+escH(r1.fl_rider)+')' : '';
        const fl2r = r2.fl_rider ? ' ('+escH(r2.fl_rider)+')' : '';
        // 车队+赛车副标题
        const sub1 = (r1.team||r1.motorcycle) ? `<div style="display:flex;align-items:center;flex-wrap:wrap;gap:2px;margin-top:1px">${r1.team?`<span style="color:var(--sec2);font-size:10px">${escH(r1.team)}</span>`:''}${r1.team&&r1.motorcycle?' · ':''}${motChip(r1.motorcycle)}</div>` : '';
        const sub2 = (r2.team||r2.motorcycle) ? `<div style="display:flex;align-items:center;flex-wrap:wrap;gap:2px;margin-top:1px">${r2.team?`<span style="color:var(--sec2);font-size:10px">${escH(r2.team)}</span>`:''}${r2.team&&r2.motorcycle?' · ':''}${motChip(r2.motorcycle)}</div>` : '';
        html+=`<div class="hist-row">
          <div class="hist-year">${yr}</div>
          <div><div class="hist-race">${r1.winner?escH(r1.winner):'—'}</div>${sub1}<div class="hist-fl">${fl1?('⚡ '+fl1+fl1r):''}</div></div>
          <div><div class="hist-race">${r2.winner?escH(r2.winner):'—'}</div>${sub2}<div class="hist-fl">${fl2?('⚡ '+fl2+fl2r):''}</div></div>
        </div>`;
      });
      html+=`</div>`;
    }
  }
  
  // 2026 年该站比赛结果
  if(rcs.length){
    html+=`<div class="card-hd" style="padding:0 4px 12px;border:none"><h3>🏁 2026 年比赛结果</h3></div>`;
    html+=`<div class="cols-2">`;
    rcs.forEach((race, ri) => {
      const raceLabel = race.race==='RC1'?'Race 1':'Race 2';
      html+=`<div class="card"><div class="card-hd"><h3>${raceLabel}</h3><span class="meta">${race.date||''} · ${race.results.length} 人</span></div>`;
      if(race.fastest_lap_ms){
        html+=`<div style="padding:8px 14px;display:flex;gap:10px;border-bottom:0.5px solid var(--sep)">
          <div style="flex:1;text-align:center;background:var(--card-2);border-radius:8px;padding:8px">
            <div style="font-size:9px;color:var(--gold);text-transform:uppercase">🥇 冠军</div>
            <div style="font-size:12px;font-weight:700;margin-top:2px">${race.results[0]?flag(race.results[0].country)+' '+race.results[0].name:'—'}</div>
          </div>
          <div style="flex:1;text-align:center;background:var(--card-2);border-radius:8px;padding:8px">
            <div style="font-size:9px;color:var(--sec2);text-transform:uppercase">⚡ 全场最快</div>
            <div style="font-size:12px;font-weight:700;margin-top:2px;color:var(--accent)">${fmtLap(race.fastest_lap_ms)}</div>
            <div style="font-size:10px;color:var(--sec)">${race.fastest_lap_rider?escH(race.fastest_lap_rider):''}</div>
          </div>
        </div>`;
      }
      const topN = race.results.slice(0,10);
      html+=`<div class="tbl-row head" style="grid-template-columns:30px 28px 1fr 50px 70px 60px;padding:5px 14px">
        <div>名次</div><div>#</div><div>车手 / 赛车</div><div class="col-num">圈数</div><div class="gap-cell">差距</div><div class="fl-cell">最快圈</div></div>`;
      topN.forEach(r => {
        const pk = r.pos===1?'p1':r.pos===2?'p2':r.pos===3?'p3':'';
        const isFl = r.fl_pos===1;
        const teamLine = r.team ? `<span style="color:var(--sec2);font-size:10px">${escH(r.team)}</span>` : '';
        const motoLine = r.motorcycle ? motChip(r.motorcycle) : '';
        const nameSub = (teamLine||motoLine) ? `<div style="display:flex;align-items:center;gap:4px;margin-top:1px">${teamLine}${teamLine&&motoLine?' · ':''}${motoLine}</div>` : '';
        html+=`<div class="tbl-row" style="grid-template-columns:30px 28px 1fr 50px 70px 60px;padding:5px 14px" onclick="openRider('${r.id}')">
          <div class="pos ${pk}">${r.pos}</div>
          <div class="num-badge" style="width:24px;height:22px;font-size:10px">${r.num||'-'}</div>
          <div style="min-width:0"><div style="font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"><span class="fl">${flag(r.country)}</span>${r.name}</div>${nameSub}</div>
          <div class="col-num muted" style="font-size:11px">${r.laps||'—'}</div>
          <div class="gap-cell" style="font-size:11px">${fmtGap(r.gap_ms)}</div>
          <div class="fl-cell ${isFl?'best':''}" style="font-size:11px">${isFl?'⚡ ':''}${fmtLap(r.fl_ms)}</div>
        </div>`;
      });
      if(race.results.length>10){
        html+=`<div style="padding:6px 14px;text-align:center;color:var(--sec2);font-size:11px;border-top:0.5px solid var(--sep)">共 ${race.results.length} 名车手</div>`;
      }
      html+=`</div>`;
    });
    html+=`</div>`;
  } else {
    html+=`<div class="empty-note">该分站比赛尚未开始，敬请期待</div>`;
  }
  
  return html;
}

// ===== 热力图 =====
function viewHeatmap(){
  const ncol = rounds.length;
  const top = D.riders.slice(0, 25);
  let html=`<div class="page-title"><h2>赛季全景</h2><span class="cnt">TOP ${top.length} 车手</span></div>
    <div class="page-desc">每场比赛完赛位置热力图 · 横轴=分站×Race · 纵轴=车手</div>`;
  html+=`<div class="heatmap-card"><div class="heatmap-wrap"><div class="heatmap" style="--ncol:${ncol*2}">`;
  // 表头 (每站跨2列)
  html+=`<div class="hm-head"><div></div>`;
  rounds.forEach(rd=>{ html+=`<div class="hm-hd-grp" style="grid-column:span 2">${flag(rd.country)} ${rd.k}</div>`; });
  html+=`</div>`;
  // 每个车手一行
  top.forEach(r=>{
    const tm = [r.team, r.motorcycle].filter(Boolean).join(' · ');
    html+=`<div class="hm-body-row"><div class="hm-lbl" onclick="openRider('${r.id}')" title="${escH(tm)}">${motDot(r.motorcycle)}${flag(r.country)} ${r.name} <span style="color:var(--sec2);font-size:10px">#${r.num}</span></div>`;
    rounds.forEach(rd=>{
      ['RC1','RC2'].forEach(rt=>{
        const rk=rd.k+'_'+rt;
        const pr=r.per_race[rk];
        let cls='empty', txt='–';
        if(pr){
          const p=pr.pos;
          if(pr.status!=='Classified'&&p>20){ cls='dnf'; txt='×'; }
          else if(p===1){cls='p1';txt='1';}
          else if(p===2){cls='p2';txt='2';}
          else if(p===3){cls='p3';txt='3';}
          else if(p<=6){cls='p4t6';txt=p;}
          else if(p<=10){cls='p7t10';txt=p;}
          else {cls='p11p';txt=p;}
        }
        html+=`<div class="hm-cell ${cls}" title="${r.name} · ${rd.k} ${rt} · ${pr?('P'+pr.pos):'未参赛'}" onclick="openRider('${r.id}')">${txt}</div>`;
      });
    });
    html+=`</div>`;
  });
  html+=`</div></div>`;
  html+=`<div class="legend">
    <span><i style="background:var(--gold)"></i>冠军</span>
    <span><i style="background:var(--silver)"></i>亚军</span>
    <span><i style="background:var(--bronze)"></i>季军</span>
    <span><i style="background:#0a8a0a"></i>4-6</span>
    <span><i style="background:#3a6b3a"></i>7-10</span>
    <span><i style="background:#2c2c2e"></i>10+</span>
    <span><i style="background:#5c1f1c"></i>退赛</span>
    <span><i style="background:#111113"></i>未参赛</span>
  </div></div>`;
  return html;
}

// ===== 车手详情抽屉 =====
function openRider(id){
  const r=D.riders.find(x=>x.id===id);
  if(!r) return;
  const subLine = `${r.team?`<span style="color:var(--sec2)">${escH(r.team)}</span>`:''}${r.team&&r.motorcycle?' · ':''}${motChip(r.motorcycle)}` || r.country||'';
  let h=`<button class="dr-close" onclick="closeDrawer()">✕</button>
    <div class="dr-header">
      <div class="nb">#${r.num||'-'}</div>
      <div class="nm">${flag(r.country)} ${r.name}</div>
      <div class="ct">${subLine}</div>
    </div>
    <div class="dr-stats">
      ${ds(r.points,'积分','accent')}${ds(r.wins,'胜场','gold')}${ds(r.podiums,'领奖台','gold')}${ds(r.fl,'最快圈')}
      ${ds(r.starts,'出场')}${ds(r.p2,'P2')}${ds(r.p3,'P3')}${ds(r.dnf,'退赛')}
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;padding:0 28px;margin-bottom:4px">
      <div style="background:var(--card-2);border-radius:10px;padding:12px;text-align:center"><div style="font-size:10px;color:var(--sec);text-transform:uppercase;letter-spacing:0.3px">平均完赛位</div><div style="font-size:20px;font-weight:800;margin-top:2px">${r.avg_pos||'—'}</div></div>
      <div style="background:var(--card-2);border-radius:10px;padding:12px;text-align:center"><div style="font-size:10px;color:var(--sec);text-transform:uppercase;letter-spacing:0.3px">赛季最快圈</div><div style="font-size:20px;font-weight:800;margin-top:2px;color:var(--accent)">${fmtLap(r.fastest_fl)}</div></div>
    </div>
    <div class="dr-section-t">各分站表现</div>
    <div class="pr-grid">`;
  rounds.forEach(rd=>{
    ['RC1','RC2'].forEach(rt=>{
      const rk=rd.k+'_'+rt;
      const pr=r.per_race[rk];
      if(!pr) return;
      const race=D.races.find(x=>x.rk===rk);
      const p=pr.pos;
      let pk = p===1?'p1':p===2?'p2':p===3?'p3':(pr.status!=='Classified'&&p>20?'dnf':'');
      const posTxt = (pr.status!=='Classified'&&p>20) ? pr.status.substr(0,3).toUpperCase() : p;
      const myFl = race && race.results.find(x=>x.id===id);
      const isFl = myFl && myFl.fl_pos===1;
      h+=`<div class="pr-row">
        <div><div class="rnd">${flag(rd.country)} ${rd.k}</div><div class="rc">${RACE_LABELS[rt]} · ${rd.date||''}</div></div>
        <div class="pp ${pk}">${posTxt}</div>
        <div class="ft ${isFl?'best':''}">${myFl&&myFl.fl_ms?fmtLap(myFl.fl_ms):'—'}</div>
      </div>`;
    });
  });
  h+=`</div>`;
  document.getElementById('drawerPanel').innerHTML=h;
  document.getElementById('drawer').classList.add('open');
}
function ds(v,l,c){ return `<div class="dr-stat"><div class="v ${c||''}">${v}</div><div class="l">${l}</div></div>`; }
function closeDrawer(){ document.getElementById('drawer').classList.remove('open'); }

function setView(v){ curView=v; render(); document.querySelector('.main').scrollTop=0; }
function setRound(k){ curRound=k; const rcs=racesByRound[k]||[]; if(!rcs.find(r=>r.race===curRaceTab)) curRaceTab=rcs[0]?.race||'RC1'; }
function setRaceTab(rt){ curRaceTab=rt; render(); }
function goRace(k){ setRound(k); setView('races'); }
function goRound(k){ curRound=k; setView('roundDetail'); }

// 绑定侧栏导航
document.querySelectorAll('.nav-item').forEach(n=>{
  n.onclick=()=>setView(n.dataset.view);
});

// ESC 关闭抽屉
document.addEventListener('keydown', e=>{ if(e.key==='Escape') closeDrawer(); });

render();
</script>
</body>
</html>
"""

final_html = HTML.replace("__DATA__", DATA_JSON).replace("__FLAGS__", json.dumps(FLAGS, ensure_ascii=False))

out_path = os.path.join(HERE, "index.html")
with open(out_path, "w", encoding="utf-8") as f:
    f.write(final_html)

print(f"✅ 已生成 {out_path}")
print(f"   文件大小: {os.path.getsize(out_path)//1024} KB")
print(f"   车手数: {len(front_riders)} / 比赛数: {len(front_races)}")
