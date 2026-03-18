#!/usr/bin/env python3
"""Smoke test for MCP servers via WebSocket and SSE."""
import asyncio, json, sys
try: import websockets
except Exception: websockets=None
try: import httpx
except Exception: httpx=None

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
            r=await c.post(url,json={"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}})
            print(f"  SSE POST -> {r.status_code}")
            async with c.stream("GET",f"{base}/sse") as resp2:
                msg_url=None
                async for line in resp2.aiter_lines():
                    if line.startswith("data: "):
                        data=line[6:].strip()
                        if data.startswith("/"):
                            msg_url=base+data; break
                        try:
                            payload=json.loads(data)
                            if "result" in payload and "serverInfo" in payload["result"]:
                                sname=payload["result"]["serverInfo"]["name"]
                                print(f"  SSE serverInfo.name -> {sname}")
                                assert sname==name.lower().replace(" ","-")+"-mcp" or sname in ("observability-mcp","jira-mcp"), f"Unexpected serverInfo.name: {sname}"
                                break
                        except (json.JSONDecodeError, KeyError):
                            pass
                if msg_url:
                    await c.post(msg_url,json={"jsonrpc":"2.0","id":10,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}})
                    async for line in resp2.aiter_lines():
                        if line.startswith("data: ") and not line[6:].strip().startswith("/"):
                            try:
                                payload=json.loads(line[6:].strip())
                                if "result" in payload and "serverInfo" in payload["result"]:
                                    sname=payload["result"]["serverInfo"]["name"]
                                    print(f"  SSE serverInfo.name -> {sname}")
                                    assert sname in ("observability-mcp","jira-mcp"), f"Unexpected serverInfo.name: {sname}"
                                    break
                            except (json.JSONDecodeError, KeyError):
                                pass
    print(f"  PASS")

async def test_ws_tool_obs(uri):
    """Test observability metrics_topk tool via WebSocket."""
    if not websockets: print(f"Skip WS tool test (pip install websockets)"); return
    print(f"\nTesting Observability tools/call at {uri}")
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}))
        await ws.recv()
        await ws.send(json.dumps({"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"metrics_topk","arguments":{"type":"endpoints","k":3}}}))
        r=json.loads(await ws.recv())
        content=json.loads(r["result"]["content"][0]["text"])
        assert "results" in content, f"Expected 'results' in response, got: {content}"
        assert len(content["results"])>0, "Expected non-empty results"
        print(f"  metrics_topk -> {len(content['results'])} results")
    print(f"  PASS")

async def test_ws_tool_jira(uri):
    """Test Jira issue_search tool via WebSocket."""
    if not websockets: print(f"Skip WS tool test (pip install websockets)"); return
    print(f"\nTesting Jira tools/call at {uri}")
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}))
        await ws.recv()
        await ws.send(json.dumps({"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"issue_search","arguments":{"jql":"status = In Progress"}}}))
        r=json.loads(await ws.recv())
        content=json.loads(r["result"]["content"][0]["text"])
        assert "issues" in content, f"Expected 'issues' in response, got: {content}"
        assert len(content["issues"])>0, "Expected non-empty issues"
        print(f"  issue_search -> {len(content['issues'])} issues")
    print(f"  PASS")

async def main():
    h=sys.argv[1] if len(sys.argv)>1 else "localhost"
    await test_ws(f"ws://{h}:8001/","Observability"); await test_ws(f"ws://{h}:8002/","Jira")
    await test_sse(f"http://{h}:8001","Observability"); await test_sse(f"http://{h}:8002","Jira")
    await test_ws_tool_obs(f"ws://{h}:8001/"); await test_ws_tool_jira(f"ws://{h}:8002/")
    print("\nALL PASSED")

if __name__=="__main__": asyncio.run(main())
