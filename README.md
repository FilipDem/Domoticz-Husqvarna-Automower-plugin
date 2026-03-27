# Donation
It took me quite some effort to get the plugin available, including with the Husqvarna helpdesk because of some bugs in the management of the API calls.
Small contributions are thus very welcome...

## Use your Mobile Banking App and scan the QR Code
The QR codes comply the EPC069-12 European Standard for SEPA Credit Transfers ([SCT](https://www.europeanpaymentscouncil.eu/sites/default/files/KB/files/EPC069-12%20v2.1%20Quick%20Response%20Code%20-%20Guidelines%20to%20Enable%20the%20Data%20Capture%20for%20the%20Initiation%20of%20a%20SCT.pdf)). The amount of the donation can possibly be modified in your Mobile Banking App.
| 5 EUR      | 10 EUR      |
|------------|-------------|
| <img src="https://user-images.githubusercontent.com/16196363/110995648-000cff80-837b-11eb-83a7-7a8c0e0f6996.png" width="80" height="80"> | <img src="https://user-images.githubusercontent.com/16196363/110995669-08fdd100-837b-11eb-98f9-aa32446b5b28.png" width="80" height="80"> |

## Use PayPal
[![](https://www.paypalobjects.com/en_US/BE/i/btn/btn_donateCC_LG.gif)](https://www.paypal.com/cgi-bin/webscr?cmd=_s-xclick&hosted_button_id=AT4L7ST55JR4A) 

# Domoticz-Husqvarna-Automower-plugin
Domoticz plugin for Husqvarna automowers.

The plugin allows you to monotor the status of your automower, including the battery status. It offers the possibility to trigger different actions like start mowing, pausing and parking.

I personally de-activated the scheduling system of the automower itself and the timers are completely managed by Domoticz.

# Husqvarna API
This Husqvarna plugin makes use of the offical Husqvarna API. Consult [Husqvarna API](https://developer.husqvarnagroup.cloud/docs/get-started) for more information.

## Create an Husqvarna account
Please follow the instructions on [Signup](https://developer.husqvarnagroup.cloud/docs/get-started#1sign-up-and-create-account).

## Create the Domoticz application
Please follow the instructions on [Create Application](https://developer.husqvarnagroup.cloud/docs/get-started#2create-application) and use the following data:
* Application name: MyDomoticz
* Description: Husqvarna Application for Domoticz
* Redirect URL: http://localhost:8080

Connect then the Authentication API and Husqvarna Automower API by by using the button CONNECT NEW API.

On the developer site, you will find now a client_id (or application_id) and a client_secret (or an application_secret). Enter both in the settings of the Domoticz plugin hardware settings...

## Restrictions
* When activating an action in Domoticz (eg start mowing), the action is not always executed immediately and it can take some seconds. This delay is mainly caused by the communication between the Husqvarna Cloud and the automower. Sometimes actions are scheduled in Husqvarna Cloud.
* There is a restriction on the number of API calls by Husqvarna:
  * the quota is 21000 requests per week and appKey in total. That is 2 requests per minute for a week
  * the rate limit is 120 requests per minute and appKey
In theory we could now have a polling interval of every minute (which seems a bit overkill). Keep in mind that it is a change in policy as previously it was maximal 10000 calls per month. The plugin implemented a "light" mechanism to slow down the polling in the following cases. The waitng interval for these cases can be adapted in the Husqvarna.json file.
  * all mowers are OFF
  * Husqvarna Cloud connection errors
  * Husqvarna returns that quota limit is achieved.

## Updating
When updating to the plugin supporting the Extended Plugin Framework, new devices are created. To keep the history, use the "replace" function from the GUI. Then all the history will be kept and all the references to the devices in scripts, groups, ... are also kept.

## Automation ideas
* You can link possible weather sensors with the Husqvarna mower. Eg. if it is start raining, the Husqvarna mower can be stopped mowing and return return to its charging station.
* The device 'State' can be used to check if there has been an error occured; in case of error a notification could be sent.

Success!

**Don't forget a small gift by using the donation button...**

