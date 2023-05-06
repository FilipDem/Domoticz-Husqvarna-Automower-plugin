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
        <param field="Mode5" label="Minutes between update" width="120px" required="true" default="1"/>
        <param field="Mode6" label="Debug" width="120px">
            <options>
                <option label="True" value="Debug"/>
                <option label="False" value="Normal" default="True"/>
            </options>
        </param>
    </params>
</plugin>
"""

#IMPORTS
import sys, os
major,minor,x,y,z = sys.version_info
sys.path.append('/usr/lib/python3/dist-packages')
sys.path.append('/usr/local/lib/python{}.{}/dist-packages'.format(major, minor))
sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from domoticz_tools import *
from datetime import datetime, timedelta
import Domoticz
import Husqvarna
import threading
import queue
import time
import re

#DEVICES
STATE = 'State'
RUN = 'Run'
BATTERY = 'Battery Level'
ACTIONS = 'Actions'

#UPDATE SPEED
STATUS_SPEED_NORMAL = 0
STATUS_SPEED_NIGHT = 1
STATUS_SPEED_LIMITS_EXCEEDED = 2
STATUS_SPEED_ALL_OFF = 3

#DEFAULT IMAGE
_IMAGE = 'Husqvarna'
_IMAGE_INVERSE = 'Husqvarna_Inverse'
_IMAGE_OFF = 'Husqvarna_Off'

#ACTIONS
LOGIN = 'Login'
GET_MOWERS = 'GetMowers'
GET_STATUS = 'GetStatus'
START = 'Start (10h)'
PAUSE = 'Pause'
RESUME_SCHEDULE = 'Resume Schedule'
PARK_UNTIL_FURTHER_NOTICE = 'Park Until Further Notice'
PARK_UNTIL_NEXT_SCHEDULE = 'Park Until Next Schedule'

################################################################################
# Start Plugin
################################################################################

class BasePlugin:

    def __init__(self):
        self.debug = DEBUG_OFF
        self.runAgain = MINUTE
        self.speed_status = STATUS_SPEED_NORMAL
        self.MyHusqvarna = None
        self.tasksQueue = queue.Queue()
        self.tasksThread = threading.Thread(name='QueueThread', target=BasePlugin.handleTasks, args=(self,))

    def onStart(self):
        Domoticz.Debug('onStart called')

        # Debugging On/Off
        self.debug = DEBUG_ON_NO_FRAMEWORK if Parameters['Mode6'] == 'Debug' else DEBUG_OFF
        Domoticz.Debugging(self.debug)
        if self.debug == DEBUG_ON:
            DumpConfigToLog(Parameters, Devices)
        
        # Check if images are in database
        if _IMAGE not in Images:
            Domoticz.Image('Husqvarna.zip').Create()
        if _IMAGE_INVERSE not in Images:
            Domoticz.Image('Husqvarna_Inverse.zip').Create()
        if _IMAGE_OFF not in Images:
            Domoticz.Image('Husqvarna_Off.zip').Create()

        # Timeout all devices
        TimeoutDevice(Devices, All=True)
        
        # Start thread
        self.tasksThread.start()
        self.tasksQueue.put({'Action': LOGIN})
        self.tasksQueue.put({'Action': GET_MOWERS})
        self.tasksQueue.put({'Action': GET_STATUS})

    def onStop(self):
        Domoticz.Debug('onStop called')
        
        # Signal queue thread to exit
        self.tasksQueue.put(None)
        if self.tasksThread and self.tasksThread.is_alive():
            self.tasksThread.join()

        # Wait until queue thread has exited
        Domoticz.Debug('Threads still active: {} (should be 1)'.format(threading.active_count()))
        endTime = time.time() + 70
        while (threading.active_count() > 1) and (time.time() < endTime):
            for thread in threading.enumerate():
                if thread.name != threading.current_thread().name:
                    Domoticz.Debug('Thread {} is still running, waiting otherwise Domoticz will abort on plugin exit.'.format(thread.name))
            time.sleep(1.0)

        Domoticz.Debug('Plugin stopped')

    def onConnect(self, Connection, Status, Description):
        Domoticz.Debug('onConnect called ({}) with status={}'.format(Connection.Name, Status))

    def onMessage(self, Connection, Data):
        Domoticz.Debug("onMessage called: {} - {}".format(Connection.Name, Data['Status']))

    def onCommand(self, Unit, Command, Level, Hue):
        Domoticz.Debug('onCommand called for Unit: {} ({}) - Parameter: {} - Level: {}'.format(Unit, Devices[Unit].Name, Command, Level))
        if Devices[Unit].Name.endswith(RUN) or Devices[Unit].Name.endswith(ACTIONS):
            try:
                mower_name = ''
                if Devices[Unit].Name.endswith(RUN):
                    mower_name = re.search('{} - (.*?) - {}'.format(Parameters['Name'], RUN), Devices[Unit].Name)[1]
                elif Devices[Unit].Name.endswith(ACTIONS):
                    mower_name = re.search('{} - (.*?) - {}'.format(Parameters['Name'], ACTIONS), Devices[Unit].Name)[1]
                Domoticz.Debug('Mower found to send command to ({}).'.format(mower_name))
                found = False
                for mower in self.MyHusqvarna.mowers:
                    if mower['name'] == mower_name:
                        found = True
                        if Devices[Unit].Name.endswith(RUN):
                            if Command == 'On':
                                if mower['activity'] == 'CHARGING':
                                    Domoticz.Status('Mower {} cannot be started as it is still charging.'.format(mower['name']))
                                else:
                                    UpdateDevice(False, Devices, Unit, 1, 1)
                                    self.tasksQueue.put({'Action': START, 'Mower_name': mower_name})
                            else:
                                UpdateDevice(False, Devices, Unit, 0, 0)
                                self.tasksQueue.put({'Action': PARK_UNTIL_FURTHER_NOTICE, 'Mower_name': mower_name})
                        elif Devices[Unit].Name.endswith(ACTIONS) and Command == 'Set Level' and Level:
                            if Level == 10:
                                if mower['activity'] == 'CHARGING':
                                    Domoticz.Status('Mower {} cannot be started as it is still charging.'.format(mower['name']))
                                else:
                                    self.tasksQueue.put({'Action': START, 'Mower_name': mower_name})
                            elif Level == 20:
                                self.tasksQueue.put({'Action': PAUSE, 'Mower_name': mower_name})
                            elif Level == 30:
                                self.tasksQueue.put({'Action': RESUME_SCHEDULE, 'Mower_name': mower_name})
                            elif Level == 40:
                                self.tasksQueue.put({'Action': PARK_UNTIL_FURTHER_NOTICE, 'Mower_name': mower_name})
                            elif Level == 50:
                                self.tasksQueue.put({'Action': PARK_UNTIL_NEXT_SCHEDULE, 'Mower_name': mower_name})
                if not found:
                    Domoticz.Error('"{}" is not a valid mower (cannot be found in the list of connected mowers "{}").'.format(mower_name, self.MyHusqvarna.mowers)) 
                    TimeoutDevicesByName(Devices, mower_name)               
            except:
                Domoticz.Debug('Error executing the action.')
                
    def onNotification(self, Name, Subject, Text, Status, Priority, Sound, ImageFile):
        Domoticz.Debug('Notification: {}, {}, {}, {}, {}, {}, {}'.format(
            Name, Subject, Text, Status, Priority, Sound, ImageFile
        ))

    def onDisconnect(self, Connection):
        Domoticz.Debug('onDisconnect called ({})'.format(Connection.Name))

    def onHeartbeat(self):
        self.runAgain -= 1
        if self.runAgain <= 0:
        
            if self.MyHusqvarna is None:
                self.tasksQueue.put({'Action': LOGIN})
            
            now = datetime.now()
            if self.MyHusqvarna.get_timestamp_last_update_mower_list() + timedelta(days=1) < now:
                self.tasksQueue.put({'Action': GET_MOWERS})
                
            self.tasksQueue.put({'Action': GET_STATUS})
            # Dynamic adaption of update time to reduce possibility throttling on reaching the API limits
            # This does not solve the problem of having reached the limit of 10000 requests/month (max: every 4-5 minutes)
            if self.MyHusqvarna.are_api_limits_reached():
                self.runAgain = max(60*MINUTE, self.runAgain)
                if self.speed_status != STATUS_SPEED_LIMITS_EXCEEDED:
                    Domoticz.Status('Reduce status update speed to {} minutes as Husqvarna API limits are reached'.format(self.runAgain/MINUTE))
                    self.speed_status = STATUS_SPEED_LIMITS_EXCEEDED
            else:
                hours = now.hour
                if self.MyHusqvarna.are_all_mowers_off():
                    self.runAgain = 60*MINUTE    #slow down when mowers are off
                    if self.speed_status != STATUS_SPEED_ALL_OFF:
                        Domoticz.Status('Reduce status update speed to {} minutes as all Husqvarna mowers are off.'.format(self.runAgain/MINUTE))
                        self.speed_status = STATUS_SPEED_ALL_OFF
                elif hours >= 22 and hours <= 5:
                    self.runAgain = MINUTE*180   #limited status update during night
                    if self.speed_status != STATUS_SPEED_LIMITS_NIGHT:
                        Domoticz.Status('Reduce status update speed to {} minutes as all we are running into the night.'.format(self.runAgain/MINUTE))
                        self.speed_status = STATUS_SPEED_LIMITS_NIGHT
                else:                        
                    self.runAgain = MINUTE*float(Parameters['Mode5'].replace(',','.'))
                    if self.speed_status != STATUS_SPEED_NORMAL:
                        Domoticz.Status('Re-establish normal update speed to {} minutes.'.format(self.runAgain/MINUTE))
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
                        Domoticz.Error('Unable to get credentials from Husqvarna Cloud (Husqvarna description: {}).'.format(self.MyHusqvarna.get_http_error()))
                        TimeoutDevice(Devices, All=True)
                
                elif task['Action'] == GET_MOWERS:
                    if not self.MyHusqvarna.get_mowers():
                        Domoticz.Error('Error getting list of mowers from Husqvarna Cloud (Husqvarna description: {}).'.format(self.MyHusqvarna.get_http_error()))
                        TimeoutDevice(Devices, All=True)

                elif task['Action'] == GET_STATUS:
                    if self.MyHusqvarna.get_mowers_info():
                        if self.MyHusqvarna.mowers:
                           
                            for mower in self.MyHusqvarna.mowers:
                            
                                # Status of Mower
                                Unit = FindUnitFromName(Devices, Parameters, '{} - {}'.format(mower['name'], STATE))
                                if not Unit:
                                    Unit = GetNextFreeUnit(Devices)
                                    Domoticz.Device(Unit=Unit, Name='{} - {}'.format(mower['name'], STATE), TypeName='Text', Image=Images[_IMAGE].ID, Used=1).Create()
                                    TimeoutDevice(Devices, Unit=Unit)
                                if mower['error_state']:
                                    Error = mower['error_state'].replace('\r', '').replace('\n', '')
                                    Text = '{}: {}\n(<body><p style="line-height:80%;font-size:80%;">{}</p></body>)'.format(mower['state'], mower['activity'], Error)
                                else:
                                    Text = '{}'.format(mower['state']) if mower['activity'] == 'NOT_APPLICABLE' else '{}: {}'.format(mower['state'], mower['activity'])
                                if mower['state'] == 'OFF':
                                    Image = Images[_IMAGE_OFF].ID
                                else:
                                    Image = Images[_IMAGE].ID if mower['activity'] in ['LEAVING', 'MOWING'] else Images[_IMAGE_INVERSE].ID
                                UpdateDevice(False, Devices, Unit, 0, Text, Image=Image)

                                # Busy mowing or not
                                Unit = FindUnitFromName(Devices, Parameters, '{} - {}'.format(mower['name'], RUN))
                                if not Unit:
                                    Unit = GetNextFreeUnit(Devices)
                                    Domoticz.Device(Unit=Unit, Name='{} - {}'.format(mower['name'], RUN), Type=244, Subtype=73, Switchtype=0, Image=Images[_IMAGE].ID, Used=1).Create()
                                    TimeoutDevice(Devices, Unit=Unit)
                                Image = Images[_IMAGE_OFF].ID if mower['state'] == 'OFF' else Images[_IMAGE].ID
                                if mower['activity'] in ['LEAVING', 'MOWING']:
                                    UpdateDevice(False, Devices, Unit, 1, 1, Image=Image)
                                else:
                                    UpdateDevice(False, Devices, Unit, 0, 0, Image=Image)
                                UpdateDeviceBatSig(False, Devices, Unit, BatteryLevel=mower['battery_pct'])

                                # Battery level
                                Unit = FindUnitFromName(Devices, Parameters, '{} - {}'.format(mower['name'], BATTERY))
                                if not Unit:
                                    Unit = GetNextFreeUnit(Devices)
                                    Domoticz.Device(Unit=Unit, Name='{} - {}'.format(mower['name'], BATTERY), TypeName='Custom', Options={'Custom': '0;%'}, Image=Images[_IMAGE].ID, Used=0).Create()
                                if mower['state'] == 'OFF':
                                    Image = Images[_IMAGE_OFF].ID
                                else:
                                    Image = Images[_IMAGE].ID if mower['activity'] in ['LEAVING', 'MOWING'] else Images[_IMAGE_INVERSE].ID
                                UpdateDevice(False, Devices, Unit, mower['battery_pct'], mower['battery_pct'], Image=Image)

                                # Actions
                                Unit = FindUnitFromName(Devices, Parameters, '{} - {}'.format(mower['name'], ACTIONS))
                                if not Unit:
                                    Unit = GetNextFreeUnit(Devices)
                                    Domoticz.Device(Unit=Unit, Name='{} - {}'.format(mower['name'], ACTIONS), TypeName='Selector Switch', Options={'LevelActions': '|||||', 'LevelNames': '|{}|{}|{}|{}|{}'.format(START, PAUSE, RESUME_SCHEDULE, PARK_UNTIL_FURTHER_NOTICE, PARK_UNTIL_NEXT_SCHEDULE), 'LevelOffHidden': 'false', 'SelectorStyle': '1'}, Image=Images[_IMAGE].ID, Used=1).Create()
                                if mower['state'] == 'OFF':
                                    Image = Images[_IMAGE_OFF].ID
                                else:
                                    Image = Images[_IMAGE].ID if mower['activity'] in ['LEAVING', 'MOWING'] else Images[_IMAGE_INVERSE].ID
                                UpdateDevice(True, Devices, Unit, 2, 0, Image=Image)

                        else:
                            Domoticz.Error('No Husvarna mowers available in the list.')
                            TimeoutDevice(Devices, All=True)

                    else:
                        Domoticz.Error('Error getting detailed status of mowers from Husqvarna Cloud (Husqvarna description: {}).'.format(self.MyHusqvarna.get_http_error()))
                        TimeoutDevice(Devices, All=True)

                elif task['Action'] == START:
                    #Start for 10 hours
                    if self.MyHusqvarna.is_mower_off(task['Mower_name']) == False and not self.MyHusqvarna.action_Start(task['Mower_name'], 600):
                        Domoticz.Error('Error Husqvarna {} on Start Action: {}'.format(task['Mower_name'], self.MyHusqvarna.get_http_error()))
                        TimeoutDevicesByName(Devices, task['Mower_name'])
                    self.runAgain = 2*MINUTE

                elif task['Action'] == PARK_UNTIL_FURTHER_NOTICE:
                    if self.MyHusqvarna.is_mower_off(task['Mower_name']) == False and not self.MyHusqvarna.action_ParkUntilFurtherNotice(task['Mower_name']):
                        Domoticz.Error('Error Husqvarna {} on ParkUntilFurtherNotice action: {}'.format(task['Mower_name'], self.MyHusqvarna.get_http_error()))
                        TimeoutDevicesByName(Devices, task['Mower_name'])
                    self.runAgain = 2*MINUTE

                elif task['Action'] == PARK_UNTIL_NEXT_SCHEDULE:
                    if self.MyHusqvarna.is_mower_off(task['Mower_name']) == False and not self.MyHusqvarna.action_ParkUntilNextSchedule(task['Mower_name']):
                        Domoticz.Error('Error Husqvarna {} on ParkUntilNextSchedule action: {}'.format(task['Mower_name'], self.MyHusqvarna.get_http_error()))
                        TimeoutDevicesByName(Devices, task['Mower_name'])
                    self.runAgain = 2*MINUTE
                    
                elif task['Action'] == PAUSE:
                    if self.MyHusqvarna.is_mower_off(task['Mower_name']) == False and not self.MyHusqvarna.action_Pause(task['Mower_name']):
                        Domoticz.Error('Error Husqvarna {} on Pause action: {}'.format(task['Mower_name'], self.MyHusqvarna.get_http_error()))
                        TimeoutDevicesByName(Devices, task['Mower_name'])
                    self.runAgain = 2*MINUTE

                elif task['Action'] == RESUME_SCHEDULE:
                    if self.MyHusqvarna.is_mower_off(task['Mower_name']) == False and not self.MyHusqvarna.action_ResumeSchedule(task['Mower_name']):
                        Domoticz.Error('Error Husqvarna {} on ResumeSchedule action: {}'.format(task['Mower_name'], self.MyHusqvarna.get_http_error()))
                        TimeoutDevicesByName(Devices, task['Mower_name'])
                    self.runAgain = 2*MINUTE

                else:
                    Domoticz.Error('TaskHandler: unknown action code {}'.format(task['Action']))

                Domoticz.Debug('Finished handling task: {}.'.format(task['Action']))
                self.tasksQueue.task_done()

        except Exception as err:
            Domoticz.Error('General error TaskHandler: {}'.format(err))
            # For debugging
            import traceback
            Domoticz.Debug('Login error TRACEBACK: {}'.format(traceback.format_exc()))
            with open('{}Husqvarna_traceback.txt'.format(Parameters['HomeFolder']), "a") as myfile:
                myfile.write('{}'.format(traceback.format_exc()))
                myfile.write('---------------------------------\n')
            self.tasksQueue.task_done()


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

def onCommand(Unit, Command, Level, Hue):
    global _plugin
    _plugin.onCommand(Unit, Command, Level, Hue)

def onNotification(Name, Subject, Text, Status, Priority, Sound, ImageFile):
    global _plugin
    _plugin.onNotification(Name, Subject, Text, Status, Priority, Sound, ImageFile)

def onDisconnect(Connection):
    global _plugin
    _plugin.onDisconnect(Connection)

def onHeartbeat():
    global _plugin
    _plugin.onHeartbeat()

################################################################################
# Specific helper functions
################################################################################
