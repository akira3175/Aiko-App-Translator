"""Portable Chrome and ChromeDriver selection."""

import os

from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager


def create_chrome_service(portable_driver, driver_manager_factory=ChromeDriverManager):
    if os.path.isfile(portable_driver):
        return Service(portable_driver)
    return Service(driver_manager_factory().install())


def apply_portable_chrome(options, portable_chrome):
    if os.path.isfile(portable_chrome):
        options.binary_location = portable_chrome
