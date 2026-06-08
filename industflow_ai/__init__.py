"""industflow_ai — AI intelligence layer on top of the Industflow data slice.

Built on the existing `industflow_starter` data layer (db + queries + importer).
Provides: an Ollama-backed agent for natural-language Q&A over production data,
an automatic shift/trend report narrator, a sandboxed read-only aggregation tool,
an audit log, and a scheduler for continuous analysis.
"""
