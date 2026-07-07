import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { execSync } from "node:child_process";
import { writeFileSync, unlinkSync, readFileSync, existsSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

const SCRIPT = `${homedir()}/.pi/agent/extensions/bin/tts_gen.py`;
const DEFAULT_VOICE_SAMPLE = "/home/evert/Videos/Own/Projects/2026/Voice_Sample2.wav";
const DEFAULT_MODEL = "tts_models/multilingual/multi-dataset/xtts_v2";

function readSettings(): Record<string, unknown> {
	try {
		const p = join(homedir(), ".pi", "agent", "settings.json");
		if (!existsSync(p)) return {};
		return JSON.parse(readFileSync(p, "utf-8"));
	} catch {
		return {};
	}
}

export default function (pi: ExtensionAPI) {
	pi.registerTool({
		name: "tts-clone",
		label: "TTS Clone",
		description:
			"Speak text aloud using cloned voice (coqui-tts XTTS v2). Uses Voice_Sample2.wav for voice cloning. Saves a wav file for inline display. Streams via Pipewire. Output the path as an HTML <audio controls> tag with no markdown, code fences, backticks, or quotes around the tag so the browser renders it inline.",
		promptSnippet: "Speak text using the cloned Dora voice",
		parameters: Type.Object({
			text: Type.String({
				description: "Text to speak aloud",
			}),
		}),

		async execute(_toolCallId, params, signal) {
			try {
				const cfg = readSettings();
				const voiceSample = (cfg.voice_sample_path as string) ?? DEFAULT_VOICE_SAMPLE;
				const outDir = (cfg.tts_output_dir as string) ?? "/tmp";
				const modelUri = (cfg.tts_clone_model as string) ?? DEFAULT_MODEL;
				const textFile = `/tmp/tts_text_${Date.now()}.txt`;
				writeFileSync(textFile, params.text, "utf-8");

				const result = execSync(
					`/opt/coqui-tts/venv/bin/python3 ${SCRIPT} --model-uri "${modelUri}" --speaker "${voiceSample}" --out-dir "${outDir}" --text-file "${textFile}"`,
					{ encoding: "utf-8", timeout: 180_000, signal, shell: "/bin/bash" },
				);

				unlinkSync(textFile);
				const outPath = result.trim().split("\n").pop() || "";

				return {
					content: [
						{
							type: "text",
							text: `Cloned voice: "${params.text.slice(0, 100)}"\n\n[file: ${outPath}]`,
						},
					],
					details: { model: modelUri, speakerWav: voiceSample, tmpFile: outPath },
				};
			} catch (err) {
				return {
					isError: true,
					content: [
						{
							type: "text",
							text: `TTS clone failed: ${err instanceof Error ? err.message : String(err)}`,
						},
					],
				};
			}
		},
	});
}
