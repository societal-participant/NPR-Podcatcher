# NPR Podcatcher
The NPR Podcatcher is a dedicated player appliance for listening to your favorite NPR podcasts. The podcatcher downloads your specified NPR broadcasts to your Raspberry Pi Zero W, where you can listen to them. 

## About the Podcatcher
### Hardware Requirements
### Software Requirements

1. Base operating system

-   **Raspberry Pi OS**
    -   Debian Trixie
-   To fully update the dydtem:
    
    ```
    sudo apt update
    sudo apt upgrade -y
    ```
    
2. Essential system packages

-   Python 3
-   Git
-   ALSA utilities
-   mpv
-   FFmpeg

A clean installation can start with:

```
sudo apt install -y python3 python3-pip git alsa-utils mpv ffmpeg
```

3. Audio system

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
eyJoaXN0b3J5IjpbMTQyMjg4NjI2NywtMTc3OTM0OTY5OSwtNj
M0MTEzMjVdfQ==
-->