"""SD 1.5 image generator.
Usage: python3 sd15_gen.py [--model-path PATH] [--out-dir DIR] <prompt>
"""
import argparse
import sys
from datetime import datetime

import torch
from tokenizers import processors

_orig_rp = processors.RobertaProcessing
def _rp_new(*args, **kwargs):
    if 'cls' in kwargs and 'cls_token' not in kwargs:
        kwargs['cls_token'] = kwargs.pop('cls')
    return _orig_rp(*args, **kwargs)
processors.RobertaProcessing = _rp_new
import tokenizers  # noqa: E402
tokenizers.processors.RobertaProcessing = _rp_new

from diffusers import StableDiffusionPipeline  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SD 1.5 image generator")
    parser.add_argument("--model-path", default="/home/evert/models/sd15",
                        help="Path to SD 1.5 model directory")
    parser.add_argument("--out-dir", default="/home/evert/Pictures/Stable Diffusion",
                        help="Output directory for generated images")
    parser.add_argument("prompt", nargs="*", help="Text prompt")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    prompt = " ".join(args.prompt) if args.prompt else sys.stdin.read().strip()
    if not prompt:
        print("Usage: python3 sd15_gen.py [--model-path PATH] [--out-dir DIR] <prompt>", file=sys.stderr)
        sys.exit(1)

    pipe = StableDiffusionPipeline.from_pretrained(
        args.model_path,
        torch_dtype=torch.float16,
        safety_checker=None,
        feature_extractor=None,
    ).to("cuda")

    result = pipe(
        prompt=prompt,
        height=512,
        width=512,
        num_inference_steps=20,
        guidance_scale=7.0,
    )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = f"{args.out_dir.rstrip('/')}/sd15_{stamp}.png"
    result.images[0].save(out_path)
    print(out_path)


if __name__ == "__main__":
    main()
