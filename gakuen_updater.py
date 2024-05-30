import os
import io
import cv2
import time
import yaml
import logging
import numpy as np
import pandas as pd

from PIL import Image
from MTM import matchTemplates
from ppadb.client import Client as AdbClient

class GakuenUpdater():
    log = logging.getLogger("MAIN")

    ASSETS_NUMPY = { # load the assets as numpy arrays for template matching
        "gakuen_setup": np.array(Image.open("assets/gakuen_setup.png").convert("L")),
        "loading": np.array(Image.open("assets/gakuen_loading.png").convert("L")),
        "playstore_install": np.array(Image.open("assets/playstore_install.png").convert("L")),
        "gakuen_consent": np.array(Image.open("assets/gakuen_consent.png").convert("L")),
        "gakuen_agree": np.array(Image.open("assets/gakuen_agree.png").convert("L")),
        "gakuen_agree_all": np.array(Image.open("assets/gakuen_agree_all.png").convert("L")),
        "gakuen_move_forward": np.array(Image.open("assets/gakuen_move_forward.png").convert("L")),
    }

    def __init__(self) -> None:
        self.load_config()
        logging.info(f"Connecting to ADB server at {self.config['adb']['server']['host']}:{self.config['adb']['server']['port']}")
        self.adb = AdbClient(host=self.config['adb']['server']['host'],
                              port=self.config['adb']['server']['port'])
        
        assert self.config['adb']['device_serial'] in [d.serial for d in self.adb.devices()], f"Device {self.config['adb']['device_serial']} not found."
        self.device = self.adb.device(self.config['adb']['device_serial'])
        logging.info(f"Device {self.config['adb']['device_serial']} found.")

    def load_config(self) -> None:
        # if the config file exists, load it
        if os.path.exists("config.yaml"):
            with open("config.yaml", "r") as f:
                self.config = yaml.safe_load(f)
                logging.info("Configuration loaded successfully.")
        else:
            raise FileNotFoundError("Configuration file not found.")

    def start(self):
        """
        Starts the Gakuen Updater process.

        This method handles the installation, launching, and monitoring of Gakuen imas.
        It checks if the game is already installed and uninstalls it if specified in the configuration.
        If the game is not installed and installation is enabled in the configuration, it launches the Play Store,
        installs the game, waits for the installation to complete, and then launches the game.
        It waits for the game to start, detects the loading screens, and clicks on buttons until the game starts.
        Finally, it waits for the game to finish downloading and exits the game.

        Raises:
            Exception: If the game does not finish installing or starting within the specified timeouts.
        """
        self.rotate()
        
        if self.config['uninstall']:
            if self.gakuen_installed():
                logging.info("Uninstalling Gakuen.")
                self.uninstall_gakuen()


        if not self.gakuen_installed() and self.config['install']:
            logging.info("Gakuen not installed, launching Play Store.")
            self.launch_playstore()
            self.playstore_install()
            if not self.wait_install():
                raise Exception("Game did not finish installing in time, exiting.")
            self.press_home()
            time.sleep(3)
            self.log.info("Game installed successfully.")
        else:
            self.exit_gakuen() 
        
        self.launch_gakuen()
        
        logging.info("Waiting for game to start.")
        assert self.wait_function(self.gakuen_running,
                                  exec_func=self.launch_gakuen,
                                  timeout=self.config['timeouts']['gakuen_running'],
                                  boolean=True) == True, "Game did not start in time, exiting."

        logging.info("Waiting for game to finish loading.")
        assert self.wait_function(self.detect_credit_screen, 
                                  timeout=self.config['timeouts']['detect_credit_screen']) == True, "Game did not finish loading in time, exiting. (credits screen)"
        logging.info("Passed credits screen.")
        
        assert self.wait_function(self.detect_setup_screen, 
                                  timeout=self.config['timeouts']['detect_setup_screen']) == True, "Game did not finish loading in time, exiting. (loading screen)"
        logging.info("Game loaded successfully.")

        self.click_middle_screen() # click the screen to start
        time.sleep(1)
        
        
        
        logging.info("Entering button click loop.")
        self.button_click_loop()
        logging.info("Game download started.")

        if not self.config['wait_for_download']:
            logging.info("flag set to not wait for download, exiting.")
            self.exit_gakuen()
            return
        
        self.download_loop()
    
    def button_click_loop(self):
        """
        This method handles the consent screens and the initial setup screens.
        It waits for the game to start downloading additional data and raises an exception if it takes too long.

        Algorithm:
        1. Wait for the screen orientation to be 0 (indicating the initial setup screens).
        2. Detect the screen and click buttons to handle consent screens and initial setup.
        3. Sleep for 1 second.
        4. If the game does not start downloading within the specified timeout, raise an exception.

        Raises:
            Exception: If the game does not start downloading in time.

        """
        timeout = time.time() + self.config['timeouts']['download_start'] 
        while self.get_screen_orientation() == 0:
            self.detect_screen(1)
            self.click_buttons(True)
            time.sleep(1)
            if time.time() > timeout:
                raise Exception("Game did not start downloading in time, exiting.")
    
    def download_loop(self):
        """
        Continuously checks if the game has finished downloading.
        If the game does not finish downloading within the specified timeout,
        an exception is raised and the program exits.
        """
        logging.info("Entering download loop.")
        timeout = time.time() + self.config['timeouts']['download_finish']
        while not self.detect_move_forward():
            self.click_middle_screen()
            time.sleep(1)
            if time.time() > timeout:
                raise Exception("Game did not finish downloading in time, exiting.")
        
        logging.info("Game has finished downloading!")
        self.exit_gakuen()
    
    def rotate(self):
        """
        Rotates the device screen by disabling accelerometer rotation and setting the user rotation to 3.
        This method uses ADB shell commands to change the device settings. It sets the accelerometer_rotation to 0,
        which disables the automatic rotation of the screen based on the device's orientation. It also sets the
        user_rotation to 3, which rotates the screen to a specific orientation (landscape mode in this case).
        Note: This method requires ADB (Android Debug Bridge) to be installed and the device to be connected.
        Returns:
            None
        """
        self.device.shell("settings put system accelerometer_rotation 0")
        self.device.shell("settings put system user_rotation 3")

    def save_screenshot(self):
        """ 
        Save a screenshot to the current working directory.
        
        This method captures a screenshot using the `screenshot` method and saves it as a PNG file in the current working directory. The filename is generated based on the current timestamp.
        """
        self.screenshot().save(f"{str(time.time()).split('.')[0]}.png")

    def match_resolution(self):
        """ 
        Matches the resolution of the device to the images used for element detection.
        
        This method checks if the device resolution matches the supported resolution of 2560x1600 or 1600x2560.
        If the resolution matches, it logs a message indicating the resolution is matched.
        If the resolution is rotated, it logs a message indicating the resolution is matched but rotated.
        If the resolution is not supported, it raises an exception with the actual device resolution.
        """
        # match resolution in either horizontal or vertical direction
        if self.get_resolution() == (2560, 1600):
            logging.info("Device resolution matched.")
            return
        elif self.get_resolution() == (1600, 2560):
            logging.info("Device resolution matched. (Rotated)")
            return
        else:
            raise Exception(f"Device resolution {self.get_resolution()} not supported.")

    def press_home(self):
        """Presses the home button."""
        self.device.shell("input keyevent 3")

    def screenshot(self) -> Image.Image:
        """
        Take a screenshot and return it as a PIL Image.

        Returns:
            Image.Image: The screenshot image as a PIL Image object.
        """
        stream = io.BytesIO(self.device.screencap())
        stream.seek(0)
        return Image.open(stream)

    def get_screen_orientation(self) -> int:
        """ 
        Get the screen orientation of the device.
        
        Returns:
            int: The screen orientation of the device. 0 for portrait, 1 for landscape.
        """
        orientation = self.device.shell("dumpsys window | grep mCurrentAppOrientation | awk '{ print $1 }'").split("=")[-1].strip()
        
        if orientation == "SCREEN_ORIENTATION_PORTRAIT":
            return 0
        elif orientation == "SCREEN_ORIENTATION_LANDSCAPE":
            return 1
        elif orientation == "SCREEN_ORIENTATION_UNSPECIFIED":
            return 0 # default to portrait
        else:
            raise Exception(f"Unknown screen orientation: {orientation}")

    def get_resolution(self) -> tuple:
        """ 
        Get the resolution of the device.
        
        Returns:
            A tuple representing the resolution of the device in the format (width, height).
        """
        return tuple(map(int, self.device.shell("wm size").split(" ")[-1].split("x")))

    def gakuen_installed(self) -> bool:
        """Check if com.bandainamcoent.idolmaster_gakuen is installed.

        Returns:
            bool: True if the package is installed, False otherwise.
        """
        return "package:com.bandainamcoent.idolmaster_gakuen" in self.device.shell("pm list packages").split("\n")

    def uninstall_gakuen(self) -> None:
        """Uninstall the com.bandainamcoent.idolmaster_gakuen package.

        This method sends a shell command to uninstall the
        com.bandainamcoent.idolmaster_gakuen package.

        """
        self.device.shell("pm uninstall com.bandainamcoent.idolmaster_gakuen")

    def launch_gakuen(self) -> None:
        """ 
        Launches the com.bandainamcoent.idolmaster_gakuen application.
        
        Note:
                - For devices without hardware keys or screens (e.g., emulators or running in a docker container),
                    the `pct-syskeys 0` option is needed.
        
        """
        self.device.shell("monkey --pct-syskeys 0 -p com.bandainamcoent.idolmaster_gakuen 1")
        time.sleep(1) # wait at least one second for the app to start

    def exit_gakuen(self)-> None:
        """Exit the com.bandainamcoent.idolmaster_gakuen application.

        This method sends a shell command to force-stop the
        com.bandainamcoent.idolmaster_gakuen application, effectively
        closing it.

        """
        self.device.shell("am force-stop com.bandainamcoent.idolmaster_gakuen")
    
    def gakuen_running(self) -> bool:
        """Check if com.bandainamcoent.idolmaster_gakuen is running.

        Returns:
            bool: True if the package is running, False otherwise.
        """
        return "com.bandainamcoent.idolmaster_gakuen" in self.device.shell("ps -A").split("\n")

    def launch_playstore(self):
        """Launches the Google Play Store with the specified package ID.

        This method uses the `am start` command to launch the Google Play Store
        with the specified package ID. It sends an intent with the action
        `android.intent.action.VIEW` and the data `market://details?id=com.bandainamcoent.idolmaster_gakuen`.

        Note:
            This method requires the Android Debug Bridge (ADB) to be installed
            and the device to be connected to the computer.

        Args:
            self (object): The current instance of the class.

        Returns:
            None
        """
        self.device.shell("am start -a android.intent.action.VIEW -d 'market://details?id=com.bandainamcoent.idolmaster_gakuen'")
        time.sleep(1)

    def match_template(self, templates: dict, img: np.ndarray, 
                       image_mode: str = "L", threshold: float = 0.8) -> pd.DataFrame:
        """
        Match a list of templates to an image.

        Parameters:
            templates (dict): A dictionary containing the templates to match.
            img (np.ndarray): The image to match the templates against.
            image_mode (str, optional): The mode of the image. Defaults to "L".
            threshold (float, optional): The threshold for matching. Defaults to 0.8.

        Returns:
            pd.DataFrame: A DataFrame containing the matched templates and their scores.
        """
        screenshot = np.array(self.screenshot().convert(image_mode))
        return matchTemplates(templates, screenshot, N_object=1, 
                              score_threshold=threshold, method=cv2.TM_CCOEFF_NORMED)

    def click_template(self, templateResults: pd.DataFrame) -> pd.DataFrame:
        """
        Clicks on the templates in the given DataFrame if their score is above 0.8.

        Args:
            templateResults (pd.DataFrame): A DataFrame containing template matching results.

        Returns:
            pd.DataFrame: The original DataFrame with the clicked templates.
        """
        for _, row in templateResults.iterrows():
            # make sure the score is above 0.8
            if row['Score'] < 0.8:
                continue
            x, y, w, h = row['BBox']
            self.device.shell(f"input tap {x + w // 2} {y + h // 2}")
        return templateResults

    def click_middle_screen(self) -> None:
            """Clicks the middle of the screen.

            This method calculates the coordinates of the ""middle"" of the screen
            and performs a tap action at that location using ADB shell command.

            Returns:
                None
            """
            logging.info("Clicking screen.")
            w, h = self.get_resolution()
            self.device.shell(f"input tap {w // 2} {h // 2}")
            time.sleep(1)

    def detect_screen(self, screen_type: int, threshold: float = 0.8) -> bool:
        """
        Detects if the specified screen type is currently being displayed.

        Args:
            screen_type (int): The type of screen to detect. 0 for setup screen, 1 for loading screen.
            threshold (float, optional): The minimum score threshold for considering a screen as detected. Defaults to 0.8.

        Returns:
            bool: True if the specified screen is detected, False otherwise.
        """
        if screen_type == 0:
            templateResp = self.match_template([("loading", self.ASSETS_NUMPY['gakuen_setup'])], self.screenshot())
        elif screen_type == 1:
            templateResp = self.match_template([("loading", self.ASSETS_NUMPY['loading'])], self.screenshot())
        else:
            raise ValueError("Invalid screen type. Must be 0 for setup screen or 1 for loading screen.")
        
        templateResp = templateResp[templateResp["Score"] > threshold] # filter out results with a score below the threshold
        return not templateResp.empty

    def detect_credit_screen(self, threshold: int = 200) -> bool:
        """ 
        Detects if the game is currently loading by analyzing the loading screen.
        
        Args:
            threshold (int): The threshold value to determine if the screen is mostly white.
        
        Returns:
            bool: True if the screen is mostly white (indicating loading), False otherwise.
        """
        img = np.array(self.screenshot().convert("L")) # convert to grayscale, and then to numpy array
        return np.mean(img) > threshold # if the mean is greater than 200, then the screen is mostly white
    
    def detect_move_forward(self, threshold: float = 0.8) -> bool:
        """Detects if the move forward button is currently being displayed.

        Returns:
            bool: True if the move forward button is detected, False otherwise.
        """
        templateResp = self.match_template([("move_forward", self.ASSETS_NUMPY['gakuen_move_forward'])], self.screenshot())
        templateResp = templateResp[templateResp["Score"] > threshold] 
        return not templateResp.empty

    def detect_setup_screen(self) -> bool:
        """Detects if the setup screen is currently being displayed.

        Returns:
            bool: True if the setup screen is detected, False otherwise.
        """
        return self.detect_screen(0)

    def detect_buttons(self, threshold: float = 0.8) -> pd.DataFrame:
        """
        Detects buttons in the screenshot and returns a DataFrame with the detected buttons and their scores.

        Args:
            threshold (float, optional): The minimum score threshold for considering a button as detected. Defaults to 0.8.

        Returns:
            pd.DataFrame: A DataFrame containing the detected buttons and their scores.
        """
        # detect consent, agree, and agree_all buttons
        templateResp = self.match_template([("consent", self.ASSETS_NUMPY['gakuen_consent']),
                                            ("agree", self.ASSETS_NUMPY['gakuen_agree']),
                                            ("agree_all", self.ASSETS_NUMPY['gakuen_agree_all']),
                                            ("move_forward", self.ASSETS_NUMPY['gakuen_move_forward'])], 
                                            self.screenshot().convert("L"))
        templateResp = templateResp[templateResp["Score"] > threshold]
        return templateResp

    def click_buttons(self, clickUntilNone: bool = False) -> None:
        """
        Clicks any of the buttons that are detected.

        Args:
            clickUntilNone (bool, optional): Specifies whether to keep clicking buttons until none are detected. 
                Defaults to False.

        Returns:
            None
        """
        # click any of the buttons that are detected
        templateResponse = self.detect_buttons()

        if clickUntilNone:
            while not templateResponse.empty:
                self.click_template(templateResponse)
                templateResponse = self.detect_buttons()
        else:
            if not templateResponse.empty:
                self.click_template(templateResponse)

    def wait_install(self, timeout:int = 300, delay:int = 1) -> bool:
        """ 
        Wait for the game to finish installing.

        Args:
            timeout (int): The maximum time to wait for the game to finish installing, in seconds. Default is 300 seconds.
            delay (int): The delay between each check for game installation, in seconds. Default is 1 second.

        Returns:
            bool: True if the game finishes installing within the specified timeout, False otherwise.
        """
        logging.info("Waiting for game to finish installing.")
        return self.wait_function(self.gakuen_installed, timeout=timeout, delay=delay, boolean=False)

    def wait_function(self, func: callable, exec_func: callable = None, 
                      timeout: int = 30, delay: int = 1, boolean:bool = True) -> bool:
        """ 
        Wait for the game to finish loading.

        Args:
            func (callable): A callable function that returns True if the game is still loading, and False otherwise.
            exec_func (callable): A callable function to execute while waiting for the game to finish loading. Default is None.
            timeout (int): The maximum time to wait for the game to finish loading, in seconds. Default is 30 seconds.
            delay (int): The delay between each check for game loading, in seconds. Default is 1 second.

        Returns:
            bool: True if the game finishes loading within the specified timeout, False otherwise.
        """
        start = time.time()
        logging.debug(f"Waiting for function {func.__name__} to return {boolean}. ")
        while func() == boolean:
            if time.time() - start > timeout:
                return False
            if exec_func is not None:
                exec_func()
            time.sleep(delay)
        return True
    
    def playstore_detect_install(self,) -> pd.DataFrame:
        """Detects if the install button is visible in the play store.
        Returns:
            pd.DataFrame: A DataFrame containing the match results.
        """
        return self.match_template([("button",  self.ASSETS_NUMPY["playstore_install"])], 
                                       self.screenshot())

    def playstore_install(self) -> None:
        """Clicks the install button in the playstore.

        This method detects the install button in the playstore and clicks it.
        If the install button is not found, an assertion error is raised.

        Returns:
            None
        """
        templateResults = self.playstore_detect_install()
        assert not templateResults.empty, "Could not find the install button."
        self.click_template(templateResults)
        
if __name__ == "__main__":

    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    logging.info("Starting GakenUpdater.")
    g = GakuenUpdater()
    g.start()