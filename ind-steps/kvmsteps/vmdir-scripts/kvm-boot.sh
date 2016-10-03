#!/bin/bash

reportfailed()
{
    echo "Script failed...exiting. ($*)" 1>&2
    exit 255
}

export ORGCODEDIR="$(cd "$(dirname $(readlink -f "$0"))" && pwd -P)" || reportfailed
export CODEDIR="$(cd "$(dirname "$0")" && pwd -P)" || reportfailed

if [ "$DATADIR" = "" ]; then
    # Choose directory of symbolic link by default
    DATADIR="$CODEDIR"
fi
source "$ORGCODEDIR/simple-defaults-for-bashsteps.source"
source "$DATADIR/datadir.conf"
[ -d "$DATADIR/runinfo" ] || mkdir "$DATADIR/runinfo"
: ${KVMMEM:=1024}
: ${VNCPORT:=$(( 11100 - 5900 ))}
# Note: EXTRAHOSTFWD can be set to something like ",hostfwd=tcp::18080-:8888"
#       EXTRAHOSTFWDREL works the same, except the first port number
#       after each hostfwd=tcp gets replaced with $VNCPORT added to that number.
#       Therefore, using EXTRAHOSTFWDREL lets this script try different ports
#       whenever there is a port collision.

calculate_ports()
{
    echo ${VNCPORT} >"$DATADIR/runinfo/port.vnc"
    echo ${SSHPORT:=$(( VNCPORT + 22 ))} >"$DATADIR/runinfo/port.ssh"
    echo ${MONPORT:=$(( VNCPORT + 30 ))} >"$DATADIR/runinfo/port.monitor"
    echo ${SERPORT:=$(( VNCPORT + 40 ))} >"$DATADIR/runinfo/port.serial"
    rewriteme="$EXTRAHOSTFWDREL"  # e.g. ",hostfwd=tcp::80-:8888,...."
    hostfwdrel=""
    set -x
    while [[ "$rewriteme" == *hostfwd=tcp* ]]; do
	portatfront="${rewriteme#*hostfwd=tcp:*:}"   # e.g. "80-:8888,...."
	afterport="${portatfront#*-}"  # e.g. ":8888,...."
	theport="${portatfront%$afterport}"  # e.g. 80-
	theport="${theport%-}"  # e.g. 80
	if [ "$theport" == "" ] || [ "${theport//[0-9]/}" != "" ]; then
	    reportfailed "Non digit character in port number in $EXTRAHOSTFWDREL"
	fi
	hostfwdrel="$hostfwdrel${rewriteme%$portatfront}"  # e.g. ",hostfwd=tcp::"
	hostfwdrel="$hostfwdrel$(( theport + VNCPORT ))"  # e.g. ",hostfwd=tcp::18080"
	rewriteme="-$afterport"  # e.g. "-:8888,...."
    done
    hostfwdrel="$hostfwdrel$rewriteme"  # append rest
}
calculate_ports

(
    $starting_group "Boot KVM"
    (
	$starting_step "Find qemu binary"
	[ "$KVMBIN" != "" ] && [ -f "$KVMBIN" ]
	$skip_step_if_already_done
	binlist=(
	    /usr/libexec/qemu-kvm
	    /usr/bin/qemu-kvm
	)
	for i in "${binlist[@]}"; do
	    if [ -f "$i" ]; then
		echo ": \${KVMBIN:=$i}" >>"$DATADIR/datadir.conf"
		exit 0
	    fi
	done
	exit 1
    ) ; prev_cmd_failed
    source "$DATADIR/datadir.conf"

    # TODO: decide if it is worth generalizing kvmsteps to deal with cases like this:
    [ "$mcastPORT" = "" ] && mcastPORT="1234"
    [ "$mcastMAC" = "" ] && mcastMAC="52:54:00:12:00:00"
    [ "$mcastnet" = "" ] && mcastnet="-net nic,vlan=1,macaddr=$mcastMAC  -net socket,vlan=1,mcast=230.0.0.1:$mcastPORT"

    build-cmd-line() # a function, not a step
    {
        ## Putting all non-wakame nodes on 10.0.3.0/24 so Wakame instances can be accessed at 10.0.2.0/24
	cat <<EOF
	    $KVMBIN

	    -m $KVMMEM
	    -smp 2
	    -name kvmsteps

	    -monitor telnet:127.0.0.1:$MONPORT,server,nowait
	    -no-kvm-pit-reinjection
	    -vnc 127.0.0.1:$VNCPORT
	    -serial telnet:127.0.0.1:$SERPORT,server,nowait
	    -drive file=$IMAGEFILENAME,id=vol-tu3y7qj4-drive,if=none,serial=vol-tu3y7qj4,cache=none,aio=native
	    -device virtio-blk-pci,id=vol-tu3y7qj4,drive=vol-tu3y7qj4-drive,bootindex=0,bus=pci.0,addr=0x4

	    -net nic,vlan=0,macaddr=52:54:00:65:28:dd,model=virtio,addr=10
	    -net user,net=10.0.3.0/24,vlan=0,hostfwd=tcp::$SSHPORT-:22$EXTRAHOSTFWD$hostfwdrel

            $mcastnet
EOF
    }

    portcollision()
    {
	erroutput="$(cat "$DATADIR/runinfo/kvm.stderr")"
	for i in "could not set up host forwarding rule" \
		     "Failed to bind socket" \
		     "socket bind failed"
	do
	    if [[ "$erroutput" == *${i}* ]]; then
		echo "Failed to bind a socket, probably because it is already in use." 1>&2
		echo "Will try a different set of port numbers." 1>&2
		# pick a random number between 100 and 300, then add two zeros
		target="$(( $RANDOM % 200 + 100 ))00"
		VNCPORT="$(( target - 5900 ))"
		SSHPORT=""  MONPORT=""  SERPORT=""
		calculate_ports

		# value is saved, so that the VM will attempt to use same ports next time
		echo "VNCPORT=$VNCPORT" >>"$DATADIR/datadir.conf"
		return 0 # yes, a port collision, so retry
	    fi
	done
	return 1 # no, so maybe KVM started OK
    }

    kvm_is_running()
    {
	pid="$(cat "$DATADIR/runinfo/kvm.pid" 2>/dev/null)" &&
	    [ -d /proc/"$(< "$DATADIR/runinfo/kvm.pid")" ]
    }

    (
	$starting_step "Start KVM process"
	kvm_is_running
	$skip_step_if_already_done
	set -e
	: ${KVMBIN:?} ${IMAGEFILENAME:?} ${KVMMEM:?}
	: ${VNCPORT:?} ${SSHPORT:?} ${MONPORT:?} ${SERPORT:?}
	set -e
	cd "$DATADIR"
	repeat=true
	while $repeat; do
	    repeat=false
	    ( # using a temporary subprocess to supress job control messages
		kpat=( $(build-cmd-line) )
		# Using /dev/null in the next line so that ssh will exit when used to call
		# this script.  Otherwise, the open stdout and stderr will keep ssh connected.
		setsid "$ORGCODEDIR/monitor-process.sh" runinfo/kvm "${kpat[@]}" 1>/dev/null 2>&1 &
	    )
	    for s in ${kvmearlychecks:=1 1 1 1 1} ; do # check early errors for 5 seconds
		sleep "$s"
		if ! kvm_is_running; then
		    portcollision && { repeat=true; break ; }
		    reportfailed "KVM exited early. Check runinfo/kvm.stderr for clues."
		fi
	    done
	    sleep 0.5
	done
    ) ; prev_cmd_failed
    source "$DATADIR/datadir.conf"
    SSHPORT=""  MONPORT=""  SERPORT="" # TODO: make this not needed
    calculate_ports

    ssh_is_active()
    {
	# TODO: make sure this generalizes to different version of nc
	[[ "$(nc 127.0.0.1 -w 3 "$SSHPORT" </dev/null)" == *SSH* ]]
    }

    : ${WAITFORSSH:=5 2 1 1 1 1 1 1 1 1 5 10 20 30 120} # set WAITFORSSH to "0" to not wait
    (
	$starting_step "Wait for SSH port response"
	[ "$WAITFORSSH" = "0" ] || kvm_is_running && ssh_is_active
	$skip_step_if_already_done
	WAITFORSSH="${WAITFORSSH/[^0-9 ]/}" # make sure its only a list of integers
	waitfor="5"
	while true; do
	    ssh_is_active && break
	    # Note that the </dev/null above is necessary so nc does not
	    # eat the input for the next line
	    read -d ' ' nextwait # read from list
	    [ "$nextwait" == "0" ] && reportfailed "SSH port never became active"
	    [ "$nextwait" != "" ] && waitfor="$nextwait"
	    echo "Waiting for $waitfor seconds for ssh port ($SSHPORT) to become active"
	    sleep "$waitfor"
	done <<<"$WAITFORSSH"
    ) ; prev_cmd_failed
)
