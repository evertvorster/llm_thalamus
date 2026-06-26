/**
 * Tool Approval Extension
 *
 * Intercepts dangerous bash commands (rm -rf, sudo, etc.) and asks the
 * user for confirmation before allowing them to execute.
 *
 * In TUI mode: shows a native terminal dialog via ctx.ui.confirm().
 * In RPC mode (llm-thalamus): emits extension_ui_request → Qt dialog
 * → extension_ui_response back.
 *
 * Place in {PI_CODING_AGENT_DIR}/extensions/ for auto-discovery.
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

export default function (pi: ExtensionAPI) {
	const dangerousPatterns = [
		/\brm\s+(-rf\b|--recursive\b|-r\b|-f\b)/i,
		/\bsudo\b/i,
		/\b(chmod|chown)\b.*777/i,
		/\bdd\b/,
		/\bmkfs\b/,
		/\bmkswap\b/,
		/\b>:+\b/, // redirect to device
		/\bpasswd\b/,
		/\buseradd\b/,
		/\busermod\b/,
		/\bgroupadd\b/,
		/\b:\(\)\s*\{/, // fork bomb
	];

	pi.on("tool_call", async (event, ctx) => {
		if (event.toolName !== "bash") return undefined;

		const command = event.input.command as string;
		const isDangerous = dangerousPatterns.some((p) => p.test(command));

		if (isDangerous) {
			if (!ctx.hasUI) {
				return {
					block: true,
					reason: `Dangerous command blocked (no UI for confirmation): ${command}`,
				};
			}

			const ok = await ctx.ui.confirm(
				"⚠️ Dangerous command",
				`Allow this command?\n\n  ${command}`,
			);

			if (!ok) {
				return { block: true, reason: "Blocked by user" };
			}
		}

		return undefined;
	});
}
