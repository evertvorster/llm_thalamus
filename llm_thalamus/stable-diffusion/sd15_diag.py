import torch
import numpy as np
from diffusers import StableDiffusionPipeline

model_path = "/home/evert/models/sd15"  # adjust if needed

device = "cpu"   # force CPU for a clean, fp32 run
print(f"Using device: {device}")

print("Loading pipeline...")
pipe = StableDiffusionPipeline.from_pretrained(
    model_path,
    torch_dtype=torch.float32,
    safety_checker=None,
    feature_extractor=None,
)

pipe = pipe.to(device)

print("Generating...")
prompt = "a serene desert landscape at sunset, photorealistic, 8k"

result = pipe(
    prompt,
    num_inference_steps=10,    # fewer steps, faster diagnostic
    guidance_scale=7.5,
)

image = result.images[0]

# Inspect raw pixel statistics
arr = np.array(image)
print("Image shape:", arr.shape)
print("Pixel min:", arr.min(), "max:", arr.max(), "mean:", arr.mean())

out_path = "test_sd15_diag.png"
image.save(out_path)
print("Done! Saved:", out_path)
