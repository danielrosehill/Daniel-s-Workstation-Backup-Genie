#!/bin/bash

# Daniel's Workstation Backup Genie - V1
# Created by Daniel in collaboration with Claude, an AI assistant by Anthropic

set -x

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Error: This script must be run as root (sudo)."
    exit 1
fi

# Check if root filesystem is BTRFS
if [ "$(stat -f -c %T /)" != "btrfs" ]; then
    echo "Error: Root filesystem is not BTRFS. This script requires a BTRFS root filesystem."
    exit 1
fi

# Get approved Serial Numbers from command-line arguments
APPROVED_SNS=("$@")

find_device_by_serial() {
    local serial="$1"
    lsblk -ndo NAME,SERIAL,SIZE,MOUNTPOINT | awk -v serial="$serial" '$2 == serial {print $1"1", $3, $4}'
}

check_btrfs_format() {
    local device="$1"
    echo "Checking BTRFS format for $device..."
    if sudo btrfs filesystem show "$device" &>/dev/null; then
        echo "Device $device is formatted as BTRFS."
        return 0
    else
        local fs_type=$(sudo blkid -s TYPE -o value "$device")
        if [ "$fs_type" == "btrfs" ]; then
            echo "Device $device is formatted as BTRFS (detected by blkid)."
            return 0
        fi
    fi
    echo "Error: Device $device does not appear to be formatted as BTRFS."
    return 1
}

prepare_mount_point() {
    local device="$1"
    local mount_point="$2"
    if [ ! -d "$mount_point" ]; then
        sudo mkdir -p "$mount_point"
    fi
    if ! mountpoint -q "$mount_point"; then
        if sudo mount "$device" "$mount_point"; then
            echo "Device mounted successfully at $mount_point"
        else
            echo "Error mounting $device to $mount_point"
            return 1
        fi
    else
        echo "Device already mounted at $mount_point"
    fi
    return 0
}

perform_backup() {
    local source="/"
    local destination="$1"
    local timestamp=$(date +"%Y-%m-%d_%H-%M-%S")
    local temp_snapshot="/root/temp_btrfs_snapshot_${timestamp}"
    local final_snapshot_name="snapshot_${timestamp}"

    echo "Starting backup..."

    # Create a temporary snapshot
    if sudo btrfs subvolume snapshot -r "$source" "$temp_snapshot"; then
        echo "Temporary snapshot created: $temp_snapshot"

        # If there's a previous snapshot on the destination, do an incremental send
        local prev_snapshot=$(sudo btrfs subvolume list -o "$destination" | tail -n1 | awk '{print $NF}')
        if [ -n "$prev_snapshot" ]; then
            echo "Previous snapshot found: $prev_snapshot"
            echo "Performing incremental backup..."

            # Ensure the previous snapshot is read-only
            sudo btrfs property set -ts "$destination/$prev_snapshot" ro true

            # Check if the previous snapshot exists and is accessible
            if [ ! -d "$destination/$prev_snapshot" ]; then
                echo "Error: Previous snapshot not found or inaccessible."
                sudo btrfs subvolume delete "$temp_snapshot"
                return 1
            fi

            # Perform the incremental send/receive with error checking
            if sudo btrfs send -vv -p "$destination/$prev_snapshot" "$temp_snapshot" | sudo btrfs receive -vv "$destination"; then
                echo "Incremental backup completed successfully."
            else
                echo "Failed to perform incremental backup. Falling back to full backup."
                if sudo btrfs send -vv "$temp_snapshot" | sudo btrfs receive -vv "$destination"; then
                    echo "Full backup completed successfully."
                else
                    echo "Failed to perform full backup."
                    sudo btrfs subvolume delete "$temp_snapshot"
                    return 1
                fi
            fi
        else
            echo "No previous snapshot found. Performing full backup..."
            if sudo btrfs send -vv "$temp_snapshot" | sudo btrfs receive -vv "$destination"; then
                echo "Full backup completed successfully."
            else
                echo "Failed to perform full backup."
                sudo btrfs subvolume delete "$temp_snapshot"
                return 1
            fi
        fi

        # Rename the received snapshot to remove the "temp_" prefix
        sudo mv "$destination/$(basename $temp_snapshot)" "$destination/$final_snapshot_name"

        # Clean up the temporary snapshot
        sudo btrfs subvolume delete "$temp_snapshot"

        # Delete old snapshots, keeping only the last 3
        sudo btrfs subvolume list -o "$destination" | head -n -3 | cut -d ' ' -f9 | xargs -I {} sudo btrfs subvolume delete "$destination/{}"

        echo "Backup completed successfully."
    else
        echo "Failed to create temporary snapshot."
        return 1
    fi
}

main() {
    local device_info

    for sn in "${APPROVED_SNS[@]}"; do
        device_info=$(find_device_by_serial "$sn")
        if [ -n "$device_info" ]; then
            read -r device_name size current_mount <<< "$device_info"
            device_path="/dev/${device_name}"
            echo "Found backup device:"
            echo " Device: $device_path"
            echo " Serial: $sn"
            echo " Size: $size"
            echo " Current Mount: ${current_mount:-Not mounted}"

            # Unmount the device if it's mounted
            if [ -n "$current_mount" ]; then
                echo "Unmounting $device_path from $current_mount"
                sudo umount "$device_path"
                if [ $? -ne 0 ]; then
                    echo "Failed to unmount $device_path. Please unmount manually and try again."
                    return 1
                fi
            fi

            if check_btrfs_format "$device_path"; then
                mount_point="/mnt/btrfs_backup"
                if prepare_mount_point "$device_path" "$mount_point"; then
                    perform_backup "$mount_point"
                    return 0
                else
                    echo "Failed to prepare mount point at $mount_point"
                fi
            else
                echo "Error: Device is not formatted as BTRFS or cannot be accessed. Please check the device and try again."
            fi
        fi
    done

    echo "No device found with any of the approved serial numbers."
    return 1
}

main "${APPROVED_SNS[@]}"