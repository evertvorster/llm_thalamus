import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

const LLAMA_API = "http://localhost:8080/v1/chat/completions";
const EVICT_MODEL = "bartowski/Llama-3.2-3B-Instruct-GGUF:Q4_K_M";
const SDXL_SCRIPT =
	"/home/evert/Software/Projects/llm_thalamus_documentation/llm_thalamus_V02_backup/stable-diffusion/sdxl_gen.py";
const SD15_SCRIPT =
	"/home/evert/Software/Projects/llm_thalamus_documentation/llm_thalamus_V02_backup/stable-diffusion/sd15_gen.py";

/** Evict any loaded LLM from VRAM by loading a tiny model, freeing VRAM for SDXL */
async function evictLlm(signal?: AbortSignal): Promise<void> {
	const body = JSON.stringify({
		model: EVICT_MODEL,
		messages: [{ role: "user", content: "hi" }],
		max_tokens: 1,
		temperature: 0.1,
	});

	const resp = await fetch(LLAMA_API, {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body,
		signal,
	});

	if (!resp.ok) {
		const text = await resp.text().catch(() => "");
		console.warn(`[image-gen] evict request returned ${resp.status}: ${text.slice(0, 200)}`);
	}

	// Wait a moment for the new model to settle
	await new Promise((resolve) => setTimeout(resolve, 500));
}

async function execCommand(command: string, signal?: AbortSignal): Promise<string> {
	const { execSync } = await import("node:child_process");
	const result = execSync(command, {
		encoding: "utf-8",
		timeout: 300_000,
		maxBuffer: 10 * 1024 * 1024,
		signal,
		shell: "/bin/bash",
	});
	return result.trim();
}

export default function (pi: ExtensionAPI) {
	pi.registerTool({
		name: "generate_image",
		label: "Generate Image",
		description:
			"Generate an image from a text description using SDXL or SD 1.5. Returns the path to the generated image file.",
		promptSnippet: "Generate images from text descriptions using SDXL or SD 1.5",
		promptGuidelines: [
			"Use generate_image when the user asks to create, generate, or render an image from a text description.",
			"The tool accepts a description string and returns the file path of the generated image.",
		],
		parameters: Type.Object({
			description: Type.String({
				description: "Description of the image to generate",
			}),
			model: Type.Optional(
				Type.Union(
					[Type.Literal("sdxl"), Type.Literal("sd15")],
					{ description: "Model to use: sdxl (high quality) or sd15 (fast, default: sdxl)" },
				),
			),
		}),

		async execute(_toolCallId, params, signal) {
			const script = params.model === "sd15" ? SD15_SCRIPT : SDXL_SCRIPT;
			// Script joins all args with space, so unquoted description works fine
			const command = `python3 ${script} ${params.description}`;

			// Step 1: Evict any loaded LLM to free VRAM
			await evictLlm(signal);

			// Step 2: Run SDXL
			try {
				const output = await execCommand(command, signal);
				const lines = output.split("\n").filter(Boolean);
				const imageLine = lines.find((l) => l.includes(".png")) ?? lines[lines.length - 1] ?? output;
				return {
					content: [{ type: "text", text: `Generated image: ${imageLine}` }],
					details: { imagePath: imageLine, model: params.model ?? "sdxl" },
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
	});
}
