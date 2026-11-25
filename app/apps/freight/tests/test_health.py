from unittest.mock import MagicMock, patch

from django.conf import settings
from django.test import SimpleTestCase, TestCase
from django.urls import reverse


class HealthCheckTests(SimpleTestCase):
    def test_application_version_comes_from_version_file(self):
        version_file = settings.BASE_DIR / 'VERSION'
        self.assertEqual(settings.APP_VERSION, version_file.read_text(encoding='utf-8').strip())

    def test_health_check(self):
        response = self.client.get(reverse('health_check'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {'status': 'ok', 'service': 'calc', 'version': settings.APP_VERSION},
        )


class ReadinessCheckTests(TestCase):
    def test_ready_when_database_is_available_and_migrations_are_current(self):
        response = self.client.get(reverse('readiness_check'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            'status': 'ready',
            'service': 'calc',
            'version': settings.APP_VERSION,
            'checks': {'database': 'ok', 'migrations': 'ok'},
        })

    @patch('config.urls.MigrationExecutor')
    def test_not_ready_when_migrations_are_pending(self, executor_class):
        executor = executor_class.return_value
        executor.loader.graph.leaf_nodes.return_value = [('audit', '0004_remove_alertdelivery')]
        executor.migration_plan.return_value = [MagicMock()]

        response = self.client.get(reverse('readiness_check'))

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['status'], 'not_ready')
        self.assertEqual(response.json()['checks'], {
            'database': 'ok',
            'migrations': 'pending',
        })

    @patch('config.urls.connection.cursor')
    def test_not_ready_without_exposing_database_error(self, cursor):
        cursor.side_effect = RuntimeError('secret database detail')

        response = self.client.get(reverse('readiness_check'))

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['status'], 'not_ready')
        self.assertEqual(response.json()['checks'], {
            'database': 'unavailable',
            'migrations': 'unknown',
        })
        self.assertNotContains(response, 'secret database detail', status_code=503)
