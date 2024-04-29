#!/bin/bash

USERNAME=""
PASSWORD=""
OTP_SECRET=""

LOGDIR=$1
PROGDIR=$(dirname -- $0)

if [ -z "$LOGDIR" ]; then
    $PROGDIR/noip-renew.py "$USERNAME" "$PASSWORD" "$OTP_SECRET" 2
else
    cd $LOGDIR
    : > $USERNAME.log 
    $PROGDIR/noip-renew.py "$USERNAME" "$PASSWORD" "$OTP_SECRET" 2 >> $USERNAME.log
fi
