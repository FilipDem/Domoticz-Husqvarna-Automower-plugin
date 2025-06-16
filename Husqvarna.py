"""
Python module to get information from Husqvarna Mower.

Based on the Husqvarna official API.
https://developer.husqvarnagroup.cloud/applications

"""

try:
    import DomoticzEx as Domoticz
    def log(msg=""):
        # Check length to avoid Domoticz debug log limits
        if len('{}'.format(msg)) <= 5000:
            Domoticz.Debug(">> {}".format(msg))
        else:
            Domoticz.Debug(">> (in several blocks)")
            # Split message into smaller chunks
            string = [msg[i:i+5000] for i in range(0, len('{}'.format(msg)), 5000)]
            for k in string:
                Domoticz.Debug(">> {}".format(k))
except:
    # Fallback log function if DomoticzEx is not available
    def log(msg=""):
        print(msg)

import httpx
import time
from datetime import datetime, timedelta

URL_TOKEN_REQUEST = 'https://api.authentication.husqvarnagroup.dev/v1/oauth2/token'
URL_BASE_API = 'https://api.amc.husqvarna.dev/v1/'
URL_GET_MOWERS = f'{URL_BASE_API}mowers'
API_CALL_DELAY = 2
API_TIMEOUT = 5 #seconds (timeout is for connect and read by default in httpx when given as a single number)

ACTION_PARKNEXTSCHEDULE = 'ParkUntilNextSchedule'
ACTION_PARKFURTHERNOTICE = 'ParkUntilFurtherNotice'
ACTION_RESUMESCHEDULE = 'ResumeSchedule'
ACTION_START = 'Start'
ACTION_PAUSE = 'Pause'

STATE_OFF = 'OFF'

POST = 0
GET = 1

# Error codes dictionary remains the same
ErrorCodes = {
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
    80:   'Cutting system imbalance  Warning',
    81: 'Safety function faulty',
    82: 'Wheel motor blocked, rear right',
    83: 'Wheel motor blocked, rear left',
    84: 'Wheel drive problem, rear right',
    85: 'Wheel drive problem, rear left',
    86: 'Wheel motor overloaded, rear right',
    87: 'Wheel motor overloaded, rear left',
    88: 'Angular sensor problem',
    89: 'Invalid system configuration',
    90: 'No power in charging station',
    91: 'Switch cord problem',
    92: 'Work area not valid',
    93: 'No accurate position from satellites',
    94: 'Reference station communication problem',
    95: 'Folding sensor activated',
    96: 'Right brush motor overloaded',
    97: 'Left brush motor overloaded',
    98: 'Ultrasonic Sensor 1 defect',
    99: 'Ultrasonic Sensor 2 defect',
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

class Husqvarna():

    def __init__(self, client_id, client_secret):
        self.mowers = []
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = None
        self.access_token_expiration = datetime(2000,1,1)
        self.timestamp_last_update_mower_list = datetime(2000,1,1)
        self.error = None
        self.api_limit_reached = False
        self.session = self._create_session() # Create session using a method

    def __bool__(self):
        # __bool__ should return True or False.
        # The current implementation in _get_access_token returns a status boolean, which is fine.
        log('Return value on creation of Husqvarna object')
        return self._get_access_token()

    def __enter__(self):
        """Enables using the class with a context manager."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Ensures the httpx session is closed when exiting the context."""
        self.close()

    def _create_session(self):
        return httpx.Client(verify=False, headers={'x-api-key': self.client_id, 'accept': 'application/vnd.api+json'})

    def get_mowers(self):
        if self._check_access_token_and_renew():
            if ( status := self._get_mowers() ):
                self.timestamp_last_update_mower_list = datetime.now()
            return status
        return False

    def get_mower_messages(self, mower_name):
        if not self._check_access_token_and_renew():
            return False

        mower_id = self._find_id_from_name(mower_name)
        if mower_id:
            # _http_with_retry handles the GET call via self.session (httpx.Client)
            if ( mower_messages := self._http_with_retry(GET, f'{URL_GET_MOWERS}/{mower_id}/messages', mower_name=mower_name) ):
                return mower_messages
        return None

    def get_mowers_info(self):
        if self._check_access_token_and_renew():
            # _get_mower_detailed_info calls _http_with_retry which uses self.session (httpx.Client)
            return self._get_mower_detailed_info()
        return False

    def action_ParkUntilNextSchedule(self, mower_name):
        return self._send_action_to_mower(mower_name, ACTION_PARKNEXTSCHEDULE)

    def action_ParkUntilFurtherNotice(self, mower_name):
        return self._send_action_to_mower(mower_name, ACTION_PARKFURTHERNOTICE)

    def action_Pause(self, mower_name):
        return self._send_action_to_mower(mower_name, ACTION_PAUSE)

    def action_ResumeSchedule(self, mower_name):
        return self._send_action_to_mower(mower_name, ACTION_RESUMESCHEDULE)

    def action_Start(self, mower_name, duration=60):
        return self._send_action_to_mower(mower_name, ACTION_START, duration=duration)

    def get_mower_from_name(self, mower_name):
        return next( (mower for mower in self.mowers if mower['name'] == mower_name), None)

    def set_headlight(self, mower_name, light):
        if not self._check_access_token_and_renew():
            return False

        if ( mower_id := self._find_id_from_name(mower_name) ):
            json_payload = { 'data': {'type': 'settings', 'attributes': {'headlight': {'mode': 'ALWAYS_ON'} } } } if light else { 'data': {'type': 'settings', 'attributes': {'headlight': {'mode': 'ALWAYS_OFF'} } } } 
            self.session.headers.update( { 'Content-Type': 'application/vnd.api+json' } )
            if ( action := self._http_with_retry(POST, f'{URL_GET_MOWERS}/{mower_id}/settings', json_post_data=json_payload, mower_name=mower_name) ):
                return True
        return False

    def set_cutting_height(self, mower_name, height):
        if not self._check_access_token_and_renew():
            return False

        if ( mower_id := self._find_id_from_name(mower_name) ):
            json_payload = { 'data': {'type': 'settings', 'attributes': {'cuttingHeight': height } } }
            self.session.headers.update( { 'Content-Type': 'application/vnd.api+json' } )
            if ( action := self._http_with_retry(POST, f'{URL_GET_MOWERS}/{mower_id}/settings', json_post_data=json_payload, mower_name=mower_name) ):
                return True
        return False


    def are_all_mowers_off(self):
        return all(mower.get('state', None) == STATE_OFF for mower in self.mowers)

    def get_timestamp_last_update_mower_list(self):
        return self.timestamp_last_update_mower_list

    def is_mower_off(self, name_or_mower):
        mower = name_or_mower if isinstance(name_or_mower, dict) else self.get_mower_from_name(name_or_mower)
        return mower.get('state') == STATE_OFF if mower else None

    def are_api_limits_reached(self):
        return self.api_limit_reached

    def close(self):
        self.session.close()

    def get_http_error(self):
        return self.error

    def _get_access_token(self):
        self.session.headers.clear()
        self.session.headers.update({'Content-Type': 'application/x-www-form-urlencoded'})
        data = { 'grant_type': 'client_credentials',
                 'client_id' : self.client_id,
                 'client_secret': self.client_secret,
                 'token_endpoint': URL_TOKEN_REQUEST
               }
        self.access_token = self._http_with_retry(POST, URL_TOKEN_REQUEST, post_data=data)

        # Return True if authenticated
        if self.access_token:
            self.error = None
            self.access_token_expiration = datetime.now() + timedelta(seconds=self.access_token.get('expires_in', 0)) - timedelta(seconds=600)
            # Headers worden op de self.session (httpx.Client) beheerd, update() werkt hetzelfde
            self.session.headers.update( {
                'x-api-key': self.client_id,
                'Authorization': f"{self.access_token.get('token_type', '')} {self.access_token.get('access_token', '')}",
                'Authorization-Provider': self.access_token.get('provider', ''),
                'accept': 'application/vnd.api+json'
            } )
            log(f"New access token generated!!! Expiration: {datetime.now() + timedelta(seconds=self.access_token.get('expires_in', 0))} - Type: {self.access_token.get('token_type', '')} - Token: ...{self.access_token.get('access_token', 'N/A')[-20:]}.")
            return True
        else:
            self.error = f'Bad or unauthorized authentication request (url: {URL_TOKEN_REQUEST}).'
            return False

    def _check_access_token_and_renew(self):
        if datetime.now() > self.access_token_expiration:
            log('Create new access token!!!')
            return self._get_access_token()
        log(f"Use existing access token!!! Expiration: {datetime.now() + timedelta(seconds=self.access_token.get('expires_in', 0))} - Type: {self.access_token.get('token_type', '')} - Token: ...{self.access_token.get('access_token', 'N/A')[-20:]}.")
        return True

    def _get_mowers(self):
        if ( mowers := self._http_with_retry(GET, URL_GET_MOWERS) ):
            self.mowers = [{'id': mower.get('id'), 'name': mower.get('attributes', {}).get('system', {}).get('name')} for mower in mowers.get('data', [])]
            return True
        return False

    def _get_mower_detailed_info(self):
        status = True
        for index, mower in enumerate(self.mowers):
            mower_info = self._http_with_retry(GET, f"{URL_GET_MOWERS}/{mower.get('id')}", mower_name=self.mowers[index].get('name'))
            if mower_info and 'data' in mower_info:
                attributes = mower_info['data'].get('attributes', {})
                self.mowers[index]['battery_pct'] = attributes.get('battery', {}).get('batteryPercent')
                self.mowers[index]['activity'] = attributes.get('mower', {}).get('activity')
                self.mowers[index]['state'] = attributes.get('mower', {}).get('state')
                positions = attributes.get('positions', [])
                self.mowers[index]['location'] = positions[0] if positions else None
                self.mowers[index]['cutting_height'] = attributes.get('settings', {}).get('cuttingHeight')
                try:
                    error_code = attributes.get('mower', {}).get('errorCode')
                    self.mowers[index]['error_state'] = ErrorCodes.get(error_code) if self.mowers[index].get('state') == 'ERROR' and error_code is not None else None
                except:
                    self.mowers[index]['error_state'] = None
            else:
                status = False
                log(f"Failed to get detailed info for mower index {index}: {self.get_http_error()}")
                break
        return status

    def _send_action_to_mower(self, mower_name, action, duration=60):
        if action not in [ACTION_PARKNEXTSCHEDULE, ACTION_PARKFURTHERNOTICE, ACTION_PAUSE, ACTION_RESUMESCHEDULE, ACTION_START]:
            log(f"Unknown action requested: {action}")
            return False

        if not self._check_access_token_and_renew():
            return False

        if ( mower_id := self._find_id_from_name(mower_name) ):
            if action == ACTION_START:
                json_payload = { 'data': {'type': action, 'attributes': {'duration': duration} } }
            else:
                json_payload = { 'data': {'type': action} }
            self.session.headers.update( { 'Content-Type': 'application/vnd.api+json' } )
            if self._http_with_retry(POST, f'{URL_GET_MOWERS}/{mower_id}/actions', json_post_data=json_payload, mower_name=mower_name):
                 return True
        return False

    def _find_id_from_name(self, name):
        mower = self.get_mower_from_name(name)
        return mower.get('id') if mower else None

    def _analyze_http_error(self, response, url, mower_name=None):
        #API limits reached
        self.api_limit_reached = True if response.status_code == 429 else False

        try:
            error_info = response.json()
            if 'errors' in error_info:
                error_detail = error_info['errors'][0] if error_info['errors'] else {}
                return f"({mower_name} - {response.status_code}) {error_detail.get('title', 'Unknown Error')}: {error_detail.get('detail', 'No detail')} (url: {url})"
            elif 'message' in error_info:
                 return f"({mower_name} - {response.status_code}) {error_info.get('message', 'No message')} (url: {url})"
            else:
                return f"({mower_name} - {response.status_code}) Uncaptured error returned by Husqvarna API (url: {url})"
        except httpx.JSONDecodeError:
            return f"({mower_name} - {response.status_code}) Uncaptured error returned by Husqvarna API (url: {url}, response: {response.text}) - JSON decode error"
        except Exception as e:
             return f"({mower_name} - {response.status_code}) Error analyzing API response (url: {url}, response: {response.text}): {e}"

    def _http_with_retry(self, mode, url, json_post_data=None, post_data=None, mower_name=None):
        retry_counter = 0
        execution_status = False
        self.error = ''

        while retry_counter < 3: 
            try:
                if mode == GET:
                    r = self.session.get(url, timeout=API_TIMEOUT)
                else: # mode == POST
                    r = self.session.post(url, json=json_post_data, data=post_data, timeout=API_TIMEOUT)

                # All good (2xx status codes)
                if 200 <= r.status_code < 300:
                    self.error = None
                    self.api_limit_reached = False
                    execution_status = True
                    break

                #Authentication error received: following the exchange with the helpdesk openapi.servicedesk@husqvarnagroup.com, there
                #are regularly timeouts on the commands that translates also in an authentication error. Hence adding also retries...
                elif r.status_code == 403:
                     log(f"Retry {retry_counter} - Authentication error (403) for url {url}. Retrying...")
                     retry_counter += 1
                     if retry_counter >= 3:
                         self.error = self._analyze_http_error(r, url, mower_name)
                         break

                # Client error (4xx), not 403
                elif 400 <= r.status_code < 500:
                    if r.status_code == 429: # Specific check for API limits
                        log(f"Retry {retry_counter} - API limit reached (429) for url {url}.")
                    else:
                        log(f"Retry {retry_counter} - Client error ({r.status_code}) for url {url}. No retry.")
                    self.error = self._analyze_http_error(r, url, mower_name)
                    break

                # Server error (5xx)
                elif 500 <= r.status_code < 600:
                    log(f"Retry {retry_counter} - Server error ({r.status_code}) for url {url}. Retrying...")
                    retry_counter += 1
                    if retry_counter >= 3:
                        self.error = self._analyze_http_error(r, url, mower_name)
                        break

                # Other errors
                else:
                    log(f"Retry {retry_counter} - Unhandled HTTP status code ({r.status_code}) for url {url}. No retry.")
                    self.error = f'HTTP error ({r.status_code}) not specifically handled.'
                    break

            except (httpx.TimeoutException, httpx.ConnectError, httpx.RequestError) as e:
                self.error = f'Retry {retry_counter} - Connection error to url {url} with error "{e}".\n'
                log(self.error.strip())
                retry_counter += 1
                if retry_counter >= 3:
                    break

            if retry_counter < 3 and not execution_status:
                time.sleep(API_CALL_DELAY*(retry_counter+1))

        return r.json() if execution_status and 'r' in locals() and r is not None else None


if __name__ == "__main__":
    husq = Husqvarna('xxxxxxxxxxxx', 'yyyyyyyyyyyyyyy')
    if husq:
        if husq.get_mowers() and husq.get_mowers_info():
            print(husq.mowers)
            #print(f"Execute ParkUntilFurtherNotice: {husq.action_ParkUntilFurtherNotice(husq.mowers[0]['name'])} - {husq.get_http_error()}"
        else:
            print(f'Error getting mower information: {husq.get_http_error()}')
        while True:
            print(f'are_all_mowers_off: {husq.are_all_mowers_off()}')
            if husq.get_mowers_info(): 
                print(f'({datetime.now()}) {husq.mowers}')
                print(f"Get messages: {husq.get_mower_messages(husq.mowers[0]['name'])} - {husq.get_http_error()}")
            else:
                print(f'({datetime.now()}) Error getting mower information: {husq.get_http_error()}')
            import time
            time.sleep(30)
    else:
        print(husq.error)
