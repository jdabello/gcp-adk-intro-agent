import os

GEMINI_MODEL = "gemini-2.5-flash"

# Where the label-management MCP server is reachable. Default assumes you're
# running `gcloud run services proxy mcp-server --region=us-central1 --port=8081`
# so the proxy handles Cloud Run auth for you. Override via .env if needed.
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "https://mcp-server-4dqzycbenq-uc.a.run.app")
