"""Opt-in paid-provider connectivity smoke. Not a substitute for business-policy evaluation."""

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config import settings
from app.provider import answer, embeddings

if settings().model_mode != "openai":
    raise SystemExit(
        "Set MODEL_MODE=openai and configure MODEL_API_KEY before this opt-in test."
    )
vectors = embeddings(["Shipping takes 3 business days."])
assert len(vectors[0]) == settings().embedding_dimensions
source = SimpleNamespace(id="smoke-evidence", text="Shipping takes 3 business days.")
result = answer("How long does shipping take?", [], [source])
assert result["citations"] == [source.id], (
    "Provider did not return the supplied citation identifier"
)
assert "3" in result["answer"], "Inspect provider output against the test policy"
print(
    "PASS: real-provider embedding and grounded chat smoke (provider calls may incur charges)"
)
