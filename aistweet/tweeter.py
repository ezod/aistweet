import datetime
import fractions
import os
import threading
import time

import tweepy
from event_scheduler import EventScheduler
from gtts import gTTS
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
        tts=False,
        logging=True,
    ):
        self.tracker = tracker

        self.direction = direction

        self.hashtags = hashtags

        self.tts = tts

        self.logging = logging

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

        # set up Twitter connection
        auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
        auth.set_access_token(access_token, access_token_secret)
        self.twitter = tweepy.API(auth)

        self.scheduler.start()

        # register callback
        self.tracker.message_callbacks.append(self.check)

    def stop(self):
        self.scheduler.stop()

    def log(self, mmsi, message):
        if self.logging:
            shipname = self.tracker[mmsi]["shipname"]
            print("[{}] {}: {}".format(str(datetime.datetime.now()), shipname, message))

    def check(self, mmsi, t):
        crossing, depth = self.tracker.crossing(mmsi, self.direction)
        if crossing is None:
            return
        delta = crossing - time.time() - self.CAMERA_WARMUP - self.CAMERA_DELAY
        if 0.0 < delta < 60.0:
            try:
                existing_event = self.schedule.pop(mmsi)
                self.scheduler.cancel(existing_event)
            except (KeyError, ValueError, AttributeError):
                pass
            self.schedule[mmsi] = self.scheduler.enter(
                delta,
                1,
                self.snap_and_tweet,
                arguments=(mmsi, depth),
            )
            self.log(mmsi, "scheduled for tweet in {} seconds".format(delta))

    def purge_schedule(self, mmsi):
        try:
            del self.schedule[mmsi]
            self.log(mmsi, "removed from schedule")
        except KeyError:
            pass

    def snap_and_tweet(self, mmsi, depth):
        # only tweet once while this ship is scheduled (60 second cooldown)
        if mmsi in self.schedule and self.schedule[mmsi] is None:
            return
        self.schedule[mmsi] = None

        self.log(mmsi, "ship in view, tweeting...")
        with self.lock:
            # determine whether this is a "large" ship in FOV (horiz. 62.2deg)
            # large if ship length > 0.9 * tan(31.1) * distance to ship
            large = self.tracker.dimensions(mmsi)[0] > (0.542915 * depth)

            # grab the image
            image_path = os.path.join("/tmp", "{}.jpg".format(mmsi))
            self.snap(image_path, large)
            self.log(mmsi, "image captured to {}".format(image_path))

            # tweet the image with info
            lat, lon = self.tracker.center_coords(mmsi)
            try:
                self.twitter.update_status_with_media(
                    self.generate_text(mmsi), image_path, lat=lat, long=lon
                )
            except tweepy.errors.TweepyException as e:
                self.log(mmsi, "tweet error: {}".format(e))

            # clean up the image
            os.remove(image_path)

            # remove event from schedule after a minute
            self.scheduler.enter(60.0, 2, self.purge_schedule, arguments=(mmsi,))

            # announce the ship using TTS
            if self.tts:
                shipname = self.tracker[mmsi]["shipname"]
                if shipname:
                    speech_path = os.path.join("/tmp", "{}.mp3".format(mmsi))
                    speech = gTTS(text=shipname, lang="en", slow=False)
                    speech.save(speech_path)
                    os.system("mpg321 -q {}".format(speech_path))
                    os.remove(speech_path)

        self.log(mmsi, "done tweeting")

    def snap(self, path, large):
        with self.lock:
            # set zoom based on ship size
            self.camera.zoom = (0.0, 0.0, 1.0, 1.0) if large else (0.25, 0.35, 0.5, 0.5)
            # set exposure mode based on dawn/dusk times
            sun = astral.sun.sun(
                self.location.observer,
                datetime.date.today(),
                tzinfo=self.location.timezone,
            )
            now = self.now()
            if now < sun["dawn"] or now > sun["dusk"]:
                self.camera.resolution = (1640, 1232)
                self.camera.framerate = fractions.Fraction(2, 1)
                self.camera.exposure_mode = "night"
            else:
                self.camera.resolution = (1640, 1232) if large else (3280, 2464)
                self.camera.framerate = fractions.Fraction(30, 1)
                self.camera.exposure_mode = "auto"

            # capture image
            self.camera.start_preview()
            time.sleep(self.CAMERA_WARMUP)
            self.camera.capture(path)
            self.camera.stop_preview()

    def now(self):
        return pytz.utc.localize(datetime.datetime.utcnow()).astimezone(
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
            text += u", course: {c:.1f} \N{DEGREE SIGN} / speed: {s:.1f} kn".format(
                c=course, s=speed
            )

        text += u" https://www.marinetraffic.com/en/ais/details/ships/mmsi:{}".format(
            mmsi
        )

        for hashtag in self.hashtags:
            text += u" #{}".format(hashtag)

        return text
