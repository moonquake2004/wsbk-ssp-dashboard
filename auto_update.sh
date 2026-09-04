#!/bin/bash
# auto_update.sh — WSBK SSP 数据自动更新脚本
# 由 launchd 每 30 分钟调用
# 逻辑：运行 fetch_data.sh → 对比 data.json 是否变化 → 有变化则重建 index.html
#
# 用法:
#   ./auto_update.sh          # 正常运行（检查差异）
#   ./auto_update.sh --force  # 强制全量重建（无差异也重建）

set -euo pipefail

BASEDIR="$(cd "$(dirname "$0")" && pwd)"
cd "$BASEDIR"
LOG="$BASEDIR/auto_update.log"

FORCE=false
[ "${1:-}" = "--force" ] && FORCE=true

log(){
  echo "$(date -u '+%Y-%m-%d %H:%M:%S') UTC — $*" | tee -a "$LOG"
}

log "===== 开始检查更新 ====="

# ===== 1) 备份当前 data.json 的哈希（用于对比，排除 generated_at 时间戳） =====
DATA_JSON="$BASEDIR/data.json"
OLD_HASH=""
if [ -f "$DATA_JSON" ]; then
  OLD_HASH=$(python3 -c "
import json, hashlib
d = json.load(open('$DATA_JSON'))
d.pop('generated_at', None)
d.pop('auto_updated_at', None)
print(hashlib.md5(json.dumps(d, sort_keys=True, ensure_ascii=False).encode()).hexdigest())
")
  log "当前 data.json MD5: $OLD_HASH"
fi

# ===== 2) 运行 fetch_data.sh 拉取最新数据 =====
log "运行 fetch_data.sh ..."
bash "$BASEDIR/fetch_data.sh" >> "$LOG" 2>&1

# ===== 3) 对比 data.json 是否有变化（排除时间戳） =====
if [ ! -f "$DATA_JSON" ]; then
  log "❌ data.json 不存在，fetch_data.sh 可能失败"
  exit 1
fi

NEW_HASH=$(python3 -c "
import json, hashlib
d = json.load(open('$DATA_JSON'))
d.pop('generated_at', None)
d.pop('auto_updated_at', None)
print(hashlib.md5(json.dumps(d, sort_keys=True, ensure_ascii=False).encode()).hexdigest())
")
log "新 data.json MD5: $NEW_HASH"

if [ "$OLD_HASH" = "$NEW_HASH" ] && [ "$FORCE" = false ]; then
  log "数据无变化，跳过重建"
  exit 0
fi

if [ "$FORCE" = true ]; then
  log "强制模式：无论数据是否变化都重建"
fi

# ===== 4) 数据有变化，运行 build.py 重建 index.html =====
log "检测到数据变化，运行 build.py 重建 index.html ..."
python3 "$BASEDIR/build.py" >> "$LOG" 2>&1

# ===== 5) 记录更新摘要 =====
ROUNDS=$(python3 -c "import json; d=json.load(open('$DATA_JSON')); print(len(d.get('rounds',{})))")
RACES=$(python3 -c "import json; d=json.load(open('$DATA_JSON')); print(len(d.get('races',[])))")
RIDERS=$(python3 -c "import json; d=json.load(open('$DATA_JSON')); print(len(d.get('riders',{})))")

log "✅ 自动更新完成！${ROUNDS} 分站 / ${RACES} 场比赛 / ${RIDERS} 车手"

# 可选: 发 macOS 通知
if command -v osascript &>/dev/null; then
  osascript -e 'display notification "WSBK SSP 数据已自动更新" with title "WSBK SSP Dashboard" sound name "Submarine"' 2>/dev/null || true
fi
