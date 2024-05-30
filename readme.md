# GakuenUpdater

GakuenUpdater is a Python-based automation tool designed to manage the installation, launching, and monitoring of Gakuen idolm@ster (学園アイドルマスター) on an Android device via ADB (Android Debug Bridge). 

This automation tool handles various aspects of the game update process, such as uninstalling the existing game, installing a new version from the Google Play Store, and navigating through the initial setup screens.

## Requirements

- Python 3.x
- ADB (Android Debug Bridge) installed and accessible from the command line
- An Android device connected and recognized by ADB
- Required Python packages (listed in `requirements.txt`)

## Installation

1. **Clone the repository:**
   ```sh
   git clone <repository-url>
   cd GakuenUpdater
   ```

2. **Install required Python packages:**
   ```sh
   pip install -r requirements.txt
   ```

3. **Ensure ADB is installed and added to your system's PATH.**
   - Download ADB from [Android Developer Tools](https://developer.android.com/studio/releases/platform-tools).
   - Follow the instructions to set it up on your system.

4. **Prepare the `config.yaml` file:**
   ```yaml
   adb:
     server:
       host: 127.0.0.1
       port: 5037
     device_serial: 10.1.1.60:6666

   uninstall: True
   install: True

   timeouts:
     detect_credit_screen: 300
     detect_setup_screen: 300
     gakuen_running: 300
   ```

5. **Place the required assets in the `assets` directory:**
   - `gakuen_setup.png`
   - `gakuen_loading.png`
   - `playstore_install.png`
   - `gakuen_consent.png`
   - `gakuen_agree.png`
   - `gakuen_agree_all.png`
   - `gakuen_move_forward.png`

## Usage

1. **Run the script:**
   ```sh
   python GakuenUpdater.py
   ```

## Configuration

The `config.yaml` file contains the necessary configuration settings:

- **ADB Settings:**
  - `adb.server.host`: The host address of the ADB server.
  - `adb.server.port`: The port number of the ADB server.
  - `adb.device_serial`: The serial number of the target device.

- **Installation Settings:**
  - `uninstall`: Set to `True` to uninstall the existing game before installing the new version.
  - `install`: Set to `True` to install the game from the Play Store.
  - `wait_for_download`: Set to `True` to wait for the game to finish downloading assets.

- **Timeout Settings:**
  - `timeouts.detect_credit_screen`: Timeout for detecting the credit screen (in seconds).
  - `timeouts.detect_setup_screen`: Timeout for detecting the setup screen (in seconds).
  - `timeouts.gakuen_running`: Timeout for checking if the game is running (in seconds).
  - `timeouts.download_start`: Timeout for waiting for the download of assets to start (in seconds).
  - `download_finish`: Timeout for waiting for the asset download to finish (in seconds).


## Troubleshooting

- Ensure the device is connected and recognized by ADB:
  ```sh
  adb devices
  ```
- Check the ADB server is running and accessible at the specified host and port.
- Verify the `config.yaml` file is correctly configured.
- Ensure the required assets are present in the `assets` directory.
- The script has been made with a resolution of 2560x1600 in mind
- It has only been tested on an android instance running in Docker (redroid)

## Contributing

Contributions are welcome! Please fork the repository and create a pull request with your changes.

## License

This project is licensed under the MIT License.

## Acknowledgements

- [MTM](https://github.com/multi-template-matching/MultiTemplateMatching-Python) for the template matching functionality.
- [Pillow](https://python-pillow.org/) for image handling.
- [pure-python-adb](https://github.com/Swind/pure-python-adb) for device communication.
