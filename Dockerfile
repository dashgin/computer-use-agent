FROM docker.io/ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV DEBIAN_PRIORITY=high

RUN apt-get update && \
    apt-get -y upgrade && \
    apt-get -y install \
    # UI Requirements
    xvfb \
    xterm \
    xdotool \
    scrot \
    imagemagick \
    sudo \
    mutter \
    x11vnc \
    # Python/pyenv reqs
    build-essential \
    libssl-dev  \
    zlib1g-dev \
    libbz2-dev \
    libreadline-dev \
    curl \
    git \
    libncursesw5-dev \
    xz-utils \
    tk-dev \
    libxml2-dev \
    libxmlsec1-dev \
    libffi-dev \
    liblzma-dev \
    # Network tools
    net-tools \
    netcat \
    # Additional deps for FastAPI backend
    # PPA req
    software-properties-common && \
    # Userland apps
    sudo add-apt-repository ppa:mozillateam/ppa && \
    sudo apt-get install -y --no-install-recommends \
    libreoffice \
    firefox-esr \
    x11-apps \
    xpdf \
    gedit \
    xpaint \
    tint2 \
    galculator \
    pcmanfm \
    unzip && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install noVNC
RUN git clone --branch v1.5.0 https://github.com/novnc/noVNC.git /opt/noVNC && \
    git clone --branch v0.12.0 https://github.com/novnc/websockify /opt/noVNC/utils/websockify && \
    ln -s /opt/noVNC/vnc.html /opt/noVNC/index.html

# setup user
ENV USERNAME=computeruse
ENV HOME=/home/$USERNAME
RUN useradd -m -s /bin/bash -d $HOME $USERNAME
RUN echo "${USERNAME} ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers
USER computeruse
WORKDIR $HOME

# setup python
RUN git clone https://github.com/pyenv/pyenv.git ~/.pyenv && \
    cd ~/.pyenv && src/configure && make -C src && cd .. && \
    echo 'export PYENV_ROOT="$HOME/.pyenv"' >> ~/.bashrc && \
    echo 'command -v pyenv >/dev/null || export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.bashrc && \
    echo 'eval "$(pyenv init -)"' >> ~/.bashrc
ENV PYENV_ROOT="$HOME/.pyenv"
ENV PATH="$PYENV_ROOT/bin:$PATH"
ENV PYENV_VERSION_MAJOR=3
ENV PYENV_VERSION_MINOR=11
ENV PYENV_VERSION_PATCH=6
ENV PYENV_VERSION=$PYENV_VERSION_MAJOR.$PYENV_VERSION_MINOR.$PYENV_VERSION_PATCH
RUN eval "$(pyenv init -)" && \
    pyenv install $PYENV_VERSION && \
    pyenv global $PYENV_VERSION && \
    pyenv rehash

ENV PATH="$HOME/.pyenv/shims:$HOME/.pyenv/bin:$PATH"

RUN python -m pip install --upgrade pip==23.1.2 setuptools==58.0.4 wheel==0.40.0 && \
    python -m pip config set global.disable-pip-version-check true

# Install computer use demo requirements
COPY --chown=$USERNAME:$USERNAME computer_use_demo/requirements.txt $HOME/computer_use_demo/requirements.txt
RUN python -m pip install -r $HOME/computer_use_demo/requirements.txt

# Install FastAPI backend requirements
COPY --chown=$USERNAME:$USERNAME requirements-backend.txt $HOME/requirements-backend.txt
RUN pip install -r $HOME/requirements-backend.txt

# setup desktop env & original demo app
COPY --chown=$USERNAME:$USERNAME image/ $HOME
COPY --chown=$USERNAME:$USERNAME computer_use_demo/ $HOME/computer_use_demo/

# Copy FastAPI backend application
COPY --chown=$USERNAME:$USERNAME app/ $HOME/app/
COPY --chown=$USERNAME:$USERNAME alembic/ $HOME/alembic/
COPY --chown=$USERNAME:$USERNAME alembic.ini $HOME/
COPY --chown=$USERNAME:$USERNAME pyproject.toml $HOME/

# Create directories for data persistence
RUN mkdir -p $HOME/data $HOME/logs

ARG DISPLAY_NUM=1
ARG HEIGHT=768
ARG WIDTH=1024
ENV DISPLAY_NUM=$DISPLAY_NUM
ENV HEIGHT=$HEIGHT
ENV WIDTH=$WIDTH

# Environment variables for FastAPI
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV DATABASE_URL="postgresql+asyncpg://postgres:comp_use_password@postgres:5432/postgres"
ENV FASTAPI_ENV=production

# Health check for the combined service
HEALTHCHECK --interval=30s --timeout=30s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose ports
EXPOSE 8000 5900 6080
ENTRYPOINT [ "./entrypoint.sh" ]
