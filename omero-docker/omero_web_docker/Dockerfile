# This container uses the tag for the latest web release of OMERO 5
# To upgrade to the next major release, increment the major version number

FROM "openmicroscopy/omero-web-standalone:latest"

USER root

# Install OMERO.openlink: https://github.com/sukunis/OMERO.openlink.git
# Using a fork that supports the latest OMERO.web
RUN cd /opt && \
	yum install unzip -y && \
	curl https://codeload.github.com/MicheleBortol/OMERO.openlink/zip/refs/heads/update-urls --output OMERO.openlink-update-urls.zip && \
	unzip OMERO.openlink-update-urls.zip && \
	rm OMERO.openlink-update-urls.zip && \
	cd /opt/OMERO.openlink-update-urls/omero-openlink && \
	source /opt/omero/web/venv3/bin/activate && \
	pip3 install -e . && \
	cd && \
	deactivate

RUN mkdir /openlink && chown omero-web:omero-web /openlink
VOLUME /openlink

# Overwrite the default config file with one that enables the plugins
COPY --chown=omero-web:omero-web web_config.omero /opt/omero/web/config/50-omero-web-app-config.omero


USER omero-web

