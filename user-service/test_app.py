import app

def test_home():
    tester = app.app.test_client()
    response = tester.get('/')
    assert response.status_code == 200
    assert b'Hello from user-service!' in response.data
