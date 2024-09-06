#!/usr/bin/env bash

export ENCRYPTION_KEY=$(cat ~/.ssh/Fkey)

# https://stackoverflow.com/questions/4774054/reliable-way-for-a-bash-script-to-get-the-full-path-to-itself
SCRIPTPATH="$( cd -- "$(dirname "$0")" >/dev/null 2>&1 ; pwd -P )"

cd $SCRIPTPATH

source ./env/bin/activate
python3 -m mergecal.standalone.generate

echo "Done"
