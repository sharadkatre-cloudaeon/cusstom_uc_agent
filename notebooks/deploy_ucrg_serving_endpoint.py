# Databricks notebook source
# MAGIC %md
# MAGIC # Deploy UCRG Agent to Databricks Model Serving
# MAGIC
# MAGIC Packages the Use-Case Requirement Gathering agent as an MLflow **pyfunc** model
# MAGIC and deploys it to a **Model Serving endpoint**.
# MAGIC
# MAGIC **Protocol (stateless, multi-replica safe)**
# MAGIC 1. `action=start` → returns greeting + first question + `session_state`
# MAGIC 2. `action=send` + user `message` + prior `session_state` → next turn
# MAGIC 3. When `done=true`, parse `output_json` for SDD + scorecard markdown
# MAGIC
# MAGIC **Prerequisites**
# MAGIC - Unity Catalog model registry (`catalog.schema.model_name`)
# MAGIC - Secret scope with `ANTHROPIC_API_KEY` (for `--llm anthropic` behaviour)
# MAGIC - Upload this repo to Databricks (Repos or workspace files) so `ucrg/`, `data/`, `prompts/` are available

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1 · Configuration

# COMMAND ----------

dbutils.widgets.text("catalog", "main", "Unity Catalog")
dbutils.widgets.text("schema", "ucrg", "Schema")
dbutils.widgets.text("model_name", "ucrg_agent", "Registered model name")
dbutils.widgets.text("endpoint_name", "ucrg-agent", "Serving endpoint name")
dbutils.widgets.dropdown("llm_backend", "anthropic", ["anthropic", "mock"], "LLM backend")
dbutils.widgets.text("secret_scope", "ucrg", "Secret scope for ANTHROPIC_API_KEY")
dbutils.widgets.text("secret_key", "anthropic_api_key", "Secret key name")
dbutils.widgets.text("project_root", "", "Repo root (blank = auto-detect from notebook path)")

CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")
MODEL_NAME = dbutils.widgets.get("model_name")
ENDPOINT_NAME = dbutils.widgets.get("endpoint_name")
LLM_BACKEND = dbutils.widgets.get("llm_backend")
SECRET_SCOPE = dbutils.widgets.get("secret_scope")
SECRET_KEY = dbutils.widgets.get("secret_key")

FULL_MODEL_NAME = f"{CATALOG}.{SCHEMA}.{MODEL_NAME}"
print(f"Model: {FULL_MODEL_NAME}")
print(f"Endpoint: {ENDPOINT_NAME}")
print(f"Backend: {LLM_BACKEND}")
print("Project root: auto-detected after pip install (cell 3)")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2 · Install dependencies
# MAGIC
# MAGIC Installs only packages not bundled on the cluster runtime. Avoid upgrading
# MAGIC `pandas` / `mlflow` here — that triggers a Python restart and can break
# MAGIC pre-installed notebook dependencies (protobuf, numpy, etc.).

# COMMAND ----------

# MAGIC %pip install anthropic>=0.39 requests>=2.31 --quiet
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3 · Reload config (required after `restartPython`)
# MAGIC
# MAGIC Widget values survive a restart; Python variables do not. Re-read them here
# MAGIC before any downstream cells.

# COMMAND ----------

import os
from pathlib import Path


def _resolve_project_root(widget_value: str) -> str:
    """Resolve repo root from widget override or this notebook's path in the workspace."""
    cleaned = (widget_value or "").strip()
    if cleaned:
        root = Path(cleaned)
        if (root / "ucrg").is_dir():
            return str(root)
        raise FileNotFoundError(
            f"project_root widget is {root!s} but ucrg/ was not found there. "
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
        if (cursor / "ucrg").is_dir() and (cursor / "data" / "ucrg_engine.json").is_file():
            return str(cursor)
        if cursor.parent == cursor:
            break
        cursor = cursor.parent

    raise FileNotFoundError(
        f"Could not auto-detect repo root from notebook path {nb_path!r}. "
        "Set project_root to your Repo path, e.g. "
        "/Workspace/Repos/<user-or-org>/cusstom_uc_agent"
    )


CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")
MODEL_NAME = dbutils.widgets.get("model_name")
ENDPOINT_NAME = dbutils.widgets.get("endpoint_name")
LLM_BACKEND = dbutils.widgets.get("llm_backend")
SECRET_SCOPE = dbutils.widgets.get("secret_scope")
SECRET_KEY = dbutils.widgets.get("secret_key")
PROJECT_ROOT = _resolve_project_root(dbutils.widgets.get("project_root"))

FULL_MODEL_NAME = f"{CATALOG}.{SCHEMA}.{MODEL_NAME}"
print(f"Project root: {PROJECT_ROOT}")
print(f"Model: {FULL_MODEL_NAME}")
print(f"Endpoint: {ENDPOINT_NAME}")
print(f"Backend: {LLM_BACKEND}")
assert os.path.isdir(PROJECT_ROOT), f"Project root not found: {PROJECT_ROOT}"

if LLM_BACKEND == "anthropic":
    os.environ["ANTHROPIC_API_KEY"] = dbutils.secrets.get(
        scope=SECRET_SCOPE, key=SECRET_KEY
    )

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4 · Smoke-test the serving wrapper locally

# COMMAND ----------

import os
import sys

sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

import pandas as pd
from ucrg.serving import UCRGServingModel

class _Ctx:
    artifacts = {
        "ucrg_engine": f"{PROJECT_ROOT}/data/ucrg_engine.json",
        "system_prompt": f"{PROJECT_ROOT}/prompts/system_prompt.md",
    }
    model_config = {"backend": LLM_BACKEND}

model = UCRGServingModel()
model.load_context(_Ctx())

start = model.predict(_Ctx(), pd.DataFrame([{
    "action": "start",
    "session_id": "smoke-test",
    "message": "",
    "session_state": "",
}]))
print(start.iloc[0]["message"][:200], "…")
assert start.iloc[0]["session_state"], "expected session_state blob"
print("Smoke test OK")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5 · Log & register the model (Unity Catalog)

# COMMAND ----------

import mlflow
from mlflow.models import infer_signature
from mlflow.tracking import MlflowClient

mlflow.set_registry_uri("databricks-uc")

input_example = pd.DataFrame([{
    "action": "start",
    "session_id": "example",
    "message": "",
    "session_state": "",
}])

output_example = pd.DataFrame([{
    "session_id": "example",
    "message": "Hi! …",
    "done": False,
    "session_state": "{}",
    "output_json": "",
    "error": "",
}])

signature = infer_signature(input_example, output_example)

with mlflow.start_run(run_name="ucrg-serving") as run:
    logged = mlflow.pyfunc.log_model(
        artifact_path="model",
        python_model=UCRGServingModel(),
        code_paths=[
            f"{PROJECT_ROOT}/ucrg",
            f"{PROJECT_ROOT}/data",
            f"{PROJECT_ROOT}/prompts",
        ],
        artifacts={
            "ucrg_engine": f"{PROJECT_ROOT}/data/ucrg_engine.json",
            "system_prompt": f"{PROJECT_ROOT}/prompts/system_prompt.md",
        },
        pip_requirements=[
            "anthropic>=0.39",
            "pandas>=2.0",
        ],
        signature=signature,
        input_example=input_example,
        model_config={"backend": LLM_BACKEND},
    )
    run_id = run.info.run_id

model_uri = f"runs:/{run_id}/model"
registered = mlflow.register_model(model_uri, FULL_MODEL_NAME)
version = registered.version
print(f"Registered {FULL_MODEL_NAME} version {version}")

client = MlflowClient()
client.set_registered_model_alias(FULL_MODEL_NAME, "champion", version)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6 · Create or update the serving endpoint
# MAGIC
# MAGIC If `version` is missing (kernel restart or cell 5 skipped), resolves the
# MAGIC `champion` alias or latest registered version from Unity Catalog.

# COMMAND ----------

import mlflow
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import EndpointCoreConfigInput, ServedEntityInput
from mlflow.tracking import MlflowClient

mlflow.set_registry_uri("databricks-uc")

if "FULL_MODEL_NAME" not in globals():
    CATALOG = dbutils.widgets.get("catalog")
    SCHEMA = dbutils.widgets.get("schema")
    MODEL_NAME = dbutils.widgets.get("model_name")
    ENDPOINT_NAME = dbutils.widgets.get("endpoint_name")
    LLM_BACKEND = dbutils.widgets.get("llm_backend")
    SECRET_SCOPE = dbutils.widgets.get("secret_scope")
    SECRET_KEY = dbutils.widgets.get("secret_key")
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

w = WorkspaceClient()

served_entity = ServedEntityInput(
    entity_name=FULL_MODEL_NAME,
    entity_version=version,
    workload_size="Small",
    scale_to_zero_enabled=True,
    environment_vars={
        "UCRG_LLM_BACKEND": LLM_BACKEND,
        "ANTHROPIC_API_KEY": f"{{{{secrets/{SECRET_SCOPE}/{SECRET_KEY}}}}}",
    },
)

endpoint_config = EndpointCoreConfigInput(served_entities=[served_entity])

existing = [ep for ep in w.serving_endpoints.list() if ep.name == ENDPOINT_NAME]
if existing:
    print(f"Updating endpoint {ENDPOINT_NAME} → v{version}")
    w.serving_endpoints.update_config_and_wait(
        name=ENDPOINT_NAME,
        served_entities=endpoint_config.served_entities,
    )
else:
    print(f"Creating endpoint {ENDPOINT_NAME}")
    w.serving_endpoints.create_and_wait(
        name=ENDPOINT_NAME,
        config=endpoint_config,
    )

print("Endpoint ready:", ENDPOINT_NAME)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7 · Invoke the endpoint (REST)

# COMMAND ----------

import json
import requests

host = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiUrl().get()
token = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()
url = f"{host}/serving-endpoints/{ENDPOINT_NAME}/invocations"

headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

def invoke(records: list[dict]) -> list[dict]:
    payload = {"dataframe_records": records}
    resp = requests.post(url, headers=headers, json=payload, timeout=120)
    resp.raise_for_status()
    body = resp.json()
    preds = body.get("predictions", body)
    if isinstance(preds, dict) and "data" in preds:
        cols = preds["columns"]
        return [dict(zip(cols, row)) for row in preds["data"]]
    return preds

# Start interview
turn = invoke([{
    "action": "start",
    "session_id": "notebook-demo",
    "message": "",
    "session_state": "",
}])[0]
print("Agent:", turn["message"][:300], "…\n")

session_state = turn["session_state"]

# Example answer — replace with real user input in your app
turn = invoke([{
    "action": "send",
    "session_id": "notebook-demo",
    "message": "I want a chatbot that answers HR policy questions from our internal wiki.",
    "session_state": session_state,
}])[0]
print("Agent:", turn["message"][:300], "…")
print("done:", turn["done"])

# COMMAND ----------

# MAGIC %md
# MAGIC ## Client integration notes
# MAGIC
# MAGIC | Field | Description |
# MAGIC |---|---|
# MAGIC | `action` | `start` · `send` · `reset` |
# MAGIC | `session_id` | Your conversation / user correlation id |
# MAGIC | `message` | User reply (empty for `start`) |
# MAGIC | `session_state` | Opaque JSON string — **store client-side** and send back each turn |
# MAGIC | `output_json` | When `done=true`, JSON with `sdd` and `scorecard` markdown strings |
# MAGIC
# MAGIC Use `mock` backend for integration tests without an API key. Switch widget to
# MAGIC `anthropic` in production and ensure the secret is mounted on the endpoint.
