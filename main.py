import multiprocessing
import sys
import time

from loguru import logger

from client import Client
from server import Server
from setup import get_cmdoptions

if __name__ == '__main__':
    args = get_cmdoptions()

    if not args.verbose:
        logger.disable("")

    logger.info('Starting Bingo Game')
    logger.info('Mode : {}', args.mode)
    logger.info('Instances : {}', args.instances)
    logger.info('Config : {}', args.config)

    try:
        match args.mode:
            case "server":
                server = Server()
                processes = [multiprocessing.Process(target=Server().start_servers) for x in range(0, args.instances)]
                for process in processes:
                    process.start()
            case "client":
                Client().start_clients()
            case default:
                logger.error("Not a valid option")
                sys.exit(1)

        while True:
            try:
                time.sleep(1)
                logger.trace("Main is running")
            except KeyboardInterrupt:
                logger.info("Main thread caught KeyboardInterrupt. Shutting down gracefully.")
                raise KeyboardInterrupt
    except KeyboardInterrupt:
        logger.error("[SHUTTING DOWN] Main is stopping...")
        exit(1)
    except Exception as e:
        logger.error("Caught exception {}", e)
        logger.error("[SHUTTING DOWN] Main is stopping...")
    finally:
        logger.error("Main shutting down")
