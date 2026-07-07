import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { execSync } from "node:child_process";
import { readFileSync, existsSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

// ── Config reader ────────────────────────────────────────────────

const SDXL_SCRIPT = `${homedir()}/.pi/agent/extensions/bin/sdxl_gen.py`;
const SD15_SCRIPT = `${homedir()}/.pi/agent/extensions/bin/sd15_gen.py`;

interface Config {
	[key: string]: string | boolean | number | object | undefined;
}

function readSettings(): Config {
	try {
		const p = join(homedir(), ".pi", "agent", "settings.json");
		if (!existsSync(p)) return {};
		return JSON.parse(readFileSync(p, "utf-8"));
	} catch {
		return {};
	}
}

// ── VRAM eviction ─────────────────────────────────────────────────

function evictLlm(): void {
	const out = execSync(
		`ps aux | awk '/[l]lama-server.*--port/ && !/--port 8080/ {print $2}'`,
		{ encoding: "utf-8", timeout: 5000, shell: "/bin/bash" },
	).trim();

	for (const pid of out.split("\n").filter(Boolean)) {
		try {
			process.kill(parseInt(pid), "SIGKILL");
		} catch {
			/* already gone */
		}
	}
}

async function execCommand(command: string, signal?: AbortSignal): Promise<string> {
	const { execSync: exec } = await import("node:child_process");
	const result = exec(command, {
		encoding: "utf-8",
		timeout: 300_000,
		maxBuffer: 10 * 1024 * 1024,
		signal,
		shell: "/bin/bash",
	});
	return result.trim();
}

// ── Tool factory ──────────────────────────────────────────────────

function buildImageTool(
	name: "gen_image_sdxl" | "gen_image_sd15",
	label: string,
	promptSnippet: string,
	script: string,
	modelDefault: string,
	modelConfigKey: string,
	defaultSize: string,
) {
	return {
		name,
		label,
		description: `Generate an image from a text description using ${label}. Returns the path to the generated image file. Output the path as an HTML <img> tag with no markdown, code fences, backticks, or quotes around the tag so the browser renders it inline.`,
		promptSnippet,
		parameters: Type.Object({
			description: Type.String({
				description: "Description of the image to generate",
			}),
		}),

		async execute(_toolCallId: string, params: { description: string }, signal?: AbortSignal) {
			const cfg = readSettings();
			const modelPath = (cfg[modelConfigKey] as string | undefined) ?? modelDefault;
			const outDir = (cfg.image_output_dir as string | undefined) ?? "/home/evert/Pictures/Stable Diffusion";
			const command = `python3 ${script} --model-path "${modelPath}" --out-dir "${outDir}" ${params.description}`;

			evictLlm();

			try {
				const output = await execCommand(command, signal);
				const lines = output.split("\n").filter(Boolean);
				const imageLine = lines.find((l) => l.includes(".png")) ?? lines[lines.length - 1] ?? output;
				return {
					content: [{ type: "text", text: `[file: ${imageLine}]` }],
					details: { imagePath: imageLine, model: label, size: defaultSize },
				};
			} catch (err) {
				return {
					isError: true,
					content: [
						{
							type: "text",
							text: `Image generation failed: ${err instanceof Error ? err.message : String(err)}`,
						},
					],
				};
			}
		},
	};
}

// ── Registration ──────────────────────────────────────────────────

export default function (pi: ExtensionAPI) {
	pi.registerTool(buildImageTool(
		"gen_image_sdxl",
		"SDXL",
		"Generate high-quality images using SDXL (1024x1024)",
		SDXL_SCRIPT,
		"/home/evert/models/sdxl-base",
		"sdxl_model_path",
		"1024x1024",
	));

	pi.registerTool(buildImageTool(
		"gen_image_sd15",
		"SD 1.5",
		"Generate images quickly using SD 1.5 (512x512)",
		SD15_SCRIPT,
		"/home/evert/models/sd15",
		"sd15_model_path",
		"512x512",
	));
}
