#!/usr/bin/python3

import os
import sys

from flask import Flask, jsonify
from bs4 import BeautifulSoup
import requests
import re
import numpy as np

from threading import Timer, Thread, Event

import pandas_market_calendars as mcal

from selenium import webdriver
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options

chrzopt = Options()
chrzopt.headless = True

driver = webdriver.Chrome(ChromeDriverManager().install(), chrome_options=chrzopt)

# want the exchange that the stock trades on - q&d here
nyse = mcal.get_calendar('NYSE')

refresh = int(os.getenv('WEATHER_CACHE_REFRESH', 5))
wurl = os.getenv('WEATHER_CACHE_URI',
                 'https://weather.com/weather/today/l/02139:4:US')
ticker = os.getenv('WEATHER_CACHE_TICKER', 'AAPL')
spurl = f'https://stocktwits.com/symbol/{ticker}'
gurl = f'https://google.com/search?q={ticker}+stock+price'

rrr = r"jsname=\"\S+\" class=\".*?\"\>(?P<price>([1-9]*)|(([0-9]*)\.([0-9]*)))\<\/span\>\<span jsname=\"\S+\" class="

current = {}

#driver = webdriver.Chrome(chrome_options=chrome_options)
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
    mph = float(mph) # addressed 21/01/2021
    for bft, val in enumerate(bft_threshold):
        if mph < val:
            return bft
    return len(bft_threshold)


def degToCompass(num):
    val=int((num/22.5)+.5)
    arr=["N","NNE","NE","ENE","E","ESE", "SE", "SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"]
    return arr[(val % 16)]


def cache_weather():
    global current
    cache = current
    try:
        with requests.get(wurl) as url:
            if 200 == url.status_code:

                soup = BeautifulSoup(url.text, 'lxml')
                conds = soup.find('div',attrs={"data-testid":"CurrentConditionsContainer"})

                current['temp'] = lazyFtoC(conds.find('span',attrs={"data-testid":"TemperatureValue"}).text.strip())
                current['phrase'] = conds.find('div',attrs={"data-testid":"wxPhrase"}).text.strip()

                try:
                    for icons in conds.find_all('svg', attrs={"data-testid":"Icon"}):
                        icon = re.match(r'.*skycode="(\d+)".*', f'{icons}')
                        if icon.group:
                            current['icon'] = f"icon-{icon.group(1)}"
                except:
                    pass

                conds = soup.find('div',attrs={"data-testid":"FeelsLikeSection"})
                current['feels'] = conds.find('span',attrs={"data-testid":"TemperatureValue"}).text.strip().replace('°','°F')

                sun = soup.find('div',attrs={"data-testid":"sunriseSunsetContainer"})
                current['sunrise'] = sun.find('div',attrs={"data-testid":"SunriseValue"}).text.strip()
                current['sunset'] = sun.find('div',attrs={"data-testid":"SunsetValue"}).text.strip()

                conds = soup.find('section',attrs={"data-testid":"TodaysDetailsModule"})

                # graphic name strings crept into the mix ~ 18/01/2021
                # wind direction, pressure mainly affected - minor retool
                for today in conds.find_all('div', attrs={"data-testid":"WeatherDetailsListItem"}):
                    key = today.find('div',attrs={"data-testid":"WeatherDetailsLabel"}).text.strip().lower()
                    if 'high / low' == key:
                        key = 'hilo'
                    val = today.find('div',attrs={"data-testid":"wxData"}).text.strip()
                    current[key] = val.replace('°','°F')
                    if 'wind' == key:
                        current[key] = re.findall(r'[\w|\b]\d+\b', f'{val}')[0][1]
                        current['beafort'] = wind_beaufort(current[key])
                        direction = re.match(r'.*rotate\((\d+)deg\).*', f'{today}')
                        if direction.group:
                            blows = direction.group(1)
                            current['wind degrees'] = int(blows)
                            blows = degToCompass(int(blows))
                            current['wind'] = f"{blows} {current['wind']}"

                    elif 'pressure' == key:
                        current[key] = re.findall(r'[^|\w|\b]\d+', f'{val}')[0][1] # deal with Arrow [Up|Down]

                    print(f"{key:} {(16-len(key)) * '.'}: {current[key]}")

                try:
                    lookahead = soup.find('section',attrs={"data-testid":"DailyWeatherModule"})
                    try:
                        pid = 0
                        for lp in lookahead.find_all('a'):
                            looker = {}
                            ptitle = lp.find('span',attrs={"style":"-webkit-line-clamp:2"}).text.strip()
                            looker['label'] = ptitle
                            hitemp = lp.find('div',attrs={"data-testid":"SegmentHighTemp"}).text.strip().replace('°','°F')
                            lotemp = lp.find('div',attrs={"data-testid":"SegmentLowTemp"}).text.strip().replace('°','°F')
                            looker['hilo'] = f'{hitemp}/{lotemp}'
                            looker['temperature'] = f'{hitemp}'
                            looker['id'] = pid
                            pcntprecip = lp.find('div',attrs={"data-testid":"SegmentPrecipPercentage"}).text.strip()
                            looker['pcntprecip'] = pcntprecip
                            try:
                                for icons in lp.find_all('svg', attrs={"data-testid":"Icon","set":"weather"}):
                                    icon = re.match(r'.*skycode="(\d+)".*', f'{icons}')
                                    if icon.group:
                                        looker['icon'] = f"icon-{icon.group(1)}"
                            except:
                                pass

                            period = f'daypart-{pid}'
                            current[period] = looker
                            pid += 1
                    except:
                        pass
                except:
                    pass

    except:
        current = cache
        print(f'Fetch exception [weather]\n{sys.exc_info()[0]}\n')


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


def getCovidAttr(c19attr):
    c19url = f'https://raw.githubusercontent.com/CSSEGISandData/COVID-19/master/csse_covid_19_data/csse_covid_19_time_series/time_series_19-covid-{c19attr}.csv'
    df={'names': ('Location', 'Country', c19attr),'formats': ('S128', 'S128', 'i')}
    with requests.get(c19url, headers={'Accept': 'application/text'}) as durl:
        if 200 == durl.status_code:
            dataset = np.genfromtxt(durl.content.decode('utf-8').splitlines(), dtype=df, delimiter=",", skip_header=True, usecols=(0, 1, -1))
            #####################dataset = np.loadtxt(durl.content.decode('utf-8').splitlines(), dtype=df, delimiter=",", skiprows=1, usecols=(0, 1, -1))
            return dataset[c19attr].sum()
    return -1


def cache_covid_attr():
    global current
    cache = current
    try:
        for attr in ('Confirmed','Recovered','Deaths'):
            val = getCovidAttr(attr)
            if val>0:
                current[f'c19-{attr.lower()}'] = int(val)
    except:
        print(f'Fetch exception [Covid-19]')
        current = cache


def cache_nasdaq_stock():
    global current
    cache = current
    import traceback
    if not_market_holiday():
        try:
            driver.refresh()
            page = driver.page_source
            pp = re.findall(rrr, page, re.MULTILINE)
            price = float(pp[0][0])
            current['price'] = price
            current['ticker'] = ticker
        except:
            current = cache
            print(f'Scrape exception [ticker] {ticker}')
            traceback.print_exc()

def cache_google_stock():
    # borked - now 100% JS render ???
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
    #print('Serve ...')
    #print(current)
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
        cache_covid_attr()
        c19 = perpetualTimer(60*60, cache_covid_attr) # too aggressive!
        c19.start()
        cache_dad_joke()
        jc = perpetualTimer(120, cache_dad_joke)
        jc.start()
        app.run(host='0.0.0.0', debug=True)

    except KeyboardInterrupt:
        print('Cleanup')
        c19.cancel()
        jc.cancel()
        sc.cancel()
        wc.cancel()
        driver.quit()

driver.quit()
print('Done.')
