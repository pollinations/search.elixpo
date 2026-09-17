---
title: OreoLook
emoji: 🔎
colorFrom: red
colorTo: gray
sdk: gradio
sdk_version: 6.27.0
python_version: "3.12"
app_file: app.py
pinned: true
license: mit
short_description: Live AI search with citations, research, and PDF reports.
thumbnail: https://search.elixpo.com/og-image.png
tags:
  - agent
  - search
  - deep-research
  - pollinations
  - arxiv:2609.05463
---

# OreoLook Space

[![Powered by Pollinations](https://img.shields.io/badge/Powered%20by-Pollinations-e53935)](https://pollinations.ai)
[![Paper](https://img.shields.io/badge/arXiv-2609.05463-b31b1b)](https://arxiv.org/abs/2609.05463)

OreoLook is Pollinations' open-source AI research scout: it searches current
sources, reads useful pages, streams a grounded answer, preserves same-tab
follow-ups, and can produce downloadable PDF reports.

The Space is a thin UI. It sends OpenAI-compatible Chat Completions requests to
`https://gen.pollinations.ai/v1` using the registered OreoLook model. Pollinations
then delegates the run to OreoLook with a short-lived `ag_` token. The Space
never requests, receives, displays, stores, or logs that delegated token.

This demo accompanies **“A Three-Layer Caching Architecture for Low-Latency
LLM Web Search”** by Ayushman Bhattacharya and Nihal Gazi (2026):
[arXiv:2609.05463](https://arxiv.org/abs/2609.05463) ·
[Hugging Face Papers](https://huggingface.co/papers/2609.05463). Linking the
paper here lets Hugging Face associate this Space with the paper's Apps/Demos
section. OreoLook is developed with and powered by
[Pollinations AI](https://pollinations.ai).

```bibtex
@article{bhattacharya2026three,
  title={A Three-Layer Caching Architecture for Low-Latency LLM Web Search},
  author={Bhattacharya, Ayushman and Gazi, Nihal},
  journal={arXiv preprint arXiv:2609.05463},
  year={2026}
}
```

## Features

- Quick Search and Deep Research controls
- Streaming Markdown responses
- Optional task-progress trail kept separate from the final answer
- Clickable citation panel
- Downloadable PDF artifact panel
- Same-browser-session follow-ups and a clear New conversation action
- Optional masked user-provided Pollinations key
- Friendly bounded failures for authentication, rate limiting, timeouts, and 5xx errors

## Hugging Face settings

Add this only under **Settings → Repository secrets** when the public demo
should work without requiring every visitor to supply a key:

| Secret | Required | Purpose |
|---|---:|---|
| `POLLINATIONS_API_KEY` | Optional | Normal `sk_` Pollinations key used as the demo fallback. |

Do not configure `AGENT_TOKEN`, `AGENT_RUN_TOKEN`, `API_KEY`, a signing secret,
or any `ag_` value. Pollinations owns delegated-token minting and passes the
short-lived token directly to the OreoLook endpoint.

These are public, non-secret Space variables and normally need no changes:

| Variable | Default |
|---|---|
| `POLLINATIONS_BASE_URL` | `https://gen.pollinations.ai/v1` |
| `POLLINATIONS_MODEL` | `Circuit-Overtime/OreoLook` |
| `OREOLOOK_SITE_URL` | `https://search.elixpo.com` |
| `POLLINATIONS_KEY_URL` | `https://enter.pollinations.ai` |

If no demo secret is configured, visitors must enter their own normal
Pollinations API key. The masked component sends it only to the Space backend
for the current request. It is not written to disk, logs, analytics, chat
history, or generated links. A supplied `ag_` token is rejected before any
network request.

## Run locally

From this directory:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
export POLLINATIONS_API_KEY="sk_your_normal_key"
python app.py
```

Open the local Gradio URL printed by the process. The environment key is
optional; omit it to test the user-supplied-key flow.

## Deploy

Create the public Space on a personal account using the free ZeroGPU flavor,
then push this directory as the Space repository root:

```bash
hf repos create Elixpo/OreoLook --type space --space-sdk gradio \
  --flavor zero-a10g --public
hf upload Elixpo/OreoLook . --repo-type space \
  --exclude "**/__pycache__/**"
```

The YAML header selects Python 3.12, Gradio 6.27.0, and `app.py`. The Space
uses the free-account `zero-a10g` flavor only to satisfy Hugging Face's Gradio
hosting policy. Its decorated ZeroGPU function is never called; all real work
is an outbound Pollinations API request, so visitors do not consume GPU quota.
Hugging Face installs `requirements.txt` automatically. Add the optional demo
key in the Space settings, never in Git.

## Health and smoke checks

After the Space reports **Running**:

1. Open it without a key. It should either use the configured demo secret or
   ask for a key without exposing implementation details.
2. Run a Quick Search and confirm the answer streams while task updates remain
   in the separate progress card.
3. Run Deep Research and confirm citations appear as clickable source cards.
4. Request a PDF and open the download from the Downloads panel.
5. Ask a follow-up in the same tab, then click New conversation and confirm the
   previous context no longer influences the answer.
6. Enter an invalid key and verify the UI shows a safe 401/403 message.

Automated unit smoke tests live in `tester/test_huggingface_space.py` in the
main OreoLook repository. They cover SSE parsing, task separation, key safety,
citations, PDF links, mode routing, and upstream failures without making paid
network calls.

## Failure modes

- **401:** the user or demo key is invalid.
- **403:** the key cannot access the registered model, or the model is not yet public.
- **429:** Pollinations rate limit; retry after a short pause.
- **5xx:** temporary Pollinations or OreoLook upstream failure.
- **Timeout:** the bounded read window elapsed; retry, or use Quick Search for a smaller request.

Project website: [search.elixpo.com](https://search.elixpo.com)  
Source: [pollinations/search.elixpo](https://github.com/pollinations/search.elixpo)
