## Openrelik worker for interacting with a Timesketch server

### Installation
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

---

### Example local host setup
If you are running OpenRelik and Timesketch on the same host (server or laptop) using docker-compose:

#### 1. Connect Timesketch to OpenRelik

List docker networks
```
$ docker network ls
NETWORK ID     NAME                     DRIVER    SCOPE
f75ce99f7b00   bridge                   bridge    local
62733d6006e2   host                     host      local
38ed0efd9746   none                     null      local
8c4f1a667d05   openrelik_default        bridge    local
3709ce30c0fa   timesketch_default   bridge    local
```

Link OpenRelik to the timesketch-web container. This will enable containers in OpenRelik to talk to your Timesketch server at `http://timesketch-web:5000`
```
$ docker network connect openrelik_default timesketch-web
```

#### 2. (Optional) Create an openrelik user in Timesketch
```
docker compose exec timesketch-web tsctl create-user openrelik
```

#### 3. Add the Timesketch worker to docker-compose.yml (change <PASSWORD>)
```
  openrelik-worker-timesketch:
    container_name: openrelik-worker-timesketch
    image: ghcr.io/openrelik/openrelik-worker-timesketch:${OPENRELIK_WORKER_TIMESKETCH_VERSION}
    restart: always
    environment:
      - REDIS_URL=redis://openrelik-redis:6379
      - TIMESKETCH_SERVER_URL=https://timesketch-web:5000
      - TIMESKETCH_SERVER_PUBLIC_URL=https://127.0.0.1:5000
      - TIMESKETCH_USERNAME=openrelik
      - TIMESKETCH_PASSWORD=<PASSWORD>
    volumes:
      - ./data:/usr/share/openrelik/data
    command: "celery --app=src.app worker --task-events --concurrency=1 --loglevel=INFO -Q openrelik-worker-timesketch"
```

