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
    Retrieves an existing Timesketch sketch or creates a new one.

    If `sketch_id` is provided, it attempts to fetch that specific sketch.
    If `sketch_name` is provided (and `sketch_id` is not), it attempts to create
    a sketch with that name.
    If neither `sketch_id` nor `sketch_name` is provided, it generates a default
    sketch name based on the `workflow_id`. In this default case, a Redis
    distributed lock is used to prevent race conditions if multiple workers
    attempt to create the same sketch concurrently. The lock ensures that only
    one worker will create the sketch if it doesn't already exist.

    Args:
        timesketch_api_client: An instance of the Timesketch API client.
        redis_client: An instance of the Redis client, used for distributed locking.
        sketch_id (int, optional): The ID of an existing sketch to retrieve.
        sketch_name (str, optional): The name for a new sketch to be created.
        workflow_id (str, optional): The ID of the workflow, used to generate
            a default sketch name if `sketch_id` and `sketch_name` are not provided.

    Returns:
        timesketch_api_client.Sketch or None: The retrieved or created Timesketch
            sketch object, or None if the operation failed (e.g., sketch not found
            when an ID is provided, or creation fails).
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
        {
            "name": "make_sketch_public",
            "label": "Make sketch public",
            "description": "Set the sketch to be publicly accessible in Timesketch.",
            "type": "boolean",
            "required": False,
            "default": True,  # Default to making sketches public
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
    """
    Uploads files to a Timesketch instance, creating or updating a sketch and timelines.

    The task retrieves input files, connects to a Timesketch server using credentials
    from environment variables, gets or creates a sketch, optionally makes it public,
    and then imports each input file as a new timeline within that sketch.

    Args:
        self: The Celery task instance.
        pipe_result (str, optional): Base64-encoded string representing the result
            from a previous Celery task. If provided, input files are derived from this.
        input_files (list, optional): A list of dictionaries, where each dictionary
            represents an input file with keys like 'path' and 'display_name'.
            Used if pipe_result is None. Defaults to an empty list if both are None.
        output_path (str, optional): Path to the output directory.
            Note: This parameter is currently unused in the function.
        workflow_id (str, optional): The ID of the OpenRelik workflow. Used for
            generating default sketch names and included in the task result.
        task_config (dict, optional): A dictionary containing user-supplied
            configuration for the task, such as 'sketch_id', 'sketch_name',
            'timeline_name', and 'make_sketch_public'.

    Returns:
        str: A Base64-encoded dictionary string containing the task results,
             including a link to the Timesketch sketch.

    Raises:
        ValueError: If required Timesketch environment variables are missing.
        RuntimeError: If there's an issue creating/retrieving the sketch,
                      setting its ACL, or importing files into Timesketch.
        ConnectionError: If the worker fails to connect or authenticate with
                         the Timesketch server.
        FileNotFoundError: If an input file specified for import is not found.
    """
    input_files = get_input_files(pipe_result, input_files or [])

    # Connection details from environment variables.
    timesketch_server_url = os.environ.get("TIMESKETCH_SERVER_URL")
    timesketch_server_public_url = os.environ.get("TIMESKETCH_SERVER_PUBLIC_URL")
    timesketch_username = os.environ.get("TIMESKETCH_USERNAME")
    timesketch_password = os.environ.get("TIMESKETCH_PASSWORD")

    # Validate required environment variables
    required_env_vars = {
        "TIMESKETCH_SERVER_URL": timesketch_server_url,
        "TIMESKETCH_SERVER_PUBLIC_URL": timesketch_server_public_url,
        "TIMESKETCH_USERNAME": timesketch_username,
        "TIMESKETCH_PASSWORD": timesketch_password,
    }
    missing_vars = [k for k, v in required_env_vars.items() if not v]
    if missing_vars:
        raise ValueError(
            "Missing required environment variables for "
            f"Timesketch worker: {', '.join(missing_vars)}"
        )

    # User supplied config.
    sketch_id = task_config.get("sketch_id")
    sketch_name = task_config.get("sketch_name")
    sketch_identifier = (
        {"sketch_id": sketch_id} if sketch_id else {"sketch_name": sketch_name}
    )
    make_sketch_public = task_config.get("make_sketch_public", True)

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
    sketch.add_to_acl(make_public=True)

    # Make the sketch public if configured.
    if make_sketch_public:
        try:
            sketch.add_to_acl(make_public=True)
        except Exception as e:  # Consider catching more specific exceptions
            raise RuntimeError(
                f"Failed to make sketch {sketch.id} ('{sketch.name}') public: {e}"
            ) from e

    # Import each input file to it's own index.
    for input_file in input_files:
        input_file_path = input_file.get("path")
        timeline_name = task_config.get("timeline_name") or input_file.get(
            "display_name"
        )
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
