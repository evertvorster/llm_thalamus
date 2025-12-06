import sys
import torch
from diffusers import StableDiffusionPipeline

model_path = "/home/evert/models/sd15"

prompt = sys.stdin.read().strip()
print("Using prompt:\n", prompt)

pipe = StableDiffusionPipeline.from_pretrained(
    model_path,
    torch_dtype=torch.float32,  # safer for GPU
    safety_checker=None,
    feature_extractor=None,
).to("cuda")

image = pipe(prompt, num_inference_steps=25).images[0]
image.save("sd15_from_stdin.png")

print("Saved: sd15_from_stdin.png")
