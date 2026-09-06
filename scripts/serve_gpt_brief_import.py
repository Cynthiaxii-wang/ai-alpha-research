#!/usr/bin/env python3
"""Local-only browser UI for pasting and importing the ChatGPT AI brief."""
from __future__ import annotations

import argparse
import json
import secrets
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from gpt_brief_import import import_text  # noqa: E402


PAGE = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI 晨报导入台</title><style>
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#07111f;color:#f7fbff;font:16px/1.65 -apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}main{max-width:920px;margin:42px auto;padding:0 24px}.eyebrow{color:#b8ff36;letter-spacing:.14em;font:600 13px ui-monospace,monospace}h1{font-size:38px;margin:8px 0 10px}.lead{color:#aebbd0;margin:0 0 24px}.panel{background:#0d1d31;border:1px solid #29415d;border-radius:20px;padding:24px;box-shadow:0 22px 70px #0007}.steps{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:20px 0}.step{padding:12px;border-radius:12px;background:#10243b;color:#bed0e5;font-size:14px}.step b{color:#59d7f2}textarea{width:100%;min-height:360px;resize:vertical;border:1px solid #36506c;border-radius:14px;background:#071522;color:#edf6ff;padding:18px;font:15px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace;outline:none}textarea:focus{border-color:#59d7f2;box-shadow:0 0 0 3px #59d7f222}.actions{display:flex;gap:12px;align-items:center;margin-top:16px}button{border:0;border-radius:999px;padding:12px 20px;background:#b8ff36;color:#07111f;font-weight:800;cursor:pointer}button:disabled{opacity:.5;cursor:wait}.muted{color:#8292a8;font-size:13px}.result{margin-top:18px;padding:16px;border-radius:14px;background:#071522;border:1px solid #29415d;white-space:pre-wrap;display:none}.ok{border-color:#4cae78}.bad{border-color:#ef6674;color:#ffd9dd}@media(max-width:700px){.steps{grid-template-columns:1fr}h1{font-size:30px}}
</style></head><body><main><div class="eyebrow">LOCAL ONLY · 127.0.0.1</div><h1>AI 晨报导入台</h1><p class="lead">复制 GPT 日报全文并粘贴。系统只读取其中的 AI_ALPHA_IMPORT_V1 JSON，核验后才会重建页面并尝试推送 GitHub。</p><div class="panel"><div class="steps"><div class="step"><b>01</b> 粘贴完整日报</div><div class="step"><b>02</b> 来源、日期与重复项检查</div><div class="step"><b>03</b> Quality PASS 后自动发布</div></div><textarea id="brief" placeholder="在这里粘贴 GPT 每日 AI 跟踪全文……"></textarea><div class="actions"><button id="submit">核验、导入并发布</button><span class="muted">不会上传原始粘贴内容、DuckDB 或密钥</span></div><div id="result" class="result"></div></div></main><script>
const token=__TOKEN__;const button=document.querySelector('#submit');const result=document.querySelector('#result');button.onclick=async()=>{const text=document.querySelector('#brief').value;if(!text.trim()){show('请先粘贴日报。',false);return}button.disabled=true;button.textContent='正在核验与重建…';show('处理中，请保持页面打开。研究流水线可能需要几分钟。',true);try{const response=await fetch('/import',{method:'POST',headers:{'content-type':'application/json','x-import-token':token},body:JSON.stringify({text})});const data=await response.json();const pub=data.publication||{};const message=[`导入状态：${data.status}`,data.importedEvents!=null?`事件数量：${data.importedEvents}`:'',pub.status?`GitHub 发布：${pub.status}`:'',pub.commitHash?`Commit：${pub.commitHash}`:'',data.reason||pub.reason?`说明：${data.reason||pub.reason}`:''].filter(Boolean).join('\n');show(message,response.ok&&data.status==='ok')}catch(error){show('请求失败：'+error.message,false)}finally{button.disabled=false;button.textContent='核验、导入并发布'}};function show(message,ok){result.style.display='block';result.className='result '+(ok?'ok':'bad');result.textContent=message}
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    token = ""

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._json(200, {"status": "ok", "scope": "localhost_only"})
            return
        if self.path != "/":
            self._json(404, {"status": "not_found"})
            return
        body = PAGE.replace("__TOKEN__", json.dumps(self.token)).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/import":
            self._json(404, {"status": "not_found"})
            return
        if self.headers.get("x-import-token") != self.token:
            self._json(403, {"status": "forbidden"})
            return
        try:
            length = int(self.headers.get("content-length", "0"))
            if length <= 0 or length > 2_000_000:
                raise ValueError("粘贴内容为空或超过 2MB")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            text = payload.get("text", "")
            if not isinstance(text, str):
                raise ValueError("text 必须是字符串")
            result = import_text(text, publish=True)
            self._json(200 if result["status"] == "ok" else 422, result)
        except (ValueError, json.JSONDecodeError) as exc:
            self._json(400, {"status": "rejected", "reason": str(exc)})

    def log_message(self, format: str, *args) -> None:
        print(f"[import-ui] {self.address_string()} {format % args}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve the local GPT brief import UI.")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args()
    Handler.token = secrets.token_urlsafe(24)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}"
    print(f"本地导入台：{url}\n按 Control-C 关闭。")
    if not args.no_open:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
