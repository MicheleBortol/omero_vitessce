# This container uses the tag for the latest web release of OMERO 5
# To upgrade to the next major release, increment the major version number

FROM "openmicroscopy/omero-server:5"

USER root

# For NGFF
RUN yum install blosc-devel -y

# Add omero.openlink script
COPY  --chown=omero-server:omero-server Create_OpenLink.py  /opt/omero/server/OMERO.server/lib/scripts/omero/Create_Openlink.py


USER omero-server

