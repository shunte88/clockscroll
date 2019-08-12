#!/usr/bin/python3

import os
from flask import Flask, jsonify
from bs4 import BeautifulSoup
import requests
from threading import Timer, Thread, Event


refresh = int(os.getenv('WEATHER_CACHE_REFRESH', 5))
wurl = os.getenv('WEATHER_CACHE_URI', 'https://weather.com/weather/today/l/02139:4:US')
ticker = os.getenv('WEATHER_CACHE_TICKER', 'AKAM')
spurl = 'https://stocktwits.com/symbol/'+ticker
current = {}


class perpetualTimer():

    def __init__(self, t, hFunction):
        self.t = t  # time seconds
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
                    current[lk.replace('today_nowcard-', '')] = f'{t}'
    except:
        current = cache
        print('Fetch exception [weather]')


def cache_stock():
    global current
    cache = current
    # we only want to do this if market open
    # times a little fuzzy and need weekends and
    # market holiday incorporation too
    from datetime import datetime
    from pytz import timezone
    import json
    import traceback
    tz = timezone('EST')
    now = datetime.now(tz).hour
    if now > 8 and now < 18:
        try:
            key = 'window.INITIAL_STATE = {'
            with requests.get(spurl) as url:
                if 200 == url.status_code:
                    soup = BeautifulSoup(url.text, 'lxml')
                    rawJ = soup.find_all('script')
                    for x in rawJ:
                        if str(x).find(key) > 0:
                            x1 = str(x).split(key)
                            x2 = x1[1].split(';')
                            js = json.loads('{'+x2[0])
                            current['ticker'] = ticker
                            current['price'] = js['stocks']['inventory'][ticker]['price']
        except:    
            current = cache
            print(f'Fetch exception [ticker] {ticker}')
            traceback.print_exc()


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
        cache_stock()
        sc = perpetualTimer(180, cache_stock)
        sc.start()
        app.run(host='0.0.0.0')

    except KeyboardInterrupt:
        sc.cancel()
        wc.cancel()

