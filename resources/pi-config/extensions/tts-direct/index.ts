import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { execSync } from "node:child_process";
import { writeFileSync, unlinkSync } from "node:fs";

import { homedir } from "node:os";

const SCRIPT = `${homedir()}/Software/Projects/llm_thalamus/resources/pi-config/scripts/tts_gen.py`;

export default function (pi: ExtensionAPI) {
	pi.registerTool({
		name: "tts-direct",
		label: "TTS Direct",
		description:
			"Speak text aloud using TTS (coqui-tts Tacotron2-DDC). Streams audio via Pipewire and saves a wav file for inline display.",
		promptSnippet: "Speak text aloud using TTS",
		promptGuidelines: [
			"Use tts-direct when the user wants to hear something spoken aloud.",
			"The tool accepts text to speak, generates it, plays through speakers, and returns the file path.",
		],
		parameters: Type.Object({
			text: Type.String({
				description: "Text to speak aloud",
			}),
		}),

		async execute(_toolCallId, params, signal) {
			try {
				const textFile = `/tmp/tts_text_${Date.now()}.txt`;
				writeFileSync(textFile, params.text, "utf-8");

				const result = execSync(
					`/opt/coqui-tts/venv/bin/python3 ${SCRIPT} --model tacotron2 --text-file "${textFile}"`,
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
					details: { model: "tacotron2", tmpFile: outPath },
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
