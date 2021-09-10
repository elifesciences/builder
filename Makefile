CUSTOM_SSH_KEY ?= ~/.ssh/elife.id_rsa

start:
	@docker run --rm -it -v /etc/timezone:/etc/timezone:ro -v /etc/localtime:/etc/localtime:ro -v ${CURDIR}:/builder:rw -v ${HOME}/.ssh/elife.id_rsa:/root/.ssh/id_rsa:ro -v ${HOME}/.ssh/elife.id_rsa.pub:/root/.ssh/id_rsa.pub:ro -v ${HOME}/.aws:/root/.aws:ro -v ${HOME}/.vault-token:/root/.vault-token:ro builder:test /bin/bash
