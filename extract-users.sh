#!/bin/bash
data_dir=$1
user_list=$2
if [ -d $data_dir/files/punchfork.com/recipe ]
then
  grep -h 'class="tiny-user-card"' $data_dir/files/punchfork.com/recipe/* | grep -oE 'href="[^"]+' | cut -c 8- | sort -u > $user_list
else
  touch $user_list
fi

