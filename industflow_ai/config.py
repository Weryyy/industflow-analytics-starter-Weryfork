"""Central configuration for the AI layer. Everything overridable by env var."""
from __future__ import annotations

import os

# --- LLM (Ollama, local-first per the project brief) ---
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
# qwen3:14b fits fully in 16GB VRAM (RTX 5080) and has native tool-calling.
AGENT_MODEL = os.environ.get("AGENT_MODEL", "qwen3:14b-q4_K_M")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "bge-m3:latest")
LLM_TEMPERATURE = float(os.environ.get("LLM_TEMPERATURE", "0.1"))

# Language of generated reports/answers. Project default is English.
REPORT_LANG = os.environ.get("REPORT_LANG", "en")  # "en" | "es"

# --- Data ---
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/mip")

# --- Safety / sandbox ---
MAX_AGGREGATE_RESULTS = int(os.environ.get("MAX_AGGREGATE_RESULTS", "200"))
AGGREGATE_TIMEOUT_MS = int(os.environ.get("AGGREGATE_TIMEOUT_MS", "5000"))

# Collections the agent is allowed to read (the data layer only — never ai.*).
READABLE_COLLECTIONS = {
    "products",
    "products.steps",
    "products.defect_history",
    "workshifts",
    "lines",
    "stations",
    "defectcode",
}

# --- Audit / reports persistence ---
AUDIT_COLLECTION = "ai.audit"
REPORTS_COLLECTION = "ai.reports"

# --- Baseline windows (days) ---
SHIFT_BASELINE_DAYS = int(os.environ.get("SHIFT_BASELINE_DAYS", "7"))
TREND_BASELINE_DAYS = int(os.environ.get("TREND_BASELINE_DAYS", "30"))

# --- Anomaly detection (scrap-rate z-score vs the trend baseline) ---
ANOMALY_Z_THRESHOLD = float(os.environ.get("ANOMALY_Z_THRESHOLD", "2.0"))
ANOMALY_RECENT_DAYS = int(os.environ.get("ANOMALY_RECENT_DAYS", "3"))
ANOMALY_MIN_TOTAL = int(os.environ.get("ANOMALY_MIN_TOTAL", "20"))
