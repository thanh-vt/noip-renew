#!/usr/bin/env python3
# Copyright 2017 loblab
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import base64
import os
import re
import subprocess
import sys
import time
import pyotp
from datetime import date
from datetime import timedelta

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By


class Logger:
    def __init__(self, level):
        self.level = 0 if level is None else level

    def log(self, msg, level=None):
        self.time_string_formatter = time.strftime('%Y/%m/%d %H:%M:%S', time.localtime(time.time()))
        self.level = self.level if level is None else level
        if self.level > 0:
            print(f"[{self.time_string_formatter}] - {msg}")


class Robot:
    USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.14; rv:64.0) Gecko/20100101 Firefox/64.0"
    LOGIN_URL = "https://www.noip.com/login"
    HOST_URL = "https://my.noip.com/dynamic-dns"
    SCREENSHOT_DIR = "screenshots/"

    def __init__(self, username, password, otp_secret, debug):
        self.debug = debug
        self.username = username
        self.password = password
        self.otp_secret = otp_secret
        self.browser = self.init_browser()
        self.logger = Logger(debug)
        is_exist = os.path.exists(Robot.SCREENSHOT_DIR)
        if not is_exist:
            # Create a new directory because it does not exist
            os.makedirs(Robot.SCREENSHOT_DIR)
            print("The screenshots directory is created!")

    @staticmethod
    def init_browser():

        options = webdriver.ChromeOptions()
        # added for Raspbian Buster 4.0+ versions. Check https://www.raspberrypi.org/forums/viewtopic.php?t=258019 for reference.
        options.add_argument("disable-features=VizDisplayCompositor")
        options.add_argument("headless")
        options.add_argument("no-sandbox")  # need when run in docker
        options.add_argument("window-size=1200x800")
        options.add_argument(f"user-agent={Robot.USER_AGENT}")
        if 'https_proxy' in os.environ:
            options.add_argument("proxy-server=" + os.environ['https_proxy'])
        service = Service(executable_path="/usr/bin/chromedriver")
        browser = webdriver.Chrome(options=options, service=service)
        # browser = webdriver.Chrome(options=options)
        browser.set_page_load_timeout(90)  # Extended timeout for Raspberry Pi.
        return browser

    def login(self):
        self.logger.log(f"Opening {Robot.LOGIN_URL}...")
        self.browser.get(Robot.LOGIN_URL)
        if self.debug > 1:
            self.browser.save_screenshot(Robot.SCREENSHOT_DIR + "debug1.png")
        decodedPassword = base64.b64decode(self.password).decode('utf-8')
        self.logger.log(f"Logging in with username={self.username}, password={decodedPassword}...")
        self.browser.find_element(By.ID, "toggle-password").click()
        ele_usr = self.browser.find_element(By.NAME, "username")
        ele_pwd = self.browser.find_element(By.NAME, "password")
        ele_usr.clear()
        ele_usr.click()
        ele_usr.send_keys(self.username)
        ele_pwd.clear()
        ele_pwd.click()
        ele_pwd.send_keys(decodedPassword)
        self.browser.find_element(By.ID, "clogs-captcha-button").click()

        if self.debug > 1:
            time.sleep(5)
            self.browser.save_screenshot(Robot.SCREENSHOT_DIR + "debug2.png")
            time.sleep(5)
            retry = 0
            while True:
                ele_otp = self.get_otp_input()
                if ele_otp is None:
                    self.browser.save_screenshot(Robot.SCREENSHOT_DIR + "debug3.png")
                    break
                totp = pyotp.TOTP(self.otp_secret)
                otp = totp.now()
                ele_otp.send_keys(otp)
                self.browser.save_screenshot(Robot.SCREENSHOT_DIR + "debug3.png")
                ele_confirm = self.browser.find_element(By.XPATH, "//input[(@type='submit') and (@value = 'Verify')]")
                ele_confirm.click()
                time.sleep(10)
                retry += 1
                ele_otp = self.get_otp_input()
                if ele_otp is None or retry > 5:
                    self.browser.save_screenshot(Robot.SCREENSHOT_DIR + "debug4.png")
                    break

    def get_otp_input(self):
        try:
            ele_otp = self.browser.find_element(By.XPATH,
                                                "//input[contains(@placeholder, 'Enter the 6-digit code')]")
            return ele_otp
        except NoSuchElementException:
            return None

    def update_hosts(self):
        count = 0

        self.open_hosts_page()
        time.sleep(5)
        iteration = 1
        next_renewal = []

        hosts = self.get_hosts()
        for host in hosts:
            host_link = self.get_host_link(host, iteration)  # This is for if we wanted to modify our Host IP.
            host_button = self.get_host_button(host, iteration)  # This is the button to confirm our free host
            host_name = host_link.text
            expiration_days = self.get_host_expiration_days(host, iteration)
            next_renewal.append(expiration_days)
            self.logger.log(f"{host_name} expires in {str(expiration_days)} days")
            if expiration_days <= 7:
                self.update_host(host_button, host_name)
                count += 1
            iteration += 1
        self.browser.save_screenshot(Robot.SCREENSHOT_DIR + "results.png")
        self.logger.log(f"Confirmed hosts: {count}", 2)
        nr = min(next_renewal) - 6
        today = date.today() + timedelta(days=nr)
        day = str(today.day)
        month = str(today.month)
        subprocess.call(['/usr/local/bin/noip-renew-skd.sh', day, month, "True"])
        return True

    def open_hosts_page(self):
        self.logger.log(f"Opening {Robot.HOST_URL}...")
        try:
            self.browser.get(Robot.HOST_URL)
        except TimeoutException as e:
            self.browser.save_screenshot(Robot.SCREENSHOT_DIR + "timeout.png")
            self.logger.log(f"Timeout: {str(e)}")

    def update_host(self, host_button, host_name):
        self.logger.log(f"Updating {host_name}")
        host_button.click()
        time.sleep(3)
        intervention = False
        try:
            if self.browser.find_elements(By.XPATH, "//h2[@class='big']")[0].text == "Upgrade Now":
                intervention = True
        except:
            pass

        if intervention:
            raise Exception("Manual intervention required. Upgrade text detected.")

        self.browser.save_screenshot(Robot.SCREENSHOT_DIR + f"{host_name}_success.png")

    @staticmethod
    def get_host_expiration_days(host, iteration):
        try:
            host_remaining_days = host.find_element(By.XPATH, ".//a[@class='no-link-style']").text
        except:
            host_remaining_days = host.find_element(By.XPATH, ".//a[text()='Active']").get_attribute("data-original-title")
            pass
        regex_match = re.search("in (\\d+) day", host_remaining_days)
        if regex_match is None:
            raise Exception("Expiration days label does not match the expected pattern in iteration: {iteration}")
        expiration_days = int(regex_match.group(0))
        return expiration_days

    @staticmethod
    def get_host_link(host, iteration):
        return host.find_element(By.XPATH, ".//a[@class='link-info cursor-pointer']")

    @staticmethod
    def get_host_button(host, iteration):
        return host.find_element(By.XPATH, ".//following-sibling::td[5]/button[contains(@class, 'btn')]")

    def get_hosts(self):
        host_tds = self.browser.find_elements(By.XPATH, "//td[@data-title=\"Host\"]")
        if len(host_tds) == 0:
            raise Exception("No hosts or host table rows not found")
        return host_tds

    def run(self):
        rc = 0
        self.logger.log(f"Debug level: {self.debug}")
        try:
            self.login()
            if not self.update_hosts():
                rc = 3
        except Exception as e:
            self.logger.log(str(e))
            self.browser.save_screenshot(Robot.SCREENSHOT_DIR + "exception.png")
            subprocess.call(['/usr/local/bin/noip-renew-skd.sh', "*", "*", "False"])
            rc = 2
        finally:
            self.browser.quit()
        return rc


def main(argv=None):
    noip_username, noip_password, noip_otp_secret, debug = get_args_values(argv)
    return (Robot(noip_username, noip_password, noip_otp_secret, debug)).run()


def get_args_values(argv):
    if argv is None:
        argv = sys.argv
    if len(argv) < 4:
        print(f"Usage: {argv[0]} <noip_username> <noip_password> <noip_otp_secret> [<debug-level>] ")
        sys.exit(1)

    noip_username = argv[1]
    noip_password = argv[2]
    noip_otp_secret = argv[3]
    debug = 1
    if len(argv) > 4:
        debug = int(argv[4])
    return noip_username, noip_password, noip_otp_secret, debug


if __name__ == "__main__":
    sys.exit(main())
