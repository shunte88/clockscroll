# clockscroll

Simple scrolling clock using Pimironi [scrollphathd]

The clock is run on a Raspberry Pi W

The clock maintains time by making NTP calls daily

The clock has the following functionality:

* Current time
* Current date on the hour
* Weather conditions via the Accuweather [API]
* Display brightness is controlled based on sunrise and sunset

To use the Accuweather [API] you require an API key

The key should be defined as an environment variable

See the code for details

[scrollphathd]: https://shop.pimoroni.com/products/scroll-phat-hd
[API]: https://developer.accuweather.com/apis