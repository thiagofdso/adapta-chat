#!/bin/bash

# This script renames video files to add a leading zero if the number is less than 100.

# Loop through all files matching the pattern "-video.txt" in the current directory.
for file in *-video.txt; do
    # Extract the numeric part of the filename.
    numberStr=$(echo "$file" | cut -d'-' -f1)

    # Check if the extracted part is a number.
    if [[ "$numberStr" =~ ^[0-9]+$ ]]; then
        # Check if the number is less than 100.
        if [ "$numberStr" -lt 100 ]; then
            # Construct the new filename by adding a "0" at the beginning.
            newName="0$file"
            
            # Display the change that will be made.
            echo "Renaming '$file' to '$newName'"
            
            # Rename the file.
            mv -- "$file" "$newName"
        fi
    fi
done

echo "Renaming completed."
