import os

GEMINI_MODEL = "gemini-2.5-flash"

# Where the label-management MCP server is reachable. Default assumes you're
# running `gcloud run services proxy mcp-server --region=us-central1 --port=8081`
# so the proxy handles Cloud Run auth for you. Override via .env if needed.
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://127.0.0.1:8081/")

# A2A cleaner server. Same auth situation as MCP: behind Cloud Run IAM, so
# either run `gcloud run services proxy a2a-server --region=us-central1
# --port=8082` and keep this default, or override with the full public URL
# plus a valid id-token mechanism.
A2A_SERVER_URL = os.getenv("A2A_SERVER_URL", "http://127.0.0.1:8080")

# Gemini Decisions API (gemini-decision-1). Only available through AI Studio
# with an API key for now (no Vertex AI support yet), so this one call uses
# GEMINI_API_KEY while the rest of the app stays on Vertex.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DECISION_MODEL = "gemini-decision-1"
DECISIONS_API_URL = os.getenv(
    "DECISIONS_API_URL", "https://generativelanguage.googleapis.com/v1beta/decisions"
)
# VMs whose calibrated "is idle" probability is at or above this are passed on
# to the labeler.
IDLE_PROBABILITY_THRESHOLD = float(os.getenv("IDLE_PROBABILITY_THRESHOLD", "0.7"))
