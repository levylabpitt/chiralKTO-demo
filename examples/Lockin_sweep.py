'''
FLEX Script: Lockin Sweep with Transport Server
'''
#%% - Imports
from flex.exp.CESession import CESession
import time

#%% - Sweep
exp_folder = '03 - 0408_IVSweep_withLight'
exp_comments = \
"""\
T = 6K
I+/- = 1/3
V+/- = 4/5
BG -1V
"""
sweep_config = {'sweepTime': 30, # seconds
       'initialWaitTime': 1, # seconds
       'returnToStart': False,
       'sweepChannels': [{'Enable?': True,
                          'Channel': 1,
                          'Start': -0.1,
                          'End': 0.1,
                          'Pattern': 'Ramp /\\',
                          'Table': [1]}
                          # add more channels here if needed
                          ]}
with CESession() as exp:
    exp.Transport.LockinSweep(exp_folder, exp_comments, sweep_config, run_continuous = False)

# %%
import numpy as np
import matplotlib.pyplot as plt
from nptdms import TdmsFile

tdms_path = r"G:\.shortcut-targets-by-id\0B8-gGFa6hkR4XzJJMDlqZXVKRk0\ansom\Data\THz 1\SA40751.20260327\01 - IV Sweep_withLight\SA40751.20260327.000000.tdms"
tdms = TdmsFile.read(tdms_path)
group = tdms["Data.000000"]
Iplus = group["AO1"].data
Iminus = group["AI4"].data
Vplus = group["AI3"].data
Vminus = group["AI5"].data


fig, axes = plt.subplots(2, 1, figsize=(8, 10))

# (1) 2T IV
axes[0].plot(Iplus, Iminus)
axes[0].set_ylabel("Current (A)")
axes[0].set_title("2T IV")
axes[0].grid(True, alpha=0.3)

# (2) Resistance vs Time
axes[1].plot(Vplus-Vminus, Iminus)
axes[1].set_ylabel("Current (A)")
axes[1].set_title(f"4T IV")
axes[1].grid(True, alpha=0.3)

# Optional: log scale
# axes[2].set_yscale('log')
plt.tight_layout()
plt.show()
# %%
