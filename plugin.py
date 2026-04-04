#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Husqvarna Mower Plugin for Domoticz

This plugin integrates Husqvarna robotic lawn mowers with Domoticz home automation system.
It provides monitoring of mower status, battery level, location, and control functions like
start/stop, parking, and cutting height adjustment.

Author: Filip Demaertelaere

"""

# Standard imports
import sys
import os
import datetime
import json
import threading
import queue
import time
from typing import Dict, List, Optional, Any, Tuple, Union, Set, cast
from enum import Enum, IntEnum, auto
from dataclasses import dataclass, field
from pathlib import Path

# Add the parent directory to the path for Domoticz imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

# Domoticz imports
import DomoticzEx as Domoticz
from domoticzEx_tools import (
    DomoticzConstants, dump_config_to_log, update_device, timeout_device,
    check_activity_units_and_timeout, get_device_s_value, get_device_n_value,
    get_unit, get_distance, log_backtrace_error
)

# Local imports
import Husqvarna

# XML plugin configuration
"""
<plugin key="Husqvarna" name="Husqvarna" author="Filip Demaertelaere" version="2.1.4">
    <description>
        <h2>Husqvarna</h2>
        <p>Version 2.1.4</p>
        <p>The Husqvarna plugin for Domoticz provides seamless integration with your Husqvarna robotic lawnmowers. Leveraging the official Husqvarna API, this plugin allows you to monitor your mower's status and control key functions directly from your Domoticz environment. It creates virtual devices for each connected mower, offering real-time insights into its activity, battery level, cutting height, and precise location.</p>
        <br/>
        <h2>Key features</h2>
        <ul>
            <li><b>Real-time Status Monitoring:</b> View your mower's current state (e.g., mowing, charging, parked, paused, off).</li>
            <li><b>Battery Level Indication:</b> Keep track of your mower's battery percentage.</li>
            <li><b>Location Tracking:</b> Based on GPS coordinates of your mower, with an option to display its proximity to predefined zones (e.g., "Front Garden", "Back Garden").</li>
            <li><b>Remote Control Actions:</b> Start mowing, pause operations, resume schedules, or park the mower (until further notice or next schedule).</li>
            <li><b>Cutting Height Adjustment:</b> Remotely set the cutting height of your mower.</li>
            <li><b>Next Schedule:</b> Shows the next upcoming scheduled mowing session.</li>
            <li><b>Zone Management:</b> Define custom zones for your property to get distance information and easily identify which zone your mower is currently in.</li>
            <li><b>Night Mode:</b> Automatically reduces polling frequency during configurable night hours to save API quota.</li>
        </ul>
        <p>The RUN device generates a command <b>resume schedule</b> (ON) and <b>park until further notice</b> (OFF). For a fluent integration and the ability to use the timer mechanism of Domoticz to manage the Husqvarna mower, define a full-day schedule (00:00-24:00) on the mower or in the Husqvarna app for the complete week.</p>
        <br/>
        <h2>Hardware Plugin Configuration</h2>
        <ul>
            <li><b>Client_id:</b> Your Husqvarna API client ID (also known as application ID). Obtain this from the Husqvarna Developer Portal: <a href="https://developer.husqvarnagroup.cloud/applications">https://developer.husqvarnagroup.cloud/applications</a>. You will need to create an application to get these credentials.</li>
            <li><b>Client_secret:</b> Your Husqvarna API client secret (also known as application secret). Obtain this from the Husqvarna Developer Portal, linked to your application. This should be kept confidential.</li>
            <li><b>Update interval:</b> The frequency, in minutes, at which the plugin will poll the Husqvarna API for status updates. A smaller interval means more frequent updates. The current restrictions mentioned on the Husqvarna Developer Portal are a rate limit of 120 requests per minute and a quota of 21000 requests per week (2 requests per minute for a week). Please note that if all configured mowers are detected as 'OFF' (e.g., during winter storage), the plugin will automatically reduce this polling interval to once per hour to minimize unnecessary API calls and save resources. Normal polling resumes when a mower becomes active again.</li>
            <li><b>Debug:</b> Select the level of debugging information to be logged to the Domoticz log. "None" is recommended for normal operation, while other options provide more detailed logs for troubleshooting and development.</li>
        </ul>
        <br/>
        <h2>Advanced Configuration (Husqvarna.json)</h2>
        <p>For advanced configurations such as defining specific zones for your mower or setting custom cutting height ranges, an optional configuration file named `Husqvarna.json` can be placed in the plugin's home folder.</p>
        <h3>Husqvarna.json content</h3>
        <ul>
            <li><b>zones:</b> List of dictionaries, defining a name of a zone and the coordinates of its center. The name of the zone is logged in Location device depending on the mowers location.</li>
            <li><b>height_min_max (cm):</b> Convertion table of the mowing height steps to centimeter. The number of steps can be found in the Husqvarna Mower App.</li>
            <li><b>update_interval (min):</b> Definition of interval time for mower updates in special cases/periods (eg mower is OFF, quota errors, ...).</li>
            <li><b>start_duration (min):</b> Mowing duration assigned to the "Start mowing" command.</li>
            <li><b>night_mode:</b> Optional. Defines the night period during which polling is slowed down. "start" and "end" are hours (0-23), "interval" is the polling interval in minutes during the night.</li>
        </ul>
        <br/>
        <h3>Example Husqvarna.json</h3>
        <pre><code>
{
    "zones": [
        { "name": "FrontGarden", "latitude": 50.8503, "longitude": 4.3517 },
        { "name": "BackGarden", "latitude": 50.8400, "longitude": 4.3400 }
    ],
    "height_min_max (cm)": { "min": 2, "max": 6, "steps": 9 },
    "update_interval (min)": { "off": 60, "cloud_error": 180, "quota_error": 30 },
    "start_duration (min)": 360,
    "night_mode": { "start": 22, "end": 6, "interval": 60 }
}
        </code></pre>
        <p>If this file is not present or is invalid, the plugin will revert to default values for zones (using Domoticz's configured title/location) and cutting height (min: 2, max: 6, steps: 9). Night mode defaults to 22:00-06:00 with a 60-minute interval if not specified.</p>
    </description>
    <params>
        <param field="Mode1" label="Client_id" width="250px" required="true" default=""/>
        <param field="Mode2" label="Client_secret" width="250px" required="true" default="" password="true"/>
        <param field="Mode5" label="Update interval" width="120px" required="true" default="2"/>
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

class UnitId(IntEnum):
    """Unit identifiers for Husqvarna mower devices in Domoticz."""
    STATE = 1
    RUN = 2
    BATTERY = 3
    ACTIONS = 4
    LOCATION = 5
    CUTTING = 6
    NEXT_SCHEDULE = 7

class DeviceText(str, Enum):
    """Text identifiers for device names."""
    STATE = 'State'
    RUN = 'Run'
    BATTERY = 'Battery Level'
    ACTIONS = 'Actions'
    LOCATION = 'Location'
    CUTTING = 'Cutting Height (cm)'
    NEXT_SCHEDULE = 'Next Schedule'

class ImageIdentifier(str, Enum):
    """Custom image identifiers for Husqvarna mower devices."""
    STANDARD = 'Husqvarna'
    OFF = 'HusqvarnaOff'

class UpdateSpeed(IntEnum):
    """Status update speed modes for the plugin."""
    NORMAL = 0
    NIGHT = 1
    LIMITS_EXCEEDED = 2
    ALL_OFF = 3
    SYSTEM_ERROR = 4

class ExecutionStatus(IntEnum):
    """Execution status values for mower commands."""
    INITIATED = 0
    DONE = 1
    ERROR = 2

class HusqvarnaAction(str, Enum):
    """Actions that can be performed on Husqvarna mowers."""
    LOGIN = 'Login'
    GET_MOWERS = 'GetMowers'
    GET_STATUS = 'GetStatus'
    SET_CUTTING_HEIGHT = 'SetCuttingHeight'
    START = Husqvarna.MowerAction.START.value
    PAUSE = Husqvarna.MowerAction.PAUSE.value
    RESUME_SCHEDULE = Husqvarna.MowerAction.RESUME_SCHEDULE.value
    PARK_UNTIL_FURTHER_NOTICE = Husqvarna.MowerAction.PARK_FURTHER_NOTICE.value
    PARK_UNTIL_NEXT_SCHEDULE = Husqvarna.MowerAction.PARK_NEXT_SCHEDULE.value

@dataclass
class MowerConfig:
    """Configuration for Husqvarna mowers from JSON file."""
    zones: List[Dict[str, Any]] = field(default_factory=list)
    height_min_max: Dict[str, Any] = field(default_factory=dict)
    update_interval: Dict[str, Any] = field(default_factory=dict)
    start_duration: int = field(default_factory=int)
    night_mode: Dict[str, Any] = field(default_factory=dict)  # Night mode configuration

@dataclass
class ExecutionState:
    """State tracking for command execution."""
    status: Optional[ExecutionStatus] = None
    action: Optional[HusqvarnaAction] = None
    command_data: Dict[str, Any] = field(default_factory=dict)
    retries: int = 0

class HusqvarnaPlugin:
    """Main plugin class for Husqvarna mower integration with Domoticz."""
    
    def __init__(self) -> None:
        """Initialize the plugin with default values."""
        self.run_again = DomoticzConstants.MINUTE
        self.stop_requested = False
        self.speed_status = UpdateSpeed.NORMAL
        self.system_retries = 0
        self.execution_status = {}  # type: Dict[str, ExecutionState]
        self.Husqvarna_api = None   # type: Optional[Husqvarna.Husqvarna]
        self.config = MowerConfig()
        self.tasks_queue = queue.Queue()
        self.tasks_thread = threading.Thread(
            name='QueueThread', 
            target=self._handle_tasks
        )

    def on_start(self) -> None:
        """Handle the plugin startup process."""
        Domoticz.Debug('onStart called')

        # Setup debugging if enabled
        self._setup_debugging()
        
        # Load configuration from file
        self._load_configuration()
        
        # Ensure custom images are available
        self._create_custom_images()
        
        # Start background task thread
        self.tasks_thread.start()
        
        # Initialize API and get mower data
        self.tasks_queue.put({'Action': HusqvarnaAction.LOGIN.value})
        self.tasks_queue.put({'Action': HusqvarnaAction.GET_MOWERS.value})
        self.tasks_queue.put({'Action': HusqvarnaAction.GET_STATUS.value})

    def _setup_debugging(self) -> None:
        """Set up debugging based on plugin parameters."""
        if Parameters["Mode6"] != '0':
            try:
                Domoticz.Debugging(int(Parameters["Mode6"]))
                dump_config_to_log(Parameters, Devices)
            except Exception as e:
                pass

    def _load_configuration(self) -> None:
        """Load mower configuration from JSON file."""
        config_file_path = Path(Parameters['HomeFolder']) / 'Husqvarna.json'
        Domoticz.Debug(f'Looking for configuration file {config_file_path}')
        try:
            # Default values if config file not found or invalid
            default_height_min_max = {"min": 2, "max": 6, "steps": 9}
            default_update_interval = { "off": 60, "cloud_error": 180, "quota_error": 30 }
            default_start_duration = 360
            default_night_mode = {"start": 22, "end": 6, "interval": 60}

            position_parts = Settings['Location'].split(';')
            # Check if position_parts has at least two elements and they can be converted to float
            if len(position_parts) >= 2 and all(isinstance(p, str) and p.strip().replace('.', '', 1).isdigit() for p in position_parts[:2]):
                default_zones = [{"name": Settings['Title'], "latitude": float(position_parts[0]), "longitude": float(position_parts[1])}]
            else:
                default_zones = [] # No valid location in settings

            self.config.height_min_max = default_height_min_max
            self.config.zones = default_zones
            self.config.update_interval = default_update_interval
            self.config.start_duration = default_start_duration
            self.config.night_mode = default_night_mode
        
            if config_file_path.exists():
                with open(config_file_path, 'r') as json_file:
                    config_data = json.load(json_file)
                self.config.zones = config_data.get('zones', default_zones)
                self.config.height_min_max = config_data.get('height_min_max (cm)', default_height_min_max)
                self.config.update_interval = config_data.get('update_interval (min)', default_update_interval)
                self.config.start_duration = config_data.get('start_duration (min)', default_start_duration)
                self.config.night_mode = config_data.get('night_mode', default_night_mode)
                Domoticz.Status(f'Configuration loaded from {config_file_path.name}:')
                zone_names = ', '.join(z.get('name', '?') for z in self.config.zones) if self.config.zones else 'none'
                Domoticz.Status(f'  Zones               : {zone_names}')
                Domoticz.Status(f'  Cutting height (cm) : min={self.config.height_min_max.get("min")}, max={self.config.height_min_max.get("max")}, steps={self.config.height_min_max.get("steps")}')
                Domoticz.Status(f'  Update intervals    : off={self.config.update_interval.get("off")} min, cloud_error={self.config.update_interval.get("cloud_error")} min, quota_error={self.config.update_interval.get("quota_error")} min')
                Domoticz.Status(f'  Start duration      : {self.config.start_duration} min')
                Domoticz.Status(f'  Night mode          : {self.config.night_mode.get("start", 22):02d}:00 - {self.config.night_mode.get("end", 6):02d}:00, interval={self.config.night_mode.get("interval", 60)} min')
            else:
                Domoticz.Status(f'Configuration file {config_file_path.name} not found, using defaults.')
                Domoticz.Debug("Husqvarna.json not found, using default zones, cutting height, update intervals, start duration and night mode.")

        except json.JSONDecodeError as err:
            Domoticz.Error(f"Error parsing configuration file: {err}; using default zones and cutting height.")
            log_backtrace_error(Parameters)
        except Exception as err:
            Domoticz.Error(f'Error reading Husqvarna.json configuration file: {err}; using default zones and cutting height.')
            log_backtrace_error(Parameters)

    def _create_custom_images(self) -> None:
        """Create custom images for the mower devices if not already available."""
        for image_id in [image.value for image in ImageIdentifier]:
            if image_id not in Images:
                Domoticz.Image(f'{image_id}.zip').Create()
                Domoticz.Debug(f"Created {image_id} image")

    def on_stop(self) -> None:
        """Handle the plugin shutdown process."""
        Domoticz.Debug('onStop called')
        self.stop_requested = True
        
        # Signal queue thread to exit
        self.tasks_queue.put(None)
        
        # Wait for thread to exit
        if self.tasks_thread and self.tasks_thread.is_alive():
            self.tasks_thread.join(timeout=10) # Added timeout for graceful shutdown

        # Wait until queue thread has exited
        Domoticz.Debug(f'Threads still active: {threading.active_count()} (should be 1)')
        end_time = time.time() + 70
        while (threading.active_count() > 1) and (time.time() < end_time):
            for thread in threading.enumerate():
                if thread.name != threading.current_thread().name:
                    Domoticz.Debug(f'Thread {thread.name} is still running, waiting to prevent Domoticz abort on exit.')
            time.sleep(1.0)

        Domoticz.Debug('Plugin stopped')

    def on_connect(self, connection: Any, status: int, description: str) -> None:
        """Handle connection events."""
        Domoticz.Debug(f'onConnect called ({connection.Name}) with status={status}')

    def on_message(self, connection: Any, data: Dict) -> None:
        """Handle message events."""
        Domoticz.Debug(f"onMessage called: {connection.Name} - {data['Status']}")

    def on_command(self, device_id: str, unit: int, command: str, level: int, color: str) -> None:
        """
        Handle commands sent to the plugin from Domoticz.
        Args:
            device_id: The device identifier
            unit: The unit within the device
            command: The command to execute
            level: The level parameter for the command
            color: The color parameter for the command
        """
        Domoticz.Debug(f'onCommand called for DeviceID/Unit: {device_id}/{unit} - Parameter: {command} - Level: {level}')

        if self.stop_requested:
            return

        if self.husqvarna_api is None:
            Domoticz.Error("Husqvarna API is not initialized. Actions cannot be performed.")
            timeout_device(Devices, device_id=device_id)
            return

        mower = self.husqvarna_api.get_mower_from_name(device_id)
        if not mower:
            Domoticz.Error(f"Mower {device_id} not found in connected mowers.")
            timeout_device(Devices, device_id=device_id)
            return

        if mower.get('state') == Husqvarna.State.OFF.name:
            Domoticz.Error(f"Husqvarna mower {mower['name']} is switched off and cannot execute commands.")
            return

        # Initialize execution status for this mower if not exists
        if device_id not in self.execution_status:
            self.execution_status[device_id] = ExecutionState()

        # Handle Run switch (On/Off)
        if unit == UnitId.RUN:
            self._handle_run_command(device_id, mower, command)

        # Handle cutting height adjustment
        elif unit == UnitId.CUTTING and command == 'Set Level':
            self._handle_cutting_height_command(device_id, mower, level)
                
        # Handle action selector
        elif unit == UnitId.ACTIONS and command == 'Set Level':
            self._handle_action_command(device_id, mower, level)

    def _handle_run_command(self, device_id: str, mower: Dict[str, Any], command: str) -> None:
        """Handle commands for the Run switch."""
        exec_state = self.execution_status[device_id]
        exec_state.status = ExecutionStatus.INITIATED.value
        exec_state.command_data.clear()
        exec_state.retries = 0
        
        if command == 'On':            
            if mower.get('activity') == Husqvarna.Activity.CHARGING.name:
                exec_state.status = ExecutionStatus.DONE.value
                Domoticz.Status(f"Mower {mower['name']} cannot be started as it is still charging.")
            else:
                exec_state.action = HusqvarnaAction.RESUME_SCHEDULE.value
                update_device(False, Devices, device_id, UnitId.RUN, 1, 1)
                self.tasks_queue.put({'Action': exec_state.action, 'Mower_name': mower['name']})
        else: # Command is 'Off'
            exec_state.action = HusqvarnaAction.PARK_UNTIL_FURTHER_NOTICE.value
            update_device(False, Devices, device_id, UnitId.RUN, 0, 0)
            self.tasks_queue.put({'Action': exec_state.action, 'Mower_name': mower['name']})

    def _handle_cutting_height_command(self, device_id: str, mower: Dict[str, Any], level: int) -> None:
        """Handle commands for cutting height adjustment."""
        exec_state = self.execution_status[device_id]
        exec_state.action = HusqvarnaAction.SET_CUTTING_HEIGHT.value
        exec_state.status = ExecutionStatus.INITIATED.value
        exec_state.command_data.clear()
        exec_state.retries = 0
        
        # Calculate actual cutting height (level/10 + 1)
        # Assuming the level in Domoticz 0, 10, 20, ...
        cutting_height = (level // 10) #level 0 = OFF
        self.tasks_queue.put({
            'Action': HusqvarnaAction.SET_CUTTING_HEIGHT.value, 
            'Mower_name': mower['name'], 
            'Cutting_height': cutting_height
        })
        exec_state.command_data['Cutting_height'] = cutting_height # Store for retry if needed

    def _handle_action_command(self, device_id: str, mower: Dict[str, Any], level: int) -> None:
        """Handle commands from the Actions selector switch."""
        exec_state = self.execution_status[device_id]
        exec_state.status = ExecutionStatus.INITIATED.value
        exec_state.command_data.clear()
        exec_state.retries = 0
        
        if level >= 20:
            # Map levels to actions
            action_list = get_unit(Devices, mower['name'], UnitId.ACTIONS).Options['LevelNames'].split('|')
            action = action_list[level//10]
            
            # Check if we need to prevent starting when charging
            if action.startswith(HusqvarnaAction.START.value) and mower.get('activity') == Husqvarna.Activity.CHARGING.name:
                exec_state.status = ExecutionStatus.DONE.value
                update_device(False, Devices, mower_name, UnitId.ACTIONS, 2, 10, Image=image)
                Domoticz.Status(f"Mower {mower['name']} cannot be started as it is still charging.")
            else:
                exec_state.action = action
                Domoticz.Debug(f'Launch action {action} after command (level {level}).')
                self.tasks_queue.put({'Action': action, 'Mower_name': mower['name']})

    def on_disconnect(self, connection: Any) -> None:
        """Handle disconnection events."""
        Domoticz.Debug(f'onDisconnect called ({connection.Name})')

    def on_heartbeat(self) -> None:
        """
        Handle heartbeat events.
        This is called regularly by Domoticz and is used to:
        1. Retry API initialization if needed
        2. Refresh mower list periodically
        3. Update mower status
        4. Retry failed commands
        5. Adjust polling frequency based on time of day and mower status
        """
        if self.stop_requested:
            return

        self.run_again -= 1
        if self.run_again <= 0:
            # If API not initialized, try to login
            if self.husqvarna_api is None:
                self.tasks_queue.put({'Action': HusqvarnaAction.LOGIN.value})
            
            # Refresh mower list daily
            now = datetime.datetime.now()
            # Ensure husqvarna_api and its method exist before calling
            if (self.husqvarna_api and 
                self.husqvarna_api.get_timestamp_last_update_mower_list() and # Check if timestamp is available
                self.husqvarna_api.get_timestamp_last_update_mower_list() + datetime.timedelta(days=1) < now):
                self.tasks_queue.put({'Action': HusqvarnaAction.GET_MOWERS.value})
                
            # Update mower status
            self.tasks_queue.put({'Action': HusqvarnaAction.GET_STATUS.value})
            
            # Retry failed commands
            if self.husqvarna_api and self.husqvarna_api.mowers:
                self._retry_failed_commands()
                
    def _retry_failed_commands(self) -> None:
        """Retry failed commands if they haven't exceeded retry limit."""
        if not self.husqvarna_api or not self.husqvarna_api.mowers:
            return

        for mower in self.husqvarna_api.mowers:
            mower_name = mower['name']
            if mower_name in self.execution_status:
                exec_state = self.execution_status[mower_name]
                if exec_state.status == ExecutionStatus.ERROR.value and exec_state.retries < 2:
                    Domoticz.Status(f"Retry {exec_state.retries + 1} for Husqvarna mower {mower_name} to launch command {exec_state.action}")
                    exec_state.status = ExecutionStatus.INITIATED.value # Reset status to initiated for retry
                    exec_state.retries += 1
                    
                    if exec_state.action:
                        task_to_retry = {'Action': exec_state.action, 'Mower_name': mower_name}
                        # Re-add command-specific data if it exists
                        if exec_state.action == HusqvarnaAction.SET_CUTTING_HEIGHT.value and 'Cutting_height' in exec_state.command_data:
                            task_to_retry['Cutting_height'] = exec_state.command_data['Cutting_height']
                        self.tasks_queue.put(task_to_retry)
                    else:
                        Domoticz.Debug(f"No action defined for retry for mower {mower_name}. Skipping retry.")

    def _is_night_time(self) -> bool:
        """
        Check whether the current time falls within the configured night period.
        Handles overnight ranges (e.g. 22:00 - 06:00) correctly.
        """
        hour = datetime.datetime.now().hour
        start = self.config.night_mode.get('start', 22)
        end = self.config.night_mode.get('end', 6)

        if start > end:
            # Overnight range: e.g. 22 -> 06 (crosses midnight)
            return hour >= start or hour < end
        elif start < end:
            # Same-day range: e.g. 01 -> 05
            return start <= hour < end
        else:
            # start == end: night mode disabled (zero-length window)
            return False

    def _adjust_update_frequency(self) -> None:
        """
        Adjust the update frequency based on:
        1. Night mode (quiet hours)
        2. Errors from Husqvarna Cloud
        3. API rate limits
        4. Whether all mowers are off
        5. Going home (temporary speed boost)
        """
        now = datetime.datetime.now()

        # --- Night mode: checked first, highest priority after errors ---
        if self._is_night_time():
            interval = self.config.night_mode.get('interval', 60)
            self.run_again = interval * DomoticzConstants.MINUTE
            if self.speed_status != UpdateSpeed.NIGHT:
                Domoticz.Status(
                    f'Night mode active: polling slowed to {interval} minutes '
                    f'(night window {self.config.night_mode.get("start", 22):02d}:00 - '
                    f'{self.config.night_mode.get("end", 6):02d}:00).'
                )
                self.speed_status = UpdateSpeed.NIGHT
            return  # Skip all other checks during night

        # --- Cloud / system errors ---
        if self.system_retries > 5:
            self.run_again = self.config.update_interval.get('cloud_error', 180) * DomoticzConstants.MINUTE
            if self.speed_status != UpdateSpeed.SYSTEM_ERROR:
                Domoticz.Status(
                    f'Reduce status update speed to {self.run_again / DomoticzConstants.MINUTE} minutes '
                    f'because of too many errors from Husqvarna Cloud.'
                )
                self.speed_status = UpdateSpeed.SYSTEM_ERROR

        # --- API quota / rate limits exceeded ---
        elif self.husqvarna_api and self.husqvarna_api.are_api_limits_reached():
            self.run_again = self.config.update_interval.get('quota_error', 30) * DomoticzConstants.MINUTE
            if self.speed_status != UpdateSpeed.LIMITS_EXCEEDED:
                Domoticz.Status(
                    f'Reduce status update speed to {self.run_again / DomoticzConstants.MINUTE} minutes '
                    f'as Husqvarna API limits are reached!'
                )
                self.speed_status = UpdateSpeed.LIMITS_EXCEEDED

        # --- All mowers are off (e.g. winter storage) ---
        elif self.husqvarna_api and self.husqvarna_api.mowers and self.husqvarna_api.are_all_mowers_off():
            self.run_again = self.config.update_interval.get('off', 60) * DomoticzConstants.MINUTE
            if self.speed_status != UpdateSpeed.ALL_OFF:
                Domoticz.Status(
                    f'Reduce status update speed to {self.run_again / DomoticzConstants.MINUTE} minutes '
                    f'as all Husqvarna mowers are off.'
                )
                self.speed_status = UpdateSpeed.ALL_OFF

        # --- Temporary speed boost: mower is heading home ---
        elif self.husqvarna_api and any(
            m.get('activity', '') == 'GOING_HOME'
            for m in self.husqvarna_api.mowers
            if isinstance(m, dict)
        ):
            self.run_again = DomoticzConstants.MINUTE
            Domoticz.Debug(
                f'Increasing update speed to {self.run_again / DomoticzConstants.MINUTE} minute(s) '
                f'as a mower is going home.'
            )
            # No speed_status change; this is a transient boost

        # --- Normal daytime operation ---
        else:
            configured_interval_minutes = float(Parameters.get('Mode5', '1').replace(',', '.'))
            self.run_again = DomoticzConstants.MINUTE * configured_interval_minutes
            if self.speed_status != UpdateSpeed.NORMAL:
                Domoticz.Status(
                    f'Re-establish normal update speed to {self.run_again / DomoticzConstants.MINUTE} minutes.'
                )
                self.speed_status = UpdateSpeed.NORMAL

    def _handle_tasks(self) -> None:
        """
        Background thread to handle API tasks.
        This runs in a separate thread to prevent blocking the main Domoticz thread
        during potentially slow API operations.
        """
        Domoticz.Debug('Entering tasks handler')
            
        while True:
            try:
                # Get task from queue (blocking)
                task = self.tasks_queue.get(block=True)
                    
                # Exit signal received
                if task is None:
                    Domoticz.Debug('Exiting task handler')
                    try:
                        if self.husqvarna_api:
                            self.husqvarna_api.close()
                            self.husqvarna_api = None
                    except AttributeError:
                        pass
                    #self.tasks_queue.task_done() - the "finally" part is still executed...
                    break
                        
                # Process the task
                Domoticz.Debug(f"Handling task: {task['Action']} (parameters: {task}).")
                self._process_task(task)

            except queue.Empty:
                pass # Continue loop if queue is empty 
            except Exception as e:
                Domoticz.Error(f"Unexpected error in task handler: {e}")
                log_backtrace_error(Parameters)
                   
            finally:
                # Mark task as done
                if 'task' in locals():
                    self.tasks_queue.task_done()
                    del task

    def _process_task(self, task: Dict[str, Any]) -> None:
        """
        Process a task from the queue.
        Args:
            task: The task dictionary with action and parameters
        """
        action = task['Action']
        
        # Handle login
        if action == HusqvarnaAction.LOGIN.value:
            self._handle_login_task()

        else:            
            # Handle mower list retrieval
            if action == HusqvarnaAction.GET_MOWERS.value:
                self._handle_get_mowers_task()
                
            # Handle status update
            elif action == HusqvarnaAction.GET_STATUS.value:
                self._handle_get_status_task()
                
            # Handle mower commands
            else:
                self._handle_mower_command_task(task)

            # Dynamic adaptation of update frequency
            self._adjust_update_frequency()

    def _handle_login_task(self) -> None:
        """
        Handle API login task.
        Uses bool(api) which calls __bool__ on the Husqvarna object,
        which returns self.state.authenticated set during __init__.
        """
        Domoticz.Debug("Log in to Husqvarna API.")
        # Ensure Husqvarna instance is re-created on each login attempt for fresh state if needed
        self.husqvarna_api = Husqvarna.Husqvarna(Parameters['Mode1'], Parameters['Mode2'])
        if self.husqvarna_api:
            self.system_retries = 0
            Domoticz.Debug("Successfully logged in to Husqvarna API.")
        else:
            error = self.husqvarna_api.get_http_error() if self.husqvarna_api is not None else 'Unknown'
            Domoticz.Error(f"Unable to get credentials from Husqvarna Cloud: {error}")
            self.system_retries += 1
            timeout_device(Devices)

    def _handle_get_mowers_task(self) -> None:
        """Handle retrieving the list of mowers."""
        Domoticz.Debug("Retrieving the list of mowers.")
        if self.husqvarna_api:
            if self.husqvarna_api.get_mowers():
                self.system_retries = 0
                current_mowers = { mower['name'] for mower in self.husqvarna_api.mowers }
                for mower_name in current_mowers:
                    # Create devices if they don't exist
                    self._create_mower_devices(mower_name)
                    # Initialize execution state
                    if mower_name not in self.execution_status:
                        self.execution_status[mower_name] = ExecutionState()
                # Clean up execution_status for mowers no longer present
                mowers_to_remove = [ name for name in self.execution_status if name not in current_mowers ]
                for mower_to_del in mowers_to_remove:
                    del self.execution_status[mower_to_del]
                    Domoticz.Debug(f"Removed staled execution status for mower '{mower_to_del}'.")
            else:
                Domoticz.Error(f"Error getting list of mowers from Husqvarna Cloud: {self.husqvarna_api.get_http_error()}")
                self.system_retries += 1
                timeout_device(Devices)

    def _handle_get_status_task(self) -> None:
        """Handle retrieving current status for all mowers."""
        Domoticz.Debug("Retrieving current status for all mowers.")
        if self.husqvarna_api: 
            if self.husqvarna_api.get_mowers_info():
                self.system_retries = 0
                if not self.husqvarna_api.mowers:
                    Domoticz.Error("No Husqvarna mowers available from the Husqvarna Cloud.")
                    self.system_retries += 1
                    timeout_device(Devices)
                for mower in self.husqvarna_api.mowers:
                    self._update_mower_devices(mower)
            else:
                Domoticz.Error(f"Error getting detailed status of mowers: {self.husqvarna_api.get_http_error()}")
                self.system_retries += 1
                timeout_device(Devices)

    def _update_mower_devices(self, mower: Dict[str, Any]) -> None:
        """
        Update or create Domoticz devices for a mower.
        Args:
            mower: Dictionary with mower information
        """
        Domoticz.Debug(f'Status information received from Husqvarna Cloud: {mower}')

        # Name of mower
        mower_name = mower['name']
                
        # Determine image based on mower state
        image = Images[ImageIdentifier.OFF.value].ID if mower.get('state') == Husqvarna.State.OFF.name else Images[ImageIdentifier.STANDARD.value].ID
        
        # Update state text
        state_text = self._format_state_text(mower)
        update_device(False, Devices, mower_name, UnitId.STATE, 0, state_text, Image=image)
        
        # Update running status
        if mower.get('activity') in [Husqvarna.Activity.LEAVING.name, Husqvarna.Activity.MOWING.name, Husqvarna.Activity.CHARGING.name, Husqvarna.Activity.GOING_HOME.name]:
            update_device(False, Devices, mower_name, UnitId.RUN, 1, 1, Image=image, BatteryLevel=mower.get('battery_pct', 0))
        else:
            update_device(False, Devices, mower_name, UnitId.RUN, 0, 0, Image=image, BatteryLevel=mower.get('battery_pct', 0))
            
        # Update battery level
        update_device(False, Devices, mower_name, UnitId.BATTERY, mower.get('battery_pct', 0), str(mower.get('battery_pct', 0)), Image=image)
        
        # Update location
        zone = self._determine_mower_zone(mower)
        update_device(False, Devices, mower_name, UnitId.LOCATION, 0, zone, Image=image)
        
        # Update cutting height
        if mower.get('cutting_height'):
            update_device(False, Devices, mower_name, UnitId.CUTTING, 2, 10*mower['cutting_height'], Image=image)
            
        # Update actions selector
        update_device(True, Devices, mower_name, UnitId.ACTIONS, 2, 10, Image=image)

        # Update next schedule
        schedule_text = self._format_next_schedule_text(mower)
        update_device(False, Devices, mower_name, UnitId.NEXT_SCHEDULE, 0, schedule_text, Image=image)

    def _format_state_text(self, mower: Dict[str, Any]) -> str:
        """Format the state text based on mower state, activity, and error."""
        error_state = mower.get('error_state', '')
        state = mower.get('state', '')
        activity = mower.get('activity', '')
        planner = mower.get('planner', {}) or {}
        restricted_reason = planner.get('restricted_reason', '')

        state_str = getattr(Husqvarna.State, state, Husqvarna.State.UNKNOWN).value
        activity_str = getattr(Husqvarna.Activity, activity, Husqvarna.Activity.UNKNOWN).value
        restricted_reason_str = getattr(Husqvarna.PlannerRestrictedReason, restricted_reason, Husqvarna.PlannerRestrictedReason.NONE).value

        # When parked in charging station, show "Parked in base until <next schedule>"
        if activity == Husqvarna.Activity.PARKED_IN_CS.name:
            next_schedule = self._format_next_schedule_label(mower)
            if next_schedule and next_schedule != 'No schedule':
                return f"Parked until {next_schedule}"
            else:
                return activity_str

        base_str = f"{state_str}: {activity_str}" if activity != Husqvarna.Activity.NOT_APPLICABLE.name else f"{state_str}"

        if error_state:
            return f"{base_str}\n<body><p style=\"line-height:80%;font-size:80%;\">{error_state.strip()}</p></body>"
        else:
            if restricted_reason:
                if ( reason_text := getattr(Husqvarna.PlannerRestrictedReason, restricted_reason, Husqvarna.PlannerRestrictedReason.NONE).value ):
                    return f"{base_str}\n<body><p style=\"line-height:80%;font-size:80%;\">{reason_text}</p></body>"
            return base_str

    def _format_next_schedule_label(self, mower: Dict[str, Any]) -> str:
        """
        Return a plain 'Day HH:MM' label for the next schedule (no HTML).
        Returns empty string if no schedule is available.
        """
        planner = mower.get('planner', {}) or {}
        timestamp_ms = planner.get('next_start_timestamp', None)
        if not timestamp_ms:
            return ''
        try:
            slot_dt = datetime.datetime.utcfromtimestamp(timestamp_ms / 1000)
            now = datetime.datetime.now()
            if slot_dt.date() == now.date():
                day_label = 'Today'
            elif slot_dt.date() == (now + datetime.timedelta(days=1)).date():
                day_label = 'Tomorrow'
            else:
                day_label = slot_dt.strftime('%A')
            return f'{day_label} {slot_dt.strftime("%H:%M")}'
        except Exception as e:
            Domoticz.Debug(f"Error formatting schedule label: {e}")
            return ''

    def _format_next_schedule_text(self, mower: Dict[str, Any]) -> str:
        """
        Format the next scheduled mowing session as readable text (with optional HTML subtitle).
        Uses nextStartTimestamp from the Husqvarna planner API (milliseconds).
        Note: Husqvarna API returns local time in the timestamp, not UTC.
        utcfromtimestamp is used intentionally to avoid double timezone conversion.
        """
        planner = mower.get('planner', {}) or {}
        restricted_reason = planner.get('restricted_reason', '')

        label = self._format_next_schedule_label(mower)
        if not label:
            return 'No schedule'

        result = label

        if restricted_reason is not Husqvarna.PlannerRestrictedReason.NONE.name:
            if ( reason_text := getattr(Husqvarna.PlannerRestrictedReason, restricted_reason, Husqvarna.PlannerRestrictedReason.NONE).value ):
                result += f"\n<body><p style=\"line-height:80%;font-size:80%;\">{reason_text}</p></body>"

        return result

    def _determine_mower_zone(self, mower: Dict[str, Any]) -> str:
        """
        Determine the garden zone where the mower is located.
        When the mower is in its base, this is returned as location.
        """
        activity = mower.get('activity', '')
        if activity in (Husqvarna.Activity.CHARGING.name, Husqvarna.Activity.PARKED_IN_CS.name):
            return Husqvarna.Activity.PARKED_IN_CS.value

        location_data = mower.get('location')
        if location_data and location_data.get('latitude') is not None and location_data.get('longitude') is not None:
            # Pass only the necessary parts of location to _find_nearest_zone
            return self._find_nearest_zone({'latitude': location_data['latitude'], 'longitude': location_data['longitude']})
        else:
            # No GPS location available (e.g. mower is in charging station): return activity as fallback
            activity = mower.get('activity', '')
            return getattr(Husqvarna.Activity, activity, Husqvarna.Activity.UNKNOWN).value

    def _find_nearest_zone(self, position: Dict[str, float]) -> str:
        """Find the nearest zone based on GPS coordinates."""
        Domoticz.Debug(f"Inside _find_nearest_zone: self.config.zones = {self.config.zones}")

        if not self.config.zones:
            Domoticz.Debug("No garden zones configured.")
            return "Unknown"
            
        try:
            # Filter for valid zones before sorting
            valid_zones = [
                z for z in self.config.zones 
                if isinstance(z, dict) and 'latitude' in z and 'longitude' in z and 
                   isinstance(z['latitude'], (int, float)) and isinstance(z['longitude'], (int, float))
            ]
            
            if not valid_zones:
                Domoticz.Debug("No valid zones (with complete coordinates) found for distance calculation.")
                return "Unknown"

            sorted_zones = sorted(
                valid_zones,
                key=lambda zone: get_distance(
                    (position['latitude'], position['longitude']),
                    (zone["latitude"], zone["longitude"])
                )
            )
            Domoticz.Debug(f"Mower is located in the zone {sorted_zones[0]['name']}.")
            return sorted_zones[0]['name']
        except Exception as e:
            Domoticz.Debug(f"Error finding nearest zone: {e}")
            return "Unknown"

    def _create_mower_devices(self, mower_name: str) -> None:
        """
        Create Domoticz devices for a mower.
        Args:
            mower_name: Name of the mower
        """
        new_device_created = False

        # State text display
        if not get_unit(Devices, mower_name, UnitId.STATE):
            Domoticz.Unit(
                DeviceID=mower_name, 
                Unit=UnitId.STATE, 
                Name=f"{Parameters['Name']} - {mower_name} - {DeviceText.STATE.value}", 
                TypeName='Text', 
                Image=Images[ImageIdentifier.STANDARD.value].ID, 
                Used=1
            ).Create()
            new_device_created = True
        
        # Run (On/Off) switch
        if not get_unit(Devices, mower_name, UnitId.RUN):
            Domoticz.Unit(
                DeviceID=mower_name, 
                Unit=UnitId.RUN, 
                Name=f"{Parameters['Name']} - {mower_name} - {DeviceText.RUN.value}", 
                Type=244, 
                Subtype=73, 
                Switchtype=0, 
                Image=Images[ImageIdentifier.STANDARD.value].ID, 
                Used=1
            ).Create()
            new_device_created = True
        
        # Battery level
        if not get_unit(Devices, mower_name, UnitId.BATTERY):
            Domoticz.Unit(
                DeviceID=mower_name, 
                Unit=UnitId.BATTERY, 
                Name=f"{Parameters['Name']} - {mower_name} - {DeviceText.BATTERY.value}", 
                TypeName='Custom', 
                Options={'Custom': '0;%'}, 
                Image=Images[ImageIdentifier.STANDARD.value].ID, 
                Used=0
            ).Create()
            new_device_created = True
        
        # Location in garden
        if not get_unit(Devices, mower_name, UnitId.LOCATION):
            Domoticz.Unit(
                DeviceID=mower_name, 
                Unit=UnitId.LOCATION, 
                Name=f"{Parameters['Name']} - {mower_name} - {DeviceText.LOCATION.value}", 
                TypeName='Text', 
                Image=Images[ImageIdentifier.STANDARD.value].ID, 
                Used=1
            ).Create()
            new_device_created = True
        
        # Cutting height selector
        if not get_unit(Devices, mower_name, UnitId.CUTTING):
            self._create_cutting_height_selector(mower_name)
            new_device_created = True
        
        # Actions selector
        start = f"{HusqvarnaAction.START.value} ({self.config.start_duration/60:.1f}h)"
        actions = f"|(select)|{start}|{HusqvarnaAction.PAUSE.value}|{HusqvarnaAction.RESUME_SCHEDULE.value}|{HusqvarnaAction.PARK_UNTIL_FURTHER_NOTICE.value}|{HusqvarnaAction.PARK_UNTIL_NEXT_SCHEDULE.value}"
        if not get_unit(Devices, mower_name, UnitId.ACTIONS):
            Domoticz.Unit(
                DeviceID=mower_name, 
                Unit=UnitId.ACTIONS, 
                Name=f"{Parameters['Name']} - {mower_name} - {DeviceText.ACTIONS.value}", 
                TypeName='Selector Switch', 
                Options={
                    'LevelActions': '|'*actions.count('|'), 
                    'LevelNames': actions, 
                    'LevelOffHidden': 'true', 
                    'SelectorStyle': '1'
                }, 
                Image=Images[ImageIdentifier.STANDARD.value].ID, 
                Used=1
            ).Create()
            new_device_created = True
        else:
            # Update action list
            Options={'LevelActions': '|'*actions.count('|'), 'LevelNames': actions, 'LevelOffHidden': 'true', 'SelectorStyle': '1' }
            update_device(False, Devices, mower_name, UnitId.ACTIONS, None, None, Options=Options)

        # Next schedule text device
        if not get_unit(Devices, mower_name, UnitId.NEXT_SCHEDULE):
            Domoticz.Unit(
                DeviceID=mower_name,
                Unit=UnitId.NEXT_SCHEDULE,
                Name=f"{Parameters['Name']} - {mower_name} - {DeviceText.NEXT_SCHEDULE.value}",
                TypeName='Text',
                Image=Images[ImageIdentifier.STANDARD.value].ID,
                Used=1
            ).Create()
            new_device_created = True
        
        # Set all devices as timed out until we get real data
        if new_device_created: 
            timeout_device(Devices, device_id=mower_name)

    def _create_cutting_height_selector(self, mower_name: str) -> None:
        """Create the cutting height selector with proper range."""
        # Use configured height range if available
        min_height = self.config.height_min_max.get('min')
        max_height = self.config.height_min_max.get('max')
        steps = self.config.height_min_max.get('steps')

        if min_height is not None and max_height is not None and steps is not None and steps >= 1:
            if steps > 1:
                height_interval = (max_height - min_height) / (steps - 1)
                height_range = [min_height + i * height_interval for i in range(steps)]
            else: # Handle case with 1 step to avoid division by zero if interval is calculated
                height_range = [min_height] # Only one value

            level_names = '|'.join(f'{height:.1f}' for height in height_range)
                
            Domoticz.Unit(
                DeviceID=mower_name, 
                Unit=UnitId.CUTTING, 
                Name=f"{Parameters['Name']} - {mower_name} - {DeviceText.CUTTING.value}", 
                TypeName='Selector Switch', 
                Options={
                    'LevelActions': '||' * (steps - 1), 
                    'LevelNames': f'|{level_names}', 
                    'LevelOffHidden': 'true', 
                    'SelectorStyle': '0'
                }, 
                Image=Images[ImageIdentifier.STANDARD.value].ID, 
                Used=1
            ).Create()
        else:
           Domoticz.Error(f"Error creating cutting height selector.")

    def _handle_mower_command_task(self, task: Dict[str, Any]) -> None:
        """
        Handle mower commands like start, pause, park, etc.
        Args:
            task: Task information including action and mower name
        """
        Domoticz.Debug(f"Executing mower command: {task['Action']} for {task.get('Mower_name')}.")

        if not self.husqvarna_api:
            Domoticz.Debug("Cannot execute command: API not initialized")
            return

        action = task['Action']
        mower_name = task.get('Mower_name')
        
        if not mower_name:
            Domoticz.Debug(f"Missing mower name for action {action}")
            return

        if self.husqvarna_api.is_mower_off(mower_name):
            Domoticz.Debug(f"Mower {mower_name} is switched off. Action {action} will not be executed.")
            return
            
        # Initialize execution status tracking if not exists
        if mower_name not in self.execution_status:
            self.execution_status[mower_name] = ExecutionState()
            
        # Execute the command based on action type
        status = None
        
        try:
            # Start mowing (24 hours)
            if action == HusqvarnaAction.START.value:
                status = self.husqvarna_api.action_Start(mower_name, duration=1440)
                    
            # Start mowing (x hours)
            elif action.startswith(HusqvarnaAction.START.value) and len(action)>len(HusqvarnaAction.START.value):
                status = self.husqvarna_api.action_Start(mower_name, duration=self.config.start_duration)
                    
            # Park until further notice
            elif action == HusqvarnaAction.PARK_UNTIL_FURTHER_NOTICE.value:
                status = self.husqvarna_api.action_ParkUntilFurtherNotice(mower_name)
                    
            # Park until next schedule
            elif action == HusqvarnaAction.PARK_UNTIL_NEXT_SCHEDULE.value:
                status = self.husqvarna_api.action_ParkUntilNextSchedule(mower_name)
                    
            # Pause mowing
            elif action == HusqvarnaAction.PAUSE.value:
                status = self.husqvarna_api.action_Pause(mower_name)
                    
            # Resume schedule
            elif action == HusqvarnaAction.RESUME_SCHEDULE.value:
                status = self.husqvarna_api.action_ResumeSchedule(mower_name)
                    
            # Set cutting height
            elif action == HusqvarnaAction.SET_CUTTING_HEIGHT.value:
                cutting_height = task.get('Cutting_height')
                if cutting_height is not None:
                    status = self.husqvarna_api.set_cutting_height(mower_name, cutting_height)
                else:
                    Domoticz.Debug(f"Missing cutting height value for {mower_name}")
            
            # Update status based on command result
            if status is None:
                Domoticz.Error(f"Unknown action code {action}")
            elif status:
                self.execution_status[mower_name].status = ExecutionStatus.DONE.value
            else:
                Domoticz.Error(f"Error executing {action} on {mower_name}: {self.husqvarna_api.get_http_error()}")
                timeout_device(Devices, device_id=mower_name)
                self.execution_status[mower_name].status = ExecutionStatus.ERROR.value
                
            # Request quick status update after command
            self.run_again = DomoticzConstants.MINUTE / 2
                
        except Exception as e:
            Domoticz.Error(f"Error executing command {action} on {mower_name}: {e}")
            self.execution_status[mower_name].status = ExecutionStatus.ERROR.value

# Global plugin instance
_plugin = HusqvarnaPlugin()

def onStart():
    global _plugin
    _plugin.on_start()

def onStop():
    global _plugin
    _plugin.on_stop()

def onConnect(Connection, Status, Description):
    global _plugin
    _plugin.on_connect(Connection, Status, Description)

def onMessage(Connection, Data):
    global _plugin
    _plugin.on_message(Connection, Data)

def onCommand(DeviceID, Unit, Command, Level, Color):
    global _plugin
    _plugin.on_command(DeviceID, Unit, Command, Level, Color)

def onDisconnect(Connection):
    global _plugin
    _plugin.on_disconnect(Connection)

def onHeartbeat():
    global _plugin
    _plugin.on_heartbeat()