"""The service half of the model pills: which model ANSWERED, and whether it searched.

The console shows two pills at the top right: the model that answered the last request, and
``Search`` when that answer used an online search tool. Both come from response headers the kit
emits (``install_answer_provenance`` in ``api/app.py``) for whatever the model adapters NOTED as
they called. Before a request is answered the pill shows ``generator_model`` from ``/healthz``,
so that value must be the model the bound adapter answers as, never one a configuration flag
names while the adapter calls another.

The model port here is the narration port (classify an intake, narrate a draft). Under ``local``
the deterministic narrator answers and notes its stub name, which is what ``generator_model``
reports, so the pill reads the same before and after the first answer.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from hex_service_kit import provenance

from disputes_chargebacks_manager import config
from disputes_chargebacks_manager.adapters.local.narration import LocalNarrator

from tests import REPO_ROOT

ANSWERED_BY = "x-answered-by"
SEARCH_USED = "x-search-used"


@pytest.fixture(autouse=True)
def _local_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    """CI targets run with no profile exported; this suite states the one it proves."""
    monkeypatch.setenv("DISPUTES_PROFILE", "local")


def _intake(api_client: TestClient) -> dict[str, str]:
    response = api_client.post(
        "/v1/intake",
        json={"conversation_ref": "conv-complaint-003"},
        headers={"X-Dev-Persona": "auditor"},
    )
    assert response.status_code == 200, response.text
    return dict(response.headers)


def test_the_local_narrator_answers_as_the_model_the_pill_already_names(
    api_client: TestClient,
) -> None:
    headers = _intake(api_client)
    assert headers[ANSWERED_BY] == config.LOCAL_STUB_MODEL
    assert headers[ANSWERED_BY] == api_client.get("/healthz").json()["generator_model"]
    # No search tool is attached to the stub, so the Search pill stays hidden.
    assert SEARCH_USED not in headers


def test_a_call_that_searched_says_so_and_the_next_one_does_not_inherit_it(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = LocalNarrator.classify

    def searching_classify(self: LocalNarrator, text: str, *, categories: tuple[str, ...]) -> str:
        provenance.note_search()
        return original(self, text, categories=categories)

    monkeypatch.setattr(LocalNarrator, "classify", searching_classify)
    headers = _intake(api_client)
    assert headers[SEARCH_USED] == "true"
    assert headers[ANSWERED_BY] == config.LOCAL_STUB_MODEL
    monkeypatch.setattr(LocalNarrator, "classify", original)
    assert SEARCH_USED not in _intake(api_client)


def test_a_request_that_called_no_model_names_none(api_client: TestClient) -> None:
    """Nothing noted, nothing sent: the pill never invents a model that did not answer."""
    response = api_client.get("/healthz")
    assert response.status_code == 200
    assert ANSWERED_BY not in response.headers
    assert SEARCH_USED not in response.headers


def test_generator_model_is_the_setting_the_adapter_reads_and_no_flag_swaps_it() -> None:
    """The latent false banner: a flag that moved the pill but not the model that answered."""
    models = SimpleNamespace(
        reasoning="the-model-the-adapter-calls",
        hard_reasoning="a-model-nobody-calls",
        use_hard_reasoning=True,
    )
    named = config._model_from_settings(SimpleNamespace(models=models), "models.reasoning")
    assert named == "the-model-the-adapter-calls"


def test_the_hard_reasoning_flag_does_not_exist() -> None:
    settings_file = (REPO_ROOT / "config" / "settings.yaml").read_text(encoding="utf-8")
    assert "use_hard_reasoning" not in settings_file
    for source in sorted((REPO_ROOT / "src").rglob("*.py")):
        assert "use_hard_reasoning" not in source.read_text(encoding="utf-8"), source
