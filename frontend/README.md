
# Fire Department Visualization Tool

This is a code bundle for Fire Department Visualization Tool. The original project is available at https://www.figma.com/design/zruflYr4n3tQyJO2bcrxnk/Fire-Department-Visualization-Tool.

## Running the code

Run `npm i` to install the dependencies.

Run `npm run dev` to start the development server.
npm install leaflet

## Running everything on RHEL8 (Government Server)
This assumes you have cloned both fire_demo3 and fire_demo3_api

1. Login to `hobvmisap57`
3. Installing Node and NPM (to follow, this will make things easier but not sure if RHEL8 has it)
    ```bash
    sudo dnf module enable nodejs:16
    sudo dnf install nodejs

    # Run these commands
    npm config set prefix ~/.npm
    export PATH=$PATH:~/.npm/bin

    # Running the instance
    cd /path/to/fire_demo3

    # to run normally
    npm install
    npm install leaflet
    npm run dev

    # to use pm2
    sudo npm install pm2 -g
    pm2 start npm --name "fire-front-end" -- run dev
    pm2 startup
    # follow instructions
    pm2 save

    # [PM2] Remove init script via:
    # pm2 unstartup systemd

    ```
2. Check if front end is running: https://hobvmisap57
3. Check nginx (if installed)
    ```bash
    sudo systemctl status nginx
    # if not existing, install
    sudo yum install nginx
    # To try and lock nginx package down
    sudo yum install yum-plugin-versionlock
    sudo yum versionlock add nginx
    sudo dnf versionlock list # verify
    # enable
    sudo systemctl enable nginx
    ```
4. Check nginx.conf/dashapp.conf (TODO: Make Nginx a daemon service)
    ```bash
    sudo vim /etc/nginx/conf.d/dash_app.conf
    # Check if pointing to correct port (from step 1)
    location / {
          proxy_pass http://[::1]:3001;
          proxy_http_version 1.1;
          proxy_set_header Upgrade $http_upgrade;
          proxy_set_header Connection "upgrade";
          proxy_set_header Host $host;
    }
    location /endpoint/ {
          #Fix this config
          proxy_pass ... 9999 
    }
    
    # Restart Nginx
    sudo nginx -t && sudo systemctl restart nginx
    ```
5. Go to jump server (should show the frontend)
	https://hobvmisap57/
6. Activate the backend
    ```bash
	  cd /home/vdr-jptalusan/fire_demo3_api
	  tmux new -s backend
	  uv run uvicorn src.app:app --reload --log-level debug --host 0.0.0.0 --port 9999
    ```
    To convert it into a daemon service
    
    ```bash
    which uv
    # Take note of this path
    # ~/.local/bin/uv

    # create service file
    sudo vim /etc/systemd/system/fire-backend-app.service

    # Add the following
    [Unit]
    Description=Fire Backend App
    After=network.target

    [Service]
    User=vdr-jptalusan
    WorkingDirectory=/home/vdr-jptalusan/fire_demo3_api
    # Do not use relative paths here
    ExecStart=/home/vdr-jptalusan/.local/bin/uv run uvicorn src.app:app --reload --log-level debug --host 0.0.0.0 --port 9999
    Restart=always

    [Install]
    WantedBy=multi-user.target
    ```
    Start the service
    ```bash
    sudo systemctl daemon-reload
    sudo systemctl enable fire-backend-app.service
    sudo systemctl start fire-backend-app.service
    ```

7. Go to jump server and select `11/12/2023 to 11/13/2023` incident range, get incident
    - it should show the incidents on the map
8. Double check that docker is still installed and up and running.
    - Docker somehow is able to avoid the issues of nginx and other services.
    - it always restarts properly.