### Openrelik worker for interacting with a Timesketch server

#### Installation
Add to your docker-compose configuration:

```
  openrelik-worker-timesketch:
    container_name: openrelik-worker-timesketch
    image: ghcr.io/openrelik/openrelik-worker-timesketch:${OPENRELIK_WORKER_TIMESKETCH_VERSION}
    restart: always
    environment:
      - REDIS_URL=redis://openrelik-redis:6379
      - TIMESKETCH_SERVER_URL=https://<REPLACE_WITH_YOUR_TIMESKETCH_SERVER>
      - TIMESKETCH_SERVER_PUBLIC_URL=https://<REPLACE_WITH_YOUR_TIMESKETCH_SERVER>
      - TIMESKETCH_USERNAME=dev
      - TIMESKETCH_PASSWORD=dev
    volumes:
      - ./data:/usr/share/openrelik/data
    command: "celery --app=src.app worker --task-events --concurrency=1 --loglevel=INFO -Q openrelik-worker-timesketch"
```
