#!/usr/bin/python3

import argparse
import threading

from aistweet.ship_tracker import ShipTracker
from aistweet.tweeter import Tweeter


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Raspberry Pi AIS tracker/camera Twitter bot"
    )
    parser.add_argument("latitude", type=float, help=("AIS station latitude"))
    parser.add_argument("longitude", type=float, help=("AIS station longitude"))
    parser.add_argument(
        "direction",
        type=float,
        help=("bearing of camera (degrees clockwise from north)"),
    )
    parser.add_argument("consumer_key", type=str, help=("Twitter consumer key"))
    parser.add_argument("consumer_secret", type=str, help=("Twitter consumer secret"))
    parser.add_argument("access_token", type=str, help=("Twitter access token"))
    parser.add_argument(
        "access_token_secret", type=str, help=("Twitter access token secret")
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help=("host for receiving UDP AIS messages"),
    )
    parser.add_argument(
        "--port", type=int, default=10110, help=("port for receiving UDP AIS messages")
    )
    parser.add_argument("--db", type=str, help=("database file for static ship data"))
    parser.add_argument(
        "--hashtags",
        type=str,
        nargs="+",
        default=[],
        help=("hashtags to add to tweets"),
    )
    parser.add_argument(
        "--tts", action="store_true", help=("announce ship name via text-to-speech")
    )
    args = parser.parse_args()

    try:
        tracker = ShipTracker(
            args.host, args.port, args.latitude, args.longitude, args.db
        )
        tweeter = Tweeter(
            tracker,
            args.direction,
            args.consumer_key,
            args.consumer_secret,
            args.access_token,
            args.access_token_secret,
            args.hashtags,
            args.tts,
        )
        forever = threading.Event()
        forever.wait()
    except KeyboardInterrupt:
        pass
    finally:
        tweeter.stop()
