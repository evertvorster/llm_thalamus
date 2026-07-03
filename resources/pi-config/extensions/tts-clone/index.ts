import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { execSync } from "node:child_process";
import { writeFileSync, unlinkSync } from "node:fs";

import { homedir } from "node:os";

const SCRIPT = `${homedir()}/Software/Projects/llm_thalamus/resources/pi-config/scripts/tts_gen.py`;
const VOICE_SAMPLE = "/home/evert/Videos/Own/Projects/2026/Voice_Sample2.wav";

export default function (pi: ExtensionAPI) {
	pi.registerTool({
		name: "tts-clone",
		label: "TTS Clone",
		description:
			"Speak text aloud using Evert's cloned voice (coqui-tts XTTS v2). Uses Voice_Sample2.wav for voice cloning. Saves a wav file for inline display. Streams via Pipewire.",
		promptSnippet: "Speak text using the cloned Dora voice",
		promptGuidelines: [
			"Use tts-clone when the user wants to hear something in the cloned voice.",
			"The tool accepts text, speaks it aloud, and returns the file path for inline audio display.",
			"First use loads the XTTS v2 model (~6s on GPU). Subsequent calls are faster.",
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
					`/opt/coqui-tts/venv/bin/python3 ${SCRIPT} --model xtts --speaker "${VOICE_SAMPLE}" --text-file "${textFile}"`,
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
					details: { model: "xtts", speakerWav: VOICE_SAMPLE, tmpFile: outPath },
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
