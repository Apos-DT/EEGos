"""Trial-aware SEED-IV raw EEG pipeline. No model/torch dependency.

Signals remain in microvolts internally; MNE receives volts explicitly.
All filtering is per original trial, before windowing; windows never cross trials.
"""
from __future__ import annotations
import argparse
import csv
import html
import json
import platform
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from fractions import Fraction
from pathlib import Path
from typing import Callable
import numpy as np
import scipy
from scipy import signal
from scipy.io import loadmat, whosmat
from .seed_iv import CHANNELS, SESSION_LABELS, CLASS_NAMES_ZH
from .manifest import sha256_file, write_feature_dataset

BANDS = {"delta":(1.,4.),"theta":(4.,8.),"alpha":(8.,14.),"beta":(14.,31.),"gamma":(31.,50.)}


def now(): return datetime.now().astimezone().isoformat(timespec="seconds")


def save(path, value):
    path=Path(path); tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding="utf-8"); tmp.replace(path)


@dataclass
class RawConfig:
    sessions: tuple = (1,)
    subjects: tuple = (1,)
    fs: float = 200.
    unit: str = "uV"
    low: float = 1.
    high: float = 75.
    notch: float = 50.
    target_fs: float = 200.
    reref: str = "car"
    window: float = 4.
    step: float = 4.
    edge: float = 1.
    reject_uv: float = 200.
    flat_uv: float = .1
    bad_channels: tuple = ()
    save_windows: bool = False
    ica_mode: str = "off"
    ica_components: int = 20
    ica_reference: str = ""
    ica_exclude: tuple = ()
    seed: int = 42

    def validate(self):
        if len(set(self.sessions))!=len(self.sessions) or len(set(self.subjects))!=len(self.subjects): raise ValueError("会话或被试不能重复")
        if not self.sessions or not self.subjects or any(s not in (1,2,3) for s in self.sessions) or any(not 1<=s<=15 for s in self.subjects): raise ValueError("会话应为 1–3，被试应为 1–15")
        if not 100<=self.fs<=5000 or not 100<=self.target_fs<=self.fs: raise ValueError("采样率应满足 100 ≤ 目标采样率 ≤ 原始采样率 ≤ 5000")
        if not 0<self.low<self.high<min(self.fs,self.target_fs)/2: raise ValueError("截止频率应满足 0 < low < high < 输入及输出 Nyquist")
        if self.low>1 or self.high<50: raise ValueError("当前五频带特征需要完整的 1–50 Hz 通带")
        if self.notch and not 0<self.notch<min(self.fs,self.target_fs)/2: raise ValueError("陷波频率应小于 Nyquist，或填 0 关闭")
        if not .5<=self.window<=30 or not .5<=self.step<=self.window or not 0<=self.edge<=5: raise ValueError("窗口/步长/边界裁剪参数不合法")
        if self.reject_uv<0 or self.flat_uv<0 or self.unit not in ("uV","V") or self.reref not in ("none","car"): raise ValueError("单位、参考或质量阈值不合法")
        if not set(self.bad_channels).issubset(CHANNELS) or len(set(self.bad_channels))>12: raise ValueError("坏导需来自官方通道名，最多移除 12 导")
        if self.ica_mode not in ("off","review","apply"): raise ValueError("未知 ICA 模式")
        if self.ica_mode!="off" and len(self.subjects)*len(self.sessions)!=1: raise ValueError("ICA 审阅/应用限定单被试单会话，避免跨分解误用成分编号")
        if self.ica_mode=="apply" and (not self.ica_reference or not self.ica_exclude): raise ValueError("ICA 应用需提供已审阅任务和排除成分")
        if not 2<=self.ica_components<=40 or any(not 0<=i<40 for i in self.ica_exclude): raise ValueError("ICA 成分设置不合法")


def raw_file(root, session, subject):
    files=list((Path(root)/"eeg_raw_data"/str(session)).glob(f"{subject}_*.mat"))
    if len(files)!=1: raise ValueError(f"会话 {session} 被试 {subject} 需要恰好一个原始 MAT，实际 {len(files)}")
    return files[0]


def trial_variables(path):
    result=[]
    for name,shape,dtype in whosmat(path):
        match=re.fullmatch(r"[A-Za-z0-9_]*eeg(\d+)",name)
        if match and 1<=int(match[1])<=24:
            if len(shape)!=2 or shape[0]!=62 or shape[1]<200: raise ValueError(f"{name} 应为62通道原始矩阵，实际{shape}")
            result.append({"name":name,"trial":int(match[1]),"shape":list(shape),"dtype":dtype})
    result.sort(key=lambda r:r["trial"])
    if [r["trial"] for r in result]!=list(range(1,25)): raise ValueError("需要完整且不重复的 eeg1–eeg24，不能把官方特征 MAT 当作原始数据")
    return result


def inspect_raw(root, session, subject):
    path=raw_file(root,session,subject); variables=trial_variables(path)
    for v in variables: v.update(label=SESSION_LABELS[session][v["trial"]-1],duration_seconds=round(v["shape"][1]/200,3))
    x=np.asarray(loadmat(path,variable_names=[variables[0]["name"]])[variables[0]["name"]],dtype=float)
    if not np.isfinite(x).all(): raise ValueError("预览 trial 含 NaN/Inf")
    samples=np.arange(0,min(x.shape[1],4000),4)
    return {"filename":path.name,"size_mb":round(path.stat().st_size/2**20,1),"session":session,"subject":subject,
        "n_channels":62,"n_trials":24,"fs":200,"unit":"uV","channels":CHANNELS,"class_names":CLASS_NAMES_ZH,
        "metadata_basis":"采样率依据 SEED-IV 官方发布协议；单位作为用户确认的输入假设，MAT 未内嵌单位。通道顺序对应本机 Channel Order.xlsx。",
        "variables":variables,"duration_seconds":round(sum(v["shape"][1] for v in variables)/200,2),
        "preview":{"times":(samples/200).tolist(),"channels":CHANNELS[:4],"values":x[:4,samples].tolist()}}


def window_starts(n, fs, window, step, edge):
    width=int(round(window*fs)); stride=int(round(step*fs)); trim=int(round(edge*fs))
    return np.arange(trim,max(trim,n-trim-width+1),stride,dtype=int),width


def clean_trial(x, cfg):
    if x.ndim!=2 or x.shape[0]!=62 or not np.isfinite(x).all(): raise ValueError("原始 trial 形状异常或含 NaN/Inf")
    x=np.asarray(x,dtype=float)*(1e6 if cfg.unit=="V" else 1.)
    picks=[i for i,c in enumerate(CHANNELS) if c not in cfg.bad_channels]
    x=x[picks]
    sos=signal.butter(4,[cfg.low,cfg.high],fs=cfg.fs,btype="bandpass",output="sos")
    clean=signal.sosfiltfilt(sos,x,axis=-1)
    if cfg.notch:
        b,a=signal.iirnotch(cfg.notch,Q=30.,fs=cfg.fs); clean=signal.filtfilt(b,a,clean,axis=-1)
    if cfg.reref=="car": clean-=clean.mean(axis=0,keepdims=True)
    if cfg.target_fs!=cfg.fs:
        ratio=Fraction(cfg.target_fs/cfg.fs).limit_denominator(10000)
        clean=signal.resample_poly(clean,ratio.numerator,ratio.denominator,axis=-1)
    return clean,[CHANNELS[i] for i in picks]


def qc_windows(x, cfg):
    starts,width=window_starts(x.shape[1],cfg.target_fs,cfg.window,cfg.step,cfg.edge)
    keep=[]; records=[]
    for start in starts:
        w=x[:,start:start+width]; ptp=float(np.ptp(w,axis=1).max()); flat=int((w.std(axis=1)<cfg.flat_uv).sum()) if cfg.flat_uv else 0
        ok=(not cfg.reject_uv or ptp<=cfg.reject_uv) and not flat
        keep.append(ok); records.append({"start_s":round(start/cfg.target_fs,4),"max_ptp_uv":round(ptp,4),"flat_channels":flat,"accepted":bool(ok)})
    return starts,width,np.asarray(keep,dtype=bool),records


def de_windows(x, starts, width, fs):
    out=np.empty((len(starts),x.shape[0],5),dtype=np.float32)
    for i,(low,high) in enumerate(BANDS.values()):
        filtered=signal.sosfiltfilt(signal.butter(4,[low,high],fs=fs,btype="bandpass",output="sos"),x,axis=-1)
        for j,start in enumerate(starts): out[j,:,i]=.5*np.log(2*np.pi*np.e*np.maximum(filtered[:,start:start+width].var(axis=1),1e-12))
    return out


def _figures(before, after, cfg, channels, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(4,1,figsize=(11,6),sharex=True)
    for i,ax in enumerate(axes):
        n=min(before.shape[1],int(10*cfg.fs)); m=min(after.shape[1],int(10*cfg.target_fs))
        ax.plot(np.arange(n)/cfg.fs,before[i,:n],color="#b7bfc5",lw=.6,label="Input")
        ax.plot(np.arange(m)/cfg.target_fs,after[i,:m],color="#138677",lw=.6,label="Processed")
        ax.set_ylabel(channels[i]+" (uV)",fontsize=8); ax.grid(alpha=.15)
    axes[0].legend(fontsize=8);axes[-1].set_xlabel("Time (s)");fig.tight_layout();fig.savefig(out/"waveform.png",dpi=130);plt.close(fig)
    fig,ax=plt.subplots(figsize=(10,3))
    for array,fs,label,color in [(before,cfg.fs,"Input","#9aa7b0"),(after,cfg.target_fs,"Processed","#138677")]:
        f,p=signal.welch(array,fs=fs,nperseg=min(int(fs*2),array.shape[1]),axis=-1)
        ax.plot(f,10*np.log10(p.mean(axis=0)+1e-20),label=label,color=color)
    ax.set(xlim=(0,min(100,cfg.target_fs/2)),xlabel="Frequency (Hz)",ylabel="PSD (dB uV²/Hz)");ax.legend();ax.grid(alpha=.15)
    fig.tight_layout();fig.savefig(out/"spectrum.png",dpi=130);plt.close(fig)


def ica_process(cleaned, cfg, channels, out, source_hash):
    import mne
    from mne.preprocessing import ICA, read_ica
    info=mne.create_info(channels,cfg.target_fs,ch_types="eeg")
    profile={k:v for k,v in asdict(cfg).items() if k in ("fs","unit","low","high","notch","target_fs","reref","bad_channels","sessions","subjects")}
    # JSON normalizes tuples to lists for equality with a persisted profile.
    profile=json.loads(json.dumps(profile))
    if cfg.ica_mode=="apply":
        ref=Path(cfg.ica_reference)
        previous=json.loads((ref/"ica_profile.json").read_text(encoding="utf-8"))
        if previous.get("n_iter",0)>=500: raise ValueError("参考 ICA 分解未收敛，请调整成分数或质量阈值后重新拟合审阅")
        if previous["profile"]!=profile or previous["source_sha256"]!=source_hash: raise ValueError("ICA 参考任务的数据版本或预处理参数不一致，需重新审阅")
        ica=read_ica(ref/"review-ica.fif",verbose="ERROR")
        if max(cfg.ica_exclude)>=ica.n_components_: raise ValueError("排除的成分编号超过该分解成分数")
        for i,data in enumerate(cleaned):
            raw=mne.io.RawArray(data*1e-6,info,verbose="ERROR")
            ica.apply(raw,exclude=list(cfg.ica_exclude),verbose="ERROR");cleaned[i]=raw.get_data()*1e6
        return {"mode":"apply","components":ica.n_components_,"excluded":list(cfg.ica_exclude),"reference":ref.name}
    chunks=[]
    for data in cleaned:
        starts,width,keep,_=qc_windows(data,cfg)
        for start in starts[keep]:
            chunks.append(data[:,start:start+width])
            if len(chunks)>=120: break
        if len(chunks)>=120: break
    if len(chunks)*cfg.window<60: raise ValueError("ICA 拟合至少需要60秒通过当前质量阈值的窗口，请检查数据和阈值")
    epochs=mne.EpochsArray(np.stack(chunks)*1e-6,info,tmin=0,baseline=None,verbose="ERROR")
    epochs.filter(l_freq=1,h_freq=None,method="iir",verbose="ERROR")
    ica=ICA(n_components=min(cfg.ica_components,len(channels)-1),method="fastica",random_state=cfg.seed,max_iter=500)
    ica.fit(epochs,verbose="ERROR");ica.save(out/"review-ica.fif",overwrite=True,verbose="ERROR")
    components=ica.get_sources(epochs[:1]).get_data()[0]
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(len(components),1,figsize=(10,max(4,len(components)*.6)),sharex=True)
    for i,ax in enumerate(np.atleast_1d(axes)):
        ax.plot(np.arange(components.shape[1])/cfg.target_fs,components[i],lw=.7,color="#138677");ax.set_ylabel(f"IC{i}",fontsize=8);ax.set_yticks([])
    fig.tight_layout();fig.savefig(out/"ica_components.png",dpi=110);plt.close(fig)
    save(out/"ica_profile.json",{"profile":profile,"source_sha256":source_hash,"n_components":int(ica.n_components_),"n_iter":int(ica.n_iter_)})
    return {"mode":"review","components":int(ica.n_components_),"n_iter":int(ica.n_iter_),"converged":bool(ica.n_iter_<500),"excluded":[],"note":"已保存固定分解供审阅；本次不移除成分。查看成分波形并在应用模式引用此任务。不能只凭波形判定脑源/伪迹。"}


def process_raw(root, out, cfg, log: Callable=print):
    cfg.validate(); root=Path(root);out=Path(out);out.mkdir(parents=True,exist_ok=False)
    started=now();clock=time.monotonic();records=[]; all_features=[];ys=[];subjects=[];sessions=[];trials=[];offsets=[];raw_windows=[];source_records=[];qc_channel=[];ica_info=None
    report={"status":"running","run_id":out.name,"started_at":started,"config":asdict(cfg),"dataset":"SEED-IV raw","fs_basis":"SEED-IV official distribution: 200 Hz; unit is a user-confirmed assumption (no unit field in MAT).","processing":{"filter":"4th-order Butterworth SOS, forward-backward zero phase, per original trial","notch_Q":30,"resampling":"scipy.signal.resample_poly anti-alias polyphase FIR","de":"0.5 * ln(2*pi*e*population_variance), uV input, band-filter before windowing","channel_flags":"flat std or robust log-std outliers; review only, no automatic interpolation"},"bands":BANDS,"class_names":CLASS_NAMES_ZH,"pipeline_sha256":sha256_file(Path(__file__)),"label_source":"SEED-IV ReadMe.txt session-specific labels; Channel Order.xlsx verified against CHANNELS","environment":{"python":platform.python_version(),"numpy":np.__version__,"scipy":scipy.__version__},"trials":records,"sources":source_records}
    save(out/"eeg_report.json",report)
    try:
        for session in cfg.sessions:
            for subject in cfg.subjects:
                path=raw_file(root,session,subject);variables=trial_variables(path)
                log(f"[load] session={session} subject=S{subject:02d} file={path.name}",flush=True)
                fingerprint=sha256_file(path);source_records.append({"path":str(path),"size_bytes":path.stat().st_size,"sha256":fingerprint})
                mat=loadmat(path,variable_names=[v["name"] for v in variables]);cleaned=[];clean_starts=[]
                for v in variables:
                    clean_starts.append(now())
                    data,channels=clean_trial(mat[v["name"]],cfg);cleaned.append(data)
                if cfg.ica_mode!="off":
                    log(f"[ICA] {cfg.ica_mode}: fitting/reusing a recording-specific decomposition",flush=True)
                    ica_info=ica_process(cleaned,cfg,channels,out,fingerprint)
                    report["environment"]["mne"]=__import__('mne').__version__
                for v,clean,started_trial in zip(variables,cleaned,clean_starts):
                    trial=v["trial"];label=SESSION_LABELS[session][trial-1]
                    before=np.asarray(mat[v["name"]],dtype=float)*(1e6 if cfg.unit=="V" else 1)
                    picks=[i for i,c in enumerate(CHANNELS) if c not in cfg.bad_channels]; before=before[picks]
                    std=before.std(axis=1);median=np.median(np.log(np.maximum(std,1e-12)));mad=np.median(np.abs(np.log(np.maximum(std,1e-12))-median))
                    for i,c in enumerate(channels):
                        qc_channel.append({"session":session,"subject":subject,"trial":trial,"channel":c,"std_uv":round(float(std[i]),5),"ptp_uv":round(float(np.ptp(before[i])),5),"flag":bool(std[i]<cfg.flat_uv or abs(np.log(max(std[i],1e-12))-median)>max(5*1.4826*mad,1.))})
                    starts,width,keep,windows=qc_windows(clean,cfg)
                    accepted=starts[keep]
                    if len(accepted):
                        x=de_windows(clean,accepted,width,cfg.target_fs);all_features.append(x)
                        ys.extend([label]*len(x));subjects.extend([f"S{subject:02d}"]*len(x));sessions.extend([f"session{session}"]*len(x));trials.extend([f"S{subject:02d}_session{session}_T{trial:02d}"]*len(x));offsets.extend((accepted/cfg.target_fs).tolist())
                        if cfg.save_windows: raw_windows.extend([clean[:,n:n+width].astype(np.float32) for n in accepted])
                    records.append({"session":session,"subject":subject,"trial":trial,"label":label,"input_samples":v["shape"][1],"output_samples":clean.shape[1],"windows_total":len(starts),"windows_kept":int(keep.sum()),"windows_rejected":int((~keep).sum()),"started_at":started_trial,"finished_at":now(),"windows":windows})
                    log(f"[trial] session={session} S{subject:02d} T{trial:02d} label={label} accepted={int(keep.sum())}/{len(keep)}",flush=True)
                    if len(records)==1: _figures(before,clean,cfg,channels,out)
                    save(out/"progress.json",{"done_trials":len(records),"total_trials":len(cfg.sessions)*len(cfg.subjects)*24,"at":now()})
                del mat,cleaned
        if not all_features: raise ValueError("没有窗口通过质量检查；请查看拒绝记录并复核单位、坏导和阈值，不会生成空训练集")
        meta={"source":"SEED-IV raw","sessions":list(cfg.sessions),"channels":channels,"window_seconds":cfg.window,"step_seconds":cfg.step,"n_trials":len(records),"config":asdict(cfg),"source_files":source_records,"units":"DE computed from microvolt signals, natural logarithm","note":"Recomputed DE without LDS smoothing; not equivalent to official de_LDS. Keep all windows from a trial/subject in one evaluation split."}
        write_feature_dataset(out/"features.npz",np.concatenate(all_features),np.asarray(ys),subjects,sessions=sessions,trial_ids=trials,class_names=CLASS_NAMES_ZH,feature_names=list(BANDS),metadata=meta)
        np.savez_compressed(out/"window_index.npz",subjects=np.asarray(subjects),sessions=np.asarray(sessions),trial_ids=np.asarray(trials),start_seconds=np.asarray(offsets))
        if cfg.save_windows: np.savez_compressed(out/"raw.npz",x=np.stack(raw_windows),y=np.asarray(ys),subjects=np.asarray(subjects),sessions=np.asarray(sessions),trial_ids=np.asarray(trials),fs=cfg.target_fs,channel_names=np.asarray(channels))
        with (out/"channel_qc.csv").open("w",encoding="utf-8-sig",newline="") as f:
            writer=csv.DictWriter(f,fieldnames=list(qc_channel[0]));writer.writeheader();writer.writerows(qc_channel)
        report.update(status="success",n_subjects=len(set(subjects)),n_samples=len(ys),n_channels=len(channels),channels=channels,n_trials=len(records),n_rejected=sum(r["windows_rejected"] for r in records),n_windows_total=sum(r["windows_total"] for r in records),class_counts={CLASS_NAMES_ZH[i]:ys.count(i) for i in range(4)},flagged_channel_records=sum(r["flag"] for r in qc_channel),ica=ica_info)
        report["files"]=[p.name for p in out.iterdir() if p.is_file() and p.name not in ("eeg_report.json.tmp",)]+["report.html"]
    except Exception as exc:
        report.update(status="failed",error=f"{type(exc).__name__}: {exc}");raise
    finally:
        report.update(finished_at=now(),elapsed_seconds=round(time.monotonic()-clock,3));save(out/"eeg_report.json",report)
        header="<h1>SEED-IV 原始 EEG 处理报告</h1>"
        header+=f"<p>任务 {html.escape(out.name)} · 状态 {html.escape(report['status'])} · 有效窗口 {report.get('n_samples',0)} · 拒绝窗口 {report.get('n_rejected',0)}</p><p>开始 {started} · 结束 {report['finished_at']} · 耗时 {report['elapsed_seconds']} 秒</p>"
        body="<details><summary>完整参数、输入文件指纹与逐窗口质量记录</summary><pre>"+html.escape(json.dumps(report,ensure_ascii=False,indent=2))+"</pre></details>"
        plots=''.join(f'<h2>{title}</h2><img style="max-width:100%" src="{file}">' for title,file in [("首个 trial 波形","waveform.png"),("首个 trial 平均功率谱","spectrum.png"),("ICA 成分审阅","ica_components.png")] if (out/file).exists())
        (out/"report.html").write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>原始 EEG 处理报告</title><style>body{font:14px/1.7 system-ui;max-width:1100px;margin:24px auto;padding:16px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f7f8;padding:20px;border-radius:12px}</style>'+header+plots+body+'</html>',encoding="utf-8")
    return report


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--request",required=True)
    args=parser.parse_args();request=json.loads(Path(args.request).read_text(encoding="utf-8"))
    process_raw(request["root"],request["output"],RawConfig(**request["config"]))
