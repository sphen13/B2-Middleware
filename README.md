### What is B2 Middleware?
B2 Middleware enables managed clients to securely access a [munki][0] repo from Backblaze's [B2][1] Cloud Storage. B2 offers aggressive pricing for both storage and access.

B2 Middleware uses a private Application Key to create and requests for private B2 resources. Each request includes an expiration date after which the request is no longer valid.

#### Requirements
* [Backblaze B2][1] private bucket with your munki repo inside.
* B2 [Account ID and Application Key][2].

#### Configure a managed client to access the CloudFront munki repo.
1. Install ```middleware_b2.py``` to ```/usr/local/munki/```.
2. Set the munki preference ```SoftwareRepoURL``` to the following format:

    ```
    https://b2/BUCKET_NAME/PATH
    ```
    This middleware looks specifically for a URL starting with https://b2 to be triggered.  The first folder will be your bucket name.  If you have your munki repo within a subfolder on this bucket please also provide that as well.  The additional path is not needed if your repo is based at the root of your bucket.
3. Set B2 Middleware preferences for your Account ID, Application Key, and the resource expiration timeout in seconds. If unset expiration will default to 30 minutes.

    ```
    sudo defaults write com.github.sphen13.b2 account_id -string "B2_ACCOUNT_ID"
    sudo defaults write com.github.sphen13.b2 application_key -string "B2_APPLICATION_KEY"
    sudo defaults write com.github.sphen13.b2 valid_duration -int 3600

    ```
4. Run munki and verify that B2 requests are being made.

    ```
    sudo managedsoftwareupdate --checkonly -vvv
    ```


#### Build a luggage package to install B2 Middleware
The included [luggage][3] makefile can be used to create an installer package for B2 Middleware.

2. Replace the `account_id` and `application_key` on line 4+5 of the **postinstall** script with the appropriate values from Backblaze B2.
3. ```make pkg``` and install.
4. Set your ```SoftwareRepoURL``` to https://b2/BUCKET_NAME/PATH as stated in step 2 above.

[0]: https://github.com/munki/munki
[1]: https://www.backblaze.com/b2/cloud-storage.html
[2]: https://help.backblaze.com/hc/en-us/articles/224991568-Where-can-I-find-my-Account-ID-and-Application-Key-
[3]:https://github.com/unixorn/luggage
