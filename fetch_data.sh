#!/bin/bash
# WSBK 2026 WorldSSP 成绩采集脚本
# 数据源: WorldSBK 官方 pulselive API (api.wsbk.pulselive.com)
# 输出: data.json (含分站、车手、每场比赛成绩)

set -e
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
API="https://api.wsbk.pulselive.com"
DIR="$(cd "$(dirname "$0")" && pwd)"
RAW="$DIR/raw"
mkdir -p "$RAW"

# --retry 4: 网络抖动/超时自动重试，避免单次超时导致整个抓取中止
get() { curl -sS --retry 4 --retry-delay 2 --retry-all-errors -A "$UA" -H "x-client: FE" -H "Referer: https://www.worldsbk.com/" -m 20 "$API$1"; }

echo "=== 1) 拉取分站列表 ==="
get "/wsbk-events/v1/seasons/2026/rounds" > "$RAW/rounds.json"
echo "rounds.json: $(wc -c < "$RAW/rounds.json") 字节"

echo ""
echo "=== 2) 拉取积分榜 (车手 + 厂商) ==="
get "/wsbk-results/v1/seasons/2026/categories/SSP/riders/standings" > "$RAW/standings_riders.json"
get "/wsbk-results/v1/seasons/2026/categories/SSP/manufacturers/standings" > "$RAW/standings_manuf.json" 2>/dev/null || true
echo "standings_riders.json: $(wc -c < "$RAW/standings_riders.json") 字节"

echo ""
echo "=== 3) 拉取各分站 SSP sessions + Race1/Race2 成绩 ==="
# 处理所有非 NOT-STARTED 的分站 (包括 CURRENT / LIVE)
ROUNDS=$(python3 -c "
import json
d=json.load(open('$RAW/rounds.json'))
for r in d['data']:
    a=r['attributes']
    if a.get('status') != 'NOT-STARTED':
        print(a['source_id'])
")

for RD in $ROUNDS; do
    echo "--- 分站 $RD ---"
    get "/wsbk-events/v1/seasons/2026/rounds/$RD/sessions" > "$RAW/sessions_$RD.json"
    # Race1 = source_id 001, Race2 = 002
    for SID in 001 002; do
        OUT="$RAW/result_${RD}_${SID}.json"
        get "/wsbk-results/v1/seasons/2026/categories/SSP/rounds/$RD/sessions/$SID/results" > "$OUT"
        CNT=$(python3 -c "import json; d=json.load(open('$OUT')); print(len(d.get('data',[])))" 2>/dev/null || echo "ERR")
        echo "  Race $SID: $CNT 车手 -> $OUT ($(wc -c < "$OUT") 字节)"
    done
done

echo ""
echo "=== 4) 聚合为 data.json ==="
python3 <<'PYEOF'
import json, os
RAW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "raw")

def load(name):
    with open(os.path.join(RAW, name)) as f:
        return json.load(f)

# API 时间字段解码: 原始值是 "M(M)SSMMM" 格式(分钟+秒+毫秒去掉分隔符), 不是毫秒
# 例: 2922738 -> 29分22.738秒, 137216 -> 1分37.216秒
def decode_time(v):
    if v is None: return None
    try:
        s = str(int(v))
    except (ValueError, TypeError):
        return None
    if len(s) < 4:
        return int(s)  # 短值直接当毫秒
    ms = int(s[-3:])
    secs = int(s[-5:-3])
    mins = int(s[:-5]) if len(s) > 5 else 0
    return mins * 60000 + secs * 1000 + ms


# 分站信息 + 赛道信息
rounds_data = load("rounds.json")["data"]
included_circuits = {}
for inc in load("rounds.json").get("included", []):
    if inc.get("type") == "circuits":
        cid = inc.get("id", "")
        ca = inc.get("attributes", {})
        included_circuits[cid] = {
            "id": cid,
            "name": ca.get("name", ""),
            "description": ca.get("description", ""),
            "locality": ca.get("locality", ""),
            "country": ca.get("country_iso", ""),
            "length_m": ca.get("length", 0),
            "time_zone": ca.get("time_zone", ""),
        }

rounds = {}
for r in rounds_data:
    a = r["attributes"]
    # 提取 circuit id (通过 relationships)
    circuit_rel = r.get("relationships", {}).get("circuit", {}).get("data", {})
    circuit_id = circuit_rel.get("id", "") if circuit_rel else ""
    # 提取分站代码: 从 id 取最后一段 (如 2026-ARA -> ARA)
    rd_id = r["id"].split("-")[-1]
    rounds[rd_id] = {
        "id": a["source_id"],
        "name": a["name"],
        "circuit": a.get("brief_description", a["name"]),
        "country": a.get("country_iso", ""),
        "start_date": a.get("start_date", "")[:10],
        "end_date": a.get("end_date", "")[:10],
        "status": a.get("status"),
        "circuit_id": circuit_id,
        "sequence_order": a.get("sequence_order", 0),
    }

# 按官方 sequence_order 排序分站
round_order = sorted(rounds.keys(), key=lambda k: rounds[k].get("sequence_order", 0))

# 赛道信息映射至 circuit_id
circuits = included_circuits

# 车手主表 (id -> 信息)
riders = {}
teams = {}

# 所有比赛成绩
races = []
for rd in round_order:
    # 找该站 sessions, 确定 race1/race2 的 source_id
    try:
        sess = load(f"sessions_{rd}.json")["data"]
    except (FileNotFoundError, KeyError):
        continue
    ssp_races = {}
    for s in sess:
        if "SSP" not in s["id"]:
            continue
        sa = s["attributes"]
        short = sa.get("short_name", "")
        if short in ("RC1", "RC2"):
            ssp_races[short] = sa["source_id"]

    for race_key in ("RC1", "RC2"):
        sid = ssp_races.get(race_key)
        if not sid:
            continue
        try:
            res = load(f"result_{rd}_{sid}.json")
        except FileNotFoundError:
            continue
        included = {f"{i['type']}:{i['id']}": i for i in res.get("included", [])}

        results = []
        for entry in res.get("data", []):
            at = entry["attributes"]
            # 车手信息
            rider_rel = entry.get("relationships", {}).get("rider", {}).get("data")
            team_rel = entry.get("relationships", {}).get("team", {}).get("data")
            rider_info = {}
            if rider_rel:
                rider_info = (included.get(f"{rider_rel['type']}:{rider_rel['id']}", {})
                              or included.get(f"rider:{rider_rel['id']}", {})
                              or included.get(f"riders:{rider_rel['id']}", {})).get("attributes", {})
            team_info = {}
            if team_rel:
                team_info = (included.get(f"{team_rel['type']}:{team_rel['id']}", {})
                             or included.get(f"team:{team_rel['id']}", {})
                             or included.get(f"teams:{team_rel['id']}", {})).get("attributes", {})

            rider_id = rider_rel["id"] if rider_rel else entry["id"]
            full_name = (rider_info.get("name", "") + " " + rider_info.get("surname", "")).strip()

            # 写入车手主表
            if rider_id not in riders:
                riders[rider_id] = {
                    "id": rider_id,
                    "name": rider_info.get("name", ""),
                    "surname": rider_info.get("surname", ""),
                    "full_name": full_name,
                    "country": rider_info.get("country_iso", ""),
                    "number": at.get("number"),
                }
            else:
                # 更新车号 (保证最新)
                if at.get("number"):
                    riders[rider_id]["number"] = at["number"]

            if team_rel:
                teams[team_rel["id"]] = team_info.get("name", "")

            # 摩托车型号 UUID
            mb_rel = entry.get("relationships", {}).get("motorbike_model", {}).get("data")
            mb_id = mb_rel["id"] if mb_rel else ""

            results.append({
                "pos": at.get("position"),
                "rider_id": rider_id,
                "number": at.get("number"),
                "team": team_info.get("name", ""),
                "motorbike_model_id": mb_id,
                "laps": at.get("laps"),
                "time_ms": decode_time(at.get("time")),
                "status": at.get("status"),
                "top_speed": at.get("speed"),
                "fastest_lap_ms": decode_time(at.get("fastest_lap_time")),
                "fastest_lap_pos": at.get("fastest_lap_position"),
                "fastest_lap_no": at.get("fastest_lap_number"),
            })

        races.append({
            "round": rd,
            "round_name": rounds[rd]["name"],
            "race": race_key,
            "session_id": sid,
            "date": next((s["attributes"].get("circuit_date") for s in sess
                          if "SSP" in s["id"] and s["attributes"].get("short_name") == race_key), ""),
            "results": results,
        })

# 积分榜 (用官方数据)
standings = []
try:
    sd = load("standings_riders.json")
    inc = {f"{i['type']}:{i['id']}": i for i in sd.get("included", [])}
    for row in sd.get("data", []):
        a = row["attributes"]
        rider_rel = row.get("relationships", {}).get("rider", {}).get("data")
        # included 里 rider 类型可能是 'rider' 或 'riders'，兼容两种
        ri = {}
        if rider_rel:
            ri = (inc.get(f"{rider_rel['type']}:{rider_rel['id']}", {})
                  or inc.get(f"rider:{rider_rel['id']}", {})
                  or inc.get(f"riders:{rider_rel['id']}", {})).get("attributes", {})
        rider_id = rider_rel["id"] if rider_rel else None
        full = (ri.get("name","") + " " + ri.get("surname","")).strip()
        standings.append({
            "pos": a.get("position"),
            "rider_id": rider_id,
            "full_name": full,
            "country": ri.get("country_iso", ""),
            "number": a.get("number"),
            "points": a.get("points"),
        })
except Exception as e:
    print(f"积分榜解析警告: {e}")

# ===== 厂商积分榜 (Manufacturer Standings) =====
manufacturer_standings = []
try:
    mdata = load("standings_manuf.json")
    minc = {}
    for inc in mdata.get("included", []):
        minc[inc.get("id")] = inc.get("attributes", {})
    for entry in mdata.get("data", []):
        a = entry.get("attributes", {})
        mfr_rel = entry.get("relationships", {}).get("manufacturer", {}).get("data")
        mfr_name = ""
        mfr_id = ""
        if mfr_rel:
            mfr_id = mfr_rel.get("id", "")
            mfr_name = minc.get(mfr_id, {}).get("name", "")
        # last round info
        last_round_rel = entry.get("relationships", {}).get("last_round", {}).get("data")
        last_round = last_round_rel.get("id", "") if last_round_rel else ""
        manufacturer_standings.append({
            "pos": a.get("position"),
            "manufacturer_id": mfr_id,
            "name": mfr_name,
            "points": a.get("points", 0),
            "last_round": last_round,
        })
    manufacturer_standings.sort(key=lambda x: (x.get("pos") or 99))
except Exception as e:
    print(f"厂商积分榜解析警告: {e}")

# 摩托车型号 UUID -> 型号名称 (API 不含此数据, 从官方站点和赛事资料手动映射)
# 来源: AMCN 2026 WorldSSP 赛季前瞻 + WSBK 官方参赛名单
MOTORBIKE_MODELS = {
    "53d84d89-4caa-5e0b-8510-c3b3d8b45823": "Ducati Panigale V2",
    "320a38a2-468a-57d0-9129-a418e670ff5d": "Yamaha YZF-R9",
    "14f9610e-934e-5360-805c-5100fe218f27": "Triumph Street Triple 765 RS",
    "d74cc533-af9f-527a-93ed-0d450ba94e55": "Kawasaki Ninja ZX-6R",
    "50767e52-483b-5d6f-b326-68eca702f8e3": "Honda CBR600RR",
    "8b8425b7-2406-500e-9c62-7094b2d1876f": "QJ Motor SRK800RS",
    "0f641396-e545-5bac-9e2a-7118220c4ac0": "ZXMOTO 820RR-RS",
    "879e3e99-b3d7-5f3c-8979-e231b6127443": "MV Agusta F3 800 RR",
}

# 为每场比赛结果填入摩托车型号名称
for race in races:
    for res in race["results"]:
        mb_id = res.get("motorbike_model_id", "")
        res["motorcycle"] = MOTORBIKE_MODELS.get(mb_id, "")

# 车手级车队和摩托车型号 (取最近一场比赛的数据)
from collections import OrderedDict
rider_last_team = OrderedDict()  # rider_id -> {team, motorcycle, round, race}
for race in races:
    rk = race_key_func = f"{race['round']}_{race['race']}"
    for res in race["results"]:
        rid = res["rider_id"]
        if res.get("team") or res.get("motorcycle"):
            rider_last_team[rid] = {
                "team": res.get("team", ""),
                "motorcycle": res.get("motorcycle", ""),
            }

# 更新车手主表
for rid, info in riders.items():
    lt = rider_last_team.get(rid, {})
    info["team"] = lt.get("team", "")
    info["motorcycle"] = lt.get("motorcycle", "")

out = {
    "season": 2026,
    "category": "SSP",
    "category_name": "WorldSSP",
    "generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat().replace("+00:00","Z"),
    "rounds": rounds,
    "round_order": round_order,
    "circuits": circuits,
    "riders": riders,
    "teams": sorted(set(teams.values())),
    "races": races,
    "standings": standings,
    "manufacturer_standings": manufacturer_standings,
}

out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)

print(f"\n✅ 已生成 {out_path}")
print(f"   分站数: {len(rounds)}")
print(f"   比赛场次: {len(races)}")
print(f"   车手数: {len(riders)}")
print(f"   积分榜车手数: {len(standings)}")
print(f"   厂商积分榜数: {len(manufacturer_standings)}")
print(f"\n   积分榜 TOP5:")
for s in sorted(standings, key=lambda x: x.get("points",0) or 0, reverse=True)[:5]:
    print(f"   {s['pos']:>2}. #{s['number']:<3} {s['full_name']:<22} {s['country']} | {s['points']} pts")
print(f"\n   厂商积分榜:")
for m in manufacturer_standings:
    print(f"   {m['pos']:>2}. {m['name']:<12} | {m['points']} pts")
PYEOF

echo ""
echo "完成。"