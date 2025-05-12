# Copyright 2024 Google LLC
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

import os

from openrelik_worker_common.task_utils import create_task_result, get_input_files
from timesketch_api_client import client as timesketch_client
from timesketch_import_client import importer

from .app import celery, redis_client


def get_or_create_sketch(
    timesketch_api_client,
    redis_client,
    sketch_id=None,
    sketch_name=None,
    workflow_id=None,
):
    """
    Retrieves or creates a sketch, handling locking if needed.
    This uses Redis distrubuted lock to avoid race conditions.

    Args:
        client: Timesketch API client.
        redis_client: Redis client.
        sketch_id: ID of the sketch to retrieve.
        sketch_name: Name of the sketch to create.
        workflow_id: ID of the workflow.

    Returns:
        Timesketch sketch object or None if failed
    """
    sketch = None

    if sketch_id:
        sketch = timesketch_api_client.get_sketch(int(sketch_id))
    elif sketch_name:
        sketch = timesketch_api_client.create_sketch(sketch_name)
    else:
        sketch_name = f"openrelik-workflow-{workflow_id}"
        # Prevent multiple distributed workers from concurrently creating the same
        # sketch. This Redis-based lock ensures only one worker proceeds at a time, even
        # across different machines. The code will block until the lock is acquired.
        # The lock automatically expires after 60 seconds to prevent deadlocks.
        with redis_client.lock(sketch_name, timeout=60, blocking_timeout=5):
            # Search for an existing sketch while having the lock
            for _sketch in timesketch_api_client.list_sketches():
                if _sketch.name == sketch_name:
                    sketch = _sketch
                    break

            # If not found, create a new one
            if not sketch:
                sketch = timesketch_api_client.create_sketch(sketch_name)

    return sketch


# Task name used to register and route the task to the correct queue.
TASK_NAME = "openrelik-worker-timesketch.tasks.upload"

# Task metadata for registration in the core system.
TASK_METADATA = {
    "display_name": "Upload to Timesketch",
    "description": "Upload resulting file to Timesketch",
    "task_config": [
        {
            "name": "sketch_id",
            "label": "Add to an existing sketch",
            "description": "Provide the numerical sketch ID of the existing sketch",
            "type": "text",
            "required": False,
        },
        {
            "name": "sketch_name",
            "label": "Name of the new sketch to create",
            "description": "Create a new sketch",
            "type": "text",
            "required": False,
        },
        {
            "name": "timeline_name",
            "label": "Name of the timeline to create",
            "description": "Timeline name",
            "type": "text",
            "required": False,
        },
    ],
}


@celery.task(bind=True, name=TASK_NAME, metadata=TASK_METADATA)
def upload(
    self,
    pipe_result: str = None,
    input_files: list = None,
    output_path: str = None,
    workflow_id: str = None,
    task_config: dict = None,
) -> str:
    """Export files to Timesketch.

    Args:
        pipe_result: Base64-encoded result from the previous Celery task, if any.
        input_files: List of input file dictionaries (unused if pipe_result exists).
        output_path: Path to the output directory.
        workflow_id: ID of the workflow.
        task_config: User configuration for the task.

    Returns:
        Base64-encoded dictionary containing task results.
    """
    input_files = get_input_files(pipe_result, input_files or [])

    # Connection details from environment variables.
    timesketch_server_url = os.environ.get("TIMESKETCH_SERVER_URL")
    timesketch_server_public_url = os.environ.get("TIMESKETCH_SERVER_PUBLIC_URL")
    timesketch_username = os.environ.get("TIMESKETCH_USERNAME")
    timesketch_password = os.environ.get("TIMESKETCH_PASSWORD")

    # User supplied config.
    sketch_id = task_config.get("sketch_id")
    sketch_name = task_config.get("sketch_name")
    sketch_identifier = {"sketch_id": sketch_id} if sketch_id else {"sketch_name": sketch_name}

    # Create a Timesketch API client.
    timesketch_api_client = timesketch_client.TimesketchApi(
        host_uri=timesketch_server_url,
        username=timesketch_username,
        password=timesketch_password,
    )

    # Get or create sketch using a distributed lock.
    sketch = get_or_create_sketch(
        timesketch_api_client,
        redis_client,
        **sketch_identifier,
        workflow_id=workflow_id,
    )

    if not sketch:
        raise Exception(f"Failed to create or retrieve sketch '{sketch_name}'")

    # Make the sketch public.
    # TODO: Make this user configurable.
    sketch.add_to_acl(make_public=True)

    # Import each input file to it's own index.
    for input_file in input_files:
        input_file_path = input_file.get("path")
        timeline_name = task_config.get("timeline_name") or input_file.get("display_name")
        with importer.ImportStreamer() as streamer:
            streamer.set_sketch(sketch)
            streamer.set_timeline_name(timeline_name)
            streamer.add_file(input_file_path)

    return create_task_result(
        output_files=[],
        workflow_id=workflow_id,
        command="Timesketch Importer Client",
        meta={"sketch": f"{timesketch_server_public_url}/sketch/{sketch.id}"},
    )
