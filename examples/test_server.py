import asyncio
from notify.server import NotifyWorker

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    worker = NotifyWorker(debug=True)
    try:
        loop.run_until_complete(worker.start())
    except KeyboardInterrupt:
        loop.run_until_complete(worker.stop())
    finally:
        loop.close()
