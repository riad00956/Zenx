web: gunicorn --worker-class eventlet -w 1 --threads 8 --timeout 120 --bind 0.0.0.0:$PORT wsgi:app
worker: python main.py
bot: python bot.py
redis: redis-server --port 6379
