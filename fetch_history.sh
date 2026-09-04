#!/bin/bash
# fetch_history.sh — 拉取往年 WorldSSP 各赛道历史冠军和最快圈速
# 数据源: WSBK Pulselive API (bash curl 拉取, python 解析)
# 输出: history_cache.json
# 用法: bash fetch_history.sh

set -euo pipefail
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
API="https://api.wsbk.pulselive.com"
DIR="$(cd "$(dirname "$0")" && pwd)"
RAW="$DIR/raw"
mkdir -p "$RAW"

get() { curl -sf -A "$UA" -H "x-client: FE" -H "Referer: https://www.worldsbk.com/" -m 30 "$API$1"; }

echo "=== 拉取历年 WorldSSP 赛道数据 ==="

[ ! -f "$DIR/data.json" ] && { echo "❌ 请先运行 fetch_data.sh"; exit 1; }

# 先读出 2026 有哪些赛道 (circuit_id 列表)
CIRCUITS_2026=$(python3 -c "
import json
d = json.load(open('$DIR/data.json'))
for cid in d.get('circuits', {}):
    print(cid)
")
echo "2026 年赛道: $(echo \"$CIRCUITS_2026\" | wc -l | tr -d ' ')"

# 对每个历史赛季
for YEAR in 2025 2024 2023; do
    echo ""
    echo "=== ${YEAR} 赛季 ==="

    # 1. 拉取该年分站列表
    OUTF="$RAW/rounds_${YEAR}.json"
    get "/wsbk-events/v1/seasons/${YEAR}/rounds" > "$OUTF" 2>/dev/null || {
        echo "  ⚠️  获取分站列表失败"; continue
    }
    echo "  rounds.json ($(wc -c < "$OUTF") 字节)"

    # 2. 找到该赛季中与 2026 赛道重合的分站
    ROUNDS=$(python3 -c "
import json
import sys
with open('$OUTF') as f:
    d = json.load(f)
circuits_2026 = set('''
$CIRCUITS_2026
'''.strip().split())
inc_circuits = {}
for inc in d.get('included', []):
    if inc.get('type') == 'circuits':
        inc_circuits[inc['id']] = inc.get('attributes', {}).get('name', inc['id'])
for r in d.get('data', []):
    a = r.get('attributes', {})
    rd_id = a.get('source_id', '')
    circuit_rel = r.get('relationships', {}).get('circuit', {}).get('data', {})
    circuit_id = circuit_rel.get('id', '') if circuit_rel else ''
    circ_name = inc_circuits.get(circuit_id, circuit_id)
    if circuit_id in circuits_2026:
        print(f'{rd_id}|{circuit_id}|{circ_name}')
    # 也匹配 PHILL -> ? 直接用 circuit_id 匹配
")
    [ -z "$ROUNDS" ] && { echo "  无匹配赛道"; continue; }

    echo "$ROUNDS" | while IFS='|' read -r RD_ID C_ID C_NAME; do
        echo "  赛道 ${C_NAME} (${C_ID}) / 分站 ${RD_ID} ..."
        
        # 3. 拉取 sessions
        SESS="$RAW/sessions_${YEAR}_${RD_ID}.json"
        get "/wsbk-events/v1/seasons/${YEAR}/rounds/${RD_ID}/sessions" > "$SESS" 2>/dev/null || {
            echo "    sessions 获取失败"; continue
        }
        
        # 4. 找 SSP RC1/RC2
        SSP_SIDS=$(python3 -c "
import json
with open('$SESS') as f:
    d = json.load(f)
for s in d.get('data', []):
    if 'SSP' not in s.get('id',''): continue
    sa = s.get('attributes', {})
    sn = sa.get('short_name', '')
    if sn in ('RC1','RC2'):
        src = sa.get('source_id', '')
        print(f'{sn}={src}')
")
        [ -z "$SSP_SIDS" ] && { echo "    无 SSP 数据"; continue; }

        # 5. 对 RC1/RC2 逐一拉取结果
        while IFS='=' read -r RACE SID; do
            RES="$RAW/hist_${YEAR}_${RD_ID}_${SID}.json"
            get "/wsbk-results/v1/seasons/${YEAR}/categories/SSP/rounds/${RD_ID}/sessions/${SID}/results" > "$RES" 2>/dev/null || continue
            echo "    ${RACE} (SID=${SID}): $(wc -c < "$RES") 字节"
        done <<< "$SSP_SIDS"
    done
done

# 6. 用 Python 聚合全部历史结果
echo ""
echo "=== 聚合历史数据 ==="
python3 <<'PYEOF'
import json, os, glob

DIR = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(DIR, "raw")

# 加载 2026 赛道信息
d2026 = json.load(open(os.path.join(DIR, "data.json")))
circuits_2026 = set(d2026.get("circuits", {}).keys())

history = {}

# 扫描所有历史结果文件: hist_{YEAR}_{RD}_{SID}.json
for f in sorted(glob.glob(os.path.join(RAW, "hist_*.json"))):
    basename = os.path.basename(f)
    parts = basename.replace(".json", "").split("_")
    # hist_YEAR_RD_SID -> ["hist", YEAR, RD, SID]
    if len(parts) < 4:
        continue
    year = int(parts[1])
    rd_source = "_".join(parts[2:-1]) if len(parts) > 4 else parts[2]
    sid = parts[-1]
    # 从 raw rounds_{YEAR}.json 查询 circuit_id
    rounds_file = os.path.join(RAW, f"rounds_{year}.json")
    if not os.path.exists(rounds_file):
        continue
    rd_data = json.load(open(rounds_file))
    circuit_id = ""
    circ_name = ""
    for r in rd_data.get("data", []):
        a = r.get("attributes", {})
        if a.get("source_id") == parts[2]:
            circuit_rel = r.get("relationships", {}).get("circuit", {}).get("data", {})
            circuit_id = circuit_rel.get("id", "") if circuit_rel else ""
            # 从 included 找赛道名
            for inc in rd_data.get("included", []):
                if inc.get("type") == "circuits" and inc.get("id") == circuit_id:
                    circ_name = inc.get("attributes", {}).get("name", circuit_id)
            break
    
    if not circuit_id or circuit_id not in circuits_2026:
        continue
    
    # 解析结果文件
    try:
        res_data = json.load(open(f))
    except:
        continue
    
    inc_map = {}
    for inc in res_data.get("included", []):
        inc_map[f"{inc.get('type')}:{inc.get('id')}"] = inc
    
    winner = ""
    fl_ms = None
    fl_rider = ""
    
    for entry in res_data.get("data", []):
        at = entry.get("attributes", {})
        pos = at.get("position")
        rider_rel = entry.get("relationships", {}).get("rider", {}).get("data")
        ri = {}
        if rider_rel:
            ri_key = f"{rider_rel['type']}:{rider_rel['id']}"
            ri_data = inc_map.get(ri_key, {})
            ri = ri_data.get("attributes", {})
        rname = f"{ri.get('name','')} {ri.get('surname','')}".strip()
        if pos == 1:
            winner = rname
        fl = at.get("fastest_lap_time")
        if fl and (fl_ms is None or fl < fl_ms):
            fl_ms = fl
            fl_rider = rname
    
    # 确定 race key (RC1/RC2)
    # 从 sessions 文件推断
    sess_file = os.path.join(RAW, f"sessions_{year}_{parts[2]}.json")
    race_key = f"RC{sid}" if len(sid) == 3 else sid
    if os.path.exists(sess_file):
        sess_data = json.load(open(sess_file))
        for s in sess_data.get("data", []):
            if "SSP" in s.get("id","") and s.get("attributes",{}).get("source_id") == sid:
                race_key = s.get("attributes", {}).get("short_name", sid)
    
    if circuit_id not in history:
        history[circuit_id] = {}
    if year not in history[circuit_id]:
        history[circuit_id][year] = []
    
    history[circuit_id][year].append({
        "race": race_key,
        "session_id": sid,
        "winner": winner,
        "fl_ms": fl_ms,
        "fl_rider": fl_rider if fl_rider != winner else "",
    })
    
    print(f"  {circ_name} ({circuit_id}) {year} {race_key}: 冠军={winner or '?'}, FL={fl_ms}")

out_path = os.path.join(DIR, "history_cache.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(history, f, ensure_ascii=False, indent=2)

total = sum(len(entries) for cid in history for year, races in history[cid].items() for entries in [races])
matched = sum(1 for cid in circuits_2026 if cid in history)
print(f"\n✅ 已生成 {out_path}")
print(f"   匹配赛道: {matched}/{len(circuits_2026)}")
print(f"   历史记录: {total} 条")
PYEOF

echo ""
echo "完成。"
