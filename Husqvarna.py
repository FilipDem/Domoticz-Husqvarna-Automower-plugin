#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Husqvarna API Module

This module provides a Python interface to the Husqvarna Automower API, allowing control
and monitoring of Husqvarna robotic lawn mowers. It handles authentication, API requests,
rate limiting, and various mower operations.

Based on the official Husqvarna API:
https://developer.husqvarnagroup.cloud/

Author: Filip Demaertelaere
Version: 2.0.0
"""

import time
import httpx
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union, Tuple, cast
from enum import Enum
from dataclasses import dataclass, field
import json

# Configure logging based on environment
try:
    import DomoticzEx as Domoticz
    
    def log(msg: str = "") -> None:
        """Log to Domoticz debug log with length management."""
        formatted = f"{msg}"
        if len(formatted) <= 5000:
            Domoticz.Debug(f">> {formatted}")
        else:
            Domoticz.Debug(">> (in several blocks)")
            # Split message into smaller chunks for Domoticz log limit
            chunks = [formatted[i:i+5000] for i in range(0, len(formatted), 5000)]
            for chunk in chunks:
                Domoticz.Debug(f">> {chunk}")
except ImportError:
    # Fallback log function if Domoticz modules aren't available
    def log(msg: str = "") -> None:
        """Simple print-based logging for non-Domoticz environments."""
        print(msg)

class ApiEndpoints:
    """API endpoints for Husqvarna cloud services."""
    TOKEN_REQUEST = 'https://api.authentication.husqvarnagroup.dev/v1/oauth2/token'
    BASE_API = 'https://api.amc.husqvarna.dev/v1/'
    MOWERS = f'{BASE_API}mowers'

class ApiConfig:
    """Configuration values for API communication."""
    RETRY_DELAY = 2             # Seconds between API calls for retries
    TIMEOUT = 8                 # Seconds for connection and read timeout
    TOKEN_REFRESH_MARGIN = 600  # Seconds before token expiration to refresh

class HttpMethod(Enum):
    """HTTP methods used for API requests."""
    POST = 0
    GET = 1

class MowerAction(str, Enum):
    """Actions that can be sent to the mower."""
    PARK_NEXT_SCHEDULE = 'ParkUntilNextSchedule'
    PARK_FURTHER_NOTICE = 'ParkUntilFurtherNotice'
    RESUME_SCHEDULE = 'ResumeSchedule'
    START = 'Start'
    PAUSE = 'Pause'

@dataclass
class ApiState:
    """State information for API communication."""
    access_token: Optional[Dict[str, Any]] = None
    access_token_expiration: datetime = field(default_factory=lambda: datetime(2000, 1, 1))
    timestamp_last_update_mower_list: datetime = field(default_factory=lambda: datetime(2000, 1, 1))
    error: Optional[str] = None
    api_limit_reached: bool = False
    authenticated: bool = False

class Activity(Enum):
    """ 
    Human-readable labels for mower activities (shared across methods). 
    https://developer.husqvarnagroup.cloud/apis/automower-connect-api?tab=status%20description%20and%20error%20codes
    """
    UNKNOWN = 'Unknown'
    NOT_APPLICABLE = 'Not applicable'
    MOWING = 'Mowing'
    GOING_HOME = 'Going home'
    CHARGING = 'Charging'
    LEAVING = 'Leaving base'
    PARKED_IN_CS = 'Parked in base'
    STOPPED_IN_GARDEN = 'Stopped in garden'

class State(Enum):
    """ Human-readable labels for mower states (shared across methods).
    https://developer.husqvarnagroup.cloud/apis/automower-connect-api?tab=status%20description%20and%20error%20codes
    """
    UNKNOWN = 'Unknown'
    NOT_APPLICABLE = ''
    PAUSED = 'Pauzed'
    IN_OPERATION = 'In operation'
    WAIT_UPDATING = 'Updating firmware'
    WAIT_POWER_UP = 'Power-up testing'
    RESTRICTED = 'Not mowing'
    OFF = 'Switched off'
    STOPPED = 'Stopped'
    ERROR = 'Error'
    FATAL_ERROR = 'Fatal error'
    ERROR_AT_POWER_UP = 'Error at power-up'

class PlannerRestrictedReason(Enum):
    """ Human-readable labels for mower restricted reasons when using the planner.
    https://developer.husqvarnagroup.cloud/apis/automower-connect-api?tab=openapi
    """
    NONE = None
    WEEK_SCHEDULE = None
    PARK_OVERRIDE = 'Parked (override)'
    SENSOR = 'Grass too short'
    DAILY_LIMIT = 'Daily mowering limit reached'
    FOTA = 'Updating firmware'
    FROST = 'Frost protection'
    ALL_WORK_AREAS_COMPLETED = 'All areas completed'
    EXTERNAL = 'External reason'
    WORK_AREA_ABANDONED = 'Areas could not be completed'

class ErrorCodes:
    """
    Error codes dictionary for Husqvarna mowers.
    Maps numeric error codes to human-readable descriptions.
    https://developer.husqvarnagroup.cloud/apis/automower-connect-api?tab=status%20description%20and%20error%20codes
    """
    CODES = {
        0:    'Unexpected error',
        1:    'Outside working area',
        2:    'No loop signal',
        3:    'Wrong loop signal',
        4:    'Loop sensor problem, front',
        5:    'Loop sensor problem, rear',
        6:    'Loop sensor problem, left',
        7:    'Loop sensor problem, right',
        8:    'Wrong PIN code',
        9:    'Trapped',
        10:   'Upside down',
        11:   'Low battery',
        12:   'Empty battery',
        13:   'No drive',
        14:   'Mower lifted',
        15:   'Lifted',
        16:   'Stuck in charging station',
        17:   'Charging station blocked',
        18:   'Collision sensor problem, rear',
        19:   'Collision sensor problem, front',
        20:   'Wheel motor blocked, right',
        21:   'Wheel motor blocked, left',
        22:   'Wheel drive problem, right',
        23:   'Wheel drive problem, left',
        24:   'Cutting system blocked',
        25:   'Cutting system blocked',
        26:   'Invalid sub-device combination',
        27:   'Settings restored',
        28:   'Memory circuit problem',
        29:   'Slope too steep',
        30:   'Charging system problem',
        31:   'STOP button problem',
        32:   'Tilt sensor problem',
        33:   'Mower tilted',
        34:   'Cutting stopped - slope too steep',
        35:   'Wheel motor overloaded, right',
        36:   'Wheel motor overloaded, left',
        37:   'Charging current too high',
        38:   'Electronic problem',
        39:   'Cutting motor problem',
        40:   'Limited cutting height range',
        41:   'Unexpected cutting height adj',
        42:   'Limited cutting height range',
        43:   'Cutting height problem, drive',
        44:   'Cutting height problem, curr',
        45:   'Cutting height problem, dir',
        46:   'Cutting height blocked',
        47:   'Cutting height problem',
        48:   'No response from charger',
        49:   'Ultrasonic problem',
        50:   'Guide 1 not found',
        51:   'Guide 2 not found',
        52:   'Guide 3 not found',
        53:   'GPS navigation problem',
        54:   'Weak GPS signal',
        55:   'Difficult finding home',
        56:   'Guide calibration accomplished',
        57:   'Guide calibration failed',
        58:   'Temporary battery problem',
        59:   'Temporary battery problem',
        60:   'Temporary battery problem',
        61:   'Temporary battery problem',
        62:   'Temporary battery problem',
        63:   'Temporary battery problem',
        64:   'Temporary battery problem',
        65:   'Temporary battery problem',
        66:   'Battery problem',
        67:   'Battery problem',
        68:   'Temporary battery problem',
        69:   'Alarm! Mower switched off',
        70:   'Alarm! Mower stopped',
        71:   'Alarm! Mower lifted',
        72:   'Alarm! Mower tilted',
        73:   'Alarm! Mower in motion',
        74:   'Alarm! Outside geofence',
        75:   'Connection changed',
        76:   'Connection NOT changed',
        77:   'Com board not available',
        78:   'Slipped - Mower has Slipped.Situation not solved with moving pattern',
        79:   'Invalid battery combination - Invalid combination of different battery types.',
        80:   'Cutting system imbalance',
        81:   'Safety function faulty',
        82:   'Wheel motor blocked, rear right',
        83:   'Wheel motor blocked, rear left',
        84:   'Wheel drive problem, rear right',
        85:   'Wheel drive problem, rear left',
        86:   'Wheel motor overloaded, rear right',
        87:   'Wheel motor overloaded, rear left',
        88:   'Angular sensor problem',
        89:   'Invalid system configuration',
        90:   'No power in charging station',
        91:   'Switch cord problem',
        92:   'Work area not valid',
        93:   'No accurate position from satellites',
        94:   'Reference station communication problem',
        95:   'Folding sensor activated',
        96:   'Right brush motor overloaded',
        97:   'Left brush motor overloaded',
        98:   'Ultrasonic Sensor 1 defect',
        99:   'Ultrasonic Sensor 2 defect',
        100:  'Ultrasonic Sensor 3 defect',
        101:  'Ultrasonic Sensor 4 defect',
        102:  'Cutting drive motor 1 defect',
        103:  'Cutting drive motor 2 defect',
        104:  'Cutting drive motor 3 defect',
        105:  'Lift Sensor defect',
        106:  'Collision sensor defect',
        107:  'Docking sensor defect',
        108:  'Folding cutting deck sensor defect',
        109:  'Loop sensor defect',
        110:  'Collision sensor error',
        111:  'No confirmed position',
        112:  'Cutting system major imbalance',
        113:  'Complex working area',
        114:  'Too high discharge current',
        115:  'Too high internal current',
        116:  'High charging power loss',
        117:  'High internal power loss',
        118:  'Charging system problem',
        119:  'Zone generator problem',
        120:  'Internal voltage error',
        121:  'High internal temerature',
        122:  'CAN error',
        123:  'Destination not reachable',
        124:  'Destination blocked',
        125:  'Battery needs replacement',
        126:  'Battery near end of life',
        127:  'Battery problem',
        701:  'Connectivity problem',
        702:  'Connectivity settings restored',
        703:  'Connectivity problem',
        704:  'Connectivity problem',
        705:  'Connectivity problem',
        706:  'Poor signal quality',
        707:  'SIM card requires PIN',
        708:  'SIM card locked',
        709:  'SIM card not found',
        710:  'SIM card locked',
        711:  'SIM card locked',
        712:  'SIM card locked',
        713:  'Geofence problem',
        714:  'Geofence problem',
        715:  'Connectivity problem',
        716:  'Connectivity problem',
        717:  'SMS could not be sent',
        724:  'Communication circuit board SW must be updated'
    }
    
    @classmethod
    def get_description(cls, code: Optional[int]) -> Optional[str]:
        """Get the error description for a given error code."""
        if code is None:
            return None
        return cls.CODES.get(code, f"Unknown error code: {code}")


class Husqvarna:
    """
    Husqvarna API client for controlling and monitoring Automower devices.
    This class provides methods to authenticate with the Husqvarna API,
    retrieve mower information, and send commands to mowers.
    """
    
    def __init__(self, client_id: str, client_secret: str):
        """
        Initialize the Husqvarna API client.
        Args:
            client_id: The client ID (application ID) from Husqvarna Developer Portal
            client_secret: The client secret from Husqvarna Developer Portal
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.mowers: List[Dict[str, Any]] = []
        self.state = ApiState()
        self.session = self._create_session()
        self.state.authenticated = self._get_access_token()

    def __bool__(self) -> bool:
        """
        Check if the API client is properly authenticated.
        Returns:
            bool: True if authenticated, False otherwise
        """
        # log(f'Husqvarna object returns {self.state.authenticated}.')
        return self.state.authenticated

    def __enter__(self) -> 'Husqvarna':
        """Context manager entry point."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - ensure the session is closed."""
        self.close()

    def _create_session(self) -> httpx.Client:
        """
        Create an HTTP session for API communication.
        Returns:
            httpx.Client: Configured HTTP client
        """
        return httpx.Client(
            verify=False,
            headers={
                'x-api-key': self.client_id,
                'accept': 'application/vnd.api+json'
            }
        )

    def get_mowers(self) -> bool:
        """
        Retrieve the list of mowers associated with the account.
        Returns:
            bool: True if successful, False otherwise
        """
        if self._check_access_token_and_renew():
            if self._get_mowers():
                self.state.timestamp_last_update_mower_list = datetime.now()
                return True
        return False

    def get_mower_messages(self, mower_name: str) -> Optional[Dict[str, Any]]:
        """
        Get messages for a specific mower.
        Args:
            mower_name: Name of the mower
        Returns:
            Optional[Dict[str, Any]]: Messages if available, None otherwise
        """
        if not self._check_access_token_and_renew():
            return None

        if ( mower_id := self._find_id_from_name(mower_name) ):
            return self._http_with_retry(
                HttpMethod.GET,
                f'{ApiEndpoints.MOWERS}/{mower_id}/messages',
                mower_name=mower_name
            )
        return None

    def get_mowers_info(self) -> bool:
        """
        Get detailed information for all mowers.
        Returns:
            bool: True if successful, False otherwise
        """
        if self._check_access_token_and_renew():
            return self._get_mower_detailed_info()
        return False

    def get_mower_from_name(self, mower_name: str) -> Optional[Dict[str, Any]]:
        """
        Get mower data by name.
        Args:
            mower_name: Name of the mower
        Returns:
            Optional[Dict[str, Any]]: Mower data if found, None otherwise
        """
        for mower in self.mowers:
            if mower.get('name') == mower_name:
                return mower
        return None

    def action_ParkUntilNextSchedule(self, mower_name: str) -> bool:
        """
        Command the mower to park until the next scheduled mowing session.
        Args:
            mower_name: Name of the mower
        Returns:
            bool: True if successful, False otherwise
        """
        return self._send_action_to_mower(mower_name, MowerAction.PARK_NEXT_SCHEDULE)

    def action_ParkUntilFurtherNotice(self, mower_name: str) -> bool:
        """
        Command the mower to park until manually started again.
        Args:
            mower_name: Name of the mower
        Returns:
            bool: True if successful, False otherwise
        """
        return self._send_action_to_mower(mower_name, MowerAction.PARK_FURTHER_NOTICE)

    def action_Pause(self, mower_name: str) -> bool:
        """
        Pause the mower's current operation.
        Args:
            mower_name: Name of the mower
        Returns:
            bool: True if successful, False otherwise
        """
        return self._send_action_to_mower(mower_name, MowerAction.PAUSE)

    def action_ResumeSchedule(self, mower_name: str) -> bool:
        """
        Resume the mower's normal schedule.
        Args:
            mower_name: Name of the mower
        Returns:
            bool: True if successful, False otherwise
        """
        return self._send_action_to_mower(mower_name, MowerAction.RESUME_SCHEDULE)

    def action_Start(self, mower_name: str, duration: int = 60) -> bool:
        """
        Start mowing for a specified duration.
        Args:
            mower_name: Name of the mower
            duration: Mowing duration in minutes (default: 60)
        Returns:
            bool: True if successful, False otherwise
        """
        return self._send_action_to_mower(mower_name, MowerAction.START, duration=duration)

    def set_headlight(self, mower_name: str, light: bool) -> bool:
        """
        Set the mower's headlight state.
        Args:
            mower_name: Name of the mower
            light: True to turn on, False to turn off
        Returns:
            bool: True if successful, False otherwise
        """
        if not self._check_access_token_and_renew():
            return False

        if ( mower_id := self._find_id_from_name(mower_name) ):
            headlight_mode = 'ALWAYS_ON' if light else 'ALWAYS_OFF'
            json_payload = {
                'data': {
                    'type': 'settings',
                    'attributes': {
                        'headlight': {
                            'mode': headlight_mode
                        }
                    }
                }
            }
            
            self.session.headers.update({'Content-Type': 'application/vnd.api+json'})
            response = self._http_with_retry(
                HttpMethod.POST,
                f'{ApiEndpoints.MOWERS}/{mower_id}/settings',
                json_post_data=json_payload,
                mower_name=mower_name
            )
            return bool(response)
        return False

    def set_cutting_height(self, mower_name: str, height: float) -> bool:
        """
        Set the mower's cutting height.
        Args:
            mower_name: Name of the mower
            height: Cutting height in centimeters
        Returns:
            bool: True if successful, False otherwise
        """
        if not self._check_access_token_and_renew():
            return False

        if ( mower_id := self._find_id_from_name(mower_name) ):
            json_payload = {
                'data': {
                    'type': 'settings',
                    'attributes': {
                        'cuttingHeight': height
                    }
                }
            }
            
            self.session.headers.update({'Content-Type': 'application/vnd.api+json'})
            response = self._http_with_retry(
                HttpMethod.POST,
                f'{ApiEndpoints.MOWERS}/{mower_id}/settings',
                json_post_data=json_payload,
                mower_name=mower_name
            )
            return bool(response)
        return False

    def get_timestamp_last_update_mower_list(self) -> datetime:
        """
        Get the timestamp of the last update of the mower list.
        Returns:
            datetime: Timestamp of last update
        """
        return self.state.timestamp_last_update_mower_list

    def is_mower_off(self, name_or_mower: Union[str, Dict[str, Any]]) -> Optional[bool]:
        """
        Check if a mower is in the OFF state.
        Args:
            name_or_mower: Either the mower name or a mower dict
        Returns:
            Optional[bool]: True if off, False if on, None if mower not found
        """
        if isinstance(name_or_mower, dict):
            mower = name_or_mower
        else:
            mower = self.get_mower_from_name(name_or_mower)
        if mower:
            return mower.get('state') == State.OFF.name
        return None

    def are_all_mowers_off(self) -> bool:
        """
        Check if all mowers are in the OFF state.
        Returns:
            bool: True if all mowers are off, False otherwise
        """
        return all(
            mower.get('state') == State.OFF.name
            for mower in self.mowers
        )

    def are_api_limits_reached(self) -> bool:
        """
        Check if API rate limits have been reached.
        Returns:
            bool: True if limits reached, False otherwise
        """
        return self.state.api_limit_reached

    def close(self) -> None:
        """Close the HTTP session."""
        if self.session:
            self.session.close()
            self.session = None

    def get_http_error(self) -> Optional[str]:
        """
        Get the last HTTP error message.
        Returns:
            Optional[str]: Error message or None if no error
        """
        return self.state.error

    def _get_access_token(self) -> bool:
        """
        Authenticate with the Husqvarna API and get an access token.
        Returns:
            bool: True if successful, False otherwise
        """
        # Clear existing headers
        self.session.headers.clear()
        self.session.headers.update({'Content-Type': 'application/x-www-form-urlencoded'})
        
        # Prepare authentication data
        auth_data = {
            'grant_type': 'client_credentials',
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'token_endpoint': ApiEndpoints.TOKEN_REQUEST
        }
        
        # Make the request
        response = self._http_with_retry(
            HttpMethod.POST,
            ApiEndpoints.TOKEN_REQUEST,
            post_data=auth_data
        )
        
        # Process the response
        if response:
            self.state.access_token = response
            self.state.error = None
            
            # Calculate token expiration time with a safety margin
            self.state.access_token_expiration = (
                datetime.now() + 
                timedelta(seconds=response.get('expires_in', 0)) - 
                timedelta(seconds=ApiConfig.TOKEN_REFRESH_MARGIN)
            )
            
            # Update session headers with token
            self.session.headers.update({
                'x-api-key': self.client_id,
                'Authorization': f"{response.get('token_type', '')} {response.get('access_token', '')}",
                'Authorization-Provider': response.get('provider', ''),
                'accept': 'application/vnd.api+json'
            })
            
            log(f"New access token generated! Expiration: {datetime.now() + timedelta(seconds=response.get('expires_in', 0))} - "
                f"Type: {response.get('token_type', '')} - Token: ...{response.get('access_token', 'N/A')[-20:]}.")
                
            return True
        else:
            self.state.error = f'Bad or unauthorized authentication request (url: {ApiEndpoints.TOKEN_REQUEST}).'
            return False

    def _check_access_token_and_renew(self) -> bool:
        """
        Check if the current access token is valid and renew if needed.
        Returns:
            bool: True if a valid token is available, False otherwise
        """
        if datetime.now() > self.state.access_token_expiration:
            log('Create new access token!')
            self.state.authenticated = self._get_access_token() 
            return self.state.authenticated
            
        log(f"Use existing access token! Expiration: "
            f"{self.state.access_token_expiration} - "
            f"Type: {self.state.access_token.get('token_type', '') if self.state.access_token else 'N/A'} - "
            f"Token: ...{self.state.access_token.get('access_token', 'N/A')[-20:] if self.state.access_token else 'N/A'}.")

        self.state.authenticated = True    
        return self.state.authenticated

    def _get_mowers(self) -> bool:
        """
        Retrieve the list of mowers from the API.
        Returns:
            bool: True if successful, False otherwise
        """
        response = self._http_with_retry(HttpMethod.GET, ApiEndpoints.MOWERS)
        if response:
            # Extract mower IDs and names
            try:
                self.mowers = [
                    {
                        'id': mower.get('id'),
                        'name': mower.get('attributes', {}).get('system', {}).get('name')
                    }
                    for mower in response.get('data', [])
                ]
                return True
            except (KeyError, TypeError) as e:
                log(f"Error parsing mower list: {e}")
                return False
        return False

    def _get_mower_detailed_info(self) -> bool:
        """
        Retrieve detailed information for all mowers.
        Returns:
            bool: True if successful for all mowers, False otherwise
        """
        status = True
        
        for index, mower in enumerate(self.mowers):
            mower_id = mower.get('id')
            mower_name = mower.get('name')
            
            if not mower_id or not mower_name:
                log(f"Skipping mower at index {index} due to missing ID or name")
                status = False
                continue
                
            # Request detailed mower information
            mower_info = self._http_with_retry(
                HttpMethod.GET,
                f"{ApiEndpoints.MOWERS}/{mower_id}",
                mower_name=mower_name
            )
            
            if mower_info and 'data' in mower_info:
                try:
                    # Extract and store relevant information
                    attributes = mower_info['data'].get('attributes', {})
                    
                    # Battery information
                    self.mowers[index]['battery_pct'] = attributes.get('battery', {}).get('batteryPercent')
                    
                    # Status information
                    self.mowers[index]['activity'] = attributes.get('mower', {}).get('activity')
                    self.mowers[index]['state'] = attributes.get('mower', {}).get('state')
                    
                    # Position information
                    positions = attributes.get('positions', [])
                    self.mowers[index]['location'] = positions[0] if positions else None
                    
                    # Settings
                    self.mowers[index]['cutting_height'] = attributes.get('settings', {}).get('cuttingHeight', 0)

                    # Schedule information
                    planner = attributes.get('planner', {})
                    self.mowers[index]['planner'] = {}
                    self.mowers[index]['planner']['next_start_timestamp'] = planner.get('nextStartTimestamp')
                    self.mowers[index]['planner']['restricted_reason'] = planner.get('restrictedReason')
                    
                    # Error information
                    try:
                        error_code = attributes.get('mower', {}).get('errorCode')
                        if self.mowers[index].get('state') in [State.ERROR.name, State.FATAL_ERROR.name, State.ERROR_AT_POWER_UP.name] and error_code is not None:
                            self.mowers[index]['error_state'] = ErrorCodes.get_description(error_code)
                        else:
                            self.mowers[index]['error_state'] = None
                    except Exception as e:
                        log(f"Error getting error state: {e}")
                        self.mowers[index]['error_state'] = None
                        
                except Exception as e:
                    log(f"Error parsing mower info for {mower_name}: {e}")
                    status = False
                    break
            else:
                status = False
                log(f"Failed to get detailed info for mower {mower_name}: {self.get_http_error()}")
                break
                
        return status

    def _send_action_to_mower(
        self, 
        mower_name: str, 
        action: MowerAction, 
        duration: int = 60
    ) -> bool:
        """
        Send a command action to a mower.
        Args:
            mower_name: Name of the mower
            action: The action to perform
            duration: Duration in minutes for timed actions (default: 60)
        Returns:
            bool: True if successful, False otherwise
        """
        # Validate the action
        if action not in [
            MowerAction.PARK_NEXT_SCHEDULE,
            MowerAction.PARK_FURTHER_NOTICE,
            MowerAction.PAUSE,
            MowerAction.RESUME_SCHEDULE,
            MowerAction.START
        ]:
            log(f"Unknown action requested: {action}")
            return False
            
        # Check token and get mower ID
        if not self._check_access_token_and_renew():
            return False
            
        mower_id = self._find_id_from_name(mower_name)
        if not mower_id:
            return False
            
        # Prepare payload
        if action == MowerAction.START:
            json_payload = {
                'data': {
                    'type': action,
                    'attributes': {
                        'duration': duration
                    }
                }
            }
        else:
            json_payload = {
                'data': {
                    'type': action
                }
            }
            
        # Send the command
        self.session.headers.update({'Content-Type': 'application/vnd.api+json'})
        response = self._http_with_retry(
            HttpMethod.POST,
            f'{ApiEndpoints.MOWERS}/{mower_id}/actions',
            json_post_data=json_payload,
            mower_name=mower_name
        )
        
        return bool(response)

    def _find_id_from_name(self, name: str) -> Optional[str]:
        """
        Find a mower's ID from its name.
        Args:
            name: Mower name
        Returns:
            Optional[str]: Mower ID if found, None otherwise
        """
        mower = self.get_mower_from_name(name)
        return mower.get('id') if mower else None

    def _analyze_http_error(
        self, 
        response: httpx.Response, 
        url: str, 
        mower_name: Optional[str] = None
    ) -> str:
        """
        Analyze an HTTP error response and create an informative error message.
        Args:
            response: The HTTP response
            url: The request URL
            mower_name: Optional mower name for context
        Returns:
            str: Formatted error message
        """
        # Check for API rate limiting
        self.state.api_limit_reached = (response.status_code == 429)
        
        try:
            # Try to parse error details from JSON response
            error_info = response.json()
            
            if 'errors' in error_info:
                error_detail = error_info['errors'][0] if error_info['errors'] else {}
                return f"({mower_name or 'Unknown'} - {response.status_code}) {error_detail.get('title', 'Unknown Error')}: {error_detail.get('detail', 'No detail')} (url: {url})"
                
            elif 'message' in error_info:
                return f"({mower_name or 'Unknown'} - {response.status_code}) {error_info.get('message', 'No message')} (url: {url})"
                
            else:
                return f"({mower_name or 'Unknown'} - {response.status_code}) Uncaptured error returned by Husqvarna API (url: {url})"
                
        except (httpx.JSONDecodeError, json.JSONDecodeError):
            # Handle non-JSON responses
            return f"({mower_name or 'Unknown'} - {response.status_code}) Uncaptured error returned by Husqvarna API (url: {url}, response: {response.text}) - JSON decode error"
            
        except Exception as e:
            # Handle unexpected errors during analysis
            return f"({mower_name or 'Unknown'} - {response.status_code}) Error analyzing API response (url: {url}, response: {response.text}): {e}"

    def _http_with_retry(
        self, 
        method: HttpMethod, 
        url: str, 
        json_post_data: Optional[Dict[str, Any]] = None, 
        post_data: Optional[Dict[str, Any]] = None, 
        mower_name: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Send an HTTP request with automatic retry for certain error conditions.
        Args:
            method: HTTP method (GET or POST)
            url: Request URL
            json_post_data: Optional JSON data for POST requests
            post_data: Optional form data for POST requests
            mower_name: Optional mower name for context
        Returns:
            Optional[Dict[str, Any]]: JSON response if successful, None otherwise
        """
        retry_counter = 0
        execution_status = False
        self.state.error = ''
        response = None

        while retry_counter < 3:

            # Be sure plugin is not stopping
            if self.session is None:
                break

            try:
                # Make the request
                if method == HttpMethod.GET:
                    response = self.session.get(url, timeout=ApiConfig.TIMEOUT)
                else:  # method == HttpMethod.POST
                    response = self.session.post(
                        url, 
                        json=json_post_data, 
                        data=post_data, 
                        timeout=ApiConfig.TIMEOUT
                    )

                # Handle different response categories
                if 200 <= response.status_code < 300:
                    # Success - 2xx status codes
                    self.state.error = None
                    self.state.api_limit_reached = False
                    execution_status = True
                    break
                    
                elif response.status_code == 403:
                    # Authentication error (403) - retry a few times
                    # Following the exchange with the helpdesk openapi.servicedesk@husqvarnagroup.com, there
                    # are regularly timeouts on the commands that translates also in an authentication error. Hence adding also retries...
                    log(f"Retry {retry_counter} - Authentication error (403) for url {url}. Retrying...")
                    retry_counter += 1
                    if retry_counter >= 3:
                        self.state.error = self._analyze_http_error(response, url, mower_name)
                        break
                        
                elif 400 <= response.status_code < 500:
                    # Other client errors (4xx) - don't retry
                    if response.status_code == 429:
                        log(f"Retry {retry_counter} - API limit reached (429) for url {url}.")
                    else:
                        log(f"Retry {retry_counter} - Client error ({response.status_code}) for url {url}. No retry.")
                    self.state.error = self._analyze_http_error(response, url, mower_name)
                    break
                    
                elif 500 <= response.status_code < 600:
                    # Server errors (5xx) - retry
                    log(f"Retry {retry_counter} - Server error ({response.status_code}) for url {url}. Retrying...")
                    retry_counter += 1
                    if retry_counter >= 3:
                        self.state.error = self._analyze_http_error(response, url, mower_name)
                        break
                        
                else:
                    # Unexpected status codes
                    log(f"Retry {retry_counter} - Unhandled HTTP status code ({response.status_code}) for url {url}. No retry.")
                    self.state.error = f'HTTP error ({response.status_code}) not specifically handled.'
                    break

            except (httpx.TimeoutException, httpx.ConnectError, httpx.RequestError) as e:
                # Connection and timeout errors
                self.state.error = f'Retry {retry_counter} - Connection error to url {url} with error "{e}".\n'
                log(self.state.error.strip())
                retry_counter += 1
                if retry_counter >= 3:
                    break

            # Wait before retrying
            if retry_counter < 3 and not execution_status:
                stop_time = time.time() + ApiConfig.RETRY_DELAY * (retry_counter + 1)
                while time.time() < stop_time:
                    if self.session is None:
                        break
                    time.sleep(0.1)

        # Return parsed JSON response if successful
        if execution_status and response is not None:
            try:
                return response.json()
            except (json.JSONDecodeError, httpx.JSONDecodeError) as e:
                log(f"Error parsing JSON response: {e}")
                self.state.error = f"Error parsing JSON response: {e}"
                return None

        # End
        return None


if __name__ == "__main__":
    """
    Example usage of the Husqvarna API client.
    This will authenticate, get mower information, and continuously
    monitor mower status if run directly.
    """
    # Example credentials - replace with your own
    CLIENT_ID = 'xxx'
    CLIENT_SECRET = 'yyy'
    
    husq = Husqvarna(CLIENT_ID, CLIENT_SECRET)
    
    if husq:
        if husq.get_mowers() and husq.get_mowers_info():
            print(husq.mowers)
            #print(f"Execute ParkUntilFurtherNotice: {husq.action_ParkUntilFurtherNotice(husq.mowers[0]['name'])} - {husq.get_http_error()}")
        else:
            print(f'Error getting mower information: {husq.get_http_error()}')
            
        # Continuous monitoring example
        while True:
            print(f'are_all_mowers_off: {husq.are_all_mowers_off()}')
            
            if husq.get_mowers_info():
                print(f'({datetime.now()}) {husq.mowers}')
                print(f"Get messages: {husq.get_mower_messages(husq.mowers[0]['name'])} - {husq.get_http_error()}")
            else:
                print(f'({datetime.now()}) Error getting mower information: {husq.get_http_error()}')
                
            time.sleep(30)
    else:
        print(husq.get_http_error())
