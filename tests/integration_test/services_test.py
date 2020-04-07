import pytest
from trainer import app

@pytest.fixture(name='testapp')
def _test_app():
  return app

@pytest.mark.asyncio
async def test_get_intent_list(testapp):
    test_client = testapp.test_client()
    response = await test_client.get('/getIntentList')
    assert response.status_code == 200
    result = await response.get_json()
    print(result)
    assert result == []


@pytest.mark.asyncio
async def test_add_intent(testapp):
    test_client = testapp.test_client()
    data = {'query': 'Hi'}
    response = await test_client.post('/predict', json=data)
    assert response.status_code == 200
    result = await response.get_json()
    print(result)
    assert result == []
