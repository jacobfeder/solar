# script for simulating the cost of a solar installation + [optional] battery 

# Jacob Feder 3/13/2021

import numpy as np
import datetime
import calendar
import csv
import types
import matplotlib.pyplot as plt

# simulation time step size (hr)
time_step = 1

class SolarPanel:
    def __init__(self, name, power_stc, tcp, degradation, nmot, efficiency):
        """simulates a solar panel"""
        # string identifier
        self.name = name
        # power output (kW) (initial condition is at rated standard test condition)
        self.power = power_stc
        # temperature coefficient of power (1/C, negative)
        self.tcp = tcp
        # annual degradation rate (unitless, positive)
        self.degradation = degradation
        # nominal module operating temperature
        self.nmot = nmot
        # efficiency of non-panel electronics (inverter, other losses)
        self.efficiency = efficiency

class Battery:
    def __init__(self, name, capacity, max_power, efficiency):
        """simulates a battery"""
        # string identifier
        self.name = name
        # useable capacity (kWh)
        self.capacity = capacity
        # inverter max power rating continuous (kW)
        self.max_power = max_power
        # battery round-trip efficiency
        self.efficiency = efficiency
        # current state of charge (unitless, 0-1)
        self.soc = 0

class EnergyPlan:
    def __init__(self, name, usage_cost, total_cost):
        """simulates an energy usage plan"""
        # string identifier
        self.name = name
        # reset state variables
        self.reset()
        # function that updates the usage cost for a single hour
        self.calc_usage_cost = types.MethodType(usage_cost, self)
        # function that calculates the total cost of the plan for the simulated period
        self.calc_total_cost = types.MethodType(total_cost, self)

    def reset(self):
        # peak power usage at any point in the simulated period (kW) (used in E-27 plan)
        self.peak = 0
        # peak power usage (during peak hours) for each simulated day (kWh) (used in E-15 plan)
        self.daily_peaks = []
        # accumulated usage cost in the past billing period
        self.usage_cost = 0

def kelvin(c):
    """convert C to K"""
    return c + 273.15

def celsius(k):
    """convert K to C"""
    return k - 273.15

# TODO unverified
def solar_sim(panel, irr, temp_a):
    """calculate the energy output (kWh) of a solar panel in a single time step"""
    # irradiance at standard test conditions (kW/m^2)
    irr_stc = 1.0
    # standard test condition temperature (C)
    temp_stc = 25
    # nominal module operating temperature ambient temperature (C)
    temp_a_nmot = 20
    # nominal module operating temperature irradiance (kW/m^2)
    irr_nmot = 0.8
    # calculate panel temperature
    # https://www.homerenergy.com/products/pro/docs/latest/how_homer_calculates_the_pv_cell_temperature.html
# TODO
#    temp_p = (kelvin(temp_a) + (kelvin(panel.nmot) - kelvin(temp_a_nmot)) * (irr / irr_nmot) * (1 - panel.power*(1 - panel.tcp*temp_stc)/0.9)) / \
#             (1 + (kelvin(panel.nmot) - kelvin(temp_a_nmot)) * (irr / irr_nmot) * (panel.tcp * panel.power / 0.9))
    temp_p = 40
    # power output calculation
    # https://www.homerenergy.com/products/pro/docs/latest/how_homer_calculates_the_pv_array_power_output.html
    pout = panel.power * panel.efficiency * irr / irr_stc * (1 + panel.tcp * (temp_p - temp_stc))
    # calculate new solar panel efficiency considering degradation rate
    panel.power = panel.power * (1 - panel.degradation / (24*365))

    return pout * time_step

def battery_sim(battery, e_sys):
    """calculate the battery state of charge and any residual energy at a single time step;
    this only simulates 'stupid' batteries that use a greedy algorithm (no time-of-use optimization)"""

    # account for inverter max continuous power
    battery_emax = battery.max_power * time_step
    # energy returned after interaction with the battery
    e_resid = 0
    if e_sys > battery_emax:
        # extra energy not affected by the battery
        e_resid = e_sys - battery_emax
        # remaining rate-limited energy due to inverter limitation
        e_sys = battery_emax
    elif e_sys < -battery_emax:
        e_resid = e_sys - battery_emax
        e_sys = -battery_emax

    # total energy available to the battery in this time step
    e_tot = battery.soc * battery.capacity + e_sys
    if e_tot > battery.capacity:
        battery.soc = 1.0
        return e_resid + battery.efficiency * (e_tot - battery.capacity)
    elif e_tot < 0.0:
        battery.soc = 0.0
        return e_resid + e_tot
    else:
        if battery.capacity != 0:
            battery.soc = e_tot / battery.capacity
        return e_resid

###############
# parameters
###############

# https://www.srpnet.com/prices/pdfx/april2015/e13.pdf
def e13_usage(self, time, energy):
    """calculate the hourly cost of the SRP E-13 plan (ignores special holiday hours)"""
    # importing energy from the grid
    if energy > 0:
        # summer (peak)
        if time.month == 7 or time.month == 8:
            # on-peak hours weekdays 2pm-8pm
            if time.hour >= 14 and time.hour < 20 and time.weekday() < 5:
                self.usage_cost += energy * 0.2409
            # off-peak hours
            else:
                self.usage_cost += energy * 0.0730
        # winter
        elif time.month <= 4 or time.month >= 11:
            # on-peak hours weekdays 2pm-8pm
            if ((time.hour >= 5 and time.hour < 9) or (time.hour >= 17 and time.hour < 21)) and time.weekday() < 5:
                self.usage_cost += energy * 0.0951
            # off-peak hours
            else:
                self.usage_cost += energy * 0.0691
        # summer
        else:
            # on-peak hours weekdays 2pm-8pm
            if time.hour >= 14 and time.hour < 20 and time.weekday() < 5:
                self.usage_cost += energy * 0.2094
            # off-peak hours
            else:
                self.usage_cost += energy * 0.0727
    # exporting energy to the grid
    else:
        self.usage_cost += energy * 0.0281

def e13_total(self, time):
    """calculate the cost of the SRP E13 plan for the simulated period"""
    service_charge = 32.44
    if self.usage_cost > 0.0:
        total_cost = service_charge + self.usage_cost
    else:
        total_cost = service_charge
    self.reset()
    return total_cost

# https://www.srpnet.com/prices/pdfx/april2015/e15.pdf
def e15_usage(self, time, energy):
    """calculate the hourly cost of the SRP E13 plan (ignores special holiday hours)"""
    if time.hour == 0:
        self.daily_peaks.append(0.0)
    # summer (peak)
    if time.month == 7 or time.month == 8:
        # on-peak hours weekdays 2pm-8pm
        if time.hour >= 14 and time.hour < 20 and time.weekday() < 5:
            self.usage_cost += energy * 0.0622
            if energy > self.daily_peaks[-1]:
                self.daily_peaks[-1] = energy
        # off-peak hours
        else:
            self.usage_cost += energy * 0.0412
    # winter
    elif time.month <= 4 or time.month >= 11:
        # on-peak hours weekdays 2pm-8pm
        if ((time.hour >= 5 and time.hour < 9) or (time.hour >= 17 and time.hour < 21)) and time.weekday() < 5:
            self.usage_cost += energy * 0.0410
            if energy > self.daily_peaks[-1]:
                self.daily_peaks[-1] = energy
        # off-peak hours
        else:
            self.usage_cost += energy * 0.0370
    # summer
    else:
        # on-peak hours weekdays 2pm-8pm
        if time.hour >= 14 and time.hour < 20 and time.weekday() < 5:
            self.usage_cost += energy * 0.0462
            if energy > self.daily_peaks[-1]:
                self.daily_peaks[-1] = energy
        # off-peak hours
        else:
            self.usage_cost += energy * 0.0360

def e15_total(self, time):
    """calculate the cost of the SRP E15 plan for the simulated billing period"""
    service_charge = 32.44

    # calculate average daily peak charge
    # summer (peak)
    if time.month == 7 or time.month == 8:
        average_peak_charge = np.mean(self.daily_peaks) * 21.94
    # winter
    elif time.month <= 4 or time.month >= 11:
        average_peak_charge = np.mean(self.daily_peaks) * 19.29
    # summer
    else:
        average_peak_charge = np.mean(self.daily_peaks) * 8.13

    # calculate total charge
    if self.usage_cost + average_peak_charge > 0.0:
        total_cost = service_charge + self.usage_cost + average_peak_charge
    else:
        total_cost = service_charge

    self.reset()
    return total_cost

# TODO
# https://www.srpnet.com/prices/pdfx/April2015/E-27.pdf
def e27(self):
    pass

# solar panel options
panels = [SolarPanel('None', 0, 0, 0, 0, 0),
          SolarPanel('LG', 0.335*0.98, -0.0036, 0.0033, 42.0, 0.95), # https://www.lg.com/us/business/download/resources/CT00002151/LG335N1K-V5_FinalVer051520[20200527_003458].pdf
          SolarPanel('REC', 0.330*0.975, -0.0034, 0.007, 44.6, 0.95), # https://recgroup.global.ssl.fastly.net/sites/default/files/documents/ds_rec_twinpeak_3_mono_black_series_en_us.pdf
          SolarPanel('SILFAB', 0.330*0.98, -0.00377, 0.006, 43.5, 0.95)] # https://silfabsolar.com/wp-content/uploads/2020/09/Silfab-SIL-330-BL-20200910-Final.pdf

batteries = [Battery('None', 0, 0, 0),
             Battery('Tesla', 13.5, 5, 0.9)]

plans = [EnergyPlan('E13', e13_usage, e13_total),\
         EnergyPlan('E15', e15_usage, e15_total)]#,\
         #EnergyPlan('E27', e27_usage, e27_total)]

# solar irradiance data file
# https://pvwatts.nrel.gov/pvwatts.php
# make sure to set roof location, tilt, azimuth - other parameters don't matter
weather_data_filename = 'pvwatts_hourly.csv'

# utility data file
load_data_filename = 'hourlyUsage1_1_2020_to_12_31_2020.csv'
# year for the load simulation data
year = 2020

# number of years for the simulation to run (uses the same data as 'year' and repeats)
num_years = 1

###############
# simulation
###############

# remove quotation marks from the files
for filename in [weather_data_filename, load_data_filename]:
    with open(filename, 'r+') as f:
        data = f.read()
        f.seek(0)
        f.write(data.replace('"', ''))
        f.truncate()

# simulation results
results = {}

with open(weather_data_filename, newline='') as solar_data_file,\
     open(load_data_filename, newline='') as load_data_file:
    # import solar irradiance data
    solar_data = list(csv.reader(solar_data_file))[18:-1]
    # import energy usage data from utility
    load_data = list(csv.reader(load_data_file))[1:]
    # iterate over all possible equipment combinations
    for panel in panels:
        for battery in batteries:
            for plan in plans:
                monthly_bills = []
                today = datetime.date(year, 1, 1)
                end_date = datetime.date(year + num_years, 1, 1)
                while today < end_date:
                    # day index (1-366)
                    day_idx = today.timetuple().tm_yday

                    load_data_today = load_data[day_idx]
                    # load data looks like ['1/1/2020', '12:0 am', '1.2']
                    load_data_time = datetime.strptime(f'{load_data_now[0]} {load_data_now[1]}', '%m/%d/%Y %I:%M %p')
                    if load_data_time.timetuple().tm_yday != day_idx:
                        #
                        solar_data_now = solar_data[i]

                        raise ValueError('solar and utility date/time mismatch')

                    # Plane of Array Irradiance (kW/m^2)
                    irradiance = float(solar_data_now[7]) / 1000.0
                    # ambient temperature (C)
                    temp = float(solar_data_now[5])
                    # month number (1-12)
                    month = int(solar_data_now[0])
                    # day number of month (1-31)
                    day = int(solar_data_now[1])
                    # hour of the day (1-24)
                    hour = int(solar_data_now[2])
                    # today as a date object
                    solar_data_time = datetime(year, month, day, hour, minute=0)

                    load = float(load_data_now[2])

                    # calculate energy input/output from/to the grid
                    grid_energy = - battery_sim(battery, solar_sim(panel, irradiance, temp) - load)
                    plan.calc_usage_cost(load_data_time, grid_energy)
                    # if it's the last time step of the month, calculate the bill
                    if day == calendar.monthrange(year, month)[1] and hour == 23:
                        monthly_bills.append(plan.calc_total_cost(load_data_time))
                    today += datetime.timedelta(days=1)
                results[f'{panel.name}:{battery.name}:{plan.name}'] = monthly_bills

for r in results:
    total = np.sum(results[r])
    monthly_mean = np.mean(results[r])
    print(f'{r} mean bill: {monthly_mean:.2f} total: {total:.2f}')
    # import pdb; pdb.set_trace()

import pdb; pdb.set_trace()
plot_name = 'LG:None:E13'
np.arange(1,len(results[r]), 1)
plt.bar(list(range(len(results[r]))) + 1, results[r], color='green')
plt.xlabel('Month')
plt.ylabel('Cost')
plt.title(plot_name)
plt.show()
