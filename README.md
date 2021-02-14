`aistweet`, a Twitter photo bot for Raspberry Pi AIS tracking stations
----------------------------------------------------------------------

aistweet tracks ships via AIS and takes their picture with a Raspberry Pi camera as they pass by.

Command Line
------------
```
usage: aistweet.py [-h] [--host HOST] [--port PORT] [--db DB]
                   [--hashtags HASHTAGS [HASHTAGS ...]]
                   latitude longitude direction consumer_key consumer_secret
                   access_token access_token_secret

Raspberry Pi AIS tracker/camera Twitter bot

positional arguments:
  latitude              AIS station latitude
  longitude             AIS station longitude
  direction             bearing of camera (degrees clockwise from north)
  consumer_key          Twitter consumer key
  consumer_secret       Twitter consumer secret
  access_token          Twitter access token
  access_token_secret   Twitter access token secret

optional arguments:
  -h, --help            show this help message and exit
  --host HOST           host for receiving UDP AIS messages
  --port PORT           port for receiving UDP AIS messages
  --db DB               database file for static ship data
  --hashtags HASHTAGS [HASHTAGS ...]
                        hashtags to add to tweets
```

Dependencies
------------
  - [astral](https://pypi.org/project/astral/)
  - [emoji-country-flag](https://pypi.org/project/emoji-country-flag/)
  - [event-scheduler](https://pypi.org/project/event-scheduler/)
  - [geopy](https://pypi.org/project/geopy/)
  - [picamera](https://pypi.org/project/picamera/)
  - [pyais](https://pypi.org/project/pyais/)
  - [pytz](https://pypi.org/project/pytz/)
  - [timezonefinder](https://pypi.org/project/timezonefinder/)
  - [tweepy](https://pypi.org/project/tweepy/)
