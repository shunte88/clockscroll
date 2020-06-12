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

rrr = r"jsname=\"\S+\"\>(?P<price>([1-9]*)|(([0-9]*)\.([0-9]*)))\<\/span\>"

# nasdaq replacement
#gurl = f'https://www.nasdaq.com/market-activity/stocks/{ticker}'
#rrr = r'\<span class="symbol-page-header__pricing-price"\>\$(?P<price>([1-9]*)|(([0-9]*)\.([0-9]*)))\<\/span\>'

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

                # retool 2020-06-10
                soup = BeautifulSoup(url.text, 'lxml')
                conds = soup.find('div',attrs={"data-testid":"CurrentConditionsContainer"})
                current['temp'] = lazyFtoC(conds.find('span',attrs={"data-testid":"TemperatureValue"}).text.strip())
                current['phrase'] = conds.find('div',attrs={"data-testid":"wxPhrase"}).text.strip()

                try:
                    for icons in conds.find_all('svg', attrs={"data-testid":"Icon"}):
                        icon = re.findall(r'skycode="\d+"', f'{icons}')[0]
                        icon = icon.replace('skycode="','icon-').replace('"','')
                        current['icon'] = f'{icon}'
                except:
                    pass

                conds = soup.find('div',attrs={"data-testid":"FeelsLikeSection"})
                current['feels'] = conds.find('span',attrs={"data-testid":"TemperatureValue"}).text.strip().replace('°','°F')

                sun = soup.find('div',attrs={"data-testid":"sunriseSunsetContainer"})
                current['sunrise'] = sun.find('div',attrs={"data-testid":"SunriseValue"}).text.strip()
                current['sunset'] = sun.find('div',attrs={"data-testid":"SunsetValue"}).text.strip()

                conds = soup.find('section',attrs={"data-testid":"TodaysDetailsModule"})

                for today in conds.find_all('div', attrs={"data-testid":"WeatherDetailsListItem"}):
                    key = today.find('div',attrs={"data-testid":"WeatherDetailsLabel"}).text.strip().lower()
                    if 'high / low' == key:
                        key = 'hilo'
                    val = today.find('div',attrs={"data-testid":"wxData"}).text.strip()
                    current[key] = val.replace('°','°F')
                    if 'wind' == key:
                        current['beafort'] = wind_beaufort(val)
                        direction = re.findall(r'rotate\(\d+deg\)', f'{today}')
                        if direction:
                            blows = direction[0].replace('rotate(','').replace('deg)','')
                            current['winddegrees'] = f"{blows}"
                            blows = degToCompass(int(blows))
                            current['wind'] = f"{blows} {current['wind']}"

                try:
                    lookahead = soup.find('section',attrs={"data-testid":"DailyWeatherModule"})
                    try:
                        pid = 0
                        for lp in lookahead.find_all('a'):
                            looker = {}
                            ptitle = lp.find('span',attrs={"style":"-webkit-line-clamp:2"}).text.strip()
                            looker['label'] = ptitle
                            hitemp = lp.find('div',attrs={"data-testid":"SegmentHighTemp"}).text.strip()
                            lotemp = lp.find('div',attrs={"data-testid":"SegmentLowTemp"}).text.strip()
                            looker['hilo'] = f'{hitemp}/{lotemp}'
                            looker['temperature'] = f'{hitemp}'
                            looker['id'] = pid
                            pcntprecip = lp.find('div',attrs={"data-testid":"SegmentPrecipPercentage"}).text.strip()
                            looker['pcntprecip'] = pcntprecip
                            try:
                                for icons in conds.find_all('svg', attrs={"data-testid":"Icon","set":"weather"}):
                                    icon = re.findall(r'skycode="\d+"', f'{icons}')[0]
                                    icon = icon.replace('skycode="','icon-').replace('"','')
                                    looker['icon'] = f'{icon}'
                            except:
                                pass

                            period = f'daypart-{pid}'
                            current[period] = looker
                            pid += 1
                    except:
                        pass
                except:
                    pass
                '''
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
                '''
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
            price = float(re.findall(rrr, page, re.MULTILINE)[0])
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
        app.run(host='0.0.0.0')

    except KeyboardInterrupt:
        print('Cleanup')
        c19.cancel()
        jc.cancel()
        sc.cancel()
        wc.cancel()
        driver.quit()

driver.quit()
print('Done.')
