#!/usr/bin/python3

import os
import sys

from flask import Flask, jsonify
from bs4 import BeautifulSoup
import requests
import re

from threading import Timer, Thread, Event

import pandas_market_calendars as mcal

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

chrome_options = Options()
chrome_options.headless = True

# want the exchange that the stock trades on - q&d here
nyse = mcal.get_calendar('NYSE')

refresh = int(os.getenv('WEATHER_CACHE_REFRESH', 5))
wurl = os.getenv('WEATHER_CACHE_URI',
                 'https://weather.com/weather/today/l/02139:4:US')
ticker = os.getenv('WEATHER_CACHE_TICKER', 'AKAM')
spurl = f'https://stocktwits.com/symbol/{ticker}'
gurl = f'https://google.com/search?q={ticker}+stock'
rrr = r",\\\"" + ticker + \
      r"\\\",\\\"(?P<price>([1-9]*)|(([0-9]*)\.([0-9]*)))\\\","
current = {}

driver = webdriver.Chrome(chrome_options=chrome_options)
driver.get(gurl)


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
    F = int(F.replace('°', ''))
    C = round((F-32)*5/9, 1)
    return f'{F}°F {C}°C'


bft_threshold = (
    1.01, 3.01, 7.01, 12.01, 18.01, 24.01, 31.01, 38.01, 40.01, 54.01, 55.01, 72.01)
def wind_beaufort(mph):
    if mph is None:
        return None

    # if we have a wind phrase - purify
    mph = float(re.findall(r'\b\d+\b', f'{mph}')[0])
    for bft, val in enumerate(bft_threshold):
        if mph < val:
            return bft
    return len(bft_threshold)


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
                        t = conds.find(class_=lk).text.replace('°', '°F')
                    current[lk.replace('today_nowcard-', '')] = f'{t}'

                try:
                    for icons in conds.find_all('icon', attrs={"class":"icon-svg"}):
                        icon = re.findall(r'icon-\d+', f'{icons}')[0]
                        current['icon'] = f'{icon}'
                except:
                    pass

                for caption in soup.find_all('caption'):
                    if 'Right Now' == caption.get_text():
                        for row in caption.find_parent('table').find_all('tr'):
                            key = row.find('th').getText().lower()
                            val = row.find_all('td')[0].text.strip()
                            current[key] = val
                            if 'wind' == key:
                                current['beafort'] = wind_beaufort(val)

                try:
                    sun = soup.find(class_='dp-details')
                    current['sunrise'] = sun.find('span',attrs={"class":"wx-dsxdate","id":"dp0-details-sunrise"}).text.strip()
                    current['sunset'] = sun.find('span',attrs={"class":"wx-dsxdate","id":"dp0-details-sunset"}).text.strip()
                except:
                    pass

                try:
                    lookahead = soup.find(class_='looking-ahead')
                    try:
                        for lookperiod in lookahead.find_all('div', attrs={"class":re.compile('today-daypart daypart-\d+.*'),"id":re.compile('daypart-\d+')}):
                            looker = {}
                            period = re.findall(r'daypart-\d+',f'{lookperiod}')[0]
                            pid = period.replace('daypart-','')
                            looker['id'] = pid
                            ptitle = lookperiod.find('span',attrs={"class":"today-daypart-title"}).text.strip()
                            looker['label'] = ptitle
                            philo = lookperiod.find('div',attrs={"id":f'dp{pid}-highLow'}).text.strip()
                            looker['hilo'] = philo
                            ptemp = lookperiod.find('div',attrs={"class":'today-daypart-temp'}).text.strip()
                            looker['temperature'] = ptemp
                            pcntprecip = lookperiod.find('span',attrs={"class":"precip-val"}).text.strip()
                            looker['pcntprecip'] = pcntprecip
                            try:
                                for icons in lookperiod.find_all('icon', attrs={"class":re.compile("icon icon-svg.*")}):
                                    icon = re.findall(r'icon-\d+', f'{icons}')[0]
                                    looker['icon'] = icon
                            except:
                                pass
                            current[period] = looker
                    except:
                        pass
                except:
                    pass

    except:
        current = cache
        print('Fetch exception [weather]')


def not_market_holiday():
    from datetime import datetime
    import pandas as pd
    stdt = datetime.now().isoformat()
    early = nyse.schedule(start_date=stdt, end_date=stdt)
    return nyse.open_at_time(early, pd.Timestamp(stdt, tz=nyse.tz.zone))


def cache_dad_joke():
    global current
    cache = current
    hurl = 'https://icanhazdadjoke.com'
    try:
        with requests.get(hurl, headers={'Accept': 'application/json'}) as url:
            if 200 == url.status_code:
                current['joke'] = url.json()['joke']
    except:
        current = cache


def cache_google_stock():
    global current
    cache = current
    import traceback
    if not_market_holiday():
        try:
            # expensive ???
            driver.refresh()
            page = driver.page_source
            price = float(re.findall(rrr, page, re.MULTILINE)[0][0])
            current['ticker'] = ticker
            current['price'] = price
        except:
            current = cache
            print(f'Scrape exception [ticker] {ticker}')
            traceback.print_exc()


def cache_stock():
    global current
    cache = current
    import json
    import traceback
    if not_market_holiday():
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
                            current['price'] = \
                                js['stocks']['inventory'][ticker]['price']
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
        cache_google_stock()
        sc = perpetualTimer(120, cache_google_stock)
        sc.start()
        cache_dad_joke()
        jc = perpetualTimer(120, cache_dad_joke)
        jc.start()
        app.run(host='0.0.0.0')

    except KeyboardInterrupt:
        jc.cancel()
        sc.cancel()
        wc.cancel()
        driver.quit()

driver.quit()
