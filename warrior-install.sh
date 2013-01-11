#!/bin/bash
if ! sudo pip freeze | grep -q beautifulsoup4
then
  echo "Installing BeautifulSoup 4"
  if ! sudo pip install beautifulsoup4
  then
    exit 1
  fi
fi

if ! sudo pip freeze | grep -q requests
then
  echo "Installing Requests"
  if ! sudo pip install requests
  then
    exit 1
  fi
fi

exit 0

