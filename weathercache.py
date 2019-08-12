#!/usr/bin/python3

import os
from flask import Flask, jsonify
from bs4 import BeautifulSoup
import requests
from threading import Timer, Thread, Event


refresh = int(os.getenv('WEATHER_CACHE_REFRESH', 5))
wurl = os.getenv('WEATHER_CACHE_URI', 'https://weather.com/weather/today/l/02139:4:US')
current = {}


class perpetualTimer():

   def __init__(self, t, hFunction):
      self.t=t # time seconds
      self.hFunction = hFunction # function to execute
      self.thread = Timer(self.t, self.handle_function)

   def handle_function(self):
      self.hFunction()
      self.thread = Timer(self.t, self.handle_function)
      self.thread.start()

   def start(self):
      self.thread.start()

   def cancel(self):
      self.thread.cancel()


def lazyFtoC(F):
    F = int(F.replace('°',''))
    C = round((F-32)*5/9, 1)
    return f'{F}°F {C}°C'


def cache_weather():
    global current
    cache = current
    try:
        with requests.get(wurl) as url:
            if 200 == url.status_code:
                soup = BeautifulSoup(url.text, 'lxml')
                conds = soup.find(class_='today_nowcard-condition')
                gets = ('today_nowcard-temp',
                        'today_nowcard-phrase',
                        'today_nowcard-feels',
                       )

                for lk in gets:
                    if lk == gets[0]:
                        t = lazyFtoC(conds.find(class_=lk).text)
                    else:
                        t = conds.find(class_=lk).text.replace('°','°F')
                    current[lk.replace('today_nowcard-','')] = f'{t}'
    except:
        current = cache
        print(f'Fetch exception')


app = Flask(__name__)


@app.route('/weather/current', methods=['GET'])
def get_weather():
    global current
    return jsonify({'current': current})


if __name__ == '__main__':
    try:
        cache_weather()
        # background event - refresh cache at intervals
        wc = perpetualTimer((refresh*60), cache_weather)
        wc.start()
        app.run(host='0.0.0.0')

    except KeyboardInterrupt:
        wc.cancel()

