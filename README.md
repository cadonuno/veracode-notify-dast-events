# veracode-notify-dast-events

This script has been developed to run daily to notify on new DAST scans.

It is built to notify on:
- Any scans scheduled to start in the next 24 hours
- Any scans that completed in the last 24 hours
- Any scans that failed in the last 24 hours

The notifications are added to a list with 3 items:
- to: owner of the DAST scan - can be used to fetch a username, or, even be an e-mail directly
- subject: a simple subject explaining what the notification is about. Can be a message title or e-mail subject
- body: the message to send, will contain a link to the scan in Veracode

Implementation of the send_notification method is required as it depends on your environment

## Don't forget to run pip install -r requirements.txt