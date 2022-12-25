"""
Python module to get information from Husqvarna Mower.

Based on the Husqvarna official API.
https://developer.husqvarnagroup.cloud/applications

"""

import requests
import time
from datetime import datetime, timedelta
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

URL_TOKEN_REQUEST = 'https://api.authentication.husqvarnagroup.dev/v1/oauth2/token'
URL_BASE_API = 'https://api.amc.husqvarna.dev/v1/'
URL_GET_MOWERS = '{}{}'.format(URL_BASE_API, 'mowers')
API_CALL_DELAY = 2

ACTION_PARKNEXTSCHEDULE = 'ParkUntilNextSchedule'
ACTION_PARKFURTHERNOTICE = 'ParkUntilFurtherNotice'
ACTION_PAUSE = 'Pause'
ACTION_RESUMESCHEDULE = 'ResumeSchedule'
ACTION_START = 'Start'

STATE_OFF = 'OFF'

POST = 0
GET = 1

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

class Husqvarna():

    def __init__(self, client_id, client_secret):
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = None
        self.access_token_expiration = None
        self.timestamp_last_update_mower_list = None
        self.s = requests.Session()
        self.s.verify = False
        self.error = None
        self.api_limit_reached = False
        self._get_access_token()
                
    def get_mowers(self):
        if self._check_access_token_and_renew():
            status = self._get_mowers()
            if status:
                self.timestamp_last_update_mower_list = datetime.now()
            return status
        return False

    def get_mowers_info(self):
        if self._check_access_token_and_renew():
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

    def are_all_mowers_off(self):
        status = True
        for mower in self.mowers:
            if 'state' in mower and mower['state'] != STATE_OFF:
                status = False
                break
        return status

    def get_timestamp_last_update_mower_list(self):
        return self.timestamp_last_update_mower_list
        
    def is_mower_off(self, name):
        for mower in self.mowers:
            if name == mower['name']:
                return mower['state'] == STATE_OFF
        return None
        
    def are_api_limits_reached(self):
        return self.api_limit_reached    
        
    def close(self):
        self.s.close()

    def get_http_error(self):
        return self.error

    def _get_access_token(self):
        self.s.headers.clear()
        data = { 'grant_type': 'client_credentials',
                 'client_id' : self.client_id,
                 'client_secret': self.client_secret,
                 'token_endpoint': URL_TOKEN_REQUEST
               }
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        time.sleep(API_CALL_DELAY) #Avoid doing more than 1 call per second
        r = self.s.post(URL_TOKEN_REQUEST, data=data, headers=headers, verify=False)

        # Return if authenticated
        status = False
        if r.status_code in [200, 201]:
            self.error = None
            self.access_token = r.json()
            self.access_token_expiration = datetime.now() + timedelta(seconds=self.access_token['expires_in']) - timedelta(seconds=600)
            self.s.headers.update( {
                'x-api-key': self.client_id,
                'Authorization': '{} {}'.format(self.access_token['token_type'], self.access_token['access_token']),
                'Authorization-Provider': self.access_token['provider'],
                'accept': 'application/vnd.api+json'
            } )
            status = True
        elif r.status_code >= 400:
            self.error = '(Http error: {}) Bad or unauthorized authentication request (url: {}).'.format(r.status_code, URL_TOKEN_REQUEST)

        return status

    def _check_access_token_and_renew(self):
        if not self.access_token_expiration or datetime.now() > self.access_token_expiration:
            return self._get_access_token()
        return True

    def _get_mowers(self):
    
        self.mowers = []
        mowers = self._http_get_with_retry(GET, URL_GET_MOWERS)
        if mowers:
            for mower in mowers['data']:
                self.mowers.append({'id': mower['id'], 'name': mower['attributes']['system']['name']})
            return True
        return False

    def _get_mower_detailed_info(self):
        status = True
        for index, mower in enumerate(self.mowers):
            mower_info = self._http_get_with_retry(GET, '{}/{}'.format(URL_GET_MOWERS, mower['id']), mower_name=self.mowers[index]['name'])
            if mower_info:
                self.mowers[index]['battery_pct'] = mower_info['data']['attributes']['battery']['batteryPercent']
                self.mowers[index]['activity'] = mower_info['data']['attributes']['mower']['activity']
                self.mowers[index]['state'] = mower_info['data']['attributes']['mower']['state']
                self.mowers[index]['error_state'] = ErrorCodes[mower_info['data']['attributes']['mower']['errorCode']] if 'ERROR' in self.mowers[index]['state'] else None
            else:
                status = False
                break
        return status
            
    def _send_action_to_mower(self, mower_name, action, duration=60):
        if action not in [ACTION_PARKNEXTSCHEDULE, ACTION_PARKFURTHERNOTICE, ACTION_PAUSE, ACTION_RESUMESCHEDULE, ACTION_START]:
            return False

        if not self._check_access_token_and_renew():
            return False

        mower_id = self._find_id_from_name(mower_name)
        if mower_id:
            if action == ACTION_START:
                json = { 'data': {'type': action, 'attributes': {'duration': duration} } } 
            else:
                json = { 'data': {'type': action} } 
            self.s.headers.update( { 'Content-Type': 'application/vnd.api+json' } )
            action = self._http_get_with_retry(POST, '{}/{}/actions'.format(URL_GET_MOWERS, mower_id), json, mower_name=mower_name)
            if action:
                return True
        return False

    def _find_id_from_name(self, name):
        for mower in self.mowers:
            if name == mower['name']:
                return mower['id']
        return None

    def _http_get_with_retry(self, mode, url, json_post_data=None, mower_name=None):
        def _analyze_http_error(message, url, mower_name=None):
    
            #API limits reached
            self.api_limit_reached = True if message.status_code == 429 else False
        
            error_info = message.json()
            if 'errors' in error_info:
                return '({} - {}) {}: {} (url: {})'.format(mower_name, message.status_code, error_info['errors'][0]['title'], error_info['errors'][0]['detail'], url)
            elif 'message' in error_info:
                return '({} - {}) {} (url: {})'.format(mower_name, message.status_code, error_info['message'], url)
            else:
                return '({} - {}) Uncaptured error returned by Husqvarna API (url: {})'.format(mower_name, message.status_code, url)
    

        retry_counter = 0
        execution_status = False
        while True:
            time.sleep(API_CALL_DELAY) #Avoid doing more than 1 call per second
            try:
                if mode == GET:
                    r = self.s.get(url)
                else:
                    r = self.s.post(url, json=json_post_data)
            except (requests.ConnectTimeout, requests.ReadTimeout, requests.Timeout, requests.ConnectionError):
                retry_counter += 1
                if retry_counter >= 3:
                    self.error = 'Connection error to url {}.'.format(url)
                break

            #All good
            if r.status_code in [200, 202]:
                self.error = None
                self.api_limit_reached = False
                execution_status = True
                break

            #Error received
            elif r.status_code >= 400 and r.status_code < 500:
                self.error = _analyze_http_error(r, url, mower_name)
                break

            #Internal server error
            elif r.status_code >= 500:
                retry_counter += 1
                if retry_counter >= 3:
                    self.error = _analyze_http_error(r, url, mower_name)
                    break
                    
            #Other errors
            else:
                self.error = 'HTTP error ({}) not specifically handled.'.format(r.status_code)
                break

        return r.json() if execution_status else None
                
if __name__ == "__main__":

    husq = Husqvarna('xxx', 'xxx')
    if husq:
        if husq.get_mowers() and husq.get_mowers_info():
            print(husq.mowers)
            print('Execute ParkUntilFurtherNotice: {} - {}'.format(husq.action_ParkUntilFurtherNotice(husq.mowers[0]['name']), husq.get_http_error()))
        else:
            print('Error getting mower information: {}'.format(husq.get_http_error()))
        while True:
            print('are_all_mowers_off: {}'.format(husq.are_all_mowers_off()))
            if husq.get_mowers_info():
                print('({}) {}'.format(datetime.now(), husq.mowers))
            else:
                print('({}) Error getting mower information: {}'.format(datetime.now(), husq.get_http_error()))
            import time
            time.sleep(30)

