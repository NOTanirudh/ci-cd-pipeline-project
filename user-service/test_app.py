import app
import unittest
from unittest.mock import patch

def test_home():
    tester = app.app.test_client()
    response = tester.get('/')
    assert response.status_code == 200
    assert b'Hello from user-service!' in response.data

class TestCIIntegration(unittest.TestCase):
    def test_github_workflow_trigger_missing_token(self):
        with patch.dict('os.environ', {}, clear=True):
            success, msg = app.trigger_github_workflow('test/repo', 'main')
            self.assertFalse(success)
            self.assertEqual(msg, 'GitHub token not configured')

    def test_jenkins_job_trigger_missing_config(self):
        with patch.dict('os.environ', {}, clear=True):
            success, msg = app.trigger_jenkins_job('test/repo', 'main')
            self.assertFalse(success)
            self.assertEqual(msg, 'Jenkins URL/job not configured')

    @patch('requests.post')
    @patch('requests.get')
    def test_github_workflow_trigger_success(self, mock_get, mock_post):
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            'workflows': [{'id': 123}]
        }
        mock_post.return_value.status_code = 204

        with patch.dict('os.environ', {'GITHUB_TOKEN': 'test_token'}):
            success, msg = app.trigger_github_workflow('test/repo', 'main')
            self.assertTrue(success)
            self.assertEqual(msg, 'GitHub Actions workflow triggered successfully')

    @patch('requests.post')
    def test_jenkins_job_trigger_success(self, mock_post):
        mock_post.return_value.status_code = 201

        with patch.dict('os.environ', {
            'JENKINS_URL': 'http://jenkins',
            'JENKINS_JOB': 'test-job',
            'JENKINS_TOKEN': 'test-token'
        }):
            success, msg = app.trigger_jenkins_job('test/repo', 'main')
            self.assertTrue(success)
            self.assertEqual(msg, 'Jenkins job triggered successfully')
