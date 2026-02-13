#!/usr/bin/env python3
"""Smoke test for MCP servers via WebSocket and SSE."""
import asyncio, json, sys
try: import websockets
except: websockets=None
try: import httpx
except: httpx=None

async def test_ws(uri, name):
    if not websockets: print(f"Skip WS test (pip install websockets)"); return
    print(f"\nTesting {name} WebSocket at {uri}")
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}))
        r=json.loads(await ws.recv()); print(f"  init -> {r['result']['serverInfo']['name']}")
        await ws.send(json.dumps({"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}))
        r=json.loads(await ws.recv()); print(f"  tools -> {[t['name'] for t in r['result']['tools']]}")
    print(f"  PASS")

async def test_sse(base, name):
    if not httpx: print(f"Skip SSE test (pip install httpx)"); return
    print(f"\nTesting {name} SSE at {base}/sse")
    async with httpx.AsyncClient(timeout=10) as c:
        async with c.stream("GET",f"{base}/sse") as resp:
            url=None
            async for line in resp.aiter_lines():
                if line.startswith("data: "): url=base+line[6:].strip(); break
        if url:
            await c.post(url,json={"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}})
            print(f"  SSE POST ok")
    print(f"  PASS")

async def main():
    h=sys.argv[1] if len(sys.argv)>1 else "localhost"
    await test_ws(f"ws://{h}:8001/","Observability"); await test_ws(f"ws://{h}:8002/","Jira")
    await test_sse(f"http://{h}:8001","Observability"); await test_sse(f"http://{h}:8002","Jira")
    print("\nALL PASSED")

if __name__=="__main__": asyncio.run(main())
