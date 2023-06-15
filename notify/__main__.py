"""Notify Worker server entry point."""
import asyncio
import argparse
import uvloop
from notify.server import NotifyWorker
from notify.conf import (
    NOTIFY_DEFAULT_HOST,
    NOTIFY_DEFAULT_PORT
)

def main():
    """Main Worker Function."""
    asyncio.set_event_loop_policy(
        uvloop.EventLoopPolicy()
    )
    uvloop.install()
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        '--host', dest='host', type=str,
        default=NOTIFY_DEFAULT_HOST,
        help='set server host'
    )
    parser.add_argument(
        '--port', dest='port', type=int,
        default=NOTIFY_DEFAULT_PORT,
        help='set server port'
    )
    parser.add_argument(
        '--debug', action="store_true",
        default=False,
        help="Start workers in Debug Mode"
    )
    args = vars(parser.parse_args())
    try:
        loop = asyncio.get_event_loop()
        print('::: Starting Workers ::: ')
        worker = NotifyWorker(**args)
        loop.run_until_complete(
            worker.start()
        )
    except KeyboardInterrupt:
        pass
    except Exception as ex:
        # log the unexpected error
        print(
            f"Unexpected error: {ex}"
        )
    finally:
        loop.run_until_complete(
            worker.stop()
        )
        loop.close()  # close the event loop


if __name__ == '__main__':
    main()
