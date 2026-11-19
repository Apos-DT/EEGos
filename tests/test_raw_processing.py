import json
import tempfile
import unittest
from pathlib import Path
import numpy as np
from scipy.io import savemat
from eeg_emostudio.data.raw_processing import RawConfig, clean_trial, window_starts, trial_variables, process_raw
from eeg_emostudio.data.seed_iv import SESSION_LABELS


class RawProcessingTests(unittest.TestCase):
    def test_input_units_are_explicit_and_equivalent(self):
        x=np.random.default_rng(5).normal(0,20,(62,1000))
        a,_=clean_trial(x,RawConfig(unit="uV"))
        b,_=clean_trial(x*1e-6,RawConfig(unit="V"))
        np.testing.assert_allclose(a,b,atol=1e-8)

    def test_strict_nyquist_and_no_duplicate_scope(self):
        for config in [RawConfig(target_fs=100),RawConfig(subjects=(1,1)),RawConfig(low=4),RawConfig(ica_mode="review",subjects=(1,2))]:
            with self.assertRaises(ValueError):config.validate()

    def test_no_window_padding_or_boundary_crossing(self):
        starts,width=window_starts(799,200,4,4,0)
        self.assertEqual(width,800);self.assertEqual(len(starts),0)
        starts,width=window_starts(1601,200,4,4,0)
        self.assertEqual(starts.tolist(),[0,800])

    def test_eeglab_boundary_events_keep_correct_labels(self):
        from eeg_emostudio.data.eeglab import process_eeglab_set
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); source=root/"sample.set"
            eeg={"data":np.random.default_rng(8).normal(0,5,(4,2400)),"srate":200.,"nbchan":4,"pnts":2400,
                 "event":np.array([{"latency":1.,"type":"1"},{"latency":401.,"type":"2"}],dtype=object)}
            savemat(source,{"EEG":eeg})
            process_eeglab_set(source,root/"out",bandpass=(1,40),notch_hz=None,target_fs=100,epoch_start=-.2,epoch_end=2,reject_uv=1000)
            with np.load(root/"out/raw.npz") as f:self.assertEqual(f["y"].tolist(),[1])
            with np.load(root/"out/eeg_clean.npz") as f:self.assertEqual(f["event_latencies"].tolist(),[1,201])

    def test_real_mat_contract_and_subject_trial_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/"eeg_raw_data/1";source.mkdir(parents=True)
            rng=np.random.default_rng(9)
            for subject in (1,2):
                savemat(source/f"{subject}_test.mat",{f"sample_eeg{trial}":rng.normal(size=(62,800))*10 for trial in range(1,25)})
            output=root/"result"
            cfg=RawConfig(subjects=(1,2),notch=0,reref="none",edge=0,reject_uv=0,flat_uv=0,window=2,step=2)
            result=process_raw(root,output,cfg,log=lambda *a,**k:None)
            self.assertEqual(result["n_samples"],96)
            with np.load(output/"features.npz",allow_pickle=False) as f:
                self.assertEqual(f["x"].shape,(96,62,5))
                self.assertEqual(set(f["subjects"]),{"S01","S02"})
                self.assertEqual(len(set(f["trial_ids"])),48)
                self.assertEqual(f["y"][:48].tolist(),np.repeat(SESSION_LABELS[1],2).tolist())
            self.assertEqual(result["status"],"success")
            self.assertTrue((output/"spectrum.png").exists())
            savemat(source/"bad.mat",{"de_LDS1":np.zeros((62,2,5))})
            with self.assertRaises(ValueError):trial_variables(source/"bad.mat")


if __name__=="__main__":unittest.main()
