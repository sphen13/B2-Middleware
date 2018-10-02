"""
Generate authorized backblaze B2 URLs for your munki repo
This module is using munki middleware
https://github.com/munki/munki/wiki/Middleware

Influenced heavilly by the other great middleware examples!
    - https://github.com/AaronBurchfield/CloudFront-Middleware
    - https://github.com/waderobson/gcs-auth
    ...
"""

import os
import time
import datetime
import json
import base64
import urllib2
from string import maketrans
from urlparse import urlparse
from Foundation import CFPreferencesCopyAppValue
from Foundation import CFPreferencesSetValue
from Foundation import CFPreferencesAppSynchronize
from Foundation import kCFPreferencesAnyUser
from Foundation import kCFPreferencesCurrentHost

__version__ = '1.1'

BUNDLE = 'ManagedInstalls'

def path_and_bucket(url):
    parse = urlparse(url)

    bucket = parse.path.split('/')[1]
    path = parse.path.split(bucket,1)[1]

    return bucket, path

def read_preference(key, bundle):
    """Read a preference key from a preference domain."""
    value = CFPreferencesCopyAppValue(key, bundle)
    return value

def write_preference(key, value, bundle):
    """Write a preference key from a preference domain."""
    CFPreferencesSetValue(key, value, bundle, kCFPreferencesAnyUser, kCFPreferencesCurrentHost)
    CFPreferencesAppSynchronize(bundle)
    return

def authorize_b2(account_id, application_key):
    """Authorize B2 account-level requests"""

    # build auth headers
    id_and_key = account_id + ":" + application_key
    basic_auth_string = 'Basic ' + base64.b64encode(id_and_key)
    headers = { 'Authorization': basic_auth_string }

    # submit api request to b2
    request = urllib2.Request(
        'https://api.backblazeb2.com/b2api/v1/b2_authorize_account',
        headers = headers
        )
    try:
        response = urllib2.urlopen(request)
    except urllib2.HTTPError, e:
        # we got an error - return None
        print ('B2-Middleware: HTTPError ' + str(e.code))
        return None, None, None, None

    response_data = json.loads(response.read())
    response.close()

    # return authorization info
    return response_data['authorizationToken'], response_data['apiUrl'], response_data['downloadUrl'], response_data['allowed']['bucketId']

def b2_bucketName_to_bucketId(account_id, account_token, api_url, bucket_name):
    """Return bucket_id for bucket_name"""

    # build and submit api request to b2
    request = urllib2.Request(
    	'%s/b2api/v1/b2_list_buckets' % api_url,
    	json.dumps({ 'accountId' : account_id }),
    	headers = { 'Authorization': account_token }
    	)
    response = urllib2.urlopen(request)
    response_data = json.loads(response.read())
    response.close()

    # iterate over results to get bucket_id
    for bucket in response_data["buckets"]:
        if bucket["bucketName"] == bucket_name:
            bucket_id = bucket["bucketId"]

    return bucket_id

def b2_download_authorization(account_token, api_url, valid_duration, bucket_id):
    """Return download_authorization_token"""

    # build and submit api request to b2
    request = urllib2.Request(
        '%s/b2api/v1/b2_get_download_authorization' % api_url,
        json.dumps({ 'bucketId' : bucket_id, 'fileNamePrefix' : "", 'validDurationInSeconds' : valid_duration}),
        headers = { 'Authorization': account_token }
        )
    response = urllib2.urlopen(request)
    response_data = json.loads(response.read())
    response.close()

    # return authorization info
    return response_data['authorizationToken']

def b2_url_builder(url):
    """Build our b2 url"""

    # read in our preference keys
    account_id = read_preference('B2AccountID', BUNDLE)
    application_key = read_preference('B2ApplicationKey', BUNDLE)
    valid_duration = read_preference('B2ValidDuration', BUNDLE) or 1800
    valid_duration = int(valid_duration)
    expiration_date = read_preference('B2ExpirationDate', BUNDLE) or datetime.datetime.now()
    download_url = read_preference('B2DownloadURL', BUNDLE)
    download_authorization_token = read_preference('B2DownloadAuthorizationToken', BUNDLE)

    # parse url for b2 file path and bucket name
    bucket_name, path = path_and_bucket(url)

    b2_url = ""
    HEADERS = {}

    # test if our prefs are set
    if account_id and application_key:
        if not (expiration_date > datetime.datetime.now() and download_authorization_token):
            # need to get updated auth token

            # set new expiration date
            expiration_date = datetime.datetime.now() + datetime.timedelta(seconds=valid_duration)

            # get b2 account authorization
            account_token, api_url, download_url, bucket_id = authorize_b2(account_id, application_key)
            if (account_token == None):
                # stop trying to build a url - we dont have authorization
                print "B2-Middleware: Not Authorized."
                return url, None

            if not (bucket_id):
                # we are not restricted to a single bucket, lets get the id we want
                bucket_id = b2_bucketName_to_bucketId(account_id, account_token, api_url, bucket_name)

            # get download authorization token
            download_authorization_token = b2_download_authorization(account_token, api_url, valid_duration, bucket_id)

            if download_authorization_token:
                # We just updated tokens - lets update our prefs
                write_preference("B2ExpirationDate", expiration_date, BUNDLE)
                write_preference("B2DownloadURL", download_url, BUNDLE)
                write_preference("B2DownloadAuthorizationToken", download_authorization_token, BUNDLE)

        if download_authorization_token:
            # We have a valid download_authorization_token at this point, lets continue processing URL.

            b2_url = download_url + "/file/" + bucket_name + path
            HEADERS = { 'Authorization': download_authorization_token }
        else:
            print ("B2-Middleware: API Error")
    else:
        print ("B2-Middleware: No account_id or application_key provided.")

    return b2_url, HEADERS

def process_request_options(options):
    """Return an authorized URL for b2."""

    if '://b2/' in options['url']:
        options['url'], HEADERS = b2_url_builder(options['url'])
        if HEADERS:
            options['additional_headers'].update(HEADERS)

    return options
