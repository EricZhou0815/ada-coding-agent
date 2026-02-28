# Ada Async API & Workers

To start up your scalable AI Team locally:
1. `docker run -d -p 6379:6379 redis`
2. `uvicorn api.main:app --reload`
3. `celery -A worker.tasks worker --loglevel=info`
