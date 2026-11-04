# Photo Shooting Experiment

This repository contains the experimental code, stimuli, background literature, and course documents for the **Photo Shooting Experiment**, conducted by LMU-NCP students as part of their Lab Rotation during the Winter Semester 2026/27.

## Repository Structure

```
.
├── experiment/
│   ├── CARA_B_main_trialwise.py
│   ├── CODE_GUIDE.md
│   └── chosen_stimuli_nolures/
├── papers/
├── NCP Lab Rotation Project Evaluation WS_2026-27.docx
├── PreregistrationTemplate.docx
└── README.md
```

| Path | Description |
|------|-------------|
| `experiment/` | Everything needed to run the experiment. |
| `experiment/CARA_B_main_trialwise.py` | The experimental code used to run the experiment (PsychoPy). |
| [`experiment/CODE_GUIDE.md`](experiment/CODE_GUIDE.md) | A walkthrough of the experiment and the code. |
| `experiment/chosen_stimuli_nolures/` | The stimulus images shown during the experiment, plus `stimuli_list.csv`. |
| `papers/` | Background literature on sense of agency and its relation to memory. |
| `NCP Lab Rotation Project Evaluation WS_2026-27.docx` | Evaluation criteria for the lab rotation project. |
| `PreregistrationTemplate.docx` | Template for preregistering your study. |

## Running the Experiment

Run `experiment/CARA_B_main_trialwise.py` with PsychoPy. The script locates the stimuli relative to its own location, so keep `chosen_stimuli_nolures/` in the same folder as the script. Participant data are saved to `experiment/trialwise_data/`, which is created automatically on the first run.

## Background Literature

The `papers/` folder contains two groups of papers:

1) What is SoA?
- Chambon et al. (2014). From action intentions to action effects: How does the sense of agency come about?
- Moore (2016). What is the sense of agency and why does it matter?
- Haggard & Chambon (2012). Sense of agency.
- Haggard (2017). Sense of agency in the human brain.
- Hon & Yeo (2021). Having a sense of agency can improve memory.
2) SoA & Recognition Memory
- Cheng et al. (2023). The effect of choice on memory: The role of theta oscillations.
- Schreiner et al. (2024). Linking actions and memories: Probing the interplay of action-effect congruency, agency experience, and recognition memory.
- Tsuji & Imaizumi (2022). Sense of agency may not improve recollection and familiarity in recognition memory.
- Zhu et al. (2026). Sense of agency promotes recognition memory: The role of self-referential processing.

## Stimuli

The stimuli were sampled from the THINGS database. If you use these stimuli, please cite:

- Hebart, M. N., Dickter, A. H., Kidder, A., Kwok, W. Y., Corriveau, A., Wicklin, C. V., & Baker, C. I. (2019). THINGS: A database of 1,854 object concepts and more than 26,000 naturalistic object images. *PLOS ONE, 14*(10), e0223792. [https://doi.org/10.1371/journal.pone.0223792](https://doi.org/10.1371/journal.pone.0223792)
- Stoinski, L. M., Perkuhn, J., & Hebart, M. N. (2024). THINGSplus: New norms and metadata for the THINGS database of 1854 object concepts and 26,107 natural object images. *Behavior Research Methods, 56*(3), 1583–1603. [https://doi.org/10.3758/s13428-023-02110-8](https://doi.org/10.3758/s13428-023-02110-8)
