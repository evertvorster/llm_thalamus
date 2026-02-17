import torch
from diffusers import StableDiffusionXLPipeline

model_path = "/home/evert/models/sdxl-base"

device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Using device: {device}")

print("Loading SDXL base...")
pipe = StableDiffusionXLPipeline.from_pretrained(
    model_path,
    torch_dtype=torch.float32,
)
pipe = pipe.to(device)

prompt = "a detailed painting of a spaceship flying over a desert at sunset, ultra detailed, sdxl style"

print("Generating...")
result = pipe(
    prompt=prompt,
    num_inference_steps=20,
    guidance_scale=7.0,
)

image = result.images[0]
image.save("test_sdxl_base.png")

print("Done! Saved: test_sdxl_base.png")
