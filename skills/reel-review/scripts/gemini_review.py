#!/usr/bin/env python3
"""Send videos and a prompt to a Gemini chat in the user's signed-in Arc, then save the reply.

Arc's native file picker hides its contents from accessibility, so this drives the Gemini tab over
Chrome DevTools Protocol: trusted clicks open Upload files, the file chooser is intercepted, and the
files are set on it directly. Arc must be running with --remote-debugging-port (see SKILL.md).

Usage: gemini_review.py --chat URL --prompt FILE --out REPLY.txt [--port 9333] VIDEO [VIDEO ...]
"""
import argparse
import json
import time
import urllib.request
from pathlib import Path

import websocket


class Tab:
    def __init__(self, port, url_prefix):
        tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list"))
        match = [t for t in tabs if t["type"] == "page" and t["url"].startswith(url_prefix)]
        if not match:
            raise SystemExit(f"No open tab starts with {url_prefix}. Open the Gemini chat in Arc first.")
        self.ws = websocket.create_connection(match[0]["webSocketDebuggerUrl"], timeout=60, suppress_origin=True)
        self.n = 0

    def call(self, method, **params):
        self.n += 1
        mid = self.n
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})

    def js(self, expr):
        r = self.call("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
        if "exceptionDetails" in r:
            raise RuntimeError(json.dumps(r["exceptionDetails"])[:600])
        return r["result"].get("value")

    def click(self, selector_js, label, wait=5.0):
        deadline = time.time() + wait
        pt = None
        while time.time() < deadline and not pt:
            pt = self.js(f"""(() => {{ const e = {selector_js}; if (!e) return null; e.scrollIntoView({{block:'center'}});
                const r = e.getBoundingClientRect(); return {{x: r.left + r.width/2, y: r.top + r.height/2}}; }})()""")
            if not pt:
                time.sleep(0.25)
        if not pt:
            raise SystemExit(f"{label}: not found")
        for t in ("mouseMoved", "mousePressed", "mouseReleased"):
            self.call("Input.dispatchMouseEvent", type=t, x=pt["x"], y=pt["y"], button="left", clickCount=1)

    def wait_event(self, method, timeout):
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.ws.settimeout(max(0.1, deadline - time.time()))
            try:
                msg = json.loads(self.ws.recv())
            except Exception:
                break
            if msg.get("method") == method:
                self.ws.settimeout(60)
                return msg["params"]
        self.ws.settimeout(60)
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chat", required=True, help="Gemini chat URL, e.g. https://gemini.google.com/app/<id>")
    ap.add_argument("--prompt", required=True, help="text file with the approved review prompt")
    ap.add_argument("--out", required=True)
    ap.add_argument("--port", type=int, default=9333)
    ap.add_argument("videos", nargs="+")
    a = ap.parse_args()
    files = [str(Path(v).resolve()) for v in a.videos]
    for f in files:
        if not Path(f).is_file():
            raise SystemExit(f"missing file: {f}")
    prompt = Path(a.prompt).read_text().strip()

    tab = Tab(a.port, a.chat.split("?")[0])
    tab.call("Page.enable")
    tab.call("DOM.enable")
    tab.call("Page.bringToFront")
    before = tab.js('document.querySelectorAll("model-response").length') or 0

    tab.call("Page.setInterceptFileChooserDialog", enabled=True)
    tab.click('document.querySelector(\'[aria-label="Upload & tools"]\')', "Upload & tools")
    tab.click('[...document.querySelectorAll("[role=menuitem]")].find(e => /Upload files/i.test(e.innerText || ""))', "Upload files")
    chooser = tab.wait_event("Page.fileChooserOpened", 15)
    if not chooser:
        raise SystemExit("The file chooser did not open")
    tab.call("DOM.setFileInputFiles", files=files, backendNodeId=chooser["backendNodeId"])
    tab.call("Page.setInterceptFileChooserDialog", enabled=False)

    for _ in range(120):
        time.sleep(1)
        busy = tab.js('document.querySelectorAll("[role=progressbar], mat-progress-spinner").length') or 0
        chips = tab.js('document.querySelectorAll("[data-test-id*=file], uploader-file-preview, button[aria-label*=Remove]").length') or 0
        if chips and not busy:
            break
    print(f"attached {len(files)} file(s)")

    tab.click('document.querySelector("rich-textarea .ql-editor, [contenteditable=true]")', "prompt box")
    tab.call("Input.insertText", text=prompt)
    typed = (tab.js('(document.querySelector("rich-textarea .ql-editor, [contenteditable=true]").innerText || "").trim()') or "")
    if typed != prompt:
        raise SystemExit("The prompt box text does not match the approved prompt. Nothing was sent.")
    tab.click("document.querySelector(\"[aria-label='Send message']\")", "Send")
    print("sent; waiting for the reply")

    prev, stable = "", 0
    for _ in range(150):
        time.sleep(4)
        count = tab.js('document.querySelectorAll("model-response").length') or 0
        txt = tab.js('(() => { const r = [...document.querySelectorAll("model-response")]; return r.length ? r[r.length-1].innerText : ""; })()') or ""
        busy = tab.js("!!document.querySelector(\"[aria-label='Stop response']\")")
        if count > before and txt and txt == prev and not busy:
            stable += 1
            if stable >= 3:
                break
        else:
            stable = 0
        prev = txt
    Path(a.out).write_text(prev)
    print(f"reply saved to {a.out} ({len(prev)} chars)")


if __name__ == "__main__":
    main()
