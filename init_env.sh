#!/bin/bash

(return 0 2>/dev/null)
if [ $? -eq 1 ]; then
    echo "Error: Script must be sourced."
    exit
fi

function activate_env {
    source $1/bin/activate 2>/dev/null
    if [ ! $? -eq 0 ]; then
        return 1
    fi
}

PY3=python3.7
PROMPT=venv
VENV_DIR=.venv

activate_env $VENV_DIR
if [ $? -eq 0 ]; then
    return
fi

echo "Creating virtual environment in $VENV_DIR."
$PY3 -m venv --prompt=$PROMPT $VENV_DIR
if [ ! $? -eq 0 ]; then
    return
fi

activate_env $VENV_DIR
pip install -r requirements.txt --log pip.log