# Experiment

This folder contains everything needed to run the **Photo Shooting Experiment**.

## Contents

| Path | Description |
|------|-------------|
| `CARA_B_main_trialwise.py` | The experimental code used to run the experiment (PsychoPy). |
| [`CODE_GUIDE.md`](CODE_GUIDE.md) | A walkthrough of the experiment and the code. |
| `chosen_stimuli_nolures/` | The stimulus images shown during the experiment, plus `stimuli_list.csv`. |

## Running the Experiment

Run `CARA_B_main_trialwise.py` with PsychoPy. The script locates the stimuli relative to its own location, so keep `chosen_stimuli_nolures/` in the same folder as the script. Participant data are saved to `trialwise_data/`, which is created automatically on the first run.

## Stimuli

The stimuli were sampled from the THINGS database. If you use these stimuli, please cite:

- Hebart, M. N., Dickter, A. H., Kidder, A., Kwok, W. Y., Corriveau, A., Wicklin, C. V., & Baker, C. I. (2019). THINGS: A database of 1,854 object concepts and more than 26,000 naturalistic object images. *PLOS ONE, 14*(10), e0223792. [https://doi.org/10.1371/journal.pone.0223792](https://doi.org/10.1371/journal.pone.0223792)
- Stoinski, L. M., Perkuhn, J., & Hebart, M. N. (2024). THINGSplus: New norms and metadata for the THINGS database of 1854 object concepts and 26,107 natural object images. *Behavior Research Methods, 56*(3), 1583–1603. [https://doi.org/10.3758/s13428-023-02110-8](https://doi.org/10.3758/s13428-023-02110-8)

