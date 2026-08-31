# NPR Podcatcher
The NPR Podcatcher is a dedicated player appliance for listening to your favorite NPR podcasts. The podcatcher downloads your specified NPR broadcasts to your Raspberry Pi Zero W, where you can listen to them. 

## About the Podcatcher
### Hardware Requirements
### Software Requirements
1. Base operating system

-   **Raspberry Pi OS**
    -   Debian-based
    -   Our current Pi is running **64-bit ARM (`aarch64`)**
-   System fully updated:
    
    ```
    sudo apt update
    sudo apt upgrade -y
    ```
    

### 2. Essential system packages

These are the things I'd consider part of the basic software environment:

-   Python 3
-   Python 3 `pip` if we end up needing third-party Python packages
-   Git
-   ALSA utilities
-   mpv
-   FFmpeg

A clean installation can start with:

```
sudo apt install -y python3 python3-pip git alsa-utils mpv ffmpeg
```

### 3. Audio system

-   ALSA installed/configured
-   MAX98357A ALSA device recognized
-   Verify with:
    
    ```
    aplay -l
    ```
    

We currently expect:

```
card 0: MAX98357A
```

The player specifically targets:

```
alsa/plughw:MAX98357A
```

## Installing the Podcatcher Files

## Configuring the Podcatcher

## Assembling the Podcatcher

## Using the Podcatcher

<!--stackedit_data:
eyJoaXN0b3J5IjpbNjU2OTExNDAyLC0xNzc5MzQ5Njk5LC02Mz
QxMTMyNV19
-->