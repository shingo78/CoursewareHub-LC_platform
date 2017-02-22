#!/bin/bash

reportfailed()
{
    echo "Script failed...exiting. ($*)" 1>&2
    exit 255
}

usage()
{
    cat <<EOF
Usage:

./bin/serverctl {hubid} list                       ## List servers
./bin/serverctl {hubid} netconnections             ## List all(?) ESTABLISHED connections in system

EOF
}

export ORGCODEDIR="$(cd "$(dirname $(readlink -f "$0"))" && pwd -P)" || reportfailed

rootdir="${ORGCODEDIR%/*}"
ahdir="$rootdir/active-hubs"

DDCONFFILE="datadir.conf"


[ -d "$ahdir" ] || mkdir "$ahdir" || reportfailed

node_list="node1 node2"  # This should be overwritten by the value in the main datadir.conf

classid_to_hubpath()
{
    if [ -f "$1/hubid" ]; then
	echo "$1"
	exit
    else
	local hubid="$1"
	result="$(grep -HFx "$hubid" "$ahdir"/*/hubid)"
	[ "$result" = "" ] && reportfailed "Hub with name '$hubid' not found"
	# result is something like: active-hubs/002/hubid:class4
	echo "${result%/hubid*}"
    fi
}

get_container_names()
{
    annotation="$1"
    read ln # skip first line
    while read -a allwords; do
	lastword="${allwords[@]: -1}"
	echo "$lastword$annotation"
    done
}

do_list()
{
    for n in $node_list; do
	"$hubpath"/jhvmdir-${n}/ssh-shortcut.sh -q sudo docker ps -a | get_container_names " ($n)"
    done
}

netstat_filter1()
{
    while read ln; do
	# skip ssh connections
	[[ "$ln" == *10.0.3.15:22* ]] && continue

	# skip header lines
	[[ "$ln" == Active* ]] && continue
	[[ "$ln" == Proto* ]] && continue

	# skip NFS lines
	[[ "$ln" == *192.168.33.1?:848* ]] && continue
	[[ "$ln" == *192.168.33.1?:834* ]] && continue
	echo "$ln"
    done
}

info_from_inside_a_kvm()
{
    local vmdir="$1"
    "$hubpath/$vmdir/ssh-shortcut.sh" -q sudo netstat -ntp | netstat_filter1

    containerlist="$(
         "$hubpath/$vmdir/ssh-shortcut.sh" -q sudo docker ps | (
     read skipfirst
     rev | while read token1 therest ; do echo "$token1" ; done | rev
           )
    )"
#    echo "$containerlist"

    for c in $containerlist; do
	if [ "$aptupdate" != "" ]; then
	    "$hubpath/$vmdir/ssh-shortcut.sh" -q sudo docker exec $c apt-get update
	    "$hubpath/$vmdir/ssh-shortcut.sh" -q sudo docker exec $c apt-get install -y net-tools
	fi
	echo "Container (($c))"
#        echo "$hubpath/$vmdir/ssh-shortcut.sh -q sudo docker exec $c netstat -ntp"
        "$hubpath/$vmdir/ssh-shortcut.sh" -q sudo docker exec $c netstat -ntp | netstat_filter1
    done
}

do_netconnections()
{
    for vm in "${vmdirlist[@]}"; do
	echo ",,,,,,,,,,,,,,,,,,,,,,,,,$vm,,,,,,,,,,,,,,,,,,,,,,"
	info_from_inside_a_kvm "$vm"
    done
#    "$hubpath/jhvmdir-hub/ssh-shortcut.sh" -q sudo docker exec root_jupyterhub_1 netstat -ntp4 | netstat_filter1
}

hubpath="$(classid_to_hubpath "$1")" || exit
source "$hubpath/$DDCONFFILE" || reportfailed "missing $DDCONFFILE"
shift

cmd="$1"
shift

case "$cmd" in
    list)
	do_list "$@"
	;;
    netconnections)
	do_netconnections "$@"
	;;
    *) usage
       ;;
esac
