# Building from Dockerfile

    cd docker
    docker build -t elife/docker-base .

This will build the contents of the `Dockerfile` into a container called 
`elife/docker-base`

# Launching

Launching a container instance:

    docker run -t -i elife/docker-base /bin/bash
    
This will run the command `/bin/bash` within the container. The `-t -i` flags
ensure the command is run interactively and via a tty.
