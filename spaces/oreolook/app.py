"""OreoLook's public Hugging Face Space."""
from __future__ import annotations

import html
import os
import time

import spaces
import gradio as gr

from oreolook_client import (
    OreoLookAPIError,
    begin_device_authorization,
    extract_links,
    poll_device_authorization,
    stream_completion,
)


SITE_URL = os.getenv("OREOLOOK_SITE_URL", "https://search.elixpo.com")
KEY_URL = os.getenv("POLLINATIONS_KEY_URL", "https://enter.pollinations.ai")
APP_KEY = os.getenv("OREOLOOK_APP_KEY", "").strip()
SPACE_URL = os.getenv("OREOLOOK_SPACE_URL", "https://huggingface.co/spaces/Elixpo/OreoLook")
OG_IMAGE_URL = os.getenv("OREOLOOK_OG_IMAGE_URL", f"{SITE_URL}/og-image.png")

SEO_HEAD = f"""
<meta name="description" content="OreoLook is an open-source AI search and deep research agent with live web results, grounded citations, streaming answers, follow-up memory, and downloadable PDF reports.">
<meta name="keywords" content="AI search engine, deep research agent, web search AI, cited answers, PDF research reports, Pollinations AI, OreoLook, open source AI search">
<meta name="robots" content="index, follow, max-image-preview:large, max-snippet:-1, max-video-preview:-1">
<meta name="application-name" content="OreoLook">
<meta name="theme-color" content="#f7f5f0">
<link rel="canonical" href="{SPACE_URL}">
<link rel="icon" href="{SITE_URL}/favicon.png" type="image/png">
<meta property="og:type" content="website">
<meta property="og:site_name" content="OreoLook">
<meta property="og:title" content="OreoLook — AI Search & Deep Research with Receipts">
<meta property="og:description" content="Search the live web, investigate topics deeply, verify claims with citations, and export polished PDF research reports.">
<meta property="og:url" content="{SPACE_URL}">
<meta property="og:image" content="{OG_IMAGE_URL}">
<meta property="og:image:alt" content="OreoLook AI search and deep research agent">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="OreoLook — AI Search with Receipts">
<meta name="twitter:description" content="Live web search, cited deep research, streaming answers, and downloadable PDF reports.">
<meta name="twitter:image" content="{OG_IMAGE_URL}">
<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  "name": "OreoLook",
  "alternateName": "OreoLook AI Search",
  "applicationCategory": "ResearchApplication",
  "operatingSystem": "Web",
  "url": "{SPACE_URL}",
  "image": "{OG_IMAGE_URL}",
  "description": "Open-source AI search and deep research agent with live sources, citations, follow-up memory, and PDF report generation.",
  "isAccessibleForFree": true,
  "license": "https://opensource.org/licenses/MIT",
  "creator": [
    {{"@type": "Person", "name": "Ayushman Bhattacharya"}},
    {{"@type": "Person", "name": "Nihal Gazi", "url": "https://nihalgazi.com"}}
  ],
  "publisher": {{"@type": "Organization", "name": "Pollinations AI", "url": "https://pollinations.ai"}},
  "citation": "https://arxiv.org/abs/2609.05463",
  "codeRepository": "https://github.com/pollinations/search.elixpo"
}}
</script>
"""


@spaces.GPU(duration=1)
def _zerogpu_runtime_contract():
    """ZeroGPU startup contract for a free API-proxy Space; intentionally never called."""
    return None


CSS = """
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Newsreader:opsz,wght@6..72,500;6..72,600&display=swap');
:root{--canvas:#f7f5f0;--paper:#fffdf9;--paper-2:#f1eee8;--ink:#2f2b27;--muted:#756f67;--line:#ded9d0;--accent:#c15f3c;--accent-dark:#9d472a;--accent-soft:#f8e9e1;--sage:#52705d;--shadow:0 18px 52px rgba(58,45,34,.08)}
.gradio-container,.dark .gradio-container{
  color-scheme:light!important;min-height:100vh!important;max-width:none!important;padding:0!important;
  font-family:'DM Sans',ui-sans-serif,system-ui,sans-serif!important;color:var(--ink)!important;background:var(--canvas)!important;
  --body-background-fill:var(--canvas)!important;--body-text-color:var(--ink)!important;--body-text-color-subdued:var(--muted)!important;
  --background-fill-primary:var(--paper)!important;--background-fill-secondary:var(--paper-2)!important;
  --block-background-fill:var(--paper)!important;--block-border-color:var(--line)!important;--block-label-text-color:var(--muted)!important;
  --input-background-fill:var(--paper)!important;--input-border-color:var(--line)!important;--input-placeholder-color:#9b958d!important;
  --button-primary-background-fill:var(--accent)!important;--button-primary-background-fill-hover:var(--accent-dark)!important;
  --button-primary-text-color:#fff!important;--button-secondary-background-fill:var(--paper)!important;--button-secondary-text-color:var(--ink)!important;
  --border-color-primary:var(--line)!important;--shadow-drop:var(--shadow)!important
}
.gradio-container>main,.gradio-container main,.gradio-container .main,.gradio-container .contain,.gradio-container .fill-width{max-width:none!important;width:100%!important;margin:0!important;padding-left:0!important;padding-right:0!important}
.site-header{background:rgba(255,253,249,.94)!important;border:0!important;border-bottom:1px solid var(--line)!important;padding:0!important;position:sticky!important;top:0!important;z-index:20!important;backdrop-filter:blur(18px)}
.topbar{width:min(1240px,calc(100% - 48px));margin:0 auto;min-height:70px;display:flex;align-items:center;justify-content:space-between}.brand{display:flex;align-items:center;gap:12px;color:var(--ink)}
.brand img{width:38px;height:38px;border-radius:11px;box-shadow:0 5px 16px rgba(47,43,39,.15)}.brand strong{display:block;font-size:17px;letter-spacing:-.025em}.brand small{display:block;color:var(--muted);font-size:10px;font-weight:600;letter-spacing:.07em;text-transform:uppercase;margin-top:1px}
.toplinks{display:flex;align-items:center;gap:7px}.toplinks a{color:var(--muted)!important;font-size:12px;font-weight:600;text-decoration:none!important;padding:8px 11px;border-radius:9px}.toplinks a:hover{background:var(--paper-2);color:var(--ink)!important}
.hero-wrap{background:transparent!important;border:0!important;padding:0!important}.hero{width:min(1240px,calc(100% - 48px));margin:0 auto;padding:48px 0 30px}.eyebrow{color:var(--accent);font-size:11px;font-weight:800;letter-spacing:.13em;text-transform:uppercase}
.hero h1{font:600 clamp(40px,5vw,66px)/1.02 'Newsreader',Georgia,serif;letter-spacing:-.045em;color:var(--ink);margin:9px 0 12px;max-width:780px}.hero h1 em{color:var(--accent);font-style:normal}.hero p{color:var(--muted);font-size:16px;line-height:1.65;max-width:680px;margin:0}
.workspace{width:min(1240px,calc(100% - 48px))!important;max-width:1240px!important;margin:0 auto!important;padding:0 0 42px!important;gap:20px!important;align-items:flex-start!important}
.chat-card,.panel{background:var(--paper)!important;border:1px solid var(--line)!important;border-radius:18px!important;box-shadow:var(--shadow)!important}.chat-card{padding:10px!important;overflow:hidden}.panel{padding:18px!important;box-shadow:0 9px 32px rgba(58,45,34,.055)!important}
.panel h3,.panel h4,.panel strong,.panel label,.panel span,.panel p{color:var(--ink)!important}.panel h3{font:600 20px 'Newsreader',Georgia,serif!important;margin:0 0 4px!important}.panel-copy{color:var(--muted);font-size:12px;line-height:1.55;margin-bottom:12px}
.chatbot,.chatbot>div{background:var(--paper)!important;border:0!important;color:var(--ink)!important}.chatbot{height:clamp(390px,calc(100dvh - 365px),650px)!important}.chatbot .message{border-radius:16px!important;box-shadow:none!important;font-size:14px!important;line-height:1.6!important}.chatbot .message.user{background:#37322d!important;color:#fff!important}.chatbot .message.bot{background:var(--paper-2)!important;border:1px solid var(--line)!important;color:var(--ink)!important}
.composer-row{border-top:1px solid var(--line)!important;padding:10px 4px 2px!important;gap:9px!important}.composer{border:0!important;background:transparent!important}.composer textarea{font-size:15px!important;line-height:1.5!important;background:#f8f6f1!important;color:var(--ink)!important;border:1px solid var(--line)!important;border-radius:13px!important;padding:13px 14px!important}.send-btn{min-width:122px!important;border:0!important;border-radius:13px!important;background:var(--accent)!important;color:#fff!important;font-weight:700!important;box-shadow:none!important}.send-btn:hover{background:var(--accent-dark)!important}
.new-btn{border:1px solid var(--line)!important;border-radius:11px!important;color:var(--ink)!important;background:var(--paper)!important;font-weight:700!important}.new-btn:hover{border-color:#bcb4a9!important;background:var(--paper-2)!important}
.oauth-status{background:#f8f6f1!important;border:1px solid var(--line)!important;border-radius:11px!important;padding:11px 12px!important}.oauth-status p{font-size:12px!important;line-height:1.5!important;margin:0!important}.oauth-actions{gap:8px!important}.oauth-connect{background:var(--accent)!important;color:#fff!important;border:0!important;font-weight:700!important}.oauth-disconnect{background:transparent!important;color:var(--muted)!important;border:1px solid var(--line)!important}
.session-actions{gap:10px!important;margin-top:9px!important;align-items:stretch!important}.session-actions>*{flex:1 1 0!important}.key-link{padding:0!important;border:0!important;background:transparent!important}.key-link a{display:flex;align-items:center;justify-content:center;min-height:42px;padding:9px 12px;border:1px solid var(--line);border-radius:11px;background:var(--paper);color:var(--accent-dark)!important;text-decoration:none!important;font-size:12px;font-weight:700;text-align:center}.key-link a:hover{background:var(--accent-soft);border-color:#e7baa7}
.secondary-card{background:var(--paper)!important;border:1px solid var(--line)!important;border-radius:14px!important;box-shadow:0 7px 22px rgba(58,45,34,.04)!important;overflow:hidden!important}.secondary-card>button{padding:13px 15px!important;color:var(--ink)!important;font-weight:700!important}.secondary-card [class*="content"]{padding:0 14px 14px!important}
.progress-card{background:#37322d!important;border:0!important;border-radius:14px!important;color:#f7f2eb!important;padding:12px 15px!important}.progress-card p,.progress-card strong{color:#f7f2eb!important;font-size:12px!important;margin:0!important}
.source-panel a,.artifact-panel a{display:block;background:#f8f6f1;border:1px solid var(--line);border-radius:11px;color:var(--ink)!important;margin:8px 0;padding:11px 12px;text-decoration:none!important;font-size:12px;font-weight:650;overflow-wrap:anywhere}.source-panel a:hover{border-color:#bdb4aa;background:#fff}.artifact-panel a{background:var(--accent-soft);border-color:#e7baa7;color:var(--accent-dark)!important}
.feature-list{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:11px}.feature-list span{background:#f5f2ec;border:1px solid var(--line);border-radius:9px;padding:9px 10px;color:var(--muted)!important;font-size:11px;font-weight:600}
#examples{border:0!important;background:transparent!important;margin-top:10px!important}#examples button{background:var(--paper)!important;border:1px solid var(--line)!important;border-radius:999px!important;color:var(--muted)!important;font-size:11px!important;padding:7px 12px!important}#examples button:hover{border-color:#bdb4aa!important;color:var(--ink)!important}
.footer-note{text-align:center;color:#928b82;font-size:11px;padding:0 20px 28px}.footer-note a{color:var(--accent-dark)!important;text-decoration:none!important;font-weight:700}
@media(max-width:960px){.workspace{flex-direction:column!important}.workspace>div{width:100%!important;min-width:0!important}.research-rail{display:grid!important;grid-template-columns:1fr 1fr!important}.hero h1{font-size:48px}.chatbot{height:clamp(420px,calc(100dvh - 330px),620px)!important}}
@media(max-width:640px){.topbar,.hero,.workspace{width:calc(100% - 26px)!important}.topbar{min-height:62px}.toplinks a:not(:first-child){display:none}.hero{padding:28px 0 18px}.hero h1{font-size:39px}.hero p{font-size:14px}.research-rail{display:flex!important}.chatbot{height:clamp(360px,calc(100dvh - 300px),540px)!important}.send-btn{min-width:82px!important}.composer-row{align-items:stretch!important}.feature-list{grid-template-columns:1fr}}
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


def connect_pollinations():
    """Authorize one browser session to spend the user's own Pollinations Pollen."""
    try:
        authorization = begin_device_authorization(APP_KEY)
    except OreoLookAPIError as exc:
        yield "", f"**Sign-in unavailable:** {html.escape(str(exc))}"
        return
    link = html.escape(authorization.verification_uri, quote=True)
    code = html.escape(authorization.user_code)
    yield "", (
        f'<a href="{link}" target="_blank"><strong>Open Pollinations to authorize ↗</strong></a>'
        f"<br>Enter code <code>{code}</code>. This page will connect automatically."
    )
    deadline = time.monotonic() + authorization.expires_in
    while time.monotonic() < deadline:
        time.sleep(authorization.interval)
        try:
            token = poll_device_authorization(authorization.device_code)
        except OreoLookAPIError as exc:
            yield "", f"**Sign-in stopped:** {html.escape(str(exc))}"
            return
        if token:
            yield token, "**Connected to Pollinations.** Requests use your account and approved budget."
            return
    yield "", "**Sign-in code expired.** Select Connect with Pollinations to start again."


def disconnect_pollinations():
    """Forget the user-scoped Pollinations key held in this browser session."""
    return "", "Not connected. Connect your Pollinations account to search."


with gr.Blocks(title="OreoLook — AI search with receipts") as demo:
    conversation = gr.State([])
    api_key = gr.State("")
    mode = gr.State("Auto")
    gr.HTML(f"""<div class="topbar"><div class="brand">
      <img src="{SITE_URL}/favicon.png" alt="OreoLook"><div><strong>OreoLook</strong><small>AI search with receipts</small></div>
    </div><div class="toplinks"><a href="{SITE_URL}" target="_blank">Website ↗</a><a href="{SITE_URL}/docs" target="_blank">API docs ↗</a><a href="https://github.com/pollinations/search.elixpo" target="_blank">GitHub ↗</a></div></div>""", elem_classes="site-header")
    gr.HTML("""<div class="hero"><span class="eyebrow">Research, grounded</span><h1>The web, with <em>receipts.</em></h1><p>Ask a quick question, investigate a topic from several angles, or turn current research into a polished PDF report.</p></div>""", elem_classes="hero-wrap")
    with gr.Row(elem_classes="workspace"):
        with gr.Column(scale=8, min_width=560):
            with gr.Group(elem_classes="chat-card"):
                chatbot = gr.Chatbot(
                    value=[], height=610, show_label=False,
                    placeholder=(
                        "Ask OreoLook anything. Try today's news, a cited comparison, "
                        "a deep investigation, or a PDF briefing."
                    ),
                    elem_classes="chatbot",
                )
                with gr.Row(elem_classes="composer-row"):
                    prompt = gr.Textbox(
                        placeholder="What should OreoLook investigate?", show_label=False,
                        lines=2, max_lines=7, container=False, elem_classes="composer", scale=8,
                    )
                    send = gr.Button("Ask OreoLook", variant="primary", elem_classes="send-btn", scale=1)
            gr.Examples(
                examples=[
                    "What changed in AI today? Cite the original sources.",
                    "Compare PostgreSQL, MySQL, and MongoDB for a high-traffic application.",
                    "Research the latest climate-tech funding trends and explain the strongest signals.",
                    "Create a PDF briefing on this week's major space-technology news.",
                ], inputs=prompt, label="Start with an example", elem_id="examples",
            )
        with gr.Column(scale=3, min_width=290, elem_classes="research-rail"):
            with gr.Group(elem_classes="panel"):
                gr.HTML('<h3>Session controls</h3><div class="panel-copy">OreoLook automatically chooses the right research depth for each question.</div>')
                show_tasks = gr.Checkbox(value=True, label="Show task progress")
                oauth_status = gr.Markdown(
                    "Not connected. Connect your Pollinations account to search.",
                    elem_classes="oauth-status",
                )
                with gr.Row(elem_classes="oauth-actions"):
                    oauth_connect = gr.Button(
                        "Connect with Pollinations", variant="primary", elem_classes="oauth-connect",
                    )
                    oauth_disconnect = gr.Button("Disconnect", elem_classes="oauth-disconnect")
                with gr.Row(elem_classes="session-actions"):
                    gr.HTML(
                        f'<a href="{KEY_URL}" target="_blank">Get an API key ↗</a>',
                        elem_classes="key-link",
                    )
                    new_conversation = gr.Button("＋ New conversation", elem_classes="new-btn")
            progress = gr.Markdown(_progress([], True), elem_classes="progress-card")
            with gr.Accordion("Sources", open=False, elem_classes="secondary-card"):
                sources = gr.Markdown(_sources_markdown("")[0], elem_classes="source-panel")
            with gr.Accordion("Downloads", open=False, elem_classes="secondary-card"):
                artifacts = gr.Markdown(_sources_markdown("")[1], elem_classes="artifact-panel")
            with gr.Accordion("Built for real research", open=False, elem_classes="secondary-card"):
                gr.HTML("""<div class="feature-list"><span>Live web search</span><span>Automatic depth</span><span>Source citations</span><span>PDF reports</span><span>Same-tab memory</span><span>Streaming answers</span></div>""")
    gr.HTML(f'<div class="footer-note">Powered by <a href="https://pollinations.ai" target="_blank">Pollinations AI</a> · Learn more at <a href="{SITE_URL}" target="_blank">search.elixpo.com</a></div>')

    outputs = [chatbot, conversation, progress, sources, artifacts, prompt]
    inputs = [prompt, conversation, api_key, mode, show_tasks]
    prompt.submit(chat, inputs=inputs, outputs=outputs, concurrency_limit=8, api_name="research")
    send.click(chat, inputs=inputs, outputs=outputs, concurrency_limit=8, api_name=False)
    new_conversation.click(reset_conversation, outputs=outputs, queue=False, api_name="new_conversation")
    oauth_connect.click(
        connect_pollinations, outputs=[api_key, oauth_status],
        concurrency_limit=4, api_name=False,
    )
    oauth_disconnect.click(
        disconnect_pollinations, outputs=[api_key, oauth_status],
        queue=False, api_name=False,
    )


if __name__ == "__main__":
    # The production OreoLook MCP is hosted at search.elixpo.com/mcp. Keeping
    # this UI as a plain Gradio app avoids exposing its API-key input as a tool.
    demo.queue(default_concurrency_limit=8, max_size=64).launch(css=CSS, head=SEO_HEAD)
