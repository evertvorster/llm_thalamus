#!/opt/coqui-tts/venv/bin/python3
"""Generate TTS audio with sentence-chunked streaming playback.

Args:
  --model tacotron2|xtts     Model shortcut (alias for --model-uri)
  --model-uri URI            Full model URI (overrides --model)
  --text "text"               Text to speak (alias: --text-file /path)
  --text-file /path           Read text from file (safer for special chars)
  --speaker /path/to.wav      Speaker sample (required for xtts / voice cloning)
  --out /path/to.wav          Output file (default: <out-dir>/tts_<ts>.wav)
  --out-dir /path             Output directory (default: /tmp)

Output: prints the WAV file path on completion.
"""
import sys, subprocess, os, time, re, logging, warnings

# Silence upstream pysbd SyntaxWarnings from Python 3.14+ (coqui-tts dep)
warnings.simplefilter("ignore", SyntaxWarning)

import torch

from TTS.api import TTS

logging.getLogger("transformers").setLevel(logging.ERROR)

DEFAULT_TACOTRON = "tts_models/en/ljspeech/tacotron2-DDC"
DEFAULT_XTTS = "tts_models/multilingual/multi-dataset/xtts_v2"
SAMPLE = "/home/evert/Videos/Own/Projects/2026/Voice_Sample2.wav"


def parse_args():
    args = {}
    argv = sys.argv[1:]
    for k in ("--model", "--model-uri", "--text", "--text-file", "--speaker", "--out", "--out-dir"):
        if k in argv:
            i = argv.index(k)
            args[k] = argv[i + 1]
    if "--text-file" in args:
        with open(args["--text-file"], "r") as f:
            args["--text"] = f.read()
    return args


def sentences(text):
    parts = re.split(r"(?<=[.!?,])\s+", text)
    return [p.strip() for p in parts if p.strip()]


def main():
    a = parse_args()
    text = a.get("--text", "")
    speaker = a.get("--speaker", "")
    out_dir = a.get("--out-dir", "/tmp")
    out_path = a.get("--out")

    if not out_path:
        out_path = f"{out_dir.rstrip('/')}/tts_{int(time.time()*1000)}.wav"
    if not text:
        print("No text", file=sys.stderr)
        sys.exit(1)

    # Resolve model URI: --model-uri wins, then --model shortcut, then default
    model_uri = a.get("--model-uri", "")
    if not model_uri:
        shortcut = a.get("--model", "tacotron2")
        model_uri = DEFAULT_XTTS if shortcut == "xtts" else DEFAULT_TACOTRON

    # If speaker not set and model looks like xtts, use default sample
    if not speaker and "xtts" in model_uri:
        speaker = SAMPLE

    # Load model
    tts = TTS(model_uri)
    if torch.cuda.is_available():
        tts.to("cuda")

    chunks = sentences(text)
    chunk_files = []
    play_proc = None

    for s in chunks:
        cf = f"/tmp/tts_c_{int(time.time()*1000)}_{len(chunk_files)}.wav"

        if speaker:
            tts.tts_to_file(text=s, speaker_wav=speaker, language="en", file_path=cf)
        else:
            tts.tts_to_file(text=s, file_path=cf)

        # Wait for previous chunk playback to finish
        if play_proc:
            play_proc.wait()

        # Start playing this chunk
        play_proc = subprocess.Popen(["pw-play", cf], stderr=subprocess.DEVNULL)
        chunk_files.append(cf)

    if play_proc:
        play_proc.wait()

    # Concatenate all chunks using sox (handles WAV headers correctly)
    subprocess.run(["sox"] + chunk_files + [out_path], check=True, capture_output=True)
    for cf in chunk_files:
        os.unlink(cf)

    print(out_path)


if __name__ == "__main__":
    main()
