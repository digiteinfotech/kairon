import pytest
from trainer import app

@pytest.fixture(name='testapp')
def _test_app():
  return app

@pytest.mark.asyncio
async def test_get_intent_list(testapp):
    test_client = testapp.test_client()
    expected = ["about", "agile", "buySK", "careers", "challenge_bot", "contact", "demo", "feedback", "getstarted", "goodbye", "greeting", "how_are_you", "integration", "kanban", "kanbantool", "location_query", "login", "mobapp", "need_advice", "pricing", "products", "resources", "sEnt_updates", "safetool", "scrumtool", "selfhosted", "testimonials", "thanking", "training", "trial", "webinar", "test2", "Reject", "about organization"]
    response = await test_client.get('/getIntentList')
    assert response.status_code == 200
    result = await response.get_json()
    assert all( intent in expected for intent in result )


@pytest.mark.asyncio
async def test_add_intent(testapp):
    test_client = testapp.test_client()
    data = {'query': 'Hi'}
    expected = {"intent": "greeting", "questions": ["hey", "hello", "hi", "good morning", "good evening", "hey there", "sup", "yo", "wassup", "whats up", "bonjour"], "answer": "Hey! How can I help you? &#128512"}
    response = await test_client.post('/predict', json=data)
    assert response.status_code == 200
    result = await response.get_json()
    assert expected == result
