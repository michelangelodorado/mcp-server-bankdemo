# MCP Banking Demo

## Start
```
cd mcp-server-bankdemo && docker compose up --build
```

## LibreChat config (librechat.yaml)
```yaml
mcpSettings:
  allowedDomains:
    - "10.1.10.102"
mcpServers:
  observability:
    type: sse
    url: http://10.1.10.102:8001/sse
    timeout: 30000
  jira:
    type: sse
    url: http://10.1.10.102:8002/sse
    timeout: 30000
```

## Test
```
pip install websockets httpx
python test_mcp.py 10.1.10.102
```
