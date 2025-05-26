# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import unittest
from unittest.mock import patch, MagicMock

from src.tasks import get_or_create_sketch


class TestGetOrCreateSketch(unittest.TestCase):
    @patch("src.tasks.redis_client")
    def test_get_or_create_sketch_by_id(self, mock_redis_client):
        """Tests retrieving an existing sketch by its ID."""
        mock_timesketch_client = MagicMock()
        mock_sketch = MagicMock()
        mock_timesketch_client.get_sketch.return_value = mock_sketch

        sketch = get_or_create_sketch(
            mock_timesketch_client, mock_redis_client, sketch_id=123
        )

        mock_timesketch_client.get_sketch.assert_called_once_with(123)
        self.assertEqual(sketch, mock_sketch)

    @patch("src.tasks.redis_client")
    def test_get_or_create_sketch_by_id_not_found(self, mock_redis_client):
        """Tests handling the case where a sketch ID is not found."""
        mock_timesketch_client = MagicMock()
        mock_timesketch_client.get_sketch.return_value = None

        with self.assertRaises(RuntimeError) as context:
            get_or_create_sketch(
                mock_timesketch_client, mock_redis_client, sketch_id=123
            )

        self.assertIn("Failed to retrieve sketch with ID '123'", str(context.exception))

    @patch("src.tasks.redis_client")
    def test_get_or_create_sketch_by_name(self, mock_redis_client):
        """Tests creating a new sketch by a given name."""
        mock_timesketch_client = MagicMock()
        mock_sketch = MagicMock()
        mock_timesketch_client.create_sketch.return_value = mock_sketch

        sketch = get_or_create_sketch(
            mock_timesketch_client, mock_redis_client, sketch_name="Test Sketch"
        )

        mock_timesketch_client.create_sketch.assert_called_once_with("Test Sketch")
        self.assertEqual(sketch, mock_sketch)

    @patch("src.tasks.redis_client")
    def test_get_or_create_sketch_by_name_failure(self, mock_redis_client):
        """Tests handling the failure of sketch creation by name."""
        mock_timesketch_client = MagicMock()
        mock_timesketch_client.create_sketch.return_value = None

        with self.assertRaises(RuntimeError) as context:
            get_or_create_sketch(
                mock_timesketch_client, mock_redis_client, sketch_name="Test Sketch"
            )

        self.assertIn(
            "Failed to create sketch with name 'Test Sketch'", str(context.exception)
        )

    @patch("src.tasks.redis_client")
    def test_get_or_create_sketch_default_name_existing(self, mock_redis_client):
        """Tests retrieving an existing sketch using the default naming convention."""
        mock_timesketch_client = MagicMock()
        mock_sketch = MagicMock()
        mock_sketch.name = "openrelik-workflow-123"
        mock_timesketch_client.list_sketches.return_value = [mock_sketch]
        mock_redis_client.lock.return_value.__enter__ = MagicMock(return_value=None)
        mock_redis_client.lock.return_value.__exit__ = MagicMock(return_value=False)

        sketch = get_or_create_sketch(
            mock_timesketch_client, mock_redis_client, workflow_id="123"
        )

        self.assertEqual(sketch, mock_sketch)

    @patch("src.tasks.redis_client")
    def test_get_or_create_sketch_default_name_new(self, mock_redis_client):
        """Tests creating a new sketch using the default naming convention."""
        mock_timesketch_client = MagicMock()
        mock_sketch = MagicMock()
        mock_sketch.name = "openrelik-workflow-123"
        mock_timesketch_client.list_sketches.return_value = []
        mock_timesketch_client.create_sketch.return_value = mock_sketch
        mock_redis_client.lock.return_value.__enter__ = MagicMock(return_value=None)
        mock_redis_client.lock.return_value.__exit__ = MagicMock(return_value=False)

        sketch = get_or_create_sketch(
            mock_timesketch_client, mock_redis_client, workflow_id="123"
        )
        self.assertEqual(sketch, mock_sketch)
