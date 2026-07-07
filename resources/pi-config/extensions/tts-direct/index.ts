import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { execSync } from "node:child_process";
import { writeFileSync, unlinkSync, readFileSync, existsSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

const SCRIPT = `${homedir()}/.pi/agent/extensions/bin/tts_gen.py`;
const DEFAULT_MODEL = "tts_models/en/ljspeech/tacotron2-DDC";

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
		name: "tts-direct",
		label: "TTS Direct",
		description:
			"Speak text aloud using TTS (coqui-tts Tacotron2-DDC). Streams audio via Pipewire and saves a wav file for inline display. Output the path as an HTML <audio controls> tag with no markdown, code fences, backticks, or quotes around the tag so the browser renders it inline.",
		promptSnippet: "Speak text aloud using TTS",
		parameters: Type.Object({
			text: Type.String({
				description: "Text to speak aloud",
			}),
		}),

		async execute(_toolCallId, params, signal) {
			try {
				const cfg = readSettings();
				const outDir = (cfg.tts_output_dir as string) ?? "/tmp";
				const modelUri = (cfg.tts_direct_model as string) ?? DEFAULT_MODEL;
				const textFile = `/tmp/tts_text_${Date.now()}.txt`;
				writeFileSync(textFile, params.text, "utf-8");

				const result = execSync(
					`/opt/coqui-tts/venv/bin/python3 ${SCRIPT} --model-uri "${modelUri}" --out-dir "${outDir}" --text-file "${textFile}"`,
					{ encoding: "utf-8", timeout: 180_000, signal, shell: "/bin/bash" },
				);

				unlinkSync(textFile);
				const outPath = result.trim().split("\n").pop() || "";

				return {
					content: [
						{
							type: "text",
							text: `Spoken: "${params.text.slice(0, 100)}"\n\n[file: ${outPath}]`,
						},
					],
					details: { model: modelUri, tmpFile: outPath },
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
	});
}
