# Databricks notebook source
# MAGIC %md
# MAGIC # Deploy UCRG Agent to Mosaic AI (Playground + Review App)
# MAGIC
# MAGIC Packages the Use-Case Requirement Gathering agent as an MLflow **ChatAgent**
# MAGIC and deploys via `databricks.agents.deploy()` so it appears in **Mosaic AI → Playground**.
# MAGIC
# MAGIC **Protocol**
# MAGIC - Playground / Review App: OpenAI-style `messages[]` (state replayed from history)
# MAGIC - Production frontend: send `custom_inputs.session_state` from prior `custom_outputs`
# MAGIC - When `custom_outputs.done=true`, parse `custom_outputs.output_json` for SDD + scorecard
# MAGIC
# MAGIC **Prerequisites**
# MAGIC - Unity Catalog model registry (`catalog.schema.model_name`)
# MAGIC - A Foundation Model serving endpoint (e.g. `databricks-claude-opus-4-6`) when using `databricks` backend
# MAGIC - Secret scope with `ANTHROPIC_API_KEY` only when using external `anthropic` backend
# MAGIC - Upload this repo to Databricks (Repos) so `ucrg/`, `data/`, `prompts/`, `databricks_agent.py` exist
# MAGIC - DBR 15.4 ML LTS or newer
# MAGIC
# MAGIC **Auth pattern:** `databricks` backend declares the FM endpoint as a `DatabricksServingEndpoint`
# MAGIC resource at log time — deployed agents get automatic M2M OAuth passthrough (no PAT / apiToken).

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1 · Configuration

# COMMAND ----------

dbutils.widgets.text("catalog", "ai_build", "Unity Catalog")
dbutils.widgets.text("schema", "atlas_serve_build", "Schema")
dbutils.widgets.text("model_name", "ucrg_agent", "Registered model name")
dbutils.widgets.dropdown("llm_backend", "databricks", ["databricks", "anthropic", "mock"], "LLM backend")
dbutils.widgets.text("llm_endpoint", "databricks-claude-opus-4-6", "FM serving endpoint (databricks backend)")
dbutils.widgets.text("secret_scope", "ucrg", "Secret scope for ANTHROPIC_API_KEY")
dbutils.widgets.text("secret_key", "anthropic_api_key", "Secret key name")
dbutils.widgets.text("project_root", "", "Repo root (blank = auto-detect from notebook path)")
dbutils.widgets.dropdown("scale_to_zero", "true", ["true", "false"], "Scale endpoint to zero")

CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")
MODEL_NAME = dbutils.widgets.get("model_name")
LLM_BACKEND = dbutils.widgets.get("llm_backend")
LLM_ENDPOINT = dbutils.widgets.get("llm_endpoint")
SECRET_SCOPE = dbutils.widgets.get("secret_scope")
SECRET_KEY = dbutils.widgets.get("secret_key")
SCALE_TO_ZERO = dbutils.widgets.get("scale_to_zero").lower() == "true"

FULL_MODEL_NAME = f"{CATALOG}.{SCHEMA}.{MODEL_NAME}"
print(f"Model: {FULL_MODEL_NAME}")
print(f"Backend: {LLM_BACKEND}")
if LLM_BACKEND == "databricks":
    print(f"LLM endpoint: {LLM_ENDPOINT}")
print(f"Scale to zero: {SCALE_TO_ZERO}")
print("Project root: auto-detected after pip install (cell 3)")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2 · Install dependencies

# COMMAND ----------

# MAGIC %pip install -U \
# MAGIC   "anthropic>=0.39" \
# MAGIC   "mlflow[databricks]>=2.20" \
# MAGIC   "databricks-agents>=0.16" \
# MAGIC   "databricks-langchain>=0.4" \
# MAGIC   "langchain-core>=0.3" \
# MAGIC   "pydantic>=2.9" \
# MAGIC   --quiet
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3 · Reload config (required after `restartPython`)

# COMMAND ----------

import os
import sys
from pathlib import Path


def _resolve_project_root(widget_value: str) -> str:
    """Resolve repo root from widget override or this notebook's path in the workspace."""
    cleaned = (widget_value or "").strip()
    if cleaned:
        root = Path(cleaned)
        if (root / "ucrg").is_dir() and (root / "databricks_agent.py").is_file():
            return str(root)
        raise FileNotFoundError(
            f"project_root widget is {root!s} but ucrg/ or databricks_agent.py was not found. "
            "Clear the widget to auto-detect, or set the correct Databricks Repo path."
        )

    nb_path = (
        dbutils.notebook.entry_point.getDbutils()
        .notebook()
        .getContext()
        .notebookPath()
        .get()
    )
    if not nb_path.startswith("/Workspace"):
        nb_path = f"/Workspace{nb_path}"

    cursor = Path(nb_path).parent
    for _ in range(6):
        if (
            (cursor / "ucrg").is_dir()
            and (cursor / "data" / "ucrg_engine.json").is_file()
            and (cursor / "databricks_agent.py").is_file()
        ):
            return str(cursor)
        if cursor.parent == cursor:
            break
        cursor = cursor.parent

    raise FileNotFoundError(
        f"Could not auto-detect repo root from notebook path {nb_path!r}. "
        "Set project_root to your Repo path, e.g. "
        "/Workspace/Repos/<user-or-org>/dta-ai-usecase-requirement-gathering-agent/ucrg-agent"
    )


CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")
MODEL_NAME = dbutils.widgets.get("model_name")
LLM_BACKEND = dbutils.widgets.get("llm_backend")
LLM_ENDPOINT = dbutils.widgets.get("llm_endpoint")
SECRET_SCOPE = dbutils.widgets.get("secret_scope")
SECRET_KEY = dbutils.widgets.get("secret_key")
SCALE_TO_ZERO = dbutils.widgets.get("scale_to_zero").lower() == "true"
PROJECT_ROOT = _resolve_project_root(dbutils.widgets.get("project_root"))

FULL_MODEL_NAME = f"{CATALOG}.{SCHEMA}.{MODEL_NAME}"
print(f"Project root: {PROJECT_ROOT}")
print(f"Model: {FULL_MODEL_NAME}")
print(f"Backend: {LLM_BACKEND}")
if LLM_BACKEND == "databricks":
    print(f"LLM endpoint: {LLM_ENDPOINT}")
assert os.path.isdir(PROJECT_ROOT), f"Project root not found: {PROJECT_ROOT}"

os.chdir(PROJECT_ROOT)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ["UCRG_LLM_BACKEND"] = LLM_BACKEND
if LLM_BACKEND == "databricks":
    os.environ["DATABRICKS_LLM_ENDPOINT"] = LLM_ENDPOINT
elif LLM_BACKEND == "anthropic":
    os.environ["ANTHROPIC_API_KEY"] = dbutils.secrets.get(
        scope=SECRET_SCOPE, key=SECRET_KEY
    )

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4 · Smoke-test the ChatAgent locally

# COMMAND ----------

from databricks_agent import AGENT
from mlflow.types.agent import ChatAgentMessage

resp = AGENT.predict(
    messages=[ChatAgentMessage(role="user", content="hi")],
    custom_inputs={},
)
print("Assistant:", resp.messages[-1].content[:300], "…")
assert resp.custom_outputs.get("session_state"), "expected session_state in custom_outputs"
print("Smoke test OK")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5 · Log & register the model (Unity Catalog)

# COMMAND ----------

import mlflow
from mlflow.models.resources import DatabricksServingEndpoint
from mlflow.tracking import MlflowClient
from pkg_resources import get_distribution

mlflow.set_registry_uri("databricks-uc")

pip_requirements = [
    f"mlflow=={get_distribution('mlflow').version}",
    "databricks-agents",
    "databricks-langchain>=0.4",
    "langchain-core>=0.3",
    "anthropic>=0.39",
    "pydantic>=2.9",
]

resources = []
if LLM_BACKEND == "databricks":
    resources = [DatabricksServingEndpoint(endpoint_name=LLM_ENDPOINT)]
    print(f"Declaring resource dependency: {LLM_ENDPOINT}")

with mlflow.start_run(run_name="ucrg-chat-agent") as run:
    logged = mlflow.pyfunc.log_model(
        artifact_path="agent",
        python_model="databricks_agent.py",
        code_paths=[
            f"{PROJECT_ROOT}/ucrg",
            f"{PROJECT_ROOT}/data",
            f"{PROJECT_ROOT}/prompts",
        ],
        pip_requirements=pip_requirements,
        resources=resources,
    )
    run_id = run.info.run_id

model_uri = logged.model_uri
registered = mlflow.register_model(model_uri, FULL_MODEL_NAME)
version = registered.version
print(f"Registered {FULL_MODEL_NAME} version {version}")

client = MlflowClient()
client.set_registered_model_alias(FULL_MODEL_NAME, "champion", version)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6 · Deploy as a Mosaic AI Agent (Playground + Review App)
# MAGIC
# MAGIC Uses `databricks.agents.deploy()` — **required** for Playground visibility.
# MAGIC A plain Model Serving endpoint (pyfunc DataFrame protocol) does not appear there.

# COMMAND ----------

from databricks import agents

if "FULL_MODEL_NAME" not in globals():
    CATALOG = dbutils.widgets.get("catalog")
    SCHEMA = dbutils.widgets.get("schema")
    MODEL_NAME = dbutils.widgets.get("model_name")
    LLM_BACKEND = dbutils.widgets.get("llm_backend")
    LLM_ENDPOINT = dbutils.widgets.get("llm_endpoint")
    SECRET_SCOPE = dbutils.widgets.get("secret_scope")
    SECRET_KEY = dbutils.widgets.get("secret_key")
    SCALE_TO_ZERO = dbutils.widgets.get("scale_to_zero").lower() == "true"
    FULL_MODEL_NAME = f"{CATALOG}.{SCHEMA}.{MODEL_NAME}"


def _resolve_model_version(model_name: str) -> str:
    client = MlflowClient()
    try:
        return str(client.get_model_version_by_alias(model_name, "champion").version)
    except Exception:
        versions = client.search_model_versions(f"name='{model_name}'")
        if not versions:
            raise RuntimeError(
                f"No registered versions for {model_name}. Run section 5 first."
            )
        return str(max(versions, key=lambda mv: int(mv.version)).version)


if "version" not in globals():
    version = _resolve_model_version(FULL_MODEL_NAME)
    print(f"Resolved model version: {version}")

env_vars = {"UCRG_LLM_BACKEND": LLM_BACKEND}
if LLM_BACKEND == "databricks":
    env_vars["DATABRICKS_LLM_ENDPOINT"] = LLM_ENDPOINT
elif LLM_BACKEND == "anthropic":
    env_vars["ANTHROPIC_API_KEY"] = f"{{{{secrets/{SECRET_SCOPE}/{SECRET_KEY}}}}}"

deployment = agents.deploy(
    model_name=FULL_MODEL_NAME,
    model_version=int(version),
    scale_to_zero=SCALE_TO_ZERO,
    environment_vars=env_vars,
    tags={"project": "ucrg", "stage": "prototype"},
)

print("Serving endpoint:", deployment.endpoint_name)
print("Review app URL:  ", deployment.review_app_url)
print()
print("Open the Review App URL above to chat with the agent.")
print("Or test from Playground: Mosaic AI → Playground → select the endpoint above.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7 · Smoke-test the deployed endpoint
# MAGIC
# MAGIC Uses ambient notebook credentials via MLflow Deployments SDK — no captured apiToken.

# COMMAND ----------

from mlflow.deployments import get_deploy_client

client = get_deploy_client("databricks")
out = client.predict(
    endpoint=deployment.endpoint_name,
    inputs={
        "messages": [{"role": "user", "content": "hi"}],
        "custom_inputs": {},
    },
)
print(out)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Client integration notes
# MAGIC
# MAGIC | Field | Description |
# MAGIC |---|---|
# MAGIC | `messages` | OpenAI-style chat history (`role` + `content`) |
# MAGIC | `custom_inputs.session_state` | Opaque JSON string from prior `custom_outputs` — **send each turn in production** |
# MAGIC | `custom_outputs.done` | `true` when interview is complete |
# MAGIC | `custom_outputs.output_json` | When done, JSON with `sdd` and `scorecard` markdown strings |
# MAGIC
# MAGIC **Playground flow:** type `hi` to start → answer each question in turn. State is
# MAGIC reconstructed by replaying message history (no `session_state` needed).
# MAGIC
# MAGIC Use `mock` backend for integration tests without any LLM call.
# MAGIC
# MAGIC **LLM auth by backend:**
# MAGIC | Backend | Dev (notebook) | Prod (deployed agent) |
# MAGIC |---|---|---|
# MAGIC | `databricks` | Notebook identity via `ChatDatabricks` | Automatic passthrough — declare `DatabricksServingEndpoint` in `resources` |
# MAGIC | `anthropic` | Secret scope / env var | Secret mounted on endpoint via `environment_vars` |
# MAGIC | `mock` | No auth | No auth |
