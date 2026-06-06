---
name: minimax-multimodal
description: MiniMax multimodal REST endpoints (video, image, TTS, music, voice cloning). TRIGGER when task asks to generate video, image, speech, music, or clone a voice. SKIP for text/code/analysis-only tasks.
---

# MiniMax Multimodal API Reference

**Model:** any (read-only reference — no judgment required).

MiniMax's multimodal products are all plain REST endpoints with Bearer auth. You do **not** need a special SDK, the `minimax-cli` npm package, or the foundry-delegate tooling to use them — any agent that can `curl` or `requests.post` can reach them.

## Endpoints

| Capability | Endpoint | Sync/Async |
|---|---|---|
| Text-to-Video | `POST https://api.minimax.io/v1/video_generation` | Async |
| Image-to-Video | `POST https://api.minimax.io/v1/video_generation` (with `first_frame_image`) | Async |
| Text-to-Image | `POST https://api.minimax.io/v1/image_generation` | Sync |
| Text-to-Speech (async) | `POST https://api.minimax.io/v1/t2a_v2` | Async |
| Music Generation | `POST https://api.minimax.io/v1/music_generation` | Async |
| Voice Cloning | `POST https://api.minimax.io/v1/voice_clone` | Sync |

Base URL is `https://api.minimax.io` (international) or `https://api.minimaxi.com` (China). Pick one and stick with it — keys are region-specific.

## Auth

Same MiniMax API key as the text endpoint (including Coding Plan `sk-cp-…` keys):

```
Authorization: Bearer $MINIMAX_API_KEY
Content-Type: application/json
```

Already in your env if you've set up the delegate skill's `.env` (at `<repo>/.env` or `.claude/skills/delegate/scripts/.env`). Otherwise read from `~/.minimax_apikey` or wherever you keep it.

## Async pattern (video, TTS, music)

All async endpoints return a `task_id`. Poll the status endpoint until `status == "Success"`, then download:

```python
import os, time, requests
KEY = os.environ["MINIMAX_API_KEY"]
HEAD = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}

# 1. Submit
r = requests.post("https://api.minimax.io/v1/video_generation",
                  headers=HEAD,
                  json={"model": "MiniMax-Hailuo-02",
                        "prompt": "a cat typing on a laptop",
                        "duration": 6, "resolution": "768P"})
task_id = r.json()["task_id"]

# 2. Poll (video takes 1-5 min)
while True:
    s = requests.get(f"https://api.minimax.io/v1/query/video_generation?task_id={task_id}",
                     headers=HEAD).json()
    if s["status"] == "Success":
        break
    if s["status"] == "Fail":
        raise RuntimeError(s.get("message", "generation failed"))
    time.sleep(10)

# 3. Fetch the file_id → download URL
file_id = s["file_id"]
dl = requests.get(f"https://api.minimax.io/v1/files/retrieve?file_id={file_id}",
                  headers=HEAD).json()
print(dl["file"]["download_url"])
```

## Sync pattern (image, voice_clone)

Response body contains the asset directly — base64 or a URL. No polling.

```python
r = requests.post("https://api.minimax.io/v1/image_generation",
                  headers=HEAD,
                  json={"model": "image-01",
                        "prompt": "product hero shot, studio lighting",
                        "n": 1, "aspect_ratio": "16:9"})
url = r.json()["data"]["image_urls"][0]
```

## When to use each agent layer

- **Plain script (curl / Python)** — direct REST calls. Cheapest, fastest, scriptable. Use when you know what you want generated.
- **Claude Code in foundry (primary)** — ask it to write + run the script above. Good for "generate 5 variants and pick the best."
- **foundry-delegate (secondary on MiniMax)** — redundant here. MiniMax generating content about MiniMax content isn't meaningful; no token savings when you're calling REST anyway.

## Gotchas

- **Video cost** isn't free even on Coding Plan — it's billed from the multimedia pool, which is separate from the flat-rate text tokens. Check platform.minimax.io billing before bulk runs.
- **Region-lock** — `api.minimax.io` and `api.minimaxi.com` have different keys and different model catalogs. Don't cross-post.
- **Content filter** — MiniMax's safety filter blocks more aggressively than Western providers. Expect retries on prompts containing proper nouns, public figures, or unusual phrasing.
- **File retention** — generated assets on MiniMax's file storage expire (exact window varies by product, roughly 24h for video). Download and store locally.

## Official docs

- <https://platform.minimax.io/docs/api-reference/video-generation-t2v.md>
- <https://platform.minimax.io/docs/api-reference/image-generation-t2i.md>
- <https://platform.minimax.io/docs/api-reference/music-generation.md>
- <https://platform.minimax.io/docs/api-reference/speech-t2a-async-create.md>
- <https://platform.minimax.io/docs/api-reference/voice-cloning-clone.md>
