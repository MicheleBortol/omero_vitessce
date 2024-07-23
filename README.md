# OUTDATED!!!!!!!!!!!!!!!!!!!!!!!!!!
**Please switch to:** https://github.com/MicheleBortol/omero-vitessce


















# Prototype for using vitessce with OMERO

## Installation
### Requirements
- [Docker](https://docs.docker.com/).
- [Nginx](https://docs.nginx.com/nginx/admin-guide/installing-nginx/installing-nginx-open-source/). I used nginx, but any webserver would work.
- Clone this repository:
  ```
  https://github.com/MicheleBortol/omero_vitessce.git
  ```
  
### Configuration
#### Docker compose
Change the `docker-compose.yml` file in `./omero-docker/docker-compose.yml`.

The following place holders need to be replaced:
- `OMERO_WEB_PORT`
- `VITESSCE_PORT`
  
The following values can be updated:
- Username and password for the database and password for the `root` user for OMERO
- Paths for the volumes
  
#### OMERO.openlink
Config changes need to be made in the following files:
- `Create_OpenLink.py` at `./omero-docker/omero_server_docker/Create_OpenLink.py`:
  This script has been modified to work with docker volumes.
  + NEW_PATH_PREFIX = "PATH_TO_THE_VOLUME_WITH_THE_OMERO_DATA_DIRECTORY"
  
- `web_config.omero` `./omero-docker/omero_web_docker/web_config.omero`
  + `ADDRESS`: replace with the address of your website.
    
#### nginx
The configuration file needs to be updated with values for the following placeholders:
- `OMERO_OPENLINK_VOLUME_PATH`
- `OMERO_WEB_PORT`
- `VITESSCE_PORT`

## Starting & Stopping
- **Starting**
  ```
  docker-compose up -d
  ``` 
- **Stopping**
  ```
  docker-compose down
  ``` 

## Usage

### 1.) OMERO and OMERO.openlink
1) Upload all the images in OMERO and all other necessary data (e.g. cv tables) as attachments.
Having everything in the same Project/Dataset makes things easier, but it is not necessary.

2) Generate an Openlink area with the `Create OpenLink.py` script from OMERO.web. It is easier to do it once at the Project or Dataset level
   to include all the images and data to be viewed. It is important to select the add attachements checkbox.

### 2.) Vitessce
1) Upload to OMERO a config.json file for the viewer. See docs and examples at:
- http://vitessce.io/docs/
- http://vitessce.io/examples/
In the config file use the openlink urls to point at the data.

2) Recreate the openlink area so the config file is added to it. The add attachements checkbox must be selected.
   In alternative a new openlink area can also be used.

### 3.) Viewing
Clink on the link:
```
https://ADDRESS/webapp/?config=https://ADDRESSS/openlink/OPENLINK_ADDRESS/config.json
```

### Test data
TO BE ADDED
