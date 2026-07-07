import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { execSync } from "node:child_process";
import { writeFileSync, unlinkSync, readFileSync, existsSync } from "node:fs";
import { homedir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

// ── Paths ─────────────────────────────────────────────────────────

const __dirname = dirname(fileURLToPath(import.meta.url));
const BIN = join(__dirname, "bin");

// ── Config reader ─────────────────────────────────────────────────

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

// ── Helper ─────────────────────────────────────────────────────────

function runTts(
	modelUri: string,
	text: string,
	outDir: string,
	speaker: string | undefined,
	signal?: AbortSignal,
): string {
	const textFile = `/tmp/tts_text_${Date.now()}.txt`;
	writeFileSync(textFile, text, "utf-8");

	const args = [
		`/opt/coqui-tts/venv/bin/python3`,
		join(BIN, "tts_gen.py"),
		`--model-uri "${modelUri}"`,
		`--out-dir "${outDir}"`,
		`--text-file "${textFile}"`,
	];
	if (speaker) args.push(`--speaker "${speaker}"`);

	const result = execSync(args.join(" "), {
		encoding: "utf-8",
		timeout: 180_000,
		signal,
		shell: "/bin/bash",
	});

	unlinkSync(textFile);
	return result.trim().split("\n").pop() || "";
}

// ── Tool builders ──────────────────────────────────────────────────

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

function buildTtsTool(
	name: "tts-direct" | "tts-clone",
	label: string,
	description: string,
	promptSnippet: string,
	getArgs: (settings: Config) => { modelUri: string; outDir: string; speaker?: string },
) {
	return {
		name,
		label,
		description,
		promptSnippet,
		parameters: Type.Object({
			text: Type.String({
				description: "Text to speak aloud",
			}),
		}),

		async execute(_toolCallId: string, params: { text: string }, signal?: AbortSignal) {
			try {
				const cfg = readSettings();
				const { modelUri, outDir, speaker } = getArgs(cfg);
				const outPath = runTts(modelUri, params.text, outDir, speaker, signal);
				const labelText = name === "tts-clone" ? "Cloned voice" : "Spoken";
				return {
					content: [
						{
							type: "text",
							text: `${labelText}: "${params.text.slice(0, 100)}"\n\n[file: ${outPath}]`,
						},
					],
					details: { model: modelUri, tmpFile: outPath, speakerWav: speaker },
				};
			} catch (err) {
				return {
					isError: true,
					content: [
						{
							type: "text",
							text: `TTS failed: ${err instanceof Error ? err.message : String(err)}`,
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
		join(BIN, "sdxl_gen.py"),
		"/home/evert/models/sdxl-base",
		"sdxl_model_path",
		"1024x1024",
	));

	pi.registerTool(buildImageTool(
		"gen_image_sd15",
		"SD 1.5",
		"Generate images quickly using SD 1.5 (512x512)",
		join(BIN, "sd15_gen.py"),
		"/home/evert/models/sd15",
		"sd15_model_path",
		"512x512",
	));

	pi.registerTool(buildTtsTool(
		"tts-direct",
		"TTS Direct",
		"Speak text aloud using TTS (coqui-tts Tacotron2-DDC). Streams audio via Pipewire and saves a wav file for inline display. Output the path as an HTML <audio controls> tag with no markdown, code fences, backticks, or quotes around the tag so the browser renders it inline.",
		"Speak text aloud using TTS",
		(settings) => ({
			modelUri: (settings.tts_direct_model as string) ?? "tts_models/en/ljspeech/tacotron2-DDC",
			outDir: (settings.tts_output_dir as string) ?? "/tmp",
		}),
	));

	pi.registerTool(buildTtsTool(
		"tts-clone",
		"TTS Clone",
		"Speak text aloud using cloned voice (coqui-tts XTTS v2). Uses Voice_Sample2.wav for voice cloning. Saves a wav file for inline display. Streams via Pipewire. Output the path as an HTML <audio controls> tag with no markdown, code fences, backticks, or quotes around the tag so the browser renders it inline.",
		"Speak text using the cloned Dora voice",
		(settings) => ({
			modelUri: (settings.tts_clone_model as string) ?? "tts_models/multilingual/multi-dataset/xtts_v2",
			outDir: (settings.tts_output_dir as string) ?? "/tmp",
			speaker: (settings.voice_sample_path as string) ?? "/home/evert/Videos/Own/Projects/2026/Voice_Sample2.wav",
		}),
	));
}
