#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Husqvarna Python Plugin
#
# Author: Filip Demaertelaere
#
# Plugin manage the Husqvarna Mower. It gives the status of the mower and allows
# to execute actions (start mowing, parking, ...)
#
"""
<plugin key="Husqvarna" name="Husqvarna" author="Filip Demaertelaere" version="1.0.0">
    <description>
        <h2>Husqvarna</h2>
        This Husqvarna plugin makes use of the offical Husqvarna API.<br/>
        Consult https://developer.husqvarnagroup.cloud/applications for more information<br/>
        and to create the credientials for using the API. This gives you a client_id (or application_id)<br/>
        and a client_secret (or an application_secret). Enter both in the settings below...<br/><br/>
        Note that polling interval is reduced to once per hour when the mower is OFF (eg in winter).<br/><br/>
    </description>
    <params>
        <param field="Mode1" label="Client_id" width="250px" required="true" default=""/>
        <param field="Mode2" label="Client_secret" width="250px" required="true" default="" password="true"/>
        <param field="Mode5" label="Update interval" width="120px" required="true" default="1"/>
        <param field="Mode6" label="Debug" width="120px">
            <options>
                <option label="None" value="0" default="true"/>
                <option label="Python Only" value="2"/>
                <option label="Basic Debugging" value="62"/>
                <option label="Basic+Messages" value="126"/>
                <option label="Queue" value="128"/>
                <option label="Connections Only" value="16"/>
                <option label="Connections+Queue" value="144"/>
                <option label="All" value="-1"/>
            </options>
        </param>
    </params>
</plugin>
"""

#IMPORTS
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
import DomoticzEx as Domoticz
from domoticzEx_tools import *
from datetime import datetime, timedelta
import Husqvarna
import threading
import queue
import time
import json

#DEVICES
STATE = 1
STATE_TEXT = 'State'
RUN = 2
RUN_TEXT = 'Run'
BATTERY = 3
BATTERY_TEXT = 'Battery Level'
ACTIONS = 4
ACTIONS_TEXT = 'Actions'
LOCATION = 5
LOCATION_TEXT = 'Location'
CUTTING = 6
CUTTING_TEXT = 'Cutting Height (cm)'

#UPDATE SPEED
STATUS_SPEED_NORMAL = 0
STATUS_SPEED_NIGHT = 1
STATUS_SPEED_LIMITS_EXCEEDED = 2
STATUS_SPEED_ALL_OFF = 3

#DEFAULT IMAGE
_IMAGE = 'Husqvarna'
_IMAGE_INVERSE = 'Husqvarna_Inverse'
_IMAGE_OFF = 'Husqvarna_Off'

#EXECUTION STATUS
EXECUTION_STATUS_INITIATED = 0
EXECUTION_STATUS_DONE = 1
EXECUTION_STATUS_ERROR = 2

#ACTIONS
LOGIN = 'Login'
GET_MOWERS = 'GetMowers'
GET_STATUS = 'GetStatus'
START = 'Start'
START_6h = 'Start (6h)'
PAUSE = 'Pause'
RESUME_SCHEDULE = 'Resume Schedule'
PARK_UNTIL_FURTHER_NOTICE = 'Park Until Further Notice'
PARK_UNTIL_NEXT_SCHEDULE = 'Park Until Next Schedule'
SET_CUTTING_HEIGHT = 'Set Cutting Height'

################################################################################
# Start Plugin
################################################################################

class BasePlugin:

    def __init__(self):
        self.runAgain = MINUTE
        self.Stop = False
        self.speed_status = STATUS_SPEED_NORMAL
        self.execution_status_last_action = {}
        self.MyHusqvarna = None
        self.zones = []
        self.height_min_max = {}
        self.file_gps_coordinates = None
        self.tasksQueue = queue.Queue()
        self.tasksThread = threading.Thread(name='QueueThread', target=BasePlugin.handleTasks, args=(self,))

    def onStart(self):
        Domoticz.Debug('onStart called')

        # Debugging
        if Parameters["Mode6"] != '0':
            try:
                Domoticz.Debugging(int(Parameters["Mode6"]))
                DumpConfigToLog(Parameters, Devices)
            except:
                pass
        
        # Read technical parameters
        Domoticz.Debug('Looking for configuration file {}Husqvarna.json'.format(Parameters['HomeFolder']))
        try:
            config = None
            with open(f"{Parameters['HomeFolder']}Husqvarna.json") as json_file:
                config = json.load(json_file)
            self.zones = config['zones']
            self.height_min_max = config['height_min_max (cm)']
            Domoticz.Debug(f'Zones found: {self.zones}.')
        except:
            pass

        # Check if images are in database
        if _IMAGE not in Images:
            Domoticz.Image('Husqvarna.zip').Create()
        if _IMAGE_INVERSE not in Images:
            Domoticz.Image('Husqvarna_Inverse.zip').Create()
        if _IMAGE_OFF not in Images:
            Domoticz.Image('Husqvarna_Off.zip').Create()
        
        # Start thread
        self.tasksThread.start()
        self.tasksQueue.put({'Action': LOGIN})
        self.tasksQueue.put({'Action': GET_MOWERS})
        self.tasksQueue.put({'Action': GET_STATUS})

    def onStop(self):
        Domoticz.Debug('onStop called')
        self.Stop = True
        
        # Signal queue thread to exit
        self.tasksQueue.put(None)
        if self.tasksThread and self.tasksThread.is_alive():
            self.tasksThread.join()

        # Wait until queue thread has exited
        Domoticz.Debug(f'Threads still active: {threading.active_count()} (should be 1)')
        endTime = time.time() + 70
        while (threading.active_count() > 1) and (time.time() < endTime):
            for thread in threading.enumerate():
                if thread.name != threading.current_thread().name:
                    Domoticz.Debug(f'Thread {thread.name} is still running, waiting otherwise Domoticz will abort on plugin exit.')
            time.sleep(1.0)

        Domoticz.Debug('Plugin stopped')

    def onConnect(self, Connection, Status, Description):
        Domoticz.Debug(f'onConnect called ({Connection.Name}) with status={Status}')

    def onMessage(self, Connection, Data):
        Domoticz.Debug(f"onMessage called: {Connection.Name} - {Data['Status']}")

    def onCommand(self, DeviceID, Unit, Command, Level, Color):
        if self.Stop: return
        Domoticz.Debug(f'onCommand called for DeviceID/Unit: {DeviceID}/{Unit} - Parameter: {Command} - Level: {Level}')
        if ( mower := self.MyHusqvarna.get_mower_from_name(DeviceID) ):
            if mower['state'] != 'OFF':
                if Unit == RUN:
                    if Command == 'On':
                        self.execution_status_last_action[DeviceID]['status'] = EXECUTION_STATUS_INITIATED
                        self.execution_status_last_action[DeviceID]['retries'] = 0
                        if mower['activity'] == 'CHARGING':
                            self.execution_status_last_action[DeviceID]['status'] = EXECUTION_STATUS_DONE
                            Domoticz.Status(f"Mower {mower['name']} cannot be started as it is still charging.")
                        else:
                            self.execution_status_last_action[DeviceID]['action'] = RESUME_SCHEDULE #START
                            UpdateDevice(False, Devices, Unit, 1, 1)
                            self.tasksQueue.put({'Action': START, 'Mower_name': mower['name']})
                    else:
                        self.execution_status_last_action[DeviceID]['action'] = PARK_UNTIL_FURTHER_NOTICE
                        UpdateDevice(False, Devices, Unit, 0, 0)
                        self.tasksQueue.put({'Action': PARK_UNTIL_FURTHER_NOTICE, 'Mower_name': mower['name']})
                    
                elif Unit == CUTTING and Command == 'Set Level':
                    self.execution_status_last_action[DeviceID]['action'] = CUTTING
                    self.execution_status_last_action[DeviceID]['status'] = EXECUTION_STATUS_INITIATED
                    self.execution_status_last_action[DeviceID]['retries'] = 0
                    self.tasksQueue.put({'Action': SET_CUTTING_HEIGHT, 'Mower_name': mower['name'], 'Cutting_height': (Level/10)+1})
                
                elif Unit == ACTIONS and Command == 'Set Level' and Level:
                    self.execution_status_last_action[DeviceID]['status'] = EXECUTION_STATUS_INITIATED
                    self.execution_status_last_action[DeviceID]['retries'] = 0
                    if Level == 10:
                        if mower['activity'] == 'CHARGING':
                            self.execution_status_last_action[DeviceID]['status'] = EXECUTION_STATUS_DONE
                            Domoticz.Status(f"Mower {mower['name']} cannot be started as it is still charging.")
                        else:
                            self.execution_status_last_action[DeviceID]['action'] = START_6h
                            self.tasksQueue.put({'Action': START_6h, 'Mower_name': mower['name']})
                    elif Level == 20:
                        self.execution_status_last_action[DeviceID]['action'] = PAUSE
                        self.tasksQueue.put({'Action': PAUSE, 'Mower_name': mower['name']})
                    elif Level == 30:
                        self.execution_status_last_action[DeviceID]['action'] = RESUME_SCHEDULE
                        self.tasksQueue.put({'Action': RESUME_SCHEDULE, 'Mower_name': mower['name']})
                    elif Level == 40:
                        self.execution_status_last_action[DeviceID]['action'] = PARK_UNTIL_FURTHER_NOTICE
                        self.tasksQueue.put({'Action': PARK_UNTIL_FURTHER_NOTICE, 'Mower_name': mower['name']})
                    elif Level == 50:
                        self.execution_status_last_action[DeviceID]['action'] = PARK_UNTIL_NEXT_SCHEDULE
                        self.tasksQueue.put({'Action': PARK_UNTIL_NEXT_SCHEDULE, 'Mower_name': mower['name']})
            else:
                Domoticz.Error(f"Husqvarna mower {mower['name']} is switched off and cannot execute the command).") 
                        
        else:
            Domoticz.Error(f"Husqvarna mower {mower['name']} is not a valid mower (cannot be found in the list of connected mowers {self.MyHusqvarna.mowers}).") 
            TimeoutDevice(Devices, device_id=DeviceID)               
                
    def onDisconnect(self, Connection):
        Domoticz.Debug(f'onDisconnect called ({Connection.Name})')

    def onHeartbeat(self):
        if self.Stop: return

        self.runAgain -= 1
        if self.runAgain <= 0:
        
            if self.MyHusqvarna is None:
                self.tasksQueue.put({'Action': LOGIN})
            
            now = datetime.now()
            if self.MyHusqvarna.get_timestamp_last_update_mower_list() + timedelta(days=1) < now:
                self.tasksQueue.put({'Action': GET_MOWERS})
                
            self.tasksQueue.put({'Action': GET_STATUS})
            
            ## Retry for commands
            for mower in self.MyHusqvarna.mowers:
                if self.execution_status_last_action[mower['name']]['status'] == EXECUTION_STATUS_ERROR and self.execution_status_last_action[mower['name']]['retries'] < 2:
                    Domoticz.Status(f"Retry {self.execution_status_last_action[mower['name']]['retries']} for Husqvarna mower {mower['name']} to launch command/action {self.execution_status_last_action[mower['name']]['action']}.")
                    self.execution_status_last_action[mower['name']]['retries'] += 1
                    self.tasksQueue.put({'Action': self.execution_status_last_action[mower['name']]['action'], 'Mower_name': mower['name']})

            # Dynamic adaption of update time to reduce possibility throttling on reaching the API limits
            # This does not solve the problem of having reached the limit of 10000 requests/month (max: every 4-5 minutes)
            if self.MyHusqvarna.are_api_limits_reached():
                self.runAgain = max(60*MINUTE, self.runAgain)
                if self.speed_status != STATUS_SPEED_LIMITS_EXCEEDED:
                    Domoticz.Status(f'Reduce status update speed to {self.runAgain/MINUTE} minutes as Husqvarna API limits are reached!')
                    self.speed_status = STATUS_SPEED_LIMITS_EXCEEDED
            else:
                hours = now.hour
                if self.MyHusqvarna.are_all_mowers_off():
                    self.runAgain = 60*MINUTE    #slow down when mowers are off
                    if self.speed_status != STATUS_SPEED_ALL_OFF:
                        Domoticz.Status(f'Reduce status update speed to {self.runAgain/MINUTE} minutes as all Husqvarna mowers are off.')
                        self.speed_status = STATUS_SPEED_ALL_OFF
                elif hours >= 22 and hours <= 5:
                    self.runAgain = MINUTE*180   #limited status update during night
                    if self.speed_status != STATUS_SPEED_LIMITS_NIGHT:
                        Domoticz.Status(f'Reduce status update speed to {self.runAgain/MINUTE} minutes as all we are running into the night.')
                        self.speed_status = STATUS_SPEED_LIMITS_NIGHT
                else:                        
                    self.runAgain = MINUTE*float(Parameters['Mode5'].replace(',','.'))
                    if self.speed_status != STATUS_SPEED_NORMAL:
                        Domoticz.Status(f'Re-establish normal update speed to {self.runAgain/MINUTE} minutes.')
                        self.speed_status = STATUS_SPEED_NORMAL

    # Thread to handle the messages
    def handleTasks(self):
        try:
            Domoticz.Debug('Entering tasks handler')
            while True:
                task = self.tasksQueue.get(block=True)
                if task is None:
                    Domoticz.Debug('Exiting task handler')
                    try:
                        self.MyHusqvarna.close()
                        self.MyHusqvarna = None
                    except AttributeError:
                        pass
                    self.tasksQueue.task_done()
                    break

                Domoticz.Debug('Handling task: {}.'.format(task['Action']))
                if task['Action'] == LOGIN:
                    self.MyHusqvarna = Husqvarna.Husqvarna(Parameters['Mode1'], Parameters['Mode2'])
                    if not self.MyHusqvarna:
                        Domoticz.Error(f'Unable to get credentials from Husqvarna Cloud (Husqvarna description: {self.MyHusqvarna.get_http_error()}).')
                        TimeoutDevice(Devices)
                
                elif task['Action'] == GET_MOWERS:
                    if not self.MyHusqvarna.get_mowers():
                        Domoticz.Error(f'Error getting list of mowers from Husqvarna Cloud (Husqvarna description: {self.MyHusqvarna.get_http_error()}).')
                        TimeoutDevice(Devices)
                    else:
                        for mower in self.MyHusqvarna.mowers:
                            self.execution_status_last_action[mower['name']] = { 'status': None, 'action': None, 'mower': None, 'retries': 0 }

                elif task['Action'] == GET_STATUS:
                    if self.MyHusqvarna.get_mowers_info():
                        if self.MyHusqvarna.mowers:

                            for mower in self.MyHusqvarna.mowers:
                            
                                # Create mower if it does not exit in Domoticz
                                if not Devices.get(mower['name'], None):
                                    Domoticz.Unit(DeviceID=mower['name'], Unit=STATE, Name=f"{Parameters['Name']} - {mower['name']} - {STATE_TEXT}", TypeName='Text', Image=Images[_IMAGE].ID, Used=1).Create()
                                    Domoticz.Unit(DeviceID=mower['name'], Unit=RUN, Name=f"{Parameters['Name']} - {mower['name']} - {RUN_TEXT}", Type=244, Subtype=73, Switchtype=0, Image=Images[_IMAGE].ID, Used=1).Create()
                                    Domoticz.Unit(DeviceID=mower['name'], Unit=BATTERY, Name=f"{Parameters['Name']} - {mower['name']} - {BATTERY_TEXT}", TypeName='Custom', Options={'Custom': '0;%'}, Image=Images[_IMAGE].ID, Used=0).Create()
                                    height_interval = (self.height_min_max['max']-self.height_min_max['min'])/(self.height_min_max['steps']-1)
                                    height_range = [self.height_min_max['min']+i*height_interval for i in range(self.height_min_max['steps'])]
                                    LevelNamesStr = '|'.join(map(lambda n: '{:.1f}'.format(n), height_range))
                                    Domoticz.Unit(DeviceID=mower['name'], Unit=LOCATION, Name=f"{Parameters['Name']} - {mower['name']} - {LOCATION_TEXT}", TypeName='Text', Image=Images[_IMAGE].ID, Used=1).Create()
                                    Domoticz.Unit(DeviceID=mower['name'], Unit=CUTTING, Name=f"{Parameters['Name']} - {mower['name']} - {CUTTING_TEXT}", TypeName='Selector Switch', Options={'LevelActions': '|'*(self.height_min_max['steps']-1), 'LevelNames': LevelNamesStr, 'LevelOffHidden': 'false', 'SelectorStyle': '0'}, Image=Images[_IMAGE].ID, Used=1).Create()
                                    Domoticz.Unit(DeviceID=mower['name'], Unit=ACTIONS, Name=f"{Parameters['Name']} - {mower['name']} - {ACTIONS_TEXT}", TypeName='Selector Switch', Options={'LevelActions': '|||||', 'LevelNames': '|{}|{}|{}|{}|{}'.format(START_6h, PAUSE, RESUME_SCHEDULE, PARK_UNTIL_FURTHER_NOTICE, PARK_UNTIL_NEXT_SCHEDULE), 'LevelOffHidden': 'false', 'SelectorStyle': '1'}, Image=Images[_IMAGE].ID, Used=1).Create()
                                    TimeoutDevice(Devices, device_id=mower['name'])

                                # Update state of the mower
                                Text = '{}: {}\n<body><p style="line-height:80%;font-size:80%;">({})</p></body>'.format(mower['state'], mower['activity'], mower['error_state'].strip()) if mower['error_state'] else '{}'.format(mower['state']) if mower['activity'] == 'NOT_APPLICABLE' else '{}: {}'.format(mower['state'], mower['activity'])
                                Image = Images[_IMAGE_OFF].ID if mower['state'] == 'OFF' else Images[_IMAGE].ID
                                UpdateDevice(False, Devices, mower['name'], STATE, 0, Text, Image=Image)

                                # Busy mowing or not
                                Image = Images[_IMAGE_OFF].ID if mower['state'] == 'OFF' else Images[_IMAGE].ID
                                if mower['activity'] in ['LEAVING', 'MOWING', 'GOING_HOME', 'CHARGING']:
                                    UpdateDevice(False, Devices, mower['name'], RUN, 1, 1, Image=Image, BatteryLevel=mower['battery_pct'])
                                else:
                                    UpdateDevice(False, Devices, mower['name'], RUN, 0, 0, Image=Image, BatteryLevel=mower['battery_pct'])

                                # Battery level
                                Image = Images[_IMAGE_OFF].ID if mower['state'] == 'OFF' else Images[_IMAGE].ID
                                UpdateDevice(False, Devices, mower['name'], BATTERY, mower['battery_pct'], mower['battery_pct'], Image=Image)

                                # Location in garden
                                Image = Images[_IMAGE_OFF].ID if mower['state'] == 'OFF' else Images[_IMAGE].ID
                                if mower['activity'] in ['MOWING"', 'GOING_HOME', 'LEAVING', 'PARKED_IN_CS', 'STOPPED_IN_GARDEN', 'PAUSED']:
                                    zone = self._find_nearest_by_zone(mower['location'], self.zones) if 'location' in mower else 'Unknown'
                                else:
                                    zone = GetDevicesValue(Devices, mower['name'], LOCATION)                                
                                UpdateDevice(False, Devices, mower['name'], LOCATION, 0, zone, Image=Image)

                                # Cutting height
                                Image = Images[_IMAGE_OFF].ID if mower['state'] == 'OFF' else Images[_IMAGE].ID
                                if mower['cutting_height']:
                                    UpdateDevice(False, Devices, mower['name'], CUTTING, 2, 10*(mower['cutting_height']-1), Image=Image)

                                # Actions
                                Image = Images[_IMAGE_OFF].ID if mower['state'] == 'OFF' else Images[_IMAGE_INVERSE].ID
                                UpdateDevice(True, Devices, mower['name'], ACTIONS, 2, 0, Image=Image)

                        else:
                            Domoticz.Error('No Husvarna mowers available in the list.')
                            TimeoutDevice(Devices)

                    else:
                        Domoticz.Error(f'Error getting detailed status of mowers from Husqvarna Cloud (Husqvarna description: {self.MyHusqvarna.get_http_error()}).')
                        TimeoutDevice(Devices)

                else:
                    status = None
                    if task['Action'] == START:
                        #Start until further notice (24 hours)
                        if self.MyHusqvarna.is_mower_off(task['Mower_name']) == False:
                           status = self.MyHusqvarna.action_Start(task['Mower_name'], duration=1440)

                    elif task['Action'] == START_6h:
                        #Start for 6 hours
                        if self.MyHusqvarna.is_mower_off(task['Mower_name']) == False:
                            status = self.MyHusqvarna.action_Start(task['Mower_name'], duration=360)

                    elif task['Action'] == PARK_UNTIL_FURTHER_NOTICE:
                        if self.MyHusqvarna.is_mower_off(task['Mower_name']) == False:
                            status = self.MyHusqvarna.action_ParkUntilFurtherNotice(task['Mower_name'])

                    elif task['Action'] == PARK_UNTIL_NEXT_SCHEDULE:
                        if self.MyHusqvarna.is_mower_off(task['Mower_name']) == False:
                            status = self.MyHusqvarna.action_ParkUntilNextSchedule(task['Mower_name'])
                    
                    elif task['Action'] == PAUSE:
                        if self.MyHusqvarna.is_mower_off(task['Mower_name']) == False:
                            status = self.MyHusqvarna.action_Pause(task['Mower_name'])

                    elif task['Action'] == RESUME_SCHEDULE:
                        if self.MyHusqvarna.is_mower_off(task['Mower_name']) == False:
                            status = self.MyHusqvarna.action_ResumeSchedule(task['Mower_name'])

                    elif task['Action'] == SET_CUTTING_HEIGHT:
                        if self.MyHusqvarna.is_mower_off(task['Mower_name']) == False:
                            status = self.MyHusqvarna.set_cutting_height(task['Mower_name'], task['Cutting_height'])

                    if status is None:
                        Domoticz.Error(f"TaskHandler: unknown action code {task['Action']}.")
                    elif status:
                        self.execution_status_last_action[task['Mower_name']]['status'] = EXECUTION_STATUS_DONE
                    else:
                        Domoticz.Error(f"Error Husqvarna mower {task['Mower_name']} on action ({task['Action']}): {self.MyHusqvarna.get_http_error()}")
                        TimeoutDevice(Devices, device_id=task['Mower_name'])
                        self.execution_status_last_action[task['Mower_name']]['status'] = EXECUTION_STATUS_ERROR
                    self.runAgain = MINUTE/2

                Domoticz.Debug(f"Finished handling task: {task['Action']}.")
                self.tasksQueue.task_done()

        except Exception as err:
            Domoticz.Error(f'General error TaskHandler: {err}')
            # For debugging
            import traceback
            Domoticz.Debug('Login error TRACEBACK: {traceback.format_exc()}')
            with open(f"{Parameters['HomeFolder']}Husqvarna_traceback.txt", "a") as myfile:
                myfile.write(f'{traceback.format_exc()}')
                myfile.write('---------------------------------\n')
            self.tasksQueue.task_done()

    def _find_nearest_by_zone(self, position, zones):
        SortedZonesByDistance = sorted(zones, key=lambda d: getDistance((position['latitude'], position['longitude']), (d["latitude"], d["longitude"])))
        return SortedZonesByDistance[0]['name']

global _plugin
_plugin = BasePlugin()

def onStart():
    global _plugin
    _plugin.onStart()

def onStop():
    global _plugin
    _plugin.onStop()

def onConnect(Connection, Status, Description):
    global _plugin
    _plugin.onConnect(Connection, Status, Description)

def onMessage(Connection, Data):
    global _plugin
    _plugin.onMessage(Connection, Data)

def onCommand(DeviceID, Unit, Command, Level, Color):
    global _plugin
    _plugin.onCommand(DeviceID, Unit, Command, Level, Color)

def onDisconnect(Connection):
    global _plugin
    _plugin.onDisconnect(Connection)

def onHeartbeat():
    global _plugin
    _plugin.onHeartbeat()

################################################################################
# Specific helper functions
################################################################################

