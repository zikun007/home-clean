#!/usr/bin/env bash
# ==============================================================================
# lark-bot 调度器：监听飞书消息 → pi 执行 → 进度实时上报 → 结果回发
#
# 参数化设计：
#   本脚本可入库（不含隐私），个人配置从本地 config.sh 读取：
#   ~/.pi/lark-bot/config.sh   （含 open_id 等，不入库）
#   config.example.sh          （模板，入库）
#
# 功能：
#   1. P2P 单聊接收任务，仅响应主人消息
#   2. pi --mode json 执行，实时解析事件流：
#      - tool_execution_start → 上报「正在执行：工具名 + 参数摘要」
#   3. 长回复自动分片发送（不再粗暴截断）
#   4. status 指令：查询当前任务执行状态
#   5. 串行队列：任务依次执行，执行中收到新任务先回执排队
# ==============================================================================
set -u

BOT_DIR="$HOME/.pi/lark-bot"
LOG_FILE="$BOT_DIR/bot.log"
EVENTS_FILE="$BOT_DIR/events.ndjson"      # 原始事件留档（追加）
STATE_FILE="$BOT_DIR/state.json"          # 当前任务状态（status 指令用）
QUEUE_FILE="$BOT_DIR/queue.txt"           # 待执行任务队列
PI_WORKDIR="$HOME/workspace"

# ---- 加载本地个人配置（不入库）----
# shellcheck source=/dev/null
[ -f "$BOT_DIR/config.sh" ] || { echo "缺少 $BOT_DIR/config.sh，请参考 config.example.sh 创建" >&2; exit 1; }
source "$BOT_DIR/config.sh"

# ---- 飞书流量不走代理（代理会 403）----
export no_proxy="localhost,127.0.0.1,10.0.0.0/8,172.16.0.0/12,${NO_PROXY_EXTRA:-feishu.cn,larksuite.com,feishucdn.com}"
export NO_PROXY="$no_proxy"

# 飞书文本消息单条上限（字节），超长自动分片
MSG_MAX_LEN=3500

log() { echo "[$(date '+%F %T')] $*" >> "$LOG_FILE"; }

# ---- 状态文件维护（status 指令用）----
set_state() {  # $1=状态文本
    printf '{"time":"%s","state":"%s"}' "$(date '+%F %T')" "$1" > "$STATE_FILE"
}

# ---- 群里发消息 ----
send_msg() {
    local text="$1"
    # 超长分片：按字节切，避免飞书拒收
    local total chunk_start chunk
    total=$(printf '%s' "$text" | wc -c)
    if [ "$total" -le "$MSG_MAX_LEN" ]; then
        lark-cli im +messages-send --as bot "${SEND_TARGET[@]}" --text "$text" >> "$LOG_FILE" 2>&1
        return
    fi
    local idx=1
    chunk_start=0
    while [ "$chunk_start" -lt "$total" ]; do
        chunk=$(printf '%s' "$text" | dd bs=1 skip="$chunk_start" count="$MSG_MAX_LEN" 2>/dev/null)
        lark-cli im +messages-send --as bot "${SEND_TARGET[@]}" --text "📄 [$idx] $chunk" >> "$LOG_FILE" 2>&1
        chunk_start=$((chunk_start + MSG_MAX_LEN))
        idx=$((idx + 1))
    done
}

# ---- 处理单条任务：pi --mode json 执行 + 实时进度上报 ----
handle_task() {
    local task="$1"

    set_state "执行中：${task:0:80}"
    send_msg "🤖 收到，开始处理：${task:0:100}"

    local result_file
    result_file="$(mktemp "$BOT_DIR/task_result.XXXXXX")"

    # pi 以 json 模式运行；实时进度由扩展 lark-progress.ts 负责（环境变量激活），
    # 调度器只留档事件流 + 提取最终文本
    (cd "$PI_WORKDIR" && LARK_BOT_PROGRESS=1 LARK_BOT_OWNER="$OWNER_ID" pi --mode json "$task" < /dev/null) 2>>"$LOG_FILE" > "$result_file"

    # 从事件留档中提取最终 assistant 文本
    local final_text
    final_text="$(jq -r 'select(.type == "message_end" and .message.role == "assistant") |
        [.message.content[]? | select(.type == "text") | .text] | join("")' \
        "$result_file" 2>/dev/null | tail -1)"
    # 兜底：若 json 提取为空（如 pi 异常退出），回退输出原始留档最后几行
    if [ -z "$final_text" ]; then
        final_text="[pi 未返回最终文本，原始事件留档：$(basename "$result_file")]"
        log "pi 任务无最终文本: $task"
    else
        log "pi 任务完成: $task"
    fi

    send_msg "✅ 完成：

$final_text"
    rm -f "$result_file"
    set_state "空闲"
}

# ---- 处理入队消息（主循环调用）----
process_incoming() {
    local content="$content_from_event"

    # status 指令：查状态
    if [[ "$content" == "status" || "$content" == "状态" ]]; then
        local st
        st="$(cat "$STATE_FILE" 2>/dev/null || echo '未知')"
        local queued
        queued=$(grep -c . "$QUEUE_FILE" 2>/dev/null || echo 0)
        send_msg "📊 当前状态：$st
待处理任务数：${queued}"
        return
    fi

    # 有任务在执行中 → 入队回执
    if grep -q '"state":"执行中' "$STATE_FILE" 2>/dev/null; then
        echo "$content" >> "$QUEUE_FILE"
        local pos
        pos=$(grep -c . "$QUEUE_FILE")
        send_msg "📥 当前有任务在执行，你的任务已排队（第 $pos 位）"
        return
    fi

    # 空闲 → 立即执行
    handle_task "$content"

    # 执行完，检查队列
    while IFS= read -r next_task < <(head -1 "$QUEUE_FILE" 2>/dev/null); do
        sed -i '1d' "$QUEUE_FILE" 2>/dev/null
        [ -z "$next_task" ] && break
        send_msg "📤 开始处理排队任务"
        handle_task "$next_task"
    done
}

# ==========================================
# 主循环：事件监听
# ==========================================
main() {
    log "==== lark-bot 调度器启动 (pid $$) ===="
    set_state "空闲"
    : > "$QUEUE_FILE" 2>/dev/null || true

    # stdin 用 tail -f 保持打开，防止 unbounded 模式因 EOF 退出
    tail -f /dev/null | lark-cli event consume im.message.receive_v1 --as bot \
        | while IFS= read -r line; do
            [ -z "$line" ] && continue
            echo "$line" >> "$EVENTS_FILE"

            local chat_type sender_id msg_type
            chat_type="$(echo "$line" | jq -r '.chat_type // empty')"
            sender_id="$(echo "$line" | jq -r '.sender_id // empty')"
            msg_type="$(echo "$line" | jq -r '.message_type // empty')"

            # 只处理 P2P 单聊、文本消息、主人消息
            [ "$chat_type" != "p2p" ] && continue
            [ "$msg_type" != "text" ] && { log "忽略非文本消息: $msg_type"; continue; }
            [ "$sender_id" != "$OWNER_ID" ] && { log "忽略非主人消息: $sender_id"; continue; }

            content_from_event="$(echo "$line" | jq -r '.content // empty')"
            log "收到消息: ${content_from_event:0:100}"

            process_incoming
        done

    log "事件管道退出，5 秒后重启监听..."
    sleep 5
    exec "$0"
}

main "$@"
