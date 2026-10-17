/**
 * lark-bot 进度上报扩展
 *
 * 让 pi 在执行任务过程中，通过 lark-cli 把进度实时发到飞书。
 * 适用于无头模式（pi --print / lark-bot 调度器），让用户在飞书里看到：
 *   - 每个工具调用的开始（跑了什么命令 / 编辑了什么文件）
 *   - 任务最终完成（agent_settled）
 *
 * 激活方式：设置环境变量 LARK_BOT_PROGRESS=1 时才启用，
 *           不影响正常交互式使用 pi。
 * 目标人：环境变量 LARK_BOT_OWNER（open_id），缺省则跳过。
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { execFile } from "child_process";

const OWNER = process.env.LARK_BOT_OWNER ?? "";
// 飞书流量不走代理（代理会 403）；合并用户已有 no_proxy，追加飞书域名
const USER_NO_PROXY = process.env.no_proxy ?? "";
const LARK_NO_PROXY =
	USER_NO_PROXY && !USER_NO_PROXY.includes("feishu.cn")
		? `${USER_NO_PROXY},feishu.cn,larksuite.com,feishucdn.com`
		: USER_NO_PROXY || "localhost,127.0.0.1,10.0.0.0/8,172.16.0.0/12,feishu.cn,larksuite.com,feishucdn.com";

function sendToLark(text: string): void {
	if (!OWNER) return;
	// 截断防止超长
	const clipped = text.length > 3000 ? text.slice(0, 3000) + "\n…[已截断]" : text;
	execFile(
		"lark-cli",
		["im", "+messages-send", "--as", "bot", "--user-id", OWNER, "--text", clipped],
		{
				env: { ...process.env, no_proxy: LARK_NO_PROXY, NO_PROXY: LARK_NO_PROXY },
			timeout: 30_000,
		},
		(err) => {
			if (err) console.error(`[lark-bot] 发送失败: ${err.message}`);
		},
	);
}

/** 把工具调用参数摘要成一行人类可读文本 */
function summarize(toolName: string, args: Record<string, unknown>): string {
	try {
		switch (toolName) {
			case "bash":
				return String(args.command ?? "").split("\n")[0].slice(0, 150);
			case "read":
				return `读取 ${args.path}${args.offset ? ` (从第${args.offset}行)` : ""}`;
			case "edit":
				return `编辑 ${args.path}`;
			case "write":
				return `写入 ${args.path}`;
			case "codemode":
				return "执行 codemode 脚本";
			case "subagent":
				return `派发子任务给 ${args.agent}`;
			default:
				return JSON.stringify(args).slice(0, 120);
		}
	} catch {
		return "";
	}
}

export default function (pi: ExtensionAPI) {
	// 未设置环境变量时完全静默，不影响正常使用
	if (!OWNER || process.env.LARK_BOT_PROGRESS !== "1") return;

	pi.on("session_start", async () => {
		sendToLark("🚀 任务会话已建立，开始执行");
	});

	// 每个工具调用开始时上报（只报外层调用，嵌套调用 parentToolCallId 非空则跳过）
	pi.on("tool_execution_start", async (event: any) => {
		if (event.parentToolCallId) return;
		const line = summarize(event.toolName ?? "tool", event.args ?? {});
		if (line) sendToLark(`🔧 ${line}`);
	});

	// 工具执行报错时上报
	pi.on("tool_execution_end", async (event: any) => {
		if (event.parentToolCallId) return;
		if (event.isError) {
			sendToLark(`⚠️ 工具 ${event.toolName} 执行失败`);
		}
	});

	// 一次完整运行结束（含重试/恢复后）
	pi.on("agent_settled", async () => {
		sendToLark("🏁 本次运行结束，最终答复即将送达");
	});
}
