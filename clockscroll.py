#!/usr/bin/env python
# -*- encoding: utf-8 -*-
# -*- coding: utf-8 -*-

# clockscroll v.0.8
# by shunte88
# 0.5 scrollphathd rewrite
# 0.6 accuweather retool - wu is no more
# 0.7 smarter sunrise/dusk events
# 0.8 use central weather cache running on NAS

import scrollphathd
from scrollphathd.fonts import font3x5, font5x7

import os

import time
import json
import signal

import datetime
import subprocess
import ntplib  # sync clock every 24 hours, no RTC hat/bonnet here folks!

from threading import Timer, Thread, Event

try:
    import urllib.request as urllib2
except ImportError:
    import urllib2


SHOWSECONDS = int(os.getenv('CLOCK_SHOW_SECONDS', 1))  # show seconds progress
LATITUDE = float(os.getenv('WEATHER_LATITUDE', '42.361365'))
LONGITUDE = float(os.getenv('WEATHER_LONGITUDE', '-71.103958'))
URI_WEATHER_CHANNEL = os.getenv('URI_WEATHER_CHANNEL', None)  # Weather URI

wcretry = 5 * 60         # weather cache server 5 minute lookups
NTP_MISS = 0
ntpretry = 60 * 60 * 24  # ntp daily, pi zero can drift
briteretry = 5 * 60      # check dawn-dusk brightness limits
lastconditions = ''


# observation horizon type is 0 for sunrise/set, or -6, dusk/dawn
def getSunAttr(horizon='0', days=0):

    import ephem
    import math

    sun = ephem.Sun()

    obs = ephem.Observer()
    obs.lat = (LATITUDE*math.pi)/180
    obs.lon = (LONGITUDE*math.pi)/180

    date = datetime.date.today()

    if 0 == days:
        obs.date = date
    else:
        obs.date = date + datetime.timedelta(days=days)

    now = datetime.datetime.now()
    obs.horizon = horizon
    if '0' == horizon:
        event = ephem.localtime(obs.next_rising(sun))  # sunrise
    else:
        event = ephem.localtime(obs.next_setting(sun))  # dusk

    if event < now:  # get next event (tomorrow)
        return getSunAttr(horizon, 1)
    else:
        # calculate seconds to next event
        return int((event - now).total_seconds())


class sunAttrTimer():

    def __init__(self, t, horizon, days, bright_value):
        self.t = t
        self.horizon = horizon
        self.days = days
        self.bright_value = bright_value
        self.thread = Timer(self.t, self.set_display_brightness)

    def set_display_brightness(self):
        # set the brighness attribute
        global BRIGHTNESS
        BRIGHTNESS = self.bright_value
        time.sleep(2)  # delay tweak, in a thread so no observable
        # reset the event timer
        self.t = getSunAttr(self.horizon, self.days)
        self.thread = Timer(self.t, self.set_display_brightness)
        self.thread.start()

    def start(self):
        self.thread.start()

    def cancel(self):
        self.thread.cancel()


# generic perpetual time, no args
class perpetualTimer():

    def __init__(self, t, hFunction):
        self.t = t                  # time seconds
        self.hFunction = hFunction  # function to execute
        self.thread = Timer(self.t, self.handle_function)

    def handle_function(self):
        self.hFunction()
        self.thread = Timer(self.t, self.handle_function)
        self.thread.start()

    def start(self):
        self.thread.start()

    def cancel(self):
        self.thread.cancel()


def getNTP():
    good = 0
    call = ntplib.NTPClient()
    while True:
        try:
            # try to connect to the NTP pool...
            response = call.request('pool.ntp.org')
            NTP_MISS = 0
            good = 1
            break
        except:
            print('NTP Fetch exception')
            NTP_MISS += 1
            if NTP_MISS >= 5:
                break
    if 1 == good:
        # If we get a response, update the system time.
        t = datetime.datetime.fromtimestamp(response.tx_time)
        t = t.strftime('%Y-%m-%d %H:%M:%S')
        set_string = '--set=' + t
        subprocess.call(['date', set_string])
        print('NTP Sync')


def getAW():
    global wdata
    try:
        response = urllib2.urlopen(URI_WEATHER_CHANNEL)
        wdata = json.loads(response.read().decode())
    except:
        print('Fetch exception')


def getConditionAW():
    global wdata
    try:
        d = wdata['current']
        # adding stock ticker support
        temp = u"{} {} {} ".format(d['temp'],
                                   d['phrase'].title(),
                                   d['feels'])
        try:
            temp += "{} {} ".format(d['ticker'], d['price'])
        except:
            pass
        return temp
    except:
        return ''


def simpleScrollText(limit, s):
    scrollphathd.clear()
    scrollphathd.write_string(s, font=font5x7, brightness=BRIGHTNESS)

    interval = 0.05
    # font 5 wide, display full string limit times
    # font is not proportional so a tad fuzzy

    timeout = (1+len(s))*5*interval*limit
    initt = 0

    while timeout > 0:

        scrollphathd.show()
        scrollphathd.scroll()

        time.sleep(interval)
        timeout -= interval


def showConditions(times):
    global lastconditions
    condition = getConditionAW()
    if '' != condition:
        if (lastconditions != condition):
            print(condition)
            lastconditions = condition

        simpleScrollText(times, condition)


def showTime(duration):
    interval = 0.1
    while duration > 0:

        scrollphathd.clear()
        scrollphathd.write_string(
            time.strftime("%H:%M"),
            x=0,
            y=0,
            font=font3x5,
            brightness=BRIGHTNESS
        )

        if int(time.time()) % 2 == 0:
            scrollphathd.clear_rect(8, 0, 1, 5)

        if SHOWSECONDS:
            seconds_progress = ((time.time() % 60) / 59.0) * 15
            scrollphathd.set_pixel(int(seconds_progress), 6, BRIGHTNESS)

        scrollphathd.show()
        time.sleep(interval)

        duration -= interval


def suffix(d):
    return 'th' if 11 <= d <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(d%10, 'th')


def fancyDate(format, t):
    return t.strftime(format).replace('{S}', str(t.day) + suffix(t.day))


def showDate(times):
    simpleScrollText(times,
                     fancyDate(' %A {S} %B, %Y', datetime.datetime.now()))


# comment out if not upside-downsy, should be a configurable
scrollphathd.rotate(degrees=180)

try:

    # define display brightness events
    next_dusk = getSunAttr('-6', 0)
    dusk = sunAttrTimer(next_dusk, '-6', 0, 0.15)
    dusk.start()
    next_sunrise = getSunAttr('0', 0)
    sunrise = sunAttrTimer(next_sunrise, '0', 0, 0.1)
    sunrise.start()

    # and, set brightness - a little brighter after dusk
    if (next_sunrise > next_dusk):
        BRIGHTNESS = 0.1
    else:
        BRIGHTNESS = 0.15

    # initial NTP call
    getNTP()
    # then set daily
    nt = perpetualTimer(ntpretry, getNTP)
    nt.start()

    # initialize weather
    getAW()
    # and get latest at intervals
    wt = perpetualTimer(wcretry, getAW)
    wt.start()

    # time, temp F, temp C and conditions
    displaydate = True
    while True:

        if 0 == int(time.strftime('%M')) and displaydate:
            displaydate = False
            showDate(1)   # show date on  the hour only
        else:
            displaydate = True

        showTime(20)       # show time for 20 seconds
        showConditions(2)  # show conditions twice

except KeyboardInterrupt:
    wt.cancel()
    nt.cancel()
    dusk.cancel()
    sunrise.cancel()
    scrollphathd.clear()
