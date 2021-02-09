import datetime
import os
import threading
import time

import tweepy
from event_scheduler import EventScheduler
from picamera import PiCamera

import astral
import astral.sun
import pytz
from timezonefinder import TimezoneFinder


class Tweeter(object):
    CAMERA_WARMUP = 1.0
    CAMERA_DELAY = 1.0

    def __init__(
        self,
        tracker,
        direction,
        consumer_key,
        consumer_secret,
        access_token,
        access_token_secret,
        hashtags=[],
    ):
        self.tracker = tracker

        self.direction = direction

        self.hashtags = hashtags

        self.schedule = {}
        self.scheduler = EventScheduler("tweeter")

        self.lock = threading.RLock()

        # set up location data
        tf = TimezoneFinder()
        self.location = astral.LocationInfo(
            "AIS Station",
            "Earth",
            tf.timezone_at(lat=self.tracker.lat, lng=self.tracker.lon),
            self.tracker.lat,
            self.tracker.lon,
        )

        # set up camera
        self.camera = PiCamera()
        self.camera.resolution = (3280, 2464)
        self.camera.zoom = (0.25, 0.35, 0.5, 0.5)

        # set up Twitter connection
        auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
        auth.set_access_token(access_token, access_token_secret)
        self.twitter = tweepy.API(auth)

        self.scheduler.start()

        # register callback
        self.tracker.message_callbacks.append(self.check)

    def check(self, mmsi, t):
        crossing = self.tracker.crossing_time(mmsi, self.direction)
        if crossing is None:
            return
        delta = crossing - time.time()
        if (
            not mmsi in self.schedule
            and delta < self.CAMERA_WARMUP + self.CAMERA_DELAY + 0.5
        ):
            snap_and_tweet(self, mmsi)
        if self.CAMERA_WARMUP + self.CAMERA_DELAY + 0.5 < delta < 60.0:
            try:
                existing_event = self.schedule.pop(mmsi)
                self.scheduler.cancel(existing_event)
            except KeyError:
                pass
            self.schedule[mmsi] = self.scheduler.enterabs(
                crossing
                - self.CAMERA_WARMUP
                - self.CAMERA_DELAY
                - time.time()
                + time.monotonic(),
                1,
                self.snap_and_tweet,
                argument=(mmsi,),
            )

    def snap_and_tweet(self, mmsi):
        with self.lock:
            # grab the image
            image_path = os.path.join("/tmp", "{}.jpg".format(mmsi))
            self.snap(image_path)

            # tweet the image with info
            lat, lon = self.tracker.center_coords(mmsi)
            try:
                self.twitter.update_with_media(
                    image_path, self.generate_text(mmsi), lat=lat, long=lon
                )
            except tweepy.error.TweepError:
                pass

            # clean up the image
            os.remove(image_path)

    def snap(self, path):
        with self.lock:
            # set exposure mode based on dawn/dusk times
            sun = astral.sun.sun(
                self.location.observer,
                datetime.date.today(),
                tzinfo=self.location.timezone,
            )
            now = self.now()
            if now < sun["dawn"] or now > sun["dusk"]:
                self.camera.exposure_mode = "night"
            else:
                self.camera.exposure_mode = "auto"

            # capture image
            self.camera.start_preview()
            time.sleep(self.CAMERA_WARMUP)
            self.camera.capture(path)
            self.camera.stop_preview()

    def now(self):
        now = pytz.utc.localize(datetime.datetime.utcnow()).astimezone(
            pytz.timezone(self.location.timezone)
        )

    def generate_text(self, mmsi):
        text = u"{} ".format(self.tracker.flag(mmsi))

        ship = self.tracker[mmsi]

        shipname = ship["shipname"]
        if shipname:
            text += shipname
        else:
            text += "(Unidentified)"

        text += u", {}".format(self.tracker.ship_type(mmsi))

        length, width = self.tracker.dimensions(mmsi)
        if length > 0 and width > 0:
            text += u" ({l} x {w} m)".format(l=length, w=width)

        status = self.tracker.status(mmsi)
        if status is not None:
            text += u", {}".format(status)

        destination = ship["destination"]
        if destination:
            text += u", destination: {}".format(destination)

        course = ship["course"]
        speed = ship["speed"]
        if course is not None and speed is not None:
            text += u", course: {c:.1f} \N{DEGREE SIGN} / speed: {s} kn".format(
                c=course, s=speed
            )

        for hashtag in self.hashtags:
            text += u" #{}".format(hashtag)

        return text
