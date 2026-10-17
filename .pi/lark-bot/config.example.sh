# lark-bot 本地配置模板
# 复制为 ~/.pi/lark-bot/config.sh 并填入真实值（config.sh 含个人 ID，不入库）

# 主人 open_id：只响应这个人发的消息
OWNER_ID="ou_xxxxxxxxxxxxxxxx"

# 发送目标：
#   P2P 单聊（推荐）：
SEND_TARGET=("--user-id" "ou_xxxxxxxxxxxxxxxx")
#   群聊（二选一）：
#   SEND_TARGET=("--chat-id" "oc_xxxxxxxxxxxxxxxx")

# no_proxy 追加域名（飞书不走代理），一般无需改动
# NO_PROXY_EXTRA="feishu.cn,larksuite.com,feishucdn.com"
