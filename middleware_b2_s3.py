"""
Generate authorized backblaze B2 URLs for your munki repo
This module is using munki middleware
https://github.com/munki/munki/wiki/Middleware

I have bundled in s3 handling as well so this can be dual purpose
Credit to: https://github.com/munki/munki/wiki/Middleware

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
import hashlib
import hmac
from string import maketrans
from urlparse import urlparse
from Foundation import CFPreferencesCopyAppValue
from Foundation import CFPreferencesSetValue
from Foundation import CFPreferencesAppSynchronize
from Foundation import kCFPreferencesAnyUser
from Foundation import kCFPreferencesCurrentHost

__version__ = '1.2b'

BUNDLE = 'ManagedInstalls'
METHOD = 'GET'
SERVICE = 's3'


"""
S3
"""

def pref(pref_name):
    """Return a preference. See munkicommon.py for details
    """
    pref_value = CFPreferencesCopyAppValue(pref_name, BUNDLE)
    return pref_value


ACCESS_KEY = pref('AccessKey')
SECRET_KEY = pref('SecretKey')
REGION = pref('Region')
S3_ENDPOINT = pref('S3Endpoint') or 's3.amazonaws.com'


def sign(key, msg):
    return hmac.new(key, msg.encode('utf-8'), hashlib.sha256).digest()


def get_signature_key(key, datestamp, region, service):
    kdate = sign(('AWS4' + key).encode('utf-8'), datestamp)
    kregion = sign(kdate, region)
    kservice = sign(kregion, service)
    ksigning = sign(kservice, 'aws4_request')
    return ksigning


def uri_from_url(url):
    parse = urlparse(url)
    return parse.path


def host_from_url(url):
    parse = urlparse(url)
    return parse.hostname


def s3_auth_headers(url):
    """
    Returns a dict that contains all the required header information.
    Each header is unique to the url requested.
    """
    # Create a date for headers and the credential string
    time_now = datetime.datetime.utcnow()
    amzdate = time_now.strftime('%Y%m%dT%H%M%SZ')
    datestamp = time_now.strftime('%Y%m%d') # Date w/o time, used in credential scope
    uri = uri_from_url(url)
    host = host_from_url(url)
    canonical_uri = uri
    canonical_querystring = ''
    canonical_headers = 'host:{}\nx-amz-date:{}\n'.format(host, amzdate)
    signed_headers = 'host;x-amz-date'
    payload_hash = hashlib.sha256('').hexdigest()
    canonical_request = '{}\n{}\n{}\n{}\n{}\n{}'.format(METHOD,
                                                        canonical_uri,
                                                        canonical_querystring,
                                                        canonical_headers,
                                                        signed_headers,
                                                        payload_hash)

    algorithm = 'AWS4-HMAC-SHA256'
    credential_scope = '{}/{}/{}/aws4_request'.format(datestamp, REGION, SERVICE)
    hashed_request = hashlib.sha256(canonical_request).hexdigest()
    string_to_sign = '{}\n{}\n{}\n{}'.format(algorithm,
                                             amzdate,
                                             credential_scope,
                                             hashed_request)


    signing_key = get_signature_key(SECRET_KEY, datestamp, REGION, SERVICE)
    signature = hmac.new(signing_key, (string_to_sign).encode('utf-8'), hashlib.sha256).hexdigest()

    authorization_header = ("{} Credential={}/{},"
                            " SignedHeaders={}, Signature={}").format(algorithm,
                                                                      ACCESS_KEY,
                                                                      credential_scope,
                                                                      signed_headers,
                                                                      signature)

    headers = {'x-amz-date': amzdate,
               'x-amz-content-sha256': payload_hash,
               'Authorization': authorization_header}
    return headers


"""
B2
"""

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
    except urllib2.URLError, e:
        # we got an error - return None
        print ('B2-Middleware: URLError ' + str(e))
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
    """Return an authorized URL"""

    """Process B2"""
    if '://b2/' in options['url']:
        options['url'], HEADERS = b2_url_builder(options['url'])
        if HEADERS:
            options['additional_headers'].update(HEADERS)
    """Process S3"""
    if S3_ENDPOINT in options['url']:
        headers = s3_auth_headers(options['url'])
        options['additional_headers'].update(headers)

    return options
