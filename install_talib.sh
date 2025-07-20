#!/usr/bin/env bash
# exit on error
set +e
# sanity checks
[[ $(id -u) == 0 ]] && { echo DO NOT RUN AS ROOT I WILL PROMPT WITH SUDO WHEN NECESSARY. ; exit 1;  }
env|grep -q VIRTUAL_ENV || { echo 'Run this in a virtualenv.'; exit 1;  }
# install talib
wget https://github.com/ta-lib/ta-lib/releases/download/v0.6.4/ta-lib-0.6.4-src.tar.gz
# check hash
sha256sum  ta-lib-0.6.4-src.tar.gz|grep -q aa04066d17d69c73b1baaef0883414d3d56ab3775872d82916d1cdb376a3ae86 && echo OK || { echo "BAD SUM!"; exit 1 ; }
tar -xzf ta-lib-0.6.4-src.tar.gz
cd 'ta-lib-0.6.4' || { echo 'huh?' ; exit 1 ; }
# perform install

sudo apt-get -y -qq install python3-dev
./configure 
make
make install
# install the python wrapper
python -m pip install TA-Lib
