import torch
from diffusers import StableDiffusionPipeline

model_path = "/home/evert/models/sd15"  # adjust if needed

device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Using device: {device}")

print("Loading pipeline...")
pipe = StableDiffusionPipeline.from_pretrained(
    model_path,
    torch_dtype=torch.float32,   # 👈 float32 even on GPU
    safety_checker=None,
    feature_extractor=None,
)

pipe = pipe.to(device)

print("Generating...")
prompt = "a serene desert landscape at sunset, photorealistic, 8k"

result = pipe(
    prompt,
    num_inference_steps=20,
    guidance_scale=7.5,
)
image = result.images[0]

out_path = "test_sd15_gpu.png"
image.save(out_path)

print("Done! Saved:", out_path)
