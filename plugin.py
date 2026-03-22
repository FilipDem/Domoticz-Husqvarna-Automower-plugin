#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Husqvarna Mower Plugin for Domoticz

This plugin integrates Husqvarna robotic lawn mowers with Domoticz home automation system.
It provides monitoring of mower status, battery level, location, and control functions like
start/stop, parking, and cutting height adjustment.

Author: Filip Demaertelaere
Version: 2.1.0
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
<plugin key="Husqvarna" name="Husqvarna" author="Filip Demaertelaere" version="2.1.0">
    <description>
        <h2>Husqvarna</h2>
        <p>Version 2.1.0</p>
        <p>The Husqvarna plugin for Domoticz provides seamless integration with your Husqvarna robotic lawnmowers. Leveraging the official Husqvarna API, this plugin allows you to monitor your mower's status and control key functions directly from your Domoticz environment. It creates virtual devices for each connected mower, offering real-time insights into its activity, battery level, cutting height, and precise location.</p>
        <br/>
        <h2>Key features:</h2>
        <ul>
            <li><b>Real-time Status Monitoring:</b> View your mower's current state (e.g., mowing, charging, parked, paused, off).</li>
            <li><b>Battery Level Indication:</b> Keep track of your mower's battery percentage.</li>
            <li><b>Location Tracking:</b> Based on GPS coordinates of your mower, with an option to display its proximity to predefined zones (e.g., "Front Garden", "Back Garden").</li>
            <li><b>Remote Control Actions:</b> Start mowing, pause operations, resume schedules, or park the mower (until further notice or next schedule).</li>
            <li><b>Cutting Height Adjustment:</b> Remotely set the cutting height of your mower.</li>
            <li><b>Next Schedule:</b> Shows the next upcoming scheduled mowing session.</li>
            <li><b>Zone Management:</b> Define custom zones for your property to get distance information and easily identify which zone your mower is currently in.</li>
        </ul>
        <br/>
        <h2>Hardware Plugin Configuration</h2>
        <ul>
            <li><b>Client_id:</b> Your Husqvarna API client ID (also known as application ID). Obtain this from the Husqvarna Developer Portal: <a href="https://developer.husqvarnagroup.cloud/applications">https://developer.husqvarnagroup.cloud/applications</a>. You will need to create an application to get these credentials.</li>
            <li><b>Client_secret:</b> Your Husqvarna API client secret (also known as application secret). Obtain this from the Husqvarna Developer Portal, linked to your application. This should be kept confidential.</li>
            <li><b>Update interval:</b> The frequency, in minutes, at which the plugin will poll the Husqvarna API for status updates. A smaller interval means more frequent updates. Avoid using permanently small intervals as Husqvarna implemented a restriction on the number of updates (see the Husqvarna Developer Portal for more information). Please note that if all configured mowers are detected as 'OFF' (e.g., during winter storage), the plugin will automatically reduce this polling interval to once per hour to minimize unnecessary API calls and save resources. Normal polling resumes when a mower becomes active again.</li>
            <li><b>Debug:</b> Select the level of debugging information to be logged to the Domoticz log. "None" is recommended for normal operation, while other options provide more detailed logs for troubleshooting and development.</li>
        </ul>
        <br/>
        <h2>Advanced Configuration (Husqvarna.json)</h2>
        <p>For advanced configurations such as defining specific zones for your mower or setting custom cutting height ranges, an optional configuration file named `Husqvarna.json` can be placed in the plugin's home folder. This JSON file allows you to define custom zones with geographical coordinates and override the default min/max cutting height settings. The min/max cutting settings can be found in the Husqvarna mobile application.</p>
        <h3>Example Husqvarna.json content:</h3>
        <pre><code>
{
    "zones": [
        { "name": "FrontGarden", "latitude": 50.8503, "longitude": 4.3517 },
        { "name": "BackGarden", "latitude": 50.8400, "longitude": 4.3400 }
    ],
    "height_min_max (cm)": { "min": 2, "max": 6, "steps": 9 }
}
        </code></pre>
        <p>If this file is not present or is invalid, the plugin will revert to default values for zones (using Domoticz's configured title/location) and cutting height (min: 2, max: 6, steps: 9).</p>
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

# Human-readable labels for mower activities (shared across methods)
ACTIVITY_LOG_MAP = {
    'UNKNOWN':           'Unknown',
    'NOT_APPLICABLE':    'Not applicable',
    'MOWING':            'Mowing',
    'GOING_HOME':        'Going home',
    'CHARGING':          'Charging',
    'LEAVING':           'Leaving charging station',
    'PARKED_IN_CS':      'Parked in charging station',
    'STOPPED_IN_GARDEN': 'Stopped in garden',
}

class UnitId(IntEnum):
    """Unit identifiers for Husqvarna mower devices in Domoticz."""
    STATE = 1
    RUN = 2
    BATTERY = 3
    ACTIONS = 4
    LOCATION = 5
    CUTTING = 6
    SCHEDULE = 7  # Next scheduled mowing session

class DeviceText(str, Enum):
    """Text identifiers for device names."""
    STATE = 'State'
    RUN = 'Run'
    BATTERY = 'Battery Level'
    ACTIONS = 'Actions'
    LOCATION = 'Location'
    CUTTING = 'Cutting Height (cm)'
    SCHEDULE = 'Next Schedule'

class ImageIdentifier(str, Enum):
    """Custom image identifiers for Husqvarna mower devices."""
    STANDARD = 'Husqvarna'
    INVERSE = 'Husqvarna_Inverse'
    OFF = 'Husqvarna_Off'

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
    START = 'Start'
    START_6H = 'Start (6h)'
    PAUSE = 'Pause'
    RESUME_SCHEDULE = 'Resume Schedule'
    PARK_UNTIL_FURTHER_NOTICE = 'Park Until Further Notice'
    PARK_UNTIL_NEXT_SCHEDULE = 'Park Until Next Schedule'
    SET_CUTTING_HEIGHT = 'Set Cutting Height'

@dataclass
class MowerConfig:
    """Configuration for Husqvarna mowers from JSON file."""
    zones: List[Dict[str, Any]] = field(default_factory=list)
    height_min_max: Dict[str, Any] = field(default_factory=dict)

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
        self.husqvarna_api = None   # type: Optional[Husqvarna.Husqvarna]
        self.config = MowerConfig()
        self.tasks_queue = queue.Queue()
        self.tasks_thread = threading.Thread(
            name='QueueThread',
            target=self._handle_tasks
        )
        self.previous_activity = {}  # type: Dict[str, str]
        self.devices_created = set()  # type: Set[str]  # Track mowers for which devices have been created

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
        # GET_MOWERS will also create missing devices for all known mowers
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
            position_parts = Settings['Location'].split(';')
            if len(position_parts) >= 2 and all(isinstance(p, str) and p.strip().replace('.', '', 1).isdigit() for p in position_parts[:2]):
                default_zones = [{"name": Settings['Title'], "latitude": float(position_parts[0]), "longitude": float(position_parts[1])}]
            else:
                default_zones = []

            self.config.height_min_max = default_height_min_max
            self.config.zones = default_zones

            if config_file_path.exists():
                with open(config_file_path, 'r') as json_file:
                    config_data = json.load(json_file)
                self.config.zones = config_data.get('zones', default_zones)
                self.config.height_min_max = config_data.get('height_min_max (cm)', default_height_min_max)
                Domoticz.Debug(f'Zones found: {self.config.zones}.')
                Domoticz.Debug(f'Cutting height range found: {self.config.height_min_max}.')
            else:
                Domoticz.Debug("Husqvarna.json not found, using default zones and cutting height.")

        except json.JSONDecodeError as err:
            Domoticz.Error(f"Error parsing configuration file: {err}; using default zones and cutting height.")
            log_backtrace_error(Parameters)
        except Exception as err:
            Domoticz.Error(f'Error reading Husqvarna.json configuration file: {err}; using default zones and cutting height.')
            log_backtrace_error(Parameters)

    def _create_custom_images(self) -> None:
        """Create custom images for the mower devices if not already available."""
        for image_id in [
            ImageIdentifier.STANDARD,
            ImageIdentifier.INVERSE,
            ImageIdentifier.OFF
        ]:
            if image_id.value not in Images:
                Domoticz.Image(f'{image_id.value}.zip').Create()
                Domoticz.Debug(f"Created {image_id.value} image")

    def on_stop(self) -> None:
        """Handle the plugin shutdown process."""
        Domoticz.Debug('onStop called')
        self.stop_requested = True

        self.tasks_queue.put(None)

        if self.tasks_thread and self.tasks_thread.is_alive():
            self.tasks_thread.join(timeout=10)
            if self.tasks_thread.is_alive():
                Domoticz.Debug('QueueThread did not stop within timeout.')
            else:
                Domoticz.Debug('QueueThread stopped cleanly.')

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

        if mower.get('state') == 'OFF':
            Domoticz.Error(f"Husqvarna mower {mower['name']} is switched off and cannot execute commands.")
            return

        if device_id not in self.execution_status:
            self.execution_status[device_id] = ExecutionState()

        if unit == UnitId.RUN:
            self._handle_run_command(device_id, mower, command)
        elif unit == UnitId.CUTTING and command == 'Set Level':
            self._handle_cutting_height_command(device_id, mower, level)
        elif unit == UnitId.ACTIONS and command == 'Set Level' and level:
            self._handle_action_command(device_id, mower, level)

    def _handle_run_command(self, device_id: str, mower: Dict[str, Any], command: str) -> None:
        """Handle commands for the Run switch."""
        exec_state = self.execution_status[device_id]

        if command == 'On':
            exec_state.status = ExecutionStatus.INITIATED
            exec_state.command_data.clear()
            exec_state.retries = 0

            if mower.get('activity') == 'CHARGING':
                exec_state.status = ExecutionStatus.DONE
                Domoticz.Status(f"Mower {mower['name']} cannot be started as it is still charging.")
            else:
                exec_state.action = HusqvarnaAction.START.value
                update_device(False, Devices, device_id, UnitId.RUN, 1, 1)
                self.tasks_queue.put({'Action': HusqvarnaAction.START.value, 'Mower_name': mower['name']})
        else:
            exec_state.action = HusqvarnaAction.PARK_UNTIL_FURTHER_NOTICE.value
            exec_state.status = ExecutionStatus.INITIATED
            exec_state.command_data.clear()
            exec_state.retries = 0
            update_device(False, Devices, device_id, UnitId.RUN, 0, 0)
            self.tasks_queue.put({'Action': HusqvarnaAction.PARK_UNTIL_FURTHER_NOTICE.value, 'Mower_name': mower['name']})

    def _handle_cutting_height_command(self, device_id: str, mower: Dict[str, Any], level: int) -> None:
        """Handle commands for cutting height adjustment."""
        exec_state = self.execution_status[device_id]
        exec_state.action = HusqvarnaAction.SET_CUTTING_HEIGHT.value
        exec_state.status = ExecutionStatus.INITIATED
        exec_state.command_data.clear()
        exec_state.retries = 0

        cutting_height = (level // 10) + 1
        self.tasks_queue.put({
            'Action': HusqvarnaAction.SET_CUTTING_HEIGHT.value,
            'Mower_name': mower['name'],
            'Cutting_height': cutting_height
        })
        exec_state.command_data['Cutting_height'] = cutting_height

    def _handle_action_command(self, device_id: str, mower: Dict[str, Any], level: int) -> None:
        """Handle commands from the Actions selector switch."""
        exec_state = self.execution_status[device_id]
        exec_state.status = ExecutionStatus.INITIATED
        exec_state.command_data.clear()
        exec_state.retries = 0

        action_map = {
            10: {'action': HusqvarnaAction.START_6H.value, 'check_charging': True},
            20: {'action': HusqvarnaAction.PAUSE.value},
            30: {'action': HusqvarnaAction.RESUME_SCHEDULE.value},
            40: {'action': HusqvarnaAction.PARK_UNTIL_FURTHER_NOTICE.value},
            50: {'action': HusqvarnaAction.PARK_UNTIL_NEXT_SCHEDULE.value}
        }

        if level in action_map:
            action_info = action_map[level]
            action = action_info['action']

            if action_info.get('check_charging', False) and mower.get('activity') == 'CHARGING':
                exec_state.status = ExecutionStatus.DONE
                Domoticz.Status(f"Mower {mower['name']} cannot be started as it is still charging.")
            else:
                exec_state.action = action
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
            if self.husqvarna_api is None:
                self.tasks_queue.put({'Action': HusqvarnaAction.LOGIN.value})

            now = datetime.datetime.now()
            if (self.husqvarna_api and
                self.husqvarna_api.get_timestamp_last_update_mower_list() and
                self.husqvarna_api.get_timestamp_last_update_mower_list() + datetime.timedelta(days=1) < now):
                self.tasks_queue.put({'Action': HusqvarnaAction.GET_MOWERS.value})

            self.tasks_queue.put({'Action': HusqvarnaAction.GET_STATUS.value})

            if self.husqvarna_api and self.husqvarna_api.mowers:
                self._retry_failed_commands()

            self._adjust_update_frequency()

    def _retry_failed_commands(self) -> None:
        """Retry failed commands if they haven't exceeded retry limit."""
        if not self.husqvarna_api or not self.husqvarna_api.mowers:
            return

        for mower in self.husqvarna_api.mowers:
            mower_name = mower['name']
            if mower_name in self.execution_status:
                exec_state = self.execution_status[mower_name]
                if exec_state.status == ExecutionStatus.ERROR and exec_state.retries < 2:
                    Domoticz.Status(f"Retry {exec_state.retries + 1} for Husqvarna mower {mower_name} to launch command {exec_state.action}")
                    exec_state.status = ExecutionStatus.INITIATED
                    exec_state.retries += 1

                    if exec_state.action:
                        task_to_retry = {'Action': exec_state.action, 'Mower_name': mower_name}
                        if exec_state.action == HusqvarnaAction.SET_CUTTING_HEIGHT.value and 'Cutting_height' in exec_state.command_data:
                            task_to_retry['Cutting_height'] = exec_state.command_data['Cutting_height']
                        self.tasks_queue.put(task_to_retry)
                    else:
                        Domoticz.Debug(f"No action defined for retry for mower {mower_name}. Skipping retry.")

    def _adjust_update_frequency(self) -> None:
        """
        Adjust the update frequency based on:
        1. Errors from Husqvarna Cloud
        2. API rate limits
        3. Whether all mowers are off
        4. Going home
        5. Time of day (reduced polling at night)
        """
        now = datetime.datetime.now()
        hours = now.hour

        if self.system_retries > 5:
            configured_interval_minutes = float(Parameters.get('Mode5', '1').replace(',','.'))
            self.run_again = min(12*60*DomoticzConstants.MINUTE, self.system_retries*DomoticzConstants.MINUTE*configured_interval_minutes)
            if self.speed_status != UpdateSpeed.SYSTEM_ERROR:
                Domoticz.Status(f'Reduce status update speed to {self.run_again/DomoticzConstants.MINUTE} minutes because of too many errors from Husqvarna Cloud.')
                self.speed_status = UpdateSpeed.SYSTEM_ERROR

        elif self.husqvarna_api and self.husqvarna_api.are_api_limits_reached():
            self.run_again = max(60 * DomoticzConstants.MINUTE, self.run_again)
            if self.speed_status != UpdateSpeed.LIMITS_EXCEEDED:
                Domoticz.Status(f'Reduce status update speed to {self.run_again/DomoticzConstants.MINUTE} minutes as Husqvarna API limits are reached!')
                self.speed_status = UpdateSpeed.LIMITS_EXCEEDED

        elif self.husqvarna_api and self.husqvarna_api.are_all_mowers_off():
            self.run_again = 60 * DomoticzConstants.MINUTE
            if self.speed_status != UpdateSpeed.ALL_OFF:
                Domoticz.Status(f'Reduce status update speed to {self.run_again/DomoticzConstants.MINUTE} minutes as all Husqvarna mowers are off.')
                self.speed_status = UpdateSpeed.ALL_OFF

        elif self.husqvarna_api and any(m.get('activity', '') == 'GOING_HOME' for m in self.husqvarna_api.mowers if isinstance(m, dict)):
            configured_interval_minutes = float(Parameters.get('Mode5', '1').replace(',','.'))
            self.run_again = DomoticzConstants.MINUTE * configured_interval_minutes / 2
            Domoticz.Debug(f"Increasing update speed to {self.run_again / DomoticzConstants.MINUTE} minutes as a mower is going home.")

        elif hours >= 22 or hours <= 5:
            self.run_again = DomoticzConstants.MINUTE * 180
            if self.speed_status != UpdateSpeed.NIGHT:
                Domoticz.Status(f'Reduce status update speed to {self.run_again/DomoticzConstants.MINUTE} minutes during nighttime hours.')
                self.speed_status = UpdateSpeed.NIGHT

        else:
            configured_interval_minutes = float(Parameters.get('Mode5', '1').replace(',','.'))
            self.run_again = DomoticzConstants.MINUTE * configured_interval_minutes
            if self.speed_status != UpdateSpeed.NORMAL:
                Domoticz.Status(f'Re-establish normal update speed to {self.run_again/DomoticzConstants.MINUTE} minutes.')
                self.speed_status = UpdateSpeed.NORMAL

    def _handle_tasks(self) -> None:
        """
        Background thread to handle API tasks.
        This runs in a separate thread to prevent blocking the main Domoticz thread
        during potentially slow API operations.
        """
        Domoticz.Debug('Entering tasks handler')
        task = None

        while True:
            try:
                task = self.tasks_queue.get(block=True)

                if task is None:
                    Domoticz.Debug('Exiting task handler')
                    try:
                        if self.husqvarna_api:
                            self.husqvarna_api.close()
                            self.husqvarna_api = None
                    except AttributeError:
                        pass
                    self.tasks_queue.task_done()
                    break

                Domoticz.Debug(f"Handling task: {task['Action']}.")
                self._process_task(task)

            except queue.Empty:
                pass
            except Exception as e:
                Domoticz.Error(f"Unexpected error in task handler: {e}")
                log_backtrace_error(Parameters)

            finally:
                if task is not None:
                    self.tasks_queue.task_done()
                    task = None

    def _process_task(self, task: Dict[str, Any]) -> None:
        """
        Process a task from the queue.
        Args:
            task: The task dictionary with action and parameters
        """
        action = task['Action']

        if action == HusqvarnaAction.LOGIN.value:
            self._handle_login_task()
        elif action == HusqvarnaAction.GET_MOWERS.value:
            self._handle_get_mowers_task()
        elif action == HusqvarnaAction.GET_STATUS.value:
            self._handle_get_status_task()
        else:
            self._handle_mower_command_task(task)

    def _handle_login_task(self) -> None:
        """
        Handle API login task.
        Uses bool(api) which calls __bool__ on the Husqvarna object,
        which returns self.state.authenticated set during __init__.
        """
        api = Husqvarna.Husqvarna(Parameters['Mode1'], Parameters['Mode2'])
        if bool(api):
            self.husqvarna_api = api
            self.system_retries = 0
            Domoticz.Debug("Successfully logged in to Husqvarna API.")
        else:
            error = api.get_http_error() if api is not None else 'Unknown'
            Domoticz.Error(f"Unable to get credentials from Husqvarna Cloud: {error}")
            self.husqvarna_api = None
            self.system_retries += 1
            timeout_device(Devices)

    def _handle_get_mowers_task(self) -> None:
        """
        Handle retrieving the list of mowers.
        Also creates Domoticz devices for any mower not yet known,
        so device creation is done once here instead of on every poll.
        """
        if self.husqvarna_api:
            if self.husqvarna_api.get_mowers():
                self.system_retries = 0
                for mower in self.husqvarna_api.mowers:
                    mower_name = mower['name']
                    if mower_name not in self.execution_status:
                        self.execution_status[mower_name] = ExecutionState()
                    # Create devices only once per mower
                    if mower_name not in self.devices_created:
                        Domoticz.Debug(f"Creating devices for new mower '{mower_name}'.")
                        self._create_missing_devices(mower_name)
                        self.devices_created.add(mower_name)
                # Clean up execution_status and devices_created for mowers no longer present
                current_names = {m['name'] for m in self.husqvarna_api.mowers}
                stale_names = [n for n in self.execution_status if n not in current_names]
                for name in stale_names:
                    del self.execution_status[name]
                    self.devices_created.discard(name)
                    Domoticz.Debug(f"Removed stale execution status for mower '{name}'.")
            else:
                Domoticz.Error(f"Error getting list of mowers from Husqvarna Cloud: {self.husqvarna_api.get_http_error()}")
                self.system_retries += 1
                timeout_device(Devices)

    def _handle_get_status_task(self) -> None:
        """Handle retrieving current status for all mowers."""
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
        Update Domoticz devices for a mower.
        Device creation is handled in _handle_get_mowers_task, not here.
        Args:
            mower: Dictionary with mower information
        """
        mower_name = mower['name']

        # Log activity changes with human-readable labels
        activity = mower.get('activity', '')
        previous = self.previous_activity.get(mower_name, '')
        activity_label = ACTIVITY_LOG_MAP.get(activity, activity)

        if activity != previous:
            if not previous:
                # First poll after startup - always log current status with friendly label
                Domoticz.Log(f"Mower {mower_name} startup status: {activity_label}.")
            elif activity == 'MOWING':
                Domoticz.Log(f"Mower {mower_name} started mowing.")
            elif activity == 'LEAVING':
                Domoticz.Log(f"Mower {mower_name} is leaving the charging station.")
            elif activity == 'GOING_HOME':
                Domoticz.Log(f"Mower {mower_name} is going home.")
            elif activity == 'CHARGING':
                if previous in ['GOING_HOME', 'MOWING', 'LEAVING']:
                    Domoticz.Log(f"Mower {mower_name} returned to charging station.")
            elif activity == 'PARKED_IN_CS':
                if previous in ['GOING_HOME', 'MOWING', 'LEAVING', 'CHARGING']:
                    Domoticz.Log(f"Mower {mower_name} is parked in charging station.")
            elif activity == 'STOPPED_IN_GARDEN':
                Domoticz.Log(f"Mower {mower_name} stopped in garden.")

        self.previous_activity[mower_name] = activity

        # Determine image based on mower state
        image = Images[ImageIdentifier.OFF.value].ID if mower.get('state') == 'OFF' else Images[ImageIdentifier.STANDARD.value].ID

        # Update state text
        state_text = self._format_state_text(mower)
        update_device(False, Devices, mower_name, UnitId.STATE, 0, state_text, Image=image)

        # Update running status
        if mower.get('activity') in ['LEAVING', 'MOWING', 'CHARGING', 'GOING_HOME']:
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
            update_device(False, Devices, mower_name, UnitId.CUTTING, 2, 10 * (mower['cutting_height'] - 1), Image=image)

        # Update actions selector
        action_image = Images[ImageIdentifier.OFF.value].ID if mower['state'] == 'OFF' else Images[ImageIdentifier.INVERSE.value].ID
        update_device(True, Devices, mower_name, UnitId.ACTIONS, 2, 0, Image=action_image)

        # Update next schedule
        schedule_text = self._format_schedule_text(mower)
        update_device(False, Devices, mower_name, UnitId.SCHEDULE, 0, schedule_text, Image=image)

    def _format_state_text(self, mower: Dict[str, Any]) -> str:
        """Format the state text based on mower state, activity, and error."""

        STATE_MAP = {
            'OFF':              'Off',
            'WAIT_UPDATING':    'Updating firmware',
            'WAIT_POWER_UP':    'Starting up',
            'OK':               'OK',
            'ERROR':            'Error',
            'ERROR_AT_POWER_UP':'Error at startup',
            'FATAL_ERROR':      'Fatal error',
            'RESTRICTED':       'Restricted',
            'PAUSED':           'Paused',
            'IN_OPERATION':     'In operation',
            'STOPPED':          'Stopped',
        }

        ACTIVITY_MAP = {
            'UNKNOWN':                  'Unknown',
            'NOT_APPLICABLE':           None,
            'MOWING':                   'Mowing',
            'GOING_HOME':               'Going home',
            'CHARGING':                 'Charging',
            'LEAVING':                  'Leaving',
            'PARKED_IN_CS':             'Parked in charging station',
            'STOPPED_IN_GARDEN':        'Stopped in garden',
            'CUTTING_NOT_POSSIBLE':     'Cutting not possible',
        }

        RESTRICTED_MAP = {
            'NONE':                     None,
            'NOT_APPLICABLE':           None,
            'WEEK_SCHEDULE':            None,
            'PARK_OVERRIDE':            'Parked (override)',
            'SENSOR':                   None,
            'DAILY_LIMIT':              'Daily limit reached',
            'FOTA':                     'Firmware update',
            'FROST':                    'Frost protection',
            'ALL_WORK_AREAS_COMPLETED': 'All areas completed',
            'EXTERNAL':                 'External restriction',
        }

        error_state = mower.get('error_state')
        state = mower.get('state', '')
        activity = mower.get('activity', '')
        restricted_reason = mower.get('restricted_reason', '')

        state_str = STATE_MAP.get(state, state)
        activity_str = ACTIVITY_MAP.get(activity, activity)
        restricted_str = RESTRICTED_MAP.get(restricted_reason, restricted_reason) if restricted_reason else None

        if error_state:
            base = state_str
            if activity_str:
                base += f': {activity_str}'
            return f"{base}\n<body><p style=\"line-height:80%;font-size:80%;\">{error_state.strip()}</p></body>"

        elif activity_str is None:
            # NOT_APPLICABLE - show state only, with optional restriction
            if restricted_str:
                return f'{state_str}: {restricted_str}'
            return state_str

        elif activity_str:
            if state == 'RESTRICTED':
                # Show activity only, without "Restricted:" prefix
                if restricted_str:
                    return f'{activity_str} ({restricted_str})'
                return activity_str
            return f'{state_str}: {activity_str}'

        return state_str

    def _determine_mower_zone(self, mower: Dict[str, Any]) -> str:
        """Determine the garden zone where the mower is located."""
        location_data = mower.get('location')
        if location_data and location_data.get('latitude') is not None and location_data.get('longitude') is not None:
            return self._find_nearest_zone({'latitude': location_data['latitude'], 'longitude': location_data['longitude']})

        # Geen GPS beschikbaar - gebruik de eerste zone uit de configuratie als fallback
        if self.config.zones:
            fallback_zone = self.config.zones[0]
            if isinstance(fallback_zone, dict) and 'name' in fallback_zone:
                Domoticz.Debug(f"No GPS available, using fallback zone: {fallback_zone['name']}")
                return fallback_zone['name']

        return 'Unknown'

    def _find_nearest_zone(self, position: Dict[str, float]) -> str:
        """Find the nearest zone based on GPS coordinates."""
        Domoticz.Debug(f"Inside _find_nearest_zone: self.config.zones = {self.config.zones}")

        if not self.config.zones:
            Domoticz.Debug("No garden zones configured.")
            return "Unknown"

        try:
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

    def _format_schedule_text(self, mower: Dict[str, Any]) -> str:
        """
        Format the next scheduled mowing session as readable text.
        Uses nextStartTimestamp from the Husqvarna planner API (milliseconds).
        Note: Husqvarna API returns local time in the timestamp, not UTC.
        utcfromtimestamp is used intentionally to avoid double timezone conversion.
        """
        timestamp_ms = mower.get('next_start_timestamp')
        restricted_reason = mower.get('restricted_reason')
        activity = mower.get('activity', '')

        if timestamp_ms is None or timestamp_ms == 0:
            # Show a meaningful status based on current activity instead of "No schedule"
            activity_text_map = {
                'MOWING':            'Now mowing',
                'LEAVING':           'Now leaving station',
                'GOING_HOME':        'Returning home',
                'CHARGING':          'Charging',
                'PARKED_IN_CS':      'Parked',
                'STOPPED_IN_GARDEN': 'Stopped in garden',
            }
            return activity_text_map.get(activity, 'No schedule')

        try:
            # Husqvarna API provides timestamp in local time despite being milliseconds epoch.
            # utcfromtimestamp avoids applying an additional local timezone offset.
            slot_dt = datetime.datetime.utcfromtimestamp(timestamp_ms / 1000)
            now = datetime.datetime.now()

            if slot_dt.date() == now.date():
                day_label = 'Today'
            elif slot_dt.date() == (now + datetime.timedelta(days=1)).date():
                day_label = 'Tomorrow'
            else:
                day_label = slot_dt.strftime('%A')

            result = f'{day_label} {slot_dt.strftime("%H:%M")}'

            if restricted_reason and restricted_reason not in ('NONE', 'NOT_APPLICABLE'):
                reason_map = {
                    'WEEK_SCHEDULE':            'scheduled',
                    'PARK_OVERRIDE':            'parked (override)',
                    'SENSOR':                   'sensor restriction',
                    'DAILY_LIMIT':              'daily limit reached',
                    'FOTA':                     'firmware update',
                    'FROST':                    'frost protection',
                    'ALL_WORK_AREAS_COMPLETED': 'all areas done',
                }
                reason_text = reason_map.get(restricted_reason, restricted_reason)
                result += f' ({reason_text})'

            return result

        except Exception as e:
            Domoticz.Debug(f"Error formatting schedule text: {e}")
            return 'No schedule'

    def _create_missing_devices(self, mower_name: str) -> None:
        """
        Create any missing Domoticz devices for a mower.
        This allows adding new device types without requiring deletion of existing ones.
        Called once per mower from _handle_get_mowers_task, not on every poll.
        """
        existing_units = set()
        if Devices.get(mower_name):
            existing_units = {unit for unit in Devices[mower_name].Units}

        if UnitId.STATE not in existing_units:
            Domoticz.Unit(
                DeviceID=mower_name,
                Unit=UnitId.STATE,
                Name=f"{Parameters['Name']} - {mower_name} - {DeviceText.STATE.value}",
                TypeName='Text',
                Image=Images[ImageIdentifier.STANDARD.value].ID,
                Used=1
            ).Create()

        if UnitId.RUN not in existing_units:
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

        if UnitId.BATTERY not in existing_units:
            Domoticz.Unit(
                DeviceID=mower_name,
                Unit=UnitId.BATTERY,
                Name=f"{Parameters['Name']} - {mower_name} - {DeviceText.BATTERY.value}",
                TypeName='Custom',
                Options={'Custom': '0;%'},
                Image=Images[ImageIdentifier.STANDARD.value].ID,
                Used=0
            ).Create()

        if UnitId.LOCATION not in existing_units:
            Domoticz.Unit(
                DeviceID=mower_name,
                Unit=UnitId.LOCATION,
                Name=f"{Parameters['Name']} - {mower_name} - {DeviceText.LOCATION.value}",
                TypeName='Text',
                Image=Images[ImageIdentifier.STANDARD.value].ID,
                Used=1
            ).Create()

        if UnitId.CUTTING not in existing_units:
            self._create_cutting_height_selector(mower_name)

        if UnitId.ACTIONS not in existing_units:
            actions = f"|{HusqvarnaAction.START_6H.value}|{HusqvarnaAction.PAUSE.value}|{HusqvarnaAction.RESUME_SCHEDULE.value}|{HusqvarnaAction.PARK_UNTIL_FURTHER_NOTICE.value}|{HusqvarnaAction.PARK_UNTIL_NEXT_SCHEDULE.value}"
            Domoticz.Unit(
                DeviceID=mower_name,
                Unit=UnitId.ACTIONS,
                Name=f"{Parameters['Name']} - {mower_name} - {DeviceText.ACTIONS.value}",
                TypeName='Selector Switch',
                Options={
                    'LevelActions': '|'*actions.count('|'),
                    'LevelNames': actions,
                    'LevelOffHidden': 'false',
                    'SelectorStyle': '1'
                },
                Image=Images[ImageIdentifier.STANDARD.value].ID,
                Used=1
            ).Create()

        if UnitId.SCHEDULE not in existing_units:
            Domoticz.Unit(
                DeviceID=mower_name,
                Unit=UnitId.SCHEDULE,
                Name=f"{Parameters['Name']} - {mower_name} - {DeviceText.SCHEDULE.value}",
                TypeName='Text',
                Image=Images[ImageIdentifier.STANDARD.value].ID,
                Used=1
            ).Create()

        Domoticz.Debug(f"Device check complete for mower '{mower_name}'. Existing units: {existing_units}")

    def _create_mower_devices(self, mower_name: str) -> None:
        """
        Create all Domoticz devices for a new mower.
        Delegates to _create_missing_devices and sets initial timeout.
        Args:
            mower_name: Name of the mower
        """
        self._create_missing_devices(mower_name)
        timeout_device(Devices, device_id=mower_name)

    def _create_cutting_height_selector(self, mower_name: str) -> None:
        """Create the cutting height selector with proper range."""
        min_height = self.config.height_min_max.get('min')
        max_height = self.config.height_min_max.get('max')
        steps = self.config.height_min_max.get('steps')

        if min_height is not None and max_height is not None and steps is not None and steps >= 1:
            if steps > 1:
                height_interval = (max_height - min_height) / (steps - 1)
                height_range = [min_height + i * height_interval for i in range(steps)]
            else:
                height_range = [min_height]

            level_names = '|'.join(f'{height:.1f}' for height in height_range)

            Domoticz.Unit(
                DeviceID=mower_name,
                Unit=UnitId.CUTTING,
                Name=f"{Parameters['Name']} - {mower_name} - {DeviceText.CUTTING.value}",
                TypeName='Selector Switch',
                Options={
                    'LevelActions': '|' * (steps - 1),
                    'LevelNames': level_names,
                    'LevelOffHidden': 'false',
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

        if mower_name not in self.execution_status:
            self.execution_status[mower_name] = ExecutionState()

        status = None

        try:
            if action == HusqvarnaAction.START.value:
                status = self.husqvarna_api.action_Start(mower_name, duration=1440)
            elif action == HusqvarnaAction.START_6H.value:
                status = self.husqvarna_api.action_Start(mower_name, duration=360)
            elif action == HusqvarnaAction.PARK_UNTIL_FURTHER_NOTICE.value:
                status = self.husqvarna_api.action_ParkUntilFurtherNotice(mower_name)
            elif action == HusqvarnaAction.PARK_UNTIL_NEXT_SCHEDULE.value:
                status = self.husqvarna_api.action_ParkUntilNextSchedule(mower_name)
            elif action == HusqvarnaAction.PAUSE.value:
                status = self.husqvarna_api.action_Pause(mower_name)
            elif action == HusqvarnaAction.RESUME_SCHEDULE.value:
                status = self.husqvarna_api.action_ResumeSchedule(mower_name)
            elif action == HusqvarnaAction.SET_CUTTING_HEIGHT.value:
                cutting_height = task.get('Cutting_height')
                if cutting_height is not None:
                    status = self.husqvarna_api.set_cutting_height(mower_name, cutting_height)
                else:
                    Domoticz.Debug(f"Missing cutting height value for {mower_name}")

            if status is None:
                Domoticz.Error(f"Unknown action code {action}")
            elif status:
                self.execution_status[mower_name].status = ExecutionStatus.DONE
            else:
                Domoticz.Error(f"Error executing {action} on {mower_name}: {self.husqvarna_api.get_http_error()}")
                timeout_device(Devices, device_id=mower_name)
                self.execution_status[mower_name].status = ExecutionStatus.ERROR

            self.run_again = DomoticzConstants.MINUTE / 2

        except Exception as e:
            Domoticz.Error(f"Error executing command {action} on {mower_name}: {e}")
            self.execution_status[mower_name].status = ExecutionStatus.ERROR


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
