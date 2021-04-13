# scrape data from pvoutput.org

from pathlib import Path
import time
import datetime
import csv
import random

from selenium import webdriver # conda install selenium
from bs4 import BeautifulSoup # conda install beautifulsoup4

from pvoutput_user_info import user_pass

headless = True

# sid of solar data set e.g. sid = '64456' for
# AZ Panasonic 330 + Enphase 7.920kW
# https://pvoutput.org/intraday.jsp?id=72624&sid=64456
sid = '64456'

# data file
filename = 'solar_data.csv'

# pvoutput.org login page
login_url = 'https://pvoutput.org/login.jsp'

# firefox selenium driver
driver_path = Path(__file__).resolve().parent / 'geckodriver'
# set headless mode
head_option = webdriver.FirefoxOptions()
if headless:
    head_option.add_argument('-headless')
# start driver
driver = webdriver.Firefox(executable_path='./geckodriver', options=head_option)

# navigate to the login URL
driver.get(login_url)
# fill in account info
username, password = user_pass() # function that returns ('pvoutput username', 'pvoutput password')
login_form = driver.find_element_by_id('login')
login_form.send_keys(username)
login_form = driver.find_element_by_id('password')
login_form.send_keys(password)
# login
login_form.submit()
# wait for page load
time.sleep(1.0)

year = 2020
# start date of data to collect
today = datetime.date(year, 1, 1)
# end date of data to collect
end_date = datetime.date(year + 1, 1, 1)
# interval between data points (min)
data_interval = 5
# iterate through live data and save it to a csv file
with open(filename, 'w') as csvfile:
    csvwriter = csv.writer(csvfile, delimiter=',')
    while today < end_date:
        url = f'https://pvoutput.org/intraday.jsp?id=0&sid={sid}&dt={today.year}{today.month:02}{today.day - 1:02}&gs=0&m=1'

        # navigate to data url
        driver.get(url)
        try:
            table = driver.find_element_by_id('tbl_main')
        except Exception as e:
            # the captcha got us
            print(today)
            raise e
        table_html = table.get_attribute('innerHTML')

        # parse html table data
        soup = BeautifulSoup(table_html, 'html.parser')
        # keys: hours of the day, values: array of different powers in that hour
        power_data = {}
        for row in soup.find_all('tr'):
            # iterate through each column in the row and collect it's text value
            cols = []
            for col in row.find_all('td'):
                cols.append(col.get_text())
            if len(cols) == 12:
                # hour of data point
                hour = int(cols[1].split(':')[0])
                # power during this period
                try:
                    power = float(cols[4].replace('W', '').replace(',', ''))
                except:
                    power = 0
                if hour not in power_data:
                    power_data[hour] = []
                power_data[hour].append(power)
        # average power data for each hour of the day
        for i in range(24):
            hourly_power = '0'
            if i in power_data:
                # average of data points over the hour (unreported times assumed 0)
                hourly_power = str(sum(power_data[i]) / (60/data_interval))
            # write data to the file
            csvwriter.writerow([today.year, today.month, today.day, i, hourly_power])
        # wait to prevent rate-limiting
        time.sleep(6 + random.uniform(0, 0.5))
        # move on to the next day
        today += datetime.timedelta(days=1)

# close webdriver
driver.close()
