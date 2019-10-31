include /usr/local/share/luggage/luggage.make
TITLE=B2Middleware
REVERSE_DOMAIN=com.github.sphen13.b2middleware
PACKAGE_VERSION=1.3
PAYLOAD=pack-middleware\
	      pack-script-postinstall

pack-middleware:
		@sudo mkdir -p ${WORK_D}/usr/local/munki
		@sudo ${CP} ./middleware_b2_s3.py ${WORK_D}/usr/local/munki
		@sudo ${CP} ./godaddy-root.pem ${WORK_D}/usr/local/munki
		@sudo chown root:wheel ${WORK_D}/usr/local/munki/middleware_b2_s3.py
		@sudo chmod 600 ${WORK_D}/usr/local/munki/middleware_b2_s3.py
		@sudo chown root:wheel ${WORK_D}/usr/local/munki/godaddy-root.pem
		@sudo chmod 600 ${WORK_D}/usr/local/munki/godaddy-root.pem
