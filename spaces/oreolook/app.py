"""OreoLook's public Hugging Face Space."""
from __future__ import annotations

import html
import os

import spaces
import gradio as gr

from oreolook_client import OreoLookAPIError, extract_links, stream_completion


SITE_URL = os.getenv("OREOLOOK_SITE_URL", "https://search.elixpo.com")
KEY_URL = os.getenv("POLLINATIONS_KEY_URL", "https://enter.pollinations.ai")


@spaces.GPU(duration=1)
def _zerogpu_runtime_contract():
    """ZeroGPU startup contract for a free API-proxy Space; intentionally never called."""
    return None


CSS = """
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap');
:root{--paper:#fff;--canvas:#f7f5f2;--ink:#151515;--soft:#625e59;--line:#e4e0db;--red:#e53935;--redsoft:#fff0ef;--green:#25875a}
.gradio-container{font-family:'DM Sans',sans-serif!important;background:radial-gradient(circle at 8% 0%,#fff 0,transparent 30%),var(--canvas)!important;color:var(--ink)!important;max-width:none!important;padding:0!important}
.app-shell{max-width:1240px;margin:auto;padding:22px 28px 36px}.topbar{display:flex;align-items:center;justify-content:space-between;padding:5px 2px 22px;border-bottom:1px solid var(--line)}
.brand{display:flex;align-items:center;gap:11px}.brand img{width:42px;height:42px;border-radius:12px;box-shadow:0 5px 18px #0002}.brand strong{font:700 20px 'Space Grotesk';letter-spacing:-.04em}.brand small{display:block;color:#928d87;font-size:9px;letter-spacing:.1em;text-transform:uppercase}.toplinks{display:flex;gap:18px}.toplinks a{color:var(--soft)!important;font-size:12px;font-weight:700;text-decoration:none!important}
.hero{padding:34px 0 24px}.hero h1{font:700 clamp(36px,5vw,62px)/1 'Space Grotesk';letter-spacing:-.06em;margin:7px 0 13px}.hero h1 em{color:var(--red);font-style:normal}.hero p{color:var(--soft);font-size:15px;max-width:720px;line-height:1.65}.eyebrow{color:var(--red);font-size:10px;font-weight:800;letter-spacing:.14em;text-transform:uppercase}
.workspace{gap:16px!important}.control-card,.side-card,.chat-card{background:rgba(255,255,255,.94)!important;border:1px solid var(--line)!important;border-radius:16px!important;box-shadow:0 14px 40px rgba(42,34,28,.06)!important}.control-card,.side-card{padding:17px!important}.chat-card{padding:8px!important}
.control-card h3,.side-card h3{font:700 15px 'Space Grotesk';letter-spacing:-.025em;margin:0 0 5px}.control-card p,.side-card p{color:var(--soft);font-size:11px;line-height:1.5}.mode-picker label{background:#f5f2ef!important;border-radius:9px!important}.mode-picker input:checked+span{color:var(--red)!important}
.chatbot{border:0!important;background:transparent!important}.chatbot .message{border-radius:14px!important;box-shadow:none!important}.chatbot .message.user{background:#171717!important;color:white!important}.chatbot .message.bot{background:#faf8f5!important;border:1px solid var(--line)!important;color:var(--ink)!important}
.composer textarea{font-size:14px!important;line-height:1.5!important}.send-btn{background:var(--ink)!important;border:0!important;color:#fff!important;font-weight:800!important}.send-btn:hover{background:var(--red)!important}.new-btn{border-color:var(--line)!important;color:var(--ink)!important;font-weight:700!important}
.progress-card{background:#171717!important;border:0!important;border-radius:13px!important;color:#ddd!important;padding:2px 13px!important}.progress-card p{color:#ddd!important;font-size:11px!important}.source-panel a,.artifact-panel a{display:block;background:#faf8f5;border:1px solid var(--line);border-radius:10px;color:var(--ink)!important;margin:7px 0;padding:10px 12px;text-decoration:none!important;font-size:11px;font-weight:700}.artifact-panel a{background:var(--redsoft);border-color:#f2c9c7;color:#b82d29!important}
.examples{border:0!important}.examples button{background:#fff!important;border:1px solid var(--line)!important;border-radius:10px!important;color:var(--soft)!important;font-size:11px!important}.footer-note{text-align:center;color:#999;font-size:10px;padding:24px 0 4px}.footer-note a{color:var(--red)!important}
@media(max-width:760px){.app-shell{padding:16px 13px}.toplinks{display:none}.hero{padding-top:25px}.hero h1{font-size:42px}.workspace{display:flex!important;flex-direction:column!important}}
"""


def _sources_markdown(answer: str) -> tuple[str, str]:
    sources, artifacts = extract_links(answer)
    source_lines = ["### Sources"]
    source_lines.extend(
        f"[{html.escape(label[:90])}]({url})" for label, url in sources[:12]
    )
    artifact_lines = ["### Downloads"]
    artifact_lines.extend(
        f"[Download PDF {index}]({url})" for index, url in enumerate(artifacts[:6], 1)
    )
    if len(source_lines) == 1:
        source_lines.append("Sources will appear here when OreoLook cites them.")
    if len(artifact_lines) == 1:
        artifact_lines.append("Generated reports will appear here as download links.")
    return "\n\n".join(source_lines), "\n\n".join(artifact_lines)


def _progress(tasks: list[str], visible: bool) -> str:
    if not visible:
        return "*Task progress hidden.*"
    if not tasks:
        return "**Ready.** Ask OreoLook anything that benefits from fresh sources."
    return "**Research trail**\n\n" + "\n\n".join(f"✓ {html.escape(task)}" for task in tasks[-8:])


def chat(prompt: str, messages: list[dict], api_key: str, mode: str, show_tasks: bool):
    """Stream an OreoLook research answer with citations and artifact links."""
    prompt = str(prompt or "").strip()
    history = [dict(item) for item in (messages or [])]
    if not prompt:
        yield history, history, _progress([], show_tasks), *_sources_markdown(""), ""
        return
    history.append({"role": "user", "content": prompt})
    display = [dict(item) for item in history]
    display.append({"role": "assistant", "content": "_Waking up the search hamsters…_"})
    tasks: list[str] = []
    answer = ""
    yield display, history, _progress(tasks, show_tasks), *_sources_markdown(answer), ""
    try:
        for event in stream_completion(history, api_key=api_key, mode=mode):
            if event.kind == "task":
                tasks.append(event.content)
            else:
                answer += event.content
                display[-1] = {"role": "assistant", "content": answer}
            sources, artifacts = _sources_markdown(answer)
            yield display, history, _progress(tasks, show_tasks), sources, artifacts, ""
    except OreoLookAPIError as exc:
        answer = f"**Tiny snag:** {html.escape(str(exc))}"
        display[-1] = {"role": "assistant", "content": answer}
        yield display, history, _progress(tasks, show_tasks), *_sources_markdown(answer), ""
        return
    if not answer.strip():
        answer = "**Tiny snag:** OreoLook finished without returning an answer. Please retry."
        display[-1] = {"role": "assistant", "content": answer}
    history.append({"role": "assistant", "content": answer})
    yield display, history, _progress(tasks, show_tasks), *_sources_markdown(answer), ""


def reset_conversation():
    """Clear only the current browser session's conversation state."""
    return [], [], _progress([], True), *_sources_markdown(""), ""


with gr.Blocks(title="OreoLook — AI search with receipts") as demo:
    conversation = gr.State([])
    gr.HTML(f"""
    <div class="app-shell"><div class="topbar"><div class="brand">
      <img src="{SITE_URL}/favicon.png" alt="OreoLook"><div><strong>OreoLook</strong><small>AI search with receipts</small></div>
    </div><div class="toplinks"><a href="{SITE_URL}" target="_blank">Website ↗</a><a href="{SITE_URL}/docs" target="_blank">API docs ↗</a><a href="https://github.com/pollinations/search.elixpo" target="_blank">Source ↗</a></div></div>
    <div class="hero"><span class="eyebrow">Live research playground</span><h1>Ask the web.<br><em>Keep the receipts.</em></h1><p>Quick answers, deep investigations, current sources, follow-up memory, and downloadable PDF reports—all through Pollinations.</p></div></div>
    """)
    with gr.Row(elem_classes="app-shell workspace"):
        with gr.Column(scale=3, min_width=250):
            with gr.Group(elem_classes="control-card"):
                gr.Markdown("### Search controls\nChoose quick for speed or deep for a multi-angle investigation.")
                mode = gr.Radio(
                    ["Quick Search", "Deep Research"], value="Quick Search",
                    label="Research mode", elem_classes="mode-picker",
                )
                show_tasks = gr.Checkbox(value=True, label="Show task progress")
                api_key = gr.Textbox(
                    label="Pollinations API key", type="password",
                    placeholder="sk_… (optional when demo access is enabled)",
                    info="Held only for this browser session. Never enter an ag_ token.",
                )
                gr.HTML(f'<a href="{KEY_URL}" target="_blank" style="font-size:11px;color:#e53935;font-weight:700">Get a Pollinations key ↗</a>')
            progress = gr.Markdown(_progress([], True), elem_classes="progress-card")
            new_conversation = gr.Button("＋ New conversation", elem_classes="new-btn")
        with gr.Column(scale=7, min_width=420):
            with gr.Group(elem_classes="chat-card"):
                chatbot = gr.Chatbot(
                    value=[], height=560, show_label=False,
                    placeholder="Ask about today's news, compare products, research a topic, or request a PDF.",
                    elem_classes="chatbot",
                )
                with gr.Row():
                    prompt = gr.Textbox(
                        placeholder="What should OreoLook investigate?", show_label=False,
                        lines=2, max_lines=7, elem_classes="composer", scale=8,
                    )
                    send = gr.Button("Search", variant="primary", elem_classes="send-btn", scale=1)
            gr.Examples(
                examples=[
                    "What changed in AI today? Cite the original sources.",
                    "Compare PostgreSQL, MySQL, and MongoDB for a high-traffic application.",
                    "Research the latest climate-tech funding trends and explain the strongest signals.",
                    "Create a PDF briefing on this week's major space-technology news.",
                ], inputs=prompt, label="Try a prompt", elem_classes="examples",
            )
        with gr.Column(scale=3, min_width=250):
            with gr.Group(elem_classes="side-card"):
                sources = gr.Markdown(_sources_markdown("")[0], elem_classes="source-panel")
            with gr.Group(elem_classes="side-card"):
                artifacts = gr.Markdown(_sources_markdown("")[1], elem_classes="artifact-panel")
            gr.Markdown(
                "### What this demo can do\n🌐 Live web search  \n🧭 Deep research  \n🔗 Grounded citations  \n📄 PDF reports  \n🧠 Same-tab follow-ups",
                elem_classes="side-card",
            )
    gr.HTML(f'<div class="footer-note">Powered by <a href="https://pollinations.ai" target="_blank">Pollinations AI</a> · Learn more at <a href="{SITE_URL}" target="_blank">search.elixpo.com</a></div>')

    outputs = [chatbot, conversation, progress, sources, artifacts, prompt]
    inputs = [prompt, conversation, api_key, mode, show_tasks]
    prompt.submit(chat, inputs=inputs, outputs=outputs, concurrency_limit=8, api_name="research")
    send.click(chat, inputs=inputs, outputs=outputs, concurrency_limit=8, api_name=False)
    new_conversation.click(reset_conversation, outputs=outputs, queue=False, api_name="new_conversation")


if __name__ == "__main__":
    # The production OreoLook MCP is hosted at search.elixpo.com/mcp. Keeping
    # this UI as a plain Gradio app avoids exposing its API-key input as a tool.
    demo.queue(default_concurrency_limit=8, max_size=64).launch(css=CSS)
