# Cloud Janitor Agent with ADK

This is the companion repository for the [Introduction to Agents with ADK](https://ghacks.dev/hacks/adk-intro) gHack. It includes a basic agent that will be amended with each challenge to build a complete Agentic AI solution for cleaning up idle resources in Google Cloud Projects. The goal of the gHack is to introduce the various ADK concepts in a real-world scenario.

## Getting Started

Install dependencies:

```bash
pip install -r requirements.txt
```

Copy [`janitor/.env.example`](janitor/.env.example) to `janitor/.env` and fill in your GCP project and region:

```bash
cp janitor/.env.example janitor/.env
```

Then edit `janitor/.env` and set `GOOGLE_CLOUD_PROJECT` (and adjust `GOOGLE_CLOUD_LOCATION` if needed).

Alternatively, generate `janitor/.env` in one shot using your active `gcloud` config:

```bash
REGION=us-central1
cat > janitor/.env <<EOF
GOOGLE_GENAI_USE_VERTEXAI=TRUE
GOOGLE_CLOUD_PROJECT=$(gcloud config get-value project)
GOOGLE_CLOUD_LOCATION=$REGION
EOF
```

### Authentication (only if running outside Cloud Shell)

Cloud Shell is already authenticated. On a local machine, sign in and set the quota project so Vertex AI calls are billed and authorized against your lab project:

```bash
gcloud auth login
gcloud config set project <YOUR_GCP_PROJECT>
gcloud auth application-default login
gcloud auth application-default set-quota-project <YOUR_GCP_PROJECT>
```

### Run the agent

Launch the ADK dev web UI from the project root:

```bash
adk web
```

Then open <http://127.0.0.1:8000> and pick the `janitor` app.

The agent code lives in the [`janitor/`](janitor/) directory. Use [`reset-labels.sh`](reset-labels.sh) to reset resource labels between runs.
