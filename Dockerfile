from ubuntu:20.04

WORKDIR /builder
RUN apt update && DEBIAN_FRONTEND=noninteractive apt install -y tzdata build-essential software-properties-common git python virtualenv vagrant awscli
RUN wget https://releases.hashicorp.com/terraform/0.11.15/terraform_0.11.15_linux_amd64.zip -O ./terraform.zip && unzip ./terraform.zip -d /bin && rm ./terraform.zip
RUN wget https://releases.hashicorp.com/vault/0.11.6/vault_0.11.6_linux_amd64.zip -O vault.zip && unzip ./vault.zip -d /bin && rm ./vault.zip
RUN echo 'eval $(ssh-agent); ssh-add;' >> ~/.bashrc

SHELL ["/bin/bash", "-c"]