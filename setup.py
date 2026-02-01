import argparse


def get_cmdoptions():
    parser = argparse.ArgumentParser(
        prog='Bingo Game',
        description='A distributed Bingo Game',
        epilog='Text at the bottom of help')
    parser.add_argument('--mode', '-m',
                        help='Mode to start in',
                        required=True,
                        default='server',
                        type=str)
    parser.add_argument('--verbose', '-v',
                        help='Enable verbose mode',
                        action=argparse.BooleanOptionalAction,
                        default=False)
    parser.add_argument('--instances', '-i',
                        help='Number of instances to spawn',
                        default=1,
                        type=int)
    parser.add_argument('--config', '-c',
                        help='Path to config file',
                        default=None,
                        type=str)
    parser.add_argument('--loglevel', '-ll',
                        help='Log Level',
                        default="INFO",
                        type=str)
    return parser.parse_args()
