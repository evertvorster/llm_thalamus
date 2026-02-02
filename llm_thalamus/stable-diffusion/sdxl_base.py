import torch
from diffusers import StableDiffusionXLPipeline, StableDiffusionXLImg2ImgPipeline

base_path = "/home/evert/models/sdxl-base"
refiner_path = "/home/evert/models/sdxl-refiner"

base = StableDiffusionXLPipeline.from_pretrained(
    base_path,
    torch_dtype=torch.float16,
    safety_checker=None,
).to("cuda")

refiner = StableDiffusionXLImg2ImgPipeline.from_pretrained(
    refiner_path,
    torch_dtype=torch.float16,
    safety_checker=None,
).to("cuda")

base.enable_attention_slicing()
refiner.enable_attention_slicing()

prompt = "a brain scan from the front, bluish white, high contrast, black background"

# Base pass: stop early and hand off latent/image
base_out = base(
    prompt,
    width=1024,
    height=1024,
    num_inference_steps=40,
    guidance_scale=6.5,
    output_type="latent",
)

# Refiner pass: finish details
image = refiner(
    prompt=prompt,
    image=base_out.images,
    num_inference_steps=20,
    guidance_scale=6.5,
).images[0]

image.save("sdxl_base_refiner.png")
print("Saved sdxl_base_refiner.png")
