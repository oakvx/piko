"""Role selection is explicit and cannot grant model output additional authority."""
import httpx
import pytest

from piko.api import create_app
from piko.contracts import Observation


class DesktopFixture:
    def observe(self, include_image=False):
        return Observation(executable="demo.exe", process_id=1, window_title="fixture")

    def emergency_release(self):
        pass


class ModelFixture:
    reasoning_model = ""
    vision_model = None

    async def models(self):
        return [{"name": "local-text"}, {"name": "local-vision"}]

    async def capabilities(self, model):
        return ["vision"] if model == "local-vision" else ["completion"]

    async def close(self):
        pass

    async def interpret(self, observation):
        return "only in tests"


@pytest.mark.asyncio
async def test_selection_requires_auth_and_available_capabilities(tmp_path):
    model = ModelFixture()
    app = create_app(token="s"*36, reasoning_model="", desktop=DesktopFixture(),
                     inference=model, root=tmp_path)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                base_url="http://test") as client:
        route = "/models/selection"
        assert (await client.post(route, json={"reasoning_model": "local-text"})).status_code == 401
        headers = {"Authorization": "Bearer " + "s"*36}
        assert (await client.post(route, headers=headers, json={"reasoning_model": "unknown"})).status_code == 422
        assert (await client.post(route, headers=headers, json={
            "reasoning_model": "local-text", "vision_model": "local-text"
        })).status_code == 422
        assert model.reasoning_model == ""
        accepted = await client.post(route, headers=headers, json={
            "reasoning_model": "local-text", "vision_model": "local-vision"
        })
        assert accepted.status_code == 200
        assert accepted.json() == {"reasoning": "local-text", "vision": "local-vision"}
        assert app.state.agent.vision is not None
