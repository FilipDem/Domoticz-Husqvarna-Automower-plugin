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
* There is a restriction on the number of API calls by Husqvarna (max. 1 call per second or 10000 calls per month). This means that we can update the status at a maximal speed of once per 4.5 minutes. Take this into account when defining the update status interval in the Domoticz plugin hardware settings. The plugin implemented a "light" mechanism to avoid problem by changing automatically the update interval:
  * to one hour when the limit of 10000 calls/month is achieved
  * to one hour when the automower is off (eg during winter)
  * to three hours during night (between 10pm and 5am)
  
Success!

**Don't forget a small gift by using the donation button...**

