"""
================================================================================
CARA_B_main_trialwise.py — TRIAL-WISE (INTERMIXED) VERSION       [2026-10-23]
================================================================================
"""

import os
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"

from psychopy import visual, core, event, data, gui
import random
import math
import json
import re
import pathlib
from datetime import datetime
import numpy as np
import atexit
import sys
import hashlib
try:
    import serial  # for sending triggers via triggerbox (only needed in the EEG lab)
except ImportError:
    serial = None
import time

# ---------------------------------------------------------------------------
# THIS SECTION IS IRRELEVANT FOR YOU, DISREGARD!!
# ---------------------------------------------------------------------------
# INITIALIZE TRIGGERBOX (BrainProducts TriggerBox Plus)
USE_TRIGGERS = False  # Set to False to disable EEG triggers manually
TRIGGERBOX_BAUDRATE = 2_000_000  # Required by BrainProducts TriggerBox Plus

# Replace 'COM6' with the actual port found in Device Manager
try:
    if USE_TRIGGERS:
        if serial is None:
            raise ImportError("pyserial is not installed")
        port = serial.Serial('COM6', baudrate=TRIGGERBOX_BAUDRATE, timeout=1)
        time.sleep(0.5)  # Give the device time to initialise
        port.write(b'\x00')  # Ensure it starts at zero
        TRIGGERBOX_READY = True
    else:
        print("EEG triggers are DISABLED via USE_TRIGGERS flag.")
        TRIGGERBOX_READY = False
        port = None
except Exception as e:
    print(f"WARNING: Could not connect to TriggerBox Plus on COM6: {e}")
    print("Experiment will continue without EEG triggers.")
    TRIGGERBOX_READY = False
    port = None

def send_trigger(val):
    """Sends a trigger byte and resets it after a short delay."""
    if not TRIGGERBOX_READY or port is None:
        return
    try:
        port.write(bytes([val]))      # Set the trigger lines
        time.sleep(0.01)              # Wait 10ms (standard pulse width)
        port.write(b'\x00')           # Reset all lines to zero
    except Exception as e:
        print(f"Error sending trigger {val}: {e}")

# Trigger condition offset: maps condition key to numeric index
TRIGGER_COND_OFFSET = {'F': 1, 'M': 2, 'L': 3}

# ---------------------------------------------------------------------------

# ============================================================================
# PERLIN NOISE IMPLEMENTATION
# ============================================================================

class PerlinNoise:
    def __init__(self, seed=0):
        self.grad3 = [
            (1,1,0),(-1,1,0),(1,-1,0),(-1,-1,0),
            (1,0,1),(-1,0,1),(1,0,-1),(-1,0,-1),
            (0,1,1),(0,-1,1),(0,1,-1),(0,-1,-1)
        ]
        
        self.p = [
            151,160,137,91,90,15,
            131,13,201,95,96,53,194,233,7,225,140,36,103,30,69,142,8,99,37,240,21,10,23,
            190, 6,148,247,120,234,75,0,26,197,62,94,252,219,203,117,35,11,32,57,177,33,
            88,237,149,56,87,174,20,125,136,171,168, 68,175,74,165,71,134,139,48,27,166,
            77,146,158,231,83,111,229,122,60,211,133,230,220,105,92,41,55,46,245,40,244,
            102,143,54, 65,25,63,161, 1,216,80,73,209,76,132,187,208, 89,18,169,200,196,
            135,130,116,188,159,86,164,100,109,198,173,186, 3,64,52,217,226,250,124,123,
            5,202,38,147,118,126,255,82,85,212,207,206,59,227,47,16,58,17,182,189,28,42,
            223,183,170,213,119,248,152, 2,44,154,163, 70,221,153,101,155,167, 43,172,9,
            129,22,39,253, 19,98,108,110,79,113,224,232,178,185, 112,104,218,246,97,228,
            251,34,242,193,238,210,144,12,191,179,162,241, 81,51,145,235,249,14,239,107,
            49,192,214, 31,181,199,106,157,184, 84,204,176,115,121,50,45,127, 4,150,254,
            138,236,205,93,222,114,67,29,24,72,243,141,128,195,78,66,215,61,156,180
        ]
        
        self.perm = [0] * 512
        self.gradP = [None] * 512
        self.seed(seed)

    def seed(self, seed):
        if 0 < seed < 1:
            seed *= 65536
        seed = int(math.floor(seed))
        if seed < 256:
            seed |= seed << 8
            
        for i in range(256):
            if i & 1:
                v = self.p[i] ^ (seed & 255)
            else:
                v = self.p[i] ^ ((seed >> 8) & 255)
            
            self.perm[i] = self.perm[i + 256] = v
            self.gradP[i] = self.gradP[i + 256] = self.grad3[v % 12]

    def dot2(self, g, x, y):
        return g[0]*x + g[1]*y

    def fade(self, t):
        return t*t*t*(t*(t*6-15)+10)

    def lerp(self, a, b, t):
        return (1-t)*a + t*b

    def perlin2(self, x, y):
        X = int(math.floor(x))
        Y = int(math.floor(y))
        x = x - X
        y = y - Y
        X = X & 255
        Y = Y & 255
        
        n00 = self.dot2(self.gradP[X + self.perm[Y]], x, y)
        n01 = self.dot2(self.gradP[X + self.perm[Y + 1]], x, y - 1)
        n10 = self.dot2(self.gradP[X + 1 + self.perm[Y]], x - 1, y)
        n11 = self.dot2(self.gradP[X + 1 + self.perm[Y + 1]], x - 1, y - 1)
        
        u = self.fade(x)
        
        return self.lerp(
            self.lerp(n00, n10, u),
            self.lerp(n01, n11, u),
            self.fade(y)
        )


# ============================================================================
# ADAPTIVE CONTROL ALGORITHM (Agarwal et al.)
# ============================================================================

class AdaptiveControlAlgorithm:
    """
    Adaptive algorithm that adjusts control percentage based on performance.
    Adapts control levels to maintain target difficulty across participants.
    
    ADAPTATION FROM AGARWAL ET AL. (2019):
    
    The original paper adapts tolerance (permissible deviation) while keeping
    perturbation constant. This implementation adapts perturbation level (control)
    while targeting a fixed difficulty ratio.
    
    Key modifications:
    1. Adapts control level (0-1) rather than tolerance threshold
    2. Error based on path length ratio rather than deviation from tolerance
    3. Uses population SD for error normalization (σ from pilot data, N=10)
    4. Parameters optimised via grid search on pilot data (α, β, γ)
    
    Error calculation:
        Error = (current_ratio - target_ratio) / σ_population
    
    Where σ_population is the standard deviation of deviation ratios from
    pilot participants (N=10), making error scores interpretable as
    "number of SDs from target."
    """
    
    def __init__(self, 
                 initial_control=0.5,
                 target_ratio=1.75,
                 baseline_path_length=None,
                 gamma=0.1,
                 alpha=0.05,
                 beta=0.03,
                 n_trials_avg=3,
                 min_control=0.10,
                 max_control=0.80,
                 sigma_normalized=1.0):
        
        self.control = initial_control
        self.target_ratio = target_ratio
        self.baseline_path_length = baseline_path_length
        
        # Algorithm parameters
        self.gamma = gamma
        self.alpha = alpha
        self.beta = beta
        self.n_trials_avg = n_trials_avg
        self.min_control = min_control
        self.max_control = max_control
        self.sigma_normalized = sigma_normalized
        
        # History tracking
        self.path_length_history = []
        self.control_history = [initial_control]
        self.error_score_history = []
        
    def set_baseline_path_length(self, baseline_path_length):
        """Set the participant's baseline path length (from high control trials)."""
        self.baseline_path_length = baseline_path_length
        
    def calculate_trial_metric(self, value):
        """Convert trial metric to scalar (handles both single values and arrays)."""
        if isinstance(value, (int, float)):
            return float(value)
        return np.mean(value)
    
    def calculate_average_path_length(self):
        """Calculate moving average of last n trials."""
        if len(self.path_length_history) == 0:
            return 0.0
        
        n = min(self.n_trials_avg, len(self.path_length_history))
        recent_lengths = self.path_length_history[-n:]
        
        return np.mean(recent_lengths)
    
    def calculate_error_score(self, avg_path_length):
        """Calculate error score (Based on Path Length Ratio)."""
        if self.baseline_path_length is None or self.baseline_path_length == 0:
            raise ValueError("Baseline path length must be set before calculating error score!")
        
        current_ratio = avg_path_length / self.baseline_path_length
        error_score = (current_ratio - self.target_ratio) / self.sigma_normalized
        
        return error_score
    
    def update_control(self, error_score):
        """Update control percentage based on error score."""
        prev_error = self.error_score_history[-1] if len(self.error_score_history) > 0 else 0
        error_change = error_score - prev_error
        
        new_control = (1 - self.gamma) * self.control + \
                      self.alpha * error_score + \
                      self.beta * error_change
        
        new_control = np.clip(new_control, self.min_control, self.max_control)
        
        return new_control
    
    def process_trial(self, trial_path_length):
        """Process a completed trial and update control for next trial."""
        trial_len = self.calculate_trial_metric(trial_path_length)
        self.path_length_history.append(trial_len)
        
        avg_len = self.calculate_average_path_length()
        error_score = self.calculate_error_score(avg_len)
        self.error_score_history.append(error_score)
        
        new_control = self.update_control(error_score)
        self.control = new_control
        self.control_history.append(new_control)
        
        return {
            'new_control': new_control,
            'trial_path_length': trial_len,
            'avg_path_length': avg_len,
            'error_score': error_score,
            'current_ratio': avg_len / self.baseline_path_length if self.baseline_path_length else None,
            'deviation_from_target': avg_len - (self.target_ratio * self.baseline_path_length) if self.baseline_path_length else None
        }
    
    def has_converged(self, threshold=0.03, n_stable=3, ratio_tolerance=0.5):
        """Check if control has stabilized AND ratio is near target."""
        if len(self.control_history) < n_stable + 1:
            print("  Convergence: False (Not enough trials)")
            return False
        
        recent_controls = self.control_history[-(n_stable+1):]
        changes = [abs(recent_controls[i+1] - recent_controls[i]) 
                   for i in range(len(recent_controls)-1)]
        control_stable = all(change < threshold for change in changes)
        
        if len(self.path_length_history) < self.n_trials_avg:
            print(f"  Convergence: False (Control stable: {control_stable}, but not enough trials for ratio average)")
            return False
            
        recent_pls = self.path_length_history[-self.n_trials_avg:]
        avg_path_len = sum(recent_pls) / len(recent_pls)
        
        if self.baseline_path_length is None or self.baseline_path_length == 0:
            print(f"  Convergence: False (Control stable: {control_stable}, but no baseline)")
            return False
            
        avg_ratio = avg_path_len / self.baseline_path_length
        ratio_close = abs(avg_ratio - self.target_ratio) < ratio_tolerance
        
        if control_stable and ratio_close:
            print(f"  Convergence: True (Control stabilized and ratio {avg_ratio:.2f} is within {ratio_tolerance} of target {self.target_ratio})")
            return True
        elif control_stable and not ratio_close:
            print(f"  Convergence: False (Control stabilized but ratio {avg_ratio:.2f} is away from target {self.target_ratio}. Continuing trials...)")
            return False
        elif not control_stable and ratio_close:
            print(f"  Convergence: False (Ratio {avg_ratio:.2f} is near target {self.target_ratio}, but control has not stabilized yet)")
            return False
        else:
            print(f"  Convergence: False (Control has not stabilized and ratio {avg_ratio:.2f} is away from target {self.target_ratio})")
            return False
    
    def get_final_control(self, n_trials=5):
        """Get final converged control value."""
        if len(self.control_history) < 2:
            return self.control_history[0]
        
        recent = self.control_history[-n_trials:] if len(self.control_history) > n_trials else self.control_history[1:]
        return np.mean(recent)
    
    def get_summary(self):
        """Get summary statistics of calibration."""
        return {
            'final_control': self.get_final_control(),
            'n_trials': len(self.path_length_history),
            'converged': self.has_converged(),
            'final_path_length': self.path_length_history[-1] if self.path_length_history else None,
            'final_ratio': (self.path_length_history[-1] / self.baseline_path_length) 
                          if self.path_length_history and self.baseline_path_length else None,
            'target_ratio': self.target_ratio,
            'control_history': self.control_history.copy(),
            'path_length_history': self.path_length_history.copy(),
            'error_score_history': self.error_score_history.copy()
        }


# ============================================================================
# MODULE-LEVEL SETUP
# GUI dialog, check mode, data paths, ExperimentHandler, autosave,
# global trial counter, screenshot guard.
# ============================================================================

expName = "photo_task_agarwal"

expInfo = {
    "participant": "",
    "age":         "",
    "gender":      "",   # w / m / d / n
    "handedness":  "",   # r / l
    "check_mode":  False,
}
_dlg = gui.DlgFromDict(
    expInfo,
    order=["participant", "age", "gender", "handedness", "check_mode"],
    title=expName
)
if not _dlg.OK:
    core.quit()

CHECK_MODE = bool(expInfo.pop("check_mode"))

# ── File paths ─────────────────────────────────────────────────────────
_script_dir     = pathlib.Path(__file__).resolve().parent
# Trial-wise version: separate data folder so that data from the blocked
# version (CARA_B_main.py -> data/subjects) and this version never mix.
_DATA_DIR       = _script_dir / "trialwise_data"
SCREENSHOTS_DIR = _script_dir / "screenshots"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
SCREENSHOTS_DIR.mkdir(exist_ok=True)

_date      = datetime.now().strftime("%Y%m%d_%H%M%S")
_pid       = expInfo["participant"]
csv_path   = str(_DATA_DIR / f"{_pid}_{_date}.csv")
_json_path = str(_DATA_DIR / f"{_pid}_{_date}.json")

# ── PsychoPy ExperimentHandler (primary CSV output) ───────────────────────
thisExp = data.ExperimentHandler(
    name=expName, version='1.0',
    extraInfo=expInfo,
    dataFileName=str(_DATA_DIR / f"{_pid}_{_date}"),
    savePickle=False, saveWideText=True,
)

# ── Autosave / crash safety ────────────────────────────────────────────
_saved = False

def _save():
    """Save CSV + JSON; called on crash, escape, or normal exit."""
    global _saved
    if not _saved:
        if thisExp is not None:
            thisExp.saveAsWideText(csv_path)
            print("CSV saved →", csv_path)
        if experiment_data.get('participant_id'):
            save_experiment_data(_json_path)
        _saved = True

atexit.register(_save)

# ── Global trial counter ────────────────────────────────────────────────
global_trial_counter = 0

# ── Screenshot guard ────────────────────────────────────────────────────
_screenshots_saved = set()

if CHECK_MODE:
    print("=" * 60)
    print("** CHECK MODE — Minimal trial counts **")
    print("=" * 60)
else:
    print(f"Full experiment — participant: {_pid}")


# ============================================================================
# CONSTANTS
# ============================================================================

# Screen settings
BACKGROUND_COLOR = [0.569, 0.569, 0.569]

# ── Visual Angle / Stimulus Size Setup ───────────────────────────────────────
DIST_CM    = 90.0    # Distance from eyes to monitor
WIDTH_CM   = 53.0    # Physical width of the monitor
STIM_SZ_DEG = 2.0    # Desired visual angle size of the stimuli in degrees

def vis_ang_to_pix(deg, dist_cm, width_cm, win_width_pix):
    """
    Convert visual angle (degrees) to pixels based on monitor physics.
    Requires math.tan.
    """
    size_cm = 2 * dist_cm * math.tan(math.radians(deg) / 2)
    pix_per_cm = win_width_pix / width_cm
    return int(round(size_cm * pix_per_cm))

# SQUARE_SIZE and text scaling will be calculated dynamically based on window width in main()

# Sizes
FRAME_SIZE = 100
FRAME_THICKNESS = 3

# Noise parameters
NOISE_SCALE = 40.0
NOISE_SCALE_MULT = 10.0

# Colors (PsychoPy -1 to 1 scale)
FIXATION_COLOR = [-1, -1, -1]
TEXT_COLOR = "#616161"
WHITE = [1, 1, 1]
BLACK = [-1, -1, -1]

# Target ratios based on pilot deviation ratios (Path Length Ratio: Trial / Baseline)
# Source: pilot_mean_N10_report.md — mean deviation ratios at 60% and 20% control
TARGET_RATIO_MEDIUM = 1.62  # Pilot mean deviation ratio at 60% control (N=10)
TARGET_RATIO_LOW = 4.46     # Pilot mean deviation ratio at 20% control (N=10)

# Population standard deviations for error normalization
# Source: pilot_mean_N10_report.md — SD of deviation ratios
POPULATION_SD_RATIO_MEDIUM = 0.41    # SD of deviation ratio at 60% control (N=10)
POPULATION_SD_RATIO_LOW = 1.81       # SD of deviation ratio at 20% control (N=10)

# Baseline measurement
N_BASELINE_TRIALS = 2 if CHECK_MODE else 20
BASELINE_CONTROL = 1.0

# Agarwal Algorithm Parameters
# Optimised via grid search on pilot data (N=10)
# Source: parameter_optimization/top5_per_condition_summary.csv (rank 2)
INITIAL_CONTROL = 0.5
GAMMA = 0.03         # Slacking factor (optimised; original paper: 0.2)
ALPHA = 0.02         # Error term weight (optimised; original paper: 0.45)
BETA = 0.0487        # Error change weight (optimised; original paper: 0.24)
N_TRIALS_AVG = 5     # Moving average window (original paper: 8)
MAX_CALIBRATION_TRIALS = 5 if CHECK_MODE else 40
CONVERGENCE_THRESHOLD = 0.03
N_STABLE_TRIALS = 5

# Test phase
N_TEST_TRIALS_PER_CONDITION = 10 if CHECK_MODE else 60  # trials per difficulty condition
# Trial-wise version: miniblock size must be divisible by 3 (one third per
# condition). 18 = 6 F + 6 M + 6 L  -> 60 / 6 = 10 miniblocks.
# Check mode: 6 = 2 F + 2 M + 2 L   -> 10 / 2 = 5 miniblocks.
TRIALS_PER_MINIBLOCK = 6 if CHECK_MODE else 18           # trials per mini-block
# Pseudo-randomization constraint: at most this many consecutive trials of
# the same condition (applied across the whole test phase).
MAX_SAME_CONDITION_RUN = 3

# Stimulus folder must sit next to this script (relative path -> works on any computer)
STIMULI_DIR = _script_dir / "chosen_stimuli_nolures"
IMAGE_SEED  = 42  # Fixed seed — all participants get the same image set

# Check stimuli at startup (otherwise the error would only appear AFTER calibration)
_n_stim_needed = 2 * 3 * N_TEST_TRIALS_PER_CONDITION  # test images + equal number of foils
_n_stim_found  = len(list(STIMULI_DIR.glob("*.jpg"))) if STIMULI_DIR.is_dir() else 0
if _n_stim_found < _n_stim_needed:
    raise FileNotFoundError(
        f"Need {_n_stim_needed} .jpg images in '{STIMULI_DIR}', found {_n_stim_found}. "
        f"Make sure the 'chosen_stimuli_nolures' folder is in the same folder as this script."
    )

def sample_images(n_test, n_foils, seed):
    """Sample images for test and recognition phases from a flat stimulus pool.

    Parameters
    ---------
    n_test : int
        Number of images needed for the test phase.
    n_foils : int
        Number of *new* (unseen) images needed as foils in the recognition phase.
    seed : int
        Seed for reproducible, participant-specific sampling.

    Returns
    -------
    test_images : list[str]
        Paths of images shown during the test phase.
    foil_images : list[str]
        Paths of unseen images used as "new" items in recognition.
    """
    all_jpgs = sorted(STIMULI_DIR.glob("*.jpg"))
    total_needed = n_test + n_foils

    if len(all_jpgs) < total_needed:
        raise ValueError(
            f"Not enough stimuli: need {total_needed} ({n_test} test + {n_foils} foils) "
            f"but only {len(all_jpgs)} images found in {STIMULI_DIR}"
        )

    rng_img = random.Random(seed)  # Isolated RNG for reproducible sampling
    sampled = rng_img.sample([str(p) for p in all_jpgs], total_needed)

    test_images = sampled[:n_test]
    foil_images = sampled[n_test:]
    return test_images, foil_images


# ============================================================================
# GLOBAL DATA STORAGE
# ============================================================================

experiment_data = {
    'participant_id': None,
    'age': None,
    'gender': None,
    'handedness': None,
    'timestamp': None,
    'calibration': {
        'baseline': {
            'trials': [],
            'mean_deviation': None,
            'mean_path_length': None,
            'control_level': BASELINE_CONTROL
        },
        'medium_difficulty': {
            'trials': [],
            'final_control': None,
            'converged': None,
            'n_trials': None,
            'algorithm_summary': None
        },
        'low_difficulty': {
            'trials': [],
            'final_control': None,
            'converged': None,
            'n_trials': None,
            'algorithm_summary': None
        }
    },
    'test': {
        'control_levels': {'medium': 0.0, 'low': 0.0},
        'trials': []
    },
    'recognition': {
        'trials': []
    }
}

# Tracks which control condition each test image was shown under.
# Populated during test phase, read during recognition phase for triggers.
# Key: image path (str), Value: condition key ('F', 'M', or 'L')
image_condition_map = {}


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def apply_boundary_constraints(x, y, frame_size, screen_w, screen_h):
    """Ensure the frame stays within screen bounds (PsychoPy center origin)."""
    half_frame = frame_size // 2
    half_width = screen_w // 2
    half_height = screen_h // 2
    
    x = max(-half_width + half_frame, min(half_width - half_frame, x))
    y = max(-half_height + half_frame, min(half_height - half_frame, y))
    return x, y


def calculate_deviation(trajectory, start_pos, target_pos):
    """Calculate mean Euclidean deviation from ideal straight line."""
    if len(trajectory) == 0:
        return 0.0
    
    total_duration = trajectory[-1][2]
    
    deviations = []
    for (x, y, t) in trajectory:
        progress = t / total_duration if total_duration > 0 else 0
        ideal_x = start_pos[0] + progress * (target_pos[0] - start_pos[0])
        ideal_y = start_pos[1] + progress * (target_pos[1] - start_pos[1])
        
        deviation = math.sqrt((x - ideal_x)**2 + (y - ideal_y)**2)
        deviations.append(deviation)
    
    return np.mean(deviations) if deviations else 0.0


def calculate_path_length(trajectory):
    """Calculate total path length of a trajectory."""
    if len(trajectory) < 2:
        return 0.0
    
    path_length = 0.0
    for i in range(len(trajectory) - 1):
        x1, y1 = trajectory[i][0], trajectory[i][1]
        x2, y2 = trajectory[i+1][0], trajectory[i+1][1]
        path_length += math.sqrt((x2 - x1)**2 + (y2 - y1)**2)
        
    return path_length


def save_experiment_data(filename=None):
    """Save experiment data to JSON file."""
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        participant_id = experiment_data.get('participant_id', 'unknown')
        filename = f"data_{participant_id}_{timestamp}.json"
    
    class NumpyEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, np.integer):
                return int(obj)
            if isinstance(obj, np.floating):
                return float(obj)
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            return super(NumpyEncoder, self).default(obj)
            
    with open(filename, 'w') as f:
        json.dump(experiment_data, f, indent=2, cls=NumpyEncoder)
    
    print(f"Data saved to: {filename}")
    return filename


# ============================================================================
# EXPERIMENT PHASES
# ============================================================================

def show_instructions(win, screen_width, screen_height, phase='calibration'):
    """Show instruction screen."""
    n_total_trials = N_TEST_TRIALS_PER_CONDITION * 3
    n_blocks       = n_total_trials // TRIALS_PER_MINIBLOCK
    
    if phase == 'calibration':
        lines = [
            "Dear participant, welcome to the photoshoot study!",
            "",
            f"This task involves moving a white rectangle (\"your phone's screen\") over an object on the screen, and taking its picture by pressing a button. After a short practice, the main experiment consists of {n_blocks} blocks with {TRIALS_PER_MINIBLOCK} trials each.",
            "",
            "In each trial, you will see a black rectangle on the screen.",
            "You will use the mouse to move the white rectangle (your \"phone screen\") over the object, to frame it. After you fully frame the rectangle, you need to press SPACE to take a picture. Once you've pressed SPACE, the black rectangle will go away, revealing the object you took a picture of.",
            "",
            "Please keep in mind that in some trials, it will be harder to control the movement of the white frame. This is intended. Accordingly, after each trial, you will be asked to indicate your feeling of control over the movement of the frame (on a scale of 1 to 7, where 1 is no control and 7 is full control). Please answer by using the LEFT and RIGHT arrow keys to move the slider, and press SPACE to confirm.",
            "",
            "While you use the mouse to move the white frame, please make continuous movements. Please do not lift the mouse, or do small strokes.",
            "",
            "Please feel free to ask any questions to the experimenter now.",
            "",
            "Before the main experiment, you will practice the task to familiarize yourself with the movement of the frame.  Here, you won't be able to see the pictures you took, so you will only see the black rectangle, and your frame.",
            "",
            "Please press SPACE to start the practice block."
        ]
    else:  # test phase
        lines = [
            "=== MAIN EXPERIMENT ===",
            "",
            f"You will now complete {n_blocks} blocks with {TRIALS_PER_MINIBLOCK} trials each ({n_total_trials} trials in total).",
            "Trials with full, medium and low control are intermixed.",
            "",
            "Move the frame to encapsulate the target square.",
            "Press SPACEBAR when done with each trial.",
            "",
            "Press SPACEBAR to begin"
        ]
    
    text_str = '\n'.join(lines)
    instruction_text = visual.TextStim(
        win=win,
        text=text_str,
        color=TEXT_COLOR,
        height=SCALED_TEXT_HEIGHT,
        pos=(0, 0),
        wrapWidth=SCALED_WRAP_WIDTH,
        bold=True
    )
    
    instruction_text.draw()
    win.flip()
    
    keys = event.waitKeys(keyList=['space', 'escape'])
    
    if 'escape' in keys:
        return False
    
    return True


def show_calibration_results(win, screen_width, screen_height):
    """Show end of practice message. Calibration results are logged internally."""
    
    lines = [
        "Well done - the practice block is now complete!",
        "",
        "You will now start with the main experiment.",
        "Use the mouse to move your frame over the black square. Once you've framed the square, press SPACE to take a picture, and reveal the object of which you took a picture.",
        "After each trial, rate your feeling of control over the frame's movement on a scale of 1 to 7 (1 = no control, 7 = full control) by using the LEFT and RIGHT arrow keys to move the slider, and press SPACE to confirm.",
        "",
        "Please press SPACE to start."
    ]
    
    text_str = '\n'.join(lines)
    results_text = visual.TextStim(
        win=win,
        text=text_str,
        color=TEXT_COLOR,
        height=SCALED_TEXT_HEIGHT,
        pos=(0, 0),
        wrapWidth=SCALED_WRAP_WIDTH,
        bold=True
    )
    
    results_text.draw()
    win.flip()
    
    keys = event.waitKeys(keyList=['space', 'escape'])
    
    if 'escape' in keys:
        return False
    
    return True


def run_trial(win, mouse, clock, screen_width, screen_height,
              start_pos, target_pos, control_level, trial_label,
              trial_number, total_trials, image_path=None, phase_name=None,
              condition_key=None):
    """Run a single trial. Returns trial_data dict or None if quit."""
    
    # Use deterministic seed based on trial number (matching photo_task_2.py)
    # This ensures consistency across participants
    perlin = PerlinNoise(seed=trial_number - 1)
    
    # Create visual stimuli
    target_square = visual.Rect(win=win, width=SQUARE_SIZE, height=SQUARE_SIZE, 
                                fillColor=BLACK, lineColor=None, pos=target_pos)
    
    target_image = None
    if image_path:
        # Load the image and scale it to fit precisely within the target square area
        target_image = visual.ImageStim(win=win, image=image_path, pos=target_pos, size=(SQUARE_SIZE, SQUARE_SIZE))
        
    frame = visual.Rect(win=win, width=FRAME_SIZE, height=FRAME_SIZE, fillColor=None,
                       lineColor=WHITE, lineWidth=FRAME_THICKNESS, pos=start_pos)
    fixation_h = visual.Rect(win=win, width=40, height=6, fillColor=FIXATION_COLOR, pos=(0, 0))
    fixation_v = visual.Rect(win=win, width=6, height=40, fillColor=FIXATION_COLOR, pos=(0, 0))
    
    # ── FIXATION (timed, 0.5–0.8 s random, matching CDmem_1.py patterns) ─────
    fix_dur = float(rng.uniform(0.5, 0.8))
    fixation_h.draw()
    fixation_v.draw()
    win.flip()

    # ── EEG Trigger: Fixation Onset ─────────────────────────────────────────
    trigger_fix = np.nan
    if phase_name == 'test' and condition_key:
        trigger_fix = 70 + TRIGGER_COND_OFFSET.get(condition_key, 0)
        send_trigger(trigger_fix)

    core.wait(fix_dur)

    # ── TRIAL STARTS IMMEDIATELY after fixation ───────────────────────────────
    # Frame is placed at start_pos; participant moves it with the mouse.
    # SPACE is only used to SUBMIT once the frame is over the target.
    frame_x = float(start_pos[0])
    frame_y = float(start_pos[1])
    noise_t = 0.0
    mouse.setPos((frame_x, frame_y))
    prev_mouse_x, prev_mouse_y = mouse.getPos()
    trajectory = []
    event.clearEvents(eventType='keyboard')
    clock.reset()
    start_time = clock.getTime()

    # ── EEG trigger tracking variables ──────────────────────────────────────
    _first_move_triggered = False
    _first_move_time = np.nan
    trigger_trial_onset = np.nan
    trigger_first_move = np.nan
    trigger_shutter = np.nan
    trigger_reveal_onset = np.nan
    trigger_reveal_offset = np.nan
    trigger_agency = np.nan

    running = True
    frame_counter = 0

    # ── Draw initial trial display (target + frame at start position) ─────
    target_square.draw()
    frame.pos = (frame_x, frame_y)
    frame.draw()
    win.flip()

    # ── EEG Trigger: Trial Onset (frame + target appear on screen) ────────
    if phase_name == 'test' and condition_key:
        trigger_trial_onset = 90 + TRIGGER_COND_OFFSET.get(condition_key, 0)
        send_trigger(trigger_trial_onset)

    while running:
        keys = event.getKeys(keyList=['escape', 'space'])

        for key in keys:
            if key == 'escape':
                return None
            elif key == 'space':
                # --- Framing containment check ---
                half_frame  = FRAME_SIZE  / 2.0
                half_square = SQUARE_SIZE / 2.0
                tx, ty = float(target_pos[0]), float(target_pos[1])
                framed = (
                    frame_x - half_frame <= tx - half_square and
                    frame_x + half_frame >= tx + half_square and
                    frame_y - half_frame <= ty - half_square and
                    frame_y + half_frame >= ty + half_square
                )
                if not framed:
                    continue

                end_time = clock.getTime()
                duration = end_time - start_time

                # ── EEG Trigger: Shutter Press ──────────────────────────────
                if phase_name == 'test' and condition_key:
                    trigger_shutter = 20 + TRIGGER_COND_OFFSET.get(condition_key, 0)
                    send_trigger(trigger_shutter)

                # --- Shutter flash: frame briefly expands (~100 ms) ---
                flash_frame = visual.Rect(
                    win=win,
                    width=FRAME_SIZE + 16, height=FRAME_SIZE + 16,
                    fillColor=None,
                    lineColor=WHITE, lineWidth=FRAME_THICKNESS + 3,
                    pos=(frame_x, frame_y)
                )
                target_square.draw()
                flash_frame.draw()
                win.flip()
                core.wait(0.05)
                
                # --- Target square only, visible for 1 s before image reveal ---
                target_square.draw()
                win.flip()
                core.wait(1.0)

                # ── FEEDBACK: REVEAL TARGET FOR 2 SECONDS ────────────────
                if target_image:
                    target_image.draw()
                else:
                    target_square.draw()
                win.flip()

                # ── EEG Trigger: Image Reveal Onset ─────────────────────────
                if phase_name == 'test' and condition_key:
                    trigger_reveal_onset = 30 + TRIGGER_COND_OFFSET.get(condition_key, 0)
                    send_trigger(trigger_reveal_onset)

                if phase_name == 'test' and 'test_revealed' not in _screenshots_saved:
                    win.getMovieFrame(buffer='front')
                    win.saveMovieFrames(str(SCREENSHOTS_DIR / "screenshot_test_revealed.png"))
                    _screenshots_saved.add('test_revealed')

                if phase_name != 'calibration':
                    core.wait(2.0)

                # ── EEG Trigger: Image Reveal Offset ────────────────────────
                if phase_name == 'test' and condition_key:
                    trigger_reveal_offset = 40 + TRIGGER_COND_OFFSET.get(condition_key, 0)
                    send_trigger(trigger_reveal_offset)


                # ── AGENCY RATING ─────────────────────────────────────────
                rating = np.nan
                
                if phase_name == 'test':
                    # ── EEG Trigger: Agency Rating Onset ────────────────────────
                    trigger_agency = 45
                    send_trigger(trigger_agency)
    
                    event.clearEvents(eventType='keyboard')
                    rating_msg = visual.TextStim(
                        win=win,
                        text="How much control did you feel over the frame's movement?",
                        color=TEXT_COLOR,
                        height=SCALED_TEXT_HEIGHT,
                        pos=(0, 100),
                        wrapWidth=SCALED_WRAP_WIDTH,
                        bold=True
                    )
                    
                    # Dynamic scaling for the rating scale
                    scale_width = SCALED_WRAP_WIDTH
                    spacing = scale_width / 6
                    start_x = -(scale_width / 2)
                    
                    # We draw a line above the text, so the text sits below the line
                    line_y = -100
                    text_y = line_y - SCALED_TEXT_HEIGHT * 1.5
                    
                    scale_positions = [(start_x + i * spacing, text_y) for i in range(7)]
                    scale_labels = ["1\nNo control", "2", "3", "4",
                                    "5", "6", "7\nFull control"]
                    
                    # The horizontal axis line
                    scale_line = visual.Line(
                        win, start=(start_x, line_y), end=(-start_x, line_y),
                        lineColor=TEXT_COLOR, lineWidth=5
                    )
                    
                    # Tick marks for each point
                    tick_half_height = SCALED_TEXT_HEIGHT * 0.3
                    scale_ticks = [
                        visual.Line(win, start=(x, line_y + tick_half_height), end=(x, line_y - tick_half_height),
                                    lineColor=TEXT_COLOR, lineWidth=5)
                        for x, _ in scale_positions
                    ]
                    
                    scale_stimuli = [
                        visual.TextStim(win, text=label, pos=pos, height=SCALED_TEXT_HEIGHT,
                                        color=TEXT_COLOR, alignText='center', bold=True)
                        for pos, label in zip(scale_positions, scale_labels)
                    ]
                    
                    # --- NEW CONTINUOUS SLIDER LOGIC ---
                    marker = visual.Rect(
                        win, width=15, height=45, pos=(0, line_y), 
                        fillColor='white', lineColor='black', lineWidth=2
                    )
                    
                    rating_val = 4.0
                    step_size = 0.05
                    rating = None
                    
                    from psychopy.hardware import keyboard
                    kb = keyboard.Keyboard()
                    
                    while rating is None:
                        percentage = (rating_val - 1.0) / 6.0
                        current_x = start_x + percentage * scale_width
                        marker.pos = (current_x, line_y)
                        
                        rating_msg.draw()
                        scale_line.draw()
                        for tick in scale_ticks:
                            tick.draw()
                        for stim in scale_stimuli:
                            stim.draw()
                        marker.draw()
                        win.flip()
                        
                        keys = kb.getKeys(['left', 'right', 'space', 'escape'], waitRelease=False, clear=False)
                        
                        if any(k.name == 'escape' for k in keys):
                            return None
                            
                        if any(k.name == 'space' and k.duration is None for k in keys):
                            
                            rating_msg.draw()
                            scale_line.draw()
                            for tick in scale_ticks:
                                tick.draw()
                            for stim in scale_stimuli:
                                stim.draw()
                            marker.draw()
                            win.flip()
                            
                            core.wait(1.0)
                            rating = round(rating_val, 2)
                            break
                            
                        if any(k.name == 'left' and k.duration is None for k in keys):
                            rating_val = max(1.0, rating_val - step_size)
                            
                        if any(k.name == 'right' and k.duration is None for k in keys):
                            rating_val = min(7.0, rating_val + step_size)

                # Compute trajectory metrics
                mean_deviation = calculate_deviation(trajectory, start_pos, target_pos)
                path_length    = calculate_path_length(trajectory)

                trial_data = {
                    'control_level':  control_level,
                    'control_rating': rating,
                    'image_shown':    image_path if image_path else None,
                    'label':          trial_label,
                    'trajectory':     trajectory,
                    'duration':       duration,
                    'mean_deviation': mean_deviation,
                    'path_length':    path_length,
                    'image_id':       pathlib.Path(image_path).stem if image_path else None,
                    'first_move_time': _first_move_time,
                    'movement_duration': duration - _first_move_time if not np.isnan(_first_move_time) else np.nan,
                    'start_time':     start_time,
                    'end_time':       end_time,
                    'trigger_fix':            trigger_fix,
                    'trigger_trial_onset':    trigger_trial_onset,
                    'trigger_first_move':     trigger_first_move,
                    'trigger_shutter':        trigger_shutter,
                    'trigger_reveal_onset':   trigger_reveal_onset,
                    'trigger_reveal_offset':  trigger_reveal_offset,
                    'trigger_agency':         trigger_agency,
                }
                return trial_data

        # ── Mouse movement & Perlin noise ─────────────────────────────────
        mouse_x, mouse_y = mouse.getPos()
        mouse_dx = mouse_x - prev_mouse_x
        mouse_dy = mouse_y - prev_mouse_y

        if mouse_dx != 0 or mouse_dy != 0:
            # Record first movement time (for movement_duration)
            if np.isnan(_first_move_time):
                _first_move_time = clock.getTime() - start_time
            # ── EEG Trigger: First Mouse Movement ───────────────────────
            if not _first_move_triggered and phase_name == 'test' and condition_key:
                trigger_first_move = 10 + TRIGGER_COND_OFFSET.get(condition_key, 0)
                send_trigger(trigger_first_move)
                _first_move_triggered = True

            noise_t += 0.05
            noise_val_x = perlin.perlin2(noise_t, 0)
            noise_val_y = perlin.perlin2(noise_t, 100)
            perturbed_dx = mouse_dx + (1 - control_level) * noise_val_x * NOISE_SCALE
            perturbed_dy = mouse_dy + (1 - control_level) * noise_val_y * NOISE_SCALE
            frame_x += perturbed_dx
            frame_y += perturbed_dy
            frame_x, frame_y = apply_boundary_constraints(
                frame_x, frame_y, FRAME_SIZE, screen_width, screen_height
            )
            current_time = clock.getTime() - start_time
            trajectory.append((frame_x, frame_y, current_time))

        prev_mouse_x = mouse_x
        prev_mouse_y = mouse_y

        # ── Rendering ─────────────────────────────────────────────────────
        frame.pos = (frame_x, frame_y)
        target_square.draw()
        frame.draw()
        win.flip()

        frame_counter += 1
        if phase_name and phase_name not in _screenshots_saved and frame_counter == 5:
            win.getMovieFrame(buffer='front')
            win.saveMovieFrames(str(SCREENSHOTS_DIR / f"screenshot_{phase_name}.png"))
            _screenshots_saved.add(phase_name)

    return None


def run_baseline_trials(win, mouse, clock, screen_width, screen_height, start_pos, target_pos):
    global global_trial_counter
    print("\nMeasuring BASELINE performance...")
    baseline_deviations = []
    baseline_path_lengths = []



    for trial_num in range(1, N_BASELINE_TRIALS + 1):
        global_trial_counter += 1
        trial_data = run_trial(
            win, mouse, clock, screen_width, screen_height,
            start_pos, target_pos,
            BASELINE_CONTROL,
            f"Baseline ({BASELINE_CONTROL*100:.0f}% control)",
            trial_num,
            N_BASELINE_TRIALS,
            phase_name='baseline'
        )

        if trial_data is None:
            return None

        experiment_data['calibration']['baseline']['trials'].append(trial_data)
        baseline_deviations.append(trial_data['mean_deviation'])
        baseline_path_lengths.append(trial_data['path_length'])

        # Log to CSV
        thisExp.addData('trial_num',          global_trial_counter)
        thisExp.addData('participant',        expInfo['participant'])
        thisExp.addData('phase',              'baseline')
        thisExp.addData('trial_within_phase', trial_num)
        thisExp.addData('control_level',      BASELINE_CONTROL)
        thisExp.addData('duration',           trial_data['duration'])
        thisExp.addData('path_length',        trial_data['path_length'])
        thisExp.addData('mean_deviation',     trial_data['mean_deviation'])
        thisExp.addData('control_rating',     trial_data.get('control_rating', np.nan))
        thisExp.nextEntry()

        print(f"  Baseline trial {trial_num}: Path Length={trial_data['path_length']:.1f} px")

    baseline_deviation   = np.mean(baseline_deviations)
    baseline_path_length = np.mean(baseline_path_lengths)

    experiment_data['calibration']['baseline']['mean_deviation']   = baseline_deviation
    experiment_data['calibration']['baseline']['mean_path_length'] = baseline_path_length

    print(f"\nBaseline Path Length: {baseline_path_length:.1f} px\n")
    return baseline_path_length


def run_calibration_phase(win, mouse, clock, screen_width, screen_height, start_pos, target_pos):
    global global_trial_counter



    # Step 1: Run baseline trials
    baseline_path_length = run_baseline_trials(
        win, mouse, clock, screen_width, screen_height, start_pos, target_pos
    )
    if baseline_path_length is None:
        return False

    # Step 2: Initialize adaptive algorithms
    # Both algorithms share the same α, β, γ, and INITIAL_CONTROL.
    # They differ only in target_ratio and sigma_normalized, because
    # medium and low difficulty have different population means and SDs.
    algo_medium = AdaptiveControlAlgorithm(
        initial_control=INITIAL_CONTROL,
        target_ratio=TARGET_RATIO_MEDIUM,
        baseline_path_length=baseline_path_length,
        gamma=GAMMA, alpha=ALPHA, beta=BETA, n_trials_avg=N_TRIALS_AVG,
        sigma_normalized=POPULATION_SD_RATIO_MEDIUM
    )
    algo_low = AdaptiveControlAlgorithm(
        initial_control=INITIAL_CONTROL,
        target_ratio=TARGET_RATIO_LOW,
        baseline_path_length=baseline_path_length,
        gamma=GAMMA, alpha=ALPHA, beta=BETA, n_trials_avg=N_TRIALS_AVG,
        sigma_normalized=POPULATION_SD_RATIO_LOW
    )

    # Step 3: Calibrate medium difficulty
    print(f"\nCalibrating MEDIUM difficulty (target: {TARGET_RATIO_MEDIUM}x baseline)...")
    for trial_num in range(1, MAX_CALIBRATION_TRIALS + 1):
        global_trial_counter += 1
        control = algo_medium.control
        trial_data = run_trial(
            win, mouse, clock, screen_width, screen_height, start_pos, target_pos,
            control, f"Calibration: Medium ({control*100:.1f}%)",
            trial_num, MAX_CALIBRATION_TRIALS, phase_name='calibration'
        )
        if trial_data is None:
            return False
        result = algo_medium.process_trial(trial_data['path_length'])
        trial_data['algorithm_result'] = result
        experiment_data['calibration']['medium_difficulty']['trials'].append(trial_data)

        thisExp.addData('trial_num',          global_trial_counter)
        thisExp.addData('participant',        expInfo['participant'])
        thisExp.addData('phase',              'calibration_medium')
        thisExp.addData('trial_within_phase', trial_num)
        thisExp.addData('control_level',      control)
        thisExp.addData('duration',           trial_data['duration'])
        thisExp.addData('path_length',        trial_data['path_length'])
        thisExp.addData('mean_deviation',     trial_data['mean_deviation'])
        thisExp.addData('control_rating',     trial_data.get('control_rating', np.nan))
        thisExp.addData('algo_new_control',   result['new_control'])
        thisExp.addData('algo_error_score',   result['error_score'])
        thisExp.addData('algo_ratio',         result['current_ratio'])
        thisExp.nextEntry()

        print(f"  Trial {trial_num}: Control={control*100:.1f}%, "
              f"PathLen={trial_data['path_length']:.1f}px, "
              f"Ratio={result['current_ratio']:.2f}x, "
              f"Next={result['new_control']*100:.1f}%")
        if algo_medium.has_converged(CONVERGENCE_THRESHOLD, N_STABLE_TRIALS, ratio_tolerance=0.5):
            print(f"  Calibrated successfully after {trial_num} trials!")
            break

    # Step 4: Calibrate low difficulty
    print(f"\nCalibrating LOW difficulty (target: {TARGET_RATIO_LOW}x baseline)...")
    for trial_num in range(1, MAX_CALIBRATION_TRIALS + 1):
        global_trial_counter += 1
        control = algo_low.control
        trial_data = run_trial(
            win, mouse, clock, screen_width, screen_height, start_pos, target_pos,
            control, f"Calibration: Low ({control*100:.1f}%)",
            trial_num, MAX_CALIBRATION_TRIALS, phase_name='calibration'
        )
        if trial_data is None:
            return False
        result = algo_low.process_trial(trial_data['path_length'])
        trial_data['algorithm_result'] = result
        experiment_data['calibration']['low_difficulty']['trials'].append(trial_data)

        thisExp.addData('trial_num',          global_trial_counter)
        thisExp.addData('participant',        expInfo['participant'])
        thisExp.addData('phase',              'calibration_low')
        thisExp.addData('trial_within_phase', trial_num)
        thisExp.addData('control_level',      control)
        thisExp.addData('duration',           trial_data['duration'])
        thisExp.addData('path_length',        trial_data['path_length'])
        thisExp.addData('mean_deviation',     trial_data['mean_deviation'])
        thisExp.addData('control_rating',     trial_data.get('control_rating', np.nan))
        thisExp.addData('algo_new_control',   result['new_control'])
        thisExp.addData('algo_error_score',   result['error_score'])
        thisExp.addData('algo_ratio',         result['current_ratio'])
        thisExp.nextEntry()

        print(f"  Trial {trial_num}: Control={control*100:.1f}%, "
              f"PathLen={trial_data['path_length']:.1f}px, "
              f"Ratio={result['current_ratio']:.2f}x, "
              f"Next={result['new_control']*100:.1f}%")
        if algo_low.has_converged(CONVERGENCE_THRESHOLD, N_STABLE_TRIALS, ratio_tolerance=0.5):
            print(f"  Calibrated successfully after {trial_num} trials!")
            break

    experiment_data['calibration']['medium_difficulty']['algorithm_summary'] = algo_medium.get_summary()
    experiment_data['calibration']['low_difficulty']['algorithm_summary']    = algo_low.get_summary()
    return True


def extract_calibration_results():
    """Extract final control levels from adaptive calibration."""
    
    control_medium = experiment_data['calibration']['medium_difficulty']['algorithm_summary']['final_control']
    control_low = experiment_data['calibration']['low_difficulty']['algorithm_summary']['final_control']
    
    experiment_data['calibration']['medium_difficulty']['final_control'] = control_medium
    experiment_data['calibration']['medium_difficulty']['converged'] = experiment_data['calibration']['medium_difficulty']['algorithm_summary']['converged']
    experiment_data['calibration']['medium_difficulty']['n_trials'] = experiment_data['calibration']['medium_difficulty']['algorithm_summary']['n_trials']
    
    experiment_data['calibration']['low_difficulty']['final_control'] = control_low
    experiment_data['calibration']['low_difficulty']['converged'] = experiment_data['calibration']['low_difficulty']['algorithm_summary']['converged']
    experiment_data['calibration']['low_difficulty']['n_trials'] = experiment_data['calibration']['low_difficulty']['algorithm_summary']['n_trials']
    
    experiment_data['test']['control_levels']['medium'] = control_medium
    experiment_data['test']['control_levels']['low'] = control_low
    
    
    # Save the calibration results straight to the experiment_data dict
    # so they are saved correctly by JSON
    experiment_data['n_trials_medium'] = experiment_data['calibration']['medium_difficulty']['n_trials']
    experiment_data['control_medium'] = experiment_data['calibration']['medium_difficulty']['final_control']
    experiment_data['converged_medium'] = experiment_data['calibration']['medium_difficulty']['converged']
    
    experiment_data['n_trials_low'] = experiment_data['calibration']['low_difficulty']['n_trials']
    experiment_data['control_low'] = experiment_data['calibration']['low_difficulty']['final_control']
    experiment_data['converged_low'] = experiment_data['calibration']['low_difficulty']['converged']
    
    print(f"\nCalibration Results:")
    print(f"  Medium difficulty:")
    print(f"    Final control: {control_medium*100:.1f}%")
    print(f"    Trials: {experiment_data['calibration']['medium_difficulty']['n_trials']}")
    print(f"    Converged: {experiment_data['calibration']['medium_difficulty']['converged']}")
    print(f"  Low difficulty:")
    print(f"    Final control: {control_low*100:.1f}%")
    print(f"    Trials: {experiment_data['calibration']['low_difficulty']['n_trials']}")
    print(f"    Converged: {experiment_data['calibration']['low_difficulty']['converged']}")


def _longest_run(seq):
    """Length of the longest run of identical consecutive elements."""
    longest = current = 0
    prev = None
    for x in seq:
        current = current + 1 if x == prev else 1
        longest = max(longest, current)
        prev = x
    return longest


def make_trialwise_sequence(n_per_condition, trials_per_block, seed, max_run,
                            conditions=('F', 'M', 'L'), max_attempts=10000):
    """
    Build the pseudo-randomized, trial-wise condition order for the test phase.

    * Every miniblock contains trials_per_block / 3 trials of each condition
      (full version: 6 F + 6 M + 6 L = 18; check mode: 2 + 2 + 2 = 6).
    * Number of miniblocks = n_per_condition / (trials_per_block / 3)
      (full version: 60 / 6 = 10; check mode: 10 / 2 = 5).
    * Constraint: no more than `max_run` consecutive trials of the same
      condition, checked over the WHOLE sequence, i.e. also across the
      boundary between two miniblocks (otherwise e.g. L-L-L at the end of
      one block + L-L at the start of the next = 5 Low trials in a row).
    * Method: each miniblock is shuffled; if the shuffle (together with the
      end of the previous miniblock) violates the constraint, it is
      reshuffled (rejection sampling). With 3 conditions a valid order is
      found within a few attempts.
    * `seed` makes the order reproducible for a given participant.

    Returns a list of miniblocks, each a list of condition keys.
    """
    if trials_per_block % len(conditions) != 0:
        raise ValueError(f"TRIALS_PER_MINIBLOCK ({trials_per_block}) must be divisible "
                         f"by the number of conditions ({len(conditions)}).")
    per_block = trials_per_block // len(conditions)
    if n_per_condition % per_block != 0:
        raise ValueError(f"N_TEST_TRIALS_PER_CONDITION ({n_per_condition}) must be divisible "
                         f"by trials per condition per miniblock ({per_block}).")
    n_blocks = n_per_condition // per_block

    rng_order = random.Random(seed)
    blocks, full_sequence = [], []
    for _ in range(n_blocks):
        for _attempt in range(max_attempts):
            block = [c for c in conditions for _ in range(per_block)]
            rng_order.shuffle(block)
            # check the new block together with the last trials of the
            # previous block (cross-boundary runs)
            if _longest_run(full_sequence[-max_run:] + block) <= max_run:
                break
        else:
            raise RuntimeError("Could not find a trial order satisfying the run-length constraint.")
        blocks.append(block)
        full_sequence.extend(block)

    # Sanity checks (cheap; guard against future edits)
    assert all(full_sequence.count(c) == n_per_condition for c in conditions)
    assert _longest_run(full_sequence) <= max_run
    return blocks


def run_test_phase(win, mouse, clock, screen_width, screen_height, start_pos, target_pos, sampled_image_paths):
    global global_trial_counter



    conditions = {
        'F': {'control': 1.0, 'label': 'Full Control'},
        'M': {'control': experiment_data['test']['control_levels']['medium'],
              'label': f"Medium ({experiment_data['test']['control_levels']['medium']*100:.1f}%)"},
        'L': {'control': experiment_data['test']['control_levels']['low'],
              'label': f"Low ({experiment_data['test']['control_levels']['low']*100:.1f}%)"}
    }

    # ── Trial-wise condition sequence (replaces the 6 counterbalancing
    #    groups of the blocked version) ─────────────────────────────────────
    # Participant-specific, reproducible seed (separate from the image and
    # recognition-order seeds, so those are unchanged).
    part_id = str(experiment_data.get('participant_id', '0'))
    order_seed = int(hashlib.sha256((part_id + '_trialorder').encode()).hexdigest(), 16) & 0xFFFFFFFF
    block_sequences = make_trialwise_sequence(
        N_TEST_TRIALS_PER_CONDITION, TRIALS_PER_MINIBLOCK, order_seed, MAX_SAME_CONDITION_RUN
    )
    total_blocks = len(block_sequences)
    total_trials = N_TEST_TRIALS_PER_CONDITION * 3
    print(f"\nTrial-wise sequence: {total_blocks} miniblocks x {TRIALS_PER_MINIBLOCK} trials "
          f"(max {MAX_SAME_CONDITION_RUN} same-condition trials in a row)")
    for b, blk in enumerate(block_sequences, start=1):
        print(f"  Block {b:>2}: {''.join(blk)}")

    trial_counter = 0
    block_counter = 0
    
    # Track trial counts per condition to match photo_task_2.py repetition pattern
    cond_trial_counts = {'F': 0, 'M': 0, 'L': 0}

    for block_conditions in block_sequences:
        block_counter += 1

        for trial_idx, cond_key in enumerate(block_conditions):
            cond = conditions[cond_key]
            trial_counter    += 1
            global_trial_counter += 1
            cond_trial_counts[cond_key] += 1

            trial_data = run_trial(
                win, mouse, clock, screen_width, screen_height,
                start_pos, target_pos,
                cond['control'], cond['label'],
                cond_trial_counts[cond_key], total_trials,
                image_path=sampled_image_paths[trial_counter - 1],
                phase_name='test',
                condition_key=cond_key
            )
            if trial_data is None:
                return False

            # Track which condition each image was shown under (for recognition triggers)
            image_condition_map[sampled_image_paths[trial_counter - 1]] = cond_key

            trial_data['miniblock_num']       = block_counter
            experiment_data['test']['trials'].append(trial_data)

            thisExp.addData('trial_num',          global_trial_counter)
            thisExp.addData('participant',        expInfo['participant'])
            thisExp.addData('phase',              'test')
            thisExp.addData('block_num',          block_counter)
            thisExp.addData('trial_within_block', trial_idx + 1)
            thisExp.addData('condition',          cond_key)
            thisExp.addData('control_level',      cond['control'])
            thisExp.addData('image_shown',        trial_data.get('image_shown', ''))
            thisExp.addData('duration',           trial_data['duration'])
            thisExp.addData('path_length',        trial_data['path_length'])
            thisExp.addData('mean_deviation',     trial_data['mean_deviation'])
            thisExp.addData('control_rating',     trial_data.get('control_rating', np.nan))
            thisExp.addData('image_id',           trial_data.get('image_id', ''))
            thisExp.addData('first_move_time',    trial_data.get('first_move_time', np.nan))
            thisExp.addData('movement_duration',  trial_data.get('movement_duration', np.nan))
            # Log EEG triggers
            thisExp.addData('trigger_fix',            trial_data.get('trigger_fix', np.nan))
            thisExp.addData('trigger_trial_onset',    trial_data.get('trigger_trial_onset', np.nan))
            thisExp.addData('trigger_first_move',     trial_data.get('trigger_first_move', np.nan))
            thisExp.addData('trigger_shutter',        trial_data.get('trigger_shutter', np.nan))
            thisExp.addData('trigger_reveal_onset',   trial_data.get('trigger_reveal_onset', np.nan))
            thisExp.addData('trigger_reveal_offset',  trial_data.get('trigger_reveal_offset', np.nan))
            thisExp.addData('trigger_agency',         trial_data.get('trigger_agency', np.nan))
            thisExp.nextEntry()

        # Break between miniblocks — self-paced, identical after every block.
        # (Changed 2026-10-23: the former timed 60-s break at the "middle"
        # block — total_blocks // 2, i.e. after block 4 of 9 — was removed so
        # that all between-block breaks are the same.)
        if block_counter < total_blocks:
            break_text = visual.TextStim(
                win=win,
                text=(f"This was the end of Block {block_counter} / {total_blocks}.\n\n"
                      f"Please press SPACE for the next block."),
                color=TEXT_COLOR, height=SCALED_TEXT_HEIGHT, pos=(0, 0), wrapWidth=SCALED_WRAP_WIDTH, bold=True
            )
            break_text.draw(); win.flip()
            keys = event.waitKeys(keyList=['space', 'escape'])
            if 'escape' in keys:
                return False

    return True

# ============================================================================
# RECOGNITION PHASE
# ============================================================================

def run_recognition_phase(win, screen_width, screen_height, seen_images, foil_images):
    global global_trial_counter

    msg = visual.TextStim(
        win=win,
        text=("The main experiment is now complete. One last part!\n\n"
              "You will now see a series of images on the screen, one at a time.\n"
              "For each image, decide whether you saw it during the experiment (Yes) or not (No). "
              "If you have seen the image before (Yes), press [A]. "
              "If you have not seen the image before (No), press [S].\n\n"
              "Please try to respond as accurately as possible. If unsure, make your best guess.\n\n"
              "Please press SPACE to start."),
        color=TEXT_COLOR, height=SCALED_TEXT_HEIGHT, pos=(0, 0), wrapWidth=SCALED_WRAP_WIDTH, bold=True
    )
    msg.draw(); win.flip()
    keys = event.waitKeys(keyList=['space', 'escape'])
    if 'escape' in keys:
        return False

    mem_items = (
        [{'path': p, 'ground_truth': 'seen'}   for p in seen_images] +
        [{'path': p, 'ground_truth': 'unseen'} for p in foil_images]
    )
    _mem_rng.shuffle(mem_items)
    print(f"\nMemory test: {len(mem_items)} items (seen + unseen)")

    mem_img_stim = visual.ImageStim(win, size=(SQUARE_SIZE, SQUARE_SIZE))
    mem_question = visual.TextStim(
        win, text="Have you seen this image during the experiment before?",
        pos=(0, - (SQUARE_SIZE // 2 + 100)), color=TEXT_COLOR, height=SCALED_TEXT_HEIGHT, wrapWidth=SCALED_WRAP_WIDTH, bold=True
    )
    
    # Position keys relatively based on scaled text
    key_y_pos = - (SQUARE_SIZE // 2 + 100 + SCALED_TEXT_HEIGHT * 2)
    mem_key_A = visual.TextStim(win, text="A\nOld", pos=(-(screen_width * 0.15), key_y_pos),
                                height=int(SCALED_TEXT_HEIGHT * 1.3), color=TEXT_COLOR, bold=True, alignText='center')
    mem_key_S = visual.TextStim(win, text="S\nNew", pos=((screen_width * 0.15), key_y_pos),
                                height=int(SCALED_TEXT_HEIGHT * 1.3), color=TEXT_COLOR, bold=True, alignText='center')

    # Fixation cross for inter-trial interval
    fixation_cross = visual.TextStim(win, text='+', pos=(0, 0), color=TEXT_COLOR,
                                     height=int(SCALED_TEXT_HEIGHT * 1.5), bold=True)

    for item_num, item in enumerate(mem_items, start=1):
        global_trial_counter += 1

        # Fixation cross — random duration 0.5–0.8 s
        fix_dur = float(rng.uniform(0.5, 0.8))
        fixation_cross.draw(); win.flip()

        # ── EEG Trigger: Recognition Fixation Onset ─────────────────────────
        if item['ground_truth'] == 'seen':
            _item_cond = image_condition_map.get(item['path'])
            mem_trigger_fix = 80 + TRIGGER_COND_OFFSET.get(_item_cond, 0) if _item_cond else 85
        else:
            mem_trigger_fix = 85
        send_trigger(mem_trigger_fix)

        core.wait(fix_dur)

        mem_img_stim.image = item['path']
        mem_img_stim.pos   = (0, 80)

        event.clearEvents(eventType='keyboard')
        mem_img_stim.draw(); mem_question.draw()
        mem_key_A.draw();    mem_key_S.draw()
        win.flip()

        # ── EEG Trigger: Recognition Image Onset ────────────────────────────
        if item['ground_truth'] == 'seen':
            _item_cond = image_condition_map.get(item['path'])
            mem_trigger_onset = 50 + TRIGGER_COND_OFFSET.get(_item_cond, 0) if _item_cond else 55
        else:
            mem_trigger_onset = 55
        send_trigger(mem_trigger_onset)

        # Screenshot at first recognition item
        if item_num == 1 and 'recognition' not in _screenshots_saved:
            win.getMovieFrame(buffer='front')
            win.saveMovieFrames(str(SCREENSHOTS_DIR / "screenshot_recognition.png"))
            _screenshots_saved.add('recognition')

        item_onset    = core.getTime()
        mem_response  = None
        mem_rt        = np.nan

        while mem_response is None:
            keys = event.getKeys(['a', 's', 'escape'], timeStamped=True)
            if keys:
                key, key_time = keys[0]
                if key == 'escape':
                    return False
                elif key == 'a':
                    mem_response = 'yes'
                    mem_rt       = key_time - item_onset
                    mem_img_stim.draw(); mem_question.draw()
                    mem_key_A.draw();    mem_key_S.draw()
                    win.flip()
                    core.wait(0.5)
                elif key == 's':
                    mem_response = 'no'
                    mem_rt       = key_time - item_onset
                    mem_img_stim.draw(); mem_question.draw()
                    mem_key_A.draw();    mem_key_S.draw()
                    win.flip()
                    core.wait(0.5)
            core.wait(0.01)

        # Reset colors for next trial
        mem_key_A.color = TEXT_COLOR
        mem_key_S.color = TEXT_COLOR

        ground_truth = item['ground_truth']
        mem_correct  = int(
            (mem_response == 'yes' and ground_truth == 'seen') or
            (mem_response == 'no'  and ground_truth == 'unseen')
        )

        # ── EEG Trigger: Recognition Response Accuracy ──────────────────────
        mem_trigger_resp = 61 if mem_correct else 62
        send_trigger(mem_trigger_resp)

        win.flip()  # clear screen; next trial's fixation cross follows immediately

        trial_data = {
            'item_num':    item_num,
            'image_path':  item['path'],
            'image_name':  pathlib.Path(item['path']).name,
            'image_id':    pathlib.Path(item['path']).stem,
            'encoding_condition': image_condition_map.get(item['path'], ''),
            'ground_truth': ground_truth,
            'response':    mem_response,
            'accuracy':    mem_correct,
            'rt':          mem_rt,
            'mem_trigger_fix':   mem_trigger_fix,
            'mem_trigger_onset': mem_trigger_onset,
            'mem_trigger_resp':  mem_trigger_resp,
        }
        experiment_data['recognition']['trials'].append(trial_data)

        thisExp.addData('trial_num',    global_trial_counter)
        thisExp.addData('participant',  expInfo['participant'])
        thisExp.addData('phase',        'recognition')
        thisExp.addData('item_num',     item_num)
        thisExp.addData('image_name',   trial_data['image_name'])
        thisExp.addData('image_id',     trial_data['image_id'])
        thisExp.addData('ground_truth', ground_truth)
        thisExp.addData('response',     mem_response)
        thisExp.addData('accuracy',     mem_correct)
        thisExp.addData('rt',           mem_rt)
        thisExp.addData('mem_trigger_fix',   mem_trigger_fix)
        thisExp.addData('mem_trigger_onset', mem_trigger_onset)
        thisExp.addData('mem_trigger_resp',  mem_trigger_resp)
        thisExp.addData('encoding_condition', image_condition_map.get(item['path'], ''))
        thisExp.nextEntry()

        if item_num % 100 == 0 and item_num < len(mem_items):
            BREAK_DURATION = 30.0
            break_clock = core.Clock()
            event.clearEvents(eventType='keyboard')
            while break_clock.getTime() < BREAK_DURATION:
                remaining = int(BREAK_DURATION - break_clock.getTime()) + 1
                msg.text = (f"Take a short break if needed.\n\n"
                            f"The experiment will continue automatically in {remaining} s.\n\n"
                            f"Press SPACE to continue earlier.")
                msg.draw(); win.flip()
                keys = event.getKeys(['space', 'escape'])
                if 'escape' in keys:
                    return False
                if 'space' in keys:
                    break
                core.wait(0.1)

    return True


# ============================================================================
# MAIN EXPERIMENT
# ============================================================================

def main():
    """Main experiment loop."""
    # Participant info comes from module-level GUI dialog (expInfo)
    experiment_data['participant_id'] = expInfo['participant']
    experiment_data['age']            = expInfo.get('age', '')
    experiment_data['gender']         = expInfo.get('gender', '')
    experiment_data['handedness']     = expInfo.get('handedness', '')
    experiment_data['timestamp']      = datetime.now().isoformat()

    # Create a participant-specific random number generator seeded by participant ID
    # (Matching CDmem_1.py patterns exactly)
    global rng, _mem_rng
    seed = int(hashlib.sha256(expInfo["participant"].encode()).hexdigest(), 16) & 0xFFFFFFFF
    rng = np.random.default_rng(seed)
    
    # Memory shuffling RNG (using separate MD5-based seed like CDmem_1.py)
    _mem_seed = int(hashlib.md5((expInfo['participant'] + '_mem').encode()).hexdigest(), 16) % (2**32)
    _mem_rng = random.Random(_mem_seed)

    # Initialize PsychoPy
    win          = visual.Window(fullscr=True, units='pix', color=BACKGROUND_COLOR, allowGUI=False)
    win.setMouseVisible(False)
    screen_width, screen_height = win.size
    mouse        = event.Mouse(visible=False, win=win)

    # Force-hide the Windows system cursor (PsychoPy's method is unreliable on Windows)
    if sys.platform.startswith('win'):
        import ctypes
        ctypes.windll.user32.ShowCursor(False)
    clock        = core.Clock()

    global SQUARE_SIZE, SCALED_TEXT_HEIGHT, SCALED_WRAP_WIDTH, FRAME_SIZE
    SQUARE_SIZE = vis_ang_to_pix(STIM_SZ_DEG, DIST_CM, WIDTH_CM, screen_width)
    FRAME_SIZE = int(SQUARE_SIZE * 1.5) # Dynamic margin: frame is safely larger than target
    SCALED_TEXT_HEIGHT = 26
    SCALED_WRAP_WIDTH  = 1000

    target_pos = (0,  screen_height // 3)
    start_pos  = (0, -screen_height // 3)

    # Phase 1: Calibration
    if not show_instructions(win, screen_width, screen_height, 'calibration'):
        _save(); win.close(); core.quit(); return

    if not run_calibration_phase(win, mouse, clock, screen_width, screen_height, start_pos, target_pos):
        _save(); win.close(); core.quit(); return

    extract_calibration_results()

    if not show_calibration_results(win, screen_width, screen_height):
        _save(); win.close(); core.quit(); return

    # Phase 2: Test
    total_test_trials = N_TEST_TRIALS_PER_CONDITION * 3
    n_foils = total_test_trials  # 1:1 ratio for recognition (old vs new)
    # Fixed seed ensures all participants get the same image set
    sampled_image_paths, foil_image_paths = sample_images(total_test_trials, n_foils, IMAGE_SEED)

    # Shuffle test image order per participant (participant-specific seed)
    _img_order_rng = random.Random(seed)
    _img_order_rng.shuffle(sampled_image_paths)

    if not run_test_phase(win, mouse, clock, screen_width, screen_height, start_pos, target_pos, sampled_image_paths):
        _save(); win.close(); core.quit(); return

    # Phase 3: Recognition
    if not run_recognition_phase(win, screen_width, screen_height, sampled_image_paths, foil_image_paths):
        _save(); win.close(); core.quit(); return

    # Save both CSV and JSON
    _save()

    # Print final control summary
    control_med = experiment_data['test']['control_levels']['medium']
    control_low = experiment_data['test']['control_levels']['low']
    print("\n" + "="*60)
    print("FINAL CONTROL LEVELS")
    print("="*60)
    print(f"Medium difficulty: {control_med*100:.1f}% control")
    print(f"Low difficulty:    {control_low*100:.1f}% control")
    print("="*60 + "\n")

    completion_text = visual.TextStim(
        win=win,
        text=(
              f"All done! Thank you for participating!\n\n"
              f"Press any key to exit"),
        color=TEXT_COLOR, height=SCALED_TEXT_HEIGHT, pos=(0, 0), wrapWidth=SCALED_WRAP_WIDTH, bold=True
    )
    completion_text.draw(); win.flip()
    event.waitKeys()
    win.close(); core.quit()


if __name__ == "__main__":
    main()
