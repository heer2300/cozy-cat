# 🐱 Cozy Cat

A pixel-art desktop cat with its own personality. It lives in a cozy room, jumps on shelves, climbs the curtain, plays with a ball, naps in its bed, and **chats with you using a local AI (Ollama)**, by typing or by voice. Every cat has its own character and its own voice.

<!-- Add a screenshot or GIF here, e.g. ![screenshot](screenshot.png) -->

## Features

- **6 cats, 6 personalities:** Mango (hyper and hungry), Shadow (dry and mysterious), Duchess (regal), Biscuit (dramatic diva), Snow (shy and sweet), Smokey (calm and wise)
- **A living room:** the cat walks, runs, jumps, climbs, stretches, grooms, sleeps and eats on its own, depending on its hunger, energy and mood
- **Interactive:** pet the cat, throw a ball, drop treats, chase a laser pointer
- **Chat with AI:** talk to the cat through [Ollama](https://ollama.com). It stays in character and can act on what you say ("go play!")
- **Text or voice:** type, or talk into your microphone. The cat talks back in its own voice
- **Per-cat voices:** natural neural voices, a cute offline "cat-ese" voice, or your system voice
- **Window with a view:** scrolling pixel-art hills outside the window

## Requirements

- Python 3.9 or newer
- [Ollama](https://ollama.com) with a model installed
- The art packs listed below

## Setup

### 1. Install Python packages

```bash
pip install pygame
```

Optional extras:

```bash
pip install edge-tts                      # natural voices, a different one per cat (needs internet)
pip install SpeechRecognition pyaudio     # talk to the cat with your microphone
pip install pyttsx3                       # use your system voice
```

### 2. Install Ollama and a model

```bash
ollama pull llama3.2
```

Ollama is started automatically if it isn't running. Check the connection any time with:

```bash
python pixel_cat_v5.py --test
```

### 3. Add the art

The art is **not included in this repository**. Download it and extract the folders **next to `pixel_cat_v5.py`**:

```
pixel_cat_v5.py
Pet Cats Pack/          <- required
cozy/                   <- optional (bookshelves, bed, coffee, bread)
Free Pixel Art Hill/    <- optional (hills in the window)
```


from itch.io 
| Pack | Used for | Notes |
|---|---|---|
| **Pet Cats Pack** | the six cats and their animations | CC0 |
| **cozy** | furniture and props | check the license where you downloaded it |
| **Free Pixel Art Hill** | the view from the window | read the license file inside the archive |

If the cozy or hill pack is missing, the game uses simple placeholder furniture and a painted hill view. If the cat pack is missing, the game tells you where to put it.

### 4. Run

```bash
python pixel_cat_v5.py
```

## Controls

| Key / mouse | Action |
|---|---|
| `Enter` | Talk to the cat (type in TEXT mode, speak in VOICE mode) |
| `Tab` | Switch between TEXT and VOICE mode |
| `M` | Listen with the microphone |
| `S` | Turn the cat's voice on/off |
| `V` | Switch voice style (natural / cat-ese / system) and hear a sample |
| `F` | Drop a treat |
| `B` | Drop a ball |
| Hold `Space` | Laser pointer (the cat chases the mouse) |
| `1` to `6` | Change cat |
| `R` | Reconnect to Ollama |
| Left click | Pet the cat / drag and throw the ball |
| Right click | Drop a ball at the mouse |
| `Esc` | Quit |

## Options

```bash
python pixel_cat_v5.py --cat 3 --model qwen2.5:3b --voice edge --scale 5
```

| Option | Default | Description |
|---|---|---|
| `--cat` | `1` | Which cat, 1 to 6 |
| `--model` | `llama3.2` | Ollama model to chat with |
| `--host` | `http://127.0.0.1:11434` | Ollama address |
| `--voice` | `auto` | `auto`, `edge`, `animalese`, `system` or `off` |
| `--scale` | `6` | Screen pixels per art pixel (6 gives a 1152x648 window; use 4 or 5 on small screens) |
| `--assets` | script folder | Folder containing the extracted art packs |
| `--cats-dir`, `--cozy-dir`, `--hills-dir` | auto | Point to each pack folder directly |
| `--test` | | Test the Ollama connection and exit |

## Customize

- **Personalities:** edit the `CATS` table in `pixel_cat_v5.py` (name, character description, speed, playfulness, laziness, hunger rate, idle phrases).
- **Voices:** edit the `VOICES` table (neural voice name, pitch, rate, volume, cat-ese pitch). List all natural voices with `edge-tts --list-voices`.
- **Room layout:** the places the cat can stand on are the `PLATS` list near the top of the file.

## Troubleshooting

- **"Brain offline":** make sure Ollama is installed, run `ollama pull llama3.2`, then press `R` in the game or run `--test`.
- **Model not found:** use `--model` with a model from `ollama list`.
- **No natural voice:** `pip install edge-tts` and check your internet connection. The game falls back to the cat-ese voice.
- **Microphone not working:** install `SpeechRecognition` and `pyaudio` (on Windows, `pip install pipwin` then `pipwin install pyaudio` if pyaudio fails). Speech recognition uses Google's service and needs internet.
- **Window too big:** use `--scale 4`.

## Credits

- Cat sprites: *Pet Cats Pack* (CC0)
- Props: *cozy* pack
- Background hills: *Free Pixel Art Hill*
- AI chat: [Ollama](https://ollama.com)
- Natural voices: [edge-tts](https://github.com/rany2/edge-tts)
- Built with [pygame](https://www.pygame.org)
