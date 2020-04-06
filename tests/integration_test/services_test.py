import pytest


class RestServicesTest:

    @pytest.mark.asyncio
    async def test_add_intent(self, app):
        test_client = app.test_client()
        data = {'query': 'Hi'}
        response = await test_client.post('/predict', json=data)
        assert response.status_code == 200
        result = await response.get_json()
        print(result)
        assert result == []
