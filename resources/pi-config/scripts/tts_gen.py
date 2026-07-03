#!/opt/coqui-tts/venv/bin/python3
"""Generate TTS audio with sentence-chunked streaming playback.

Args:
  --model tacotron2|xtts     Model to use
  --text "text"               Text to speak (alias: --text-file /path)
  --text-file /path           Read text from file (safer for special chars)
  --speaker /path/to.wav      Speaker sample (required for xtts)
  --out /path/to.wav          Output file (default: /tmp/tts_out_<ts>.wav)

Output: prints the WAV file path on completion.
"""
import sys, subprocess, os, time, re
import torch
from TTS.api import TTS

M = "tts_models/en/ljspeech/tacotron2-DDC"
X = "tts_models/multilingual/multi-dataset/xtts_v2"
SAMPLE = "/home/evert/Videos/Own/Projects/2026/Voice_Sample2.wav"


def parse_args():
    args = {}
    argv = sys.argv[1:]
    for k in ("--model", "--text", "--text-file", "--speaker", "--out"):
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
    model_name = a.get("--model", "tacotron2")
    text = a.get("--text", "")
    speaker = a.get("--speaker", SAMPLE if model_name == "xtts" else None)
    out_path = a.get("--out")
    if not out_path:
        out_path = f"/tmp/tts_{int(time.time()*1000)}.wav"
    if not text:
        print("No text", file=sys.stderr)
        sys.exit(1)

    # Load model
    mid = X if model_name == "xtts" else M
    tts = TTS(mid)
    if torch.cuda.is_available():
        tts.to("cuda")

    chunks = sentences(text)
    chunk_files = []
    play_proc = None

    for s in chunks:
        cf = f"/tmp/tts_c_{int(time.time()*1000)}_{len(chunk_files)}.wav"

        if model_name == "xtts":
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

    # Concatenate all chunks (skip WAV header on subsequent)
    with open(out_path, "wb") as out:
        for i, cf in enumerate(chunk_files):
            with open(cf, "rb") as inp:
                if i == 0:
                    out.write(inp.read())
                else:
                    inp.read(44)
                    out.write(inp.read())
            os.unlink(cf)

    print(out_path)


if __name__ == "__main__":
    main()
