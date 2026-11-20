from __future__ import annotations

import asyncio
import html
import ipaddress
import json
import re
import socket
import urllib.parse
import aiohttp

from src.tools.base import Tool,ToolDefinition,ToolResult

ALLOWED_SCHEMES = {"http","https"}
MAX_BYTES = 512_000
MAX_REDIRECTS = 5
UA = "InforRadar-Agent/0.1"

BLOCKED_NETS = [ipaddress.ip_network(n) for n in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8",
    "169.254.0.0/16", "0.0.0.0/8", "100.64.0.0/10", "198.18.0.0/15",
    "192.0.0.0/24", "::1/128", "fe80::/10", "fc00::/7",
)]

_SCRIPT_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.I | re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t]{2,}|\n{3,}")

class SSRFBlocked(Exception):
    pass


async def _validate_url(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise SSRFBlocked(f"schema 不允许：{parsed.scheme or '(空)'}, 仅http/https")
    if not parsed.hostname:
        raise SSRFBlocked("url 缺少 hostname")
    loop = asyncio.get_running_loop()
    infos = await loop.run_in_executor(None, socket.getaddrinfo,parsed.hostname,None)
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if any(ip in net for net in BLOCKED_NETS):
            raise SSRFBlocked(f"目标解析受限地址:{ip}")

def _html_to_text(raw: str) -> str:
    t = _SCRIPT_RE.sub(" ", raw)
    t = _TAG_RE.sub(" ", t)
    t = html.unescape(t)
    return _WS_RE.sub(lambda m: "\n" if "\n" in m.group() else " ", t).strip()

def build_fetch_page_tool() -> Tool:
    async def fetch_page(url: str) -> ToolResult:
        current = url.strip()
        try:
            async with aiohttp.ClientSession(headers={"User-Agent":UA}) as session:
                for _hop in range(MAX_REDIRECTS + 1):
                    await _validate_url(current)
                    async with session.get(current, allow_redirects=False,
                                           timeout=aiohttp.ClientTimeout(total=20)) as resp:
                        if resp.status in (301,302,303,307,308):
                            loc = resp.headers.get("Location")
                            if not loc:
                                return ToolResult(ok=False, content="重定向缺少 Location",
                                                  error_code="E_TOOL_FAILED")
                            current = urllib.parse.urljoin(current,loc)
                            continue
                        raw = await resp.content.read(MAX_BYTES+1)
                        if len(raw) > MAX_BYTES:
                            raw = raw[:MAX_BYTES]
                        if resp.status >= 400:
                            return ToolResult(ok=False,content=f"HTTP{resp.status}:{current}",
                                              error_code="E_TOOL_FAILED")
                        text = _html_to_text(raw.decode(resp.get_encoding() or "utf-8",errors="relace"))
                        return ToolResult(ok=True,content=text or "(空页面)")
                return ToolResult(ok=False,content=f"重定向超过{MAX_REDIRECTS}次",
                                      error_code="E_TOOL_FAILED")
        except SSRFBlocked as e:
            return ToolResult(ok=False,content=f"SSRF 拦截：{e}",error_code="E_TOOL_FAILED")
        except Exception as e:
            return ToolResult(ok=False,content=f"抓取失败：{e}",error_code="E_TOOL_FAILED")

    return Tool(
        defn=ToolDefinition(
            name="fetch_page",
            description="抓取网页并返回正文文本（含 SSRF 防护，仅 http/https 公网地址）",
            input_schema={
                "type": "object",
                "required": ["url"],
                "properties": {"url": {"type": "string", "description": "完整 URL"}},
            },
            timeout=25.0,
            permission="read",
        ),
        handler=fetch_page,
    )
